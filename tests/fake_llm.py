"""Test double for ChatAnthropic: deterministic responses with tool calls and structured
outputs, so the LLM code path (ReAct loop, structured output, revision loop, cache, replay)
can be tested offline. Its writer deliberately includes one causal overclaim on the first
draft so the validation -> revision loop is exercised."""
from __future__ import annotations

import hashlib
import json

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

GOOD_TERMS = ("battery life", "hours of battery", "all-day battery", "battery that lasts")


def _id(*parts) -> str:
    return "toolu_" + hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()[:16]


def _human_json(messages):
    for m in messages:
        if isinstance(m, HumanMessage):
            try:
                return json.loads(m.content)
            except (TypeError, ValueError):
                continue
    return {}


def _tool_obs(messages):
    out = []
    for m in messages:
        if isinstance(m, ToolMessage) and not m.content.startswith("ERROR"):
            try:
                out.append(json.loads(m.content))
            except ValueError:
                pass
    return out


class NotFoundError(Exception):
    """Mimics anthropic.NotFoundError by class name (the client maps errors by name)."""


class _Models:
    def retrieve(self, model_id):
        class Info:
            id = model_id
        return Info()


class FakeModels:
    """Stands in for anthropic.Anthropic() in the smoke test (client.models.retrieve)."""
    models = _Models()


