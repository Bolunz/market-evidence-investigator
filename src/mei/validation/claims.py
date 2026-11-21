"""Evidence-aware claim validation.

Claims are checked for what they ASSERT against the evidence they CITE, not for keywords:
  1. cited evidence IDs exist
  2. each assertion type is backed by evidence of a compatible type (some types, such as a
     verified launch date or a confirmed promotion, need evidence this data cannot provide)
  3. association assertions cite a test with BH q < 0.05
  4. claim level is compatible with its assertions
  5. every number in the text matches a computed value in the cited evidence. The one exception
     is a specification figure from a cited product document (e.g. "up to 20 hours"): it passes only
     in a positioning_claim citing that document, with the same unit, attributed to the document's
     own product, and framed as a manufacturer claim rather than verified performance.
     Percentages, statistics and sales metrics can only come from computed evidence.
  6. quoted text appears in a cited document
  7. product IDs and model names exist
  8. an auditor (LLM in live/replay mode, heuristic otherwise) extracts what the text implies;
     implied assertions must pass rule 2 as well. Qualified statements ("first observed sale,
     not a verified launch date") pass; unqualified strong statements do not.
Failing claims are not deleted: they are moved to a flagged section with reasons.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

REQUIRES: dict[str, set[str] | None] = {
    "signal_level": {"signal_trend", "signal_by_segment"},
    "signal_change": {"signal_trend"},
    "first_observed_sale": {"first_observed_sale"},
    "fos_reliability": {"first_observed_sale"},
    "positioning_claim": {"product_doc", "product_doc_search"},
    "cohort_definition": {"cohort_definition"},
    "sales_comparison": {"launch_trajectory"},
    "sales_association": {"launch_trajectory"},
    "price_volume_pattern": {"price_volume_pattern"},
    "complaint_comparison": {"complaint_comparison"},
    "complaint_association": {"complaint_comparison"},
    "confidence_grade": {"confidence_assessment"},
    # evidence types that do not exist in this system -> these assertions can never pass
    "launch_date_verified": {"launch_record"},
    "promotion_confirmed": {"promotion_record"},
    "causal_effect": {"causal_design"},
    "problem_resolved": {"resolution_study"},
    "demand_or_preference": {"preference_study"},
    "availability_or_distribution": {"distribution_record"},
    # interpretive / meta types: need at least one citation, any type
    "alternative_explanation": set(),
    "opportunity_hypothesis": set(),
    "evidence_gap": None,
    "method_note": None,
}
ASSOCIATION_TYPES = {"sales_association", "complaint_association"}
LEVEL_ALLOWS = {
    "observation": {"signal_level", "signal_change", "first_observed_sale", "fos_reliability",
                    "positioning_claim", "cohort_definition", "sales_comparison", "price_volume_pattern",
                    "complaint_comparison", "confidence_grade", "evidence_gap", "method_note"},
    "association": None,     # anything, but must include an association assertion
    "explanation": None,
    "hypothesis": None,
    "method_note": {"method_note", "first_observed_sale", "fos_reliability", "price_volume_pattern",
                    "evidence_gap"},
    "evidence_gap": {"evidence_gap", "method_note", "confidence_grade", "signal_level", "fos_reliability"},
}
LEVEL_NEEDS = {"association": ASSOCIATION_TYPES, "explanation": {"alternative_explanation"},
               "hypothesis": {"opportunity_hypothesis"}}

HEDGES = ("consistent with", "may ", "might", "could", "possible", "possibly", "not establish", "cannot",
          "does not", "do not", "not confirmed", "unconfirmed", "no promotion record", "not a verified",
          "not verified", "first observed", "estimate", "proxy", "hypothes", "if ", "whether", "not proof",
          "not evidence", "no evidence", "would need", "requires", "unknown", "not measured", "not available",
          "no distribution", "no data")
STRONG_PATTERNS = {
    "launch_date_verified": re.compile(r"\blaunch(ed|es)?\s+(in|on|date|during)\b|\blaunch date\b", re.I),
    "promotion_confirmed": re.compile(r"\bpromot(ion|ions|ional|ed)\b|\bon sale\b|\bdiscount(ed)?\b", re.I),
    "causal_effect": re.compile(r"\b(caused|causes|drove|drives|driven by|led to|resulted in|because of|"
                                r"due to|thanks to|boosted|explains why)\b", re.I),
    "problem_resolved": re.compile(r"\b(solved|resolved|fixed|eliminated)\b", re.I),
    "demand_or_preference": re.compile(r"\b(consumers|buyers|customers|shoppers)\s+(prefer|preferred|chose|"
                                       r"choose|want|wanted|demand|demanded|value|valued)\b", re.I),
    "availability_or_distribution": re.compile(r"\b(distribution|availability|stocked|shelf space)\b", re.I),
}


def heuristic_audit(text: str) -> list[str]:
    """Sentence-level: a strong pattern counts only if the sentence carries no hedge/qualifier."""
    implied = []
    for sent in re.split(r"(?<=[.;!?])\s+", text):
        low = sent.lower()
        hedged = any(h in low for h in HEDGES)
        for t, pat in STRONG_PATTERNS.items():
            if pat.search(sent) and not hedged and t not in implied:
                implied.append(t)
    return implied


NUM_RE = re.compile(r"(?<![\w.\-])([+-]?\d+(?:\.\d+)?)(%?)(?![\w-])")
PID_RE = re.compile(r"\bP\d{4}\b")
EID_RE = re.compile(r"\bE\d{3}\b")
PERIOD_RE = re.compile(r"\b\d{4}-M\d{2}\b|\b\d{4}-H[12]\b")


QUOTE_RE = re.compile(r"[\"\u201c]([^\"\u201d]{8,})[\"\u201d]")
CONF_LEVEL_RE = re.compile(r"\b(90|95|99)\s?%\s?(CI|confidence)", re.I)


def _numbers_in(text: str) -> list[tuple[str, float, bool, int]]:
    """Numbers asserted by the claim's own words. Quoted document text is excluded (verified by
    the quote check) and so are confidence levels such as '95% CI'."""
    text = CONF_LEVEL_RE.sub(" ", QUOTE_RE.sub(" ", text))
    clean = PERIOD_RE.sub(" ", EID_RE.sub(" ", PID_RE.sub(" ", text)))
    clean = re.sub(r"\bG\d+\b", " ", clean)                          # model generation suffixes
    out = []
    for m in NUM_RE.finditer(clean):
        tok, pct = m.group(1), m.group(2) == "%"
        val = float(tok)
        if not pct and val.is_integer() and 1990 <= val <= 2100:
            continue                                                  # a year
        dec = len(tok.split(".")[1]) if "." in tok else 0
        out.append((tok + m.group(2), val, pct, dec))
    return out


def _collect_numbers(obj, acc: list[float]) -> None:
    if isinstance(obj, bool) or obj is None:
        return
    if isinstance(obj, (int, float)):
        if not (isinstance(obj, float) and math.isnan(obj)):
            acc.append(float(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            _collect_numbers(v, acc)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _collect_numbers(v, acc)
    elif isinstance(obj, str):
        for m in re.finditer(r"\d+(?:\.\d+)?", obj):
            acc.append(float(m.group(0)))


def _number_supported(val: float, pct: bool, dec: int, candidates: list[float]) -> bool:
    tol = 0.5 * 10 ** (-dec) + 1e-9
    for c in candidates:
        for scaled in ((c * 100,) if pct else (c, c * 100)):
            if abs(abs(val) - abs(scaled)) <= tol:
                return True
    return False



# --- specification figures quoted from cited product documents -------------------------------
SPEC_NUM_RE = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s?-?\s?(hours?|hrs?|hr|wh|mah|kg|gb|tb|nits|hz|inch(?:es)?|"
                         r"mm|w)\b", re.I)
_UNIT = {"hour": "hour", "hours": "hour", "hr": "hour", "hrs": "hour", "inches": "inch"}
MANUFACTURER_CUES = ("up to", "claim", "advertis", "rated", "manufacturer", "document", "stated", "states",
                     "according to", "marketed", "promis", "spec", "announce", "headline", "position",
                     "quoted", "listed")
VERIFIED_CUES = ("measured", "tested", "real-world", "real world", "verified", "independently", "in practice",
                 "actual battery", "observed battery", "confirmed", "proven")


def _unit(u: str) -> str:
    u = u.lower()
    return _UNIT.get(u, u)


def _doc_sources(claim, evs) -> list[tuple[str, str]]:
    """(product_id, text) of documents cited by the claim's positioning_claim assertions."""
    out = []
    for a in claim.assertions:
        if a.type != "positioning_claim":
            continue
        for i in a.evidence_ids:
            e = evs.get(i)
            if e is None:
                continue
            if e.evidence_type == "product_doc" and e.detail.get("text"):
                out.append((e.values.get("product_id"), e.detail["text"]))
            for h in e.detail.get("hits", []) if e.evidence_type == "product_doc_search" else []:
                out.append((h.get("product_id"), h.get("snippet", "")))
    return out


