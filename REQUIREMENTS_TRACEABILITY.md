# Requirements Traceability — WeatherPredict / EarthScape Climate Agency

**Authoritative source:** `c:\Users\MohammadSaqib\Downloads\FqTAQX.docx` (Aptech eProject brief).
**Analysed:** 2026-09-11, against commit `4875da3` ("Baseline: Django implementation before Streamlit migration").
**Analysis method:** every "Implemented" claim below was verified by reading the cited source file. Anything not read is marked **unverified**.

> **State-of-repo caveat.** At the time of analysis the Streamlit migration had **not yet landed in code** — the working tree is still the Django implementation (only two untracked scratch files differ from `HEAD`). All evidence therefore cites the Django modules. Statuses are written about the **capability**, not the framework, so they survive the migration; where the migration specifically changes the verdict, that is called out inline under **Streamlit impact**.

---

## Scorecard

| Group | Count | Implemented | Partial | Substituted | Missing |
|---|---:|---:|---:|---:|---:|
| Functional requirements | 20 | 9 | 8 | 3 | 0 |
| Non-functional requirements | 13 | 2 | 5 | 0 | 6 |
| Project deliverables | 9 | 3 | 5 | 0 | 1 |
| **Total (contractual)** | **42** | **14** | **18** | **3** | **7** |
| Hardware/Software environment items | 12 | — | — | — | — |
| **Total enumerated** | **54** | | | | |

Fully satisfied: **14 / 42 = 33%**. Nothing further is claimed.

The doc lists **Performance** and **Performance Monitoring** as two separate NFR sections with **verbatim identical** body text. They are counted once (as NFR-1.1 / NFR-1.2) and the duplication is noted rather than double-counted.

---

# PART A — Document requirement → implementation

## A1. Functional Requirements

### FR-1 User Authentication and Authorization

#### FR-1.1 — "Implement a secure authentication system for users with different roles (e.g., administrators, analysts)."
**Status: Implemented**

Evidence:
- `accounts/models.py` — `Role` (`ADMINISTRATOR`, `ANALYST`) and `UserProfile.role`; `ensure_profile` post-save receiver guarantees every `User` has a profile.
- `accounts/views.py::login_view` — uses `django.contrib.auth.authenticate` (PBKDF2 hashing), rejects inactive accounts explicitly.
- `config/settings/base.py` — four `AUTH_PASSWORD_VALIDATORS`, `SESSION_COOKIE_HTTPONLY`, CSRF middleware, `X_FRAME_OPTIONS = "DENY"`.
- `accounts/views.py::manage_users`, `toggle_user_active`, `set_user_role` — administrator-only user provisioning, activation and role assignment; both guard against self-demotion/self-deactivation.
- `tests/test_core.py::test_login_and_role_redirect`, `::test_analyst_cannot_manage_users`, `::test_admin_user_toggle`.

**Streamlit impact — this is the highest-risk item in the migration.** Streamlit has no request/response layer, no route table, no session middleware, no CSRF, and no decorator equivalent to `@login_required`. Every guarantee above currently comes from Django. Re-implementing this in Streamlit means: a login gate that runs before any page body renders, a server-side session store (Streamlit's `st.session_state` is per-browser-session in-process and is *not* a security boundary on its own), password hashing that is no longer free (Django's PBKDF2 hasher goes away — use `passlib`/`bcrypt` or `hashlib.pbkdf2_hmac` explicitly), and a per-page authorisation check because Streamlit's multipage router will happily serve `pages/admin_console.py` to anyone who types the URL unless the page itself checks first.

#### FR-1.2 — "Define access controls to restrict **data access** based on user roles and responsibilities."
**Status: Partially implemented**

What exists is **route-level authorisation**, plus **record-level ownership** on two collections:
- `accounts/permissions.py::admin_required`, `role_required`, `is_administrator`, `is_analyst` — page gates.
- `support/views.py::ticket_list` — non-admins get `SupportTicket.objects.filter(created_by=request.user)`; admins get all. This is a real data restriction.
- `notifications/views.py::inbox` — `request.user.notifications` only.
- `analytics/views.py::train_view`, `dashboard/views.py::trigger_batch|trigger_ml|trigger_synthetic`, `batch/views.py::run_batch|run_synthetic`, `notifications/views.py::manage_rules` — all `@admin_required`.

**What is absent:** the *climate data itself* is not restricted at all. An Analyst can read every region's weather records, sensor readings, satellite metadata, anomalies and correlations. `UserProfile.region_focus` (`accounts/models.py:17`) exists, is settable in `accounts/views.py::UserCreateForm`, is seeded (`seed_demo.py:38`) and is displayed (`templates/accounts/manage_users.html:46`, `dashboard/services.py:126`) — but it is **never used as a query filter anywhere**. Verified by exhaustive search: the only occurrences are the model field, the form field, the admin `list_display`, the seed assignment and two display sites.

**Smallest correct fix:** make `region_focus` load-bearing. Add a single scoping helper (e.g. `accounts/scoping.py::allowed_regions(user) -> list[str] | None`, returning `None` for Administrator and `[profile.region_focus]` for Analyst) and apply it as a mandatory `{"region": {"$in": ...}}` clause inside the Mongo read helpers — `analytics/services.py::_weather_frame`, `::stored_anomalies`, `::get_correlations`, `realtime/services.py::unified_series`, `dashboard/services.py::_build_region_temp_summary` and `::recent_anomalies_preview`. Filtering in one shared layer rather than per-view is what makes this defensible.

---

### FR-2 Data Ingestion

#### FR-2.1 — "Ingestion of diverse climate-related datasets, including satellite imagery, weather station records, and environmental sensor data."
**Status: Partially implemented**

- Weather station records: **real**. `dataingestion/validators.py::normalize_weather` (station_id, region, observed_at, temp_c, precip_mm, humidity_pct, wind_ms, pressure_hpa, lat/lon), written to Mongo `weather_station_records` by `dataingestion/services.py::run_ingestion`.
- Environmental sensor data: **real**. `::normalize_sensor` (sensor_id, metric, value, unit, quality) → `sensor_readings`.
- Satellite: **metadata catalogue only**. `::normalize_satellite` accepts `scene_id`, `satellite`, `acquired_at`, `cloud_cover_pct`, `bands`, `bbox`, `storage_uri` and upserts into `satellite_imagery` by `scene_id`. **No raster is ever read.** `config/settings/base.py:127` sets `ALLOWED_UPLOAD_EXTENSIONS = {".csv", ".json", ".xlsx"}`, which excludes GeoTIFF/NetCDF/HDF5 outright; `batch/synthetic.py` fabricates `storage_uri` values like `local://data/synthetic/<region>/<date>.tif` that point at files which do not exist. `Pillow` is in `requirements.txt` but is imported nowhere.

**Smallest correct fix:** this is defensible as a *scene catalogue* rather than an imagery pipeline, but it must stop implying otherwise. Either (a) add a `.tif` branch to `ALLOWED_UPLOAD_EXTENSIONS` and `validators.load_records` that opens the raster with `rasterio`/`Pillow`, records real width/height/band count/CRS, and stores the file under `data/raw/`; or (b) rename the capability to "satellite scene metadata" in the README, architecture doc and UI, remove the fake `.tif` URIs from the generator, and record the limitation as an explicit assumption. Option (b) is smaller and honest; option (a) is what the requirement literally asks for.

#### FR-2.2 — "Mechanisms to handle both historical and real-time data sources."
**Status: Substituted (local equivalent)**

- Historical: `batch/synthetic.py::generate_synthetic_dataset(years=N)` produces a deterministic (`seed=42`) multi-year daily corpus across 5 regions — weather, three sensor metrics, weekly satellite scenes. Plus arbitrary-history file upload via FR-2.1.
- Real-time: `realtime/services.py::emit_sensor_tick(n_readings=10)` writes `sensor_readings` with `source="realtime"` and evaluates alert rules per reading; exposed at `realtime/views.py::tick_api` (`POST /realtime/api/tick/`) and via the Channels consumer.

**Why "Substituted":** the real-time path has **no autonomous producer**. Every tick is triggered by a human clicking a button or by an explicit HTTP POST — there is no scheduler, background thread, message queue or polling collector. This is a legitimate local stand-in for a live agency feed, but it must be documented as one rather than presented as live ingestion.

#### FR-2.3 — "Ensure compatibility with common data formats used in climate science."
**Status: Partially implemented**

Supported: `.csv` (`csv.DictReader`), `.json` (list or `{"records": [...]}`), `.xlsx` (`openpyxl`) — see `dataingestion/validators.py::load_records`. These are generic tabular formats, not climate-science formats. The formats the requirement is actually pointing at — **NetCDF (`.nc`), GRIB/GRIB2, HDF5, GeoTIFF**, and station-exchange formats such as GHCN-Daily `.dly` or BUFR — are all unsupported.

**Smallest correct fix:** add one genuine climate format rather than gesturing at all of them. NetCDF is the highest-value single addition: add `xarray`/`netCDF4` to requirements, add `.nc` to `ALLOWED_UPLOAD_EXTENSIONS`, and add a `load_records` branch that opens the dataset, reads the CF `time`/`lat`/`lon` coordinates and flattens the requested variable to the existing weather-record shape. Then state in the README exactly which formats are and are not supported.

---

### FR-3 Data Storage

#### FR-3.1 — "Utilize the Hadoop Distributed File System (HDFS) for scalable and fault-tolerant storage of large climate datasets."
**Status: Substituted (local equivalent) — no HDFS exists**

