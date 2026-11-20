"""Deterministic confidence rubric. The LLM never assigns grades.

It looks at ALL ledger evidence for a product (not only what the agent chose to cite), so
an agent cannot raise a grade by omitting inconvenient tests.

Grades (maximum is Moderate: observational panel data, no causal design):
  Moderate       sales outperformance supported AND post-first-sale complaints lower than cohort
  Weak           only one of the two holds
  Not supported  tests run, neither holds
  Insufficient   first observed sale unreliable, or the needed tests were not run
"""
from __future__ import annotations

ALPHA = 0.05
MAX_GRADE_NOTE = "Moderate is the ceiling: observational data without a causal design."


def _for_product(ledger, tool: str, pid: str):
    return [e for e in ledger.entries if e.tool == tool and e.params.get("product_id") == pid]


def _sig(e) -> bool:
    return e.q_value is not None and e.q_value < ALPHA


def assess_product(ledger, pid: str) -> dict:
    fos = _for_product(ledger, "first_observed_sale", pid)
    traj = [e for e in _for_product(ledger, "launch_trajectory", pid) if e.params.get("alternative") == "greater"]
    raw = [e for e in traj if not e.params.get("exclude_price_volume_months")]
    excl = [e for e in traj if e.params.get("exclude_price_volume_months")]
    pv = _for_product(ledger, "price_volume_pattern", pid)
    comp = _for_product(ledger, "complaint_comparison", pid)
    based_on = [e.evidence_id for e in fos + traj + pv + comp]

    reliability = fos[-1].values.get("reliability") if fos else "not_checked"
    pattern = any(e.values.get("pattern_detected") for e in pv)

    if not raw:
        sales = "not_tested"
    elif any(_sig(e) for e in raw):
        if not pattern:
            sales = "supported"
        elif excl and any(_sig(e) for e in excl):
            sales = "supported_excluding_pattern_months"
        elif excl:
            sales = "not_robust_to_price_volume_pattern"
        else:
            sales = "unresolved_price_volume_pattern"
    else:
        sales = "not_supported"

    if not comp or all("p_value" not in e.values for e in comp):
        complaints = "not_tested"
    else:
        c = [e for e in comp if "p_value" in e.values][-1]
        if _sig(c) and c.values["diff_vs_cohort_median"] < 0:
            complaints = "lower_than_cohort"
        elif _sig(c) and c.values["diff_vs_cohort_median"] > 0:
            complaints = "higher_than_cohort"
        else:
            complaints = "no_detectable_difference"

    sales_ok = sales in ("supported", "supported_excluding_pattern_months")
    comp_ok = complaints == "lower_than_cohort"
    reasons = []
    if reliability == "unreliable":
        grade = "Insufficient"
        reasons.append("first observed sale is unreliable (cannot anchor launch-aligned comparisons)")
    elif sales == "not_tested" and complaints == "not_tested":
        grade = "Insufficient"
        reasons.append("sales and complaint tests not run")
    elif sales_ok and comp_ok:
        grade = "Moderate"
    elif sales_ok or comp_ok:
        grade = "Weak"
    else:
        grade = "Not supported"
    if pattern:
        reasons.append("observed price-and-volume pattern (promotion not confirmed)")
    if sales_ok and complaints in ("no_detectable_difference", "higher_than_cohort"):
        contradiction = "sales advantage without lower complaints"
    elif comp_ok and sales in ("not_supported", "not_robust_to_price_volume_pattern"):
        contradiction = "lower complaints without a sales advantage"
    else:
        contradiction = "none"
    if reliability == "caution":
        reasons.append("first observed sale has caution flags")
    exploratory = [e.evidence_id for e in traj + comp if e.hypothesis_status == "exploratory"]
    if exploratory:
        reasons.append(f"exploratory (undeclared) tests: {', '.join(exploratory)}")
    return {"product_id": pid, "grade": grade, "sales_status": sales, "complaint_status": complaints,
            "first_sale_reliability": reliability, "price_volume_pattern": pattern,
            "contradiction": contradiction, "reasons": "; ".join(reasons) or "none",
            "ceiling_note": MAX_GRADE_NOTE, "based_on": ",".join(based_on)}


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
                                  "summary": (f"{pid}: grade {a['grade']} (sales: {a['sales_status']}; "
                                              f"complaints: {a['complaint_status']}; first sale: "
                                              f"{a['first_sale_reliability']}).")}))
    return out
