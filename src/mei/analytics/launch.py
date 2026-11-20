"""First observed sale (FOS): the panel's first month with sell-out for a model.

FOS is NOT a launch date. It can be late (panel coverage added later, delayed tracking)
or censored (model already selling when history starts). Reliability flags make those
cases explicit; unreliable FOS values must not anchor launch-aligned comparisons.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..adapters.base import CAP_SELLOUT, MarketData
from ..contracts import period_to_index

NO_RAMP_RATIO = 0.6       # first-month units >= 60% of early peak suggests no visible ramp
DOC_GAP_MONTHS = 3        # positioning doc earlier than FOS by more than this -> flag


def pinned_sellout(md: MarketData, source: str | None = None) -> pd.DataFrame:
    """Sell-out pinned to exactly one source: measures must never be summed across sources."""
    md.require(CAP_SELLOUT)
    s = md.sellout
    sources = sorted(s["source"].unique())
    if source is None:
        if len(sources) != 1:
            raise ValueError(f"multiple sell-out sources {sources}: pin one explicitly")
        source = sources[0]
    return s[s["source"] == source]


def new_model_counts(md: MarketData, source: str | None = None) -> pd.Series:
    s = pinned_sellout(md, source)
    fos = s.groupby("product_id")["period_month"].min()
    counts = fos.value_counts()
    months = sorted(s["period_month"].unique(), key=period_to_index)
    return pd.Series({m: int(counts.get(m, 0)) for m in months})


def _no_ramp(monthly: pd.Series) -> bool:
    """`monthly` should be seasonally neutral (share of segment), not raw units."""
    early = monthly.iloc[:6]
    return len(early) >= 3 and early.iloc[0] >= NO_RAMP_RATIO * early.max()


def segment_share_series(md: MarketData, source: str | None = None) -> pd.Series:
    """Product units / segment units per month, indexed (product_id, period_month).
    Removes market seasonality so ramp shapes are comparable across months."""
    ck = ("segment_share_series", source)
    if ck in md.cache:
        return md.cache[ck]
    s = pinned_sellout(md, source).merge(md.products[["product_id", "segment"]], on="product_id")
    pu = s.groupby(["product_id", "segment", "period_month"])["units"].sum().reset_index()
    seg = pu.groupby(["segment", "period_month"])["units"].transform("sum")
    pu["share"] = pu["units"] / seg
    out = pu.set_index(["product_id", "period_month"])["share"]
    md.cache[ck] = out
    return out


def coverage_anomaly_months(md: MarketData, source: str | None = None) -> list[str]:
    """Months that look like a panel coverage change rather than a launch wave:
    (1) the count of newly observed models is anomalous (median + 3 scaled MADs and at
    least 3x the median), AND (2) most of those models show no visible ramp-up (they
    enter near full volume, as already-selling models do when a retailer is added).
    Genuine launch clusters ramp up and are not flagged. The first month is excluded."""
    ck = ("coverage_anomaly_months", source)
    if ck in md.cache:
        return list(md.cache[ck])
    s = pinned_sellout(md, source)
    monthly_all = segment_share_series(md, source)
    fos = s.groupby("product_id")["period_month"].min()
    c = new_model_counts(md, source).iloc[1:]
    med = float(np.median(c))
    mad = float(np.median(np.abs(c - med))) * 1.4826
    thr = max(med + 3 * max(mad, 1.0), 3 * max(med, 1.0))
    out = []
    for m, v in c.items():
        if v < thr:
            continue
        entrants = fos[fos == m].index
        flat = 0
        for pid in entrants:
            ser = monthly_all[pid]
            ser = ser.reindex(sorted(ser.index, key=period_to_index))
            flat += _no_ramp(ser)
        if flat / len(entrants) >= 0.5:
            out.append(m)
    md.cache[ck] = tuple(out)
    return out


def first_observed_sale(md: MarketData, product_id: str, source: str | None = None) -> dict:
    s = pinned_sellout(md, source)
    p = s[s["product_id"] == product_id]
    if p.empty:
        return {"evidence_type": "first_observed_sale",
                "values": {"product_id": product_id, "status": "never_observed"},
                "summary": f"{product_id}: no sell-out observed in this source."}
    monthly = p.groupby("period_month")["units"].sum()
    monthly = monthly.reindex(sorted(monthly.index, key=period_to_index))
    fos = monthly.index[0]
    hist_start = min(s["period_month"], key=period_to_index)
    flags = []
    if fos == hist_start:
        flags.append("left_censored")
    if fos in coverage_anomaly_months(md, source):
        flags.append("coverage_expansion_month")
    early = monthly.iloc[:6]
    share = segment_share_series(md, source)[product_id]
    share = share.reindex(sorted(share.index, key=period_to_index))
    if _no_ramp(share) and fos != hist_start:
        flags.append("no_visible_ramp")
    gap = None
    if md.product_docs is not None:
        d = md.product_docs[md.product_docs["product_id"] == product_id]
        if not d.empty:
            first_doc = min(d["published_month"], key=period_to_index)
            gap = period_to_index(fos) - period_to_index(first_doc)
            if gap > DOC_GAP_MONTHS:
                flags.append("positioning_doc_precedes_first_sale")
    if {"left_censored", "coverage_expansion_month"} & set(flags):
        reliability = "unreliable"
    elif flags:
        reliability = "caution"
    else:
        reliability = "usable"
    values = {
        "product_id": product_id, "first_observed_sale_month": fos, "months_observed": int(len(monthly)),
        "first_month_units": int(monthly.iloc[0]), "early_peak_units": int(early.max()),
        "doc_to_first_sale_gap_months": gap, "flags": ",".join(flags) or "none",
        "reliability": reliability,
    }
    return {
        "evidence_type": "first_observed_sale", "values": values,
        "summary": (f"{product_id}: first observed sale {fos} (an estimate of market entry, not a verified "
                    f"launch date); reliability={reliability}; flags={values['flags']}."),
    }
