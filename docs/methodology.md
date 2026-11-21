# Methodology and limitations

## Data contracts (`src/mei/contracts.py`)

| Table | Grain | Notes |
|---|---|---|
| `products` | model | OEM, model, form factor, segment, screen size. **No launch date.** |
| `sellout_monthly` | month × source × country × channel × model | Units, revenue. Specs and price band are row-level **text**. One source must be pinned per analysis (measures never summed across sources). |
| `product_docs` | document | Announcements and spec sheets with publication month. |
| `signal_counts` | month × product × theme | `comments` (all comments: the denominator), `theme_mentions`, `complaints` (classifier-labelled), `unique_authors`. |

An adapter declares its capabilities (`signals`, `product_docs`, `sellout`). The workflow routes on them.

## Consumer signal
- **Complaint rate** = complaints / all comments, so mention volume is not mistaken for dissatisfaction.
- **Baseline vs recent window:** Newcombe difference CI and a two-proportion test.
- **Material change:** needs CI excluding zero, and an absolute change of at least 0.5 percentage points,
  and a relative change of at least 20%. Large samples make trivial shifts "significant".
- **Status values:** `emerging` (baseline ≤ 1%), `intensified_long_standing`, `declining`,
  `no_material_change`, `insufficient_observations`.
- **Concentration:** share of recent complaints from the largest single product.
- **Limitation:** pooled segment rates move with product mix. The evaluation saw a flat-truth segment show a
  "material" change in a few seeds for this reason.

## First observed sale (FOS)
- **Definition:** the first month with sell-out in the pinned source. It is an estimate of market entry,
  never a launch date.
- **Reliability flags:**
  - `left_censored`: selling in the first history month.
  - `coverage_expansion_month`: the month has an anomalous count of new models (median + 3 scaled MADs and
    ≥ 3× median) AND most entrants show no ramp. Ramp is judged on share of segment, which is seasonally
    neutral; genuine launch waves ramp up and are not flagged.
  - `no_visible_ramp`
  - `positioning_doc_precedes_first_sale`: positioning doc more than 3 months earlier.
- **Unreliable FOS** (left-censored or coverage month) cannot anchor launch-aligned comparisons, and such
  products are excluded from cohorts.

## Launch cohort and sales comparison
- **Cohort:** same segment; FOS within ±6 months; early ASP (first 3 months) within ±30%; reliable FOS.
- **Metric:** mean share of segment sell-out over the first 12 months since FOS. Using share removes market
  seasonality and trend.
- **Test:** product-level prediction-interval t-test on log mean share, where each cohort product is one
  observation, with a pre-declared direction. A rank-based reference figure (`empirical_rank_reference`,
  formerly `p_value_exceedance`) is reported alongside, but with ~15 cohort products it cannot fall below
  about 0.06 and it is one-sided, so it is not the test. In the view the agents see, the test is a separate
  `test` block (p, BH q, method, reading rule) and descriptive figures carry definitions, because in live
  run 01 the critic mistook the reference figure for the test's p-value.

## Price-and-volume pattern
- **Trigger:** a month where ASP is at least 12% below its trailing 3-month median AND units are at least
  30% above theirs.
- **Wording:** always reported as an *observed pattern (promotion not confirmed)*, because the data contain
  no promotion or list-price records.
- **Robustness check:** the launch comparison can be re-run excluding each product's own pattern months.

## Complaint comparison
- **Comparison:** target vs cohort products over the **same calendar months** as the target's first 12
  months since FOS.
- **Test:** product-level prediction-interval t-test on logit complaint rate. Pooling comments would treat
  them as independent and ignore persistent product differences; an early version did that and produced a
  false positive in a zero-effect control.
- **Interpretation:** a lower rate is *consistent with* the product addressing the need. Buyer mix, firmware
  updates, attention shifts and small samples remain alternatives.

## Unit of analysis and dependencies
- **Both comparisons use the product as the unit.** Each cohort product is one observation; comments and
  monthly sales rows are not treated as independent.
- **Sales:** each product's mean share of segment sell-out over its own first 12 months since first observed
  sale. Cohort products enter within ±6 months, so calendar windows differ by up to 6 months; share of
  segment removes common seasonality and trend.
