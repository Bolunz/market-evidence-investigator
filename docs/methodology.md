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
  observation, with a pre-declared direction. Rank-based exceedance p is reported alongside, but with ~15
  cohort products it cannot fall below about 0.06, so it is not the test.

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

## Multiple testing
- Benjamini–Hochberg within each test family: signal screening, sales vs cohort, complaints vs cohort.
- Every test run in a family counts, including agent-chosen and exploratory tests.
- Tests without a matching declared hypothesis (tool + direction) are labelled exploratory. Associations
  relying on them must say so.

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
  - **A:** attractiveness ×4 and complaint rate ×0.35 in the positive variant; ×1 and ×1 in the zero-effect
    variant.
  - **B:** ASP −20% with units ×1.8 in months 3–6 after FOS.
  - **C:** history hidden until a coverage expansion, along with about 11 other models.
- **Answer key location:** written outside the data directory; product IDs are shuffled.
- **Effect size and power:** with the earlier, smaller effects (×3.0 sales, ×0.45 complaints), raw tests were
  significant in most seeds but both survived FDR in only about 40%. Detection power depends on effect size,
  and real effects may be smaller.

## Known limitations
1. **Synthetic validation only.** Real noise, mapping errors and data gaps will reduce power.
2. **Signal side.** In this version complaint labels are simulated. A real comment pipeline needs a
   validated classifier, plus composition and time-alignment controls.
3. **Specification path not implemented.** The path for "no product positioned on the need" (spec share vs
   assortment share with placebo tests) is designed but not built.
4. **No distribution or assortment data.** Velocity (sales ÷ distribution) cannot be computed.
5. **History length.** One history window means earlier complaint episodes cannot be compared.
