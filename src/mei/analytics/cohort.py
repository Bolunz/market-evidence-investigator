"""Launch cohorts and launch-aligned sales comparisons.

Sales are expressed as SHARE OF SEGMENT SELL-OUT in each calendar month, which removes
market-wide seasonality and trend, then aligned on months since first observed sale.
Comparisons are descriptive: outperforming a cohort is an observation, not proof of why.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..contracts import period_to_index
from .launch import first_observed_sale, pinned_sellout
from .pricing import pattern_months
from .stats import exceedance_p, percentile_rank, prediction_t_p


def _segment_of(md, pid: str) -> str:
    return md.products.set_index("product_id").loc[pid, "segment"]


def _early_asp(s: pd.DataFrame, pid: str, n: int = 3) -> float:
    p = s[s["product_id"] == pid].groupby("period_month")[["units", "revenue_usd"]].sum()
    p = p.reindex(sorted(p.index, key=period_to_index)).iloc[:n]
    return float(p["revenue_usd"].sum() / max(p["units"].sum(), 1))


def define_cohort(md, product_id: str, window_months: int = 6, asp_tolerance: float = 0.30) -> dict:
    """Comparable products: same segment, first observed sale within +/- window of the
    target, early ASP within +/- tolerance, and a FOS that is not flagged unreliable."""
    s = pinned_sellout(md)
    seg = _segment_of(md, product_id)
    t_fos = first_observed_sale(md, product_id)["values"]
    t_idx = period_to_index(t_fos["first_observed_sale_month"])
    t_asp = _early_asp(s, product_id)
    seg_ids = md.products.loc[md.products["segment"] == seg, "product_id"]
    fos_all = s[s["product_id"].isin(seg_ids)].groupby("product_id")["period_month"].min()
    members, excluded_unreliable = [], []
    for pid, fm in fos_all.items():
        if pid == product_id or abs(period_to_index(fm) - t_idx) > window_months:
            continue
        asp = _early_asp(s, pid)
        if abs(asp / t_asp - 1) > asp_tolerance:
            continue
        if first_observed_sale(md, pid)["values"]["reliability"] == "unreliable":
            excluded_unreliable.append(pid)
            continue
        members.append({"product_id": pid, "first_observed_sale_month": fm, "early_asp": round(asp, 2)})
    values = {
        "target": product_id, "segment": seg, "target_first_observed_sale": t_fos["first_observed_sale_month"],
        "target_early_asp": round(t_asp, 2), "window_months": window_months, "asp_tolerance": asp_tolerance,
        "n_cohort": len(members), "cohort_ids": ",".join(m["product_id"] for m in members),
        "excluded_unreliable_fos": ",".join(excluded_unreliable) or "none",
    }
    return {"evidence_type": "cohort_definition", "values": values, "detail": {"members": members},
            "summary": (f"Cohort for {product_id}: {len(members)} {seg} models with first observed sale within "
                        f"+/-{window_months} months and early ASP within +/-{asp_tolerance:.0%}.")}


def _aligned_share(s: pd.DataFrame, seg_ids: set, pid: str, months: int, exclude: set[str]) -> list[float]:
    seg_tot = s[s["product_id"].isin(seg_ids)].groupby("period_month")["units"].sum()
    p = s[s["product_id"] == pid].groupby("period_month")["units"].sum()
    order = sorted(p.index, key=period_to_index)
    out = []
    start = period_to_index(order[0])
    for k in range(months):
        m = f"{(start + k) // 12}-M{(start + k) % 12 + 1:02d}"
        if m in exclude:
            out.append(np.nan)
        elif m in p.index and m in seg_tot.index:
            out.append(float(p[m] / seg_tot[m]))
        elif m in seg_tot.index:
            out.append(0.0)
        else:
            out.append(np.nan)
    return out


def launch_trajectory(md, product_id: str, cohort_ids: list[str], months: int = 12,
                      exclude_price_volume_months: bool = False, alternative: str = "greater") -> dict:
    """Mean segment share over the first `months` months since first observed sale,
    target vs cohort. Optionally drops each product's own price-and-volume pattern months.

    Test: prediction-interval t-test of the target's log mean share against the cohort's
    log mean shares (each cohort product = one observation). `alternative` must be declared
    before looking at results ("greater" for an outperformance hypothesis)."""
    s = pinned_sellout(md)
    seg = _segment_of(md, product_id)
    seg_ids = set(md.products.loc[md.products["segment"] == seg, "product_id"])
    cohort_ids = [c for c in cohort_ids if c != product_id]
    if not cohort_ids:
        return {"evidence_type": "launch_trajectory", "values": {"status": "empty_cohort"},
                "summary": "No cohort supplied; comparison not possible."}

    def series(pid):
        excl = {m["month"] for m in pattern_months(md, pid)} if exclude_price_volume_months else set()
        return _aligned_share(s, seg_ids, pid, months, excl)

    t = series(product_id)
    cs = {c: series(c) for c in cohort_ids}
    t_mean = float(np.nanmean(t)) if np.isfinite(t).any() else float("nan")
    c_means = [float(np.nanmean(v)) for v in cs.values() if np.isfinite(v).any()]
    months_used = int(np.isfinite(t).sum())
    cmat = np.array(list(cs.values()), dtype=float)
    with np.errstate(all="ignore"):
        med = np.nanmedian(cmat, axis=0)
        p25, p75 = np.nanpercentile(cmat, 25, axis=0), np.nanpercentile(cmat, 75, axis=0)
    c_med = float(np.median(c_means)) if c_means else float("nan")
    pr = percentile_rank(t_mean, c_means)
    pex = exceedance_p(t_mean, c_means)
    tstat, p_pred = prediction_t_p(np.log(max(t_mean, 1e-6)), [np.log(max(c, 1e-6)) for c in c_means], alternative)
    values = {
        "product_id": product_id, "segment": seg, "months_window": months, "months_used": months_used,
        "excluded_price_volume_months": exclude_price_volume_months,
        "target_mean_segment_share": t_mean, "cohort_median_segment_share": c_med,
        "ratio_to_cohort_median": t_mean / c_med if c_med else float("nan"),
        "percentile_in_cohort": pr, "p_value_exceedance": pex, "n_cohort": len(c_means),
        "n_products_compared": len(c_means) + 1,
        "t_stat": tstat, "p_value": p_pred, "alternative": alternative,
        "rank_in_cohort": int(sum(1 for c in c_means if c > t_mean) + 1),
    }
    detail = {"aligned_month": list(range(months)), "target": t, "cohort_median": med.tolist(),
              "cohort_p25": p25.tolist(), "cohort_p75": p75.tolist(), "cohort_ids": cohort_ids}
    return {
        "evidence_type": "launch_trajectory", "values": values, "detail": detail,
        "test": {"p_value": p_pred, "label": f"{product_id} launch-aligned share vs cohort"
                                          f"{' (pattern months excluded)' if exclude_price_volume_months else ''}"},
        "summary": (f"{product_id}: mean segment share {t_mean:.2%} over first {months_used} months since first "
                    f"observed sale vs cohort median {c_med:.2%} (rank {values['rank_in_cohort']} of "
                    f"{len(c_means) + 1}; prediction-interval p={p_pred:.3f}, {alternative})."),
    }
