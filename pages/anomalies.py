"""Anomaly investigation — stored findings plus an on-demand detection sweep."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from weatherpredict import console, ml
from weatherpredict.auth import PermissionDenied
from weatherpredict.batch.synthetic import REGIONS
from weatherpredict.db import get_collection
from weatherpredict.ui import charts, session, theme

user = session.guard("view_analytics")

theme.masthead(
    "Anomaly investigation",
    eyebrow="Investigation",
    lead=(
        "Observations that departed from the region's seasonal baseline, flagged by an "
        "Isolation Forest and by an absolute z-score of 3 or more."
    ),
)

session.show_flash("anomalies")

c1, c2, c3 = st.columns([1, 1, 2])
regions = session.selectable_regions(user, list(REGIONS))
region_options = ["", *regions] if user.is_administrator else regions
if not regions:
    st.error("No region is assigned to this account. Ask an Administrator to set a region focus.")
    st.stop()
default = user.region_focus if user.region_focus in regions else ("" if user.is_administrator else regions[0])
idx = region_options.index(default) if default in region_options else 0
region = c1.selectbox(
    "Region", region_options, index=idx,
    format_func=lambda r: r.replace("_", " ").title() if r else "All regions",
)
severity_filter = c2.multiselect("Severity", ["high", "medium", "low"], default=["high", "medium", "low"])

rows = ml.stored_anomalies(region or None, limit=800, user=user)
rows = [r for r in rows if r["severity"] in severity_filter]

with c3:
    st.markdown("&nbsp;", unsafe_allow_html=True)
    if user.can("persist_anomalies"):
        if st.button("Re-run detection sweep", help="Upserts findings — never duplicates"):
            try:
                session.act("persist_anomalies")
                before = get_collection("anomalies").count_documents({})
                found = ml.detect_anomalies(region or None, persist=True)
                after = get_collection("anomalies").count_documents({})
                console.invalidate_cache()
                session.flash(
                    "anomalies",
                    f"{len(found)} observations flagged; stored documents {before} -> {after} "
                    "(existing findings updated in place).",
                )
                st.rerun()
            except FileNotFoundError as exc:
                st.error(str(exc))
            except PermissionDenied as exc:
                st.error(str(exc))
    else:
        st.caption("Detection sweeps are an Administrator action.")

if not rows:
    st.info("No stored anomalies match this filter. An Administrator can run a detection sweep.")
    st.stop()

df = pd.DataFrame(rows)
df["observed_at_dt"] = pd.to_datetime(df["observed_at"], utc=True, errors="coerce")
high = int((df["severity"] == "high").sum())

theme.stat_strip(
    [
        ("Findings", f"{len(df):,}", "matching filter"),
        ("!High severity", high, "|z| >= 4"),
        ("Medium", int((df["severity"] == "medium").sum()), "|z| >= 3"),
        ("Peak |z|", f"{df['z_score'].abs().max():.2f}", "largest departure"),
        ("Regions", df["region"].nunique(), "affected"),
    ]
)

theme.caveat(
    "Severity is derived from a seasonal z-score against a baseline built from the training "
    "period only. These are statistical departures, not confirmed extreme-weather events."
)

charts.show(charts.anomaly_scatter(rows))

left, right = st.columns([1.6, 1], gap="large")

with left:
    theme.section("Findings", "most recent first")
    st.dataframe(
        df[["region", "observed_at", "value", "baseline", "z_score", "severity", "method"]]
        .assign(
            observed_at=df["observed_at"].str[:10],
            baseline=df["baseline"].round(2),
            value=df["value"].round(2),
        )
        .rename(
            columns={
                "region": "Region",
                "observed_at": "Observed",
                "value": "Value °C",
                "baseline": "Baseline °C",
                "z_score": "z",
                "severity": "Severity",
                "method": "Method",
            }
        ),
        use_container_width=True,
        hide_index=True,
        height=420,
    )
    st.download_button(
        "Download findings (CSV)",
        df.drop(columns=["observed_at_dt"]).to_csv(index=False).encode("utf-8"),
        file_name="anomalies.csv",
        mime="text/csv",
    )

with right:
    theme.section("By region")
    summary = (
        df.groupby("region")
        .agg(findings=("z_score", "size"), peak_abs_z=("z_score", lambda s: s.abs().max()))
        .reset_index()
        .sort_values("findings", ascending=False)
    )
    st.dataframe(
        summary.rename(columns={"region": "Region", "findings": "Findings", "peak_abs_z": "Peak |z|"}),
        use_container_width=True,
        hide_index=True,
    )

    theme.section("By month")
    monthly = (
        df.dropna(subset=["observed_at_dt"])
        .assign(month=lambda d: d["observed_at_dt"].dt.to_period("M").astype(str))
        .groupby("month")
        .size()
        .reset_index(name="findings")
    )
    st.dataframe(
        monthly.rename(columns={"month": "Month", "findings": "Findings"}),
        use_container_width=True,
        hide_index=True,
        height=260,
    )

    theme.section("Detection method")
    st.markdown(
        """
* Daily regional means are compared to a per-region, per-day-of-year mean and
  standard deviation computed **only** from the training window.
* An Isolation Forest scores `(temp, z, day-of-year)`; a finding is raised when the
  forest flags the point **or** `|z| >= 3`.
* Persisted findings are upserted on `(region, metric, observed_at)` under a unique
  index, so repeated sweeps update rather than duplicate, and notifications fire
  only for genuinely new findings.
        """
    )
