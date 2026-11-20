"""Evaluation harness: scores investigations against answer keys.

This is the ONLY code that reads answer keys. It is not part of the application package.

Usage
  python evaluation/run_eval.py --seeds 20                 # scripted runs, 20 seeds x 5 effect tiers
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
RANK = {"Insufficient": 0, "Not supported": 0, "Weak": 1, "Moderate": 2}
TIERS = ["strong", "moderate", "small", "null", "contradictory"]


def score_run(run_dir: Path, key: dict, data_dir: Path) -> dict:
    state = json.loads((run_dir / "state.json").read_text())
    checks = json.loads((run_dir / "checks.json").read_text())
    ledger = EvidenceLedger.load(run_dir / "ledger.json")
    r, exp = key["roles"], key["expected"]
    pos = {f["product_id"]: f["positioning"] for f in (state.get("findings") or {}).get("findings", [])}
    grades = {e.values["product_id"]: e.values for e in ledger.by_type("confidence_assessment")
              if "product_id" in e.values}
    a = grades.get(r["A"], {})
    ga = a.get("grade")
    ceiling = exp["A"]["max_justified_grade"]
    return {
        "scenario": key["scenario_id"], "variant": key["variant"],
        "path_ok": state.get("path") == "direct_response",
        "focus_segment_ok": (state.get("plan") or {}).get("focus_segment") == exp["signal_rising_in_segment"],
        "A_found": pos.get(r["A"]) == "positioned_on_need",
        "B_found": pos.get(r["B"]) == "positioned_on_need",
        "G_not_in_segment_cohort": pos.get(r["G"]) in ("segment_mismatch", None),
        "A_grade": ga, "A_grade_pooled": a.get("grade_pooled"), "A_ceiling": ceiling,
        # overclaim: grade above what the planted truth justifies (the key failure we care about)
        "A_overclaim": ga is not None and RANK.get(ga, 0) > RANK[ceiling],
        "A_sales_detected": a.get("sales_status") in ("supported", "supported_excluding_pattern_months"),
        "A_complaints_detected": a.get("complaint_status") == "lower_than_cohort",
        "A_contradiction_flagged": a.get("contradiction") == "sales advantage without lower complaints",
        "B_not_supported_as_effect": grades.get(r["B"], {}).get("sales_status") not in ("supported",),
        "B_pattern_reported": bool(grades.get(r["B"], {}).get("price_volume_pattern")),
        "C_flagged_unreliable": grades.get(r["C"], {}).get("first_sale_reliability") == "unreliable"
                                 if r["C"] in grades else None,
        "claims_verified": sum(c["status"] == "verified" for c in checks),
        "claims_flagged": sum(c["status"] == "flagged" for c in checks),
        "ledger_reproducible": replay_check(ledger, CsvMarketSource(data_dir).load(), REGISTRY) == [],
    }


def sweep(n: int, out: Path, tiers=TIERS) -> list[dict]:
    from mei.run import run_investigation
    from mei_synth.generate import generate
    rows = []
    for variant in tiers:
        for seed in range(1000, 1000 + n):
            gen = generate(seed, variant, out / variant / "data", out / variant / "keys")
            key = json.loads((out / variant / "keys" / f"{gen['scenario_id']}.json").read_text())
            run_dir = out / variant / "runs" / gen["scenario_id"]
            run_investigation(gen["data_dir"], run_dir, mode="scripted")
            rows.append(score_run(run_dir, key, Path(gen["data_dir"])))
    return rows


def scoreboard(rows: list[dict]) -> str:
    tiers = [t for t in TIERS if any(r["variant"] == t for r in rows)]
    by = {t: [r for r in rows if r["variant"] == t] for t in tiers}

    def rate(t, k):
        vals = [r[k] for r in by[t] if r[k] is not None]
        return f"{sum(bool(v) for v in vals)}/{len(vals)}"
    head = "| Check | " + " | ".join(tiers) + " |"
    lines = ["Planted effect on product A (sales multiplier / complaint multiplier): strong 4.0/0.35, "
             "moderate 2.0/0.60, small 1.4/0.80, null 1.0/1.0, contradictory 4.0/1.0.", "",
             "### Appropriateness (the primary measure)", "", head, "|---|" + "---|" * len(tiers)]
    lines.append("| **A overclaimed** (grade above what the truth justifies) | "
                 + " | ".join(rate(t, "A_overclaim") for t in tiers) + " |")
    lines.append("| A justified ceiling | " + " | ".join(by[t][0]["A_ceiling"] for t in tiers) + " |")
    dist = []
    for t in tiers:
        c = {}
        for r in by[t]:
            c[r["A_grade"]] = c.get(r["A_grade"], 0) + 1
        dist.append(", ".join(f"{k}: {v}" for k, v in sorted(c.items(), key=lambda kv: -RANK.get(kv[0], 0))))
    lines.append("| A grade distribution | " + " | ".join(dist) + " |")
    lines.append("| A sales advantage detected (power where true) | " + " | ".join(rate(t, "A_sales_detected") for t in tiers) + " |")
    lines.append("| A lower complaints detected (power where true) | " + " | ".join(rate(t, "A_complaints_detected") for t in tiers) + " |")
    lines.append("| Contradiction flagged (sales without fewer complaints) | " + " | ".join(rate(t, "A_contradiction_flagged") for t in tiers) + " |")
    lines.append("| A grade changes under pooled FDR (all tests one family) | " + " | ".join(
        f"{sum(r['A_grade'] != r['A_grade_pooled'] for r in by[t])}/{len(by[t])}" for t in tiers) + " |")
    lines += ["", "### Traps and integrity", "", head, "|---|" + "---|" * len(tiers)]
    for label, k in [("Direct-response path / correct segment", "focus_segment_ok"),
                     ("A and B identified as positioned", "B_found"),
                     ("Other-segment product kept out of cohort", "G_not_in_segment_cohort"),
                     ("B never graded as a supported sales effect", "B_not_supported_as_effect"),
                     ("B price-and-volume pattern reported", "B_pattern_reported"),
                     ("C first-sale artefact flagged unreliable", "C_flagged_unreliable"),
                     ("Ledger re-executes exactly", "ledger_reproducible")]:
        lines.append(f"| {label} | " + " | ".join(rate(t, k) for t in tiers) + " |")
    lines.append("| Claims flagged by validator | " + " | ".join(str(sum(r["claims_flagged"] for r in by[t])) for t in tiers) + " |")
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
    (res_dir / "scoreboard.md").write_text("# Scripted-policy evaluation (no LLM)\n\nScored from structured outputs "
                                           "against isolated answer keys.\n\n" + board + "\n")
    print(board)
    return 0


if __name__ == "__main__":
    sys.exit(main())
