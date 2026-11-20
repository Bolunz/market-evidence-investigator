"""API smoke test: small, cheap checks before a full live run.

  1 environment   .env found and loaded; key source reported (never printed)
  2 models        configured models are available to this key (Models API, no token cost)
  3 basic call    one tiny call per model; tokens and cost recorded
  4 structured    structured output via tool call (tool_choice=auto) on both models
  5 tools         real tool call -> tool executed -> result returned with thinking blocks intact
  6 langgraph     the real workflow up to the planner (signal profile + LLM plan), then stops
  7 errors        bad model name mapped to a clear error; spending cap refuses a call; retries set
Cost is capped by MEI_SMOKE_MAX_COST_USD (default $0.50).
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from pydantic import BaseModel, Field

from .config import load_env


class SmokeAnswer(BaseModel):
    """Answer to the smoke-test question."""
    count: int = Field(description="The number asked for")
    note: str = Field(description="One short sentence")


def run_smoke(data_dir: str, out_dir: str = "runs/smoke", skip_graph: bool = False, report=print,
              chat_factory=None, models_api=None) -> dict:
    """`chat_factory` / `models_api` exist only so the test suite can exercise this code offline."""
    results: list[dict] = []
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    cache = out / f"smoke_cache_{int(time.time())}.jsonl"

    def step(name, fn):
        t0 = time.time()
        try:
            detail = fn()
            results.append({"step": name, "status": "PASS", "detail": detail, "seconds": round(time.time() - t0, 1)})
            report(f"PASS  {name}: {detail}")
            return True
        except Exception as e:                  # noqa: BLE001 - smoke test reports everything
            results.append({"step": name, "status": "FAIL", "detail": f"{type(e).__name__}: {e}"})
            report(f"FAIL  {name}: {type(e).__name__}: {e}")
            return False

    env = load_env()

    def s_env():
        if not env["key_present"]:
            raise RuntimeError(f"ANTHROPIC_API_KEY not found (looked for .env at {env['dotenv_path'] or 'cwd/repo root'})")
        note = " (WARNING: shell variable overrides .env)" if env["shell_overrides_file"] else ""
        return (f".env={env['dotenv_path']}; key from {env['key_source']}{note}; key {env['key_masked']}; "
                f"models {env['model_main']} / {env['model_small']}; caps {env['max_calls']} calls, "
                f"${env['max_cost_usd']:.2f}; effort {env['effort_main']}/{env['effort_small']}")
    if not step("1 environment", s_env):
        return _finish(results, None, out)

    def s_models():
        if models_api is None:
            import anthropic
            c = anthropic.Anthropic()
        else:
            c = models_api
        found = []
        for m in (env["model_main"], env["model_small"]):
            info = c.models.retrieve(m)
            found.append(f"{m} -> {getattr(info, 'id', m)}")
        return "; ".join(found)
    if not step("2 models available", s_models):
        return _finish(results, None, out)

    from .llm.client import BudgetExceeded, LLMClient, LLMRequestError
    llm = LLMClient("live", cache, max_cost_usd=float(os.getenv("MEI_SMOKE_MAX_COST_USD", "0.50")),
                    chat_factory=chat_factory)

    def s_basic():
        parts = []
        for which in ("main", "small"):
            ai = llm.invoke(f"smoke_basic_{which}", [HumanMessage("Reply with the single word: OK")], which=which)
            text = ai.content if isinstance(ai.content, str) else " ".join(
                b.get("text", "") for b in ai.content if isinstance(b, dict) and b.get("type") == "text")
            if "ok" not in text.lower():
                raise RuntimeError(f"unexpected reply from {which}: {text[:80]!r}")
            parts.append(f"{which} replied OK")
        return f"{'; '.join(parts)}; tokens in/out {llm.usage.input_tokens}/{llm.usage.output_tokens}; " \
               f"cost ${llm.usage.cost_usd:.5f}"
    step("3 basic call + cost tracking", s_basic)

    def s_structured():
        q = [SystemMessage("You answer precisely."),
             HumanMessage("Three laptops were reviewed: Model X, Model Y and Model Z. How many laptops?")]
        a = llm.structured("smoke_structured_main", q, SmokeAnswer)
        b = llm.structured("smoke_structured_small", q, SmokeAnswer, which="small")
        if a.count != 3 or b.count != 3:
            raise RuntimeError(f"wrong structured answers: main={a.count}, small={b.count}")
        return "both models returned a valid SmokeAnswer via tool call (count=3)"
    step("4 structured output", s_structured)

    from .adapters.synthetic import CsvMarketSource
    from .ledger import EvidenceLedger
    from .tools import anthropic_tool_defs, run_tool
    md = CsvMarketSource(data_dir).load()

    def s_tools():
        led = EvidenceLedger(md.file_hashes)
        pid = md.products["product_id"].iloc[0]
        msgs = [SystemMessage("Use tools to answer. Never compute numbers yourself."),
                HumanMessage(f"Use the first_observed_sale tool for product {pid}, then tell me the month.")]
        ai = llm.invoke("smoke_tools_1", msgs, tools=anthropic_tool_defs(["first_observed_sale"]))
        if not ai.tool_calls:
            raise RuntimeError("model did not call the tool")
        tc = ai.tool_calls[0]
        ev, obs = run_tool(tc["name"], tc["args"], md, led, requested_by="agent")
        has_thinking = isinstance(ai.content, list) and any(
            isinstance(b, dict) and b.get("type") in ("thinking", "redacted_thinking") for b in ai.content)
        msgs += [ai, ToolMessage(content=json.dumps(obs, default=str), tool_call_id=tc["id"])]
        ai2 = llm.invoke("smoke_tools_2", msgs, tools=anthropic_tool_defs(["first_observed_sale"]))
        month = ev.values["first_observed_sale_month"]
        text = ai2.content if isinstance(ai2.content, str) else " ".join(
            b.get("text", "") for b in ai2.content if isinstance(b, dict) and b.get("type") == "text")
        if month not in text:
            raise RuntimeError(f"final answer does not contain tool result {month}: {text[:120]!r}")
        return (f"called {tc['name']}({tc['args']}) -> {ev.evidence_id} {month}; thinking blocks in turn 1: "
                f"{has_thinking}; second turn accepted and used the result")
    step("5 tool calling, multi-turn", s_tools)

    if not skip_graph:
        def s_graph():
            from .agents.graph import RunContext, build_graph
            led = EvidenceLedger(md.file_hashes)
            ctx = RunContext(md=md, ledger=led, mode="live", theme="battery",
                             question="Are battery complaints rising, and in which segment?", llm=llm)
            app = build_graph(ctx, interrupt_after=["plan"])
            st = app.invoke({"question": ctx.question, "theme": "battery", "revisions": 0},
                            config={"configurable": {"thread_id": "smoke"}})
            plan = st.get("plan")
            if not plan:
                raise RuntimeError("graph stopped without a plan")
            return (f"signal profile {len(led.entries)} evidence entries; planner chose '{plan['focus_segment']}' "
                    f"with {len(plan['hypotheses'])} declared hypotheses: "
                    f"{[(h['test_tool'], h['alternative']) for h in plan['hypotheses']]}")
        step("6 LangGraph with real model (stops after plan)", s_graph)

    def s_errors():
        notes = []
        bad = LLMClient("live", out / "smoke_bad.jsonl", model_main="claude-nonexistent-model-xyz",
                        chat_factory=chat_factory)
        try:
            bad.invoke("smoke_bad_model", [HumanMessage("hi")])
            raise RuntimeError("invalid model was accepted")
        except LLMRequestError as e:
            notes.append(f"bad model -> clear error ({str(e)[:70]}...)")
        capped = LLMClient("live", out / "smoke_cap.jsonl", max_cost_usd=0.0001, chat_factory=chat_factory)
        try:
            capped.invoke("smoke_cap", [HumanMessage("hi")])
            raise RuntimeError("spending cap did not stop the call")
        except BudgetExceeded:
            notes.append("spending cap refused the call before sending it")
        _, model = llm._model("main")
        notes.append(f"automatic retries configured: {model.max_retries}")
        return "; ".join(notes)
    step("7 error handling", s_errors)
    return _finish(results, llm, out)


def _finish(results, llm, out: Path) -> dict:
    summary = {"passed": sum(r["status"] == "PASS" for r in results), "failed": sum(r["status"] == "FAIL" for r in results),
               "steps": results, "usage": llm.usage.__dict__ if llm else None}
    (out / "smoke_report.json").write_text(json.dumps(summary, indent=2, default=str))
    return summary
