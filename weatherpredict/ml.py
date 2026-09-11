"""Trend, anomaly and correlation models.

Training uses a time-based split and lag features only (no future covariates).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone as dt_timezone
from typing import Any

import joblib
import numpy as np
import pandas as pd
from pymongo import UpdateOne

from weatherpredict import pipelines, settings
from weatherpredict.auth import User, require
from weatherpredict.db import get_collection
from weatherpredict.notifications import notify_anomaly
from weatherpredict.scoping import constrain_region, mongo_region_filter

logger = logging.getLogger("weatherpredict.ml")

ARTIFACT_DIR = settings.ARTIFACT_DIR

WEATHER_FIELDS = ("region", "observed_at", "temp_c", "precip_mm", "humidity_pct")

_SKLEARN = None


def _sklearn():
    """Import scikit-learn on first use."""
    global _SKLEARN
    if _SKLEARN is None:
        from sklearn.ensemble import GradientBoostingRegressor, IsolationForest
        from sklearn.linear_model import Ridge
        from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
        from sklearn.preprocessing import StandardScaler

        _SKLEARN = {
            "GBR": GradientBoostingRegressor,
            "Iso": IsolationForest,
            "Ridge": Ridge,
            "mae": mean_absolute_error,
            "mse": mean_squared_error,
            "r2": r2_score,
            "Scaler": StandardScaler,
        }
    return _SKLEARN


# --- artifact registry -------------------------------------------------------

def _next_version(name: str) -> str:
    existing = list(get_collection("ml_artifacts").find({"name": name}, {"version": 1}))
    numbers = []
    for doc in existing:
        try:
            numbers.append(int(str(doc.get("version", "0"))))
        except ValueError:
            continue
    return str((max(numbers) if numbers else 0) + 1)


def save_artifact(
    name: str,
    task: str,
    path: str,
    metrics: dict[str, Any],
    notes: str = "",
    version: str | None = None,
    is_active: bool = True,
) -> dict[str, Any]:
    version = version or _next_version(name)
    if is_active:
        get_collection("ml_artifacts").update_many({"name": name}, {"$set": {"is_active": False}})
    doc = {
        "name": name,
        "version": version,
        "task": task,
        "path": str(path),
        "metrics": metrics,
        "notes": notes,
        "trained_at": datetime.now(tz=dt_timezone.utc),
        "is_active": is_active,
    }
    get_collection("ml_artifacts").update_one(
        {"name": name, "version": version}, {"$set": doc}, upsert=True
    )
    return doc


def get_artifact(name: str, version: str | None = None) -> dict[str, Any] | None:
    query: dict[str, Any] = {"name": name}
    if version:
        query["version"] = version
    else:
        query["is_active"] = True
    return get_collection("ml_artifacts").find_one(query, sort=[("trained_at", -1)])


def list_artifacts(active_only: bool = True) -> list[dict[str, Any]]:
    query = {"is_active": True} if active_only else {}
    return list(get_collection("ml_artifacts").find(query).sort("trained_at", -1))


# --- feature engineering -----------------------------------------------------

def _weather_frame(
    region: str | None = None,
    fields: tuple[str, ...] = WEATHER_FIELDS,
    user: User | None = None,
) -> pd.DataFrame:
    query = mongo_region_filter(user, region) if user is not None else (
        {"region": region} if region else {}
    )
    # Project only the columns the models use; station metadata is dead weight
    # over the wire for every training and prediction call.
    projection = {"_id": 0, **{f: 1 for f in fields}}
    docs = list(get_collection("weather_station_records").find(query, projection))
    if not docs:
        return pd.DataFrame()
    df = pd.DataFrame(docs)
    df["observed_at"] = pd.to_datetime(df["observed_at"], utc=True)
    df = df.sort_values("observed_at")
    return df


def _daily_series(df: pd.DataFrame) -> pd.Series:
    return (
        df.set_index("observed_at")["temp_c"]
        .astype(float)
        .resample("D")
        .mean()
        .interpolate(limit=3)
        .dropna()
    )


def _build_lag_features(series: pd.Series, lags=(1, 7, 14, 30)) -> pd.DataFrame:
    frame = pd.DataFrame({"y": series})
    for lag in lags:
        frame[f"lag_{lag}"] = series.shift(lag)
    frame["doy_sin"] = np.sin(2 * np.pi * series.index.dayofyear / 365.25)
    frame["doy_cos"] = np.cos(2 * np.pi * series.index.dayofyear / 365.25)
    return frame.dropna()


# --- training ----------------------------------------------------------------

def train_trend_models() -> dict[str, Any]:
    sk = _sklearn()
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    df = _weather_frame()
    if df.empty:
        raise RuntimeError("No weather data available for training")

    results: dict[str, Any] = {}
    all_metrics: dict[str, Any] = {}
    for region, rdf in df.groupby("region"):
        daily = _daily_series(rdf)
        if len(daily) < 120:
            continue
        feat = _build_lag_features(daily)
        # Time-based split: last 20% held out
        split = int(len(feat) * 0.8)
        train, test = feat.iloc[:split], feat.iloc[split:]
        X_train, y_train = train.drop(columns=["y"]), train["y"]
        X_test, y_test = test.drop(columns=["y"]), test["y"]

        models = {
            "ridge": sk["Ridge"](alpha=1.0),
            "gbr": sk["GBR"](random_state=42, max_depth=3, n_estimators=100),
        }
        region_metrics: dict[str, Any] = {}
        best_name, best_model, best_mae = None, None, 1e9
        for name, model in models.items():
            model.fit(X_train, y_train)
            pred = model.predict(X_test)
            mae = float(sk["mae"](y_test, pred))
            rmse = float(np.sqrt(sk["mse"](y_test, pred)))
            r2 = float(sk["r2"](y_test, pred))
            # Sanity: naive persistence baseline
            naive = X_test["lag_1"]
            naive_mae = float(sk["mae"](y_test, naive))
            region_metrics[name] = {
                "mae": round(mae, 3),
                "rmse": round(rmse, 3),
                "r2": round(r2, 3),
                "naive_lag1_mae": round(naive_mae, 3),
                "beat_naive": mae < naive_mae,
                "n_train": int(len(train)),
                "n_test": int(len(test)),
            }
            if mae < best_mae:
                best_mae, best_name, best_model = mae, name, model

        path = ARTIFACT_DIR / f"trend_{region}.joblib"
        joblib.dump(
            {
                "model": best_model,
                "model_name": best_name,
                "feature_columns": list(X_train.columns),
                "region": region,
                "last_train_date": str(train.index.max().date()),
            },
            path,
        )
        save_artifact(
            name=f"trend_{region}",
            task="trend",
            path=str(path),
            metrics=region_metrics,
            notes=(
                "Time-based 80/20 split; lag features only. "
                "Compare MAE to lag-1 naive baseline to avoid fake accuracy."
            ),
        )
        results[region] = {"best": best_name, "metrics": region_metrics, "path": str(path)}
        all_metrics[region] = region_metrics

    report_path = ARTIFACT_DIR / "model_evaluation_report.json"
    report_path.write_text(json.dumps(all_metrics, indent=2), encoding="utf-8")
    return results


def train_anomaly_model() -> dict[str, Any]:
    sk = _sklearn()
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    df = _weather_frame()
    if df.empty:
        raise RuntimeError("No weather data for anomaly training")

    daily = (
        df.groupby(["region", pd.Grouper(key="observed_at", freq="D")])["temp_c"]
        .mean()
        .reset_index()
    )
    daily["doy"] = daily["observed_at"].dt.dayofyear
    # Baseline: historical mean/std per region+doy from training period only
    split_date = daily["observed_at"].quantile(0.8)
    train = daily[daily["observed_at"] <= split_date].copy()
    test = daily[daily["observed_at"] > split_date].copy()

    baseline = train.groupby(["region", "doy"])["temp_c"].agg(["mean", "std"]).reset_index()
    baseline["std"] = baseline["std"].replace(0, np.nan).fillna(baseline["std"].median() or 1.0)

    def attach_z(frame):
        m = frame.merge(baseline, on=["region", "doy"], how="left")
        m["std"] = m["std"].fillna(m["std"].median() or 1.0)
        m["mean"] = m["mean"].fillna(m["temp_c"].mean())
        m["z_score"] = (m["temp_c"] - m["mean"]) / m["std"]
        return m

    train_z = attach_z(train)
    test_z = attach_z(test)

    feats_train = train_z[["temp_c", "z_score", "doy"]].fillna(0)
    scaler = sk["Scaler"]()
    X_train = scaler.fit_transform(feats_train)
    iso = sk["Iso"](contamination=0.02, random_state=42)
    iso.fit(X_train)

    feats_test = test_z[["temp_c", "z_score", "doy"]].fillna(0)
    X_test = scaler.transform(feats_test)
    pred = iso.predict(X_test)
    # Honest evaluation: agreement with |z|>3 as proxy label (not ground truth climate events)
    proxy_label = (test_z["z_score"].abs() > 3).astype(int)
    iso_flag = pd.Series((pred == -1).astype(int), index=proxy_label.index)
    agree = int((proxy_label & iso_flag).sum())
    precision = float(agree / max(int(iso_flag.sum()), 1))
    recall = float(agree / max(int(proxy_label.sum()), 1))

    path = ARTIFACT_DIR / "anomaly_isolation_forest.joblib"
    joblib.dump({"model": iso, "scaler": scaler, "baseline": baseline}, path)
    metrics = {
        "proxy_precision_vs_z3": round(precision, 3),
        "proxy_recall_vs_z3": round(recall, 3),
        "n_train": int(len(train)),
        "n_test": int(len(test)),
        "test_proxy_anomalies": int(proxy_label.sum()),
        "test_iso_flags": int(iso_flag.sum()),
        "caveat": (
            "Labels are proxy (|z|>3 vs training baseline), not verified extreme events. "
            "Precision/recall are indicative only."
        ),
    }
    save_artifact(
        name="anomaly_isolation_forest",
        task="anomaly",
        path=str(path),
        metrics=metrics,
        notes=metrics["caveat"],
    )
    return metrics


def run_correlation_analysis() -> dict[str, Any]:
    df = _weather_frame()
    sensors = list(get_collection("sensor_readings").find({}, {"_id": 0}))
    if df.empty or not sensors:
        return {"error": "insufficient data"}

    sdf = pd.DataFrame(sensors)
    sdf["observed_at"] = pd.to_datetime(sdf["observed_at"], utc=True)
    weather_daily = (
        df.groupby([df["region"], pd.Grouper(key="observed_at", freq="D")])
        .agg(
            temp_c=("temp_c", "mean"),
            precip_mm=("precip_mm", "mean"),
            humidity_pct=("humidity_pct", "mean"),
        )
        .reset_index()
    )

    results: dict[str, Any] = {}
    for region in weather_daily["region"].unique():
        # Climate station daily means (exclude region label from join)
        w = (
            weather_daily[weather_daily["region"] == region]
            .set_index("observed_at")
            .drop(columns=["region"], errors="ignore")
        )
        s = sdf[sdf["region"] == region]
        if s.empty:
            continue
        pivot = s.pivot_table(index="observed_at", columns="metric", values="value", aggfunc="mean")
        pivot = pivot.resample("D").mean()
        # Sensor metric names (e.g. temp_c from realtime ticks) can collide with
        # weather columns; keep both by suffixing sensor-side overlaps.
        overlap = w.columns.intersection(pivot.columns)
        if len(overlap):
            pivot = pivot.rename(columns={c: f"sensor_{c}" for c in overlap})
        merged = w.join(pivot, how="inner")
        if len(merged) < 30:
            continue
        numeric = merged.select_dtypes(include=["number"])
        if numeric.shape[1] < 2:
            continue
        corr = numeric.corr(method="pearson")
        spearman = numeric.corr(method="spearman")
        results[region] = {
            "pearson": corr.round(3).to_dict(),
            "spearman": spearman.round(3).to_dict(),
            "n_days": int(len(merged)),
            "variables": list(numeric.columns),
        }

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    path = ARTIFACT_DIR / "correlation_report.json"
    path.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    save_artifact(
        name="correlation_analysis",
        task="correlation",
        path=str(path),
        metrics={r: {"n_days": v["n_days"]} for r, v in results.items()},
        notes="Pearson and Spearman on daily means; correlation != causation.",
    )
    return results


def train_all(user: User | None = None) -> dict[str, Any]:
    """Full training sweep. Administrators only."""
    require(user, "train_ml")
    run = pipelines.start_run(
        pipelines.ML_TRAIN, adapter="sklearn", triggered_by=user.username if user else None
    )
    try:
        trend = train_trend_models()
        anomaly = train_anomaly_model()
        corr = run_correlation_analysis()
        flagged = detect_anomalies(persist=True)
        return pipelines.finish_run(
            run,
            pipelines.SUCCESS,
            {
                "regions_trained": list(trend.keys()),
                "anomaly": anomaly,
                "anomalies_flagged": len(flagged),
                "correlation_regions": list(corr.keys()) if isinstance(corr, dict) else [],
            },
        )
    except Exception as exc:  # noqa: BLE001
        pipelines.finish_run(run, pipelines.FAILED, error=str(exc))
        raise


# --- inference ---------------------------------------------------------------

def predict_trend(
    region: str,
    horizon_days: int = 30,
    persist: bool = False,
    history_days: int = 180,
    user: User | None = None,
) -> dict[str, Any]:
    """Roll a trained regional model forward ``horizon_days``.

    ``persist`` is opt-in: viewing a forecast must not append to ml_predictions,
    otherwise the collection grows on every page refresh.
    """
    region = constrain_region(user, region) or region
    path = ARTIFACT_DIR / f"trend_{region}.joblib"
    if not path.exists():
        raise FileNotFoundError(f"No trend model for region {region}. Train models first.")
    _sklearn()  # required before unpickling sklearn estimators
    bundle = joblib.load(path)
    model = bundle["model"]
    cols = bundle["feature_columns"]

    df = _weather_frame(region, fields=("region", "observed_at", "temp_c"), user=user)
    if df.empty:
        raise RuntimeError(f"No weather data stored for region {region}.")
    daily = _daily_series(df)
    if daily.empty:
        raise RuntimeError(f"Not enough daily coverage for region {region}.")

    # Training rows pair y at date d with lag_k = y[d - k], so forecasting date
    # d+1 must read lag_k from history[-k] and seasonality from d+1 itself.
    # Recomputing the full lag frame each step also made this O(n x horizon).
    lags = sorted(int(c.split("_")[1]) for c in cols if c.startswith("lag_"))
    values = list(daily.to_numpy(dtype=float))
    next_day = daily.index.max()

    artifact = get_artifact(f"trend_{region}")
    mae = 2.0
    if artifact and artifact.get("metrics"):
        best = bundle.get("model_name", "ridge")
        mae = float(artifact["metrics"].get(best, {}).get("mae", 2.0))

    preds = []
    for _ in range(horizon_days):
        if len(values) < max(lags, default=1):
            break
        next_day = next_day + pd.Timedelta(days=1)
        feats = {f"lag_{lag}": values[-lag] for lag in lags}
        feats["doy_sin"] = float(np.sin(2 * np.pi * next_day.dayofyear / 365.25))
        feats["doy_cos"] = float(np.cos(2 * np.pi * next_day.dayofyear / 365.25))
        row = pd.DataFrame([[feats.get(c, 0.0) for c in cols]], columns=cols)
        yhat = float(model.predict(row)[0])
        values.append(yhat)
        preds.append(
            {
                "date": str(next_day.date()),
                "yhat": round(yhat, 2),
                "yhat_lower": round(yhat - 1.96 * mae, 2),
                "yhat_upper": round(yhat + 1.96 * mae, 2),
            }
        )

    recent = daily.tail(history_days)
    generated_at = datetime.now(tz=dt_timezone.utc)
    doc = {
        "model_name": f"trend_{region}",
        "selected_model": bundle.get("model_name"),
        "region": region,
        "target": "temp_c",
        "horizon_days": horizon_days,
        "generated_at": generated_at,
        "series": preds,
        "metrics": artifact.get("metrics") if artifact else {},
    }
    if persist:
        get_collection("ml_predictions").insert_one(dict(doc))
    doc["generated_at"] = generated_at.isoformat()
    doc["history"] = [
        {"date": str(idx.date()), "y": round(float(val), 2)} for idx, val in recent.items()
    ]
    return doc


def detect_anomalies(region: str | None = None, persist: bool = False) -> list[dict[str, Any]]:
    """Score observations against the seasonal baseline. Persist is off by default."""
    path = ARTIFACT_DIR / "anomaly_isolation_forest.joblib"
    if not path.exists():
        raise FileNotFoundError("Anomaly model missing. Train first.")
    _sklearn()
    bundle = joblib.load(path)
    iso, scaler, baseline = bundle["model"], bundle["scaler"], bundle["baseline"]
    df = _weather_frame(region, fields=("region", "observed_at", "temp_c"))
    if df.empty:
        return []
    daily = (
        df.groupby(["region", pd.Grouper(key="observed_at", freq="D")])["temp_c"].mean().reset_index()
    )
    daily["doy"] = daily["observed_at"].dt.dayofyear
    merged = daily.merge(baseline, on=["region", "doy"], how="left")
    merged["std"] = merged["std"].fillna(merged["std"].median() or 1.0)
    merged["mean"] = merged["mean"].fillna(merged["temp_c"].mean())
    merged["z_score"] = (merged["temp_c"] - merged["mean"]) / merged["std"]
    feats = merged[["temp_c", "z_score", "doy"]].fillna(0)
    flags = iso.predict(scaler.transform(feats))

    merged = merged.reset_index(drop=True)
    flagged = (flags == -1) | (merged["z_score"].abs() >= 3).to_numpy()
    anomalies = []
    for pos in np.flatnonzero(flagged):
        row = merged.iloc[pos]
        z = float(row["z_score"])
        anomalies.append(
            {
                "region": row["region"],
                "metric": "temp_c",
                "observed_at": row["observed_at"].to_pydatetime(),
                "value": float(row["temp_c"]),
                "baseline": float(row["mean"]),
                "z_score": round(z, 3),
                "severity": "high" if abs(z) >= 4 else "medium" if abs(z) >= 3 else "low",
                "method": "isolation_forest+zscore",
                "alerted": False,
            }
        )

    if persist and anomalies:
        collection = get_collection("anomalies")
        operations = [
            UpdateOne(
                {"region": a["region"], "metric": a["metric"], "observed_at": a["observed_at"]},
                {"$set": a, "$setOnInsert": {"first_detected_at": datetime.now(tz=dt_timezone.utc)}},
                upsert=True,
            )
            for a in anomalies
        ]
        result = collection.bulk_write(operations, ordered=False)
        new_keys = (
            {
                (doc["region"], doc["observed_at"])
                for doc in collection.find(
                    {"_id": {"$in": list(result.upserted_ids.values())}},
                    {"_id": 0, "region": 1, "observed_at": 1},
                )
            }
            if result.upserted_ids
            else set()
        )
        logger.info(
            "Anomaly detection: %s flagged, %s new, %s updated",
            len(anomalies),
            len(result.upserted_ids or {}),
            result.modified_count,
        )
        for a in anomalies:
            if (a["region"], a["observed_at"]) in new_keys and a["severity"] in ("high", "medium"):
                notify_anomaly(a)
                a["alerted"] = True
    return anomalies


def stored_anomalies(
    region: str | None = None,
    limit: int = 400,
    user: User | None = None,
) -> list[dict[str, Any]]:
    """Read persisted anomalies for display — no model load, no recomputation."""
    query = mongo_region_filter(user, region) if user is not None else (
        {"region": region} if region else {}
    )
    cursor = (
        get_collection("anomalies").find(query, {"_id": 0}).sort("observed_at", -1).limit(limit)
    )
    out = []
    for doc in cursor:
        observed = doc.get("observed_at")
        out.append(
            {
                "region": doc.get("region", "—"),
                "metric": doc.get("metric", "temp_c"),
                "value": doc.get("value"),
                "baseline": doc.get("baseline"),
                "z_score": doc.get("z_score"),
                "severity": doc.get("severity", "low"),
                "method": doc.get("method", ""),
                "observed_at": observed.isoformat() if hasattr(observed, "isoformat") else str(observed or ""),
            }
        )
    return out


def get_correlations(region: str | None = None, user: User | None = None) -> dict[str, Any]:
    path = ARTIFACT_DIR / "correlation_report.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    region = constrain_region(user, region)
    if region:
        return data.get(region, {})
    return data


def available_trend_regions() -> list[str]:
    if not ARTIFACT_DIR.exists():
        return []
    return sorted(p.stem.replace("trend_", "") for p in ARTIFACT_DIR.glob("trend_*.joblib"))
