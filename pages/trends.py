"""Trend prediction — roll a trained regional model forward."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from weatherpredict import ml, settings
from weatherpredict.batch.synthetic import REGIONS
from weatherpredict.scoping import constrain_region
from weatherpredict.ui import charts, session, theme

user = session.guard("view_analytics")

theme.masthead(
    "Trend prediction",
    eyebrow="Investigation",
    lead=(
        "Daily mean temperature forecast from lag features only — no future covariates, "
        "and a strictly time-ordered train/test split."
    ),
)


@st.cache_data(ttl=settings.ANALYTICS_CACHE_SECONDS, show_spinner=False)
def _forecast(region: str, horizon: int) -> dict:
    """Deterministic for a given region and corpus, so repeat visits are cached."""
    return ml.predict_trend(region, horizon_days=horizon, user=None)


default_region = user.region_focus if user.region_focus in REGIONS else list(REGIONS)[0]
c1, c2, c3 = st.columns([1, 1, 2])
regions = session.selectable_regions(user, list(REGIONS))
if not regions:
    st.error("No region is assigned to this account. Ask an Administrator to set a region focus.")
    st.stop()
default_region = user.region_focus if user.region_focus in regions else regions[0]
region = c1.selectbox(
    "Region", regions, index=regions.index(default_region),
    format_func=lambda r: r.replace("_", " ").title(),
)
horizon = c2.slider("Horizon (days)", 7, 90, 30, step=7)
region = constrain_region(user, region)
if c3.button("Recompute", help="Clear the cached forecast for this region"):
    _forecast.clear()
    st.rerun()

try:
    with st.spinner("Rolling the model forward..."):
        prediction = _forecast(region, horizon)
except FileNotFoundError as exc:
    st.warning(f"{exc}")
    st.caption("An Administrator can train models from Data & pipeline management.")
    st.stop()
except Exception as exc:  # noqa: BLE001
    st.error(f"Forecast unavailable: {exc}")
    st.stop()

metrics = prediction.get("metrics") or {}
selected = prediction.get("selected_model")
best = metrics.get(selected, {}) if isinstance(metrics, dict) else {}

theme.stat_strip(
    [
        ("Selected model", (selected or "—").upper(), "lowest held-out MAE"),
        ("Test MAE", f"{best.get('mae', '—')}", "°C, held-out window"),
        ("Naive lag-1 MAE", f"{best.get('naive_lag1_mae', '—')}", "persistence baseline"),
        ("Beats baseline", "yes" if best.get("beat_naive") else "no", "MAE vs persistence"),
        ("Horizon", f"{len(prediction['series'])} d", "recursive rollout"),
    ]
)

if best and not best.get("beat_naive", False):
    theme.caveat(
        "This model does not beat a lag-1 persistence baseline on the held-out window. "
        "Treat the forecast as indicative only — reported here rather than hidden."
    )

charts.show(charts.forecast_chart(prediction.get("history", []), prediction["series"], region))

left, right = st.columns([1.4, 1], gap="large")

with left:
    theme.section("Forecast values")
    st.dataframe(
        pd.DataFrame(prediction["series"]).rename(
            columns={"date": "Date", "yhat": "Forecast °C", "yhat_lower": "Lower", "yhat_upper": "Upper"}
        ),
        use_container_width=True,
        hide_index=True,
        height=360,
    )
    st.download_button(
        "Download forecast (CSV)",
        pd.DataFrame(prediction["series"]).to_csv(index=False).encode("utf-8"),
        file_name=f"forecast_{region}_{horizon}d.csv",
        mime="text/csv",
    )

with right:
    theme.section("Candidate models", "time-based 80/20 split")
    if isinstance(metrics, dict) and metrics:
        rows = [
            {
                "Model": name.upper(),
                "MAE": m.get("mae"),
                "RMSE": m.get("rmse"),
                "R²": m.get("r2"),
                "Naive MAE": m.get("naive_lag1_mae"),
                "Selected": "yes" if name == selected else "",
            }
            for name, m in metrics.items()
            if isinstance(m, dict)
        ]
        st.dataframe(
            pd.DataFrame(rows).sort_values("MAE"), use_container_width=True, hide_index=True
        )
        st.caption(
            f"Trained on {best.get('n_train', '—')} days, evaluated on {best.get('n_test', '—')} "
            "held-out days that follow the training window in time."
        )
    else:
        st.caption("No stored metrics for this artifact.")

    theme.section("Method")
    st.markdown(
        """
* Features: lags 1, 7, 14, 30 plus day-of-year sine/cosine.
* Candidates: Ridge and Gradient Boosting; the lower held-out MAE wins.
* The band is ±1.96 × held-out MAE — an empirical interval, not a model-derived one.
* Forecasting is recursive: each predicted day feeds the next day's lag-1.
  Error compounds with horizon length.
        """
    )
    if st.button("Persist this forecast", help="Writes one document to ml_predictions"):
        try:
            ml.predict_trend(region, horizon_days=horizon, persist=True)
            st.success("Forecast written to ml_predictions.")
        except Exception as exc:  # noqa: BLE001
            st.error(str(exc))
