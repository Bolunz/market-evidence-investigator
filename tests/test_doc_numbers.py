"""Specification figures quoted from cited product documents (regression from live run 01, where
'up to 20 / 17 / 18 hours' were wrongly flagged). Computed statistics stay strict."""
import pandas as pd
import pytest

from mei.agents.schemas import Assertion, Claim, ReportDraft
from mei.ledger import EvidenceLedger
from mei.validation.claims import validate_claims

PRODUCTS = pd.DataFrame({"product_id": ["P0113", "P0050", "P0120"],
                         "model": ["Altura Aero 13 G4", "Brevik Aero 14 G4", "Corvane Lumen 14 G2"],
                         "oem": ["Altura", "Brevik", "Corvane"]})


@pytest.fixture()
def led():
    led = EvidenceLedger()
    led.record("get_product_doc", {"doc_id": "D0113A"},                                     # E001
               {"evidence_type": "product_doc", "values": {"doc_id": "D0113A", "product_id": "P0113"},
                "detail": {"text": "Introducing the Altura Aero 13 G4: engineered for endurance, with up to "
                                   "20 hours of battery life."}})
    led.record("search_product_docs", {"terms": ["all-day battery"]},                     # E002
               {"evidence_type": "product_doc_search", "values": {"n_hits": 1},
                "detail": {"hits": [{"doc_id": "D0050A", "product_id": "P0050",
                                     "snippet": "The new Brevik Aero 14 G4 brings all-day battery that lasts "
                                                "up to 17 hours, in a design under 1.3 kg."}]}})
    led.record("launch_trajectory", {"product_id": "P0113", "alternative": "two-sided"},     # E003
               {"evidence_type": "launch_trajectory",
                "values": {"target_mean_segment_share": 0.1809, "cohort_median_segment_share": 0.0388},
                "test": {"p_value": 0.0037}}, requested_by="agent", hypothesis_status="confirmatory")
    return led


def _check(led, text, assertions, level="observation"):
    c = Claim(claim_id="C1", section="C_market_response", level=level, text=text,
              assertions=[Assertion(type=t, evidence_ids=ids) for t, ids in assertions])
    return validate_claims(ReportDraft(title="t", claims=[c], follow_ups=[]), led, PRODUCTS)[0]


def test_correctly_attributed_manufacturer_claims_pass(led):
    # the live-run-01 claim C4, reduced to the two documents in this fixture
    r = _check(led, "Documented positioning on battery life exists for P0113 (Altura Aero 13 G4, up to 20 hours) "
                    "and P0050 (Brevik Aero 14 G4, up to 17 hours). This is positioning, not proof that the need "
                    "was solved.", [("positioning_claim", ["E001"]), ("positioning_claim", ["E002"])])
    assert r.status == "verified", r.problems
    r = _check(led, "The Altura Aero 13 G4 is advertised with 20 hours of battery life.",
               [("positioning_claim", ["E001"])])
    assert r.status == "verified", r.problems


def test_number_attributed_to_the_wrong_product_is_flagged(led):
    r = _check(led, "P0113 is advertised with up to 17 hours of battery life.",
               [("positioning_claim", ["E001", "E002"])])
    assert r.status == "flagged"
    assert any("document for P0050, not for P0113" in p for p in r.problems)


def test_manufacturer_figure_presented_as_verified_performance_is_flagged(led):
    r = _check(led, "P0113 delivered a measured 20 hours of real-world battery life.",
               [("positioning_claim", ["E001"])])
    assert any("presented as verified performance" in p for p in r.problems)
    r = _check(led, "P0113 runs for 20 hours on a charge.", [("positioning_claim", ["E001"])])
    assert any("must be attributed as a manufacturer claim" in p for p in r.problems)


def test_wrong_unit_or_uncited_document_is_flagged(led):
    r = _check(led, "P0113 is advertised with up to 20 Wh.", [("positioning_claim", ["E001"])])
    assert any("number '20' not found" in p for p in r.problems)
    # the document is cited, but not by a positioning_claim assertion: no exception
    r = _check(led, "P0113 is advertised with up to 20 hours.", [("sales_comparison", ["E003", "E001"])])
    assert any("number '20' not found" in p for p in r.problems)


def test_computed_statistics_remain_strict(led):
    ok = _check(led, "P0113's mean segment share was 18.09% versus a cohort median of 3.88%.",
                [("sales_comparison", ["E003"])])
    assert ok.status == "verified", ok.problems
    bad = _check(led, "P0113's mean segment share was 19.5% versus a cohort median of 3.88%.",
                 [("sales_comparison", ["E003"]), ("positioning_claim", ["E001"])])
    assert any("number '19.5%' not found" in p for p in bad.problems)
    # a percentage can never be taken from document text
    led.record("get_product_doc", {"doc_id": "X"}, {"evidence_type": "product_doc",
               "values": {"doc_id": "X", "product_id": "P0113"}, "detail": {"text": "up to 25% longer battery life"}})
    r = _check(led, "P0113 is advertised with up to 25% longer battery life.", [("positioning_claim", ["E004"])])
    assert any("number '25%' not found" in p for p in r.problems)
