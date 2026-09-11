# WeatherPredict — Architecture

**EarthScape Climate Agency** climate-data intelligence platform.

## 1. System overview

Streamlit (`app.py` + `pages/`) talks only to MongoDB and local files.

```
Uploads / simulator → weatherpredict.ingestion / realtime
                         ↓
                      MongoDB
                         ↓
         batch.pipeline  ·  ml  ·  console reads
                         ↓
                   Streamlit pages
                         ↓
              notifications + support
```

## 2. Packages

| Module | Responsibility |
|--------|----------------|
| `weatherpredict.auth` | Users, bcrypt, RBAC |
| `weatherpredict.scoping` | Region-level data access |
| `weatherpredict.ingestion` / `validators` | File ingest |
| `weatherpredict.batch` | Synthetic data, pandas adapter, Hadoop seam |
| `weatherpredict.realtime` | `emit_sensor_tick`, `unified_series` |
| `weatherpredict.ml` | `predict_trend`, anomaly detection, correlations |
| `weatherpredict.notifications` | Rules + inbox |
| `weatherpredict.support` | Tickets / feedback |
| `weatherpredict.console` | Aggregates for dashboards |

## 3. Mongo collections

Climate (never wiped by seed unless `--with-data` with `clear_existing`): `weather_station_records`, `sensor_readings`, `satellite_imagery`, `anomalies`, `ml_predictions`, `batch_aggregates`.

Operational: `users`, `notifications`, `alert_rules`, `support_tickets`, `feedback`, `pipeline_runs`, `ingestion_jobs`, `ml_artifacts`.

Indexes are created at app start (`ensure_indexes`), including unique `anomalies (region, metric, observed_at)` and `users.username`.

## 4. Real-time

No Django Channels. `emit_sensor_tick` writes `source: realtime` documents. The Live page uses `st.fragment` to re-read `unified_series` (batch window + live sensors).

## 5. Batch / Hadoop seam

`LocalAdapter` implements partition / clean / reduce_aggregate / write_partitions in pandas. `HadoopAdapter` is the same contract; `submit_mapreduce` returns `not_configured` until a cluster exists.

## 6. ML

Time-based split, lag features only, naive lag-1 baseline. Anomaly IsolationForest + seasonal z-score; proxy labels `|z|>3`. Retrain versions artifacts (`_next_version`).

## 7. Auth & scoping

Login before any page body. Analysts cannot call `manage_users`, `generate_data`, `run_batch`, `train_ml`, `configure_alerts`. Reads go through `constrain_region`.
