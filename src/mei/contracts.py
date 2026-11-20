"""Data contracts: the table shapes every data adapter must deliver.

The shapes mirror a typical retail sell-out panel (monthly, model-level, specs stored
as text on each fact row, no launch date, no list price, no distribution measure) plus
a consumer-signal table and a product-document table. Real sources (e.g. an internal
sell-out cube or a YouTube comment pipeline) plug in by producing these same tables.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd

PERIOD_RE = re.compile(r"^\d{4}-M(0[1-9]|1[0-2])$")


@dataclass(frozen=True)
class TableContract:
    name: str
    required: dict[str, str]          # column -> logical type: str | int | float | period
    key: tuple[str, ...]
    description: str


PRODUCTS = TableContract(
    name="products",
    required={
        "product_id": "str", "oem": "str", "model": "str", "form_factor": "str",
        "segment": "str", "screen_size": "str",
    },
    key=("product_id",),
    description="One row per model. No launch date (none exists in the panel).",
)

SELLOUT = TableContract(
    name="sellout_monthly",
    required={
        "period_month": "period", "source": "str", "country": "str", "channel_type": "str",
        "product_id": "str", "price_band": "str", "battery_run_time": "str",
        "cpu_family": "str", "units": "int", "revenue_usd": "float",
    },
    key=("period_month", "source", "country", "channel_type", "product_id"),
    description="Monthly sell-out by model. Specs and price band are row-level text.",
)

PRODUCT_DOCS = TableContract(
    name="product_docs",
    required={
        "doc_id": "str", "product_id": "str", "doc_type": "str",
        "published_month": "period", "text": "str",
    },
    key=("doc_id",),
    description="Public positioning documents (announcements, spec sheets).",
)

SIGNALS = TableContract(
    name="signal_counts",
    required={
        "period_month": "period", "product_id": "str", "segment": "str", "theme": "str",
        "comments": "int", "theme_mentions": "int", "complaints": "int", "unique_authors": "int",
    },
    key=("period_month", "product_id", "theme"),
    description=(
        "Consumer-signal counts per product-month-theme. `comments` is ALL comments about the "
        "product that month (the denominator); `complaints` is the classifier-labelled subset "
        "expressing a complaint or unmet need about the theme."
    ),
)

CONTRACTS = {c.name: c for c in (PRODUCTS, SELLOUT, PRODUCT_DOCS, SIGNALS)}


class ContractError(ValueError):
    pass


def validate_table(df: pd.DataFrame, contract: TableContract) -> list[str]:
    """Return a list of problems (empty list = valid)."""
    problems: list[str] = []
    missing = [c for c in contract.required if c not in df.columns]
    if missing:
        return [f"{contract.name}: missing columns {missing}"]
    for col, kind in contract.required.items():
        s = df[col]
        if kind == "period":
            bad = ~s.astype(str).str.match(PERIOD_RE)
            if bad.any():
                problems.append(f"{contract.name}.{col}: {int(bad.sum())} values not in YYYY-Mnn format")
        elif kind in ("int", "float"):
            if not pd.api.types.is_numeric_dtype(s):
                problems.append(f"{contract.name}.{col}: not numeric")
            elif (s < 0).any():
                problems.append(f"{contract.name}.{col}: {int((s < 0).sum())} negative values")
    dup = df.duplicated(list(contract.key)).sum()
    if dup:
        problems.append(f"{contract.name}: {int(dup)} duplicate keys on {contract.key}")
    return problems


def period_to_index(p: str) -> int:
    """'2023-M04' -> months since year 0 (monotone integer for arithmetic)."""
    y, m = p.split("-M")
    return int(y) * 12 + int(m) - 1


def index_to_period(i: int) -> str:
    return f"{i // 12}-M{i % 12 + 1:02d}"
