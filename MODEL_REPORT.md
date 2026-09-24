# National two-week model evaluation

Selected model: **Weather + trend gradient boosting**. Average absolute weekly error in the 2022 replay: **83.2 people**, versus **172.4** for the four-week average. Error is 51.7% lower. National statistical-band accuracy is **94.2%**, versus **92.3%**.

## Selection locked before evaluation

39 expanding four-week folds cover 155 validation targets across **2019–2021**, including outbreak years. Each fold trains only on target weeks completed before its first issue date. The final validation targets must also be observable before the first 2022 issue.

The fixed candidates are the four-week average, Ridge residual (alpha 100), and seeded gradient boosting residual (120 estimators, learning rate .03, depth 2, minimum leaf 4, subsample .9, Huber loss). Seed: 20260924. The selection rule is the lowest mean of the three annual validation errors, with each year weighted equally. Exact ties prefer baseline, then Ridge, then boosting. No paired-bootstrap tie rule is used in this revision.

| Model | 2019 error | 2020 error | 2021 error | Equal-year error |
| --- | ---: | ---: | ---: | ---: |
| Four-week average | 84.2 | 197.6 | 21.5 | 101.1 |
| Ridge residual | 65.5 | 105.4 | 34.9 | 68.6 |
| Gradient boosting residual | 63.6 | 107.5 | 17.3 | 62.8 |

After selection, the winner was refitted on 249 observable pre-evaluation targets and evaluated on all 52 weeks of 2022 alongside the baseline. Rejected candidates were not evaluated by this run. **2022 is a reused evaluation year** already viewed during earlier development, not newly unseen data. It was excluded from selection in this revision. An overlapping task later ran another selector; the delivered revision preserves this originally locked run and its exact predictions rather than choosing between 2022 results.

## Advance warning before the peak

Observed peak: **1,567 people**, week starting **22 May 2022**.

- Selected forecast first High issue: **6 March 2022**, **11 weeks before peak**.
- Simple average first High issue: **13 March 2022**, **10 weeks before peak**.

The selected forecast crossed High one week earlier. High means at least 230.3 people, based on the upper third of pre-evaluation training targets; it is not an official outbreak threshold. Low is below 68.0. Validation folds use only their own training labels for thresholds.

Lead time runs from forecast issue to the beginning of the observed peak week. It is a descriptive warning measure for one replay, not proof of predicting the peak date or a validated outbreak-detection rate. If the first replay forecast is already High, the implementation reports only a lower bound; an absent crossing produces no claimed warning.

## Horizon, missing data and explanations

The target is the national weekly count at t+2, a Sunday–Saturday week, not the sum of two weeks. Features use observations through week t. Issuance is assumed on the following Sunday; the target starts one week after issue and ends almost two weeks after issue. Actual report publication delays are unknown.

The complete exported predictor includes the latest observed count, learned residual and nonnegative floor. Its name, metrics, predictions, risk bands and explanations refer to the same selected model. TreeSHAP contributions plus the training background add to each prediction before the zero floor. Four groups are **Recent cases**, **Time of year**, **Rain**, **Heat** (temperature and humidity). Missing-value indicators stay in their parent group. These are associations, not causal effects.

Missing weather remains missing until training-only median imputation. No synthetic outcomes are used. National labels end 31 December 2022, so this is not a current national forecast. No historical planning-area outcomes exist here, so no local accuracy is claimed.

MLflow stores the complete predictor and evaluation evidence. Reloading it reproduced all 52 exported predictions exactly. Logging failures stop the pipeline. Run: `ef02042b46d74bde9e46c60962f71e1c`.
