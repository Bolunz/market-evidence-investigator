"""LLM access with two modes.

live    Calls Anthropic via langchain-anthropic. Needs ANTHROPIC_API_KEY in the environment
        (loaded from a git-ignored .env). Every response is appended to a JSONL cache.
replay  Reads responses from that cache; no network, no key, no cost. Because all tools
        are deterministic, a replayed run reproduces the same conversation, so each
        request maps to the same cache key.

API notes for Claude 5.5 models (verified against platform docs, 2026-11-20):
- temperature / top_p / top_k must be omitted (non-default values return 400).
- Sonnet 5.5 rejects forced tool use (tool_choice tool/any) with 400, so structured
  outputs use tool_choice=auto plus an explicit instruction and one repair turn.
- Adaptive thinking is on by default; thinking blocks are kept unmodified in the message
  history (required for multi-turn tool use). Effort is set explicitly to control cost.

Guards: a call-count cap and a USD spending cap. A call is refused if its worst case
(estimated input + max_tokens of output) could take spend past the cap.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import dataclass, field
from pathlib import Path

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage, messages_from_dict, \
    messages_to_dict
from pydantic import BaseModel, ValidationError

from ..config import price_for


class ReplayMissError(RuntimeError):
    pass


class BudgetExceeded(RuntimeError):
    pass


class LLMRequestError(RuntimeError):
    """A request the API rejected; message explains the likely cause."""


@dataclass
class Usage:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    by_role: dict = field(default_factory=dict)

    def add(self, role: str, inp: int, out: int, cost: float) -> None:
        self.calls += 1
        self.input_tokens += inp
        self.output_tokens += out
        self.cost_usd += cost
        r = self.by_role.setdefault(role, {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0})
        r["calls"] += 1
        r["input_tokens"] += inp
        r["output_tokens"] += out
        r["cost_usd"] += cost


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


def _cost(model: str, inp: int, out: int) -> float:
    pin, pout = price_for(model)
    if math.isnan(pin):
        return 0.0
    return inp / 1e6 * pin + out / 1e6 * pout


class LLMClient:
    MAX_TOKENS = {"main": 16000, "small": 4000}

    def __init__(self, mode: str, cache_path: Path, model_main: str | None = None,
                 model_small: str | None = None, max_calls: int | None = None,
                 max_cost_usd: float | None = None, chat_factory=None):
        assert mode in ("live", "replay")
        self.mode = mode
        self.cache_path = Path(cache_path)
        self.model_main = model_main or os.getenv("MEI_MODEL_MAIN", "claude-sonnet-5-5")
        self.model_small = model_small or os.getenv("MEI_MODEL_SMALL", "claude-haiku-5-5")
        self.max_calls = max_calls or int(os.getenv("MEI_MAX_LLM_CALLS", "60"))
        self.max_cost_usd = max_cost_usd if max_cost_usd is not None else float(os.getenv("MEI_MAX_COST_USD", "3.00"))
        self.effort = {"main": os.getenv("MEI_EFFORT_MAIN", "medium"), "small": os.getenv("MEI_EFFORT_SMALL", "low")}
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
            # no temperature/top_p/top_k: rejected by Claude 5.5 models
            self._models[name] = ChatAnthropic(model=name, max_tokens=self.MAX_TOKENS[which], max_retries=3,
                                               timeout=180, effort=self.effort[which])
        return name, self._models[name]

    def _check_budget(self, name: str, which: str, messages: list[BaseMessage], tools) -> None:
        if self.usage.calls >= self.max_calls:
            raise BudgetExceeded(f"LLM call cap reached ({self.max_calls} calls; MEI_MAX_LLM_CALLS)")
        chars = len(json.dumps(messages_to_dict(messages), default=str)) + len(json.dumps(
            [t if isinstance(t, dict) else t.model_json_schema() for t in (tools or [])], default=str))
        worst = _cost(name, int(chars / 3), self.MAX_TOKENS[which])
        if self.usage.cost_usd + worst > self.max_cost_usd:
            raise BudgetExceeded(f"spending cap ${self.max_cost_usd:.2f} (MEI_MAX_COST_USD) would be exceeded: "
                                 f"spent ${self.usage.cost_usd:.4f}, next call worst case ${worst:.4f}")

    def invoke(self, role: str, messages: list[BaseMessage], tools: list | None = None,
               which: str = "main") -> AIMessage:
        name = self.model_main if which == "main" else self.model_small
        tool_sig = [t if isinstance(t, dict) else t.model_json_schema() for t in (tools or [])]
        key = _key({"model": name, "role": role, "messages": _strip_volatile(messages_to_dict(messages)),
                    "tools": tool_sig, "effort": self.effort[which]})
        if key in self._cache:
            rec = self._cache[key]
            self.usage.add(role, rec.get("input_tokens", 0), rec.get("output_tokens", 0), rec.get("cost_usd", 0.0))
            return messages_from_dict([rec["response"]])[0]
        if self.mode == "replay":
            raise ReplayMissError(f"no cached response for role={role} (key {key[:12]}). The run diverged "
                                  "from the recording; re-record with --mode live.")
        self._check_budget(name, which, messages, tools)
        _, llm = self._model(which)
        if tools:
            llm = llm.bind_tools(tools)          # tool_choice=auto (forced choice is rejected by Sonnet 5.5)
        try:
            ai = llm.invoke(messages)
        except Exception as e:                   # noqa: BLE001 - map provider errors to actionable messages
            raise _explain(e, name) from e
        um = ai.usage_metadata or {}
        inp, out = int(um.get("input_tokens", 0)), int(um.get("output_tokens", 0))
        cost = _cost(name, inp, out)
        self.usage.add(role, inp, out, cost)
        rec = {"key": key, "role": role, "model": name, "input_tokens": inp, "output_tokens": out,
               "cost_usd": cost, "stop_reason": (ai.response_metadata or {}).get("stop_reason"),
               "response": messages_to_dict([ai])[0]}
        self._cache[key] = rec
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        with self.cache_path.open("a") as f:
            f.write(json.dumps(rec, default=str) + "\n")
        return ai

    def structured(self, role: str, messages: list[BaseMessage], schema: type[BaseModel],
                   which: str = "main") -> BaseModel:
        """Structured output through a tool the model is instructed to call (tool_choice=auto).
        One repair turn if the call is missing or fails validation."""
        name = schema.__name__
        msgs = list(messages) + [HumanMessage(f"Respond only by calling the {name} tool with your complete answer.")]
        ai = self.invoke(role, msgs, tools=[schema], which=which)
        call = next((tc for tc in ai.tool_calls if tc["name"] == name), None)
        try:
            if call is None:
                raise ValueError(f"no {name} tool call in the response")
            return schema.model_validate(call["args"])
        except (ValidationError, ValueError) as e:
            fix = msgs + [ai]
            for tc in ai.tool_calls:
                fix.append(ToolMessage(content=f"Error: {e}", tool_call_id=tc["id"]))
            fix.append(HumanMessage(f"That was not a valid {name} call ({str(e)[:300]}). Call the {name} tool "
                                    "again with corrected arguments."))
            ai2 = self.invoke(role + "_repair", fix, tools=[schema], which=which)
            call2 = next((tc for tc in ai2.tool_calls if tc["name"] == name), None)
            if call2 is None:
                raise LLMRequestError(f"{role}: model did not return a {name} tool call after one repair turn")
            return schema.model_validate(call2["args"])


def _explain(e: Exception, model: str) -> Exception:
    """Map provider errors to actionable messages. Uses the HTTP status code first, because
    wrappers rename the exception classes (e.g. langchain-anthropic raises
    AnthropicModelNotFoundError for Anthropic's NotFoundError)."""
    name = type(e).__name__
    msg = str(e)
    status = getattr(e, "status_code", None) or getattr(getattr(e, "response", None), "status_code", None)
    if status == 401 or "Authentication" in name:
        return LLMRequestError("Anthropic rejected the API key (401). Check ANTHROPIC_API_KEY in .env.")
    if status == 404 or "NotFound" in name:
        return LLMRequestError(f"Model '{model}' not found or not available to this key (404). "
                               "Set MEI_MODEL_MAIN / MEI_MODEL_SMALL in .env.")
    if status == 403 or "PermissionDenied" in name:
        return LLMRequestError(f"This key cannot use '{model}' (403).")
    if status in (429, 500, 502, 503, 504, 529) or any(k in name for k in (
            "RateLimit", "Overloaded", "InternalServer", "APIConnection", "Timeout")):
        return LLMRequestError(f"{name} ({status}) after 3 automatic retries: {msg[:300]}")
    if status == 400 or "BadRequest" in name or isinstance(e, ValueError):
        return LLMRequestError(f"Request rejected ({name}): {msg[:500]}")
    return e
