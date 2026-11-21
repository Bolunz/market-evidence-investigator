"""LangGraph investigation workflow.

signal_profile [code] -> plan [LLM] -> investigate [LLM + tools, ReAct loop] -> critic [LLM]
  -> extra_test [code, optional] -> assess [code rubric] -> write [LLM] -> validate [code + auditor]
  -> (one revision of flagged claims) -> report [code]

Routing is decided in code from evidence and data capabilities:
  no material signal                  -> insufficient_signal
  no sell-out / product docs source   -> market response "not assessed" (capability boundary)
  no product positioned on the need   -> no_direct_response
  otherwise                           -> direct_response
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from ..adapters.base import CAP_PRODUCT_DOCS, CAP_SELLOUT, CAP_SIGNALS
from ..tools import REGISTRY, ToolError, anthropic_tool_defs, observation, run_tool
from ..validation.claims import validate_claims
from ..tools import resolve_comparison_group
from ..validation.rubric import record_assessments
from . import prompts, scripted
from .schemas import Critique, ImpliedAssertions, InvestigationFindings, InvestigationPlan, ReportDraft

AGENT_TOOLS = ["search_product_docs", "get_product_doc", "product_info", "first_observed_sale",
               "define_cohort", "launch_trajectory", "price_volume_pattern", "complaint_comparison"]
STRONG_TYPES = {"launch_date_verified", "promotion_confirmed", "causal_effect", "problem_resolved",
                "demand_or_preference", "availability_or_distribution"}


@dataclass
class RunContext:
    md: Any
    ledger: Any
    mode: str                                  # live | replay | scripted
    theme: str
    question: str
    llm: Any = None
    declared: set = field(default_factory=set)
    trace: list = field(default_factory=list)
    on_event: Optional[Callable[[dict], None]] = None
    max_tool_calls: int = 16
    node: str = ""

    def emit(self, kind: str, text: str, **extra) -> None:
        ev = {"step": len(self.trace) + 1, "node": self.node, "kind": kind, "text": text, **extra}
        self.trace.append(ev)
        if self.on_event:
            self.on_event(ev)


class State(TypedDict, total=False):
    question: str
    theme: str
    path: str
    profile: dict
    plan: dict
    findings: dict
    critique: dict
    draft: dict
    checks: list
    revisions: int
    notes: list


def _ledger_digest(ledger, types: set[str] | None = None) -> list[dict]:
    out = []
    for e in ledger.entries:
        if types and e.evidence_type not in types:
            continue
        o = observation(e)
        o["tool"] = e.tool
        o["params"] = {k: v for k, v in e.params.items() if k != "cohort_ids"}
        o.pop("hits", None)
        o.pop("text", None)
        out.append(o)
    return out


def _text_of(ai) -> str:
    """Visible text plus summarized thinking (if returned), for the trace only."""
    if isinstance(ai.content, str):
        return ai.content
    parts = []
    for b in ai.content:
        if isinstance(b, dict) and b.get("type") == "thinking" and b.get("thinking"):
            parts.append("(thinking) " + b["thinking"])
        elif isinstance(b, dict) and b.get("type") == "text":
            parts.append(b.get("text", ""))
    return " ".join(parts)


def build_graph(ctx: RunContext, interrupt_after: list[str] | None = None):
    use_llm = ctx.mode in ("live", "replay")

    # ------------------------------------------------------------------ nodes
    def signal_profile(state: State) -> State:
        ctx.node = "signal_profile"
        if CAP_SIGNALS not in ctx.md.capabilities:
            ctx.emit("route", "No consumer-signal source connected: investigation cannot start.")
            return {"path": "not_assessed_signal", "profile": {}}
        seg_ev, _ = run_tool("signal_by_segment", {"theme": ctx.theme}, ctx.md, ctx.ledger, requested_by="code")
        ctx.emit("tool", f"signal_by_segment -> {seg_ev.evidence_id}: {seg_ev.summary}", evidence_id=seg_ev.evidence_id)
        trend_ids, statuses, diffs = {}, {}, {}
        for seg in sorted(ctx.md.signals["segment"].unique()):
            ev, _ = run_tool("signal_trend", {"theme": ctx.theme, "segment": seg}, ctx.md, ctx.ledger,
                             requested_by="code")
            trend_ids[seg], statuses[seg] = ev.evidence_id, ev.values.get("status")
            diffs[seg] = ev.values.get("diff", 0)
            ctx.emit("tool", f"signal_trend[{seg}] -> {ev.evidence_id}: {ev.summary}", evidence_id=ev.evidence_id)
        cands = sorted([s for s, st in statuses.items() if st in ("intensified_long_standing", "emerging")],
                       key=lambda s: -diffs[s])
        profile = {"by_segment_id": seg_ev.evidence_id, "trend_ids": trend_ids, "statuses": statuses,
                   "candidate_segments": cands}
        if not cands:
            ctx.emit("route", "No segment shows a material, statistically supported increase -> insufficient signal.")
            return {"path": "insufficient_signal", "profile": profile}
        ctx.emit("decision", f"Segments with a material increase: {cands}")
        return {"profile": profile, "path": "pending"}

    def plan(state: State) -> State:
        ctx.node = "plan"
        prof = state["profile"]
        if use_llm:
            ctx_msg = {"question": ctx.question, "theme": ctx.theme,
                       "data_capabilities": sorted(ctx.md.capabilities),
                       "signal_evidence": _ledger_digest(ctx.ledger), "candidate_segments": prof["candidate_segments"]}
            p = ctx.llm.structured("planner", [SystemMessage(prompts.PLANNER),
                                               HumanMessage(json.dumps(ctx_msg, default=str))], InvestigationPlan)
        else:
            p = scripted.plan(ctx, prof)
        if p.focus_segment not in prof["candidate_segments"]:
            ctx.emit("guard", f"Planner chose '{p.focus_segment}', which has no supported signal increase; "
                              f"using '{prof['candidate_segments'][0]}'.")
            p.focus_segment = prof["candidate_segments"][0]
        ctx.declared = {(h.test_tool, h.alternative) for h in p.hypotheses}
        ctx.emit("decision", f"Focus segment: {p.focus_segment}. {p.rationale}")
        for h in p.hypotheses:
            ctx.emit("decision", f"Declared {h.hypothesis_id} ({h.test_tool}, {h.alternative}): {h.statement}")
        return {"plan": p.model_dump()}

    def investigate(state: State) -> State:
        ctx.node = "investigate"
        p = InvestigationPlan.model_validate(state["plan"])
        if not use_llm:
            inv = scripted.investigate(ctx, p)
        else:
            inv = _react_investigation(ctx, p)
        # post-check: referenced evidence must exist
        for f in inv.findings:
            for attr in ("first_sale_evidence_id", "cohort_evidence_id", "price_volume_evidence_id"):
                eid = getattr(f, attr)
                if eid and ctx.ledger.get(eid) is None:
                    ctx.emit("guard", f"{f.product_id}: {attr}={eid} does not exist; removed.")
                    setattr(f, attr, None)
            for attr in ("sales_evidence_ids", "complaint_evidence_ids"):
                ok = [e for e in getattr(f, attr) if ctx.ledger.get(e) is not None]
                if len(ok) != len(getattr(f, attr)):
                    ctx.emit("guard", f"{f.product_id}: removed non-existent evidence IDs from {attr}.")
                setattr(f, attr, ok)
            ctx.emit("decision", f"{f.product_id}: {f.positioning}. {f.observations[:300]}")
        return {"findings": inv.model_dump()}

    def critic(state: State) -> State:
        ctx.node = "critic"
        inv = InvestigationFindings.model_validate(state["findings"])
        if use_llm:
            msg = {"findings": inv.model_dump(), "evidence": _ledger_digest(ctx.ledger)}
            c = ctx.llm.structured("critic", [SystemMessage(prompts.CRITIC),
                                              HumanMessage(json.dumps(msg, default=str))], Critique)
        else:
            c = scripted.critique(ctx, inv)
        for a in c.alternative_explanations:
            ctx.emit("decision", f"Alternative for {a.product_id}: {a.explanation}")
        rt = c.requested_test
        out = c.model_dump()
        if rt is not None:
            positioned = {f.product_id for f in inv.findings if f.positioning == "positioned_on_need"}
            pid = rt.args.get("product_id")
            if pid not in positioned:
                ctx.emit("guard", f"Critic requested a test on {pid}, which is not a positioned product; skipped.")
            else:
                try:
                    args, source = resolve_comparison_group(ctx.ledger, rt.tool, rt.args)
                    if source:
                        ctx.emit("guard", f"Critic's {rt.tool} on {pid}: comparison group reused from {source} "
                                          "(the investigator's test of the same product and question).")
                        out["requested_test"]["cohort_source"] = source
                    ev, _ = run_tool(rt.tool, args, ctx.md, ctx.ledger, requested_by="critic",
                                     declared=ctx.declared, theme=ctx.theme)
                    ctx.emit("tool", f"[critic] {rt.tool} -> {ev.evidence_id}: {ev.summary}", evidence_id=ev.evidence_id)
                except ToolError as e:
                    ctx.emit("guard", f"Critic's requested test rejected: {e}")
        return {"critique": out}

    def assess(state: State) -> State:
        ctx.node = "assess"
        path = state.get("path", "pending")
        plan_ = state.get("plan")
        if path == "insufficient_signal" or path == "not_assessed_signal":
            return {"path": path}
        seg = plan_["focus_segment"] if plan_ else state["profile"]["candidate_segments"][0]
        if not ({CAP_SELLOUT, CAP_PRODUCT_DOCS} <= ctx.md.capabilities):
            record_assessments(ctx.ledger, seg, ctx.theme, [])
            ctx.emit("route", "No sell-out or product-document source connected: sections C-D are not assessed.")
            return {"path": "not_assessed_market_response"}
        inv = InvestigationFindings.model_validate(state["findings"])
        pids = [f.product_id for f in inv.findings if f.positioning == "positioned_on_need"]
        evs = record_assessments(ctx.ledger, seg, ctx.theme, pids)
        for e in evs:
            ctx.emit("assess", e.summary, evidence_id=e.evidence_id)
        path = "direct_response" if pids else "no_direct_response"
        ctx.emit("route", f"Investigation path: {path}")
        return {"path": path}

    def write(state: State) -> State:
        ctx.node = "write"
        if not use_llm:
            d = scripted.write(ctx, state)
        else:
            products = ctx.md.products.set_index("product_id")
            # sorted: iterating a set of strings depends on PYTHONHASHSEED, which made the writer prompt
            # (and so its replay cache key) differ between processes
            involved = sorted({e.params.get("product_id") for e in ctx.ledger.entries if e.params.get("product_id")})
            msg = {"question": ctx.question, "path": state.get("path"), "plan": state.get("plan"),
                   "findings": state.get("findings"), "critique": state.get("critique"),
                   "product_models": {p: products.loc[p, "model"] for p in involved if p in products.index},
                   "evidence": _ledger_digest(ctx.ledger)}
            if state.get("checks"):
                msg["previous_validation_failures"] = [c for c in state["checks"] if c["status"] == "flagged"]
                msg["instruction"] = ("Rewrite the flagged claims so they assert only what the cited evidence "
                                      "supports, or downgrade/qualify them. Keep verified claims unchanged.")
            d = ctx.llm.structured("writer", [SystemMessage(prompts.WRITER),
                                              HumanMessage(json.dumps(msg, default=str))], ReportDraft)
        ctx.emit("decision", f"Draft with {len(d.claims)} claims.")
        return {"draft": d.model_dump(), "revisions": state.get("revisions", 0) + (1 if state.get("checks") else 0)}

    def validate(state: State) -> State:
        ctx.node = "validate"
        d = ReportDraft.model_validate(state["draft"])
        auditor = None
        if use_llm:
            def auditor(claim):
                r = ctx.llm.structured("auditor", [SystemMessage(prompts.AUDITOR), HumanMessage(claim.text)],
                                       ImpliedAssertions, which="small")
                return [t for t in r.implied if t in STRONG_TYPES]
        checks = validate_claims(d, ctx.ledger, ctx.md.products, auditor)
        flagged = [c for c in checks if c.status == "flagged"]
        ctx.emit("guard" if flagged else "decision",
                 f"Claim validation: {len(checks) - len(flagged)} verified, {len(flagged)} flagged.")
        for c in flagged:
            ctx.emit("guard", f"{c.claim_id} flagged: {'; '.join(c.problems)}")
        return {"checks": [c.__dict__ for c in checks]}

    # ------------------------------------------------------------------ routing
    def after_profile(state: State) -> str:
        if state.get("path") in ("insufficient_signal", "not_assessed_signal"):
            return "write"
        if not ({CAP_SELLOUT, CAP_PRODUCT_DOCS} <= ctx.md.capabilities):
            return "assess"
        return "plan"

    def after_investigate(state: State) -> str:
        inv = InvestigationFindings.model_validate(state["findings"])
        if any(f.positioning == "positioned_on_need" for f in inv.findings):
            return "critic"
        ctx.emit("route", "No product in the focus segment was positioned on the need.")
        return "assess"

    def after_validate(state: State) -> str:
        flagged = any(c["status"] == "flagged" for c in state["checks"])
        if flagged and use_llm and state.get("revisions", 0) < 1:
            ctx.node = "validate"
            ctx.emit("route", "Returning flagged claims to the writer for one revision.")
            return "write"
        return END

    g = StateGraph(State)
    for name, fn in [("signal_profile", signal_profile), ("plan", plan), ("investigate", investigate),
                     ("critic", critic), ("assess", assess), ("write", write), ("validate", validate)]:
        g.add_node(name, fn)
    g.add_edge(START, "signal_profile")
    g.add_conditional_edges("signal_profile", after_profile, ["plan", "assess", "write"])
    g.add_edge("plan", "investigate")
    g.add_conditional_edges("investigate", after_investigate, ["critic", "assess"])
    g.add_edge("critic", "assess")
    g.add_edge("assess", "write")
    g.add_edge("write", "validate")
    g.add_conditional_edges("validate", after_validate, ["write", END])
    return g.compile(checkpointer=InMemorySaver(), interrupt_after=interrupt_after or [])


def _react_investigation(ctx: RunContext, p: InvestigationPlan) -> InvestigationFindings:
    """Bounded ReAct loop: the model chooses tools; code executes and records them."""
    tools = anthropic_tool_defs(AGENT_TOOLS) + [InvestigationFindings]
    brief = {"question": ctx.question, "theme": ctx.theme, "plan": p.model_dump(),
             "signal_evidence": _ledger_digest(ctx.ledger),
             "instruction": "Investigate, then submit by calling the InvestigationFindings tool."}
    msgs = [SystemMessage(prompts.INVESTIGATOR), HumanMessage(json.dumps(brief, default=str))]
    n_tools, nudges, repairs, final_asks = 0, 0, 0, 0
    while True:
        if n_tools >= ctx.max_tool_calls or nudges >= 2:
            # Sonnet 5.5 rejects forced tool_choice, so the final submission is requested in words.
            if final_asks >= 2:
                raise RuntimeError("investigator did not submit findings after the tool budget was reached")
            final_asks += 1
            ctx.emit("guard", "Tool budget reached: requesting final findings.")
            msgs.append(HumanMessage("Tool budget reached. Do not call analysis tools again. Submit now by calling "
                                     "the InvestigationFindings tool."))
        ai = ctx.llm.invoke("investigator", msgs, tools=tools)
        msgs.append(ai)                      # kept unmodified: thinking blocks must be passed back
        txt = _text_of(ai).strip()
        if txt:
            ctx.emit("reasoning", txt[:400])
        if not ai.tool_calls:
            nudges += 1
            msgs.append(HumanMessage("Continue using tools, or submit via the InvestigationFindings tool."))
            continue
        submitted = None
        for tc in ai.tool_calls:
            if tc["name"] == "InvestigationFindings":
                submitted = tc
                continue
            if final_asks:
                content = "ERROR: tool budget reached; submit InvestigationFindings now."
            else:
                try:
                    ev, obs = run_tool(tc["name"], tc["args"], ctx.md, ctx.ledger, requested_by="agent",
                                       declared=ctx.declared, theme=ctx.theme)
                    content = json.dumps(obs, default=str)
                    shown = {k: v for k, v in tc["args"].items() if k != "cohort_ids"}
                    ctx.emit("tool", f"{tc['name']}({shown}) -> {ev.evidence_id}: {ev.summary}",
                             evidence_id=ev.evidence_id, requested_by="agent")
                except ToolError as e:
                    content = f"ERROR: {e}"
                    ctx.emit("guard", f"Rejected tool call {tc['name']}: {e}")
            msgs.append(ToolMessage(content=content, tool_call_id=tc["id"]))
            n_tools += 1
        if submitted is not None:
            try:
                return InvestigationFindings.model_validate(submitted["args"])
            except Exception as e:                      # noqa: BLE001 - surface to the model once
                repairs += 1
                if repairs > 1:
                    raise
                msgs.append(ToolMessage(content=f"Invalid findings: {e}", tool_call_id=submitted["id"]))
                msgs.append(HumanMessage("Fix the findings and call InvestigationFindings again."))
