"""Programmatic entry point: run one investigation end to end."""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional


from .adapters.synthetic import CsvMarketSource
from .config import load_env
from .agents.graph import RunContext, build_graph
from .ledger import EvidenceLedger
from .report.render import write_outputs

DEFAULT_QUESTION = ("Consumers appear to be complaining more about battery life. Have we seen this before, "
                    "what did manufacturers do about it, what happened to those products afterwards, and what "
                    "can we reasonably learn from the evidence?")


def run_investigation(data_dir: str | Path, out_dir: str | Path, mode: str = "scripted", theme: str = "battery",
                      question: str = DEFAULT_QUESTION, cache_path: str | Path | None = None,
                      on_event: Optional[Callable[[dict], None]] = None, max_tool_calls: int = 24,
                      chat_factory=None) -> dict:
    env = load_env()                                    # local, git-ignored .env; key never printed
    out_dir = Path(out_dir)
    md = CsvMarketSource(data_dir).load()
    ledger = EvidenceLedger(md.file_hashes)
    llm = None
    if mode in ("live", "replay"):
        from .llm.client import LLMClient
        cache_path = Path(cache_path or out_dir / "llm_cache.jsonl")
        llm = LLMClient(mode, cache_path, chat_factory=chat_factory)
    ctx = RunContext(md=md, ledger=ledger, mode=mode, theme=theme, question=question, llm=llm,
                     on_event=on_event, max_tool_calls=max_tool_calls)
    app = build_graph(ctx)
    state = app.invoke({"question": question, "theme": theme, "revisions": 0},
                       config={"configurable": {"thread_id": out_dir.name}, "recursion_limit": 40})
    mode_label = {"scripted": "scripted run (no LLM; deterministic test policy, not the agent)",
                  "live": "live agent run (Anthropic API)",
                  "replay": "replay of a recorded agent run (no API calls)"}[mode]
    meta = {"mode": mode, "mode_label": mode_label, "data_label": f"{md.source_label}"
            f"{' (synthetic)' if md.synthetic else ''}", "synthetic": md.synthetic, "theme": theme,
            "question": question, "trace": ctx.trace,
            "models": {"main": llm.model_main, "small": llm.model_small} if llm else None,
            "usage": llm.usage.__dict__ if llm else None, "data_dir": str(data_dir),
            "limits": {"max_calls": llm.max_calls, "max_cost_usd": llm.max_cost_usd, "effort": llm.effort,
                       "max_tool_calls": max_tool_calls} if llm else None,
            "key_source": env["key_source"] if mode == "live" else None}
    paths = write_outputs(out_dir, dict(state), state.get("checks", []), ledger, meta)
    return {"state": state, "ledger": ledger, "trace": ctx.trace, "paths": paths, "md": md, "meta": meta}
