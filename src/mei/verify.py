"""Verify that a recorded live run replays exactly: `mei verify-replay --run runs/demo_live`.

The recording (llm_cache.jsonl) is replayed with no API key and no cost, using the settings stored in the run's run_meta.json. Every output is compared with the recorded
one, and the recorded ledger is re-executed from its inputs. On the recording machine outputs are
byte-identical; on another OS/CPU, floats may differ in their last digits and chart images in pixels,
which is reported explicitly and accepted only within the ledger check's tolerance (relative 1e-9).
"""
from __future__ import annotations

import difflib
import json
import math
import re
import tempfile
from pathlib import Path

from .config import REPO_ROOT

COMPARED = ("state.json", "ledger.json", "checks.json", "trace.jsonl", "report.md", "report.html")
MODE_LINES = ("Run mode:", "- Mode:", "live agent run (Anthropic API)", "replay of a recorded agent run")


def _resolve_data(run_dir: Path, data_dir: str | None) -> Path:
    if data_dir:
        return Path(data_dir)
    rec = json.loads((run_dir / "run_meta.json").read_text())["data_dir"]
    for cand in (Path(rec), REPO_ROOT / rec):
        if cand.exists():
            return cand
    raise FileNotFoundError(f"data directory '{rec}' from run_meta.json not found; pass --data")


def _normalise(name: str, text: str) -> str:
    if name == "report.md":           # only the run-mode label differs between a recording and its replay
        return "\n".join(l for l in text.splitlines() if not any(m in l for m in MODE_LINES))
    if name == "report.html":
        for label in ("live agent run (Anthropic API)", "replay of a recorded agent run (no API calls)"):
            text = text.replace(label, "<mode>")
        return text
    return text


# Same tolerance as the ledger re-execution check. Replaying on another OS/CPU can change the last
# binary digit of a float (different maths library), e.g. p = 0.0036856349233613003 vs ...613.
REL_TOL, ABS_TOL = 1e-9, 1e-12
PNG_RE = re.compile(r"data:image/png;base64,[A-Za-z0-9+/=]+")


def _json_diff(a, b, path="", out=None):
    """Differences beyond float rounding (list of paths) and the largest relative float difference."""
    out = out if out is not None else {"diffs": [], "n_float": 0, "max_rel": 0.0}
    if isinstance(a, float) or isinstance(b, float):
        if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
            if a != b:
                if math.isclose(a, b, rel_tol=REL_TOL, abs_tol=ABS_TOL):
                    out["n_float"] += 1
                    out["max_rel"] = max(out["max_rel"], abs(a - b) / max(abs(a), abs(b)))
                else:
                    out["diffs"].append(f"{path}: {a!r} vs {b!r}")
        elif a != b:
            out["diffs"].append(f"{path}: {a!r} vs {b!r}")
    elif isinstance(a, dict) and isinstance(b, dict):
        if a.keys() != b.keys():
            out["diffs"].append(f"{path}: keys differ {sorted(set(a) ^ set(b))}")
        for k in a.keys() & b.keys():
            _json_diff(a[k], b[k], f"{path}.{k}" if path else k, out)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out["diffs"].append(f"{path}: length {len(a)} vs {len(b)}")
        for i, (x, y) in enumerate(zip(a, b)):
            _json_diff(x, y, f"{path}[{i}]", out)
    elif a != b:
        out["diffs"].append(f"{path}: {a!r} vs {b!r}")
    return out


def compare_output(name: str, recorded: str, replayed: str) -> tuple[bool, str]:
    a, b = _normalise(name, recorded), _normalise(name, replayed)
    if a == b:
        return True, "identical"
    if name.endswith((".json", ".jsonl")):
        if name.endswith(".jsonl"):
            ja = [json.loads(l) for l in a.splitlines() if l.strip()]
            jb = [json.loads(l) for l in b.splitlines() if l.strip()]
        else:
            ja, jb = json.loads(a), json.loads(b)
        d = _json_diff(ja, jb)
        if not d["diffs"]:
            return True, (f"identical except floating-point rounding: {d['n_float']} numbers differ in the last "
                          f"digits (largest relative difference {d['max_rel']:.1e}; tolerance {REL_TOL:g})")
        return False, "\n".join(d["diffs"][:12])
    if name == "report.html" and PNG_RE.sub("<chart>", a) == PNG_RE.sub("<chart>", b):
        n = len(PNG_RE.findall(a))
        return True, (f"text and tables identical; the {n} chart images were re-drawn with pixel differences "
                      "(chart rendering differs by OS; the charted values are compared in ledger.json)")
    diff = list(difflib.unified_diff(a.splitlines(), b.splitlines(), "recorded", "replayed", lineterm="", n=0))
    return False, "\n".join(l[:300] for l in diff[:12])


def verify_replay(run_dir: str | Path, data_dir: str | None = None) -> dict:
    from .adapters.synthetic import CsvMarketSource
    from .ledger import EvidenceLedger, replay_check
    from .run import run_investigation
    from .tools import REGISTRY

    run_dir = Path(run_dir)
    data = _resolve_data(run_dir, data_dir)
    items = []
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "replay"
        try:
            run_investigation(data, out, mode="replay", cache_path=run_dir / "llm_cache.jsonl")
        except Exception as e:                                    # noqa: BLE001 - reported, not raised
            return {"ok": False, "items": [("replay", False, f"{type(e).__name__}: {e}")]}
        for name in COMPARED:
            ok, detail = compare_output(name, (run_dir / name).read_text(), (out / name).read_text())
            items.append((name, ok, detail))
        rec_meta = json.loads((run_dir / "run_meta.json").read_text())
        rep_meta = json.loads((out / "run_meta.json").read_text())
        same_usage = rec_meta.get("usage") == rep_meta.get("usage")
        items.append(("LLM calls and tokens", same_usage,
                      f"{(rep_meta.get('usage') or {}).get('calls')} calls" if same_usage else
                      f"recorded {rec_meta.get('usage')} vs replayed {rep_meta.get('usage')}"))
    led = EvidenceLedger.load(run_dir / "ledger.json")
    problems = replay_check(led, CsvMarketSource(data).load(), REGISTRY)
    n = sum(1 for e in led.entries if e.tool in REGISTRY)
    items.append(("ledger re-execution", not problems,
                  f"all {n} tool results matched" if not problems else "; ".join(problems[:5])))
    return {"ok": all(ok for _, ok, _ in items), "items": items}
