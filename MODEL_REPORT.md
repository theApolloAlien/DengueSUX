# National two-week model evaluation

Selected model: **Weather + trend gradient boosting**. In the 2022 replay, it was off by 83.2 people a week on average; the four-week-average baseline was off by 172.4.

## Selection and evaluation protocol

- Three fixed candidates: four-week average, Ridge residual (alpha 100), and seeded GradientBoosting residual with the parameters saved in model.json.
- 39 expanding four-week validation folds cover 2019–2021 (155 predictions), including the 2019 and 2020 outbreaks. A fold trains only on target weeks completed before its first issue date. The last validation targets must also be observable before the first 2022 issue.
- The predeclared rule selects the lowest mean of the three annual validation mean absolute errors, weighting 2019, 2020 and 2021 equally, with exact ties preferring baseline, then Ridge, then boosting. There is no bootstrap significance rule and no 2022 tuning.
- Selection is locked before refitting on 249 observed pre-evaluation targets. Only the selected model and baseline are evaluated on the 52 2022 weeks. Rejected candidates are not evaluated on 2022.
- **2022 is a reused evaluation year:** results were viewed in earlier prototype revisions. This is not a newly unseen test set. Selection in this revision uses only 2019–2021.

| Model | 2019 error | 2020 error | 2021 error | Equal-year error |
| --- | ---: | ---: | ---: | ---: |
| Four-week average | 84.2 | 197.6 | 21.5 | 101.1 |
| Weather + trend ridge | 65.5 | 105.4 | 34.9 | 68.6 |
| Weather + trend gradient boosting | 63.6 | 107.5 | 17.3 | 62.8 |

Errors are mean absolute differences in weekly people with dengue. Classification accuracy is 94.2% for the selected model and 92.3% for the baseline. Low/Medium/High cutoffs (68.0, 230.3) are thirds of observed target counts available before evaluation, not official outbreak thresholds. Each validation fold computes its own cutoffs from its training rows only.

## Peak warning in the 2022 replay

Observed peak: **1567 people**, week starting **2022-05-22**.

- Selected model: first High issued 2022-03-06, 11 weeks before peak.
- Four-week average: first High issued 2022-03-13, 10 weeks before peak.

Lead time uses the date a forecast would be issued, measured to the start of the observed peak week. If the first replay issue is already High, its earlier crossing is unobserved and only a lower bound is reported. This single-year descriptive measure is not a validated outbreak detection rate. The t+2 target starts one week after issue and ends almost two weeks after issue. Historical issue dates assume preceding-week case data is immediately available; actual publication delays are unknown.

## Explanations and reproducibility

The exported predictor, metrics, prediction labels and explanations all refer to the same selected model. The four groups are Recent cases, Time of year, Rain, and Heat (temperature plus humidity). Missing-value indicators stay in their parent groups. Ridge uses exact additive linear contributions; boosting uses TreeSHAP; the baseline only attributes its four-week average to Recent cases. Contributions sum to the prediction before a nonnegative floor. These are associations, not causal effects.

No synthetic case outcomes are used. Missing weather remains missing in observations and exported features; the estimator substitutes training-set medians internally and retains missingness indicators. National case labels end 2026-10-03. A current national outlook is published only when the label freshness gate passes; its unreported outcomes cannot yet be evaluated. There are no historical local outcomes for local error measurement. MLflow logs the complete selected replay predictor, including its persistence component and zero floor, with all evaluation details. Logging failures stop the run.

MLflow run: `580e033eca104e8a8bd27d8b56ab2ecb`.

## Missing weather inputs

Share of prediction weeks with at least one missing weather lag supplied to the selected learned estimator. Its imputer uses training-set medians internally; observations and exported features remain missing. The four-week-average baseline does not use weather.

| Forecast period | Weeks | Weeks with any imputed weather input | Share of weeks |
| --- | ---: | ---: | ---: |
| 2022 replay | 52 | 13 | 25.0% |
| 2023+ retrospective evaluation | 196 | 74 | 37.8% |
| Live outlook | 2 | 0 | 0.0% |

## Retrospective evaluation, 2023 onward

Retrospective evaluation of the fixed 2019–2021 selection and hyperparameters; refitted once a year on labels ending before that year's first assumed issue date. Later years are excluded from recipe selection. Revised workbook counts and immediate publication are assumed; these are not forecasts recorded in real time.

Across **196 weeks** (2023-01-01 to 2026-10-03), the forecast was off by **28.7 people a week** against **31.9** for the four-week average (10% lower). The 80% range contained the reported count in **76%** of weeks.

| Year | Weeks | Forecast error | Simple-average error | 80% range coverage | Peak week (people) |
| --- | ---: | ---: | ---: | ---: | --- |
| 2023 | 53 | 39.3 | 48.5 | 75% | 2023-09-24 (342) |
| 2024 | 52 | 42.8 | 45.1 | 81% | 2024-02-04 (515) |
| 2025 | 52 | 15.1 | 13.2 | 75% | 2025-06-08 (125) |
| 2026 | 39 | 13.8 | 16.7 | 69% | 2026-06-28 (130) |

## Proper scoring and recalibrated ranges (2023 onward)

| Range method | 80% coverage | Mean width | Interval score (lower is better) | Pinball 10% | Pinball 90% |
| --- | ---: | ---: | ---: | ---: | ---: |
| Fixed 2019–2021 | 76% | 94.7 | 131.9 | 5.32 | 7.87 |
| Rolling 104 weeks | 73% | 90.3 | 127.9 | 5.27 | 7.52 |
| Adaptive conformal (live) | 79% | 98.2 | 130.5 | 5.35 | 7.70 |

Quantiles of the last 104 weeks of out-of-sample log-ratio errors observable before each issue date (2019–2021 folds, 2022 replay, earlier 2023+ weeks); fixed 2019–2021 range when fewer than 26.
Adaptive conformal inference: the rolling window's quantile level moves by 0.05 after each observed outcome (miss widens, hit narrows), aiming at 80% long-run coverage.
Step size compared after seeing 2023+ outcomes; the chosen step's 2023+ coverage is therefore optimistic.

| Adaptive step | Coverage | Interval score |
| ---: | ---: | ---: |
| 0.005 | 75.5% | 128.0 |
| 0.01 | 76.0% | 128.6 |
| 0.02 | 76.5% | 131.5 |
| 0.05 | 78.6% | 130.5 |

| Point forecast | Mean absolute error |
| --- | ---: |
| Selected model | 28.7 |
| Four-week average | 31.9 |
| Seasonal naive (same week last year, 196 weeks) | 213.1 |

Diebold–Mariano test against the four-week average (absolute error, Newey–West, horizon 2): statistic -1.14, p = 0.256 over 196 weeks. Against seasonal naive: statistic -6.99, p = 0.000.
A negative statistic favours the forecast. A p-value above 0.05 means the difference could be chance at this sample size.


## Ranges

Empirical quantiles of log((actual+10)/(forecast+10)) from the selected model's validation folds, 155 predictions. Coverage in the 2022 replay: 79%. The range describes past forecast error, not a guarantee.

## Live forecast

Issued from the week ending 2026-10-03 (2026-W39, 71 people reported). For the week of **2026-10-11**: about **69 people** (80% range 43–96).

## Does weather help? (MLflow child runs)

| Feature set | Features | 2019–2021 equal-year error | 2023+ error |
| --- | ---: | ---: | ---: |
| Cases, trend, season + weather | 37 | 62.8 | 28.7 |
| Cases, trend, season only | 13 | 66.8 | 28.5 |

Same boosting recipe and folds; only the inputs differ. Selection still uses the locked rule above.
