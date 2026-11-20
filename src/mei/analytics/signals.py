"""Consumer-signal tools: complaint rates over time, by segment, with uncertainty."""
from __future__ import annotations

import pandas as pd

from ..adapters.base import CAP_SIGNALS, MarketData
from ..contracts import period_to_index
from .stats import newcombe_diff_ci, two_proportion_p, wilson_ci

# Emergence classification thresholds (documented in docs/methodology.md)
MIN_COMPLAINTS = 30          # below this in either window -> insufficient
EMERGING_BASELINE_MAX = 0.01  # baseline rate at/below this = effectively absent before
MIN_ABS_CHANGE = 0.005       # material change needs >= 0.5 percentage points ...
MIN_REL_CHANGE = 0.20        # ... and >= 20% relative change (large n makes tiny shifts "significant")


def _period_label(pm: str, grain: str) -> str:
    y, m = pm.split("-M")
    if grain == "year":
        return y
    return f"{y}-H{1 if int(m) <= 6 else 2}"


def _filter(md: MarketData, theme: str, segment: str | None, product_ids: list[str] | None) -> pd.DataFrame:
    md.require(CAP_SIGNALS)
    s = md.signals[md.signals["theme"] == theme]
    if segment:
        s = s[s["segment"] == segment]
    if product_ids:
        s = s[s["product_id"].isin(product_ids)]
    return s


def _window(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    i = df["period_month"].map(period_to_index)
    return df[(i >= period_to_index(start)) & (i <= period_to_index(end))]


def signal_trend(md: MarketData, theme: str, segment: str | None = None,
                 baseline: tuple[str, str] | None = None, recent: tuple[str, str] | None = None,
                 grain: str = "half") -> dict:
    """Complaint rate (complaints / all comments) by period, plus a baseline-vs-recent test."""
    s = _filter(md, theme, segment, None)
    if s.empty:
        return {"evidence_type": "signal_trend", "values": {"status": "no_data"},
                "summary": f"No signal rows for theme={theme} segment={segment}."}
    months = sorted(s["period_month"].unique(), key=period_to_index)
    if baseline is None:
        baseline = (months[0], months[min(17, len(months) - 1)])
    if recent is None:
        recent = (months[max(0, len(months) - 18)], months[-1])

    s = s.assign(period=s["period_month"].map(lambda p: _period_label(p, grain)))
    g = s.groupby("period").agg(comments=("comments", "sum"), complaints=("complaints", "sum"),
                                mentions=("theme_mentions", "sum")).reset_index()
    series = []
    for _, r in g.iterrows():
        lo, hi = wilson_ci(int(r.complaints), int(r.comments))
        series.append({"period": r.period, "comments": int(r.comments), "complaints": int(r.complaints),
                       "rate": r.complaints / r.comments, "ci_low": lo, "ci_high": hi,
                       "mention_rate": r.mentions / r.comments})

    b, rc = _window(s, *baseline), _window(s, *recent)
    kb, nb = int(b["complaints"].sum()), int(b["comments"].sum())
    kr, nr = int(rc["complaints"].sum()), int(rc["comments"].sum())
    if min(nb, nr) == 0:
        return {"evidence_type": "signal_trend", "values": {"status": "insufficient_window"},
                "detail": {"series": series}, "summary": "A comparison window has no comments."}
    rb, rr = kb / nb, kr / nr
    dlo, dhi = newcombe_diff_ci(kr, nr, kb, nb)
    p = two_proportion_p(kr, nr, kb, nb)

    material = abs(rr - rb) >= MIN_ABS_CHANGE and abs(rr - rb) >= MIN_REL_CHANGE * max(rb, 1e-9)
    if max(kb, kr) < MIN_COMPLAINTS:
        status = "insufficient_observations"
    elif rb <= EMERGING_BASELINE_MAX and dlo > 0 and material:
        status = "emerging"
    elif dlo > 0 and material:
        status = "intensified_long_standing"
    elif dhi < 0 and material:
        status = "declining"
    else:
        status = "no_material_change"

    # concentration: share of recent complaints from the single largest product
    top_share = 0.0
    if kr:
        top_share = float(rc.groupby("product_id")["complaints"].sum().max() / kr)

    values = {
        "theme": theme, "segment": segment or "ALL",
        "baseline_window": f"{baseline[0]}..{baseline[1]}", "recent_window": f"{recent[0]}..{recent[1]}",
        "baseline_rate": rb, "recent_rate": rr, "baseline_complaints": kb, "baseline_comments": nb,
        "recent_complaints": kr, "recent_comments": nr,
        "diff": rr - rb, "diff_ci_low": dlo, "diff_ci_high": dhi, "p_value": p,
        "status": status, "top_product_share_of_recent_complaints": top_share,
        "n_products_recent": int(rc["product_id"].nunique()),
    }
    return {
        "evidence_type": "signal_trend", "values": values, "detail": {"series": series, "grain": grain},
        "test": {"p_value": p, "label": f"{theme} complaint rate recent vs baseline ({segment or 'ALL'})"},
        "summary": (f"{theme} complaint rate in {segment or 'all segments'}: {rb:.1%} baseline -> {rr:.1%} recent "
                    f"(diff {rr - rb:+.1%}, 95% CI {dlo:+.1%} to {dhi:+.1%}); status={status}."),
    }


def signal_by_segment(md: MarketData, theme: str, window: tuple[str, str] | None = None) -> dict:
    """Complaint rate by segment in one window (which segments are affected?)."""
    s = _filter(md, theme, None, None)
    months = sorted(s["period_month"].unique(), key=period_to_index)
    if window is None:
        window = (months[max(0, len(months) - 18)], months[-1])
    w = _window(s, *window)
    rows = []
    for seg, d in w.groupby("segment"):
        k, n = int(d["complaints"].sum()), int(d["comments"].sum())
        lo, hi = wilson_ci(k, n)
        rows.append({"segment": seg, "complaints": k, "comments": n, "rate": k / n, "ci_low": lo, "ci_high": hi})
    rows.sort(key=lambda r: -r["rate"])
    values = {"theme": theme, "window": f"{window[0]}..{window[1]}"}
    for r in rows:
        key = r["segment"].lower().replace(" & ", "_").replace(" ", "_")
        values[f"rate_{key}"] = r["rate"]
        values[f"ci_low_{key}"] = r["ci_low"]
        values[f"ci_high_{key}"] = r["ci_high"]
    return {"evidence_type": "signal_by_segment", "values": values, "detail": {"segments": rows},
            "summary": "; ".join(f"{r['segment']}: {r['rate']:.1%} [{r['ci_low']:.1%}, {r['ci_high']:.1%}]"
                                 for r in rows)}
