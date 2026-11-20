"""End-to-end workflow (scripted policy, no LLM) against answer keys, plus capability routing."""
import json
import shutil

import pytest

from mei.adapters.synthetic import CsvMarketSource
from mei.ledger import replay_check
from mei.run import run_investigation
from mei.tools import REGISTRY
from mei_synth.generate import generate


def _grades(res):
    return {e.values["product_id"]: e.values for e in res["ledger"].by_type("confidence_assessment")
            if "product_id" in e.values}


@pytest.mark.parametrize("seed,variant", [(42, "positive"), (7, "null"), (21, "positive"), (22, "null")])
def test_end_to_end_matches_answer_key(tmp_path, seed, variant):
    g = generate(seed, variant, tmp_path / "data", tmp_path / "keys")
    key = json.loads((tmp_path / "keys" / f"{g['scenario_id']}.json").read_text())
    r = key["roles"]
    res = run_investigation(g["data_dir"], tmp_path / "run", mode="scripted")
    st = res["state"]
    assert st["path"] == "direct_response"
    assert st["plan"]["focus_segment"] == key["expected"]["signal_rising_in_segment"]
    pos = {f["product_id"]: f["positioning"] for f in st["findings"]["findings"]}
    assert pos[r["A"]] == pos[r["B"]] == pos[r["C"]] == "positioned_on_need"
    assert pos[r["G"]] == "segment_mismatch"
    gr = _grades(res)
    assert gr[r["A"]]["grade"] == ("Moderate" if variant == "positive" else "Not supported")
    assert gr[r["B"]]["grade"] in ("Not supported", "Weak") and gr[r["B"]]["price_volume_pattern"]
    assert gr[r["B"]]["sales_status"] != "supported"
    assert gr[r["C"]]["grade"] == "Insufficient" and gr[r["C"]]["first_sale_reliability"] == "unreliable"
    assert all(c["status"] == "verified" for c in st["checks"]), [c for c in st["checks"] if c["status"] != "verified"]
    assert (tmp_path / "run" / "report.html").exists()
    assert replay_check(res["ledger"], res["md"], REGISTRY) == []


def test_signals_only_source_marks_market_response_not_assessed(tmp_path):
    g = generate(42, "positive", tmp_path / "data", tmp_path / "keys")
    d = tmp_path / "signals_only"
    d.mkdir()
    for f in ("products.csv", "signal_counts.csv"):
        shutil.copy(f"{g['data_dir']}/{f}", d / f)
    md = CsvMarketSource(d).load()
    assert md.capabilities == {"signals"}
    res = run_investigation(d, tmp_path / "run", mode="scripted")
    assert res["state"]["path"] == "not_assessed_market_response"
    text = (tmp_path / "run" / "report.md").read_text()
    assert "not assessed" in text.lower() and "data-availability boundary" in text


def test_no_signal_increase_gives_insufficient_signal(tmp_path):
    g = generate(42, "positive", tmp_path / "data", tmp_path / "keys")
    import pandas as pd
    s = pd.read_csv(f"{g['data_dir']}/signal_counts.csv")
    s.loc[s["theme"] == "battery", "complaints"] = (s.loc[s["theme"] == "battery", "comments"] * 0.04).round().astype(int)
    s.to_csv(f"{g['data_dir']}/signal_counts.csv", index=False)
    res = run_investigation(g["data_dir"], tmp_path / "run", mode="scripted")
    assert res["state"]["path"] == "insufficient_signal"
    assert "plan" not in res["state"]


def test_removing_product_docs_never_invents_responses(tmp_path):
    g = generate(42, "positive", tmp_path / "data", tmp_path / "keys")
    import pandas as pd
    p = f"{g['data_dir']}/product_docs.csv"
    d = pd.read_csv(p)
    d[d["doc_type"] == "spec_sheet"].to_csv(p, index=False)      # announcements removed
    res = run_investigation(g["data_dir"], tmp_path / "run", mode="scripted")
    assert res["state"]["path"] == "no_direct_response"
    assert not any(f["positioning"] == "positioned_on_need" for f in res["state"]["findings"]["findings"])