def _product_refs(text: str, products) -> list[tuple[int, str]]:
    """(position, product_id) of every product ID or exact model name in the text."""
    refs = [(m.start(), m.group(0)) for m in PID_RE.finditer(text)]
    for pid, model in zip(products["product_id"], products["model"]):
        for m in re.finditer(re.escape(model), text):
            refs.append((m.start(), pid))
    return sorted(refs)


def spec_figure_checks(claim, evs, products) -> dict[float, list[str]]:
    """For each specification figure in the claim that appears (same value, same unit) in a cited
    document: {value: problems}. An empty list means the figure is supported as a manufacturer claim."""
    sources = _doc_sources(claim, evs)
    if not sources:
        return {}
    doc_figs = [(pid, float(m.group(1)), _unit(m.group(2))) for pid, txt in sources
                for m in SPEC_NUM_RE.finditer(txt)]
    refs = _product_refs(claim.text, products)
    out: dict[float, list[str]] = {}
    for m in SPEC_NUM_RE.finditer(claim.text):
        val, unit = float(m.group(1)), _unit(m.group(2))
        owners = sorted({pid for pid, v, u in doc_figs if v == val and u == unit})
        if not owners:
            continue                                   # not a document figure: the strict check decides
        probs = out.setdefault(val, [])
        before = [pid for pos, pid in refs if pos < m.start()]
        subject = before[-1] if before else (refs[0][1] if len({p for _, p in refs}) == 1 else None)
        fig = f"{m.group(1)} {m.group(2)}"
        if subject is None:
            probs.append(f"'{fig}' is a document figure but the claim does not say which product it belongs to")
        elif subject not in owners:
            probs.append(f"'{fig}' appears in a document for {', '.join(owners)}, not for {subject}, "
                         "to which the claim attributes it")
        sent = next((x for x in re.split(r"(?<=[.;!?])\s+", claim.text) if m.group(0) in x), claim.text).lower()
        if any(c in sent for c in VERIFIED_CUES):
            probs.append(f"'{fig}' is a manufacturer-claimed specification presented as verified performance")
        elif not any(c in sent for c in MANUFACTURER_CUES):
            probs.append(f"'{fig}' must be attributed as a manufacturer claim (e.g. 'up to', 'advertised', "
                         "'claimed'), not stated as product performance")
    return out


