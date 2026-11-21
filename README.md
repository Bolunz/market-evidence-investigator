# Market Evidence Investigator

An evidence-first agentic workflow for consumer PC market intelligence. Given a consumer problem that is
showing up in customer feedback (here: battery-life complaints), it answers four questions:

> *Have we seen this consumer problem before? What did manufacturers do about it? What happened to those
> products afterwards? What can we reasonably learn from the evidence?*

CMU Agentic AI capstone. **All data in this repository are synthetic**: the manufacturers, models, product
documents, sell-out figures and consumer signals are fictional. Passing the synthetic evaluation shows that
the method and its guardrails work as designed. It does **not** show that the findings would hold on real
market data.

---

## 1. Why it matters

Ask an LLM "what laptop should we build next?" and it will give a confident answer. That answer is not
grounded in what actually happened in the market. Market-intelligence teams need the opposite: a
recommendation they can trace back to sales records and customer feedback, with an honest statement of how
strong the evidence is.

This system therefore produces an **evidence report, not a verdict**:
- Every statement is labelled as an *observation*, a *statistical association*, a *possible explanation*,
  or an *opportunity hypothesis for an analyst to evaluate*.
- Every number traces to a recorded calculation in an **evidence ledger** that can be re-executed.
- The strength of evidence for each product is graded by fixed rules in code (highest grade: *Moderate*,
  because the data are observational). The LLM never sets a grade.
- A statement that fails verification is not silently deleted. It is moved to a **Flagged statements**
  section with the reason.

## 2. What makes it agentic

The workflow is not a fixed script. Claude decides what to investigate, and code checks it:

| Agent role (model) | What it decides |
|---|---|
| **Planner** (Claude Sonnet 5.5) | which segment to focus on, and which hypotheses and test directions to **declare before any test runs** |
| **Investigator** (Claude Sonnet 5.5, ReAct tool loop) | which documents to search, which products are really positioned on the need, which comparison group is fair, which tests to run, when to stop |
| **Critic** (Claude Sonnet 5.5) | alternative explanations, and **one** extra test it can request (e.g. a placebo theme) |
| **Writer** (Claude Sonnet 5.5) | structured claims, each with a level, assertion types and cited evidence IDs |
| **Auditor** (Claude Haiku 5.5) | implied assertions in claim wording that the rule-based validator could miss |

Around them, deterministic code does everything that must be exact: the statistics, the grades, the
routing between paths, and the claim validation. The LLMs cite evidence IDs; they never compute a number.

## 3. Architecture

```
signal_profile [code]   complaint rates by segment, baseline vs recent, 95% CIs
      |
plan          [LLM]     choose focus segment; DECLARE hypotheses and test directions up front
      |
investigate   [LLM + tools, bounded ReAct loop]
      |    search product documents -> judge positioning -> first observed sale (+ reliability flags)
      |    -> launch cohort -> launch-aligned sales vs cohort -> price-and-volume pattern
      |    -> post-first-sale complaints vs cohort
critic        [LLM]     alternative explanations; may request ONE extra test
      |
assess        [code]    rubric grades from the ledger evidence (the LLM never sets a grade)
      |
write         [LLM]     structured claims: level + assertions + evidence IDs
      |
validate      [code + auditor]   evidence-aware checks; one revision round for flagged claims
      |
report        [code]    Markdown/HTML report, charts, investigation trail, evidence ledger
```

