"""Data and pipeline management (Administrator)."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from weatherpredict import console, ml, pipelines
from weatherpredict.batch import generate_synthetic_dataset, run_batch_pipeline
from weatherpredict.batch.adapters import HadoopAdapter
from weatherpredict.db import collection_counts
from weatherpredict.ui import session, theme

user = session.guard("generate_data")

theme.masthead(
    "Data & pipeline management",
    eyebrow="Administrator",
    lead=(
        "Generate the synthetic corpus, run the batch clean/partition/aggregate layer, "
        "and retrain the models. Every run is written to the pipeline ledger."
    ),
    meta=[("adapters", "local pandas · Hadoop interface")],
)

session.show_flash("data_ops")

counts = collection_counts()
theme.stat_strip(
    [
        ("Weather records", f"{counts.get('weather_station_records', 0):,}", ""),
        ("Sensor readings", f"{counts.get('sensor_readings', 0):,}", ""),
        ("Satellite scenes", f"{counts.get('satellite_imagery', 0):,}", ""),
        ("Batch aggregates", f"{counts.get('batch_aggregates', 0):,}", ""),
        ("Stored predictions", f"{counts.get('ml_predictions', 0):,}", ""),
    ]
)

gen, batch, train = st.columns(3, gap="large")

with gen:
    theme.section("Synthetic corpus")
    st.caption(
        "Multi-year daily station records, environmental sensor streams and weekly "
        "satellite scene metadata for five regions."
    )
    years = st.slider("Years of history", 1, 5, 3)
    clear = st.checkbox("Replace existing synthetic rows", value=True, help="Uploads and live ticks are kept.")
    if st.button("Generate dataset", type="primary", use_container_width=True):
        run = session.run_action(
            "generate_data", "Generating climate corpus", generate_synthetic_dataset,
            years=years, clear_existing=clear,
        )
        if run:
            console.invalidate_cache()
            session.flash("data_ops", f"Synthetic dataset generated: {run['stats']}")
            st.rerun()

with batch:
    theme.section("Batch layer")
    st.caption(
        "Clean, partition by region (and metric), write CSV partitions, then reduce to "
        "monthly aggregates upserted into MongoDB."
    )
    adapter = st.selectbox(
        "Processing adapter",
        ["local", "hadoop"],
        format_func=lambda a: "Local pandas fallback" if a == "local" else "Hadoop / HDFS interface",
    )
    if adapter == "hadoop":
        st.info(HadoopAdapter().submit_mapreduce("clean_partition_reduce", "raw/*.csv")["message"])
    if st.button("Run batch pipeline", type="primary", use_container_width=True):
        run = session.run_action(
            "run_batch", "Running batch pipeline", run_batch_pipeline, adapter_name=adapter
        )
        if run:
            console.invalidate_cache()
            if run["status"] == "success":
                session.flash("data_ops", f"Batch pipeline succeeded: {run['stats']}")
            else:
                session.flash("data_ops", f"Batch pipeline failed: {run['error']}", "error")
            st.rerun()

with train:
    theme.section("Model training")
    st.caption(
        "Trains per-region trend models, the anomaly baseline and the correlation report, "
        "then persists a deduplicated anomaly sweep."
    )
    theme.caveat(
        "Training reports MAE against a lag-1 persistence baseline, and anomaly "
        "precision/recall against proxy labels (|z| > 3) — not verified extreme events."
    )
    if st.button("Train all models", type="primary", use_container_width=True):
        run = session.run_action("train_ml", "Training models", ml.train_all)
        if run:
            console.invalidate_cache()
            session.flash("data_ops", f"Training complete: {run['stats']}")
            st.rerun()

theme.section("Model artifacts", "active registry entries")
artifacts = ml.list_artifacts()
if artifacts:
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Artifact": a["name"],
                    "Task": a["task"],
                    "Version": a["version"],
                    "Trained": a.get("trained_at"),
                    "Path": a["path"],
                }
                for a in artifacts
            ]
        ),
        use_container_width=True,
        hide_index=True,
    )
    with st.expander("Metrics detail"):
        for a in artifacts:
            st.markdown(f"**{a['name']}** — {a.get('notes', '')}")
            st.json(a.get("metrics", {}), expanded=False)
else:
    st.caption("No trained artifacts yet. Run training above.")

theme.section("Pipeline ledger", "50 most recent runs")
runs = pipelines.recent_runs(50)
if runs:
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Job": pipelines.JOB_LABELS.get(r["job_type"], r["job_type"]),
                    "Status": r["status"],
                    "Adapter": r.get("adapter", ""),
                    "Started": r.get("started_at"),
                    "Finished": r.get("finished_at"),
                    "By": r.get("triggered_by") or "—",
                    "Error": (r.get("error") or "")[:120],
                }
                for r in runs
            ]
        ),
        use_container_width=True,
        hide_index=True,
        height=420,
    )
else:
    st.caption("No pipeline runs recorded.")

with st.expander("Production upgrade path — Hadoop / HDFS / MapReduce"):
    st.markdown(
        """
The batch layer is written against the `BatchAdapter` contract
(`clean` / `partition` / `reduce_aggregate` / `write_partitions`). Swapping the
local pandas implementation for a cluster does not change any calling code:

1. Set `HDFS_NAMENODE` / `YARN_RM` and stage raw drops under
   `hdfs://.../weatherpredict/raw/`.
2. Select the **Hadoop / HDFS interface** adapter above; `HadoopAdapter.submit_mapreduce`
   is the hook that submits the job.
3. Write cleaned partitions and monthly aggregates to
   `hdfs://.../weatherpredict/processed/`.
4. Expose that path as Impala external tables and point Tableau at Impala;
   WeatherPredict remains the ML and alerting control plane.
        """
    )