`batch/adapters/base.py::HadoopAdapter` declares `hdfs_raw = "hdfs://namenode:8020/weatherpredict/raw"` and `hdfs_processed = .../processed`, but these are **strings only**. There is no HDFS client library in `requirements.txt` (no `hdfs`, `pyarrow`, `snakebite`, `pywebhdfs`), no filesystem handle, and no code path that reads or writes an `hdfs://` URI. Every `HadoopAdapter` method delegates straight to `self._local` (lines 137–144). Actual persistence is MongoDB (`config/mongo.py`) plus local CSV under `data/processed/<timestamp>/`.

This requirement **cannot be met without a real Hadoop cluster**, which is out of reach for a single Windows workstation. It must be handled by explicit documented substitution, not silently.

**What must be documented (exact content):** that storage is MongoDB + local filesystem; that `BatchAdapter` (`partition` / `clean` / `reduce_aggregate` / `write_partitions`) is the seam at which HDFS plugs in; the exact HDFS layout that would be used (`/weatherpredict/raw/<datatype>/dt=<date>/`, `/weatherpredict/processed/<datatype>/region=<r>/`); and the concrete swap (implement `HadoopAdapter.write_partitions` against `pyarrow.fs.HadoopFileSystem`, set `HDFS_NAMENODE`, select `--adapter hadoop`).

#### FR-3.2 — "Implement data partitioning and organization strategies to optimize retrieval and processing."
**Status: Partially implemented**

Partitioning is real and working:
- `batch/adapters/base.py::LocalFallbackAdapter.partition` — groups by `["region"]` for weather and `["region", "metric"]` for sensors.
- `::write_partitions` — writes `part_<key>.csv` per partition, with filename sanitisation for Windows-illegal characters.
- `batch/services.py::run_batch_pipeline` — organises output under `data/processed/<YYYYMMDD_HHMMSS>/{weather,sensor}/`, plus a run-level `aggregates.csv`. Verified against the four run directories present on disk (70+ partition files).
- Aggregates upserted idempotently on `(region, period, source)` into `batch_aggregates`.

**What is absent — the retrieval half.** `config/mongo.py::ensure_indexes()` defines nine indexes (compound `region+observed_at`, `station_id+observed_at`, `sensor_id`, `scene_id` unique, and the `anomaly_identity_unique` compound unique index) — and **is never called anywhere in the codebase**. Verified: the identifier appears exactly once, at its own `def`. No app config `ready()`, no management command, no startup hook invokes it. So in a fresh deployment none of these indexes exist: every region query is a collection scan, and the `detect_anomalies` upsert dedup has no unique constraint backing it under concurrency.

**Smallest correct fix:** call `ensure_indexes()` once at application start (currently: an `AppConfig.ready()`; after migration: at the top of the Streamlit entrypoint behind an `@st.cache_resource` so it runs once per process).

---

### FR-4 Data Processing

#### FR-4.1 — "Implement Hadoop MapReduce jobs for parallel processing of climate data across distributed nodes."
**Status: Substituted (local equivalent) — no MapReduce, no parallelism, no distribution**

The *shape* of map/reduce is present and is a genuine design decision, not a veneer: `BatchAdapter.partition` is the map-side split, `reduce_aggregate` is the reduce-side rollup, and `batch/services.py::run_batch_pipeline` drives clean → partition → write → reduce. But execution is **single-process pandas**. `HadoopAdapter.submit_mapreduce` (`batch/adapters/base.py:147`) returns `{"status": "not_configured", "message": "Hadoop cluster not configured..."}` and submits nothing. There is no multiprocessing, no thread pool, no Spark, no YARN.

Like FR-3.1, this cannot be satisfied locally and must be a documented substitution stating: what is emulated, why (no cluster available on a single Windows host), the exact adapter method that would be replaced, and the job topology (mapper keyed on `region`/`region+metric`, reducer emitting the monthly mean/min/max/count schema already produced by `reduce_aggregate`) so the aggregate output schema is unchanged by the swap.

#### FR-4.2 — "Develop algorithms for the identification of climate patterns, anomalies, and correlations."
**Status: Implemented**

- Patterns: `analytics/services.py::_build_lag_features` — lags 1/7/14/30 plus day-of-year Fourier terms (`doy_sin`, `doy_cos`) capture the seasonal cycle; `::train_trend_models` fits Ridge and GradientBoostingRegressor per region.
- Anomalies: `::train_anomaly_model` — per-`(region, day-of-year)` mean/std baseline fitted on the training window only, plus `IsolationForest(contamination=0.02)` on `[temp_c, z_score, doy]` with a `StandardScaler`. `::detect_anomalies` flags `IsolationForest == -1` **or** `|z| >= 3`, and grades severity (high ≥4, medium ≥3).
- Correlations: `::run_correlation_analysis` — Pearson **and** Spearman matrices on daily-mean joins of weather variables with pivoted sensor metrics, per region, with a ≥30-day minimum and collision-safe `sensor_`-prefixing of overlapping column names.

#### FR-4.3 — "Include mechanisms to handle missing or incomplete data gracefully."
**Status: Implemented**

- `dataingestion/validators.py::normalize_weather` — returns `None` for fully-blank rows (skipped, not failed); accepts rows missing optional numerics and records which ones in a `missing_fields` list; only `station_id` + `observed_at` are hard requirements.
- `dataingestion/services.py::run_ingestion` — per-row try/except, accumulates up to 200 error strings, reports `records_imported` / `records_skipped`, and still marks the job `COMPLETED` when some rows imported.
- `batch/adapters/base.py::LocalFallbackAdapter.clean` — `pd.to_numeric(..., errors="coerce")`, `pd.to_datetime(..., errors="coerce")` then drop only rows with unparseable timestamps, adds a `missing_count` column, and de-duplicates on the natural key.
- `analytics/services.py::_daily_series` — `.interpolate(limit=3)` bridges short gaps without inventing long stretches.
- `::train_anomaly_model` / `::detect_anomalies` — `std` of 0 replaced with the median, `NaN` baselines back-filled, so a sparse region cannot produce infinite z-scores.

---

### FR-5 Real-time Data Processing

#### FR-5.1 — "Integrate real-time data streaming capabilities."
**Status: Partially implemented**

`realtime/consumers.py::SensorConsumer` is a genuine Django Channels `WebsocketConsumer`, wired through `realtime/routing.py` and `config/asgi.py`, with `CHANNEL_LAYERS` set to `InMemoryChannelLayer`. It authenticates on connect and handles `tick` / `unified` actions.

But it is **request/response over a socket, not a stream**: the server only ever emits in reply to a client message. There is no background producer, no `channel_layer.group_send` broadcast, and no subscription. Meanwhile the *actual* shipped path is HTTP polling — and the setting meant to switch between them, `USE_CHANNELS` (`config/settings/base.py:119`), is **never read by any code**, as is `REALTIME_POLL_SECONDS` (line 118). Both are dead configuration.

**Smallest correct fix (Streamlit target):** drop the Channels stack entirely and implement the stream with `st.fragment(run_every="5s")` on the live view, driving a producer that appends a tick and re-reads `unified_series`. That gives a genuinely self-updating view with far less machinery, and it is the only real-time mechanism Streamlit supports natively.

#### FR-5.2 — "Ensure seamless integration with batch processing for a comprehensive analysis."
**Status: Implemented**

`realtime/services.py::unified_series(region, metric, hours)` reads three sources into one time-ordered series — `weather_station_records` (batch/synthetic/upload), `sensor_readings` filtered to the metric (including `source="realtime"` ticks), and `batch_aggregates` — tagging each point with its `source` and returning per-source counts. Rendered by `realtime/views.py::live_dashboard` into `templates/realtime/live.html`. Correlation analysis (`analytics/services.py::run_correlation_analysis`) likewise joins batch weather against sensor readings that include realtime ticks, and deliberately suffixes overlapping metric names so a realtime `temp_c` sensor does not silently collide with the batch weather `temp_c`.

---

### FR-6 Machine Learning Models

#### FR-6.1 — "Develop machine learning models for predictive analysis of climate trends and impacts."
**Status: Implemented**

`analytics/services.py::train_trend_models` fits Ridge and GBR per region on lag+seasonality features, with a **time-based 80/20 split** (no shuffling), selects the lower-MAE model, and records MAE/RMSE/R² **alongside a lag-1 persistence baseline and a `beat_naive` boolean** — an unusually honest evaluation that makes it impossible to pass off a useless model as accurate. `::predict_trend` rolls the selected model forward day by day, reading each `lag_k` from the growing history (so the forecast is genuinely recursive rather than leaking future values) and attaching a ±1.96·MAE interval. Artifacts land in `ml_artifacts/trend_<region>.joblib` (5 present on disk) with metadata in `MLModelArtifact`.

#### FR-6.2 — "Include algorithms for anomaly detection, trend prediction, and correlation analysis."
**Status: Implemented** — all three verified under FR-4.2 and FR-6.1. `::train_all` runs the three together as one `PipelineRun` and persists an anomaly sweep so the investigation screen has stored findings.

#### FR-6.3 — "**Regularly update and refine models based on the latest available data.**"
**Status: Partially implemented**

Retraining is possible but **entirely manual and unversioned**:
- Triggers: `dashboard/views.py::trigger_ml` (POST, `@admin_required`), `analytics/views.py::train_view` (POST, `@admin_required`), `seed_demo --train`.
- No scheduler of any kind. Verified: no `celery`, `schedule`, `APScheduler`, `cron` or Task-Scheduler artefact anywhere in the repo.
- No trigger on new data. `dataingestion/services.py::run_ingestion` evaluates alert thresholds on import but never marks models stale or requests a retrain.
- No drift or staleness detection. Nothing compares live error against the training-time MAE.
- **Refinement is not auditable**: `train_trend_models` and `train_anomaly_model` both call `MLModelArtifact.objects.update_or_create(name=..., version="1", ...)` — the version is hard-coded, so each retrain **overwrites** the previous row. `MLModelArtifact.Meta.unique_together = ("name", "version")` exists precisely to support history, and the code never uses it. Likewise `ml_artifacts/trend_<region>.joblib` is overwritten in place, with only `last_train_date` inside the bundle as evidence.

