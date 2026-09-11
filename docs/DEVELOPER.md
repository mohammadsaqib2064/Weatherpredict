# WeatherPredict — Developer Documentation

## Layout

```
app.py                 Streamlit entry (login + nav)
pages/                 one module per screen
weatherpredict/        domain package (auth, db, ml, batch, realtime, …)
tests/                 pytest
data/test_data/        curated ingest samples
data/raw|processed|synthetic   runtime folders (.gitkeep only)
ml_artifacts/          trained joblib + evaluation notes
docs/                  guides, architecture, diagrams, compliance
scripts/               submission packager
.streamlit/            theme + server config
```

## Settings

`weatherpredict/settings.py` reads `.env`. Copy `.env.example`.

## MongoDB

`weatherpredict.db.get_collection(name)` — `ensure_indexes()` runs at Streamlit start.

## Batch adapter

`weatherpredict.batch.adapters.BatchAdapter`: `partition`, `clean`, `reduce_aggregate`, `write_partitions`. Local adapter writes CSV under `data/processed/`. Hadoop adapter documents HDFS paths and does not submit MapReduce until configured.

## ML

`weatherpredict.ml.train_all(user=admin)` — time-based split, lag features, naive baseline. Artifacts are versioned. See `ml_artifacts/MODEL_EVALUATION.md`.

## Auth

`authenticate` / `require` / `scoping.constrain_region`. Tests live in `tests/test_auth.py` and `tests/test_scoping.py`.

## Testing

```
python -m pytest
```

Uses database `weatherpredict_test` and **will not** drop the `weatherpredict` demo database.
