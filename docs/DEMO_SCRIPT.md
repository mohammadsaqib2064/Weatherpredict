# Demo / manual test script

Record a browser session of the **Streamlit** app with the URL bar visible (http://127.0.0.1:8501/).

## Setup

```powershell
python -m weatherpredict.seed --with-data --years 2 --train
streamlit run app.py
```

## Beats

1. **Login (Administrator)** — `admin` / `AdminPass123!`. Show the operations console (not Django `/admin/`).
2. **Users** — Analyst has region focus Pacific NW. Optionally create a throwaway Analyst.
3. **Ingest** — upload `data/test_data/weather_sample.csv`.
4. **Pipelines** — show recent batch/ML runs and duration seconds.
5. **Alert rules** — edit/toggle a rule; test a high temperature; show a notification.
6. **Sign out → Analyst** — `analyst` / `AnalystPass123!`. Workspace only shows Pacific NW. Attempting another region is impossible in the UI.
7. **Trends** — observed history + dotted forecast + MAE vs naive baseline.
8. **Anomalies** — chronological z-score bars, severity mix, table. Do **not** claim re-run as a page-load side effect.
9. **Correlations** — navy–sand–coral heatmap.
10. **Live** — emit tick; auto-refresh fragment; merged batch + realtime series.
11. **Support** — submit a ticket as Analyst; resolve it as Administrator.

Do not open Django `/admin/` — it does not exist in this build.