**Smallest correct fix, in two parts:** (1) bump the version — compute `version = str(int(previous_max) + 1)` and write `trend_<region>_v<version>.joblib`, keeping `is_active` to mark current, so "refine" produces a trail; (2) add a single `retrain` entrypoint (a CLI module callable as `python -m analytics.retrain`) that trains and logs a `PipelineRun`, plus a documented Windows Task Scheduler weekly trigger. A scheduled retrain the grader can see in the docs, backed by a real CLI, is the honest way to satisfy "regularly".

---

### FR-7 Data Visualization

#### FR-7.1 — "Create interactive dashboards."
**Status: Implemented**

Two role-specific consoles, both server-rendered with live data: `templates/dashboard/admin.html` (252 lines — health bar, Mongo/record counters, pipeline history, user rail, alert rail, inline pipeline triggers) fed by `dashboard/services.py::system_overview`; `templates/dashboard/analyst.html` (179 lines — regional chart, investigation paths, anomaly preview with per-region drill-down) fed by `::analyst_exploration_snapshot`. Chart.js and Plotly are vendored locally (`static/vendor/chart.umd.min.js`, `plotly-cartesian.min.js`). `tests/test_core.py::test_pages_render_for_roles` asserts both render 200.

#### FR-7.2 — "Develop visual representations of climate patterns, anomalies, and predictions."
**Status: Implemented**

`templates/analytics/trends.html` (Plotly history + forecast with uncertainty band, plus a model-comparison metrics table including the naive baseline), `templates/analytics/anomalies.html` (Chart.js z-score deviation series ordered oldest-first for a readable timeline, plus a severity-graded table), `templates/analytics/correlations.html` (Plotly diverging heatmap). Design rationale in `DESIGN_NOTES.md`.

#### FR-7.3 — "Provide **customizable** and user-friendly interfaces for stakeholders to explore data."
**Status: Partially implemented**

User-friendly: yes — consistent design system, region/metric filters as GET params (`analytics/views.py::trends_view` region; `realtime/views.py::live_dashboard` region + metric; `::anomalies_view` region), drill-down links from the analyst hub.

**Customizable: no.** There is no per-user customisation of any kind — no saved views, no dashboard layout or widget selection, no persisted default region, no preferences model, no export of a configured view. Every user gets the identical page with the identical hard-coded default `region="pacific_nw"`. The profile field that would obviously drive this, `region_focus`, is unused (see FR-1.2).

**Smallest correct fix:** wire `UserProfile.region_focus` as the default `region` on every filtered view (one change per view, reading from the profile instead of the literal `"pacific_nw"`), and add a small self-service preferences form letting a user set their own default region and preferred metric. That converts an existing-but-inert field into the customisation the requirement asks for, and it pairs naturally with the FR-1.2 scoping fix.

---

### FR-8 Notifications and Alerts

#### FR-8.1 — "Automated notifications and alerts for stakeholders based on predefined thresholds for climate anomalies or significant events."
**Status: Implemented**

- `notifications/models.py::AlertRule` — metric, operator (`gt`/`gte`/`lt`/`lte`/`abs_gt`), threshold, optional region scope, severity, `active`, `notify_email`; `::matches(value, region)` implements the comparison.
- `notifications/services.py::evaluate_value_against_rules` — creates `Notification` rows and optionally sends email (`fail_silently=True`, console backend in dev).
- Evaluated automatically at three points: on every ingested weather/sensor record (`dataingestion/services.py:84-88`), on every realtime reading (`realtime/services.py:48`), and on each newly-detected anomaly (`analytics/services.py::detect_anomalies` → `notify_anomaly`, fired **only for genuinely new upserts** via `result.upserted_ids`, so a re-run does not re-spam).
- Four default thresholds seeded (`seed_demo.py`): extreme heat >35 °C, extreme cold <−15 °C, CO₂ >450 ppm, heavy precipitation >50 mm.
- `tests/test_core.py::test_alert_rule_creates_notification`.

#### FR-8.2 — "Enable **configurable** alerting mechanisms to notify users in **real-time**."
**Status: Partially implemented**

Configurable: admins can **create** rules at `notifications/views.py::manage_rules` (`templates/notifications/rules.html`). But there is **no edit and no delete** — the view handles `POST` as create only, so a mistyped threshold can only be fixed through Django `/admin/`, which disappears with the migration. There is no per-user subscription or opt-out either.

**Defect worth fixing at the same time:** `notifications/services.py:18-20` builds recipients as
`admins = User.objects.filter(profile__role="ADMINISTRATOR", is_active=True)` unioned with `analysts = User.objects.filter(is_active=True)` — the second queryset has **no role filter**, so it is every active user. The union is therefore always "everybody", the admin queryset is redundant, and the variable name `analysts` is actively misleading. Every alert notifies every user regardless of role or region.

Real-time notification: adequate — rules are evaluated synchronously on the realtime tick path, and unread counts surface site-wide via `notifications/context_processors.py::unread_notifications`.

**Smallest correct fix:** add edit/delete/toggle handlers to `manage_rules`; fix the recipient query to `User.objects.filter(is_active=True, profile__role__in=[...])` scoped by the rule's region against `profile.region_focus`.

---

### FR-9 Feedback and Support

#### FR-9.1 — "A support system for users to contact for assistance, report issues, and provide feedback."
**Status: Implemented**

`support/models.py` — `SupportTicket` (subject, body, status open/in-progress/resolved/closed, priority, `created_by`, `assignee`, `admin_notes`) and `Feedback` (1–5 rating, message, page context). `support/views.py::ticket_list` (submit + list, ownership-scoped for analysts), `::update_ticket` (admin sets status/notes and self-assigns; non-owner non-admins are redirected), `::feedback_view` (submit; admins see all submissions). Templates `support/tickets.html`, `support/feedback.html`. Open-ticket count surfaces on the admin console (`dashboard/services.py:92`).

---

## A2. Non-Functional Requirements

### NFR-1 Performance / NFR-5 Performance Monitoring
*(The doc repeats this section verbatim under two headings; counted once.)*

#### NFR-1.1 — "Implement monitoring tools to track **system performance**, **resource utilization**, and **data processing times**."
**Status: Partially implemented — one of three sub-clauses is genuinely missing**

Present:
- System health: `dashboard/services.py::_build_system_overview` — Mongo reachability (`config/mongo.py::ping`, itself cached for 10 s so several callers share one round-trip), record counts per collection, pipeline success/failure counts over 7 days, running-job count, ingestion counters, and a derived `health` string (healthy / attention / degraded / critical).
- Audit trails: `PipelineRun` (job type, `started_at`, `finished_at`, `stats` JSON, `error`, `adapter`, `triggered_by`) and `IngestionJob` (per-job imported/skipped/error log).
- Logging: `config/settings/base.py` `LOGGING` — console + `logs/weatherpredict.log`, with dedicated `weatherpredict.*` loggers used across batch, ingestion, ML, notifications, realtime, mongo.

Absent:
- **Resource utilisation** — nothing. No CPU, memory, disk or connection-pool metric anywhere; `psutil` is not a dependency.
- **Data processing times** — the raw material exists (`PipelineRun.started_at` / `finished_at`) but **no duration is ever computed or displayed**. `templates/dashboard/pipelines.html` and the admin console both show the two timestamps and leave the subtraction to the reader.

**Smallest correct fix:** add a `duration_seconds` property on `PipelineRun` and render it as a column on the pipelines page and the admin console (satisfies "data processing times" with ~5 lines); add `psutil` and a small resource panel showing process CPU %, RSS memory and free disk on the admin console (satisfies "resource utilization").

#### NFR-1.2 — "Include optimization strategies for enhancing the overall efficiency of the system."
**Status: Implemented**

Concrete, verified optimisations rather than claims:
- Generation-token cache invalidation — `dashboard/services.py::_generation` / `::invalidate_dashboard_cache` folds a monotonic counter into every cache key, so one `cache.incr` retires all parameterised aggregates at once; called after each pipeline/ML/synthetic trigger in `dashboard/views.py`.
- TTL caching of the expensive reads: `system_overview` and `region_temp_summary` (`DASHBOARD_CACHE_SECONDS`, default 45), `trends_view` forecasts (`ANALYTICS_CACHE_SECONDS`, default 300).
- Mongo query shaping: `analytics/services.py::_weather_frame` projects only the five columns the models need; `dashboard/services.py::_build_region_temp_summary` uses a server-side `$group` aggregation rather than pulling documents; `estimated_document_count()` for counters.
- ORM query shaping: conditional aggregation in `_build_system_overview` collapses what would be a dozen counters into three `aggregate()` calls; `select_related` on every list view.
- Idempotent upserts (`bulk_write` with `UpdateOne`) so re-runs update rather than append — `detect_anomalies` and `run_batch_pipeline`.
- Forecast loop rewritten to read `values[-lag]` directly rather than recomputing the lag frame each step (documented at `analytics/services.py:349-351`).

Caveat: the **index** half of the optimisation story is inert (`ensure_indexes` never called — see FR-3.2), and `LocMemCache` is per-process, which conflicts with NFR-4.1.

---

### NFR-2 Data Security

#### NFR-2.1 — "Implement encryption mechanisms to secure sensitive climate data **during storage and transmission**."
**Status: Partially implemented — in transit partial, at rest missing entirely**

In transit: `config/settings/production.py` sets `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_HSTS_SECONDS=31536000` with subdomains + preload. These are correct *flags*, but they only matter if a TLS terminator exists — none is part of the project, and development runs plain HTTP. The MongoDB connection is `mongodb://localhost:27017` with **no TLS and no authentication** (`config/settings/base.py:100`), so the climate data itself moves unencrypted and unauthenticated between app and database. Email uses `EMAIL_USE_TLS = True` in production.