| Component | Where | Role |
|---|---|---|
| Orchestration | `src/mei/agents/graph.py` | LangGraph `StateGraph`; routing decided in code from evidence and data capabilities |
| Analytical tools | `src/mei/analytics`, `src/mei/tools.py` | 10 deterministic Python tools (signal trends, document search, first observed sale, cohorts, launch trajectories, price-and-volume patterns, complaint comparisons) |
| Evidence ledger | `src/mei/ledger.py` | every tool result with an ID (E###), its inputs, test status and q-values; re-executable with `mei check` |
| Rubric | `src/mei/validation/rubric.py` | grades from confirmatory tests only; sensitivity tests can only restrict |
| Claim validator | `src/mei/validation/claims.py` | checks what each claim asserts against the evidence it cites |
| LLM client | `src/mei/llm/client.py` | live / replay / scripted modes, spending and call caps, cost tracking |
| Data adapters | `src/mei/adapters`, `src/mei/contracts.py` | table contracts; the only layer that knows where data come from |

Routing between paths is decided in code:

| Situation | Path |
|---|---|
| No material, statistically supported complaint increase | `insufficient_signal` |
| Products positioned on the need found and examined | `direct_response` (demonstrated) |
| None positioned on the need | `no_direct_response` (specification-based path designed, not implemented) |
| No sell-out / product-document source connected | `not_assessed_market_response`: a data boundary, not a weak finding |

**Key guardrails**
- *Declared vs exploratory tests.* A test only counts towards a grade if the planner declared its tool and
  direction before testing began. Critic tests and robustness re-runs are *sensitivity* tests; anything
  else is *exploratory*.
- *Multiple testing.* Benjamini–Hochberg q-values within test families, plus a pooled q-value across all
  tests (see limitation M5).
- *Claim validation.* Each claim's assertions are checked against the evidence it cites, not by banning
  words. "First observed sale 2023-M10, not a verified launch date" passes; "launched in 2023-M10" is
  flagged because no launch record exists. The same applies to promotions, causal claims, "solved the
  problem", consumer preference and distribution. Numbers must match cited values, quotes must appear in
  cited documents, and product names must exist. A manufacturer figure ("up to 20 hours") passes only when
  attributed to the right product as a manufacturer claim.

## 4. Synthetic data

`src/mei_synth` generates a fictional market: 6 OEMs, about 150 models in 4 segments, 60 months of monthly
sell-out by channel, product announcement documents, and monthly complaint counts by theme. It includes
seasonality, lifecycle ramps, price erosion, unflagged price events, missing specs and label noise.

Each scenario plants a battery-complaint rise in one segment and four products whose truth is known:
- **A** is positioned on battery life. At five effect strengths (strong, moderate, small, null,
  contradictory) it gains share and/or draws fewer battery complaints than comparable products.
- **B** is positioned on battery life, but its early sales coincide with a price cut and volume spike
  (a price-and-volume pattern), not a battery effect.
- **C** is positioned on battery life, but its first observed sale is an artefact of the data panel
  expanding its coverage.
- **G** is positioned on battery life in a different segment, and must stay out of the comparison.

Answer keys are not committed: `make data` regenerates the demo scenarios into `data/synthetic/` and their
keys into `evaluation/answer_keys/` (generation is deterministic; the regenerated `battery_s42` data are
identical to the committed `examples/data/battery_s42`). The application never imports the generator or
reads the keys; a test enforces this. Only `evaluation/run_eval.py` reads them, to score runs.

The demo scenario (`examples/data/battery_s42`, strong tier) is a deliberately clear case for showing the
workflow. The other tiers test whether the system avoids overclaiming when the effect is weak or absent.

## 5. Install and run

Requirements: Python 3.11+ (3.12 recommended), `make`. On macOS, see [`docs/SETUP_MAC.md`](docs/SETUP_MAC.md).

```bash
git clone https://github.com/Bolunz/market-evidence-investigator.git
cd market-evidence-investigator
make setup
make test
```

`make setup` creates `.venv` and installs the pinned dependencies (`requirements.lock`). `make test` runs
the offline test suite (no network, no key).

## 6. Reproduce the recorded investigation (no API key, no cost)

```bash
make demo-replay
make verify-replay
```

- `make demo-replay` replays the recorded live investigation (`examples/battery_s42_agent`). Every
  analytical tool runs again for real; only the LLM responses are played back from the recording. It then
  re-executes every ledger entry from its recorded inputs. Open `runs/demo_replay/report.html`.
- `make verify-replay` replays the recording and compares **every** output with the recorded one: state,
  ledger, validation results, trace, both reports, and call and token counts. On the recording machine all
  outputs are byte-identical. On a different OS or CPU, floats can differ in their last digits (about
  1e-16) and chart images in pixels; the check reports this explicitly and accepts float differences only
  within a relative tolerance of 1e-9. Any other difference fails.
- To score the recorded run against its answer key:

  ```bash
  make data
  .venv/bin/python evaluation/run_eval.py --run examples/battery_s42_agent --key evaluation/answer_keys/battery_s42.json --data examples/data/battery_s42
  ```
- `make demo` runs the same workflow with a deterministic scripted policy instead of Claude, for comparison.
- `make eval` runs the scripted sweep: 20 seeds × 5 effect tiers, scored against the answer keys.

## 7. Run a new live investigation (Anthropic API key)

```bash
cp .env.example .env
```

Edit `.env` and set `ANTHROPIC_API_KEY`. The `.env` file is git-ignored; the key is read only from the
environment and never written to code, config, caches or logs. Then:

```bash
.venv/bin/mei smoke
.venv/bin/mei estimate
make demo-live
make verify-replay RUN=runs/demo_live
```

- `mei smoke`: 7 live checks of the integration (a few cents, capped at $0.50).
- `mei estimate`: cost estimate, no API calls (about $0.63 central, $0.29–$1.55 range).
- `make demo-live`: the full investigation, with a live terminal view of each tool call, decision and
  guardrail event. Each run is capped by `MEI_MAX_COST_USD` (default $3.00) and `MEI_MAX_LLM_CALLS`
  (default 60). A live run refuses to start if its output folder already holds a recording, so it never
  reuses earlier answers.
- The two recorded runs each cost about $0.34–$0.38 in 19 calls.

LLM output varies between runs (Claude Sonnet 5.5 does not accept a temperature setting), so a new run may
make different, equally defensible choices. The recorded run is what the replay reproduces.

## 8. What the system demonstrated

**Live runs with Claude** (`evaluation/live_runs/`, scored against the answer key): two full runs, on
different days and code versions, both passed every check:
- They chose the right segment and found A and B as battery-positioned products.
- They kept G out of the comparison.
- They removed each positioned product from the other's comparison group before testing.
- They graded A *Moderate*, the justified ceiling, with no overclaim.
- They did not treat B's price-and-volume spike as a battery effect, and re-ran B's test with those months
  excluded.
- They declined to test C because its first-sale date is unreliable.
- In run 2 the critic requested a placebo-theme check (display complaints for A). It found no difference
  (2.5% vs 2.2%). That is consistent with A's lower complaint rate being specific to battery, but it is a
  single diagnostic: it does not establish that the battery finding is causal or rule out other
  explanations, and the report says so.

These are two runs, not a reliability estimate. The run reviews, including the problems found and fixed,
are in `evaluation/live_runs/*/README.md`.

**Scripted sweep** ([`evaluation/results/scoreboard.md`](evaluation/results/scoreboard.md)): 100 runs
(20 seeds × 5 tiers) with a deterministic policy in place of Claude.
- **0 overclaims in 100.** No grade ever exceeded what the planted truth justified.
- Strong tier: Moderate in 20/20. Moderate tier: mostly Weak or Not supported (limited power, which is
  correct cautious behaviour). Small and null tiers: Not supported in 20/20. Contradictory tier: Weak in
  20/20, with the contradiction flagged.
- Traps were caught in 19–20 of 20 runs per tier, and every ledger re-executed exactly.

This sweep tests the tools, rubric and guardrails; it does not test Claude's judgment.

## 9. Known limitations

### Methodological
- **M1. Synthetic validation only.** Real data bring noise, mapping errors and gaps that reduce power. The
  planted effects are known by construction; real effects are not.
- **M2. Observational data.** Associations are not causal effects; the rubric therefore caps grades at
  *Moderate*, and the validator rejects causal claims. A placebo check is a diagnostic, not a causal design.
- **M3. First observed sale ≠ launch.** The panel has no launch dates, list prices, promotion flags or
  distribution measures. Market entry is estimated, with reliability flags.
- **M4. Simulated complaint labels.** The synthetic signal imitates classifier output whose accuracy is not
  validated. A real comment pipeline needs a validated classifier and controls for composition and timing.
- **M5. Test-family choice was made after seeing results.** The per-family Benjamini–Hochberg split was
  introduced during development, after a pooled correction pushed a planted effect just past q = 0.05. To
  keep this visible, every test also reports a pooled q-value and every grade is reported again under
  pooled correction; in the 100-run sweep the choice changes one grade.
- **M6. Not implemented:** the specification-based path (no product positioned on the need) and analysis
  of real customer comments are designed but not built.

### Agent behaviour (observed in the live runs)
- **A1. The critic can misread which products were compared.** In both runs the critic said A's comparison
  group "includes" B, although the test had excluded it.
  - *Cause:* a test's result, as shown to the model, does not list the comparison group the test actually
    used, so the critic relies on the earlier, unfiltered cohort list.
  - *Consequence:* a wrong alternative explanation in the critique. The writer did not adopt it, and grades
    are computed from the ledger, so no grade or number was affected.
  - *Proposed improvement:* include the comparison group's size and any excluded products in each test
    result.
- **A2. The writer sometimes labels descriptive observations as statistical associations.** For example,
  the segment's complaint trend was labelled *association*.
  - *Cause:* the validator's feedback says the label is wrong but not which label to use, so a revision can
    repeat the mistake.
  - *Consequence:* the validator correctly flags the claim; in run 2 one correct statement therefore
    appears under *Flagged statements* instead of the findings.
  - *Proposed improvement:* define each level with examples in the claim schema, and name the right label
    in the feedback.
- **A3. Variability.** Planners and investigators make different choices between runs (e.g. run 2 declared
  two overlapping complaint hypotheses). Two runs do not measure how often the agent gets it right.

### Technical
- **T1.** Replay requires the same package versions (`requirements.lock`). Across operating systems, floats
  and chart images differ slightly, as described in section 6.
- **T2.** Cost tracking uses list prices and the token counts the API reports. A request that times out on
  the client side but completes at the provider could be billed without being tracked.

## 10. Towards an authorized corporate data environment

The design keeps everything that depends on where data come from in one layer:
- **Table contracts** (`src/mei/contracts.py`) define the four inputs: products, monthly sell-out, product
  documents and signal counts. A corporate deployment would add an adapter that reads an *authorized*
  sell-out extract and maps it to these contracts. The tools, ledger, rubric and validator would not change.
- **Data capabilities are explicit.** If a source has no product documents or no sell-out, the workflow
  routes to `not_assessed_market_response` instead of guessing.
- **The analytical tools are plain Python functions**, so they can be called by this LangGraph
  orchestrator or by another environment's agent tooling where direct API access is not available.
- **Governance stays in code:** declared hypotheses, test status, FDR control, rubric ceilings and claim
  validation travel with the tools.

What this repository does **not** show: performance on real data, a validated complaint classifier, or
any corporate data. A real deployment would need data-access approval, validation against known market
events, and analyst review of the reports. No corporate data, credentials or restricted material are
included here; `scripts/check_publishable.py` checks this before publication.

## Repository layout

```
src/mei/            application: contracts, adapters, analytics tools, ledger, agents (LangGraph), validation, report
src/mei_synth/      synthetic market generator (isolated from the application)
evaluation/         answer keys, scoring, scripted sweep results, live run records
examples/           demo data, the recorded live run (battery_s42_agent), a scripted run for comparison
tests/              offline tests, incl. a fake chat model that exercises the LLM path and cross-process replay
docs/               methodology, macOS setup
scripts/            pre-publication safety check
```

Detailed methodology: [`docs/methodology.md`](docs/methodology.md).
