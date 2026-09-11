"""Model training, forecasting, anomaly detection and correlation analysis."""
from __future__ import annotations

import pytest

from weatherpredict import ml
from weatherpredict.auth import PermissionDenied
from weatherpredict.db import get_collection


def test_training_requires_administrator(analyst_user):
    with pytest.raises(PermissionDenied):
        ml.train_all(user=analyst_user)


def test_trend_training_writes_artifacts_and_honest_metrics(trained_models):
    assert (trained_models / "trend_pacific_nw.joblib").exists()
    artifact = ml.get_artifact("trend_pacific_nw")
    assert artifact is not None
    for name, metrics in artifact["metrics"].items():
        # Every candidate is reported alongside the persistence baseline it must beat.
        assert "naive_lag1_mae" in metrics
        assert "beat_naive" in metrics
        assert metrics["n_test"] > 0
    assert "naive baseline" in artifact["notes"]


def test_predict_trend_returns_a_series(trained_models):
    prediction = ml.predict_trend("pacific_nw", horizon_days=7)
    assert len(prediction["series"]) == 7
    first = prediction["series"][0]
    assert {"date", "yhat", "yhat_lower", "yhat_upper"} <= set(first)
    assert first["yhat_lower"] < first["yhat"] < first["yhat_upper"]
    assert prediction["history"]


def test_predict_trend_does_not_persist_by_default(trained_models):
    before = get_collection("ml_predictions").count_documents({})
    ml.predict_trend("pacific_nw", horizon_days=5)
    assert get_collection("ml_predictions").count_documents({}) == before
    ml.predict_trend("pacific_nw", horizon_days=5, persist=True)
    assert get_collection("ml_predictions").count_documents({}) == before + 1


def test_predict_trend_without_a_model_raises(trained_models):
    with pytest.raises(FileNotFoundError):
        ml.predict_trend("atlantis", horizon_days=5)


def test_anomaly_metrics_are_labelled_as_proxy(trained_models):
    artifact = ml.get_artifact("anomaly_isolation_forest")
    metrics = artifact["metrics"]
    assert "proxy_precision_vs_z3" in metrics
    assert "proxy" in metrics["caveat"].lower()
    assert 0.0 <= metrics["proxy_precision_vs_z3"] <= 1.0


def test_detect_anomalies_is_idempotent(trained_models, admin_user):
    """Re-running detection must update findings, never duplicate them."""
    collection = get_collection("anomalies")
    ml.detect_anomalies(persist=True)
    after_first = collection.count_documents({})
    assert after_first > 0
    ml.detect_anomalies(persist=True)
    assert collection.count_documents({}) == after_first


def test_detect_anomalies_does_not_persist_by_default(trained_models):
    collection = get_collection("anomalies")
    ml.detect_anomalies(persist=True)
    baseline = collection.count_documents({})
    found = ml.detect_anomalies(persist=False)
    assert found
    assert collection.count_documents({}) == baseline


def test_new_anomalies_notify_only_once(trained_models, admin_user):
    from weatherpredict import notifications as notif

    get_collection("anomalies").delete_many({})
    notif.create_rule(
        name="Any temp", metric="temp_c", threshold=-100, operator="gt", acting_user=admin_user
    )
    ml.detect_anomalies(persist=True)
    first_round = notif.unread_count("admin_test")
    assert first_round > 0
    ml.detect_anomalies(persist=True)
    assert notif.unread_count("admin_test") == first_round


def test_stored_anomalies_are_serialisable(trained_models):
    ml.detect_anomalies(persist=True)
    rows = ml.stored_anomalies(limit=5)
    assert rows
    assert isinstance(rows[0]["observed_at"], str)
    assert rows[0]["severity"] in {"low", "medium", "high"}


def test_correlation_analysis_returns_a_matrix(trained_models):
    report = ml.run_correlation_analysis()
    assert "error" not in report
    region, data = next(iter(report.items()))
    matrix = data["pearson"]
    variables = data["variables"]
    assert len(variables) >= 2
    # Square, and every self-correlation is exactly 1.
    assert set(matrix) == set(variables)
    for var in variables:
        assert matrix[var][var] == pytest.approx(1.0)
    assert all(-1.0 <= v <= 1.0 for col in matrix.values() for v in col.values())
    assert data["n_days"] >= 30


def test_correlation_report_is_readable_from_disk(trained_models):
    ml.run_correlation_analysis()
    report = ml.get_correlations()
    assert report
    region = next(iter(report))
    assert ml.get_correlations(region)["n_days"] >= 30


def test_sensor_name_collisions_are_suffixed(trained_models):
    """A sensor metric sharing a station column name must not overwrite it."""
    from datetime import datetime, timezone

    coll = get_collection("sensor_readings")
    docs = [
        {
            "sensor_id": "LIVE-TEMP",
            "region": "pacific_nw",
            "metric": "temp_c",
            "value": 11.0 + i * 0.01,
            "unit": "C",
            "observed_at": datetime(2024, 1, 1, tzinfo=timezone.utc).replace(day=(i % 28) + 1),
            "source": "realtime",
        }
        for i in range(60)
    ]
    coll.insert_many(docs)
    report = ml.run_correlation_analysis()
    variables = report["pacific_nw"]["variables"]
    assert "temp_c" in variables
    assert "sensor_temp_c" in variables
    coll.delete_many({"sensor_id": "LIVE-TEMP"})