At rest: **nothing**. No field-level encryption, no encrypted volume, no MongoDB encryption-at-rest configuration. `FIELD_ENCRYPTION_KEY` appears in `.env.example:21` and is described in `docs/SECURITY_RELIABILITY.md` as "(reserved)" — verified that **no code reads it**.

**Smallest correct fix:** implement the reserved key rather than leaving it aspirational. Add `cryptography`, a `config/crypto.py` with `encrypt_field`/`decrypt_field` using `Fernet(FIELD_ENCRYPTION_KEY)`, and apply it to the profile PII on save/load. Separately, enable MongoDB authentication and document `mongodb://user:pass@host/?tls=true` as the connection string, plus the reverse-proxy TLS termination that backs the HSTS flags. (Also see Part B: the `phone` field is the only PII this protects and is itself unused — deleting it is smaller than encrypting it.)

#### NFR-2.2 — "Ensure compliance with relevant data protection regulations and standards."
**Status: Missing**

`docs/SECURITY_RELIABILITY.md` lists security *controls* but names no regulation and no compliance posture. There is no privacy notice, no PII inventory, no stated retention period, no consent record, no data-subject export or deletion path, and no audit log of who read which data.

**Smallest correct fix:** a short `docs/COMPLIANCE.md` that names the applicable regime (GDPR is the defensible choice for an environmental agency), inventories the personal data actually held (username, email, and `phone` if retained), states a retention period per collection, describes the deletion path (`User` delete cascades `UserProfile`, `Notification`, `SupportTicket`, `Feedback` — verify and state it), and records that climate observations are non-personal.

---

### NFR-3 Reliability

#### NFR-3.1 — "Minimum 99% uptime, with scheduled maintenance communicated in advance."
**Status: Missing — and not achievable as stated**

No health endpoint, no process supervisor, no availability monitoring, no restart policy, no status page, and no mechanism for communicating scheduled maintenance (no banner, no maintenance-mode flag). `docs/SECURITY_RELIABILITY.md` names a 99% target and proposes health-checking `/accounts/login/` — a login page is not a health check, since it returns 200 while MongoDB is down.

99% uptime is an **operational property of hosting**, not something a codebase can contain. This must be stated plainly as an SLO with the infrastructure it presupposes.

**Smallest correct fix + what must be documented:** add a real `/healthz` (post-migration: a Streamlit health page, or better, keep it trivial) returning `{app: ok, mongo: <ping result>, last_pipeline: <status>}` with a non-200 when Mongo is unreachable; add a `MAINTENANCE_MESSAGE` env var rendered as a banner, which is the entire "communicated in advance" mechanism. Then document that the 99% figure is a target requiring a supervised process (Windows Service / systemd / container restart policy) and an external uptime monitor, neither of which ships with the project.

#### NFR-3.2 — "**Regular automated data backups** must be performed to prevent data loss."
**Status: Missing**

`docs/SECURITY_RELIABILITY.md` items 1–3 describe backups in prose (`pg_dump`, `mongodump`, version `ml_artifacts/`). **No backup code, script or scheduled job exists** — verified by search. The word "automated" is unmet in every sense.

**Smallest correct fix:** a real `backup` CLI (`python -m ops.backup`) that shells out to `mongodump --uri $MONGODB_URI --out backups/<timestamp>/mongo`, copies `ml_artifacts/` and the users store into the same folder, writes a `manifest.json`, and prunes folders older than N days. Then document one Windows Task Scheduler entry that runs it nightly. This is the single cheapest Missing→Implemented conversion on the list.

---

### NFR-4 Scalability

#### NFR-4.1 — "The architecture should support horizontal scaling to accommodate increased data volumes and processing demands."
**Status: Partially implemented**

Supportive of scaling: MongoDB is the primary climate store and is shardable on `region` (documented in `docs/SECURITY_RELIABILITY.md`); the batch layer is adapter-pluggable so processing can move off-box; sessions are database-backed rather than in-process.

**Actively blocking scaling:** `config/settings/base.py:107-113` configures `LocMemCache`, and `dashboard/services.py` builds correctness on top of it — the generation token lives in that cache. With two or more worker processes each has its own token and its own cached aggregates, so triggering a pipeline on worker A does **not** invalidate worker B, and users get stale dashboards non-deterministically depending on which worker answers. This is a correctness bug the moment the app is scaled, not merely a performance issue.

**Smallest correct fix:** move the cache to Redis (`redis` + `django.core.cache.backends.redis.RedisCache`, or after migration a shared `st.cache_resource`-held Redis client) — or, if Redis is out of scope, document unambiguously that the app is **single-worker only** and that horizontal scaling requires the shared-cache swap first.

#### NFR-4.2 — "Implement load balancing mechanisms for optimal resource utilization."
**Status: Missing (prose only)**

No reverse-proxy configuration, no nginx/HAProxy/IIS sample, no multi-worker start command, no sticky-session or health-check configuration in the repo. `gunicorn` is in `requirements.txt` but is never configured or referenced by any command. `docs/SECURITY_RELIABILITY.md:30` mentions "≥2 Gunicorn/Daphne workers behind a load balancer" as an aspiration.

This is infrastructure, not application code, so a documented topology is the honest deliverable — but it must be a **concrete, runnable** one, and it must come *after* the NFR-4.1 shared-cache fix, since load-balancing the current build would produce inconsistent dashboards.

**Smallest correct fix:** commit a working `deploy/nginx.conf` sample (upstream block with two app instances on different ports, `proxy_pass`, health check against `/healthz`) and document the exact two-instance start commands. For Streamlit, note that WebSocket upgrade headers (`Upgrade`/`Connection`) and sticky sessions by IP hash are **mandatory** — Streamlit holds per-session state on one server, so a naive round-robin balancer breaks it. That constraint must be written down.

---

### NFR-6 Compliance and Standards

#### NFR-6.1 — "Ensure adherence to relevant **environmental data standards and protocols**."
**Status: Missing**

No climate-domain standard is applied anywhere. Specifically: no CF (Climate and Forecast) metadata conventions, no CF-standard variable names or units attributes, no WMO/GHCN station identifier scheme (station IDs are invented — `STN-PAC-01` from `batch/synthetic.py`), no ISO 19115 geospatial metadata, and no STAC catalogue structure for the satellite records despite `satellite_imagery` already carrying `scene_id`, `bbox`, `bands`, `acquired_at` and `cloud_cover_pct` — which is most of a STAC Item already.

**Smallest correct fix:** a short `docs/DATA_STANDARDS.md` plus a light schema alignment. Map `satellite_imagery` onto STAC Item field names (`id`, `bbox`, `datetime`, `properties.eo:cloud_cover`, `assets`) — that is a rename, not a redesign. Map weather fields to CF standard names in the doc (`temp_c` → `air_temperature` in °C, `precip_mm` → `precipitation_amount` in mm, `pressure_hpa` → `air_pressure`, `wind_ms` → `wind_speed`) and record the units. Note the deliberate non-conformances (synthetic station IDs are not WMO-registered).

#### NFR-6.2 — "Comply with industry best practices for big data processing and analytics."
**Status: Partially implemented**

Genuinely present: raw/processed layer separation (`data/raw/`, `data/processed/<run>/`); idempotent re-runs via natural-key upserts; partitioned columnar-ish output; run-level lineage through `PipelineRun.stats`; and — notably strong — the ML discipline documented in `ml_artifacts/MODEL_EVALUATION.md` and enforced in code: time-based splits only, lag-only features, training-window-only baselines, and a naive-persistence comparison so an inflated R² cannot hide a useless model. The anomaly evaluation explicitly labels its precision/recall as **proxy** metrics against `|z|>3` rather than verified events. That refusal to fabricate favourable metrics is best practice and should be preserved verbatim through the migration.

Absent: no schema/data contract validation on the processed layer, no persisted data-quality metrics (the `missing_count` column is computed then discarded), no column-level lineage, and no partition-level statistics.

---

### NFR-7 Documentation

#### NFR-7.1 — "User Documentation: provide user **guides**, **FAQs**, and **tutorials**."
**Status: Partially implemented**

`docs/USER_GUIDE.md` (35 lines) covers roles, sign-in, ingestion (with the expected weather CSV column list), live sensors, analytics, alerts, support and pipelines. That satisfies "guides".

There is **no FAQ** and **no tutorial** — two of the three named artefacts. A tutorial in this context means a worked end-to-end walkthrough, which `docs/DEMO_SCRIPT.md` approximates but is written as a video-recording script for the author, not as instructions for a user.

**Smallest correct fix:** append two sections to `docs/USER_GUIDE.md` — a **FAQ** (10–12 real questions: why is my upload skipping rows, what does a z-score mean here, why does a forecast say "train models first", why did I get an alert email, how do I change a threshold, what does "proxy precision" mean) and a **Tutorial** (one numbered end-to-end path: log in → upload the sample weather CSV → run batch → train ML → read the trend forecast → trigger and inspect an alert), each step naming the exact screen and expected result.

#### NFR-7.2 — "Developer Documentation: system architecture, data processing workflows, and machine learning models."
**Status: Implemented (with an accuracy defect)**

- `architecture.md` (163 lines) — system diagram, app responsibility table, full relational and MongoDB schemas with example documents, RBAC capability matrix, real-time architecture, batch/big-data design, ML pipeline, settings split, and an explicit "out of scope" section.
- `docs/DEVELOPER.md` — directory layout, settings, Mongo access layer, batch adapter contract, ML entry points, testing, ASGI.
- `ml_artifacts/MODEL_EVALUATION.md` — leakage controls, per-model expectations, honest caveats.

