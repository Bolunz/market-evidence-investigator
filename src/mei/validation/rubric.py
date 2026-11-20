"""Deterministic confidence rubric. The LLM never assigns grades.

It looks at ALL ledger evidence for a product (not only what the agent chose to cite), so
an agent cannot raise a grade by omitting inconvenient tests.

Only CONFIRMATORY tests (pre-declared tool + direction) can support a grade. Sensitivity
re-runs can only restrict it (a price-and-volume pattern must be survived). Exploratory
tests are reported but never raise a grade.

Grades (maximum is Moderate: observational panel data, no causal design):
  Moderate       sales outperformance supported AND post-first-sale complaints lower than cohort
  Weak           only one of the two holds
  Not supported  confirmatory tests run, neither holds
  Insufficient   first observed sale unreliable, or the confirmatory tests were not run

The grade is also recomputed with BH across ALL tests in the run (`grade_pooled`) so the
effect of the family definition is visible.
"""
from __future__ import annotations

ALPHA = 0.05
MAX_GRADE_NOTE = "Moderate is the ceiling: observational data without a causal design."


def _for_product(ledger, tool: str, pid: str):
    return [e for e in ledger.entries if e.tool == tool and e.params.get("product_id") == pid]


def _sig(e, qattr: str) -> bool:
    q = getattr(e, qattr)
    return q is not None and q < ALPHA


def _status(ledger, pid: str, qattr: str) -> dict:
    traj = _for_product(ledger, "launch_trajectory", pid)
    # a declared one-sided ("greater") or two-sided hypothesis both count; a two-sided result supports
    # OUTperformance only when the product is above its cohort (ratio > 1)
    confirm = [e for e in traj if e.hypothesis_status == "confirmatory"
               and e.params.get("alternative") in ("greater", "two-sided")]
    sens = [e for e in traj if e.hypothesis_status == "sensitivity" and e.params.get("exclude_price_volume_months")]

    def above(e):
        r = e.values.get("ratio_to_cohort_median")
        return r is not None and r > 1
    pv = _for_product(ledger, "price_volume_pattern", pid)
    comp = [e for e in _for_product(ledger, "complaint_comparison", pid) if "p_value" in e.values]
    comp_c = [e for e in comp if e.hypothesis_status == "confirmatory" and e.params.get("alternative") in ("less", "two-sided")]
    pattern = any(e.values.get("pattern_detected") for e in pv)

    if not confirm:
        sales = "exploratory_only" if traj else "not_tested"
    elif any(_sig(e, qattr) and not above(e) for e in confirm) and not any(_sig(e, qattr) and above(e) for e in confirm):
        sales = "underperformed_cohort"
    elif any(_sig(e, qattr) and above(e) for e in confirm):
        if not pattern:
            sales = "supported"
        elif sens and any(_sig(e, qattr) and above(e) for e in sens):
            sales = "supported_excluding_pattern_months"
        elif sens:
            sales = "not_robust_to_price_volume_pattern"
        else:
            sales = "unresolved_price_volume_pattern"
    else:
        sales = "not_supported"

    if not comp_c:
        complaints = "exploratory_only" if comp else "not_tested"
    else:
        c = comp_c[-1]
        d = c.values["diff_vs_cohort_median"]
        if _sig(c, qattr) and d < 0:
            complaints = "lower_than_cohort"
        elif _sig(c, qattr) and d > 0:
            complaints = "higher_than_cohort"
        else:
            complaints = "no_detectable_difference"
    return {"sales": sales, "complaints": complaints, "pattern": pattern,
            "based_on": [e.evidence_id for e in traj + pv + comp],
            "exploratory": [e.evidence_id for e in traj + comp if e.hypothesis_status == "exploratory"]}


def _grade(reliability: str, st: dict) -> str:
    sales_ok = st["sales"] in ("supported", "supported_excluding_pattern_months")
    comp_ok = st["complaints"] == "lower_than_cohort"
    if reliability == "unreliable":
        return "Insufficient"
    if st["sales"] in ("not_tested", "exploratory_only") and st["complaints"] in ("not_tested", "exploratory_only"):
        return "Insufficient"
    if sales_ok and comp_ok:
        return "Moderate"
    if sales_ok or comp_ok:
        return "Weak"
    return "Not supported"


