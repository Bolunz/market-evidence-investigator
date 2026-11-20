"""LLM code path, offline: a fake chat model drives a 'live' run, which records a cache;
a replay run then reproduces it with no model at all."""
import json

import pytest

from mei.llm.client import LLMClient, ReplayMissError
from mei.run import run_investigation
from mei_synth.generate import generate

from .fake_llm import factory


@pytest.fixture(scope="module")
def recorded(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("llm")
    g = generate(42, "positive", tmp / "data", tmp / "keys")
    cache = tmp / "cache.jsonl"
    live = run_investigation(g["data_dir"], tmp / "live", mode="live", cache_path=cache, chat_factory=factory)
    return tmp, g, cache, live


def test_live_path_runs_react_loop_and_revision(recorded):
    _, _, cache, live = recorded
    st = live["state"]
    assert st["path"] == "direct_response"
    agent_tools = [e for e in live["ledger"].entries if e.requested_by == "agent"]
    assert {e.tool for e in agent_tools} >= {"search_product_docs", "first_observed_sale", "define_cohort",
                                             "launch_trajectory", "complaint_comparison"}
    assert all(e.hypothesis_status == "confirmatory" for e in agent_tools if e.p_value is not None)
    # like the real planner in the smoke test, the fake declares a TWO-SIDED sales hypothesis;
    # the rubric must still grade it (regression: it used to count only one-sided "greater" tests)
    grades = [e.values for e in live["ledger"].by_type("confidence_assessment") if "product_id" in e.values]
    assert grades and all(g["sales_status"] not in ("exploratory_only", "not_tested") for g in grades)
    # first draft had a causal overclaim -> flagged -> one revision -> all verified
    assert st["revisions"] == 1
    assert all(c["status"] == "verified" for c in st["checks"])
    kinds = [t["kind"] for t in live["trace"]]
    assert "guard" in kinds and "route" in kinds
    roles = {json.loads(line)["role"] for line in cache.read_text().splitlines()}
    assert {"planner", "investigator", "critic", "writer", "auditor"} <= roles


def test_replay_reproduces_live_run_without_a_model(recorded):
    tmp, g, cache, live = recorded
    rep = run_investigation(g["data_dir"], tmp / "replay", mode="replay", cache_path=cache)
    assert rep["state"]["draft"] == live["state"]["draft"]
    assert rep["state"]["checks"] == live["state"]["checks"]
    lv = [(e.tool, e.params, e.values) for e in live["ledger"].entries]
    rv = [(e.tool, e.params, e.values) for e in rep["ledger"].entries]
    assert lv == rv
    assert rep["meta"]["usage"]["calls"] == live["meta"]["usage"]["calls"]


def test_replay_miss_is_explicit(tmp_path):
    client = LLMClient("replay", tmp_path / "empty.jsonl")
    from langchain_core.messages import HumanMessage
    with pytest.raises(ReplayMissError):
        client.invoke("planner", [HumanMessage("hello")])


def test_live_mode_without_key_fails_clearly(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        LLMClient("live", tmp_path / "c.jsonl")


_RECORD = """
import sys, json
sys.path.insert(0, sys.argv[1])
from tests.fake_llm import factory
from mei.run import run_investigation
from mei_synth.generate import generate
from pathlib import Path
tmp = Path(sys.argv[2])
g = generate(42, "positive", tmp / "data", tmp / "keys")
run_investigation(g["data_dir"], tmp / "live", mode="live", cache_path=tmp / "cache.jsonl", chat_factory=factory)
print(json.dumps([json.loads(l)["key"] for l in open(tmp / "cache.jsonl")]))
"""


def test_cache_keys_identical_across_processes_with_different_hash_seeds(tmp_path):
    """Regression from the first live run: a set's iteration order leaked into the writer prompt, so a
    recording made in one Python process could not be replayed in another."""
    import os
    import subprocess
    import sys
    from pathlib import Path
    root = str(Path(__file__).resolve().parents[1])
    keys = []
    for seed in ("1", "2"):
        out = tmp_path / seed
        out.mkdir()
        env = {**os.environ, "PYTHONHASHSEED": seed, "ANTHROPIC_API_KEY": ""}
        r = subprocess.run([sys.executable, "-c", _RECORD, root, str(out)], env=env,
                           capture_output=True, text=True, timeout=600)
        assert r.returncode == 0, r.stderr[-2000:]
        keys.append(json.loads(r.stdout.strip().splitlines()[-1]))
    assert keys[0] == keys[1]
