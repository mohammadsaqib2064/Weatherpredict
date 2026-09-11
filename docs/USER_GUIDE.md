# WeatherPredict — User Guide

EarthScape Climate Agency operators and analysts.

## Roles

- **Administrator** — system overview, user provisioning, alert rules, batch/ML triggers, all support tickets.
- **Analyst** — explore trends, anomalies, correlations, ingest data, live merge view, own tickets/notifications.

## Sign in

1. Open the app URL.
2. Enter credentials (see README for demo accounts).
3. You land on the Admin overview or Analyst workspace based on role.

## Ingest data

1. Go to **Ingest**.
2. Choose type: weather station, sensor, or satellite metadata.
3. Upload `.csv`, `.json`, or `.xlsx`.
4. Review job status (imported / skipped). Missing optional fields are retained with flags; critical fields must be present.

### Weather CSV columns

`station_id,region,observed_at,temp_c,precip_mm,humidity_pct,wind_ms,pressure_hpa,lat,lon,name`

## Live sensors

1. Open **Live**.
2. Pick region/metric.
3. Click **Emit sensor tick** to simulate near-real-time readings.
4. Chart merges recent batch weather with realtime sensors.

## Analytics

- **Trends** — 30-day temperature forecast with uncertainty band.
- **Anomalies** — flagged extremes vs seasonal baseline (coral severity labels).
- **Correlations** — Pearson heatmap of daily weather/sensor variables.

Administrators retrain models from Analytics or the Admin overview (**Train ML**).

## Alerts

- Inbox lists threshold and anomaly notifications.
- Admins manage rules under **Alerts → Alert rules** (metric, operator, threshold, severity).

## Support

- Submit tickets under **Support**.
- Admins update status and notes.
- Optional product feedback form with 1–5 rating.

## Pipelines

Admins can generate synthetic climate history, run batch clean/aggregate, and inspect run history under **Data & pipeline management**.

## Tutorial (first hour)

1. Sign in as `admin` / `AdminPass123!`.
2. Confirm the Operations console shows Mongo connected and weather/sensor counts.
3. Open **Data & pipeline management** — generate data if counts are zero, then train ML.
4. Open **User management** — confirm the Analyst has region focus `pacific_nw`.
5. Sign out, sign in as `analyst` / `AnalystPass123!`.
6. Workspace, Trends, Anomalies and Correlations should only offer Pacific NW.
7. Open **Live**, emit a sensor tick, confirm the merged chart updates.
8. Sign back in as admin, open **Alert rules**, test a value above threshold, then check **Notifications**.

## FAQ

**Why can't the Analyst see Southwest data?**  
Accounts are scoped by `region_focus`. That is required access control, not a bug.

**Where is Django admin / `/admin/`?**  
Removed. The product Administrator console is in Streamlit.

**Do I need Hadoop installed?**  
No. Local pandas is the demo adapter. Hadoop is a documented production swap.

**Charts look empty.**  
Train models (`python -m weatherpredict.seed --with-data --train`) and emit a live tick.

**How do I backup?**  
`python -m weatherpredict.backup` — schedule it nightly.

**Is there a health URL?**  
Streamlit exposes `/_stcore/health`. App-level JSON: `python -m weatherpredict.health`.

**Can two people share one Streamlit server with load balancing?**  
Only with sticky sessions. Session state is per process.

**What test files can I upload?**  
`data/test_data/weather_sample.csv`, `sensor_sample.csv`, `satellite_sample.json`.

**Why are anomaly scores not 99% accurate?**  
Labels are a proxy (`|z|>3`), documented in `ml_artifacts/MODEL_EVALUATION.md`.

**Where do I change alert thresholds?**  
Administrator → Alert rules. Analysts cannot edit rules.

**How do I record the demo video?**  
Follow `docs/DEMO_SCRIPT.md` in a browser with the address bar visible.

