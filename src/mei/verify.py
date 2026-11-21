"""Verify that a recorded live run replays exactly: `mei verify-replay --run runs/demo_live`.

The recording (llm_cache.jsonl) is replayed with no API key and no cost, using the settings stored in the run's run_meta.json. Every output is compared with the recorded
one, and the recorded ledger is re-executed from its inputs.
"""
from __future__ import annotations

import difflib
import json
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
            a = _normalise(name, (run_dir / name).read_text())
            b = _normalise(name, (out / name).read_text())
            if a == b:
                items.append((name, True, "identical"))
            else:
                diff = list(difflib.unified_diff(a.splitlines(), b.splitlines(), "recorded", "replayed",
                                                 lineterm="", n=0))[:12]
                items.append((name, False, "\n".join(diff)))
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
