"""Scripted (no-LLM) policy: a deterministic stand-in for the LLM roles.

Purpose: offline tests, CI, and a safety net when no API key is available. It follows a
fixed, generic investigation recipe using the same tools and ledger as the agent. It does
NOT read answer keys. Reports from this mode are labelled "scripted run (no LLM)" and are
not presented as agentic output.
"""
from __future__ import annotations

import re

from ..tools import run_tool
from .schemas import (AlternativeExplanation, Assertion, Claim, Critique, Hypothesis, InvestigationFindings,
                      InvestigationPlan, ProductFinding, ReportDraft, RequestedTest)

POSITIONING_PATTERNS = re.compile(r"hours of battery|battery life|all-day battery|battery that lasts|"
                                  r"long-lasting battery", re.I)


def plan(ctx, profile: dict) -> InvestigationPlan:
    seg = profile["candidate_segments"][0]
    return InvestigationPlan(
        focus_segment=seg, rationale=f"Largest material increase in {ctx.theme} complaints "
                                     f"({profile['trend_ids'][seg]}).",
        search_terms=["battery life", "hours of battery", "all-day battery", "long-lasting battery",
                      "battery that lasts"],
        hypotheses=[
            Hypothesis(hypothesis_id="H1", statement="Products positioned on the need gained more segment share "
                       "than their launch cohort", test_tool="launch_trajectory", alternative="greater"),
            Hypothesis(hypothesis_id="H2", statement="Products positioned on the need show lower post-first-sale "
                       "complaint rates than their cohort", test_tool="complaint_comparison", alternative="less"),
        ],
        evidence_ids=[profile["trend_ids"][seg]],
    )


def investigate(ctx, plan_: InvestigationPlan) -> InvestigationFindings:
    def tool(name, **args):
        ev, _ = run_tool(name, args, ctx.md, ctx.ledger, requested_by="scripted", declared=ctx.declared)
        ctx.emit("tool", f"{name}({', '.join(f'{k}={v}' for k, v in args.items() if k != 'cohort_ids')}) "
                         f"-> {ev.evidence_id}: {ev.summary}")
        return ev

    search = tool("search_product_docs", terms=plan_.search_terms)
    findings, excluded = [], []
    for h in search.detail["hits"]:
        if h["doc_type"] != "announcement":
            excluded.append(f"{h['product_id']}: only spec-sheet mention ({h['doc_id']})")
            continue
        doc = tool("get_product_doc", doc_id=h["doc_id"])
        text = doc.detail["text"]
        m = POSITIONING_PATTERNS.search(text)
        sent = next((s for s in re.split(r"(?<=[.!?])\s+", text) if m and m.group(0) in s), None)
        if not m:
            excluded.append(f"{h['product_id']}: incidental mention ({h['doc_id']})")
            continue
        if h["segment"] != plan_.focus_segment:
            findings.append(ProductFinding(product_id=h["product_id"], positioning="segment_mismatch",
                                           doc_id=h["doc_id"], quote=sent,
                                           observations=f"Positioned on the need but in {h['segment']} ({doc.evidence_id})."))
            continue
        pid = h["product_id"]
        fos = tool("first_observed_sale", product_id=pid)
        f = ProductFinding(product_id=pid, positioning="positioned_on_need", doc_id=h["doc_id"], quote=sent,
                           first_sale_evidence_id=fos.evidence_id, observations="")
        if fos.values["reliability"] == "unreliable":
            f.observations = (f"First observed sale {fos.values['first_observed_sale_month']} is unreliable "
                              f"({fos.values['flags']}); launch-aligned comparison not run ({fos.evidence_id}).")
            f.open_questions.append("When did this model actually enter the market?")
            findings.append(f)
            continue
        co = tool("define_cohort", product_id=pid)
        ids = [c for c in co.values["cohort_ids"].split(",") if c]
        f.cohort_evidence_id = co.evidence_id
        tr = tool("launch_trajectory", product_id=pid, cohort_ids=ids, alternative="greater")
        pv = tool("price_volume_pattern", product_id=pid)
        f.sales_evidence_ids, f.price_volume_evidence_id = [tr.evidence_id], pv.evidence_id
        cc = tool("complaint_comparison", product_id=pid, cohort_ids=ids, theme=ctx.theme, alternative="less")
        f.complaint_evidence_ids = [cc.evidence_id]
        f.observations = f"{tr.summary} {pv.summary} {cc.summary}"
        findings.append(f)
    return InvestigationFindings(findings=findings, products_considered_and_excluded=excluded,
                                 summary=f"{len(findings)} products examined from {search.evidence_id}.")


