# Battery life complaints in Premium Thin & Light: historical context, positioning and outcomes

> **Run mode:** live agent run (Anthropic API) · **Data:** battery_s42 (synthetic)
> **Path:** Direct market-response path: products positioned on the need were found and examined.

> All data in this report are synthetic (fictional manufacturers, models and figures). Passing the synthetic evaluation shows the method and guardrails work; it does not establish real-world validity.

Every statement below passed evidence verification. Each is labelled as an observation, a statistical association, a possible explanation, or an opportunity hypothesis, and cites ledger evidence (E###). Causal conclusions are not produced.

## A. Consumer signal

- **Observation** - Premium Thin & Light has the highest recent battery complaint rate, 6.9% [6.7%, 7.1%], versus Budget 3.8%, Gaming 3.4% and Mainstream 3.4%. `[E001]`
- **Observation** - In Premium Thin & Light the battery complaint rate moved from 4.4% at baseline to 6.9% recently (diff +2.5%, CI +2.2% to +2.8%), labelled intensified_long_standing. This is descriptive and pooled segment rates can move with product mix. `[E005]`
- **Observation** - Other segments show no material change: Budget 3.5% to 3.8%, Gaming 3.2% to 3.4%, Mainstream 3.4% to 3.4%. `[E002, E003, E004]`

## B. Historical context

- **Observation** - The segment baseline window (2021-M01..2022-M06) already had a battery complaint rate of 4.4%, so battery complaints are not new in this segment; the recent level is higher. `[E005]`

## C. Historical market response

- **Observation** - Documents for P0113 (Altura Aero 13 G4) and P0050 (Brevik Aero 14 G4) headline battery life, and P0120 (Corvane Lumen 14 G2) shares battery with its display. This is documented positioning only, not proof that the need was solved. `[E008, E009, E016]`

## D. Observable sales and complaint evidence

- **Observation** - P0113 first observed sale is 2023-M10 (an estimate of market entry, not a verified launch date), reliability usable. Its mean segment share over 12 months was 18.09% versus a cohort median of 3.88%, rank 1 of 15. `[E010, E017]`
- **Statistical association** - P0113's battery complaint rate was 3.2% versus a cohort median of 9.0%, lower than the cohort (p=0.0066, q=0.0132). This is an association only. `[E018]`
- **Statistical association** - P0113's segment share is higher than the cohort median (p=0.0037, q=0.0074); this is descriptive and does not measure distribution or preference. `[E017]`
- **Observation** - P0050 share was 5.66% versus cohort median 3.88%, not distinguishable (p=0.4675); excluding the 2024-M02 and 2024-M03 observed price-and-volume months it stayed indistinguishable (p=0.6397). Promotion is not confirmed. `[E019, E021, E022]`
- **Observation** - P0050 battery complaint rate was 8.8% versus cohort median 8.7%, no detectable difference. This is insufficient evidence of a difference, not evidence of none. `[E023]`
- **Evidence gap** - P0120 first observed sale (2022-M04) is unreliable (coverage expansion month, no visible ramp), so no sales or complaint comparison was run: insufficient evidence. `[E011, E027]`

## E. Evidence assessment

- **Observation** - Rubric grades: segment signal Moderate; P0113 Moderate; P0050 Not supported; P0120 Insufficient. Moderate is the ceiling for observational data. `[E024, E025, E026, E027]`
- **Possible explanation** - P0113's results could possibly reflect factors other than battery positioning, such as comment mix or volume, buyer mix, or cohort choice. Distribution and availability are not measured in this data, so these alternatives cannot be ruled out. `[E014, E017, E018]`
- **Evidence gap** - The evidence is mixed across the positioned products and no causal conclusion is supported. The data cannot show whether manufacturer actions changed the segment-wide complaint rate. `[E005, E025, E026, E027]`

## F. Opportunity hypotheses (for analyst evaluation)

- **Opportunity hypothesis** - For human evaluation: P0113 could be examined as a case of battery-led positioning with lower battery complaints. This is a hypothesis only; a placebo-theme check and sensitivity analyses are needed first. `[E017, E018, E025]`

### Suggested follow-up investigations

- Run a placebo-theme complaint comparison (e.g. display) for P0113.
- Rerun the P0050 comparison with P0113 excluded from the cohort.
- Check sensitivity to cohort window and ASP tolerance.
- Compute fixed-product complaint trends over time and comment counts per period.
- Seek distribution or availability data, which is absent from this dataset.

## Flagged statements (failed verification; NOT findings)

_None._


## Evidence assessment (code rubric)

| Subject | Grade | Grade (pooled FDR) | Sales | Complaints | First observed sale | Contradiction | Notes |
|---|---|---|---|---|---|---|---|
| battery signal, Premium Thin & Light (E024) | Moderate | - | - | - | - | - | complaint labels come from a classifier whose accuracy is not validated in this dataset; pooled segment rates can move with product mix |
| P0113 (E025) | Moderate | Moderate | supported | lower_than_cohort | usable | none | none |
| P0050 (E026) | Not supported | Not supported | not_supported | no_detectable_difference | usable | none | observed price-and-volume pattern (promotion not confirmed) |
| P0120 (E027) | Insufficient | Insufficient | not_tested | not_tested | unreliable | none | first observed sale is unreliable (cannot anchor launch-aligned comparisons) |

Grades: Moderate (sales advantage AND lower complaints) > Weak (one of the two) > Not supported > Insufficient. Moderate is the ceiling for observational data. Only confirmatory (pre-declared) tests can support a grade; sensitivity re-runs can only restrict it; exploratory tests are reported, not graded.

### Method notes: unit of analysis and test families

- Unit of analysis is the PRODUCT, in both comparisons. Sales: each product's mean share of segment sell-out over its own first 12 months since first observed sale (cohort products enter within +/-6 months, so calendar windows differ by up to 6 months; share of segment removes common seasonality and market trend). Complaints: every product's rate over the SAME calendar months (the target's first 12 months), so market-wide complaint shifts are controlled but cohort products are at different lifecycle ages. The cohort is the same set for both tests; products with fewer than 30 comments are dropped from the complaint test (both n are reported).
- Dependencies not modelled: products from the same manufacturer; cohort products sharing calendar shocks; segment shares summing to one (a strong product slightly lowers others' shares).
- These are aggregate, product-level relationships. They do not describe individual consumers: a lower complaint rate among a product's commenters does not show that individual buyers chose it for battery life.
- Test families (Benjamini-Hochberg within each): signal screening; confirmatory sales tests; confirmatory complaint tests; sensitivity + exploratory tests. Families are defined by the question a test answers; the pooled q across all tests and the grade under pooled correction are shown for comparison.

## Investigation trail

1. `[signal_profile:tool]` signal_by_segment -> E001: Premium Thin & Light: 6.9% [6.7%, 7.1%]; Budget: 3.8% [3.6%, 3.9%]; Gaming: 3.4% [3.2%, 3.6%]; Mainstream: 3.4% [3.3%, 3.5%]
2. `[signal_profile:tool]` signal_trend[Budget] -> E002: battery complaint rate in Budget: 3.5% baseline -> 3.8% recent (diff +0.3%, 95% CI +0.1% to +0.5%); status=no_material_change.
3. `[signal_profile:tool]` signal_trend[Gaming] -> E003: battery complaint rate in Gaming: 3.2% baseline -> 3.4% recent (diff +0.3%, 95% CI -0.0% to +0.6%); status=no_material_change.
4. `[signal_profile:tool]` signal_trend[Mainstream] -> E004: battery complaint rate in Mainstream: 3.4% baseline -> 3.4% recent (diff +0.0%, 95% CI -0.2% to +0.2%); status=no_material_change.
5. `[signal_profile:tool]` signal_trend[Premium Thin & Light] -> E005: battery complaint rate in Premium Thin & Light: 4.4% baseline -> 6.9% recent (diff +2.5%, 95% CI +2.2% to +2.8%); status=intensified_long_standing.
6. `[signal_profile:decision]` Segments with a material increase: ['Premium Thin & Light']
7. `[plan:decision]` Focus segment: Premium Thin & Light. Premium Thin & Light has the highest recent battery complaint rate (6.9% [6.7%, 7.1%], E001). It is the only segment with a material increase from baseline: 4.4% to 6.9%, diff +2.5% (CI +2.2% to +2.8%), status intensified_long_standing (E005). This suggests battery complaints are a long-standing issue that has intensified, not a new one. Budget showed a small increase (+0.3%) but was labelled no_material_change (E002). Gaming (E003) and Mainstream (E004) show no material change. The complaint load is spread across 28 products, and the top product accounts for 12.6% of recent complaints (E005), so one product is unlikely to drive the pattern. This is descriptive only. The data have no distribution, availability or preference measures, so no causal conclusions can be drawn.
8. `[plan:decision]` Declared H1 (complaint_comparison, less): Premium Thin & Light products positioned on battery life in their documents have a different post-first-sale battery complaint rate than other Premium Thin & Light products in the same cohort. This is an association only, and first sale is an estimate of market entry.
9. `[plan:decision]` Declared H2 (launch_trajectory, two-sided): Premium Thin & Light products positioned on battery life have different sales per active model after their estimated first observed sale than the cohort of comparable products. This is descriptive and does not measure distribution or preference.
10. `[investigate:tool]` search_product_docs({'terms': ['all-day battery life', 'up to hours battery', 'battery life optimized', 'long-lasting battery', 'fast charging', 'power efficiency', 'extended battery runtime', 'large capacity battery'], 'segment': 'Premium Thin & Light'}) -> E006: 0 documents match ['all-day battery life', 'up to hours battery', 'battery life optimized', 'long-lasting battery', 'fast charging', 'power efficiency', 'extended battery runtime', 'large capacity battery'] (segment=Premium Thin & Light); returned 0.
11. `[investigate:tool]` search_product_docs({'terms': ['all-day battery life', 'long-lasting battery', 'battery life']}) -> E007: 3 documents match ['all-day battery life', 'long-lasting battery', 'battery life'] (segment=ALL); returned 3.
12. `[investigate:tool]` get_product_doc({'doc_id': 'D0113A'}) -> E008: D0113A (announcement, 2023-M09) for Altura Aero 13 G4: Introducing the Altura Aero 13 G4: engineered for endurance, with up to 20 hours of battery life so you can work a full day and evening without a charger.
13. `[investigate:tool]` get_product_doc({'doc_id': 'D0120A'}) -> E009: D0120A (announcement, 2021-M09) for Corvane Lumen 14 G2: Meet the Corvane Lumen 14 G2: up to 18 hours of battery life and a brilliant OLED display.
14. `[investigate:tool]` first_observed_sale({'product_id': 'P0113'}) -> E010: P0113: first observed sale 2023-M10 (an estimate of market entry, not a verified launch date); reliability=usable; flags=none.
15. `[investigate:tool]` first_observed_sale({'product_id': 'P0120'}) -> E011: P0120: first observed sale 2022-M04 (an estimate of market entry, not a verified launch date); reliability=unreliable; flags=coverage_expansion_month,no_visible_ramp,positioning_doc_precedes_first_sale.
16. `[investigate:tool]` search_product_docs({'terms': ['battery', 'hours', 'endurance', 'charger'], 'segment': 'Premium Thin & Light'}) -> E012: 55 documents match ['battery', 'hours', 'endurance', 'charger'] (segment=Premium Thin & Light); returned 25.
17. `[investigate:reasoning]` (thinking) P0050 is also positioned now, so I need to check its sale next. After that I'll pull cohorts for P0113 and P0050.
18. `[investigate:tool]` first_observed_sale({'product_id': 'P0050'}) -> E013: P0050: first observed sale 2023-M11 (an estimate of market entry, not a verified launch date); reliability=usable; flags=none.
19. `[investigate:tool]` define_cohort({'product_id': 'P0113'}) -> E014: Cohort for P0113: 15 Premium Thin & Light models with first observed sale within +/-6 months and early ASP within +/-30%.
20. `[investigate:tool]` price_volume_pattern({'product_id': 'P0113'}) -> E015: P0113: no price-and-volume pattern at thresholds (ASP -12%, units +30%).
21. `[investigate:tool]` search_product_docs({'terms': ['all-day battery', 'days of battery', 'battery that lasts']}) -> E016: 1 documents match ['all-day battery', 'days of battery', 'battery that lasts'] (segment=ALL); returned 1.
22. `[investigate:reasoning]` (thinking) I'm treating P0050 as part of P0113's cohort, so for a fair comparison I'll exclude P0050 from the cohort when evaluating P0113 and the reverse for P0050. Then I'll run the tests.
23. `[investigate:tool]` launch_trajectory({'product_id': 'P0113', 'alternative': 'two-sided'}) -> E017: P0113: mean segment share 18.09% over first 12 months since first observed sale vs cohort median 3.88% (rank 1 of 15; prediction-interval p=0.004, two-sided).
24. `[investigate:tool]` complaint_comparison({'product_id': 'P0113', 'alternative': 'less'}) -> E018: P0113: battery complaint rate 3.2% [95% CI 2.7%-3.7%] vs cohort median 9.0% across 14 products in the same months (product-level p=0.007, less); lower_than_cohort.
25. `[investigate:tool]` price_volume_pattern({'product_id': 'P0050'}) -> E019: P0050: 2 month(s) with observed price-and-volume pattern (promotion not confirmed): 2024-M02,2024-M03.
26. `[investigate:tool]` define_cohort({'product_id': 'P0050'}) -> E020: Cohort for P0050: 15 Premium Thin & Light models with first observed sale within +/-6 months and early ASP within +/-30%.
27. `[investigate:tool]` launch_trajectory({'product_id': 'P0050', 'alternative': 'two-sided'}) -> E021: P0050: mean segment share 5.66% over first 12 months since first observed sale vs cohort median 3.88% (rank 5 of 15; prediction-interval p=0.467, two-sided).
28. `[investigate:tool]` launch_trajectory({'product_id': 'P0050', 'alternative': 'two-sided', 'exclude_price_volume_months': True}) -> E022: P0050: mean segment share 5.05% over first 10 months since first observed sale vs cohort median 3.88% (rank 5 of 15; prediction-interval p=0.640, two-sided).
29. `[investigate:tool]` complaint_comparison({'product_id': 'P0050', 'alternative': 'less'}) -> E023: P0050: battery complaint rate 8.8% [95% CI 7.5%-10.4%] vs cohort median 8.7% across 14 products in the same months (product-level p=0.542, less); no_detectable_difference.
30. `[investigate:decision]` P0113: positioned_on_need. Battery life is the headline selling point (E008). First observed sale 2023-M10, usable, one month after the doc (E010). Cohort of 14 comparators after excluding P0050 (E014). Mean segment share over the first 12 months was 18.1% vs a cohort median of 3.9%, rank 1 of 15 (E017). No price-and-volume p
31. `[investigate:decision]` P0050: positioned_on_need. Battery is a lead selling point (E016). First observed sale 2023-M11, usable (E013). Segment share was 5.7% vs a cohort median of 3.9%, rank 5 of 15, not distinguishable (p=0.47) (E021). It stayed indistinguishable with the 2024-M02 and 2024-M03 price-and-volume months excluded (p=0.64) (E022, E019)
32. `[investigate:decision]` P0120: positioned_on_need. Battery is a selling point, but it is shared with the display (E009). The first observed sale is flagged unreliable (coverage_expansion_month, no_visible_ramp, doc precedes first sale by 7 months) (E011). I did not run a launch-aligned comparison or complaint comparison, because it would rest on an 
33. `[investigate:decision]` P0084: segment_mismatch. The Gaming product Elsari Strike 15 G4 mentions a long-lasting battery (E007). It is outside the focus segment.
34. `[critic:decision]` Alternative for P0113: High segment share may reflect a launch-size or distribution/availability effect, or a few-model segment composition artefact (share is relative to active models). The data contain no distribution or availability measure. Also, the first-month units (5,860) and early peak (21,541) are large, which fits a broad rollout rather than a battery-driven effect.
35. `[critic:decision]` Alternative for P0113: The low battery complaint rate may reflect complaint-pool or comment-mix differences. P0113 has 4,826 comments against 1,465 for P0050, and other themes may dominate its comments, so battery would be a smaller share. Buyer mix could also differ, for example lighter-use buyers. Other causes include firmware or hardware differences. A high-volume product may attract more casual commenters. The cohort median of 9.0% is also well above the segment rate of 6.9%, which suggests a skewed cohort.
36. `[critic:decision]` Alternative for P0113: The cohort is only 14 products with a wide spread in complaint rates (4.6% to 13.8%). The p-values come from several confirmatory tests, and the cohort definition (+/-6 months, ASP +/-30%) is a researcher choice. The result may be sensitive to those choices. Price is also a factor: ASP within 30% still allows differences in buyer expectations.
37. `[critic:decision]` Alternative for P0050: The null result for P0050 may reflect low power: the complaint pool is small (1,465 comments, 129 complaints), the share test has only 14 comparators, and the p-values are far from significance. A null is not evidence of no effect. Price-and-volume months in 2024-M02 and 2024-M03 may also distort the share, though the sensitivity check suggests not.
38. `[critic:decision]` Alternative for P0113: P0113 and P0050 share overlapping cohorts and first-sale months, and each appears in the other's cohort. P0113's very large share (18%) inflates the cohort comparison for P0050, since the cohort median is the same 3.88%. P0113 may also be an outlier that skews the others' comparisons.
39. `[critic:decision]` Alternative for P0120: The first observed sale (2022-M04) coincides with a coverage-expansion month and the doc precedes it by 7 months. The product may have sold earlier, so the entry date is an artefact. This is consistent with the unreliable flag, and the product cannot be assessed.
40. `[critic:decision]` Alternative for P0113: The segment-wide complaint rise from 4.4% to 6.9% may reflect complaint-pool changes (more comments, a shift in who comments, or greater attention to battery) and not worse batteries. The 28 products recently active against earlier ones also mean composition changed, so manufacturer responses cannot be tied to it.
41. `[critic:guard]` Critic's requested test rejected: invalid arguments for complaint_comparison: Field required
42. `[assess:assess]` Signal grade for battery in Premium Thin & Light: Moderate.
43. `[assess:assess]` P0113: grade Moderate (sales: supported; complaints: lower_than_cohort; first sale: usable; grade under pooled FDR: Moderate).
44. `[assess:assess]` P0050: grade Not supported (sales: not_supported; complaints: no_detectable_difference; first sale: usable; grade under pooled FDR: Not supported).
45. `[assess:assess]` P0120: grade Insufficient (sales: not_tested; complaints: not_tested; first sale: unreliable; grade under pooled FDR: Insufficient).
46. `[assess:route]` Investigation path: direct_response
47. `[write:decision]` Draft with 13 claims.
48. `[validate:guard]` Claim validation: 7 verified, 6 flagged.
49. `[validate:guard]` C2 flagged: level 'association' needs one of ['complaint_association', 'sales_association']
50. `[validate:guard]` C4 flagged: number '20' not found in cited evidence; number '17' not found in cited evidence; number '18' not found in cited evidence
51. `[validate:guard]` C7 flagged: level 'association' needs one of ['complaint_association', 'sales_association']
52. `[validate:guard]` C8 flagged: level 'association' needs one of ['complaint_association', 'sales_association']
53. `[validate:guard]` C11 flagged: level 'method_note' cannot carry ['confidence_grade']
54. `[validate:guard]` C12 flagged: availability_or_distribution (declared) requires distribution_record evidence; no such evidence exists in this run
55. `[validate:route]` Returning flagged claims to the writer for one revision.
56. `[write:decision]` Draft with 15 claims.
57. `[validate:decision]` Claim validation: 15 verified, 0 flagged.

## Evidence ledger

| ID | Tool | Requested by | Summary | p | q (family) | q (pooled) | Status | Family |
|---|---|---|---|---|---|---|---|---|
| E001 | signal_by_segment | code | Premium Thin & Light: 6.9% [6.7%, 7.1%]; Budget: 3.8% [3.6%, 3.9%]; Gaming: 3.4% [3.2%, 3.6%]; Mainstream: 3.4% [3.3%, 3.5%] |  |  |  |  |  |
| E002 | signal_trend | code | battery complaint rate in Budget: 3.5% baseline -> 3.8% recent (diff +0.3%, 95% CI +0.1% to +0.5%); status=no_material_change. | 0.007 | 0.014 | 0.016 | confirmatory | signal_screening |
| E003 | signal_trend | code | battery complaint rate in Gaming: 3.2% baseline -> 3.4% recent (diff +0.3%, 95% CI -0.0% to +0.6%); status=no_material_change. | 0.089 | 0.118 | 0.160 | confirmatory | signal_screening |
| E004 | signal_trend | code | battery complaint rate in Mainstream: 3.4% baseline -> 3.4% recent (diff +0.0%, 95% CI -0.2% to +0.2%); status=no_material_change. | 0.950 | 0.950 | 0.950 | confirmatory | signal_screening |
| E005 | signal_trend | code | battery complaint rate in Premium Thin & Light: 4.4% baseline -> 6.9% recent (diff +2.5%, 95% CI +2.2% to +2.8%); status=intensified_long_standing. | 0.000 | 0.000 | 0.000 | confirmatory | signal_screening |
| E006 | search_product_docs | agent | 0 documents match ['all-day battery life', 'up to hours battery', 'battery life optimized', 'long-lasting battery', 'fast charging', 'power efficiency', 'extended battery runtime', 'large capacity battery'] (segment=Premium Thin & Light); returned 0. |  |  |  |  |  |
| E007 | search_product_docs | agent | 3 documents match ['all-day battery life', 'long-lasting battery', 'battery life'] (segment=ALL); returned 3. |  |  |  |  |  |
| E008 | get_product_doc | agent | D0113A (announcement, 2023-M09) for Altura Aero 13 G4: Introducing the Altura Aero 13 G4: engineered for endurance, with up to 20 hours of battery life so you can work a full day and evening without a charger. |  |  |  |  |  |
| E009 | get_product_doc | agent | D0120A (announcement, 2021-M09) for Corvane Lumen 14 G2: Meet the Corvane Lumen 14 G2: up to 18 hours of battery life and a brilliant OLED display. |  |  |  |  |  |
| E010 | first_observed_sale | agent | P0113: first observed sale 2023-M10 (an estimate of market entry, not a verified launch date); reliability=usable; flags=none. |  |  |  |  |  |
| E011 | first_observed_sale | agent | P0120: first observed sale 2022-M04 (an estimate of market entry, not a verified launch date); reliability=unreliable; flags=coverage_expansion_month,no_visible_ramp,positioning_doc_precedes_first_sale. |  |  |  |  |  |
| E012 | search_product_docs | agent | 55 documents match ['battery', 'hours', 'endurance', 'charger'] (segment=Premium Thin & Light); returned 25. |  |  |  |  |  |
| E013 | first_observed_sale | agent | P0050: first observed sale 2023-M11 (an estimate of market entry, not a verified launch date); reliability=usable; flags=none. |  |  |  |  |  |
| E014 | define_cohort | agent | Cohort for P0113: 15 Premium Thin & Light models with first observed sale within +/-6 months and early ASP within +/-30%. |  |  |  |  |  |
| E015 | price_volume_pattern | agent | P0113: no price-and-volume pattern at thresholds (ASP -12%, units +30%). |  |  |  |  |  |
| E016 | search_product_docs | agent | 1 documents match ['all-day battery', 'days of battery', 'battery that lasts'] (segment=ALL); returned 1. |  |  |  |  |  |
| E017 | launch_trajectory | agent | P0113: mean segment share 18.09% over first 12 months since first observed sale vs cohort median 3.88% (rank 1 of 15; prediction-interval p=0.004, two-sided). | 0.004 | 0.007 | 0.016 | confirmatory | sales_confirmatory |
| E018 | complaint_comparison | agent | P0113: battery complaint rate 3.2% [95% CI 2.7%-3.7%] vs cohort median 9.0% across 14 products in the same months (product-level p=0.007, less); lower_than_cohort. | 0.007 | 0.013 | 0.016 | confirmatory | complaints_confirmatory |
| E019 | price_volume_pattern | agent | P0050: 2 month(s) with observed price-and-volume pattern (promotion not confirmed): 2024-M02,2024-M03. |  |  |  |  |  |
| E020 | define_cohort | agent | Cohort for P0050: 15 Premium Thin & Light models with first observed sale within +/-6 months and early ASP within +/-30%. |  |  |  |  |  |
| E021 | launch_trajectory | agent | P0050: mean segment share 5.66% over first 12 months since first observed sale vs cohort median 3.88% (rank 5 of 15; prediction-interval p=0.467, two-sided). | 0.467 | 0.467 | 0.697 | confirmatory | sales_confirmatory |
| E022 | launch_trajectory | agent | P0050: mean segment share 5.05% over first 10 months since first observed sale vs cohort median 3.88% (rank 5 of 15; prediction-interval p=0.640, two-sided). | 0.640 | 0.640 | 0.720 | sensitivity | sensitivity_exploratory |
| E023 | complaint_comparison | agent | P0050: battery complaint rate 8.8% [95% CI 7.5%-10.4%] vs cohort median 8.7% across 14 products in the same months (product-level p=0.542, less); no_detectable_difference. | 0.542 | 0.542 | 0.697 | confirmatory | complaints_confirmatory |
| E024 | rubric | code | Signal grade for battery in Premium Thin & Light: Moderate. |  |  |  |  |  |
| E025 | rubric | code | P0113: grade Moderate (sales: supported; complaints: lower_than_cohort; first sale: usable; grade under pooled FDR: Moderate). |  |  |  |  |  |
| E026 | rubric | code | P0050: grade Not supported (sales: not_supported; complaints: no_detectable_difference; first sale: usable; grade under pooled FDR: Not supported). |  |  |  |  |  |
| E027 | rubric | code | P0120: grade Insufficient (sales: not_tested; complaints: not_tested; first sale: unreliable; grade under pooled FDR: Insufficient). |  |  |  |  |  |

## Run metadata

- Models: {'main': 'claude-sonnet-5-5', 'small': 'claude-haiku-5-5'}
- LLM calls: 19; input tokens: 120324; output tokens: 13884
- Tests run: 9 (Benjamini-Hochberg within each family; pooled q shown alongside)
- Cost: $0.3386 (list prices; limits: {'max_calls': 60, 'max_cost_usd': 3.0, 'effort': {'main': 'medium', 'small': 'low'}, 'max_tool_calls': 24})
- Data file hashes: {"products.csv": "0b4ecc336b0d425486c24598f7ff787f095ceac95b16ae823306e4f289aa806a", "sellout_monthly.csv": "71fc64ea4921f4bbe786f5a13396cff9b1841624dcdfa8b226fbd6745a624b7f", "product_docs.csv": "b19357a8eac27b81b7b93e7a60f05b186bb936ff3facd6db90ee372f4d461f8b", "signal_counts.csv": "52964dbb96d016c1b7f4dd298c4ab01534805fa7ae1d86b2cb1aac5ce6cda7f7"}
