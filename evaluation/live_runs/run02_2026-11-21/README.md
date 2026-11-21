# Live run 02 — 2026-11-21 (Claude Sonnet 5.5 + Haiku 5.5, scenario battery_s42, strong tier)

Second full live run, recorded on macOS at commit `6a08179` after the fixes from run 01. This
recording is also the replay demo (`examples/battery_s42_agent`). All data are synthetic.

## Replay

- On the recording Mac: `make verify-replay` passed with every output byte-identical.
- On Linux (different OS/CPU): all 19 recorded calls matched. state, checks, trace and report.md are
  byte-identical. In ledger.json 25 floats differ in their last digits (largest relative difference
  4.7e-16, from the platform's maths library), and the 4 chart images differ in pixels. `verify-replay`
  reports both explicitly and accepts floats only within the ledger check's tolerance (relative 1e-9).
  All 21 tool results re-execute.

## Score against the answer key (`score.json`)

Same outcome as run 01 on every check: correct segment; A (P0113) and B (P0050) found; G kept out of
the cohort; A Moderate (= ceiling, also under pooled FDR); A's sales and complaint effects detected; B
not graded as a sales effect and its price-and-volume pattern reported; C (P0120) flagged unreliable and
not tested; ledger re-executes. Final claims: 13 verified, 1 flagged (run 01: 15 / 0).

## Cost

19 calls, 137,179 input / 13,988 output tokens, **$0.375** tracked (run 01: $0.339).

## Behaviour compared with run 01

Same decisions: focus segment, the two positioned products, removing each from the other's comparison
group (14 comparators, verified in the ledger), the price-and-volume sensitivity re-run for B, not
testing C, excluding the Gaming product.

Different, and better:
- The planner used the new `test` block correctly: it noted that Budget's +0.3 pt change is statistically
  significant (q = 0.014) but below the material-change threshold.
- The investigator was more systematic: first sale for all three candidates and price-and-volume checks
  for both positioned products before testing.
- The critic's placebo request (display complaints for P0113, no comparison group given) now ran, reusing
  the group from E019. Result: 2.5% vs 2.2%, q = 0.64, no detectable difference. This is consistent with
  P0113's lower complaint rate being specific to battery, but it is a single diagnostic: it does not show
  that the battery finding is causal, and it does not rule out other explanations (buyer mix, comment
  propensity, other product differences). The writer reported it in those terms ("this one check does not
  rule these out").
- The critic did not misread the rank reference figure this time (one run; it cannot show the fix works
  in general). All its numbers trace to the ledger.

Different, and worse or open:
- The planner declared two overlapping complaint hypotheses (two-sided and `less`). Harmless here (only
  `less` was tested), but redundant.
- Recurring in both runs: the critic said P0113's cohort "includes P0050". It did not: the test's
  comparison group excluded it. Cause (tool interface): test observations show the result but not the
  comparison group the test used, so the critic reads `define_cohort`'s list. The writer did not adopt it.
- Recurring in both runs: the writer labels descriptive signal statements as level `association`. The
  validator correctly requires an association-type assertion for that level; the feedback says what is
  wrong but not what to use instead, and in run 02 the revision did not fix C2 (the segment trend), so a
  correct statement sits in the flagged section. A guardrail working as designed, at a cost in completeness.