**Defect:** `architecture.md` §5 and §7 cite `realtime.services.sensor_simulator`, `realtime.services.unified_view` and `analytics.services.prediction_service`. **None of these three names exist.** The real names are `emit_sensor_tick`, `unified_series` and `predict_trend`. A developer following the architecture doc will fail to find any of them.

**Second issue (delivery, not accuracy):** `.gitignore:29` ignores `ml_artifacts/*` except `.gitkeep`, so **`ml_artifacts/MODEL_EVALUATION.md` is not tracked by git** — confirmed against `git ls-files`. A documentation deliverable is being excluded from the deliverable. Fix with a `!ml_artifacts/MODEL_EVALUATION.md` negation, or move the file to `docs/`.

#### NFR-7.3 — "Video: provide video displaying complete working of the application."
**Status: Missing**

`docs/DEMO_SCRIPT.md` is a 6–8 minute recording plan with 11 numbered beats — a good script, but the deliverable is the recording. No video file exists. Note the script is already stale: beat 2 references `python manage.py runserver` and beat 10 the Django 403 behaviour, both of which change with the migration.

---

## A3. Project Deliverables

#### DEL-1 — Problem Definition
**Status: Partially implemented**

README opens with a one-sentence product statement and a capability list. `PROJECT_PLAN.md` is a phase checklist, not a problem statement. Nothing in the repo states the EarthScape problem, its stakeholders, the objectives or the scope boundary — all of which exist in the source docx (Background section) and simply have not been carried across.

**Smallest correct fix:** `docs/PROBLEM_DEFINITION.md` — background (climate change, the data-volume challenge), the organisation (EarthScape Climate Agency) and its data sources, the stakeholders (administrators, analysts), the objectives, and an explicit in-scope / out-of-scope list that names the substitutions (no live satellite feed, no Hadoop cluster, no Tableau/Impala).

#### DEL-2 — Design specifications
**Status: Implemented** — `architecture.md` (schemas, component design, RBAC matrix, data flows in prose) and `DESIGN_NOTES.md` (UI design system, per-screen rationale, and a candid gap table mapping docx items to in-app equivalents).

#### DEL-3 — "Diagrams such as **flowcharts** for various activities, **Data Flow Diagrams** etc."
**Status: Partially implemented**

`architecture.md` contains exactly one ASCII diagram: a component/box diagram of the system. That is neither a flowchart nor a DFD. There is **no levelled Data Flow Diagram** (no context diagram with external entities, no L0/L1 with numbered processes, data stores and labelled flows) and **no activity flowchart** for any workflow.

**Smallest correct fix:** `docs/DIAGRAMS.md` with four Mermaid diagrams (renders on GitHub and in most viewers, no tooling needed): a context DFD (external entities: Administrator, Analyst, upload sources, sensor simulator); a level-1 DFD (processes: ingest/validate, batch clean+partition+aggregate, ML train, detect anomalies, alert; stores: `weather_station_records`, `sensor_readings`, `satellite_imagery`, `batch_aggregates`, `anomalies`, `ml_predictions`); and two activity flowcharts — file ingestion (upload → extension check → content sniff → per-row normalise → skip/error/import → threshold evaluation → job status) and alerting (value → active rules → operator match → region match → notification fan-out → email).

#### DEL-4 — Source Code
**Status: Implemented** — 130 tracked source files under git, organised by domain, with a test suite (`tests/test_core.py`, `tests/test_ml.py`) and `pytest.ini`.

#### DEL-5 — "Test Data Used in the Project"
**Status: Partially implemented**

Generation is real and reproducible: `batch/synthetic.py::generate_synthetic_dataset(seed=42)` deterministically produces multi-year weather, sensor and satellite documents across 5 regions, and writes a `data/synthetic/weather_sample.csv` extract.

But as a *deliverable*, this fails on two counts. First, **`.gitignore:27` ignores `data/synthetic/*`**, so `weather_sample.csv` is untracked and will not be in the submitted zip — verified against `git ls-files`. Second, there is no curated, described test-data set: nothing documents what the data contains, what a valid file looks like per data type, or what the expected import outcome is. The six files in `media/uploads/` are accidental runtime residue from manual testing, not test data.

**Smallest correct fix:** commit a small `data/test_data/` directory (whitelisted in `.gitignore`) containing one file per type — `weather_sample.csv`, `sensor_sample.csv`, `satellite_sample.json` — each ~20 rows and deliberately including a couple of rows with missing optional fields to exercise the graceful-degradation path, plus a `data/test_data/README.md` stating the columns, the intended data type selection, and the expected imported/skipped counts.

#### DEL-6 — Project Installation Instructions
**Status: Implemented (but will be invalidated by the migration)**

README "Quick start (Windows)" gives the full path: venv creation, `pip install -r requirements.txt`, `.env` copy, migrate, seed with data and training, run server — plus default credentials, a common-commands section, and a production upgrade path. `.env.example` documents every environment variable.

Flagged: `python manage.py migrate`, `seed_demo` and `runserver` all disappear with Django. These instructions must be rewritten as part of the migration, not after it.

#### DEL-7 — "Documentation is considered as a very important part... complete and comprehensive."
**Status: Partially implemented** — strong developer documentation, thin user documentation, and specific gaps enumerated at NFR-7.1 (no FAQ, no tutorial), NFR-7.2 (three wrong function names; the ML evaluation doc is gitignored), DEL-1 (no problem definition) and DEL-3 (no DFDs or flowcharts).

#### DEL-8 — "Submitted as a zip file with a **ReadMe.doc** file listing **assumptions** (if any)."
**Status: Partially implemented**

The assumptions themselves are done well — README has an explicit `## Assumptions` section with five numbered items (MongoDB locally available; synthetic data in place of live feeds; Hadoop/HDFS/Impala/Tableau out of scope with a documented upgrade path; demo passwords local-only; console email backend) plus a `## Known limitations` section with four more. That is exactly what the deliverable asks for in substance.

Missing: there is no `ReadMe.doc`/`.docx` and no packaging step. Also, the assumptions list needs updating post-migration and post-analysis — it does not currently mention the absence of at-rest encryption, automated backups, or real-time autonomous ingestion.

**Smallest correct fix:** keep `README.md` as the single source of truth, extend the assumptions list to cover every substitution identified in this document, and add a short packaging note (or a `make_submission` script) that exports the README to `ReadMe.docx` and zips the tree excluding `.venv/`, `__pycache__/`, `.git/`, `data/processed/`, `logs/*.log` and `media/`.

#### DEL-9 — "Submit a video clip demonstrating the working of the **Website**. Optionally, a live hosted URL."
**Status: Missing** — same as NFR-7.3.

**On "Website" and Streamlit:** the docx never names a web framework, and the Functional Requirements ask only for interactive dashboards, visual representations and customizable interfaces. Streamlit serves an HTTP web application in a browser, so it satisfies "Website" on its face. This wording is **not** an obstacle to the migration. The one thing to be careful about: the demo must be recorded in a browser and should show the URL bar, so the artefact visibly reads as a website rather than a desktop tool.

---

## A4. Hardware / Software Requirements — environmental vs. deliverable

The docx's Hardware/Software section is a **development-environment specification**, not a feature list. Two entries in it are load-bearing because they are *also* named in the Functional Requirements (MongoDB, Hadoop/HDFS); the rest are developer tooling. Judged individually:

### Hardware (all 5 items: environmental, not deliverables)

| Item | Verdict |
|---|---|
| Min. i5 4-core (i7 recommended) | Environmental. The workload (pandas over ~5,500 weather rows/year × 5 regions, sklearn Ridge/GBR/IsolationForest) is comfortable on the stated minimum. Nothing to deliver. |
| 16 GB RAM | Environmental. Current data volumes are well under 1 GB in memory. Nothing to deliver. |
| 500 GB SSD | Environmental. Actual footprint is a few MB plus `data/processed/` growth (3.7 MB across 4 runs today). Nothing to deliver. |
| Graphics card | Environmental and **irrelevant to this build** — no GPU code path exists. sklearn is CPU-only; `xgboost` (the only plausibly GPU-capable dependency) is declared but never imported. Do not claim GPU usage. |
| 64-bit Windows 10+ | Satisfied — the project is developed and documented Windows-first (PowerShell instructions, Windows-illegal-character filename sanitisation in `write_partitions`, "Windows-friendly" local adapter). |

### Software (7 items)

| Item | Verdict | Detail |
|---|---|---|
| **Jupyter / Anaconda Notebook 3** | **Suggested tooling — not satisfied, not required as a deliverable.** | The project uses a plain venv and CLI entry points. No notebook exists. Nothing in the Functional or Non-Functional requirements needs one. *Optional literal-compliance move:* add one `notebooks/model_exploration.ipynb` reproducing the trend/anomaly evaluation, which would also strengthen NFR-7.2. Low cost, purely presentational. |
| **RStudio** | **Suggested tooling — legitimately not needed.** | The stack is 100% Python; there is no R code and no requirement that implies R. This is boilerplate in the brief. Say so explicitly rather than leaving it unaddressed. |
| **Visual Studio Code / PyCharm** | **Editor choice — not a deliverable.** | No project artefact depends on either. `.gitignore` already excludes `.idea/` and `.vscode/`. |
| **MongoDB Compass and Shell** | **Satisfied in substance.** | MongoDB is genuinely required and genuinely used — `config/mongo.py` (`MongoClient`, six collections, index definitions), `pymongo` in requirements, all climate data stored there. Compass and the shell are inspection clients for a real local MongoDB instance; installing them is an evaluator convenience, not a code deliverable. |
| **Hadoop, HDFS and Apache server** | **Substituted (documented) — and this one is also a functional requirement (FR-3.1, FR-4.1).** | No HDFS, no MapReduce, no cluster (see FR-3.1/FR-4.1). "Apache server" is ambiguous in the brief — it could mean Apache HTTP Server or the Apache Hadoop ecosystem; neither is present. The web tier is Django's dev server today and will be Streamlit's after migration. This is the most significant substitution in the project and needs the most explicit documentation. |
| **Tableau** | **Substituted (documented) — legitimately unnecessary.** | The Data Visualization requirement (FR-7) is satisfied *in-app* by Chart.js/Plotly today and by Streamlit + Plotly after migration. Tableau is a suggested BI tool, not a required capability. README already documents the export path (`data/processed/**/aggregates.csv` → Impala external tables → Tableau). Keep that paragraph; it is the right answer. |
| **Impala server** | **Substituted (documented) — legitimately unnecessary.** | Impala is SQL-on-Hadoop; with MongoDB as the store and no Hadoop cluster it has no role. Nothing in the Functional Requirements needs a SQL query engine. Documented in the README upgrade path. |

