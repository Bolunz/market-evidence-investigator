"""Claim validation: strong unsupported statements are flagged; qualified versions pass."""
import json

import pytest

from mei.agents.schemas import Assertion, Claim, ReportDraft
from mei.run import run_investigation
from mei.validation.claims import validate_claims
from mei_synth.generate import generate


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("val")
    g = generate(42, "positive", tmp / "data", tmp / "keys")
    key = json.loads((tmp / "keys" / f"{g['scenario_id']}.json").read_text())
    res = run_investigation(g["data_dir"], tmp / "run", mode="scripted")
    return res, key["roles"]


def _ev(ledger, tool, **params):
    for e in ledger.entries:
        if e.tool == tool and all(e.params.get(k) == v for k, v in params.items()):
            return e
    raise KeyError((tool, params))


def _check(res, text, level, assertions):
    claim = Claim(claim_id="T1", section="D_sales_evidence", level=level, text=text,
                  assertions=[Assertion(type=t, subject=None, evidence_ids=ids) for t, ids in assertions])
    return validate_claims(ReportDraft(title="t", claims=[claim], follow_ups=[]), res["ledger"], res["md"].products)[0]


def test_launch_date_overclaim_flagged_but_qualified_statement_passes(run):
    res, r = run
    fos = _ev(res["ledger"], "first_observed_sale", product_id=r["A"])
    m = fos.values["first_observed_sale_month"]
    bad = _check(res, f"{r['A']} launched in {m}.", "observation", [("first_observed_sale", [fos.evidence_id])])
    assert bad.status == "flagged" and "launch_date_verified" in bad.implied
    ok = _check(res, f"{r['A']} first observed sale was {m}, which is not a verified launch date.",
                "method_note", [("first_observed_sale", [fos.evidence_id])])
    assert ok.status == "verified", ok.problems
    # discussing the distinction itself is allowed
    meta = _check(res, "First observed sale can differ from the actual product launch when panel coverage changes.",
                  "method_note", [("method_note", [])])
    assert meta.status == "verified", meta.problems


def test_promotion_and_causal_overclaims_flagged(run):
    res, r = run
    pv = _ev(res["ledger"], "price_volume_pattern", product_id=r["B"])
    bad = _check(res, f"The promotion drove {r['B']}'s early sales.", "observation",
                 [("price_volume_pattern", [pv.evidence_id])])
    assert bad.status == "flagged"
    assert {"promotion_confirmed", "causal_effect"} <= set(bad.implied)
    ok = _check(res, f"{r['B']} shows an observed price-and-volume pattern (promotion not confirmed).",
                "observation", [("price_volume_pattern", [pv.evidence_id])])
    assert ok.status == "verified", ok.problems


def test_wrong_number_flagged(run):
    res, r = run
    t = _ev(res["ledger"], "launch_trajectory", product_id=r["A"], exclude_price_volume_months=False)
    true = t.values["target_mean_segment_share"] * 100
    good = _check(res, f"{r['A']} averaged {true:.1f}% of segment sell-out.", "observation",
                  [("sales_comparison", [t.evidence_id])])
    assert good.status == "verified", good.problems
    bad = _check(res, f"{r['A']} averaged {true + 3:.1f}% of segment sell-out.", "observation",
                 [("sales_comparison", [t.evidence_id])])
    assert bad.status == "flagged" and any("not found in cited evidence" in p for p in bad.problems)


def test_association_requires_significant_test(run):
    res, r = run
    t = _ev(res["ledger"], "launch_trajectory", product_id=r["B"], exclude_price_volume_months=False)
    assert t.q_value >= 0.05
    bad = _check(res, f"{r['B']} sales are associated with its positioning.", "association",
                 [("sales_association", [t.evidence_id])])
    assert bad.status == "flagged" and any("not significant" in p for p in bad.problems)


def test_invented_products_flagged(run):
    res, _ = run
    oem = res["md"].products["oem"].iloc[0]
    e = res["ledger"].entries[0]
    bad = _check(res, f"The {oem} Zeta 99 G1 and P9999 also responded.", "observation",
                 [("signal_level", [e.evidence_id])])
    assert bad.status == "flagged"
    assert any("P9999" in p for p in bad.problems) and any(oem in p for p in bad.problems)


def test_demand_and_resolution_overclaims_flagged(run):
    res, r = run
    c = _ev(res["ledger"], "complaint_comparison", product_id=r["A"])
    bad = _check(res, f"{r['A']} solved the battery problem and consumers prefer long battery life.",
                 "observation", [("complaint_comparison", [c.evidence_id])])
    assert bad.status == "flagged"
    assert {"problem_resolved", "demand_or_preference"} <= set(bad.implied)
    ok = _check(res, f"Lower complaints for {r['A']} are consistent with, but do not establish, that it addressed "
                     "the need.", "explanation", [("alternative_explanation", [c.evidence_id])])
    assert ok.status == "verified", ok.problems


def test_grade_must_match_rubric_and_quotes_must_exist(run):
    res, r = run
    g = next(e for e in res["ledger"].by_type("confidence_assessment") if e.values.get("product_id") == r["A"])
    bad = _check(res, f"{r['A']}: rubric grade Strong.", "observation", [("confidence_grade", [g.evidence_id])])
    assert bad.status == "flagged"
    doc = next(e for e in res["ledger"].entries if e.tool == "get_product_doc" and e.values["product_id"] == r["A"])
    fake = _check(res, f"{r['A']} was marketed as \"the fastest charging laptop ever made\".", "observation",
                  [("positioning_claim", [doc.evidence_id])])
    assert fake.status == "flagged" and any("quoted text" in p for p in fake.problems)


def test_unknown_evidence_and_level_mismatch(run):
    res, _ = run
    bad = _check(res, "Something happened.", "observation", [("signal_level", ["E999"])])
    assert bad.status == "flagged" and any("unknown evidence" in p for p in bad.problems)
    e = res["ledger"].entries[0]
    bad = _check(res, "A hypothesis without the hypothesis assertion.", "hypothesis", [("signal_level", [e.evidence_id])])
    assert bad.status == "flagged"
