"""Administrator operations console — system health, throughput, recent activity."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from weatherpredict import console
from weatherpredict.health import status as health_status
from weatherpredict.ui import charts, session, theme

user = session.guard("view_admin_console")

overview = console.system_overview(refresh=st.session_state.pop("wp_force_refresh", False))

theme.masthead(
    "Operations console",
    eyebrow="Administrator",
    lead=(
        "Platform state across the climate corpus, the batch and real-time pipelines, "
        "and the accounts consuming them."
    ),
    meta=[
        ("MongoDB", "connected" if overview["mongo_ok"] else "unreachable"),
        ("signed in as", user.username),
    ],
)

if not overview["mongo_ok"]:
    st.error("MongoDB is unreachable. Counters and pipeline controls are unavailable.")
    st.stop()

_, refresh_col = st.columns([3, 1])
with refresh_col:
    if st.button("Refresh counters", use_container_width=True):
        console.invalidate_cache()
        st.session_state["wp_force_refresh"] = True
        st.rerun()

theme.health_bar(
    overview["health"],
    [
        ("Pipeline runs", overview["pipeline_runs"]),
        ("Succeeded (7d)", overview["pipeline_success_week"]),
        ("Failed (7d)", overview["pipeline_failed_week"]),
        ("Running now", overview["pipeline_running"]),
        ("Active alert rules", overview["alert_rules"]),
        ("Open tickets", overview["open_tickets"]),
    ],
)

theme.stat_strip(
    [
        ("Weather records", f"{overview['weather_records']:,}", "station observations"),
        ("Sensor readings", f"{overview['sensor_readings']:,}", "environmental streams"),
        ("Satellite scenes", f"{overview['satellite_scenes']:,}", "metadata only"),
        ("Batch aggregates", f"{overview['batch_aggregates']:,}", "region × period rollups"),
        ("!Stored anomalies", f"{overview['anomalies']:,}", "deduplicated findings"),
    ]
)

theme.stat_strip(
    [
        ("Accounts", overview["users"], f"{overview['active_users']} active"),
        ("Administrators", overview["administrators"], "full control"),
        ("Analysts", overview["analysts"], "investigation only"),
        ("Ingestion jobs", overview["ingestion_jobs"], f"{overview['records_imported']:,} rows imported"),
        ("!Unread alerts", overview["unread_notifications"], "across all accounts"),
    ]
)

left, right = st.columns([1.6, 1], gap="large")

with left:
    theme.section("Pipeline activity", "10 most recent runs")
    runs = overview["recent_pipelines"]
    if runs:
        df = pd.DataFrame(
            [
                {
                    "Job": r.get("job_type", ""),
                    "Status": r.get("status", ""),
                    "Adapter": r.get("adapter", ""),
                    "Started": r.get("started_at"),
                    "Duration s": r.get("duration_seconds") or "—",
                    "By": r.get("triggered_by") or "—",
                    "Detail": ", ".join(
                        f"{k}={v}" for k, v in list((r.get("stats") or {}).items())[:3]
                    )
                    or (r.get("error") or ""),
                }
                for r in runs
            ]
        )
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.caption("No pipeline runs recorded yet.")

    theme.section("Regional temperature", "mean of all stored station observations")
    regions = console.region_temp_summary()
    charts.show(charts.region_bar(regions) if regions else charts.empty("No regional data"))

with right:
    theme.section("Ingestion", "job ledger")
    ingest_rows = overview["recent_ingestions"]
    if ingest_rows:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "File": r.get("filename", ""),
                        "Type": r.get("data_type", ""),
                        "Status": r.get("status", ""),
                        "In": r.get("records_imported", 0),
                        "Skip": r.get("records_skipped", 0),
                        "By": r.get("uploaded_by") or "—",
                    }
                    for r in ingest_rows
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.caption("No uploads yet. Use Data ingestion to import a file.")
    if overview["ingest_by_status"]:
        st.caption(
            "By status: "
            + ", ".join(f"{k} {v}" for k, v in sorted(overview["ingest_by_status"].items()))
        )

    theme.section("Latest alerts", "threshold breaches")
    alerts = overview["recent_alerts"]
    if alerts:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Alert": a.get("title", ""),
                        "Severity": a.get("severity", ""),
                        "To": a.get("username", ""),
                        "Read": "yes" if a.get("is_read") else "no",
                        "At": a.get("created_at"),
                    }
                    for a in alerts
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.caption("No notifications yet.")

    theme.section("Accounts", "most recently added")
    users = overview["recent_users"]
    if users:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "User": u["username"],
                        "Role": u["role"].title(),
                        "Active": "yes" if u["is_active"] else "no",
                        "Focus": u["region_focus"] or "—",
                    }
                    for u in users
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )

theme.section("Host resources", "this Streamlit process — single worker")
hs = health_status()
res = hs.get("resources") or {}
theme.stat_strip(
    [
        ("Mongo", "up" if hs.get("mongo") else "down", hs.get("app", "")),
        ("Disk free", f"{res.get('disk_free_gb', '—')} GB", "of host volume"),
        ("PID", res.get("pid", "—"), "single-worker process"),
        ("Last pipeline", (hs.get("last_pipeline") or {}).get("status") or "—", (hs.get("last_pipeline") or {}).get("job_type") or ""),
    ]
)
