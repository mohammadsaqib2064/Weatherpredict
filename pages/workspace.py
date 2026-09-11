"""Analyst exploration workspace — the entry point for investigation work."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from weatherpredict import console
from weatherpredict.batch.synthetic import REGIONS
from weatherpredict.ui import charts, session, theme

user = session.guard("view_workspace")

snapshot = console.analyst_exploration_snapshot(user=user)
overview = snapshot["overview"]

theme.masthead(
    "Analyst workspace",
    eyebrow="Investigation",
    lead=(
        "Start from the regional picture, then follow a signal into trends, anomalies "
        "or cross-variable correlation."
    ),
    meta=[
        ("regions monitored", str(len(REGIONS))),
        ("focus", user.region_focus.replace("_", " ") or "all regions"),
    ],
)

if not overview["mongo_ok"]:
    st.error("MongoDB is unreachable — no climate data can be read.")
    st.stop()

theme.stat_strip(
    [
        ("Station observations", f"{overview['weather_records']:,}", "daily records"),
        ("Sensor readings", f"{overview['sensor_readings']:,}", "co2 · soil · uv · temp"),
        ("Satellite scenes", f"{overview['satellite_scenes']:,}", "metadata"),
        ("!Stored anomalies", f"{overview['anomalies']:,}", "seasonal baseline breaches"),
    ]
)

main, rail = st.columns([1.7, 1], gap="large")

with main:
    theme.section("Regional temperature profile", "mean, with departure from the all-region mean")
    regions = snapshot["regions"]
    charts.show(charts.region_bar(regions) if regions else charts.empty("No regional data yet"))

    theme.section("Recent anomalies", "most recent stored findings")
    anomalies = snapshot["anomalies"]
    if anomalies:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Region": a["region"],
                        "Observed": a["observed_at"][:10],
                        "Value °C": a["value"],
                        "Baseline °C": round(a["baseline"], 2) if a["baseline"] is not None else None,
                        "z": a["z_score"],
                        "Severity": a["severity"],
                    }
                    for a in anomalies
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.caption("No anomalies stored. An Administrator must run ML training first.")

with rail:
    theme.section("Investigation paths")
    st.page_link("pages/explore.py", label="Data exploration", icon=":material/explore:")
    st.caption("Filter the corpus by region and window; inspect distributions.")
    st.page_link("pages/trends.py", label="Trend prediction", icon=":material/trending_up:")
    st.caption("Roll a regional model forward with an honest uncertainty band.")
    st.page_link("pages/anomalies.py", label="Anomaly investigation", icon=":material/warning:")
    st.caption("Review flagged observations against the seasonal baseline.")
    st.page_link("pages/correlations.py", label="Correlation analysis", icon=":material/grid_on:")
    st.caption("Pearson and Spearman across weather and sensor variables.")
    st.page_link("pages/live.py", label="Live sensor feed", icon=":material/sensors:")
    st.caption("Batch history merged with the simulated real-time stream.")

    theme.section("Your assignment")
    st.caption("Analyst views are limited to this region. Ask an Administrator to change it.")
    st.write(user.region_focus.replace("_", " ").title() or "No region assigned")

    theme.section("Regional coverage")
    st.dataframe(
        pd.DataFrame(
            [
                {"Region": r.replace("_", " ").title(), "Lat": m["lat"], "Lon": m["lon"]}
                for r, m in REGIONS.items()
            ]
        ),
        use_container_width=True,
        hide_index=True,
    )
