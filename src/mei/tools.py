"""Tool registry: the only way agents touch data.

Each tool is a deterministic analytical function. `run_tool` executes it, records the
result in the evidence ledger, and returns a compact observation (evidence ID + values)
for the LLM. Agents cite evidence IDs; they never compute numbers themselves.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal, Optional

from pydantic import BaseModel, Field, ValidationError

from .analytics import cohort, complaints, docs, launch, pricing, signals
from .ledger import EvidenceLedger


# ---------- argument schemas (shown to the LLM as tool definitions) ----------
class SearchDocsArgs(BaseModel):
    terms: list[str] = Field(description="Case-insensitive phrases to look for in product documents")
    segment: Optional[str] = Field(default=None, description="Restrict to one segment (optional)")


class DocArgs(BaseModel):
    doc_id: str


class ProductArgs(BaseModel):
    product_id: str


class CohortArgs(BaseModel):
    product_id: str
    window_months: int = Field(default=6, ge=1, le=12, description="+/- months around first observed sale")
    asp_tolerance: float = Field(default=0.30, gt=0, le=0.6, description="Early-ASP tolerance, e.g. 0.30 = +/-30%")


class TrajectoryArgs(BaseModel):
    product_id: str
    cohort_ids: list[str]
    months: int = Field(default=12, ge=3, le=24)
    exclude_price_volume_months: bool = False
    alternative: Literal["greater", "less", "two-sided"] = "greater"


class ComplaintArgs(BaseModel):
    product_id: str
    cohort_ids: list[str]
    theme: str = "battery"
    months: int = Field(default=12, ge=3, le=24)
    alternative: Literal["greater", "less", "two-sided"] = "two-sided"


class SignalTrendArgs(BaseModel):
    theme: str
    segment: Optional[str] = None


class SignalSegmentArgs(BaseModel):
    theme: str


@dataclass(frozen=True)
class ToolSpec:
    name: str
    fn: Callable
    args: type[BaseModel]
    description: str
    is_test: bool = False


REGISTRY: dict[str, ToolSpec] = {t.name: t for t in [
    ToolSpec("signal_trend", signals.signal_trend, SignalTrendArgs,
             "Complaint rate (complaints / all comments) by half-year for a theme and segment, with a "
             "baseline-vs-recent comparison and 95% CIs.", is_test=True),
    ToolSpec("signal_by_segment", signals.signal_by_segment, SignalSegmentArgs,
             "Complaint rate for a theme in each segment over the recent window."),
    ToolSpec("search_product_docs", docs.search_product_docs, SearchDocsArgs,
             "Find product documents (announcements, spec sheets) containing any of the terms. Returns "
             "snippets; it does NOT judge whether a product addresses a need. You must judge that."),
    ToolSpec("get_product_doc", docs.get_product_doc, DocArgs,
             "Full text of one product document."),
    ToolSpec("product_info", docs.product_info, ProductArgs,
             "Model name, OEM, segment and most common rated battery run time for a product."),
    ToolSpec("first_observed_sale", launch.first_observed_sale, ProductArgs,
             "First month with sell-out for a product (an estimate of market entry, NOT a verified launch "
             "date) plus reliability flags (left-censored, coverage-expansion month, no visible ramp)."),
    ToolSpec("define_cohort", cohort.define_cohort, CohortArgs,
             "Comparable products: same segment, first observed sale within +/- window, similar early ASP, "
             "excluding products whose first observed sale is unreliable."),
    ToolSpec("launch_trajectory", cohort.launch_trajectory, TrajectoryArgs,
             "Launch-aligned segment share for a product vs its cohort, with a product-level "
             "prediction-interval test. Declare `alternative` from your plan before calling.", is_test=True),
    ToolSpec("price_volume_pattern", pricing.price_volume_pattern, ProductArgs,
             "Months where ASP fell well below its trailing median while units jumped. An observed pattern; "
             "the data contain no promotion records."),
    ToolSpec("complaint_comparison", complaints.complaint_comparison, ComplaintArgs,
             "A product's complaint rate vs its cohort products in the same calendar months "
             "(product-level test).", is_test=True),
]}

DETAIL_FOR_LLM = {"search_product_docs": "hits", "get_product_doc": "text"}


def _round(v):
    if isinstance(v, float):
        return round(v, 4)
    return v


def observation(ev) -> dict:
    """Compact, LLM-facing view of an evidence entry."""
    obs = {"evidence_id": ev.evidence_id, "summary": ev.summary,
           "values": {k: _round(v) for k, v in ev.values.items()}}
    if ev.p_value is not None:
        obs["p_value"] = _round(ev.p_value)
        obs["q_value_bh"] = _round(ev.q_value)
        obs["hypothesis_status"] = ev.hypothesis_status
    key = DETAIL_FOR_LLM.get(ev.tool)
    if key and key in ev.detail:
        obs[key] = ev.detail[key]
    return obs


class ToolError(ValueError):
    pass


def run_tool(name: str, args: dict, md, ledger: EvidenceLedger, requested_by: str = "agent",
             declared: set[tuple[str, str]] | None = None) -> tuple[object, dict]:
    """Validate args, execute, record. `declared` = {(tool, alternative)} from the plan; a test
    outside it is recorded as exploratory."""
    spec = REGISTRY.get(name)
    if spec is None:
        raise ToolError(f"unknown tool '{name}'")
    try:
        parsed = spec.args.model_validate(args)
    except ValidationError as e:
        raise ToolError(f"invalid arguments for {name}: {e.errors()[0]['msg']}") from e
    params = parsed.model_dump()
    result = spec.fn(md, **params)
    status = None
    if spec.is_test:
        alt = params.get("alternative", "two-sided")
        status = "declared" if declared and (name, alt) in declared else "exploratory"
        if requested_by == "code":
            status = "declared"           # fixed, pre-specified screening tests
    ev = ledger.record(name, params, result, requested_by=requested_by, hypothesis_status=status)
    return ev, observation(ev)


def anthropic_tool_defs(names: list[str]) -> list[dict]:
    """Tool definitions in the provider-neutral format LangChain's bind_tools accepts."""
    out = []
    for n in names:
        spec = REGISTRY[n]
        schema = spec.args.model_json_schema()
        out.append({"name": n, "description": spec.description,
                    "input_schema": {"type": "object", "properties": schema.get("properties", {}),
                                     "required": schema.get("required", [])}})
    return out
