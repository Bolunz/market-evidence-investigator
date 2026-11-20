"""Post-first-sale complaint comparison: a product vs its cohort in the SAME calendar months.

Primary test is PRODUCT-LEVEL: the target's complaint rate (logit) against the
distribution of cohort products' rates over the same months (prediction-interval
t-test). Pooling all comments would treat comments as independent and ignore that
products differ persistently, which overstates certainty.

A lower complaint rate is consistent with the product addressing the need, but also with
a different buyer mix, firmware updates, attention shifting, or small samples. The tool
reports the difference and its uncertainty; it does not claim the problem was solved.
"""
from __future__ import annotations

import math

from ..adapters.base import CAP_SIGNALS
from ..contracts import index_to_period, period_to_index
from .launch import first_observed_sale
from .stats import prediction_t_p, wilson_ci

MIN_COMMENTS_PER_PRODUCT = 30


def _logit(k: int, n: int) -> float:
    p = (k + 0.5) / (n + 1.0)          # continuity-corrected
    return math.log(p / (1 - p))


def complaint_comparison(md, product_id: str, cohort_ids: list[str], theme: str = "battery",
                         months: int = 12, alternative: str = "two-sided") -> dict:
    md.require(CAP_SIGNALS)
    fos = first_observed_sale(md, product_id)["values"].get("first_observed_sale_month")
    if fos is None:
        return {"evidence_type": "complaint_comparison", "values": {"status": "no_first_sale"},
                "summary": f"{product_id}: no first observed sale; comparison not possible."}
    start = period_to_index(fos)
    window = {index_to_period(start + k) for k in range(months)}
    sig = md.signals[(md.signals["theme"] == theme) & (md.signals["period_month"].isin(window))]
    per = sig.groupby("product_id")[["complaints", "comments"]].sum()
    if product_id not in per.index or per.loc[product_id, "comments"] < MIN_COMMENTS_PER_PRODUCT:
        return {"evidence_type": "complaint_comparison", "values": {"status": "insufficient_comments",
                                                                    "product_id": product_id},
                "summary": f"{product_id}: fewer than {MIN_COMMENTS_PER_PRODUCT} comments; comparison not possible."}
    kt, nt = int(per.loc[product_id, "complaints"]), int(per.loc[product_id, "comments"])
    cohort = per[per.index.isin([c for c in cohort_ids if c != product_id])]
    cohort = cohort[cohort["comments"] >= MIN_COMMENTS_PER_PRODUCT]
    if len(cohort) < 3:
        return {"evidence_type": "complaint_comparison", "values": {"status": "cohort_too_small",
                                                                    "product_id": product_id},
                "summary": f"{product_id}: fewer than 3 cohort products with enough comments."}
    rates = (cohort["complaints"] / cohort["comments"]).tolist()
    logits = [_logit(int(r.complaints), int(r.comments)) for r in cohort.itertuples()]
    tstat, p = prediction_t_p(_logit(kt, nt), logits, alternative)
    rt = kt / nt
    rates_sorted = sorted(rates)
    rc_med = rates_sorted[len(rates_sorted) // 2] if len(rates_sorted) % 2 else \
        sum(rates_sorted[len(rates_sorted) // 2 - 1:len(rates_sorted) // 2 + 1]) / 2
    tl, th = wilson_ci(kt, nt)
    if p < 0.05 and rt < rc_med:
        direction = "lower_than_cohort"
    elif p < 0.05 and rt > rc_med:
        direction = "higher_than_cohort"
    else:
        direction = "no_detectable_difference"
    values = {
        "product_id": product_id, "theme": theme,
        "window": f"{index_to_period(start)}..{index_to_period(start + months - 1)}",
        "target_rate": rt, "target_ci_low": tl, "target_ci_high": th, "target_complaints": kt, "target_comments": nt,
        "cohort_median_rate": rc_med, "cohort_min_rate": min(rates), "cohort_max_rate": max(rates),
        "n_cohort_products": len(rates), "diff_vs_cohort_median": rt - rc_med,
        "t_stat": tstat, "p_value": p, "alternative": alternative,
        "rank_lowest_first": int(sum(1 for r in rates if r < rt) + 1), "direction_at_0.05": direction,
    }
    return {
        "evidence_type": "complaint_comparison", "values": values,
        "test": {"p_value": p, "label": f"{product_id} {theme} complaint rate vs cohort products (same months)"},
        "summary": (f"{product_id}: {theme} complaint rate {rt:.1%} [95% CI {tl:.1%}-{th:.1%}] vs cohort median "
                    f"{rc_med:.1%} across {len(rates)} products in the same months (product-level p={p:.3f}, "
                    f"{alternative}); {direction}."),
    }
