"""Correlation analysis — Pearson and Spearman across weather and sensor variables."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from weatherpredict import ml
from weatherpredict.ui import charts, session, theme

user = session.guard("view_analytics")

theme.masthead(
    "Correlation analysis",
    eyebrow="Investigation",
    lead=(
        "Daily means joined per region, then correlated. Sensor metrics that share a name with "
        "a station variable are kept separately with a `sensor_` prefix."
    ),
)

report = ml.get_correlations(user=user)
if not report:
    st.info(
        "No correlation report stored. An Administrator can produce one from "
        "Data & pipeline management."
    )
    st.stop()

regions = session.selectable_regions(user, sorted(report.keys()) if isinstance(report, dict) else [])
if not regions:
    if "pearson" in report or "spearman" in report:
        regions = [user.region_focus] if user.region_focus else []
        report = {regions[0]: report} if regions else {}
if not regions:
    st.warning("No correlation data in your assigned region.")
    st.stop()
c1, c2 = st.columns([1, 1])
region = c1.selectbox("Region", regions, format_func=lambda r: r.replace("_", " ").title())
method = c2.radio(
    "Method", ["pearson", "spearman"], horizontal=True,
    format_func=lambda m: "Pearson (linear)" if m == "pearson" else "Spearman (rank)",
)

data = report[region]
matrix = data.get(method, {})
variables = data.get("variables", [])

theme.stat_strip(
    [
        ("Overlapping days", f"{data.get('n_days', 0):,}", "inner join on date"),
        ("Variables", len(variables), "station + sensor"),
        ("Regions analysed", len(regions), "with sufficient overlap"),
        ("Method", method.title(), "linear" if method == "pearson" else "monotonic"),
    ]
)

theme.caveat(
    "Correlation is not causation, and the colour scale is pinned to the full -1 to +1 range "
    "so a weak coefficient cannot be read as a strong one."
)

charts.show(
    charts.correlation_heatmap(matrix, f"{region.replace('_', ' ').title()} — {method} correlation")
)

left, right = st.columns([1.4, 1], gap="large")

df = pd.DataFrame(matrix)
df = df.reindex(index=df.columns)

with left:
    theme.section("Coefficient matrix")
    st.dataframe(df.round(3), use_container_width=True)
    st.download_button(
        "Download matrix (CSV)",
        df.to_csv().encode("utf-8"),
        file_name=f"correlation_{region}_{method}.csv",
        mime="text/csv",
    )

with right:
    theme.section("Strongest pairs", "excluding self-correlation")
    pairs = []
    cols = list(df.columns)
    for i, a in enumerate(cols):
        for b in cols[i + 1 :]:
            value = df.loc[a, b]
            if pd.notna(value):
                pairs.append({"Variable A": a, "Variable B": b, "r": round(float(value), 3)})
    if pairs:
        table = pd.DataFrame(pairs)
        table["strength"] = table["r"].abs()
        st.dataframe(
            table.sort_values("strength", ascending=False).drop(columns=["strength"]).head(15),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.caption("No variable pairs available.")

    theme.section("Reading this")
    st.markdown(
        """
* Blue cells are negative relationships, coral cells positive — the same
  below/above-normal language used everywhere else in the platform.
* Pearson measures linear association; Spearman measures monotonic association
  and is more robust to the skew in precipitation.
* A region is only analysed when at least 30 overlapping days exist between
  station records and sensor streams.
        """
    )
