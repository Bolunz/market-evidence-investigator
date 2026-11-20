# Scripted-policy evaluation (no LLM)

Scored from structured outputs against isolated answer keys.

Planted effect on product A (sales multiplier / complaint multiplier): strong 4.0/0.35, moderate 2.0/0.60, small 1.4/0.80, null 1.0/1.0, contradictory 4.0/1.0.

### Appropriateness (the primary measure)

| Check | strong | moderate | small | null | contradictory |
|---|---|---|---|---|---|
| **A overclaimed** (grade above what the truth justifies) | 0/20 | 0/20 | 0/20 | 0/20 | 0/20 |
| A justified ceiling | Moderate | Moderate | Moderate | Not supported | Weak |
| A grade distribution | Moderate: 20 | Moderate: 1, Weak: 10, Not supported: 9 | Not supported: 20 | Not supported: 20 | Weak: 20 |
| A sales advantage detected (power where true) | 20/20 | 4/20 | 0/20 | 0/20 | 20/20 |
| A lower complaints detected (power where true) | 20/20 | 8/20 | 0/20 | 0/20 | 0/20 |
| Contradiction flagged (sales without fewer complaints) | 0/20 | 3/20 | 0/20 | 0/20 | 20/20 |
| A grade changes under pooled FDR (all tests one family) | 0/20 | 1/20 | 0/20 | 0/20 | 0/20 |

### Traps and integrity

| Check | strong | moderate | small | null | contradictory |
|---|---|---|---|---|---|
| Direct-response path / correct segment | 20/20 | 20/20 | 20/20 | 20/20 | 20/20 |
| A and B identified as positioned | 20/20 | 20/20 | 20/20 | 20/20 | 20/20 |
| Other-segment product kept out of cohort | 20/20 | 20/20 | 20/20 | 20/20 | 20/20 |
| B never graded as a supported sales effect | 20/20 | 20/20 | 20/20 | 20/20 | 20/20 |
| B price-and-volume pattern reported | 20/20 | 19/20 | 19/20 | 20/20 | 20/20 |
| C first-sale artefact flagged unreliable | 20/20 | 20/20 | 20/20 | 20/20 | 20/20 |
| Ledger re-executes exactly | 20/20 | 20/20 | 20/20 | 20/20 | 20/20 |
| Claims flagged by validator | 0 | 0 | 0 | 0 | 0 |
