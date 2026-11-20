"""Command line: `mei run` (investigate) and `mei check` (re-execute a run's ledger)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel

STYLE = {"tool": "cyan", "decision": "green", "reasoning": "white", "guard": "bold yellow",
         "route": "magenta", "assess": "bold blue"}
console = Console()


def _show(ev: dict) -> None:
    style = STYLE.get(ev["kind"], "white")
    console.print(f"[dim]{ev['step']:>3}[/dim] [bold]{ev['node']:<14}[/bold] [{style}]{ev['kind']:<9}[/{style}] "
                  f"{ev['text']}", highlight=False, soft_wrap=True)


def cmd_run(a) -> int:
    from .run import run_investigation
    console.print(Panel(f"[bold]Market Evidence Investigator[/bold]\nmode: {a.mode} · data: {a.data} · theme: {a.theme}",
                        expand=False))
    res = run_investigation(a.data, a.out, mode=a.mode, theme=a.theme, cache_path=a.cache,
                            on_event=None if a.quiet else _show, max_tool_calls=a.max_tool_calls)
    checks = res["state"].get("checks", [])
    flagged = sum(c["status"] == "flagged" for c in checks)
    u = res["meta"].get("usage") or {}
    console.print(Panel(
        f"path: [bold]{res['state'].get('path')}[/bold]\nclaims verified: {len(checks) - flagged} · flagged: {flagged}\n"
        f"evidence entries: {len(res['ledger'].entries)} · tests: {len(res['ledger'].tests())}\n"
        f"LLM calls: {u.get('calls', 0)} · tokens in/out: {u.get('input_tokens', 0)}/{u.get('output_tokens', 0)}\n"
        f"report: {res['paths']['report_html']}", title="Run complete", expand=False))
    return 0


def cmd_check(a) -> int:
    from .adapters.synthetic import CsvMarketSource
    from .ledger import EvidenceLedger, replay_check
    from .tools import REGISTRY
    led = EvidenceLedger.load(Path(a.run) / "ledger.json")
    md = CsvMarketSource(a.data).load()
    problems = replay_check(led, md, REGISTRY)
    n = sum(1 for e in led.entries if e.tool in REGISTRY)
    if problems:
        console.print(f"[red]{len(problems)} mismatches[/red]")
        for p in problems:
            console.print(" -", p)
        return 1
    console.print(f"[green]All {n} tool results re-executed from recorded inputs and matched.[/green]")
    return 0


def cmd_smoke(a) -> int:
    from .smoke import run_smoke
    console.print(Panel("[bold]API smoke test[/bold] (small, capped by MEI_SMOKE_MAX_COST_USD, default $0.50)",
                        expand=False))
    res = run_smoke(a.data, a.out, skip_graph=a.skip_graph,
                    report=lambda line: console.print(("[green]" if line.startswith("PASS") else "[red]") + line,
                                                      highlight=False, soft_wrap=True))
    u = res.get("usage") or {}
    console.print(Panel(f"passed {res['passed']} · failed {res['failed']} · LLM calls {u.get('calls', 0)} · "
                        f"tokens in/out {u.get('input_tokens', 0)}/{u.get('output_tokens', 0)} · "
                        f"cost ${u.get('cost_usd', 0):.4f}\nreport: {a.out}/smoke_report.json",
                        title="Smoke test " + ("PASSED" if res["failed"] == 0 else "FAILED"), expand=False))
    return 0 if res["failed"] == 0 else 1


def cmd_estimate(a) -> int:
    from .config import load_env
    from .estimate import estimate_full_run
    env = load_env()
    est = estimate_full_run(a.data, env["model_main"], env["model_small"])
    console.print(f"Reference run: {est['assumptions']['agent_tool_calls_in_reference_run']} agent tool calls; "
                  f"prices (USD/MTok): {est['assumptions']['prices_usd_per_mtok']}")
    for k, v in est["estimate"].items():
        console.print(f"  {k:<8} ~{v['llm_calls']} calls · main {v['main_input_tokens']:,} in / "
                      f"{v['main_output_tokens']:,} out · small {v['small_input_tokens']:,} / "
                      f"{v['small_output_tokens']:,} · [bold]${v['cost_usd']:.2f}[/bold]")
    console.print(f"Spending cap (MEI_MAX_COST_USD): ${env['max_cost_usd']:.2f}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="mei")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run an investigation")
    r.add_argument("--data", required=True, help="data directory (contract tables)")
    r.add_argument("--out", required=True, help="output directory for the run")
    r.add_argument("--mode", choices=["scripted", "live", "replay"], default="scripted")
    r.add_argument("--theme", default="battery")
    r.add_argument("--cache", default=None, help="LLM cache file (live writes, replay reads)")
    r.add_argument("--max-tool-calls", type=int, default=24)
    r.add_argument("--quiet", action="store_true")
    r.set_defaults(fn=cmd_run)
    c = sub.add_parser("check", help="re-execute every ledger entry of a run and compare")
    c.add_argument("--run", required=True)
    c.add_argument("--data", required=True)
    c.set_defaults(fn=cmd_check)
    sm = sub.add_parser("smoke", help="small API smoke test before a live run")
    sm.add_argument("--data", default="examples/data/battery_s42")
    sm.add_argument("--out", default="runs/smoke")
    sm.add_argument("--skip-graph", action="store_true")
    sm.set_defaults(fn=cmd_smoke)
    es = sub.add_parser("estimate", help="estimate the cost of a full live run (no API calls)")
    es.add_argument("--data", default="examples/data/battery_s42")
    es.set_defaults(fn=cmd_estimate)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