**Summary for this section:** of the 7 software items, **1 is genuinely required and satisfied** (MongoDB), **1 is genuinely required and substituted** (Hadoop/HDFS), **2 are substituted BI/query tools that the app legitimately replaces** (Tableau, Impala), and **3 are developer tooling with no bearing on the deliverable** (Jupyter/Anaconda, RStudio, VS Code/PyCharm). None of the 5 hardware items is a deliverable.

---

# PART B — Project scope not traceable to any requirement

Note on repository hygiene: `db.sqlite3`, `media/`, `logs/*.log`, `data/processed/*`, `data/synthetic/*`, `ml_artifacts/*` and `.pytest_cache/` are **already gitignored and untracked** (verified against `git ls-files`). They are on-disk weight and submission-zip risk rather than committed scope creep — but two of those ignore rules are wrong (they exclude real deliverables; see B-13).

### B-1. Unused runtime dependencies — **Remove**
Verified by exhaustive search: **zero import sites** anywhere in the codebase for `xgboost`, `statsmodels`, `scipy`, `Pillow`, `factory-boy`, `freezegun`, `email-validator`, `channels-redis`. `scipy` is a transitive dependency of scikit-learn and should not be pinned explicitly. `pytest-cov` is installed but no coverage is configured (`pytest.ini` is just `addopts = -q`). `gunicorn` is never referenced by any command. Serves no requirement; `xgboost` alone is a large install that misleads a reader about what the ML layer does. **Remove all nine lines**, and either wire `--cov` into `pytest.ini` or drop `pytest-cov` too.

### B-2. Django Channels / WebSocket stack — **Remove**
`realtime/consumers.py`, `realtime/routing.py`, `config/asgi.py`, the `channels` + `daphne` + `channels-redis` dependencies, `CHANNEL_LAYERS`, and the `USE_CHANNELS` setting. The shipped real-time path is HTTP polling; `USE_CHANNELS` is read by nothing; the consumer is request/response rather than a stream (FR-5.1). None of it survives the move to Streamlit. Replace with `st.fragment(run_every=...)`, which satisfies FR-5.1 more directly and with far less machinery.

### B-3. `analytics/management/commands/dedupe_anomalies.py` (73 lines) — **Remove**
An orphan one-off repair command. It is referenced in **no** documentation, UI surface or test — verified, the string appears nowhere in the repo outside its own filename. The duplicate-anomaly problem it was written to fix has since been solved structurally by the identity upsert in `detect_anomalies` (`UpdateOne(..., upsert=True)` on `region+metric+observed_at`) plus the `anomaly_identity_unique` index. Keeping a repair script for a fixed bug is dead weight that invites someone to run it.

### B-4. `config/security.py::sanitize_upload_name` — **Remove (partial file)**
Dead function: the ingest path uses `dataingestion/validators.py::sanitize_filename` instead (`dataingestion/views.py` and `services.py`). Two overlapping filename sanitisers with different rules, one unused, is a security-code smell. **Keep** the other two functions in that module — `is_allowed_upload` and `sniff_is_text_or_xlsx` are both called from `dataingestion/views.py::upload` and serve upload security under NFR-2.

### B-5. Dead settings: `USE_CHANNELS`, `REALTIME_POLL_SECONDS` — **Remove**
`config/settings/base.py:118-119` and the corresponding `.env.example` entries. Both defined, neither read anywhere. Configuration that does nothing is worse than no configuration, because it implies a switch that does not exist.

### B-6. `pipeline_audit` in the collection allow-list — **Remove**
`config/mongo.py:43` specially permits a `pipeline_audit` collection that is never written or read. One-line removal.

### B-7. `UserProfile.phone` and `UserProfile.organization` — **Remove**
`phone` is never read, never displayed, never validated — and it is the **only** sensitive PII in the system beyond email, which means it single-handedly creates most of the at-rest encryption obligation under NFR-2.1 while delivering nothing. Deleting it is strictly cheaper than encrypting it. `organization` is a constant (`default="EarthScape Climate Agency"`), never varied and never queried. Both are pure schema weight.

### B-8. `UserProfile.region_focus` — **Keep, but only if wired**
Currently inert (see FR-1.2 and FR-7.3). It is the natural key to two Partial requirements at once: role-based **data** scoping and interface **customisation**. Keep it and make it load-bearing. If the implementing agent chooses not to do the FR-1.2 scoping work, then remove this field too — an unused profile field is not worth carrying.

### B-9. Django built-in admin (`/admin/` and the six `admin.py` modules) — **Remove**
A second, parallel administration UI alongside the purpose-built console at `/dashboard/admin/`. The doc asks for one administrator role in one application; `config/urls.py` even carries a comment acknowledging the collision ("Django built-in admin remains for developers only"). It disappears with Django anyway — but note the dependency first: `notifications/views.py::manage_rules` is **create-only**, so Django admin is currently the *only* way to edit or delete an alert rule. Fix FR-8.2 (add edit/delete) **before or with** this removal, or a required capability regresses.

### B-10. Django template/asset layer — **Remove with the migration**
`templates/` (16 files), `static/css/app.css`, `static/js/app.js`, `static/vendor/bootstrap.bundle.min.js`, `bootstrap.min.css`, `lucide.min.js`, `fonts.css` and four `.woff2` files. All exist to render the Django template UI. Streamlit brings its own layout, widgets and theming, and bundles Plotly. Nothing here transfers. Preserve the *design intent* from `DESIGN_NOTES.md` (palette, chart conventions, information-dense layout, coral reserved for alerts) as Streamlit theme config — that is genuinely worth keeping, and it is documentation, not code.

Caveat: `static/vendor/chart.umd.min.js` and `plotly-cartesian.min.js` are the current evidence for FR-7.1/7.2. Do not delete them until the Streamlit charts replacing them render.

### B-11. `New Text Document.txt` — **Remove**
A tracked stray file containing a duplicate of the README quick-start commands. Six lines of accidental commit.

### B-12. `_scratch_inspect.py`, `_scratch_mongo.py` — **Remove**
Untracked ad-hoc inspection scripts at the repository root. `_scratch_inspect.py` selects and prints `auth_user.password` hashes to stdout — it must not reach the submission zip.

### B-13. Two `.gitignore` rules that exclude actual deliverables — **Fix, do not keep**
`ml_artifacts/*` (line 29) excludes `ml_artifacts/MODEL_EVALUATION.md`, a required documentation artefact (NFR-7.2). `data/synthetic/*` (line 27) excludes `weather_sample.csv`, the only test-data artefact (DEL-5). Both are correct rules with wrong blast radius. Add negations (`!ml_artifacts/MODEL_EVALUATION.md`, `!data/test_data/**`) or relocate the files. This is the rare case where the ignore file, not the code, is the scope defect.

