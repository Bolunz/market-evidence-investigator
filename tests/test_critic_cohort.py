"""Critic-requested tests take their comparison group from the investigation, never by assumption."""
import pytest

from mei.ledger import EvidenceLedger
from mei.tools import ToolError, classify_test, resolve_comparison_group
from mei.validation.rubric import assess_product

G1 = ["P0003", "P0005", "P0015"]
G2 = ["P0003", "P0005", "P0016"]


def _comp(led, pid, cohort, theme="battery", diff=-0.05, p=0.001, by="agent", status="confirmatory"):
    return led.record("complaint_comparison",
                      {"product_id": pid, "cohort_ids": cohort, "theme": theme, "months": 12, "alternative": "less"},
                      {"values": {"diff_vs_cohort_median": diff, "p_value": p}, "test": {"p_value": p}},
                      requested_by=by, hypothesis_status=status)


def test_reuses_the_single_group_of_the_same_product_and_tool():
    led = EvidenceLedger()
    src = _comp(led, "PA", G1)
    _comp(led, "PB", G2)                                   # another product: not a candidate
    args, source = resolve_comparison_group(led, "complaint_comparison", {"product_id": "PA", "theme": "display"})
    assert args["cohort_ids"] == G1 and source == src.evidence_id and args["theme"] == "display"


def test_same_group_used_twice_is_not_ambiguous():
    led = EvidenceLedger()
    _comp(led, "PA", G1)
    _comp(led, "PA", list(reversed(G1)), p=0.2)
    args, _ = resolve_comparison_group(led, "complaint_comparison", {"product_id": "PA"})
    assert sorted(args["cohort_ids"]) == sorted(G1)


def test_multiple_groups_are_rejected_not_silently_chosen():
    led = EvidenceLedger()
    _comp(led, "PA", G1)
    _comp(led, "PA", G2)
    with pytest.raises(ToolError, match="ambiguous comparison group"):
        resolve_comparison_group(led, "complaint_comparison", {"product_id": "PA"})


def test_no_investigator_group_is_rejected():
    led = EvidenceLedger()
    _comp(led, "PA", G1, by="critic", status="sensitivity")          # critic's own tests never count
    led.record("launch_trajectory", {"product_id": "PA", "cohort_ids": G2, "alternative": "two-sided"},
               {"values": {}, "test": {"p_value": 0.01}}, requested_by="agent", hypothesis_status="confirmatory")
    with pytest.raises(ToolError, match="no complaint_comparison test by the investigator"):
        resolve_comparison_group(led, "complaint_comparison", {"product_id": "PA"})


def test_critic_supplied_group_must_match_an_investigator_group():
    led = EvidenceLedger()
    _comp(led, "PA", G1)
    args, source = resolve_comparison_group(led, "complaint_comparison", {"product_id": "PA", "cohort_ids": G1})
    assert source is None and args["cohort_ids"] == G1
    with pytest.raises(ToolError, match="do not match"):
        resolve_comparison_group(led, "complaint_comparison", {"product_id": "PA", "cohort_ids": G2})


def test_other_tools_pass_through():
    led = EvidenceLedger()
    assert resolve_comparison_group(led, "price_volume_pattern", {"product_id": "PA"}) == ({"product_id": "PA"}, None)


def test_off_theme_complaint_test_is_never_confirmatory_or_graded():
    declared = {("complaint_comparison", "less"), ("launch_trajectory", "greater")}
    p = {"theme": "display", "alternative": "less"}
    assert classify_test("complaint_comparison", p, "agent", declared, theme="battery") == "exploratory"
    assert classify_test("complaint_comparison", p, "critic", declared, theme="battery") == "sensitivity"
    assert classify_test("complaint_comparison", {**p, "theme": "battery"}, "agent", declared,
                         theme="battery") == "confirmatory"
    # a placebo recorded AFTER the battery test, even if labelled confirmatory, must not set the grade
    led = EvidenceLedger()
    _comp(led, "PA", G1, theme="battery", diff=-0.05, p=0.001)
    _comp(led, "PA", G1, theme="display", diff=+0.05, p=0.001)
    assert assess_product(led, "PA", "battery")["complaint_status"] == "lower_than_cohort"


def test_critic_placebo_without_cohort_runs_in_the_workflow(tmp_path):
    """End to end with the fake model: the critic asks for a display placebo without cohort_ids (as the
    real critic did in live run 01); code reuses the investigator's group and the grade is unaffected."""
    from mei.run import run_investigation
    from mei_synth.generate import generate

    from .fake_llm import factory
    g = generate(42, "positive", tmp_path / "data", tmp_path / "keys")
    out = run_investigation(g["data_dir"], tmp_path / "live", mode="live", cache_path=tmp_path / "c.jsonl",
                            chat_factory=factory)
    led = out["ledger"]
    crit = [e for e in led.entries if e.requested_by == "critic"]
    assert len(crit) == 1 and crit[0].params["theme"] == "display" and crit[0].hypothesis_status == "sensitivity"
    inv = [e for e in led.entries if e.requested_by == "agent" and e.tool == "complaint_comparison"
           and e.params["product_id"] == crit[0].params["product_id"]]
    assert crit[0].params["cohort_ids"] == inv[0].params["cohort_ids"]
    assert out["state"]["critique"]["requested_test"]["cohort_source"] == inv[0].evidence_id
    grade = [e.values for e in led.by_type("confidence_assessment")
             if e.values.get("product_id") == crit[0].params["product_id"]][0]
    assert crit[0].evidence_id not in grade["based_on"].split(",")


def test_scripted_investigator_groups_count_too():
    """Regression found by the 100-run sweep: the scripted policy's tests are requested_by='scripted'."""
    led = EvidenceLedger()
    src = _comp(led, "PA", G1, by="scripted")
    args, source = resolve_comparison_group(led, "complaint_comparison", {"product_id": "PA", "cohort_ids": G1})
    assert source is None and args["cohort_ids"] == G1
    assert resolve_comparison_group(led, "complaint_comparison", {"product_id": "PA"})[1] == src.evidence_id
