# Live run 01 — 2026-11-20 (Claude Sonnet 5.5 + Haiku 5.5, scenario battery_s42, strong tier)

First full live agent run, made on macOS at commit `452276b`. Kept as an **evaluation record**, not
as the replay demo: it cannot be replayed (see "Replay" below). All data are synthetic.

## Score against the answer key (`score.json`)

All checks pass: correct segment, A (P0113) and B (P0050) found, G (P0084) kept out of the cohort,
A graded Moderate (= ceiling, no overclaim; same under pooled FDR), A's sales and complaint effects
detected, B not graded as a sales effect and its price-and-volume pattern reported, C (P0120)
first sale flagged unreliable and not tested, ledger re-executes exactly, 15/15 final claims verified.

One run is one sample of LLM behaviour; it shows the workflow can reach the right answer, not how often.

## Cost

19 calls, 120,324 input / 13,884 output tokens, **$0.339** tracked at list prices (estimate: $0.63
central, $0.29–$1.55 range). Not yet reconciled with the Anthropic Console.

## Observed behaviour (from `trace.jsonl`, `state.json`, `llm_cache.jsonl`)

Good:
- Planner chose the right segment, read the trend as "intensified long-standing", noted the data
  cannot support causal claims, declared H1 complaints `less`, H2 sales `two-sided`.
- Investigator recovered from a zero-hit exact-phrase search by broadening terms.
- It removed the other battery-positioned product from each comparison group before testing
  (verified in the ledger `cohort_ids`), and ran the price-and-volume sensitivity test for P0050.
- It declined to test P0120 because its first sale is unreliable, and labelled P0084 a segment mismatch.
- Thinking blocks were returned on two investigator turns and passed back successfully (first live
  exercise of that path).
- Every number the critic used traces to the ledger.

Problems found:
1. **Replay broken (fixed in code after this run).** The writer prompt listed products in set order,
   which varies between Python processes, so the recording's writer key cannot be matched.
   Fix: sorted order + a test that records under two `PYTHONHASHSEED` values and requires identical keys.
2. **Critic's requested test was lost.** It asked for a placebo-theme check (P0113 display complaints)
   but omitted the required `cohort_ids`, and the request was rejected. Offline check (ours, not the
   agent's): P0113 is at the cohort median on display (2.5% vs 2.2%, p=0.72) and thermals (3.3% vs 3.0%,
   p=0.60), low only on battery. That would have been one piece of evidence against the critic's
   "comment mix" explanation, not proof of it being wrong, and nothing causal. (In synthetic data this
   pattern is expected by construction.)
3. **Validator false positive on document numbers.** "Up to 20 / 17 / 18 hours" are in the cited
   documents, but the number check searches only computed values, so the revision dropped correct figures.
4. **Critic errors (not adopted by the writer):** it said P0113 inflated P0050's comparison although
   P0113 had already been excluded; and it called A's sales result "not significant" by reading the
   rank-based `p_value_exceedance` (0.067) instead of the test's p (0.004).
5. Minor: the terminal view omits list arguments such as `cohort_ids`; the report trail truncates
   decisions at 300 characters; first-draft validation flags were mostly level/assertion-type
   mismatches that one revision fixed.

## Changes made after this run (commit after `0963ea1`)

Fixes 2–4 and the replay audit are in the next commit: the critic's comparison group is resolved from
the investigator's own tests (rejected if none or ambiguous); off-theme complaint tests are never
confirmatory or graded; document figures pass only when attributed to the right product, with the same
unit, as manufacturer claims; the test result is a separate `test` block and the rank figure is renamed
`empirical_rank_reference` with a definition. This ledger still re-executes (the old key name is mapped).
Re-validating this run's first draft with the new validator: C4 now passes; the other five flags are unchanged.
