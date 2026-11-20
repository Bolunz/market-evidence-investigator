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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="mei")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run an investigation")
    r.add_argument("--data", required=True, help="data directory (contract tables)")
    r.add_argument("--out", required=True, help="output directory for the run")
    r.add_argument("--mode", choices=["scripted", "live", "replay"], default="scripted")
    r.add_argument("--theme", default="battery")
    r.add_argument("--cache", default=None, help="LLM cache file (live writes, replay reads)")
    r.add_argument("--max-tool-calls", type=int, default=16)
    r.add_argument("--quiet", action="store_true")
    r.set_defaults(fn=cmd_run)
    c = sub.add_parser("check", help="re-execute every ledger entry of a run and compare")
    c.add_argument("--run", required=True)
    c.add_argument("--data", required=True)
    c.set_defaults(fn=cmd_check)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
