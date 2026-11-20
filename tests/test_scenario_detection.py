"""Code-only checks on generated scenarios: the tools must find planted effects and must
NOT find effects in zero-effect controls. Answer keys are read here (evaluation side),
never by the application."""
import json

import pytest

from mei.adapters.synthetic import CsvMarketSource
from mei.analytics import cohort, complaints, launch, pricing, signals
from mei_synth.generate import generate

SEEDS = [11, 12, 13]


def _load(tmp_path, seed, variant):
    g = generate(seed, variant, tmp_path / "data", tmp_path / "keys")
    key = json.loads((tmp_path / "keys" / f"{g['scenario_id']}.json").read_text())
    return CsvMarketSource(g["data_dir"]).load(), key


@pytest.mark.parametrize("seed", SEEDS)
def test_positive_variant_detected(tmp_path, seed):
    md, key = _load(tmp_path, seed, "positive")
    r = key["roles"]
    assert signals.signal_trend(md, "battery", "Premium Thin & Light")["values"]["status"] == "intensified_long_standing"
    ids = cohort.define_cohort(md, r["A"])["values"]["cohort_ids"].split(",")
    assert cohort.launch_trajectory(md, r["A"], ids)["values"]["p_value"] < 0.05
    c = complaints.complaint_comparison(md, r["A"], ids, alternative="less")["values"]
    assert c["p_value"] < 0.05


@pytest.mark.parametrize("seed", SEEDS)
def test_null_variant_not_detected(tmp_path, seed):
    md, key = _load(tmp_path, seed, "null")
    r = key["roles"]
    ids = cohort.define_cohort(md, r["A"])["values"]["cohort_ids"].split(",")
    assert cohort.launch_trajectory(md, r["A"], ids)["values"]["p_value"] >= 0.05
    assert complaints.complaint_comparison(md, r["A"], ids, alternative="less")["values"]["p_value"] >= 0.05


@pytest.mark.parametrize("seed", SEEDS)
def test_traps_flagged(tmp_path, seed):
    md, key = _load(tmp_path, seed, "positive")
    r = key["roles"]
    assert launch.coverage_anomaly_months(md) == [key["coverage_expansion_month"]]
    assert launch.first_observed_sale(md, r["C"])["values"]["reliability"] == "unreliable"
    assert pricing.price_volume_pattern(md, r["B"])["values"]["pattern_detected"]
    ids = cohort.define_cohort(md, r["B"])["values"]["cohort_ids"].split(",")
    assert cohort.launch_trajectory(md, r["B"], ids, exclude_price_volume_months=True)["values"]["p_value"] >= 0.05


def test_generator_is_deterministic(tmp_path):
    a = generate(5, "positive", tmp_path / "a", tmp_path / "ka")
    b = generate(5, "positive", tmp_path / "b", tmp_path / "kb")
    for f in ("products.csv", "sellout_monthly.csv", "signal_counts.csv", "product_docs.csv"):
        assert (tmp_path / "a" / a["scenario_id"] / f).read_bytes() == (tmp_path / "b" / b["scenario_id"] / f).read_bytes()


def test_data_dir_contains_no_answer_information(tmp_path):
    g = generate(9, "positive", tmp_path / "data", tmp_path / "keys")
    d = tmp_path / "data" / g["scenario_id"]
    assert not list(d.glob("*key*"))
    blob = " ".join(p.read_text() for p in d.iterdir())
    for leak in ("variant", "positive", "null", "role", "answer"):
        assert leak not in blob.lower()
