"""LLM access with two modes.

live    Calls Anthropic via langchain-anthropic. Needs ANTHROPIC_API_KEY in the environment
        (loaded from a git-ignored .env). Every response is appended to a JSONL cache.
replay  Reads responses from that cache; no network, no key, no cost. Because all tools
        are deterministic, a replayed run reproduces the same conversation, so each
        request maps to the same cache key.

Credentials are never read from code or config files committed to the repo.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from langchain_core.messages import AIMessage, BaseMessage, messages_from_dict, messages_to_dict
from pydantic import BaseModel, ValidationError


class ReplayMissError(RuntimeError):
    pass


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class Usage:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    by_role: dict = field(default_factory=dict)

    def add(self, role: str, inp: int, out: int) -> None:
        self.calls += 1
        self.input_tokens += inp
        self.output_tokens += out
        r = self.by_role.setdefault(role, {"calls": 0, "input_tokens": 0, "output_tokens": 0})
        r["calls"] += 1
        r["input_tokens"] += inp
        r["output_tokens"] += out


def _key(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def _strip_volatile(d: list[dict]) -> list[dict]:
    """Remove fields that differ between otherwise identical calls (usage, ids, timing)."""
    out = []
    for m in d:
        m = json.loads(json.dumps(m, default=str))
        data = m.get("data", {})
        for k in ("id", "usage_metadata", "response_metadata"):
            data.pop(k, None)
        out.append(m)
    return out


class LLMClient:
    def __init__(self, mode: str, cache_path: Path, model_main: str | None = None,
                 model_small: str | None = None, max_calls: int | None = None, chat_factory=None):
        assert mode in ("live", "replay")
        self.mode = mode
        self.cache_path = Path(cache_path)
        self.model_main = model_main or os.getenv("MEI_MODEL_MAIN", "claude-sonnet-5-5")
        self.model_small = model_small or os.getenv("MEI_MODEL_SMALL", "claude-haiku-5-5")
        self.max_calls = max_calls or int(os.getenv("MEI_MAX_LLM_CALLS", "60"))
        self.usage = Usage()
        self._cache: dict[str, dict] = {}
        if self.cache_path.exists():
            for line in self.cache_path.read_text().splitlines():
                if line.strip():
                    rec = json.loads(line)
                    self._cache[rec["key"]] = rec
        self._models: dict[str, object] = {}
        self.chat_factory = chat_factory          # tests inject a fake chat model; never used in production
        if mode == "live" and chat_factory is None and not os.getenv("ANTHROPIC_API_KEY"):
            raise RuntimeError("ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key "
                               "(the file is git-ignored), or run with --mode replay.")

    def _model(self, which: str):
        name = self.model_main if which == "main" else self.model_small
        if name not in self._models and self.chat_factory is not None:
            self._models[name] = self.chat_factory(name)
        if name not in self._models:
            from langchain_anthropic import ChatAnthropic
            self._models[name] = ChatAnthropic(model=name, temperature=0, max_tokens=4096, max_retries=3,
                                               timeout=120)
        return name, self._models[name]

    def invoke(self, role: str, messages: list[BaseMessage], tools: list | None = None,
               tool_choice: str | None = None, which: str = "main") -> AIMessage:
        name = self.model_main if which == "main" else self.model_small
        tool_sig = [t if isinstance(t, dict) else t.model_json_schema() for t in (tools or [])]
        key = _key({"model": name, "role": role, "messages": _strip_volatile(messages_to_dict(messages)),
                    "tools": tool_sig, "tool_choice": tool_choice})
        if key in self._cache:
            rec = self._cache[key]
            ai = messages_from_dict([rec["response"]])[0]
            self.usage.add(role, rec.get("input_tokens", 0), rec.get("output_tokens", 0))
            return ai
        if self.mode == "replay":
            raise ReplayMissError(f"no cached response for role={role} (key {key[:12]}). The run diverged "
                                  "from the recording; re-record with --mode live.")
        if self.usage.calls >= self.max_calls:
            raise BudgetExceeded(f"LLM call budget of {self.max_calls} reached")
        _, llm = self._model(which)
        if tools:
            llm = llm.bind_tools(tools, tool_choice=tool_choice) if tool_choice else llm.bind_tools(tools)
        ai = llm.invoke(messages)
        um = ai.usage_metadata or {}
        inp, out = int(um.get("input_tokens", 0)), int(um.get("output_tokens", 0))
        self.usage.add(role, inp, out)
        rec = {"key": key, "role": role, "model": name, "input_tokens": inp, "output_tokens": out,
               "response": messages_to_dict([ai])[0]}
        self._cache[key] = rec
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        with self.cache_path.open("a") as f:
            f.write(json.dumps(rec, default=str) + "\n")
        return ai

    def structured(self, role: str, messages: list[BaseMessage], schema: type[BaseModel],
                   which: str = "main") -> BaseModel:
        """Structured output via a forced tool call; one repair attempt on validation error."""
        ai = self.invoke(role, messages, tools=[schema], tool_choice=schema.__name__, which=which)
        try:
            return schema.model_validate(ai.tool_calls[0]["args"])
        except (ValidationError, IndexError, KeyError) as e:
            from langchain_core.messages import HumanMessage, ToolMessage
            fix = list(messages) + [ai]
            if ai.tool_calls:
                fix.append(ToolMessage(content=f"Validation error: {e}", tool_call_id=ai.tool_calls[0]["id"]))
            fix.append(HumanMessage(f"Your {schema.__name__} output was invalid: {e}. Call {schema.__name__} "
                                    "again with corrected arguments."))
            ai2 = self.invoke(role + "_repair", fix, tools=[schema], tool_choice=schema.__name__, which=which)
            return schema.model_validate(ai2.tool_calls[0]["args"])
