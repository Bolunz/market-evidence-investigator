"""Analytical tools on a hand-built market with hand-computed answers."""
import pandas as pd
import pytest

from mei.adapters.base import CapabilityError, MarketData
from mei.analytics import cohort, docs, launch, pricing, signals
from mei.contracts import CONTRACTS, validate_table


def test_fixture_satisfies_contracts(tiny_market):
    assert validate_table(tiny_market.sellout, CONTRACTS["sellout_monthly"]) == []
    assert validate_table(tiny_market.signals, CONTRACTS["signal_counts"]) == []


def test_contract_catches_bad_period_and_negative_units(tiny_market):
    bad = tiny_market.sellout.copy()
    bad.loc[0, "period_month"] = "2021-13"
    bad.loc[1, "units"] = -1
    problems = validate_table(bad, CONTRACTS["sellout_monthly"])
    assert any("YYYY-Mnn" in p for p in problems) and any("negative" in p for p in problems)


def test_first_observed_sale_and_flags(tiny_market):
    x1 = launch.first_observed_sale(tiny_market, "X1")["values"]
    assert x1["first_observed_sale_month"] == "2021-M01"
    assert "left_censored" in x1["flags"] and x1["reliability"] == "unreliable"
    x2 = launch.first_observed_sale(tiny_market, "X2")["values"]
    assert x2["first_observed_sale_month"] == "2021-M03"
    assert x2["reliability"] == "usable" and x2["doc_to_first_sale_gap_months"] == 1
    x3 = launch.first_observed_sale(tiny_market, "X3")["values"]
    # X3 enters at full volume and its doc predates first sale by 9 months
    assert "no_visible_ramp" in x3["flags"]
    assert "positioning_doc_precedes_first_sale" in x3["flags"]
    assert x3["reliability"] == "caution"


def test_fos_text_never_calls_it_a_launch_date(tiny_market):
    s = launch.first_observed_sale(tiny_market, "X2")["summary"]
    assert "not a verified launch date" in s


def test_sellout_must_be_pinned_to_one_source(tiny_market):
    two = tiny_market.sellout.copy()
    extra = two.copy()
    extra["source"] = "OTHER"
    md = MarketData("x", tiny_market.capabilities, tiny_market.products, pd.concat([two, extra]))
    with pytest.raises(ValueError, match="pin one"):
        launch.first_observed_sale(md, "X2")


def test_price_volume_pattern_hand_computed(tiny_market):
    r = pricing.price_volume_pattern(tiny_market, "X1")["values"]
    assert r["pattern_detected"] and r["pattern_months"] == "2021-M06"
    assert r["max_asp_drop"] == pytest.approx(-0.2)
    assert r["max_unit_jump"] == pytest.approx(0.6)
    assert "promotion not confirmed" in r["label"]
    assert not pricing.price_volume_pattern(tiny_market, "X2")["values"]["pattern_detected"]


def test_launch_trajectory_share_hand_computed(tiny_market):
    r = cohort.launch_trajectory(tiny_market, "X2", ["X3"], months=3)
    t = r["detail"]["target"]
    # segment S units: M03 = 50+10+40 = 100, M04 = 50+20+40 = 110, M05 = 50+40+40 = 130
    assert t == pytest.approx([0.10, 20 / 110, 40 / 130])
    assert r["values"]["months_used"] == 3


def test_signal_trend_rates(tiny_market):
    r = signals.signal_trend(tiny_market, "battery", "S", baseline=("2021-M01", "2021-M02"),
                             recent=("2021-M07", "2021-M08"))["values"]
    assert r["baseline_rate"] == pytest.approx(5 / 100)        # only X1 in M01-M02
    assert r["recent_rate"] == pytest.approx((5 + 2 + 8) * 2 / 600)


def test_doc_search_returns_text_without_judging(tiny_market):
    r = docs.search_product_docs(tiny_market, ["battery"])
    ids = {h["doc_id"] for h in r["detail"]["hits"]}
    assert ids == {"D1", "D2"}                 # incidental mention returned too; agent must judge
    full = docs.get_product_doc(tiny_market, "D1")
    assert "18 hours" in full["detail"]["text"]


def test_missing_capability_raises(tiny_market):
    md = MarketData("signals-only", {"signals"}, tiny_market.products, signals=tiny_market.signals)
    with pytest.raises(CapabilityError):
        launch.first_observed_sale(md, "X2")