- **Complaints:** all products are measured over the same calendar months (the target's first 12 months).
  This controls market-wide complaint shifts, but cohort products are at different lifecycle ages.
- **Cohort size:** the cohort is the same set for both tests. Products with fewer than 30 comments in the
  window are dropped from the complaint test, and both n are reported.
- **Not modelled:** same-manufacturer correlation; shared calendar shocks; segment shares summing to one (a
  strong product slightly lowers others' shares, a mild bias toward finding a difference).
- **Aggregate only.** Relationships are product-level aggregates. They say nothing about why individual
  consumers bought or complained (ecological inference).

## Test status and multiple testing
**Status of each test**, assigned by code when the test runs:

| Status | Definition | Role |
|---|---|---|
| confirmatory | Code screening tests, or a test whose tool and direction match a hypothesis the planner declared before any test ran | The only tests that can support a grade |
| sensitivity | Robustness re-runs: price-and-volume months excluded, or a test requested by the critic after seeing results | Can only restrict a conclusion |
| exploratory | Any other test the agent chooses | Reported, never used to raise a grade; associations that rely on it must say "exploratory" |

**Families** (Benjamini–Hochberg within each), each defined by the question its tests answer:

| Family | Question | Members |
|---|---|---|
| signal_screening | Is the complaint rate materially higher in segment S? | One fixed test per segment |
| sales_confirmatory | Did products positioned on the need gain more segment share than their cohort? | One test per positioned product the agent tests |
| complaints_confirmatory | Did they draw fewer complaints than their cohort in the same months? | One test per positioned product the agent tests |
| sensitivity_exploratory | Robustness and undeclared follow-ups | Everything else |

**Transparency.** The family split was introduced during development, after a pooled correction pushed a
planted effect just past q = 0.05. To keep that decision visible rather than hidden, every test also
reports `q_pooled` (BH across all tests in the run), and every product grade is reported again under pooled
correction (`grade_pooled`). The evaluation reports both.

## Confidence rubric (code only)

| Grade | Rule |
|---|---|
| Moderate | Sales advantage supported AND complaints lower than cohort (both q < 0.05) |
| Weak | Exactly one of the two |
| Not supported | Tests run; neither holds |
| Insufficient | FOS unreliable, or the needed tests were not run |

- **Price-and-volume pattern:** a sales advantage counts only if it survives the exclusion of pattern
  months.
- **Contradictions** are reported, e.g. a sales advantage without lower complaints.
- **Moderate is the ceiling**, because the data are observational.

## Claim validation
- **Claim structure:** each claim has a level, text, and typed assertions with evidence IDs.
- **Evidence requirements:** each assertion type requires compatible evidence types. Some types (verified
  launch date, confirmed promotion, causal effect, problem resolved, consumer preference,
  distribution/availability) require evidence this system does not have, so they can never pass.
- **Auditor:** reads the text and lists what it actually asserts. In live and replay runs this is an LLM;
  a hedge-aware heuristic always runs as well. Qualified statements pass.
- **Other checks:**
  - numbers in the claim's own words must match cited values (quoted document text and confidence levels
    are excluded)
  - quotes must appear in cited documents
  - product IDs and model names must exist
  - grades must match the rubric
- **Revision:** in agent runs, flagged claims go back to the writer once. Remaining failures are shown in a
  flagged section, not as findings.

## Synthetic market (`src/mei_synth/generate.py`)
- **Scale:** 6 fictional OEMs, about 150 models across 4 segments, 60 months, monthly sell-out by
  online/offline channel.
- **Realism:** seasonality, segment trends, lifecycle ramps and declines, ASP erosion, unflagged price events
  on random products, about 12% of battery specs set to N/A, and classifier-like label noise.
- **Planted complaint signal:** battery complaints rise in Premium Thin & Light (5% → 10% of comments, then
  8.5%).
- **Planted products:**
  - **A:** effect tiers (sales attractiveness × / complaint rate ×): strong 4.0/0.35 (demo), moderate
    2.0/0.60, small 1.4/0.80, null 1.0/1.0, contradictory 4.0/1.0.
  - **B:** ASP −20% with units ×1.8 in months 3–6 after FOS.
  - **C:** history hidden until a coverage expansion, along with about 11 other models.
- **Answer key location:** written outside the data directory; product IDs are shuffled.
- **Effect size and power:** the strong tier is a deliberately clear demonstration case. The evaluation keeps
  the moderate, small, zero-effect and contradictory tiers, and scores *appropriateness* first: a grade above
  what the planted truth justifies is an overclaim. Inconclusive results on small effects are correct
  behaviour, not failures.

## Known limitations
1. **Synthetic validation only.** Real noise, mapping errors and data gaps will reduce power.
2. **Signal side.** In this version complaint labels are simulated. A real comment pipeline needs a
   validated classifier, plus composition and time-alignment controls.
3. **Specification path not implemented.** The path for "no product positioned on the need" (spec share vs
   assortment share with placebo tests) is designed but not built.
4. **No distribution or assortment data.** Velocity (sales ÷ distribution) cannot be computed.
5. **History length.** One history window means earlier complaint episodes cannot be compared.

Limitations in the agents' behaviour observed in the two live runs (critic misreading the comparison
group; writer mislabelling descriptive statements), with causes and proposed fixes, are in the README,
section 9.
