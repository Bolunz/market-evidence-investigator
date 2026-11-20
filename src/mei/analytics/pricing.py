"""Observed price-and-volume patterns.

A month where ASP falls well below its trailing median while units jump well above
theirs. This is an OBSERVED PATTERN. The panel has no list price or promotion flag, so
the tool never asserts that a promotion occurred.
"""
from __future__ import annotations

import pandas as pd

from ..contracts import period_to_index
from .launch import pinned_sellout

PATTERN_LABEL = "observed price-and-volume pattern (promotion not confirmed)"


def monthly_product(md, product_id: str, source: str | None = None) -> pd.DataFrame:
    s = pinned_sellout(md, source)
    p = s[s["product_id"] == product_id].groupby("period_month")[["units", "revenue_usd"]].sum()
    p = p.reindex(sorted(p.index, key=period_to_index))
    p["asp"] = p["revenue_usd"] / p["units"]
    return p


def pattern_months(md, product_id: str, asp_drop: float = 0.12, unit_jump: float = 1.3,
                   source: str | None = None) -> list[dict]:
    p = monthly_product(md, product_id, source)
    out = []
    for i in range(2, len(p)):
        prior = p.iloc[max(0, i - 3):i]
        asp_ref, units_ref = prior["asp"].median(), prior["units"].median()
        row = p.iloc[i]
        if row.asp <= (1 - asp_drop) * asp_ref and row.units >= unit_jump * units_ref:
            out.append({"month": p.index[i], "asp_vs_trailing": row.asp / asp_ref - 1,
                        "units_vs_trailing": row.units / units_ref - 1})
    return out


def price_volume_pattern(md, product_id: str, asp_drop: float = 0.12, unit_jump: float = 1.3) -> dict:
    months = pattern_months(md, product_id, asp_drop, unit_jump)
    values = {
        "product_id": product_id, "pattern_detected": bool(months), "n_pattern_months": len(months),
        "pattern_months": ",".join(m["month"] for m in months) or "none",
        "max_asp_drop": min((m["asp_vs_trailing"] for m in months), default=0.0),
        "max_unit_jump": max((m["units_vs_trailing"] for m in months), default=0.0),
        "label": PATTERN_LABEL, "asp_drop_threshold": asp_drop, "unit_jump_threshold": unit_jump,
    }
    summ = (f"{product_id}: {len(months)} month(s) with {PATTERN_LABEL}: {values['pattern_months']}."
            if months else f"{product_id}: no price-and-volume pattern at thresholds "
                           f"(ASP -{asp_drop:.0%}, units +{unit_jump - 1:.0%}).")
    return {"evidence_type": "price_volume_pattern", "values": values, "detail": {"months": months},
            "summary": summ}
