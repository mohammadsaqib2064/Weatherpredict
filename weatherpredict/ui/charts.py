"""Plotly figures for climate charts."""
from __future__ import annotations

from typing import Any, Sequence

import pandas as pd
import plotly.graph_objects as go

from weatherpredict.ui import tokens as t

_LAYOUT = dict(
    template="plotly_white",
    paper_bgcolor=t.SURFACE,
    plot_bgcolor=t.SURFACE,
    font=dict(family="IBM Plex Sans, Segoe UI, sans-serif", size=13, color=t.INK_900),
    title=dict(font=dict(family="Space Grotesk, Segoe UI, sans-serif", size=18, color=t.OCEAN_900)),
    margin=dict(l=56, r=24, t=48, b=48),
    hoverlabel=dict(font=dict(family="IBM Plex Sans, Segoe UI, sans-serif", size=12)),
    colorway=t.CATEGORICAL,
    xaxis=dict(gridcolor="rgba(11,61,92,0.08)", zeroline=False, linecolor=t.LINE),
    yaxis=dict(gridcolor="rgba(11,61,92,0.08)", zeroline=False, linecolor=t.LINE),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, font=dict(size=12)),
)


def _apply(fig: go.Figure, height: int = 380, title: str | None = None) -> go.Figure:
    fig.update_layout(**_LAYOUT, height=height)
    if title:
        fig.update_layout(title_text=title)
    return fig


def forecast_chart(history: Sequence[dict], series: Sequence[dict], region: str) -> go.Figure:
    """History line plus forecast with an uncertainty band drawn from held-out MAE."""
    fig = go.Figure()
    if history:
        hx = [h["date"] for h in history]
        hy = [h["y"] for h in history]
        fig.add_trace(
            go.Scatter(
                x=hx, y=hy, name="Observed", mode="lines",
                line=dict(color=t.OCEAN_900, width=1.6),
            )
        )
    if series:
        fx = [s["date"] for s in series]
        fig.add_trace(
            go.Scatter(
                x=fx + fx[::-1],
                y=[s["yhat_upper"] for s in series] + [s["yhat_lower"] for s in series][::-1],
                fill="toself",
                fillcolor="rgba(126,182,212,0.22)",
                line=dict(color="rgba(0,0,0,0)"),
                hoverinfo="skip",
                name="95% interval (±1.96 × test MAE)",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=fx,
                y=[s["yhat"] for s in series],
                name="Forecast",
                mode="lines",
                line=dict(color=t.OCEAN_700, width=2.2, dash="dot"),
            )
        )
    fig.update_yaxes(title_text="Temperature (°C)")
    return _apply(fig, 420, f"{region.replace('_', ' ').title()} — daily mean temperature")


def anomaly_scatter(rows: Sequence[dict]) -> go.Figure:
    """Anomalies over time: colour is the signed z-score, blue cold / coral hot."""
    fig = go.Figure()
    if not rows:
        return _apply(fig, 340, "No stored anomalies")
    df = pd.DataFrame(rows)
    df["observed_at"] = pd.to_datetime(df["observed_at"], utc=True, errors="coerce")
    fig.add_trace(
        go.Scatter(
            x=df["observed_at"],
            y=df["value"],
            mode="markers",
            marker=dict(
                size=[9 if s == "high" else 7 for s in df.get("severity", [])],
                color=df["z_score"],
                colorscale=t.DIVERGING_SCALE,
                cmin=-5,
                cmax=5,
                cmid=0,
                line=dict(width=0.6, color="rgba(11,61,92,0.35)"),
                colorbar=dict(title="z-score", thickness=12, len=0.7),
            ),
            customdata=df[["region", "severity", "baseline"]].to_numpy(),
            hovertemplate=(
                "%{customdata[0]}<br>%{x|%Y-%m-%d}"
                "<br>value %{y:.2f} °C (baseline %{customdata[2]:.2f})"
                "<br>severity %{customdata[1]}<extra></extra>"
            ),
            name="Anomaly",
        )
    )
    fig.update_yaxes(title_text="Temperature (°C)")
    return _apply(fig, 400, "Flagged observations against seasonal baseline")


