"""Evaluation harness: scores investigations against answer keys.

This is the ONLY code that reads answer keys. It is not part of the application package.

Usage
  python evaluation/run_eval.py --seeds 20                 # scripted runs over 20 positive + 20 null seeds
  python evaluation/run_eval.py --run runs/X --key evaluation/answer_keys/battery_s42.json --data data/synthetic/battery_s42
                                                           # score one existing run (live or replay)

What is scored (all from structured outputs, never from report wording):
  path / focus segment, positioning judgements, rubric grades per planted product,
  zero-effect false positives, claim verification, ledger re-execution.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mei.adapters.synthetic import CsvMarketSource  # noqa: E402
from mei.ledger import EvidenceLedger, replay_check  # noqa: E402
from mei.tools import REGISTRY  # noqa: E402

SUPPORTED = {"Moderate", "Weak"}


def score_run(run_dir: Path, key: dict, data_dir: Path) -> dict:
    state = json.loads((run_dir / "state.json").read_text())
    checks = json.loads((run_dir / "checks.json").read_text())
    ledger = EvidenceLedger.load(run_dir / "ledger.json")
    r, exp = key["roles"], key["expected"]
    pos = {f["product_id"]: f["positioning"] for f in (state.get("findings") or {}).get("findings", [])}
    grades = {e.values["product_id"]: e.values for e in ledger.by_type("confidence_assessment")
              if "product_id" in e.values}
    g = lambda role: grades.get(r[role], {}).get("grade")  # noqa: E731
    positive = key["variant"] == "positive"
    res = {
        "scenario": key["scenario_id"], "variant": key["variant"],
        "path_ok": state.get("path") == "direct_response",
        "focus_segment_ok": (state.get("plan") or {}).get("focus_segment") == exp["signal_rising_in_segment"],
        "A_found": pos.get(r["A"]) == "positioned_on_need",
        "B_found": pos.get(r["B"]) == "positioned_on_need",
        "G_not_in_segment_cohort": pos.get(r["G"]) in ("segment_mismatch", None),
        "A_grade": g("A"), "B_grade": g("B"), "C_grade": g("C"),
        "A_grade_ok": (g("A") == "Moderate") if positive else (g("A") not in SUPPORTED),
        "A_false_positive": (not positive) and g("A") in SUPPORTED,
        "B_not_supported_as_effect": grades.get(r["B"], {}).get("sales_status") not in ("supported",),
        "B_pattern_reported": bool(grades.get(r["B"], {}).get("price_volume_pattern")),
        "C_flagged_unreliable": grades.get(r["C"], {}).get("first_sale_reliability") == "unreliable"
                                 if r["C"] in grades else None,
        "claims_verified": sum(c["status"] == "verified" for c in checks),
        "claims_flagged": sum(c["status"] == "flagged" for c in checks),
        "ledger_reproducible": replay_check(ledger, CsvMarketSource(data_dir).load(), REGISTRY) == [],
    }
    return res


def sweep(n: int, out: Path) -> list[dict]:
    from mei.run import run_investigation
    from mei_synth.generate import generate
    rows = []
    for variant in ("positive", "null"):
        for seed in range(1000, 1000 + n):
            gen = generate(seed, variant, out / "data", out / "keys")
            key = json.loads((out / "keys" / f"{gen['scenario_id']}.json").read_text())
            run_dir = out / "runs" / f"{gen['scenario_id']}_{variant}"
            run_investigation(gen["data_dir"], run_dir, mode="scripted")
            rows.append(score_run(run_dir, key, Path(gen["data_dir"])))
    return rows


def scoreboard(rows: list[dict]) -> str:
    def rate(rows_, k):
        vals = [r[k] for r in rows_ if r[k] is not None]
        return f"{sum(bool(v) for v in vals)}/{len(vals)}"
    pos = [r for r in rows if r["variant"] == "positive"]
    nul = [r for r in rows if r["variant"] == "null"]
    lines = ["| Check | Positive variant | Zero-effect variant |", "|---|---|---|"]
    for label, k in [("Direct-response path taken", "path_ok"), ("Correct focus segment", "focus_segment_ok"),
                     ("Product A identified as positioned", "A_found"), ("Product B identified as positioned", "B_found"),
                     ("Other-segment product kept out of the cohort", "G_not_in_segment_cohort"),
                     ("A graded correctly (Moderate / not supported)", "A_grade_ok"),
                     ("B never graded as a supported sales effect", "B_not_supported_as_effect"),
                     ("B price-and-volume pattern reported", "B_pattern_reported"),
                     ("C first-sale artefact flagged unreliable", "C_flagged_unreliable"),
                     ("Ledger re-executes exactly", "ledger_reproducible")]:
        lines.append(f"| {label} | {rate(pos, k)} | {rate(nul, k)} |")
    fp = sum(r["A_false_positive"] for r in nul)
    lines.append(f"| A false positive (zero-effect) | - | {fp}/{len(nul)} |")
    lines.append(f"| Claims flagged by validator (total) | {sum(r['claims_flagged'] for r in pos)} | "
                 f"{sum(r['claims_flagged'] for r in nul)} |")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=0)
    ap.add_argument("--out", default="evaluation/work")
    ap.add_argument("--run")
    ap.add_argument("--key")
    ap.add_argument("--data")
    a = ap.parse_args(argv)
    if a.run:
        res = score_run(Path(a.run), json.loads(Path(a.key).read_text()), Path(a.data))
        print(json.dumps(res, indent=2))
        return 0
    rows = sweep(a.seeds or 20, Path(a.out))
    board = scoreboard(rows)
    res_dir = ROOT / "evaluation" / "results"
    res_dir.mkdir(exist_ok=True)
    (res_dir / "scripted_sweep.json").write_text(json.dumps(rows, indent=2))
    (res_dir / "scoreboard.md").write_text("# Scripted-policy evaluation (no LLM)\n\n" + board + "\n")
    print(board)
    return 0


if __name__ == "__main__":
    sys.exit(main())