### B-14. On-disk runtime residue — **Delete before packaging** (not tracked, so not repo scope)
`db.sqlite3` (200 KB, contains seeded demo password hashes); `media/uploads/1_wx*.json` (6 near-identical files from manual upload testing, with Django's collision suffixes); `data/processed/2026*` (4 run directories, 70+ CSVs, 3.7 MB, fully regenerable by `run_batch`); `logs/weatherpredict.log`; `.pytest_cache/`. Keep the `.gitkeep` scaffolding.

### B-15. `batch/synthetic.py` (177 lines) — **KEEP**
Not named by the doc, but do **not** remove it. It is the sole source of the multi-year historical corpus that FR-2.2 (historical sources), FR-4.2 (pattern/anomaly/correlation algorithms), FR-6.1–6.2 (ML training needs ≥120 daily observations per region — see the guard at `analytics/services.py:86`) and DEL-5 (test data) all depend on. It is also deterministic (`seed=42`), which makes every downstream result reproducible for the grader. Removing it would break four requirements at once.

### B-16. `support.Feedback` as a model separate from `SupportTicket` — **KEEP**
Small (one model, one view, one template) and directly traceable: FR-9.1 asks for a system to "contact for assistance, **report issues**, and **provide feedback**" — three verbs that map cleanly onto tickets (first two) and rated feedback (third). Merging them would make the requirement harder to demonstrate, not easier.

### B-17. `MLModelArtifact` + the `ml_artifacts/` reports — **KEEP**
Serves NFR-7.2 (documentation of machine learning models) and is the only existing substrate for FR-6.3's audit trail. It is currently under-used (hard-coded `version="1"`, see FR-6.3) — the fix is to use it properly, not to drop it.

### B-18. Dashboard caching layer (`dashboard/services.py` generation-token machinery) — **KEEP the capability, replace the backend**
This is the primary concrete evidence for NFR-1.2 (optimisation strategies) and it is well-built. But `LocMemCache` breaks NFR-4.1 under multiple workers (see NFR-4.1). Keep the pattern; move it to Redis, or to `st.cache_data`/`st.cache_resource` with a shared invalidation token after migration.

### B-19. Three-way settings split + `whitenoise` + static-files pipeline — **Replace, don't simply delete**
`config/settings/{base,development,production}.py` is Django-specific and goes with the framework, but the *intent* must survive: environment-driven configuration, secrets from `.env`, and the production security posture (TLS redirect, HSTS, secure cookies) that is the current evidence for NFR-2.1's transit half. Carry that forward as a small `config/settings.py` reading `os.environ`, and document how TLS is terminated in front of Streamlit — otherwise the migration silently deletes the only in-transit security evidence in the project.

---

# PART C — Prioritised action list

Ordered for a later implementing agent. Each item is scoped to be independently completable.

## C1. MUST ADD (required by the doc; currently Missing or Partial)

**Tier 1 — Missing requirements with no current evidence at all**

- [ ] **1.** Add an automated backup CLI (`ops/backup.py`, runnable as `python -m ops.backup`): `mongodump` the configured URI into `backups/<timestamp>/mongo/`, copy `ml_artifacts/` and the user store alongside it, write a `manifest.json` with counts and timestamps, prune folders older than 14 days. Document one Windows Task Scheduler nightly trigger in `docs/SECURITY_RELIABILITY.md`. *(NFR-3.2 — highest value-per-effort item on this list)*
- [ ] **2.** Add a health endpoint returning `{"app": "ok", "mongo": <bool>, "last_pipeline": <status>, "checked_at": <iso>}`, non-200 when Mongo is unreachable. Add a `MAINTENANCE_MESSAGE` environment variable rendered as a site-wide banner when set — that banner *is* the "maintenance communicated in advance" mechanism. *(NFR-3.1)*
- [ ] **3.** Write `docs/COMPLIANCE.md`: name the applicable regime (GDPR), inventory the personal data actually held, state a retention period per collection, describe the deletion path and verify the cascade, and record that climate observations are non-personal. *(NFR-2.2)*
- [ ] **4.** Write `docs/DATA_STANDARDS.md` and align two schemas: map `satellite_imagery` fields onto STAC Item names (`id`, `bbox`, `datetime`, `properties.eo:cloud_cover`, `assets`) — a rename, not a redesign — and document the CF standard-name mapping for weather variables (`temp_c` → `air_temperature`, `precip_mm` → `precipitation_amount`, `pressure_hpa` → `air_pressure`, `wind_ms` → `wind_speed`) with units. State the deliberate non-conformances. *(NFR-6.1)*
- [ ] **5.** Add `docs/DIAGRAMS.md` with four Mermaid diagrams: context DFD, level-1 DFD (processes, data stores, labelled flows), ingestion activity flowchart, alerting activity flowchart. *(DEL-3)*
- [ ] **6.** Add `docs/PROBLEM_DEFINITION.md`: background, agency and data sources, stakeholders, objectives, explicit in-scope/out-of-scope naming every substitution. *(DEL-1)*
- [ ] **7.** Record the demonstration video against the **post-migration** Streamlit app, in a browser with the URL bar visible. Rewrite `docs/DEMO_SCRIPT.md` first — its current beats reference `manage.py runserver` and Django 403 behaviour. *(NFR-7.3, DEL-9 — do this last, after everything else lands)*

**Tier 2 — Partial requirements, small fixes**

- [ ] **8.** Call `ensure_indexes()` once at application start. Today it is defined and never invoked, so no MongoDB index exists in a fresh deployment. *(FR-3.2, NFR-1.2)*
- [ ] **9.** Implement role-based **data** scoping: add `accounts/scoping.py::allowed_regions(user)` returning `None` for Administrator and `[profile.region_focus]` for Analyst, and apply it as a mandatory region filter inside `_weather_frame`, `stored_anomalies`, `get_correlations`, `unified_series`, `_build_region_temp_summary` and `recent_anomalies_preview`. One shared layer, not per-view. *(FR-1.2 — the single most important functional gap)*
- [ ] **10.** Use `UserProfile.region_focus` as the default region on every filtered view (replacing the hard-coded `"pacific_nw"`), and add a self-service preferences form for default region and preferred metric. *(FR-7.3)*
- [ ] **11.** Add edit / delete / activate-toggle handlers to the alert-rule management view. **Do this before removing Django admin**, which is currently the only way to edit a rule. *(FR-8.2)*
- [ ] **12.** Fix the notification recipient query in `notifications/services.py:18-20` — `analysts = User.objects.filter(is_active=True)` has no role filter, so every alert notifies every user and the `admins` queryset is redundant. Scope recipients by role and by the rule's region against `profile.region_focus`. *(FR-8.2)*
- [ ] **13.** Version ML artifacts on retrain: compute the next `version` instead of hard-coding `"1"`, write `trend_<region>_v<n>.joblib`, and keep `is_active` to mark current. `MLModelArtifact.Meta.unique_together` already supports this. *(FR-6.3)*
- [ ] **14.** Add a `retrain` entrypoint (`python -m analytics.retrain`) that runs `train_all` and logs a `PipelineRun`, plus a documented weekly Task Scheduler trigger. *(FR-6.3 — this is what makes "regularly update" true rather than aspirational)*
- [ ] **15.** Surface processing durations: add a `duration_seconds` property on `PipelineRun` and render it as a column on the pipelines view and admin console. *(NFR-1.1)*
- [ ] **16.** Add resource-utilisation monitoring: `psutil` plus a small admin panel showing process CPU %, RSS memory and free disk. *(NFR-1.1 — currently the one sub-clause with zero evidence)*
- [ ] **17.** Commit curated test data: `data/test_data/{weather_sample.csv, sensor_sample.csv, satellite_sample.json}`, ~20 rows each, deliberately including rows with missing optional fields to exercise the graceful-degradation path, plus a README stating columns, data type and expected imported/skipped counts. Whitelist the directory in `.gitignore`. *(DEL-5, FR-4.3)*
- [ ] **18.** Add a FAQ section (10–12 real questions) and a numbered end-to-end Tutorial to `docs/USER_GUIDE.md`. *(NFR-7.1 — two of three named artefacts are currently absent)*
- [ ] **19.** Fix `architecture.md` §5 and §7: `sensor_simulator` → `emit_sensor_tick`, `unified_view` → `unified_series`, `prediction_service` → `predict_trend`. All three cited names do not exist. *(NFR-7.2)*
- [ ] **20.** Fix the two `.gitignore` rules that exclude deliverables: add `!ml_artifacts/MODEL_EVALUATION.md` and `!data/test_data/**`. *(NFR-7.2, DEL-5)*
- [ ] **21.** Add NetCDF ingestion — `xarray`/`netCDF4`, `.nc` in the allowed extensions, and a `load_records` branch reading CF `time`/`lat`/`lon` coordinates and flattening the target variable to the weather-record shape. One genuine climate format beats a claim of many. *(FR-2.3)*
- [ ] **22.** Implement field encryption using the already-reserved `FIELD_ENCRYPTION_KEY`: `cryptography`, a `config/crypto.py` with Fernet-based `encrypt_field`/`decrypt_field`, applied to profile PII. *(NFR-2.1 — or, cheaper and also acceptable: delete the `phone` field per C2-6 and document that no PII beyond email is stored)*
- [ ] **23.** Move the cache off `LocMemCache` to a shared backend, or document unambiguously that the app is single-worker-only until that swap happens. The generation token in a per-process cache makes multi-worker dashboards inconsistent. *(NFR-4.1 — must precede any load-balancing work)*
- [ ] **24.** Re-implement authentication for Streamlit with equivalent guarantees: a login gate that runs before any page body renders, explicit password hashing (`passlib`/`bcrypt` — Django's PBKDF2 is gone), a server-side session store, and a per-page role check at the top of every page module, because Streamlit's multipage router will serve any page whose URL is guessed. *(FR-1.1, FR-1.2 — the highest-risk migration item; do this first in the migration, not last)*
- [ ] **25.** Re-implement real-time refresh with `st.fragment(run_every="5s")` on the live view, replacing the polling/Channels split. *(FR-5.1)*
- [ ] **26.** Rewrite the README installation instructions for Streamlit (`streamlit run app.py`, no `migrate`, no `runserver`) and update `.env.example`. *(DEL-6)*

## C2. MUST REMOVE (unrequested scope)

Ordered so that nothing is removed before its replacement exists.

- [ ] **1.** Nine unused dependencies from `requirements.txt`: `xgboost`, `statsmodels`, `scipy`, `Pillow`, `factory-boy`, `freezegun`, `email-validator`, `channels-redis`, and `gunicorn` — plus `pytest-cov` unless coverage is wired into `pytest.ini`. Zero import sites for all of them. *(B-1)*
- [ ] **2.** `New Text Document.txt` (tracked stray duplicate of the README quick-start). *(B-11)*
- [ ] **3.** `_scratch_inspect.py` and `_scratch_mongo.py` — untracked scratch scripts; the first prints password hashes. *(B-12)*
- [ ] **4.** `analytics/management/commands/dedupe_anomalies.py` — orphan repair command for a bug already fixed structurally by the identity upsert and unique index. *(B-3)*
- [ ] **5.** `config/security.py::sanitize_upload_name` — dead duplicate sanitiser. **Keep** `is_allowed_upload` and `sniff_is_text_or_xlsx`, both of which are live upload-security controls. *(B-4)*
- [ ] **6.** `UserProfile.phone` and `UserProfile.organization` — unused fields; `phone` is the only PII driving the encryption obligation for zero benefit. *(B-7)*
- [ ] **7.** Dead settings `USE_CHANNELS` and `REALTIME_POLL_SECONDS` (and their `.env.example` entries), and the `pipeline_audit` entry in the `config/mongo.py` allow-list. *(B-5, B-6)*
- [ ] **8.** The Channels/WebSocket stack: `realtime/consumers.py`, `realtime/routing.py`, `config/asgi.py`, `channels`, `daphne`, `CHANNEL_LAYERS`. **Only after C1-25** (the Streamlit fragment refresh) is working. *(B-2)*
- [ ] **9.** Django built-in admin and the six `admin.py` modules. **Only after C1-11** (alert-rule edit/delete), which currently depends on it. *(B-9)*
- [ ] **10.** `templates/` (16 files), `static/css/app.css`, `static/js/app.js`, `static/vendor/bootstrap*`, `lucide.min.js`, `fonts.css` and the four `.woff2` files. **Only after** the equivalent Streamlit pages render. Preserve `DESIGN_NOTES.md` intent as Streamlit theme configuration. *(B-10)*
- [ ] **11.** Django framework code once migration completes: `manage.py`, `config/wsgi.py`, `config/settings/*`, all `apps.py`/`urls.py`/`views.py`/`migrations/`, and the `Django`/`whitenoise` dependencies. **Replace, don't just delete**, the environment-driven configuration and the production TLS posture — see C3-6. *(B-19)*
- [ ] **12.** Before packaging the submission zip, delete on-disk residue: `db.sqlite3`, `media/uploads/*`, `data/processed/2026*` (4 dirs, 3.7 MB), `logs/weatherpredict.log`, `.pytest_cache/`. Keep the `.gitkeep` scaffolding. *(B-14)*

**Explicitly do NOT remove:** `batch/synthetic.py` (four requirements depend on it — FR-2.2, FR-4.2, FR-6.x, DEL-5), `support.Feedback` (FR-9.1 names feedback distinctly from issue reporting), `MLModelArtifact` and the `ml_artifacts/` reports (NFR-7.2, FR-6.3), the dashboard caching pattern (NFR-1.2), and `UserProfile.region_focus` if C1-9/C1-10 are implemented.

## C3. MUST DOCUMENT (requirement met by local substitution — needs an explicit written upgrade path)

Each of these is a capability that **cannot** be genuinely implemented on a single Windows workstation. The deliverable for each is honest, specific prose — not a claim of implementation.

- [ ] **1. Hadoop / HDFS storage** *(FR-3.1; Software list)* — Document: that storage is MongoDB + local filesystem, not HDFS; that `HadoopAdapter`'s `hdfs://` paths are configuration strings with no client behind them and no HDFS library in requirements; that `BatchAdapter` (`partition` / `clean` / `reduce_aggregate` / `write_partitions`) is the exact seam for the swap; the intended HDFS layout (`/weatherpredict/raw/<datatype>/dt=<date>/`, `/weatherpredict/processed/<datatype>/region=<r>/`); and the concrete upgrade step (implement `write_partitions` against `pyarrow.fs.HadoopFileSystem`, set `HDFS_NAMENODE`, run with `--adapter hadoop`).
- [ ] **2. Hadoop MapReduce parallel processing** *(FR-4.1)* — Document: that processing is single-process pandas with no parallelism and no distribution; that `submit_mapreduce` returns `not_configured` and submits nothing; that the map/reduce *shape* is preserved deliberately (partition = map on `region` / `region+metric`, `reduce_aggregate` = reduce emitting monthly mean/min/max/count); and that the aggregate output schema is designed to be unchanged by a real cluster swap.
- [ ] **3. Live satellite / agency data feeds** *(FR-2.1, FR-2.2)* — Document: that satellite support is a **scene-metadata catalogue**, that no raster is ever read, and that the `storage_uri` values produced by the generator point at files that do not exist; that historical data is synthetic (`seed=42`, deterministic, five regions); and that real-time is a **manually triggered simulator** with no autonomous producer. Remove the fake `.tif` URIs or make them resolvable.
- [ ] **4. Tableau and Impala** *(Software list)* — Keep and sharpen the existing README paragraph: FR-7 visualisation is satisfied in-app by Streamlit + Plotly; Tableau and Impala are suggested tools with no required capability behind them; the export path (`aggregates.csv` → Impala external tables → Tableau) remains available if a cluster ever exists.
- [ ] **5. Jupyter/Anaconda, RStudio, VS Code/PyCharm** *(Software list)* — Document explicitly that these are **developer tooling suggestions, not deliverables**: the project is a Python venv with CLI entry points; there is no R code and no requirement implying R; editor choice is immaterial. Optionally add one `notebooks/model_exploration.ipynb` for literal Jupyter compliance, which would also strengthen NFR-7.2. State the decision either way rather than leaving it silent.
- [ ] **6. 99% uptime and load balancing** *(NFR-3.1, NFR-4.2)* — Document: that 99% is an **operational SLO requiring hosting the project does not include** (supervised process, external uptime monitor, restart policy); that the health endpoint (C1-2) and maintenance banner are the in-app portion. For load balancing, commit a concrete `deploy/nginx.conf` sample (upstream with two instances, `proxy_pass`, health check) and note the two hard Streamlit constraints: WebSocket upgrade headers are **mandatory**, and sessions must be sticky (IP hash) because Streamlit holds per-session state on one server — naive round-robin breaks it. State that this must follow C1-23 (shared cache).
- [ ] **7. Encryption at rest and in transit** *(NFR-2.1)* — Document: which layer terminates TLS (a reverse proxy, not the app); that the production security flags presuppose that terminator; that the MongoDB connection is currently unauthenticated plaintext to localhost, with `mongodb://user:pass@host/?tls=true` as the production form; and either that field encryption is now implemented (C1-22) or that no PII beyond email is stored (C2-6) — one of the two must be true and written down.
- [ ] **8. The Streamlit direction itself** — Record in the README that the docx **never names a web framework**, that its only framework-adjacent phrase is "a video clip demonstrating the working of the **Website**", and that Streamlit serves an HTTP web application in a browser and therefore satisfies it. Note the one requirement Streamlit makes materially harder — **FR-1.1/FR-1.2 authentication and role-based access control**, since Streamlit provides no routing layer, no session middleware, no CSRF protection and no per-route authorisation — and state how the project compensates (login gate before render, explicit password hashing, per-page role checks, region scoping in the shared data layer).
- [ ] **9. Update the README assumptions list** *(DEL-8)* — Extend the existing five-item list to cover every substitution above, plus the newly-identified limits: no encryption at rest (or PII removed instead), backups automated only via an OS scheduler, real-time ingestion is simulator-driven, and satellite support is metadata-only.

---

# ADDENDUM — migration delta observed during analysis

The Streamlit migration landed the new `weatherpredict/` package **while this analysis was being written**. The Django tree still exists alongside it. The findings above are written at the capability level and remain valid, but the following items changed under observation and are recorded here so the implementing agent does not redo completed work. Each was verified by reading the new file; anything not re-read is marked for re-verification.

**Already done by the migration — close these items:**

- **C2-1 (unused dependencies) — DONE.** `requirements.txt` is now 11 lines. All nine dependencies flagged in B-1 were removed (`xgboost`, `statsmodels`, `scipy`, `Pillow`, `factory-boy`, `freezegun`, `email-validator`, `channels-redis`, `gunicorn`), along with `whitenoise`, `pytest-cov`, `pytest-django` and Django itself. Added: `streamlit`, `plotly`, `joblib`, `bcrypt`.
- **C1-24 (Streamlit authentication) — SUBSTANTIALLY DONE at the module level.** `weatherpredict/auth.py` replaces Django auth with: bcrypt hashing at 12 rounds (`hash_password`), a correct hand-rolled verifier for legacy Django `pbkdf2_sha256` hashes with transparent re-hash on first login (`_verify_django_pbkdf2`, `needs_rehash`), a bcrypt 72-byte truncation guard, username validation, and a **data-driven `PERMISSIONS` matrix** with `can()` / `require()` raising `PermissionDenied`. `require(acting_user, "manage_users")` is already enforced inside the mutating functions (`set_role`, `set_active`, `admin_create_user`) rather than only at the UI layer, which is the right place for it. This is a stronger authorisation model than the Django decorators it replaces.
- **FR-3.2 / C1-8 (`ensure_indexes`) — PARTIALLY ADDRESSED.** `weatherpredict/db.py::ensure_indexes` now covers the six climate collections **plus** the eleven new Mongo-backed relational collections (`users`, `notifications`, `alert_rules`, `support_tickets`, `feedback`, `pipeline_runs`, `ingestion_jobs`, `ml_artifacts`), including a unique index on `users.username`. **Still to verify: whether anything calls it.** That was the actual defect in the Django build, and the search for callers was inconclusive because files were being rewritten mid-check. Re-verify before closing C1-8.

**Still open and unaffected by the migration — these remain the top gaps:**

- **FR-1.2 data scoping (C1-9)** is still the largest functional gap. `region_focus` is carried through as a field on the `User` dataclass and into `to_session()`, but no `allowed_regions` helper exists and no read path filters on it. The permission matrix gates *actions*, not *rows* — an Analyst can still read every region. The new single-package layout actually makes the fix easier: apply the filter inside `weatherpredict/db.py`'s read helpers rather than in each page.
- **`phone` (C2-6)** survived the migration onto the new `User` dataclass and `create_user`. It is still unread, and still the only PII driving the NFR-2.1 at-rest encryption obligation. Decide now: delete it, or encrypt it.
- All Missing NFRs and deliverables (backups, health endpoint, compliance doc, data-standards doc, DFDs, problem definition, FAQ/tutorial, test data, video) are untouched by the migration and remain exactly as assessed.

**Re-verify before relying on Part A evidence paths:** every file path cited in Part A points at the Django tree. Where a capability has moved (`analytics/services.py` → `weatherpredict/ml.py`, `batch/adapters/base.py` → `weatherpredict/batch/adapters.py`, `dataingestion/` → `weatherpredict/ingestion.py` + `validators.py`, `dashboard/services.py` → `weatherpredict/console.py`), confirm the behaviour carried across before treating the requirement as still satisfied — particularly the leakage controls in the ML layer and the graceful missing-data handling in the batch cleaner, which are the evidence for FR-4.3, FR-6.1 and NFR-6.2.