def correlation_heatmap(matrix: dict[str, dict[str, float]], title: str) -> go.Figure:
    """Correlation heatmap with the scale pinned to the full [-1, 1] range."""
    df = pd.DataFrame(matrix)
    df = df.reindex(index=df.columns)
    fig = go.Figure(
        go.Heatmap(
            z=df.to_numpy(),
            x=list(df.columns),
            y=list(df.index),
            colorscale=t.DIVERGING_SCALE,
            # Pinned so a 0.15 coefficient can never be painted like a 0.95 one.
            zmin=-1,
            zmax=1,
            zmid=0,
            colorbar=dict(title="r", thickness=12, len=0.8, tickvals=[-1, -0.5, 0, 0.5, 1]),
            hovertemplate="%{y} vs %{x}<br>r = %{z:.3f}<extra></extra>",
        )
    )
    fig.update_layout(yaxis=dict(autorange="reversed"))
    return _apply(fig, 460, title)


def region_bar(rows: Sequence[dict]) -> go.Figure:
    """Regional mean temperature, coloured by departure from the all-region mean."""
    fig = go.Figure()
    if not rows:
        return _apply(fig, 320, "No regional data")
    df = pd.DataFrame(rows)
    overall = float(df["avg_temp"].mean())
    df["delta"] = df["avg_temp"] - overall
    span = max(abs(df["delta"]).max(), 0.5)
    fig.add_trace(
        go.Bar(
            x=df["region"].str.replace("_", " ").str.title(),
            y=df["avg_temp"],
            marker=dict(
                color=df["delta"],
                colorscale=t.DIVERGING_SCALE,
                cmin=-span,
                cmax=span,
                cmid=0,
                colorbar=dict(title="Δ vs mean", thickness=12, len=0.7),
            ),
            customdata=df[["min_temp", "max_temp", "n"]].to_numpy(),
            hovertemplate=(
                "%{x}<br>mean %{y:.2f} °C"
                "<br>range %{customdata[0]:.1f} to %{customdata[1]:.1f} °C"
                "<br>%{customdata[2]} observations<extra></extra>"
            ),
        )
    )
    fig.add_hline(
        y=overall,
        line=dict(color=t.INK_500, width=1, dash="dash"),
        annotation_text=f"all-region mean {overall:.2f} °C",
        annotation_font=dict(size=11, color=t.INK_500),
    )
    fig.update_yaxes(title_text="Mean temperature (°C)")
    return _apply(fig, 380, "Regional mean temperature")


def unified_stream(points: Sequence[dict], region: str, metric: str) -> go.Figure:
    """Batch history and live ticks on one axis, split by provenance."""
    fig = go.Figure()
    if not points:
        return _apply(fig, 360, "No merged observations in window")
    df = pd.DataFrame(points)
    df["t"] = pd.to_datetime(df["t"], utc=True, errors="coerce")
    styles = {
        "batch": dict(color=t.OCEAN_900, dash="solid", mode="lines"),
        "synthetic": dict(color=t.OCEAN_900, dash="solid", mode="lines"),
        "upload": dict(color=t.OCEAN_700, dash="solid", mode="lines"),
        "realtime": dict(color=t.CORAL_600, dash="dot", mode="lines+markers"),
    }
    for source, group in df.groupby("source"):
        style = styles.get(str(source), dict(color=t.GLACIER_400, dash="solid", mode="lines"))
        fig.add_trace(
            go.Scatter(
                x=group["t"],
                y=group["v"],
                name=str(source),
                mode=style["mode"],
                line=dict(color=style["color"], width=1.8, dash=style["dash"]),
                marker=dict(size=5, color=style["color"]),
            )
        )
    fig.update_yaxes(title_text=metric)
    return _apply(fig, 400, f"{region.replace('_', ' ').title()} — unified {metric} stream")


def series_line(df: pd.DataFrame, x: str, y: str, title: str, y_title: str = "") -> go.Figure:
    fig = go.Figure(
        go.Scatter(x=df[x], y=df[y], mode="lines", line=dict(color=t.OCEAN_900, width=1.6))
    )
    fig.update_yaxes(title_text=y_title or y)
    return _apply(fig, 360, title)


def distribution(values: Sequence[float], title: str, x_title: str = "") -> go.Figure:
    fig = go.Figure(go.Histogram(x=list(values), marker=dict(color=t.GLACIER_400), nbinsx=40))
    fig.update_xaxes(title_text=x_title)
    fig.update_yaxes(title_text="Days")
    return _apply(fig, 320, title)


def empty(message: str) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(
        text=message, showarrow=False, font=dict(size=14, color=t.INK_500), x=0.5, y=0.5, xref="paper", yref="paper"
    )
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return _apply(fig, 240)


def show(fig: go.Figure, **kwargs: Any) -> None:
    import streamlit as st

    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False}, **kwargs)