class FakeChat:
    max_retries = 3

    def __init__(self, name, tools=None, choice=None):
        self.name, self.tools, self.choice = name, tools, choice

    def bind_tools(self, tools, tool_choice=None):
        # mirrors production: tool_choice is never forced; a single schema tool means "structured output"
        assert tool_choice is None, "forced tool_choice is rejected by Sonnet 5.5 and must not be used"
        single = tools[0].__name__ if len(tools) == 1 and isinstance(tools[0], type) else None
        return FakeChat(self.name, tools, single)

    def _reply(self, name, args, n, text=""):
        return AIMessage(content=text, tool_calls=[{"name": name, "args": args, "id": _id(name, n)}],
                         usage_metadata={"input_tokens": 100, "output_tokens": 20, "total_tokens": 120})

    def invoke(self, messages):
        n = len(messages)
        if "nonexistent" in self.name:
            raise NotFoundError("model not found")
        ctx = _human_json(messages)
        texts = " ".join(m.content for m in messages if isinstance(m, HumanMessage) and isinstance(m.content, str))
        tool_names = [t["name"] if isinstance(t, dict) else t.__name__ for t in (self.tools or [])]
        if not self.tools and "single word: OK" in texts:
            return AIMessage(content="OK", usage_metadata={"input_tokens": 10, "output_tokens": 2, "total_tokens": 12})
        if self.choice == "SmokeAnswer":
            return self._reply("SmokeAnswer", {"count": 3, "note": "three"}, n)
        if tool_names == ["first_observed_sale"]:
            obs = _tool_obs(messages)
            if not obs:
                pid = texts.split("for product ")[1].split(",")[0]
                return self._reply("first_observed_sale", {"product_id": pid}, n)
            month = obs[-1]["values"]["first_observed_sale_month"]
            return AIMessage(content=f"First observed sale: {month}.",
                             usage_metadata={"input_tokens": 50, "output_tokens": 8, "total_tokens": 58})
        if self.choice == "InvestigationPlan":
            seg = ctx["candidate_segments"][0]
            return self._reply("InvestigationPlan", {
                "focus_segment": seg, "rationale": "largest increase", "search_terms": list(GOOD_TERMS),
                "hypotheses": [{"hypothesis_id": "H1", "statement": "positioned products gained share vs cohort",
                                "test_tool": "launch_trajectory", "alternative": "two-sided"},
                               {"hypothesis_id": "H2", "statement": "positioned products have fewer complaints",
                                "test_tool": "complaint_comparison", "alternative": "less"}]}, n)
        if self.choice == "Critique":
            pid = next(f["product_id"] for f in ctx["findings"]["findings"] if f["positioning"] == "positioned_on_need")
            return self._reply("Critique", {"alternative_explanations": [
                {"product_id": pid, "explanation": "buyer mix may differ", "would_distinguish": "owner reviews"}]}, n)
        if self.choice == "ImpliedAssertions":
            text = " ".join(m.content for m in messages if isinstance(m, HumanMessage) and isinstance(m.content, str))
            return self._reply("ImpliedAssertions", {"implied": ["causal_effect"] if "drove" in text else [],
                                                     "reason": "fake"}, n)
        if self.choice == "ReportDraft":
            ev = next(e for e in ctx["evidence"] if e["tool"] == "signal_trend"
                      and e["params"].get("segment") == ctx["plan"]["focus_segment"])
            claims = [{"claim_id": "C01", "section": "A_consumer_signal", "level": "observation",
                       "text": f"The recent complaint rate was {ev['values']['recent_rate'] * 100:.1f}%.",
                       "assertions": [{"type": "signal_change", "evidence_ids": [ev["evidence_id"]]}]}]
            if "previous_validation_failures" not in ctx:
                claims.append({"claim_id": "C02", "section": "E_evidence_assessment", "level": "explanation",
                               "text": "Endurance positioning drove the sales gains.",
                               "assertions": [{"type": "alternative_explanation",
                                               "evidence_ids": [ev["evidence_id"]]}]})
            return self._reply("ReportDraft", {"title": "fake", "claims": claims, "follow_ups": []}, n)
        # investigator: ReAct turns keyed on the number of previous AI turns
        turn = sum(isinstance(m, AIMessage) for m in messages)
        obs = _tool_obs(messages)
        plan = ctx.get("plan", {})
        if self.choice == "InvestigationFindings" or turn >= 3:
            return self._reply("InvestigationFindings", self._findings(obs, plan), n)
        if turn == 0:
            return self._reply("search_product_docs", {"terms": plan["search_terms"]}, n, text="Searching documents.")
        hit = self._target_hit(obs, plan)
        if turn == 1:
            return AIMessage(content="Checking first sale and cohort.", tool_calls=[
                {"name": "first_observed_sale", "args": {"product_id": hit["product_id"]}, "id": _id("fos", n)},
                {"name": "define_cohort", "args": {"product_id": hit["product_id"]}, "id": _id("coh", n)}],
                usage_metadata={"input_tokens": 100, "output_tokens": 20, "total_tokens": 120})
        cohort = next(o for o in obs if "cohort_ids" in o.get("values", {}))["values"]["cohort_ids"].split(",")
        return AIMessage(content="Testing declared hypotheses.", tool_calls=[
            {"name": "launch_trajectory", "args": {"product_id": hit["product_id"], "cohort_ids": cohort,
                                                   "alternative": "two-sided"}, "id": _id("tr", n)},
            {"name": "complaint_comparison", "args": {"product_id": hit["product_id"], "cohort_ids": cohort,
                                                      "alternative": "less"}, "id": _id("cc", n)}],
            usage_metadata={"input_tokens": 100, "output_tokens": 20, "total_tokens": 120})

    @staticmethod
    def _target_hit(obs, plan):
        hits = next(o for o in obs if "hits" in o)["hits"]
        return next(h for h in hits if h["doc_type"] == "announcement" and h["segment"] == plan["focus_segment"]
                    and any(t in h["snippet"].lower() for t in GOOD_TERMS))

    def _findings(self, obs, plan):
        hit = self._target_hit(obs, plan)
        ids = {k: o["evidence_id"] for o in obs for k in ("first_observed_sale_month", "cohort_ids")
               if k in o.get("values", {})}
        tests = [o["evidence_id"] for o in obs if "p_value" in o]
        return {"findings": [{"product_id": hit["product_id"], "positioning": "positioned_on_need",
                              "doc_id": hit["doc_id"], "quote": hit["snippet"],
                              "first_sale_evidence_id": ids.get("first_observed_sale_month"),
                              "cohort_evidence_id": ids.get("cohort_ids"),
                              "sales_evidence_ids": tests[:1], "complaint_evidence_ids": tests[1:2],
                              "observations": "see evidence"}], "summary": "fake findings"}


def factory(name):
    return FakeChat(name)
