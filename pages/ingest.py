"""Data ingestion — CSV / JSON / XLSX upload with validation and a job ledger."""
from __future__ import annotations

import io

import pandas as pd
import streamlit as st

from weatherpredict import console, ingestion
from weatherpredict.auth import PermissionDenied
from weatherpredict.ui import session, theme
from weatherpredict.validators import ValidationError

user = session.guard("ingest_data")

theme.masthead(
    "Data ingestion",
    eyebrow="Intake",
    lead=(
        "Import satellite scene metadata, weather-station records and environmental sensor "
        "readings. Rows with missing optional fields are kept and flagged; malformed rows are "
        "skipped and reported."
    ),
    meta=[("accepted", "csv · json · xlsx"), ("max size", "10 MB")],
)

session.show_flash("ingest")

stats = ingestion.ingestion_stats()
theme.stat_strip(
    [
        ("Jobs run", stats["jobs"], ""),
        ("Rows imported", f"{stats['records_imported']:,}", "written to MongoDB"),
        ("Rows skipped", f"{stats['records_skipped']:,}", "invalid or empty"),
        (
            "Completed",
            stats["by_status"].get("completed", 0),
            f"{stats['by_status'].get('failed', 0)} failed",
        ),
    ]
)

upload_col, guide_col = st.columns([1.5, 1], gap="large")

with upload_col:
    theme.section("Upload a file")
    data_type = st.selectbox(
        "Dataset", list(ingestion.DATA_TYPES), format_func=lambda k: ingestion.DATA_TYPES[k]
    )
    uploaded = st.file_uploader("File", type=["csv", "json", "xlsx"], label_visibility="collapsed")
    if uploaded is not None and st.button("Validate and import", type="primary"):
        try:
            job = ingestion.ingest_upload(
                io.BytesIO(uploaded.getvalue()), uploaded.name, data_type, user
            )
            console.invalidate_cache()
            if job["status"] == ingestion.COMPLETED:
                session.flash(
                    "ingest",
                    f"{job['records_imported']} rows imported, {job['records_skipped']} skipped "
                    f"from {job['filename']}.",
                )
            else:
                session.flash("ingest", f"Import failed: {job['error_log'][:400]}", "error")
            st.rerun()
        except ValidationError as exc:
            st.error(f"Rejected: {exc}")
        except PermissionDenied as exc:
            st.error(str(exc))
        except Exception as exc:  # noqa: BLE001
            st.error(f"Ingestion failed: {exc}")

with guide_col:
    theme.section("Expected columns")
    st.markdown(
        """
**Weather station** — `station_id`, `region`, `observed_at`, `temp_c`
(optional: `precip_mm`, `humidity_pct`, `wind_ms`, `pressure_hpa`, `lat`, `lon`, `name`)

**Environmental sensor** — `sensor_id`, `region`, `metric`, `value`, `observed_at`
(optional: `unit`, `quality`)

**Satellite metadata** — `scene_id`, `satellite`, `region`, `acquired_at`
(optional: `cloud_cover_pct`, `bands`, `bbox`, `storage_uri`)
        """
    )
    st.caption(
        "Blank rows are ignored. A weather row missing only optional measurements is imported "
        "with those fields recorded in `missing_fields`. Satellite scenes upsert on `scene_id`, "
        "so re-uploading a manifest refreshes rather than duplicates."
    )

theme.section("Ingestion ledger", "50 most recent jobs")
jobs = ingestion.recent_jobs(50)
if jobs:
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "File": j["filename"],
                    "Dataset": ingestion.DATA_TYPES.get(j["data_type"], j["data_type"]),
                    "Status": j["status"],
                    "Total": j.get("records_total", 0),
                    "Imported": j.get("records_imported", 0),
                    "Skipped": j.get("records_skipped", 0),
                    "By": j.get("uploaded_by") or "—",
                    "Created": j.get("created_at"),
                }
                for j in jobs
            ]
        ),
        use_container_width=True,
        hide_index=True,
    )
    failed = [j for j in jobs if j.get("error_log")]
    if failed:
        with st.expander(f"Validation reports ({len(failed)} job(s) with skipped rows)"):
            for j in failed[:10]:
                st.markdown(f"**{j['filename']}**")
                st.code(j["error_log"][:2000] or "—", language="text")
else:
    st.caption("No ingestion jobs recorded yet.")