def assess_product(ledger, pid: str) -> dict:
    fos = _for_product(ledger, "first_observed_sale", pid)
    reliability = fos[-1].values.get("reliability") if fos else "not_checked"
    st = _status(ledger, pid, "q_value")
    st_pooled = _status(ledger, pid, "q_pooled")
    grade = _grade(reliability, st)
    reasons = []
    if reliability == "unreliable":
        reasons.append("first observed sale is unreliable (cannot anchor launch-aligned comparisons)")
    if reliability == "caution":
        reasons.append("first observed sale has caution flags")
    if st["pattern"]:
        reasons.append("observed price-and-volume pattern (promotion not confirmed)")
    if st["exploratory"]:
        reasons.append(f"exploratory tests reported but not graded: {', '.join(st['exploratory'])}")
    sales_ok = st["sales"] in ("supported", "supported_excluding_pattern_months")
    if sales_ok and st["complaints"] in ("no_detectable_difference", "higher_than_cohort"):
        contradiction = "sales advantage without lower complaints"
    elif st["complaints"] == "lower_than_cohort" and st["sales"] in ("not_supported", "not_robust_to_price_volume_pattern"):
        contradiction = "lower complaints without a sales advantage"
    else:
        contradiction = "none"
    return {"product_id": pid, "grade": grade, "grade_pooled": _grade(reliability, st_pooled),
            "sales_status": st["sales"], "complaint_status": st["complaints"],
            "first_sale_reliability": reliability, "price_volume_pattern": st["pattern"],
            "contradiction": contradiction, "reasons": "; ".join(reasons) or "none",
            "ceiling_note": MAX_GRADE_NOTE,
            "based_on": ",".join([e.evidence_id for e in fos] + st["based_on"])}


def assess_signal(ledger, segment: str, theme: str) -> dict:
    trend = [e for e in ledger.entries if e.tool == "signal_trend" and e.params.get("segment") == segment
             and e.params.get("theme") == theme]
    if not trend:
        return {"segment": segment, "grade": "Insufficient", "reasons": "no signal trend computed"}
    v = trend[-1].values
    status = v.get("status")
    reasons = []
    if status in ("intensified_long_standing", "emerging") and (trend[-1].q_value or 1) < ALPHA:
        grade = "Moderate"
        if v.get("top_product_share_of_recent_complaints", 0) > 0.4:
            grade = "Weak"
            reasons.append("recent complaints concentrated in one product")
    elif status == "insufficient_observations":
        grade = "Insufficient"
    else:
        grade = "Not supported"
    reasons.append("complaint labels come from a classifier whose accuracy is not validated in this dataset")
    reasons.append("pooled segment rates can move with product mix")
    return {"segment": segment, "theme": theme, "grade": grade, "status": status,
            "reasons": "; ".join(reasons), "based_on": trend[-1].evidence_id}


def record_assessments(ledger, segment: str, theme: str, product_ids: list[str]) -> list:
    out = []
    sig = assess_signal(ledger, segment, theme)
    out.append(ledger.record("rubric", {"kind": "signal", "segment": segment, "theme": theme},
                             {"evidence_type": "confidence_assessment", "values": sig,
                              "summary": f"Signal grade for {theme} in {segment}: {sig['grade']}."}))
    for pid in product_ids:
        a = assess_product(ledger, pid)
        out.append(ledger.record("rubric", {"kind": "product", "product_id": pid},
                                 {"evidence_type": "confidence_assessment", "values": a,
                                  "summary": (f"{pid}: grade {a['grade']} (sales: {a['sales_status']}; complaints: "
                                              f"{a['complaint_status']}; first sale: {a['first_sale_reliability']}; "
                                              f"grade under pooled FDR: {a['grade_pooled']}).")}))
    return out
