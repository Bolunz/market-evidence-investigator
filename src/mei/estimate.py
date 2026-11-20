"""Pre-run cost estimate for a full live investigation.

Method: run the scripted (no-LLM) investigation on the same data to obtain the real sizes of
the prompts, tool schemas and tool observations the agent would see, then simulate the
conversation growth (each ReAct turn re-sends the whole transcript) under stated
assumptions about turns and output length. Tokens are approximated as characters / 3
(the Claude 5.x tokenizer produces ~30% more tokens than earlier ones). This is an
ESTIMATE with a low / central / high range, not a quote.
"""
from __future__ import annotations

import json
import math
import tempfile
from pathlib import Path

from .agents import prompts
from .agents.graph import AGENT_TOOLS, _ledger_digest
from .agents.schemas import Critique, InvestigationFindings, InvestigationPlan, ReportDraft
from .config import price_for
from .tools import anthropic_tool_defs, observation

CHARS_PER_TOKEN = 3.0
SCENARIOS = {   # (output tokens per ReAct turn, writer output, writer revisions, input multiplier, extra agent turns)
    "low": (400, 4000, 0, 0.9, 0),
    "central": (900, 7000, 1, 1.0, 3),
    "high": (2000, 12000, 1, 1.3, 8),
}


def _tok(chars: float) -> int:
    return int(chars / CHARS_PER_TOKEN)


def estimate_full_run(data_dir: str | Path, model_main: str, model_small: str) -> dict:
    from .run import run_investigation
    with tempfile.TemporaryDirectory() as tmp:
        res = run_investigation(data_dir, Path(tmp) / "est", mode="scripted")
    led, st = res["ledger"], res["state"]
    schema = lambda s: len(json.dumps(s.model_json_schema()))  # noqa: E731
    tools_chars = len(json.dumps(anthropic_tool_defs(AGENT_TOOLS))) + schema(InvestigationFindings)
    signal_digest = len(json.dumps(_ledger_digest(led, {"signal_trend", "signal_by_segment"}), default=str))
    full_digest = len(json.dumps(_ledger_digest(led), default=str))
    agent_obs = [len(json.dumps(observation(e), default=str)) for e in led.entries if e.requested_by == "scripted"]
    findings = len(json.dumps(st.get("findings"), default=str))
    n_claims = len(st["draft"]["claims"])
    pin, pout = price_for(model_main)
    sin, sout = price_for(model_small)
    out = {}
    for name, (turn_out, writer_out, revisions, mult, extra_turns) in SCENARIOS.items():
        base = len(prompts.INVESTIGATOR) + tools_chars + signal_digest + 800
        turns = math.ceil(len(agent_obs) / 2) + 1 + extra_turns
        inp, outp, cum = 0, 0, 0.0
        for t in range(turns):
            cum += sum(agent_obs[2 * t:2 * t + 2])
            inp += _tok((base + cum) * mult) + t * turn_out
            outp += turn_out
        calls = turns
        # planner, critic, writer (+ revisions)
        inp += _tok((len(prompts.PLANNER) + signal_digest + schema(InvestigationPlan)) * mult)
        outp += 1500
        inp += _tok((len(prompts.CRITIC) + full_digest + findings + schema(Critique)) * mult)
        outp += 2500
        w_in = _tok((len(prompts.WRITER) + full_digest + findings + 3000 + schema(ReportDraft)) * mult)
        inp += w_in * (1 + revisions)
        outp += writer_out * (1 + revisions)
        calls += 3 + revisions
        main_cost = inp / 1e6 * pin + outp / 1e6 * pout
        # auditor on interpretive claims (small model)
        n_aud = max(6, n_claims // 2) * (1 + revisions)
        a_in, a_out = n_aud * 700, n_aud * 400
        small_cost = a_in / 1e6 * sin + a_out / 1e6 * sout
        out[name] = {"llm_calls": calls + n_aud, "main_input_tokens": inp, "main_output_tokens": outp,
                     "small_input_tokens": a_in, "small_output_tokens": a_out,
                     "cost_usd": round(main_cost + small_cost, 3)}
    return {"assumptions": {"chars_per_token": CHARS_PER_TOKEN, "scenarios": SCENARIOS,
                            "agent_tool_calls_in_reference_run": len(agent_obs),
                            "prices_usd_per_mtok": {model_main: (pin, pout), model_small: (sin, sout)}},
            "estimate": out}
