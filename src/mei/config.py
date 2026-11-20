"""Environment loading. Reports WHERE the API key came from without ever printing it."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import dotenv_values, find_dotenv, load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]

# USD per million tokens, list prices checked 2026-11-20 (platform.claude.com/docs/en/about-claude/pricing).
# Override in .env if prices change. Haiku 5.5 prices apply to prompts up to 100k tokens.
DEFAULT_PRICES = {
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-opus-5-5": (4.00, 20.00),
}


def load_env() -> dict:
    """Load .env (current directory first, then the repository root). Existing shell
    variables are NOT overridden, so the report says which source supplied the key."""
    in_shell = bool(os.environ.get("ANTHROPIC_API_KEY"))
    path = find_dotenv(usecwd=True) or (str(REPO_ROOT / ".env") if (REPO_ROOT / ".env").exists() else "")
    file_has_key = bool(path and dotenv_values(path).get("ANTHROPIC_API_KEY"))
    if path:
        load_dotenv(path, override=False)
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    source = "shell environment" if in_shell else (".env file" if file_has_key else "missing")
    return {
        "dotenv_path": path or None,
        "key_source": source,
        "key_present": bool(key),
        "key_masked": f"{key[:7]}...{key[-4:]} ({len(key)} chars)" if len(key) > 12 else ("set" if key else "missing"),
        "shell_overrides_file": in_shell and file_has_key,
        "model_main": os.getenv("MEI_MODEL_MAIN", "claude-sonnet-5-5"),
        "model_small": os.getenv("MEI_MODEL_SMALL", "claude-haiku-5-5"),
        "max_calls": int(os.getenv("MEI_MAX_LLM_CALLS", "60")),
        "max_cost_usd": float(os.getenv("MEI_MAX_COST_USD", "3.00")),
        "effort_main": os.getenv("MEI_EFFORT_MAIN", "medium"),
        "effort_small": os.getenv("MEI_EFFORT_SMALL", "low"),
    }


def price_for(model: str) -> tuple[float, float]:
    """(input, output) USD per million tokens; env overrides MEI_PRICE_<IN|OUT>_<MODEL>."""
    tag = model.upper().replace("-", "_")
    base = DEFAULT_PRICES.get(model, (float("nan"), float("nan")))
    return (float(os.getenv(f"MEI_PRICE_IN_{tag}", base[0])), float(os.getenv(f"MEI_PRICE_OUT_{tag}", base[1])))
