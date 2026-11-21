"""The LLM-facing view keeps the test result apart from descriptive figures (regression from live
run 01: the critic read the rank-based reference 0.067 as the test's p-value 0.004)."""
import json
import re
from pathlib import Path

import pytest

from mei.adapters.synthetic import CsvMarketSource
from mei.ledger import EvidenceLedger, replay_check
from mei.tools import REGISTRY, run_tool

DATA = Path(__file__).resolve().parents[1] / "examples" / "data" / "battery_s42"
COHORT = ["P0003", "P0005", "P0015", "P0016", "P0032", "P0042", "P0079", "P0088", "P0099", "P0102", "P0107",
          "P0125", "P0126", "P0147"]


@pytest.fixture(scope="module")
def md():
    return CsvMarketSource(DATA).load()


def _p_like_keys(obj, path=""):
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if re.search(r"p_?val|exceedance", k, re.I):
                out.append(f"{path}{k}")
            out += _p_like_keys(v, f"{path}{k}.")
    return out


@pytest.mark.parametrize("tool,args", [
    ("launch_trajectory", {"product_id": "P0113", "cohort_ids": COHORT, "alternative": "two-sided"}),
    ("complaint_comparison", {"product_id": "P0113", "cohort_ids": COHORT, "alternative": "less"}),
    ("signal_trend", {"theme": "battery", "segment": "Premium Thin & Light"}),
])
def test_one_p_value_per_test_and_it_sits_in_the_test_block(md, tool, args):
    led = EvidenceLedger()
    ev, obs = run_tool(tool, args, md, led, requested_by="code")
    assert _p_like_keys(obs) == ["test.p_value"]
    t = obs["test"]
    assert {"p_value", "q_value_bh", "significant_after_bh", "alternative", "method", "how_to_read"} <= set(t)
    assert t["p_value"] == round(ev.p_value, 4)


def test_rank_reference_is_defined_as_not_the_test(md):
    led = EvidenceLedger()
    ev, obs = run_tool("launch_trajectory", {"product_id": "P0113", "cohort_ids": COHORT,
                                             "alternative": "two-sided"}, md, led, requested_by="agent")
    ref = obs["values"]["empirical_rank_reference"]
    assert ref == pytest.approx(1 / 15, abs=1e-4)            # the 0.067 from live run 01
    assert obs["test"]["p_value"] < 0.01                      # the actual test (0.004)
    assert "NOT the test" in obs["definitions"]["empirical_rank_reference"]
    assert "q_value_bh" in obs["test"]["how_to_read"]
    # the ledger keeps every number for audit, under the clearer name
    assert "empirical_rank_reference" in ev.values and "p_value_exceedance" not in ev.values


def test_archived_live_run_01_ledger_still_reexecutes(md):
    """Run 01 was recorded before the rename; the re-execution check maps the legacy key."""
    path = Path(__file__).resolve().parents[1] / "evaluation" / "live_runs" / "run01_2026-11-20" / "ledger.json"
    led = EvidenceLedger.load(path)
    assert any("p_value_exceedance" in e.values for e in led.entries)
    assert replay_check(led, md, REGISTRY) == []
