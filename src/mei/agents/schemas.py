"""Structured outputs produced by the LLM roles. Free text is confined to fields that the
validator audits; everything else is IDs, enums and evidence references."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

Alternative = Literal["greater", "less", "two-sided"]


class Hypothesis(BaseModel):
    hypothesis_id: str = Field(description="Short ID, e.g. H1")
    statement: str = Field(description="Testable statement, phrased as an association, not a cause")
    test_tool: Literal["launch_trajectory", "complaint_comparison"]
    alternative: Alternative = Field(description="Direction declared BEFORE seeing results")


class InvestigationPlan(BaseModel):
    focus_segment: str = Field(description="Segment to investigate, chosen from the signal profile")
    rationale: str = Field(description="Why this segment, citing signal evidence IDs")
    search_terms: list[str] = Field(description="Phrases to search product documents for positioning on the need")
    hypotheses: list[Hypothesis] = Field(description="Declared hypotheses; at most 4")
    evidence_ids: list[str] = Field(default_factory=list)


Positioning = Literal["positioned_on_need", "incidental_mention", "not_positioned", "segment_mismatch"]


class ProductFinding(BaseModel):
    product_id: str
    positioning: Positioning = Field(description="Your judgement from the document text")
    doc_id: Optional[str] = Field(default=None, description="Document supporting the positioning judgement")
    quote: Optional[str] = Field(default=None, description="Exact text copied from that document")
    first_sale_evidence_id: Optional[str] = None
    cohort_evidence_id: Optional[str] = None
    sales_evidence_ids: list[str] = Field(default_factory=list)
    price_volume_evidence_id: Optional[str] = None
    complaint_evidence_ids: list[str] = Field(default_factory=list)
    observations: str = Field(description="What the evidence shows, plainly, citing evidence IDs")
    open_questions: list[str] = Field(default_factory=list)


class InvestigationFindings(BaseModel):
    findings: list[ProductFinding]
    products_considered_and_excluded: list[str] = Field(
        default_factory=list, description="product_id: reason, for products found but not pursued")
    summary: str


class AlternativeExplanation(BaseModel):
    product_id: str
    explanation: str
    would_distinguish: str = Field(description="What evidence would tell this apart from the main reading")
    addressed_by: list[str] = Field(default_factory=list, description="Evidence IDs that already bear on it")


class RequestedTest(BaseModel):
    tool: Literal["launch_trajectory", "complaint_comparison", "price_volume_pattern", "first_observed_sale",
                  "define_cohort"]
    args: dict
    reason: str


class Critique(BaseModel):
    alternative_explanations: list[AlternativeExplanation]
    requested_test: Optional[RequestedTest] = Field(default=None, description="At most one extra test")
    downgrade_recommendations: list[str] = Field(default_factory=list)


ClaimLevel = Literal["observation", "association", "explanation", "hypothesis", "method_note", "evidence_gap"]
Section = Literal["A_consumer_signal", "B_historical_context", "C_market_response", "D_sales_evidence",
                  "E_evidence_assessment", "F_opportunity_hypotheses"]

AssertionType = Literal[
    "signal_level", "signal_change", "first_observed_sale", "fos_reliability", "launch_date_verified",
    "positioning_claim", "cohort_definition", "sales_comparison", "sales_association",
    "price_volume_pattern", "promotion_confirmed", "complaint_comparison", "complaint_association",
    "confidence_grade", "causal_effect", "problem_resolved", "demand_or_preference",
    "availability_or_distribution", "alternative_explanation", "opportunity_hypothesis",
    "evidence_gap", "method_note",
]


class Assertion(BaseModel):
    type: AssertionType
    subject: Optional[str] = Field(default=None, description="product_id or segment the assertion is about")
    evidence_ids: list[str] = Field(default_factory=list)


class Claim(BaseModel):
    claim_id: str
    section: Section
    level: ClaimLevel
    text: str = Field(description="One or two sentences. Numbers must be copied from cited evidence values.")
    assertions: list[Assertion]


class ReportDraft(BaseModel):
    title: str
    claims: list[Claim]
    follow_ups: list[str] = Field(description="Specific follow-up investigations for the analyst")


class ImpliedAssertions(BaseModel):
    """Output of the claim auditor: what a free-text claim actually asserts."""
    implied: list[AssertionType]
    reason: str
