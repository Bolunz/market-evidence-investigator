# Market Evidence Investigator

An evidence-first agentic workflow that helps market-intelligence analysts answer:

> *Have we seen this consumer problem before? What did manufacturers do about it? What happened to those
> products afterwards? What can we reasonably learn from the evidence?*

The system does not hand down opportunity verdicts. It produces an **evidence report**: every statement is
labelled as an *observation*, a *statistical association*, a *possible explanation* or an *opportunity
hypothesis for analyst evaluation*, and every number traces to a recorded, re-executable calculation.
Statements that fail verification are not deleted; they are moved to a **flagged** section with the reason.

CMU Agentic AI capstone. **All data in this repository are synthetic.** The manufacturers, models, documents,
sell-out figures and consumer signals are fictional. Passing the synthetic evaluation shows that the method and
guardrails work; it does **not** establish real-world validity.

---

## Quick start (no API key needed)

```bash
make setup          # Python 3.11+; creates .venv and installs pinned dependencies
make test           # offline test suite
make demo-replay    # replays the recorded Claude-powered investigation: no key, no cost
make demo           # scripted (no-LLM) run of the same workflow, for comparison
make eval           # 20 seeds x 5 effect tiers (strong, moderate, small, null, contradictory) vs answer keys
```

Open `runs/demo_replay/report.html` to read the report.

`make demo-replay` re-executes **every analytical tool for real** and plays back only the recorded LLM
responses, then re-checks each ledger entry against its recorded inputs (`mei check`).
`make verify-replay` goes further: it replays the recording and requires every output (state, ledger,
validation checks, trace, report, call and token counts) to be identical to the recorded run. A replay
uses the models, effort and tool budget stored with the recording, not the local `.env`.

## Live run with the Anthropic API

See [`docs/SETUP_MAC.md`](docs/SETUP_MAC.md). In short:

```bash
cp .env.example .env          # .env is git-ignored; set ANTHROPIC_API_KEY=...
.venv/bin/mei smoke           # 7 checks, a few cents, capped at $0.50
.venv/bin/mei estimate        # cost estimate for a full run (no API calls)
make demo-live                # full investigation; writes runs/demo_live/ incl. an LLM cache for replay
make verify-replay RUN=runs/demo_live   # replay it (no API calls) and compare every output
```

A live run refuses to start if its output folder already holds a recording, so it can never silently
reuse earlier answers; use a new folder, or `--resume` to continue an interrupted run.

The key is read only from the environment (or the local, git-ignored `.env`). It is never written to code,
config, caches or logs. Each run has a USD spending cap (`MEI_MAX_COST_USD`, default $3.00): a call is
refused if its worst case could exceed the cap. There is also a call cap (`MEI_MAX_LLM_CALLS`, default 60). The terminal shows each step
as it happens: tool calls, agent decisions, guardrail events and routing.

## How it works

```
signal_profile [code]   complaint rates by segment, baseline vs recent, 95% CIs
      |
plan          [LLM]     choose focus segment; DECLARE hypotheses and test directions up front
      |
investigate   [LLM + tools, ReAct loop]
      |    search product documents -> judge positioning -> first observed sale (+ reliability flags)
      |    -> launch cohort -> launch-aligned sales vs cohort -> price-and-volume pattern
      |    -> post-first-sale complaints vs cohort
critic        [LLM]     alternative explanations; may request ONE extra test
      |
assess        [code]    rubric grades from ALL ledger evidence (the LLM never sets a grade)
      |
write         [LLM]     structured claims: level + assertions + evidence IDs
      |
validate      [code + auditor]   evidence-aware checks; one revision round for flagged claims
      |
report        [code]    Markdown/HTML report, charts, investigation trail, evidence ledger
```

Routing is decided in code from evidence and data capabilities:

| Situation | Path |
|---|---|
| No material, statistically supported complaint increase | `insufficient_signal` |
| Products positioned on the need found and examined | `direct_response` |
| None positioned on the need | `no_direct_response` (spec-based path designed, not implemented) |
| No sell-out / product-document source connected | `not_assessed_market_response`: a data boundary, not a weak finding |

**Division of labour.** Every number comes from a deterministic tool (`src/mei/analytics`) and is
recorded in the evidence ledger. The LLM roles plan, choose tools, judge document positioning, propose
alternative explanations and write. They cite evidence IDs and never compute.

**Guardrails** (`src/mei/validation`):
- *Claim validator.* Checks what each claim **asserts** against the evidence it **cites**, rather than
  banning words. "First observed sale 2023-M10, not a verified launch date" passes; "launched in 2023-M10"
  is flagged, because no launch-record evidence exists. The same applies to promotions, causal claims,
  "solved the problem", consumer preference and distribution. Numbers must match cited values, quotes must
  appear in cited documents, and product names must exist.
- *Associations* must cite a test with Benjamini–Hochberg q < 0.05. FDR is controlled within each test
  family, and agent-chosen tests count toward it.
- *Declared vs exploratory.* Tests whose direction was not declared in the plan are labelled exploratory.
- *Rubric ceiling.* "Moderate" is the highest grade, because the data are observational.

## Evaluation (synthetic scenarios with isolated answer keys)

The generator (`src/mei_synth`, a separate package that the application never imports; this is enforced by
a test) writes answer keys to `evaluation/answer_keys/`, which only `evaluation/run_eval.py` reads. Each
scenario plants:

- **A**: positioned on battery life; in the *positive* variant it outperforms its cohort and draws fewer
  complaints; in the *zero-effect* variant it behaves like its cohort.
- **B**: positioned on battery life; its early sales coincide with an ASP cut and unit spike (a
  price-and-volume pattern); complaints do not fall.
- **C**: positioned on battery life, but its first observed sale is an artefact of a panel coverage
  expansion.
- **G**: positioned on battery life in a different segment.
- Distractor documents that mention batteries incidentally.

Each scenario is generated at five effect strengths for A (strong, moderate, small, zero, contradictory).
The primary measure is **appropriateness**: whether a grade ever exceeds what the planted truth justifies.
Inconclusive results on small effects are correct behaviour. Results are in
[`evaluation/results/`](evaluation/results/). The scripted-policy sweep scores structured
outputs only. The recorded agent run is scored with
`python evaluation/run_eval.py --run <run> --key <key> --data <data>`.

## Repository layout

```
src/mei/            application: contracts, adapters, analytics tools, ledger, agents (LangGraph), validation, report
src/mei_synth/      synthetic market generator (isolated from the application)
evaluation/         answer-key scoring (the only code that reads answer keys)
examples/           committed demo data and the recorded agent run (report, ledger, trace, LLM cache)
tests/              offline tests, including a fake chat model that exercises the LLM path and replay
docs/               methodology and limitations
scripts/            pre-publication safety check
```

## Limitations

See [`docs/methodology.md`](docs/methodology.md). In short:
- Synthetic data validate mechanics and guardrails, not real-world effect detection.
- First observed sale estimates market entry; the panel has no launch date, list price, promotion flag or
  distribution measure.
- Complaint labels in the synthetic data simulate classifier output whose accuracy is not validated.
- Pooled segment complaint rates can move with product mix (composition effects).
- The specification-based investigation path and the real-comment signal mode are designed but not part of
  this version.