def critique(ctx, inv: InvestigationFindings) -> Critique:
    alts, req = [], None
    for f in inv.findings:
        if f.positioning != "positioned_on_need" or not f.sales_evidence_ids:
            continue
        pv = ctx.ledger.get(f.price_volume_evidence_id)
        if pv and pv.values.get("pattern_detected"):
            alts.append(AlternativeExplanation(
                product_id=f.product_id, explanation="Share gains may reflect the observed price-and-volume "
                "pattern rather than the positioning.", would_distinguish="Re-run the launch comparison "
                "excluding the pattern months.", addressed_by=[pv.evidence_id]))
            if req is None:
                co = ctx.ledger.get(f.cohort_evidence_id)
                req = RequestedTest(tool="launch_trajectory", reason="Check robustness to price-and-volume months",
                                    args={"product_id": f.product_id,
                                          "cohort_ids": co.values["cohort_ids"].split(","),
                                          "exclude_price_volume_months": True, "alternative": "greater"})
        alts.append(AlternativeExplanation(
            product_id=f.product_id, explanation="Complaint differences may reflect a different buyer mix, "
            "firmware updates or shifting attention rather than better battery performance.",
            would_distinguish="Owner-verified reviews, firmware timelines, complaint trends within the product.",
            addressed_by=f.complaint_evidence_ids))
    return Critique(alternative_explanations=alts, requested_test=req)


def _pct(x):
    return f"{x * 100:.1f}%"


