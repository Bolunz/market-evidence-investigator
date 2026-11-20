"""Runtime guards: .env loading, spending cap, test-status classification, multiplicity families."""
import os

import pytest
from langchain_core.messages import HumanMessage

from mei.config import load_env, price_for
from mei.ledger import EvidenceLedger
from mei.llm.client import BudgetExceeded, LLMClient
from mei.tools import classify_test

from .fake_llm import factory

# dummy keys assembled at runtime so the publish scanner never sees a key-shaped literal
FAKE = "sk-" + "ant-test-" + "0123456789abcdef"
FAKE_FILE = "sk-" + "ant-file-" + "0123456789abcdef"
FAKE_SHELL = "sk-" + "ant-shell-" + "0123456789abcdef"


def test_env_file_is_actually_loaded(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    (tmp_path / ".env").write_text(f"ANTHROPIC_API_KEY={FAKE}\nMEI_MAX_COST_USD=1.25\n")
    monkeypatch.chdir(tmp_path)
    info = load_env()
    assert info["dotenv_path"] == str(tmp_path / ".env")
    assert info["key_source"] == ".env file" and info["key_present"]
    assert os.environ["ANTHROPIC_API_KEY"] == FAKE
    assert "0123456789" not in info["key_masked"]                 # never printed in full
    assert info["max_cost_usd"] == 1.25
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    monkeypatch.delenv("MEI_MAX_COST_USD")


def test_shell_key_takes_precedence_and_is_reported(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(f"ANTHROPIC_API_KEY={FAKE_FILE}\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_SHELL)
    info = load_env()
    assert info["key_source"] == "shell environment" and info["shell_overrides_file"]


def test_prices_have_defaults_and_overrides(monkeypatch):
    assert price_for("claude-sonnet-5-5") == (2.0, 10.0)
    monkeypatch.setenv("MEI_PRICE_IN_CLAUDE_SONNET_5_5", "3")
    assert price_for("claude-sonnet-5-5")[0] == 3.0


def test_spending_cap_refuses_call_before_spending(tmp_path):
    c = LLMClient("live", tmp_path / "c.jsonl", max_cost_usd=0.01, chat_factory=factory)
    with pytest.raises(BudgetExceeded, match="spending cap"):
        c.invoke("planner", [HumanMessage("x" * 1000)])     # worst case = 16k output tokens at $10/MTok > $0.01
    assert c.usage.calls == 0


def test_call_cap(tmp_path):
    c = LLMClient("live", tmp_path / "c.jsonl", max_calls=1, max_cost_usd=100, chat_factory=factory)
    c.usage.calls = 1
    with pytest.raises(BudgetExceeded, match="call cap"):
        c.invoke("planner", [HumanMessage("hi")])


def test_hypothesis_status_classification():
    declared = {("launch_trajectory", "greater"), ("complaint_comparison", "less")}
    assert classify_test("signal_trend", {}, "code", None) == "confirmatory"
    assert classify_test("launch_trajectory", {"alternative": "greater"}, "agent", declared) == "confirmatory"
    assert classify_test("launch_trajectory", {"alternative": "two-sided"}, "agent", declared) == "exploratory"
    assert classify_test("launch_trajectory", {"alternative": "greater", "exclude_price_volume_months": True},
                       "agent", declared) == "sensitivity"
    assert classify_test("complaint_comparison", {"alternative": "less"}, "critic", declared) == "sensitivity"


def test_families_and_pooled_q():
    led = EvidenceLedger()
    led.record("signal_trend", {}, {"test": {"p_value": 0.001}}, requested_by="code", hypothesis_status="confirmatory")
    led.record("launch_trajectory", {}, {"test": {"p_value": 0.02}}, hypothesis_status="confirmatory")
    led.record("launch_trajectory", {}, {"test": {"p_value": 0.03}}, hypothesis_status="exploratory")
    led.record("complaint_comparison", {}, {"test": {"p_value": 0.04}}, hypothesis_status="confirmatory")
    fam = [e.test_family for e in led.entries]
    assert fam == ["signal_screening", "sales_confirmatory", "sensitivity_exploratory", "complaints_confirmatory"]
    # single-member families keep q = p; pooled BH across 4 tests is larger
    assert led.entries[1].q_value == pytest.approx(0.02)
    assert led.entries[1].q_pooled == pytest.approx(0.04)


def test_smoke_test_code_paths_offline(tmp_path, monkeypatch):
    """Runs every smoke step against the fake model (the real API is exercised on the user's machine)."""
    from mei.smoke import run_smoke

    from .fake_llm import FakeModels
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE)
    lines = []
    res = run_smoke("examples/data/battery_s42", str(tmp_path / "smoke"), report=lines.append,
                    chat_factory=factory, models_api=FakeModels())
    assert res["failed"] == 0, lines
    assert res["passed"] == 7
    assert (tmp_path / "smoke" / "smoke_report.json").exists()
    assert FAKE not in (tmp_path / "smoke" / "smoke_report.json").read_text()


def test_provider_errors_mapped_by_status_code_not_class_name():
    """Regression from the live smoke test: langchain-anthropic raises AnthropicModelNotFoundError."""
    from mei.llm.client import LLMRequestError, _explain

    class AnthropicModelNotFoundError(Exception):
        status_code = 404

    class SomeWrapperRateLimitThing(Exception):
        status_code = 429

    class Unauthorized(Exception):
        status_code = 401

    assert isinstance(_explain(AnthropicModelNotFoundError("x"), "m"), LLMRequestError)
    assert "404" in str(_explain(AnthropicModelNotFoundError("x"), "m"))
    assert "after 3 automatic retries" in str(_explain(SomeWrapperRateLimitThing("x"), "m"))
    assert "401" in str(_explain(Unauthorized("x"), "m"))


def _traj(led, pid, alt, ratio, p, status="confirmatory"):
    led.record("launch_trajectory", {"product_id": pid, "alternative": alt, "exclude_price_volume_months": False},
               {"values": {"ratio_to_cohort_median": ratio}, "test": {"p_value": p}}, hypothesis_status=status)


def test_rubric_accepts_two_sided_declared_hypothesis_with_direction():
    from mei.validation.rubric import assess_product
    led = EvidenceLedger()
    _traj(led, "PA", "two-sided", 3.5, 0.001)
    _traj(led, "PB", "two-sided", 0.4, 0.001)
    _traj(led, "PC", "two-sided", 3.5, 0.40)
    _traj(led, "PD", "greater", 3.5, 0.001, status="exploratory")
    assert assess_product(led, "PA")["sales_status"] == "supported"
    assert assess_product(led, "PB")["sales_status"] == "underperformed_cohort"
    assert assess_product(led, "PC")["sales_status"] == "not_supported"
    assert assess_product(led, "PD")["sales_status"] == "exploratory_only"
