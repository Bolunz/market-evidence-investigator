"""Data adapter interface.

An adapter turns some source (synthetic CSVs, a sell-out cube extract, a comment
pipeline) into the contract tables and declares which investigation capabilities it can
support. The workflow routes on these capabilities, so a source that lacks sales data
produces "not assessed" sections rather than invented ones.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

CAP_SIGNALS = "signals"            # consumer-signal counts by product/segment/theme
CAP_PRODUCT_DOCS = "product_docs"  # public positioning documents
CAP_SELLOUT = "sellout"            # model-level monthly sell-out


@dataclass
class MarketData:
    source_label: str
    capabilities: set[str]
    products: pd.DataFrame | None = None
    sellout: pd.DataFrame | None = None
    product_docs: pd.DataFrame | None = None
    signals: pd.DataFrame | None = None
    file_hashes: dict[str, str] = field(default_factory=dict)
    synthetic: bool = True
    cache: dict = field(default_factory=dict, repr=False)   # per-load memo for derived tables

    def require(self, cap: str) -> None:
        if cap not in self.capabilities:
            raise CapabilityError(f"capability '{cap}' not available from source '{self.source_label}'")


class CapabilityError(RuntimeError):
    pass


class DataSource:
    """Interface: implement `load()` returning MarketData."""

    def load(self) -> MarketData:  # pragma: no cover - interface
        raise NotImplementedError
