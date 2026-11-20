import pandas as pd
import pytest

from mei.adapters.base import CAP_PRODUCT_DOCS, CAP_SELLOUT, CAP_SIGNALS, MarketData

MONTHS = [f"2021-M{m:02d}" for m in range(1, 9)]


def _rows(pid, start, units, asp):
    out = []
    for k, (u, a) in enumerate(zip(units, asp)):
        out.append({"period_month": MONTHS[start + k], "source": "PANEL", "country": "US",
                    "channel_type": "Retail", "product_id": pid, "price_band": "$900-$999",
                    "battery_run_time": "10 hr", "cpu_family": "F", "units": u, "revenue_usd": u * a})
    return out


@pytest.fixture
def tiny_market() -> MarketData:
    """Hand-built market with known answers.
    X1: selling from the first month (left-censored); ASP cut 1000->800 with units 50->80 in M06.
    X2: enters M03 with a ramp (10, 20, 40, 40, 40, 40).
    X3: enters M03 already at full volume (no ramp in share terms).
    Y1: other segment, enters M04.
    """
    products = pd.DataFrame([
        {"product_id": p, "oem": "O", "model": f"Model {p}", "form_factor": "Notebook",
         "segment": seg, "screen_size": "14"}
        for p, seg in [("X1", "S"), ("X2", "S"), ("X3", "S"), ("Y1", "T")]])
    sell = (_rows("X1", 0, [50, 50, 50, 50, 50, 80, 50, 50], [1000] * 5 + [800] + [1000] * 2)
            + _rows("X2", 2, [10, 20, 40, 40, 40, 40], [1000] * 6)
            + _rows("X3", 2, [40, 40, 40, 40, 40, 40], [1000] * 6)
            + _rows("Y1", 3, [30, 30, 30, 30, 30], [500] * 5))
    docs = pd.DataFrame([
        {"doc_id": "D1", "product_id": "X2", "doc_type": "announcement", "published_month": "2021-M02",
         "text": "Model X2 offers up to 18 hours of battery life. It is light."},
        {"doc_id": "D2", "product_id": "X3", "doc_type": "announcement", "published_month": "2020-M06",
         "text": "Model X3 has a bright display and battery saver mode."},
    ])
    sig = []
    for pid, seg, start, n, k in [("X1", "S", 0, 100, 5), ("X2", "S", 2, 100, 2), ("X3", "S", 2, 100, 8),
                                  ("Y1", "T", 3, 100, 4)]:
        for m in MONTHS[start:]:
            sig.append({"period_month": m, "product_id": pid, "segment": seg, "theme": "battery",
                        "comments": n, "theme_mentions": k + 3, "complaints": k, "unique_authors": n - 5})
    return MarketData(source_label="tiny", capabilities={CAP_SELLOUT, CAP_SIGNALS, CAP_PRODUCT_DOCS},
                      products=products, sellout=pd.DataFrame(sell), product_docs=docs,
                      signals=pd.DataFrame(sig))
