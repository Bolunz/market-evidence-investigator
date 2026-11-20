"""Adapter for the synthetic CSV market under data/synthetic/<scenario_id>/.

Reads ONLY the data directory it is given. It never reads answer keys.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from ..contracts import CONTRACTS, ContractError, validate_table
from .base import CAP_PRODUCT_DOCS, CAP_SELLOUT, CAP_SIGNALS, DataSource, MarketData

FILES = {
    "products": "products.csv",
    "sellout_monthly": "sellout_monthly.csv",
    "product_docs": "product_docs.csv",
    "signal_counts": "signal_counts.csv",
}


class CsvMarketSource(DataSource):
    def __init__(self, data_dir: str | Path, source_label: str | None = None):
        self.data_dir = Path(data_dir)
        self.source_label = source_label or self.data_dir.name

    def load(self) -> MarketData:
        tables: dict[str, pd.DataFrame] = {}
        hashes: dict[str, str] = {}
        problems: list[str] = []
        for name, fname in FILES.items():
            path = self.data_dir / fname
            if not path.exists():
                continue
            df = pd.read_csv(path, dtype={"screen_size": str, "price_band": str, "battery_run_time": str})
            problems += validate_table(df, CONTRACTS[name])
            tables[name] = df
            hashes[fname] = hashlib.sha256(path.read_bytes()).hexdigest()
        if problems:
            raise ContractError("; ".join(problems))
        caps = set()
        if "signal_counts" in tables:
            caps.add(CAP_SIGNALS)
        if "product_docs" in tables:
            caps.add(CAP_PRODUCT_DOCS)
        if "sellout_monthly" in tables:
            caps.add(CAP_SELLOUT)
        synthetic = True
        mf = self.data_dir / "manifest.json"
        if mf.exists():
            synthetic = bool(json.loads(mf.read_text()).get("synthetic", True))
        return MarketData(
            source_label=self.source_label, capabilities=caps,
            products=tables.get("products"), sellout=tables.get("sellout_monthly"),
            product_docs=tables.get("product_docs"), signals=tables.get("signal_counts"),
            file_hashes=hashes, synthetic=synthetic,
        )
