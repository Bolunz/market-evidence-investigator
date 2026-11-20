"""Evidence ledger: every tool result gets an ID, its exact inputs, and its outputs.

Claims cite evidence IDs. The validator checks claims against these entries, and
`replay_check` re-executes each entry from its recorded inputs to prove reproducibility.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .analytics.stats import benjamini_hochberg


def _clean(v: Any) -> Any:
    if isinstance(v, float):
        return None if math.isnan(v) else v
    if isinstance(v, dict):
        return {k: _clean(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_clean(x) for x in v]
    if hasattr(v, "item"):              # numpy scalar
        return _clean(v.item())
    return v


@dataclass
class Evidence:
    evidence_id: str
    tool: str
    params: dict
    evidence_type: str
    values: dict
    summary: str
    detail: dict = field(default_factory=dict)
    p_value: float | None = None
    test_label: str | None = None
    q_value: float | None = None          # Benjamini-Hochberg across all tests in the run
    hypothesis_status: str | None = None  # "declared" | "exploratory" (tests only)
    requested_by: str = "code"            # "code" | "agent" | "critic"


class EvidenceLedger:
    def __init__(self, data_hashes: dict[str, str] | None = None):
        self.entries: list[Evidence] = []
        self.data_hashes = data_hashes or {}

    def record(self, tool: str, params: dict, result: dict, requested_by: str = "code",
               hypothesis_status: str | None = None) -> Evidence:
        test = result.get("test") or {}
        ev = Evidence(
            evidence_id=f"E{len(self.entries) + 1:03d}", tool=tool, params=_clean(params),
            evidence_type=result.get("evidence_type", tool), values=_clean(result.get("values", {})),
            summary=result.get("summary", ""), detail=_clean(result.get("detail", {})),
            p_value=_clean(test.get("p_value")), test_label=test.get("label"),
            hypothesis_status=hypothesis_status if test else None, requested_by=requested_by,
        )
        self.entries.append(ev)
        self.adjust()
        return ev

    def get(self, evidence_id: str) -> Evidence | None:
        return next((e for e in self.entries if e.evidence_id == evidence_id), None)

    def by_type(self, evidence_type: str) -> list[Evidence]:
        return [e for e in self.entries if e.evidence_type == evidence_type]

    def tests(self) -> list[Evidence]:
        return [e for e in self.entries if e.p_value is not None]

    def adjust(self) -> None:
        """Benjamini-Hochberg within each question family (one family per test tool: signal
        screening, sales-vs-cohort, complaints-vs-cohort). Every test run in a family counts,
        including agent-chosen and exploratory ones, so testing more products or segments raises
        the bar for all of them."""
        families: dict[str, list[Evidence]] = {}
        for e in self.tests():
            families.setdefault(e.tool, []).append(e)
        for tests in families.values():
            for e, q in zip(tests, benjamini_hochberg([e.p_value for e in tests])):
                e.q_value = _clean(q)

    def to_dict(self) -> dict:
        return {"data_hashes": self.data_hashes, "n_tests": len(self.tests()),
                "entries": [asdict(e) for e in self.entries]}

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_dict(), indent=2, default=str))

    @classmethod
    def load(cls, path: Path) -> "EvidenceLedger":
        d = json.loads(Path(path).read_text())
        led = cls(d.get("data_hashes"))
        led.entries = [Evidence(**e) for e in d["entries"]]
        return led


def _close(a: Any, b: Any) -> bool:
    if isinstance(a, float) or isinstance(b, float):
        if a is None or b is None:
            return a is b
        return math.isclose(float(a), float(b), rel_tol=1e-9, abs_tol=1e-12)
    return a == b


def replay_check(ledger: EvidenceLedger, md, registry) -> list[str]:
    """Re-execute every entry from its recorded params; return mismatches (empty = reproducible)."""
    problems = []
    if ledger.data_hashes and md.file_hashes and ledger.data_hashes != md.file_hashes:
        problems.append("data files differ from those recorded in the ledger")
    for e in ledger.entries:
        spec = registry.get(e.tool)
        if spec is None:
            continue                                   # non-tool entries (e.g. assessments)
        res = spec.fn(md, **e.params)
        vals = _clean(res.get("values", {}))
        for k, v in e.values.items():
            if not _close(v, vals.get(k)):
                problems.append(f"{e.evidence_id} {e.tool}.{k}: recorded {v!r} vs recomputed {vals.get(k)!r}")
    return problems
