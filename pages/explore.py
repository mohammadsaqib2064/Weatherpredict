"""Data exploration — regional series, distributions and the raw record view."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from weatherpredict import console
from weatherpredict.batch.synthetic import REGIONS
from weatherpredict.db import get_collection
from weatherpredict.ui import charts, session, theme

user = session.guard("view_analytics")

theme.masthead(
    "Data exploration",
    eyebrow="Investigation",
    lead="Inspect the stored corpus one region at a time before committing to a hypothesis.",
)

default_region = user.region_focus if user.region_focus in REGIONS else list(REGIONS)[0]
controls = st.columns([1, 1, 1, 1])
regions = session.selectable_regions(user, list(REGIONS))
if not regions:
    st.error("No region is assigned to this account. Ask an Administrator to set a region focus.")
    st.stop()
default_region = user.region_focus if user.region_focus in regions else regions[0]
region = controls[0].selectbox(
    "Region", regions, index=regions.index(default_region),
    format_func=lambda r: r.replace("_", " ").title(),
)
window = controls[1].selectbox("Window", [90, 180, 365, 730], index=2, format_func=lambda d: f"{d} days")
variable = controls[2].selectbox(
    "Variable", ["temp_c", "precip_mm", "humidity_pct"],
    format_func=lambda v: {"temp_c": "Temperature °C", "precip_mm": "Precipitation mm", "humidity_pct": "Humidity %"}[v],
)
sensor_metric = controls[3].selectbox("Sensor metric", ["co2_ppm", "soil_moisture", "uv_index"])

rows = console.daily_region_frame(region, window, user=user)
if not rows:
    st.warning("No stored observations for this region.")
    st.stop()

df = pd.DataFrame(rows)
df["observed_at"] = pd.to_datetime(df["observed_at"], utc=True)
series = df.dropna(subset=[variable])

theme.stat_strip(
    [
        ("Observations", f"{len(df):,}", f"last {window} days"),
        ("Mean", f"{series[variable].mean():.2f}", variable),
        ("Minimum", f"{series[variable].min():.2f}", str(series.loc[series[variable].idxmin(), 'observed_at'].date())),
        ("Maximum", f"{series[variable].max():.2f}", str(series.loc[series[variable].idxmax(), 'observed_at'].date())),
        ("Missing", int(df[variable].isna().sum()), "kept, flagged"),
    ]
)

left, right = st.columns([1.7, 1], gap="large")

with left:
    theme.section(f"{region.replace('_', ' ').title()} — {variable} over time")
    charts.show(
        charts.series_line(series, "observed_at", variable, f"Daily {variable}", variable)
    )

    theme.section("Environmental sensor stream", sensor_metric)
    sensor_docs = list(
        get_collection("sensor_readings")
        .find({"region": region, "metric": sensor_metric}, {"_id": 0, "observed_at": 1, "value": 1})
        .sort("observed_at", -1)
        .limit(window)
    )
    if sensor_docs:
        sdf = pd.DataFrame(sensor_docs).sort_values("observed_at")
        charts.show(charts.series_line(sdf, "observed_at", "value", f"{sensor_metric} readings", sensor_metric))
    else:
        charts.show(charts.empty(f"No {sensor_metric} readings stored for this region"))

with right:
    theme.section("Distribution")
    charts.show(charts.distribution(series[variable].tolist(), f"{variable} distribution", variable))

    theme.section("Records", "most recent first")
    st.dataframe(
        df.sort_values("observed_at", ascending=False)
        .head(200)
        .rename(
            columns={
                "observed_at": "Observed",
                "temp_c": "Temp °C",
                "precip_mm": "Precip mm",
                "humidity_pct": "Humidity %",
            }
        ),
        use_container_width=True,
        hide_index=True,
        height=340,
    )
    st.download_button(
        "Download this window (CSV)",
        df.to_csv(index=False).encode("utf-8"),
        file_name=f"{region}_{window}d.csv",
        mime="text/csv",
        use_container_width=True,
    )
