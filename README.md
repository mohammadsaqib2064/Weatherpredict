# WeatherPredict

Climate-data intelligence platform for **EarthScape Climate Agency**.

Ingest satellite *metadata*, weather-station records and environmental sensor readings; run a batch pipeline plus a simulated near-real-time feed; detect anomalies; forecast regional temperature trends; and explore correlations — with role-based access for Administrators and Analysts.

The client brief never names a web framework. It asks for a **Website**. This app is a Streamlit HTTP application served in the browser.

## Architecture summary

| Layer | Choice |
|-------|--------|
| App | Python + Streamlit (multipage UI) |
| Auth | bcrypt hashes in MongoDB `users`; per-page + per-function RBAC |
| Data access | Analysts are scoped to `region_focus`; Administrators see all regions |
| Store | MongoDB only (climate documents + users, alerts, tickets, jobs, artifacts) |
| Batch | Local pandas adapter + documented Hadoop/HDFS/MapReduce upgrade seam |
| Realtime | Simulated sensor ticks; Streamlit `st.fragment` refresh (no WebSockets) |
| ML | scikit-learn (Ridge / GBR trends, IsolationForest anomalies, Pearson/Spearman) |
| Charts | Plotly, climate diverging scales (navy below / coral above) |

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and [docs/DIAGRAMS.md](docs/DIAGRAMS.md).

## Assumptions

1. MongoDB is available at `mongodb://localhost:27017`.
2. Climate history for demos is **synthetic** (`python -m weatherpredict.seed --with-data`), not a live satellite or agency feed. Satellite support is a **metadata catalogue** — no rasters are read.
3. Hadoop/HDFS/MapReduce, Tableau and Impala are **out of scope** for the local demo. Upgrade paths are documented below and in docs/ARCHITECTURE.md.
4. Demo passwords are for local evaluation only.
5. Real-time ingestion is a **manually triggered simulator**, merged with batch history in one view.
6. No PII is stored beyond username, email and role. There is no phone field; TLS is terminated at a reverse proxy in production (`mongodb://user:pass@host/?tls=true`).
7. 99% uptime is an **operational SLO** of the host, not something a workstation demo can guarantee. `python -m weatherpredict.health` and Streamlit `/_stcore/health` are the in-app probes.
8. The app is **single-worker**. Streamlit session state lives in one process — load-balancing needs sticky sessions (see docs/SECURITY_RELIABILITY.md).
9. Jupyter, RStudio and a specific IDE are suggested tooling in the brief, not deliverables. The project is a Python venv with CLI entry points.

## Quick start (Windows)

Open a terminal in the project root — the directory that contains `app.py` and `requirements.txt`.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
python -m weatherpredict.seed --with-data --years 2 --train
streamlit run app.py
```

Open the URL Streamlit prints (usually http://127.0.0.1:8501/).

### Default credentials

| Role | Username | Password | Data scope |
|------|----------|----------|------------|
| Administrator | `admin` | `AdminPass123!` | All regions |
| Analyst | `analyst` | `AnalystPass123!` | `pacific_nw` only |

## Common commands

```powershell
python -m weatherpredict.seed                  # demo users + default alert rules
python -m weatherpredict.seed --with-data --train
python -m weatherpredict.retrain               # versioned ML refresh
python -m weatherpredict.backup                # mongodump or JSON fallback
python -m weatherpredict.health                # JSON health (exit 2 if Mongo down)
python -m pytest
streamlit run app.py
python scripts/make_submission.py              # ReadMe.doc + dist/WeatherPredict-submission.zip
```

## Production upgrade path

### Hadoop / HDFS / MapReduce

Local processing is single-process pandas. `weatherpredict.batch.adapters.HadoopAdapter` keeps the same `partition` / `clean` / `reduce_aggregate` / `write_partitions` contract; `submit_mapreduce` currently returns `not_configured`.

Intended HDFS layout:

- `hdfs://<nn>/weatherpredict/raw/<datatype>/dt=<date>/`
- `hdfs://<nn>/weatherpredict/processed/<datatype>/region=<r>/`

Upgrade: implement `write_partitions` against `pyarrow.fs.HadoopFileSystem`, set `HDFS_NAMENODE`, run with `--adapter hadoop`. Aggregate output schema stays the same.

### Tableau / Impala

Visualisation is in-app (Streamlit + Plotly). Tableau and Impala are optional BI tools. Export `data/processed/**/aggregates.csv` to Impala external tables if a cluster exists.

### TLS, backups, scaling

- Terminate TLS at nginx (or equivalent). Use `mongodb://user:pass@host/?tls=true` in production.
- Schedule `python -m weatherpredict.backup` nightly via Task Scheduler (see docs/SECURITY_RELIABILITY.md).
- For more than one Streamlit process: sticky sessions (IP hash) and a shared cache. Naive round-robin breaks login state.

## Documentation

- [Problem definition](docs/PROBLEM_DEFINITION.md)
- [Architecture](docs/ARCHITECTURE.md)
- [User guide](docs/USER_GUIDE.md) (includes FAQ + tutorial)
- [Developer docs](docs/DEVELOPER.md)
- [Security & reliability](docs/SECURITY_RELIABILITY.md)
- [Compliance](docs/COMPLIANCE.md)
- [Data standards](docs/DATA_STANDARDS.md)
- [Diagrams](docs/DIAGRAMS.md)
- [Demo script](docs/DEMO_SCRIPT.md)
- [ML evaluation notes](ml_artifacts/MODEL_EVALUATION.md)
- [Requirements traceability](REQUIREMENTS_TRACEABILITY.md)
- [Test data](data/test_data/README.md)
- [Design notes](docs/DESIGN_NOTES.md)

## Known limitations

- No live satellite downlink — metadata only; generated `storage_uri` values are catalogue keys, not rasters on disk.
- Local Hadoop adapter does not submit YARN jobs.
- Anomaly precision/recall are against proxy labels (`|z|>3`), not verified extremes.
- NetCDF (`.nc`) ingestion is not implemented; CSV/JSON/XLSX cover the demo. A CF mapping is documented in docs/DATA_STANDARDS.md.
