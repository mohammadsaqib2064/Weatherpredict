"""Live sensor feed merged with batch history."""
from __future__ import annotations

from datetime import datetime, timezone as dt_timezone

import pandas as pd
import streamlit as st

from weatherpredict import realtime, settings
from weatherpredict.auth import PermissionDenied
from weatherpredict.batch.synthetic import REGIONS
from weatherpredict.ui import charts, session, theme

user = session.guard("view_realtime")

theme.masthead(
    "Live sensor feed",
    eyebrow="Real-time layer",
    lead="Simulated sensor readings merged with the batch history.",
    meta=[("transport", "polling fragment"), ("no", "websockets")],
)

c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
regions = session.selectable_regions(user, list(REGIONS))
if not regions:
    st.error("No region is assigned to this account. Ask an Administrator to set a region focus.")
    st.stop()
default_region = user.region_focus if user.region_focus in regions else regions[0]
region = c1.selectbox(
    "Region", regions, index=regions.index(default_region),
    format_func=lambda r: r.replace("_", " ").title(),
)
metric = c2.selectbox("Metric", ["temp_c", "co2_ppm", "soil_moisture", "uv_index"])
hours = c3.selectbox("Window", [24, 72, 168], index=1, format_func=lambda h: f"{h} hours")
auto = c4.toggle("Auto-refresh", value=False, help=f"Re-reads every {settings.REALTIME_POLL_SECONDS}s")

emit_col, note_col = st.columns([1, 3])
with emit_col:
    if st.button("Emit sensor tick", type="primary", use_container_width=True):
        try:
            docs = realtime.emit_sensor_tick(user=user)
            st.success(f"{len(docs)} readings emitted; threshold rules evaluated on each.")
        except PermissionDenied as exc:
            st.error(str(exc))
with note_col:
    st.caption(
        "Each tick writes readings tagged `source: realtime`, evaluates every active alert rule "
        "against the value, and records a run in the pipeline ledger."
    )


@st.fragment(run_every=settings.REALTIME_POLL_SECONDS if auto else None)
def live_panel() -> None:
    data = realtime.unified_series(region, metric, hours, user=user)
    counts = data["counts"]
    theme.stat_strip(
        [
            ("Merged points", f"{counts['merged']:,}", f"last {hours}h"),
            ("Batch records", f"{counts['weather']:,}", "station observations"),
            ("Live readings", f"{counts['sensors']:,}", "simulated sensors"),
            ("Batch aggregates", len(data["aggregates"]), "monthly rollups"),
            (
                "Last refresh",
                datetime.now(tz=dt_timezone.utc).strftime("%H:%M:%S"),
                "UTC" + (" · auto" if auto else " · manual"),
            ),
        ]
    )
    charts.show(charts.unified_stream(data["points"], region, metric))

    left, right = st.columns([1.3, 1], gap="large")
    with left:
        theme.section("Latest live readings")
        readings = realtime.latest_readings(15, region)
        if readings:
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Sensor": r["sensor_id"],
                            "Metric": r["metric"],
                            "Value": r["value"],
                            "Unit": r.get("unit", ""),
                            "Observed": r["observed_at"],
                        }
                        for r in readings
                    ]
                ),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.caption("No live readings for this region yet — emit a tick.")
    with right:
        theme.section("Batch aggregates", "region rollups feeding the unified view")
        if data["aggregates"]:
            agg = pd.DataFrame(data["aggregates"])
            keep = [c for c in ["period", "source", "temp_c_mean", "value_mean", "precip_mm_mean"] if c in agg.columns]
            st.dataframe(agg[keep].head(24), use_container_width=True, hide_index=True)
        else:
            st.caption("No aggregates stored. Run the batch pipeline.")


live_panel()
