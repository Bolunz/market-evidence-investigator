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
