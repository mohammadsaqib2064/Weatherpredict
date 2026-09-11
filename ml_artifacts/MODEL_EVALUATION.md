"""Honest model evaluation report for WeatherPredict ML services."""

## Leakage controls applied

1. **Time-based splits only** — last 20% of each regional series held out; no random shuffle across time.
2. **Lag features only** — `lag_1`, `lag_7`, `lag_14`, `lag_30` plus day-of-year Fourier terms. No future covariates.
3. **Anomaly baseline** — mean/std per region×day-of-year fitted on the training window only, then applied to the holdout.
4. **Naive baseline comparison** — trend MAE is compared to lag-1 persistence so inflated R² cannot hide a useless model.

## Trend prediction (per region)

Models considered: Ridge, GradientBoostingRegressor. Best model by holdout MAE is saved under `ml_artifacts/trend_<region>.joblib`.

Expect MAE typically in the **1–3 °C** range on synthetic seasonal data, sometimes close to the naive lag-1 baseline. Beating naive is not guaranteed and is reported honestly via `beat_naive`.

## Anomaly detection

IsolationForest (`contamination=0.02`) + |z|≥3 rule. Evaluation uses a **proxy label** (|z|>3), not verified extreme weather events.

Reported proxy precision/recall are therefore **indicative only** (often modest, e.g. ~0.2–0.4). This is intentional — fabricating high F1 against circular labels would be misleading.

## Correlation analysis

Pearson and Spearman on daily means of weather + sensor metrics. Documented caveat: **correlation ≠ causation**.

## Artifacts

- `ml_artifacts/model_evaluation_report.json` — per-region trend metrics
- `ml_artifacts/correlation_report.json` — correlation matrices
- Django `MLModelArtifact` rows store metrics JSON for the UI