def write(ctx, state: dict) -> ReportDraft:
    L, claims = ctx.ledger, []

    def add(section, level, text, assertions):
        claims.append(Claim(claim_id=f"C{len(claims) + 1:02d}", section=section, level=level, text=text,
                            assertions=[Assertion(type=t, subject=s, evidence_ids=ids) for t, s, ids in assertions]))

    prof = state.get("profile") or {}
    if "plan" not in state:
        for seg, eid in prof.get("trend_ids", {}).items():
            e = L.get(eid)
            add("A_consumer_signal", "observation",
                f"{seg}: {ctx.theme} complaint rate {_pct(e.values['recent_rate'])} recently vs "
                f"{_pct(e.values['baseline_rate'])} at baseline (status: {e.values['status']}).",
                [("signal_change", seg, [eid])])
        reason = {"insufficient_signal": "No segment shows a material, statistically supported increase in "
                                         "complaints, so no market-response investigation was started.",
                  "not_assessed_market_response": "No sell-out or product-document source is connected, so "
                                                  "market response and sales evidence were not assessed."}
        add("E_evidence_assessment", "evidence_gap", reason.get(state.get("path"), "Investigation not run."),
            [("evidence_gap", None, [])])
        return ReportDraft(title=f"{ctx.theme.title()} complaints: evidence investigation", claims=claims,
                           follow_ups=[])
    seg = state["plan"]["focus_segment"]
    tr = L.get(prof["trend_ids"][seg])
    v = tr.values
    add("A_consumer_signal", "observation",
        f"In {seg}, the {ctx.theme} complaint rate was {_pct(v['recent_rate'])} of comments in {v['recent_window']} "
        f"versus {_pct(v['baseline_rate'])} in {v['baseline_window']} (difference 95% CI {_pct(v['diff_ci_low'])} "
        f"to {_pct(v['diff_ci_high'])}).", [("signal_change", seg, [tr.evidence_id])])
    seg_ev = L.get(prof["by_segment_id"])
    add("A_consumer_signal", "observation",
        f"Across segments in the recent window: {seg_ev.summary}", [("signal_level", None, [seg_ev.evidence_id])])
    add("B_historical_context", "observation",
        f"The baseline rate of {_pct(v['baseline_rate'])} shows the complaint was present before the increase "
        f"(status: {v['status']}).", [("signal_change", seg, [tr.evidence_id])])
    add("B_historical_context", "evidence_gap",
        "The history covers one panel window only, so earlier episodes cannot be checked.",
        [("evidence_gap", None, [])])

    inv = InvestigationFindings.model_validate(state["findings"])
    for f in inv.findings:
        doc_ev = next((e for e in L.entries if e.tool == "get_product_doc" and e.params.get("doc_id") == f.doc_id), None)
        model = ctx.md.products.set_index("product_id").loc[f.product_id, "model"]
        if f.positioning == "segment_mismatch":
            add("C_market_response", "observation",
                f"{model} ({f.product_id}) is positioned on the need but sits outside {seg}, so it is not "
                f"compared with this segment's cohort.", [("positioning_claim", f.product_id, [doc_ev.evidence_id])])
            continue
        add("C_market_response", "observation",
            f"{model} ({f.product_id}) was positioned on the need: \"{f.quote}\" This is documented positioning, "
            f"not evidence that the product resolved the problem.",
            [("positioning_claim", f.product_id, [doc_ev.evidence_id])])
        fos = L.get(f.first_sale_evidence_id)
        add("D_sales_evidence", "method_note",
            f"{f.product_id} first observed sale: {fos.values['first_observed_sale_month']} (an estimate of market "
            f"entry, not a verified launch date); reliability {fos.values['reliability']}.",
            [("first_observed_sale", f.product_id, [fos.evidence_id]), ("fos_reliability", f.product_id, [fos.evidence_id])])
        if not f.sales_evidence_ids:
            continue
        trs = [e for e in L.entries if e.tool == "launch_trajectory" and e.params["product_id"] == f.product_id]
        for t in trs:
            tv = t.values
            label = " excluding price-and-volume pattern months" if tv["excluded_price_volume_months"] else ""
            lvl, typ = ("association", "sales_association") if (t.q_value or 1) < 0.05 else ("observation", "sales_comparison")
            add("D_sales_evidence", lvl,
                f"{f.product_id} averaged {_pct(tv['target_mean_segment_share'])} of segment sell-out over its first "
                f"{tv['months_used']} months{label}, versus a cohort median of {_pct(tv['cohort_median_segment_share'])}"
                f" (rank {tv['rank_in_cohort']} of {tv['n_products_compared']}; p={t.p_value:.3f}, BH q={t.q_value:.3f}).",
                [(typ, f.product_id, [t.evidence_id])])
        pv = L.get(f.price_volume_evidence_id)
        if pv.values["pattern_detected"]:
            add("D_sales_evidence", "observation",
                f"{f.product_id} shows an observed price-and-volume pattern (promotion not confirmed) in "
                f"{pv.values['pattern_months']}.", [("price_volume_pattern", f.product_id, [pv.evidence_id])])
        for cid in f.complaint_evidence_ids:
            c = L.get(cid)
            cv = c.values
            if "p_value" not in cv:
                continue
            lvl, typ = ("association", "complaint_association") if (c.q_value or 1) < 0.05 else ("observation", "complaint_comparison")
            add("D_sales_evidence", lvl,
                f"{f.product_id} {ctx.theme} complaint rate was {_pct(cv['target_rate'])} versus a cohort median of "
                f"{_pct(cv['cohort_median_rate'])} in the same months (p={c.p_value:.3f}, BH q={c.q_value:.3f}).",
                [(typ, f.product_id, [c.evidence_id])])

    for a in L.by_type("confidence_assessment"):
        av = a.values
        if "product_id" in av:
            add("E_evidence_assessment", "observation",
                f"{av['product_id']}: rubric grade {av['grade']} (sales: {av['sales_status']}; complaints: "
                f"{av['complaint_status']}; contradiction: {av['contradiction']}).",
                [("confidence_grade", av["product_id"], [a.evidence_id])])
        else:
            add("E_evidence_assessment", "observation",
                f"Consumer signal in {av['segment']}: rubric grade {av['grade']}.",
                [("confidence_grade", av["segment"], [a.evidence_id])])
    crit = state.get("critique") or {}
    for alt in crit.get("alternative_explanations", []):
        add("E_evidence_assessment", "explanation",
            f"{alt['product_id']}: possible alternative explanation: {alt['explanation']}",
            [("alternative_explanation", alt["product_id"], alt["addressed_by"] or [state["plan"]["evidence_ids"][0]])])
    moderate = [a for a in L.by_type("confidence_assessment")
                if a.values.get("grade") == "Moderate" and "product_id" in a.values]
    for a in moderate:
        add("F_opportunity_hypotheses", "hypothesis",
            f"Hypothesis for analyst evaluation: endurance positioning in {seg} may merit further study, given "
            f"{a.values['product_id']}'s rubric grade of {a.values['grade']}; this does not establish that battery "
            f"life drove its sales.", [("opportunity_hypothesis", a.values["product_id"], [a.evidence_id])])
    if not moderate:
        add("F_opportunity_hypotheses", "evidence_gap",
            "No product reached a Moderate grade; the evidence does not support an opportunity hypothesis.",
            [("evidence_gap", None, [])])
    return ReportDraft(title=f"{ctx.theme.title()} complaints in {seg}: evidence investigation", claims=claims,
                       follow_ups=["Verify actual market-entry dates for flagged products.",
                                   "Check owner-verified reviews for post-launch battery experience."])