@dataclass
class ClaimCheck:
    claim_id: str
    status: str = "verified"           # verified | flagged
    problems: list[str] = field(default_factory=list)
    implied: list[str] = field(default_factory=list)


def check_claim(claim, ledger, products, implied: list[str]) -> ClaimCheck:
    chk = ClaimCheck(claim.claim_id, implied=list(implied))
    cited = {eid for a in claim.assertions for eid in a.evidence_ids}
    evs = {}
    for eid in cited:
        e = ledger.get(eid)
        if e is None:
            chk.problems.append(f"cites unknown evidence {eid}")
        else:
            evs[eid] = e
    types_cited = {e.evidence_type for e in evs.values()}

    def check_type(t: str, ids: list[str], origin: str):
        req = REQUIRES[t]
        if req is None:
            return
        have = {evs[i].evidence_type for i in ids if i in evs} if ids else types_cited
        if not ids and origin == "declared" and req != set():
            chk.problems.append(f"{t}: no evidence cited")
            return
        if req == set():
            if not (ids or cited):
                chk.problems.append(f"{t}: interpretation must cite at least one evidence ID")
            return
        if not (have & req):
            needed = "/".join(sorted(req))
            exists = any(ledger.by_type(r) for r in req)
            msg = f"{t} ({origin}) requires {needed} evidence"
            chk.problems.append(msg + ("" if exists else "; no such evidence exists in this run"))

    for a in claim.assertions:
        check_type(a.type, a.evidence_ids, "declared")
        if a.type in ASSOCIATION_TYPES:
            tests = [evs[i] for i in a.evidence_ids if i in evs and evs[i].p_value is not None]
            if not any(e.q_value is not None and e.q_value < 0.05 for e in tests):
                chk.problems.append(f"{a.type}: cited tests are not significant after BH adjustment (q >= 0.05)")
            for status in ("exploratory", "sensitivity"):
                if any(e.hypothesis_status == status for e in tests) and status not in claim.text.lower():
                    chk.problems.append(f"{a.type}: relies on a {status} test but the text does not say so")
        if a.type == "confidence_grade":
            for i in a.evidence_ids:
                g = evs.get(i)
                if g is not None and g.evidence_type == "confidence_assessment":
                    grade = str(g.values.get("grade", ""))
                    if grade and grade.lower() not in claim.text.lower():
                        chk.problems.append(f"confidence grade in text does not match rubric grade '{grade}'")
    for t in implied:
        if t not in {a.type for a in claim.assertions}:
            check_type(t, [], "implied by text")

    declared = {a.type for a in claim.assertions}
    allow = LEVEL_ALLOWS.get(claim.level)
    if allow is not None and not declared <= allow:
        chk.problems.append(f"level '{claim.level}' cannot carry {sorted(declared - allow)}")
    need = LEVEL_NEEDS.get(claim.level)
    if need and not (declared & need):
        chk.problems.append(f"level '{claim.level}' needs one of {sorted(need)}")

    # numbers
    cands: list[float] = []
    for e in evs.values():
        _collect_numbers(e.values, cands)
        _collect_numbers(e.params, cands)
        _collect_numbers([e.p_value, e.q_value, e.q_pooled], cands)
    spec = spec_figure_checks(claim, evs, products)
    text_for_numbers = claim.text
    for m in sorted(products["model"], key=len, reverse=True):     # digits in model names are not claims
        text_for_numbers = text_for_numbers.replace(m, " ")
    for tok, val, pct, dec in _numbers_in(text_for_numbers):
        if _number_supported(val, pct, dec, cands):
            continue                                                 # computed evidence: strict, unchanged
        if not pct and val in spec:
            chk.problems.extend(p for p in spec[val] if p not in chk.problems)
            continue
        chk.problems.append(f"number '{tok}' not found in cited evidence")

    # quotes
    docs_text = " ".join(str(e.detail.get("text", "")) + " " +
                         " ".join(h.get("snippet", "") for h in e.detail.get("hits", []))
                         for e in evs.values())
    for q in re.findall(r"[\"“]([^\"”]{8,})[\"”]", claim.text):
        if q.strip().lower() not in docs_text.lower():
            chk.problems.append(f"quoted text not found in cited documents: \"{q[:60]}\"")

    # product references
    known_ids = set(products["product_id"])
    for pid in PID_RE.findall(claim.text):
        if pid not in known_ids:
            chk.problems.append(f"unknown product ID {pid}")
    text_wo_models = claim.text
    for m in sorted(products["model"], key=len, reverse=True):
        text_wo_models = text_wo_models.replace(m, " ")
    for oem in set(products["oem"]):
        if re.search(rf"\b{re.escape(oem)}\b", text_wo_models):
            chk.problems.append(f"mentions '{oem}' outside a verified model name")

    if chk.problems:
        chk.status = "flagged"
    return chk


def validate_claims(draft, ledger, products, auditor=None) -> list[ClaimCheck]:
    """auditor(claim) -> list of implied assertion types (LLM). Heuristic audit always runs too."""
    out = []
    for c in draft.claims:
        implied = heuristic_audit(c.text)
        if auditor is not None and c.level in ("association", "explanation", "hypothesis"):
            for t in auditor(c):
                if t not in implied:
                    implied.append(t)
        out.append(check_claim(c, ledger, products, implied))
    return out
