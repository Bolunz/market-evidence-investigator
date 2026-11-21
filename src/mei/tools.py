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


# Statistical fields, for the LLM-facing view. Live run 01: the critic read the rank-based reference
# figure (0.067) as the test's p-value (0.004). The test now sits in its own block with its method and
# reading rule; confusable descriptive figures carry a definition next to them.
TEST_METHOD = {
    "launch_trajectory": "prediction-interval t-test of the product's log mean segment share against the "
                         "cohort products' (each cohort product is one observation)",
    "complaint_comparison": "product-level t-test of the product's logit complaint rate against the cohort "
                            "products' in the same months",
    "signal_trend": "two-proportion test of recent vs baseline complaint rate (Newcombe CI for the difference)",
}
TEST_FIELDS = ("p_value", "t_stat", "alternative")
DESCRIPTIVE_DEFS = {
    "empirical_rank_reference": "Rank-based reference figure: (cohort products at or above the target + 1) / "
                                "(cohort size + 1). It is NOT the test of the hypothesis: with this cohort size it "
                                "cannot fall below 1/(cohort size + 1), and it is one-sided whatever the declared "
                                "direction. Never use it to judge significance; use test.q_value_bh.",
    "percentile_in_cohort": "Descriptive position of the target among cohort products (1.0 = highest). "
                            "Not a test result.",
    "rank_in_cohort": "Descriptive rank among the products compared (1 = highest). Not a test result.",
}
READING_RULE = ("This block is the only statistical test in this evidence entry. Judge significance on "
                "q_value_bh < 0.05 (Benjamini-Hochberg within its test family); p_value is unadjusted.")


def observation(ev) -> dict:
    """Compact, LLM-facing view of an evidence entry. For a test: the test in its own `test` block
    (p, BH q, direction, method, status, reading rule); descriptive figures stay in `values`, with
    definitions for those that could be mistaken for a test result."""
    vals = {k: _round(v) for k, v in ev.values.items()}
    obs = {"evidence_id": ev.evidence_id, "summary": ev.summary}
    if ev.p_value is not None:
        test = {"p_value": _round(ev.p_value), "q_value_bh": _round(ev.q_value),
                "significant_after_bh": ev.q_value is not None and ev.q_value < 0.05,
                "alternative": vals.get("alternative", ev.params.get("alternative")),
                "hypothesis_status": ev.hypothesis_status, "test_family": ev.test_family,
                "method": TEST_METHOD.get(ev.tool, ev.test_label), "how_to_read": READING_RULE}
        if "t_stat" in vals:
            test["t_stat"] = vals["t_stat"]
        vals = {k: v for k, v in vals.items() if k not in TEST_FIELDS}
        obs["test"] = test
        defs = {k: DESCRIPTIVE_DEFS[k] for k in vals if k in DESCRIPTIVE_DEFS}
        if defs:
            obs["definitions"] = defs
    obs["values"] = vals
    key = DETAIL_FOR_LLM.get(ev.tool)
    if key and key in ev.detail:
        obs[key] = ev.detail[key]
    return obs


class ToolError(ValueError):
    pass


def classify_test(name: str, params: dict, requested_by: str, declared: set | None,
                  theme: str | None = None) -> str:
    """confirmatory  pre-specified: code screening tests, or a test matching a hypothesis (tool + direction)
                  declared in the plan BEFORE any test was run
    sensitivity   robustness re-runs (price-and-volume months excluded, or requested by the critic after
                  seeing results); may only RESTRICT conclusions
    exploratory   anything else the agent chose to test; reported, never used to raise a grade
    A complaint test on a theme other than the run's theme (e.g. a placebo) is never confirmatory."""
    if requested_by == "code":
        return "confirmatory"
    if params.get("exclude_price_volume_months") or requested_by == "critic":
        return "sensitivity"
    if theme and name == "complaint_comparison" and params.get("theme", theme) != theme:
        return "exploratory"          # e.g. a placebo theme: declared hypotheses are about the run's theme
    if declared and (name, params.get("alternative", "two-sided")) in declared:
        return "confirmatory"
    return "exploratory"


COHORT_TOOLS = ("launch_trajectory", "complaint_comparison")
INVESTIGATOR_ROLES = ("agent", "scripted")


def resolve_comparison_group(ledger: EvidenceLedger, tool: str, args: dict) -> tuple[dict, str | None]:
    """For a CRITIC-requested comparison test, take the comparison group from the investigation itself.

    Candidate groups = the cohort_ids of the investigator's own tests with the same tool on the same
    product (same analytical question). Exactly one distinct group: it is reused, and its evidence ID is
    returned as the source. None: rejected (the critic may not introduce a new, unreviewed group).
    Several distinct groups: rejected as ambiguous, never silently picked. A cohort_ids list the critic
    supplies itself must equal one of the candidate groups.
    Returns (args, source_evidence_id or None if nothing was filled in)."""
    if tool not in COHORT_TOOLS:
        return args, None
    pid = args.get("product_id")
    # the investigator's tests: the LLM agent ("agent") or the deterministic test policy ("scripted");
    # never the critic's own tests or code-run screening tests
    cands = [e for e in ledger.entries if e.tool == tool and e.requested_by in INVESTIGATOR_ROLES
             and e.params.get("product_id") == pid and e.params.get("cohort_ids")]
    groups: dict[tuple, list[str]] = {}
    for e in cands:
        groups.setdefault(tuple(sorted(e.params["cohort_ids"])), []).append(e.evidence_id)
    if args.get("cohort_ids"):
        if tuple(sorted(args["cohort_ids"])) in groups:
            return args, None
        raise ToolError(f"cohort_ids for {pid} do not match any comparison group the investigator used for "
                        f"{tool} on this product; the critic may only reuse an existing group")
    if not groups:
        raise ToolError(f"no {tool} test by the investigator on {pid}, so there is no comparison group to "
                        "reuse; the critic may not introduce a new one")
    if len(groups) > 1:
        srcs = "; ".join(",".join(v) for v in groups.values())
        raise ToolError(f"ambiguous comparison group for {pid}: the investigator used {len(groups)} different "
                        f"groups for {tool} ({srcs}); specify cohort_ids matching one of them")
    (group, srcs), = groups.items()
    src_ev = next(e for e in cands if e.evidence_id == srcs[0])
    return {**args, "cohort_ids": list(src_ev.params["cohort_ids"])}, srcs[0]


def run_tool(name: str, args: dict, md, ledger: EvidenceLedger, requested_by: str = "agent",
             declared: set[tuple[str, str]] | None = None, theme: str | None = None) -> tuple[object, dict]:
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
    status = classify_test(name, params, requested_by, declared, theme) if spec.is_test else None
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
