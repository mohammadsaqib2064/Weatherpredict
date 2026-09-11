"""Batch adapters and the pipeline that drives them."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from weatherpredict import pipelines, settings
from weatherpredict.auth import PermissionDenied
from weatherpredict.batch import run_batch_pipeline
from weatherpredict.batch.adapters import HadoopAdapter, LocalFallbackAdapter, get_adapter
from weatherpredict.db import get_collection


@pytest.fixture
def frame():
    return pd.DataFrame(
        [
            {"station_id": "A", "region": "r1", "observed_at": "2024-01-01T00:00:00Z", "temp_c": "10.0"},
            {"station_id": "A", "region": "r1", "observed_at": "2024-01-01T00:00:00Z", "temp_c": "10.0"},
            {"station_id": "B", "region": "r2", "observed_at": "2024-01-02T00:00:00Z", "temp_c": None},
            {"station_id": "C", "region": "r2", "observed_at": "not-a-date", "temp_c": "5"},
        ]
    )


def test_adapter_selection():
    assert isinstance(get_adapter("local"), LocalFallbackAdapter)
    assert isinstance(get_adapter(None), LocalFallbackAdapter)
    for alias in ("hadoop", "hdfs", "hadoop_hdfs"):
        assert isinstance(get_adapter(alias), HadoopAdapter)


def test_clean_drops_bad_timestamps_keeps_missing_measurements(frame):
    cleaned = LocalFallbackAdapter().clean(frame)
    assert len(cleaned) == 2  # one duplicate removed, one unparseable timestamp dropped
    assert "missing_count" in cleaned.columns
    assert cleaned["missing_count"].max() == 1  # the null temp row is kept and flagged


def test_partition_by_region(frame):
    adapter = LocalFallbackAdapter()
    parts = adapter.partition(adapter.clean(frame), ["region"])
    assert set(parts) == {"r1", "r2"}


def test_partition_without_keys_returns_single_group(frame):
    adapter = LocalFallbackAdapter()
    parts = adapter.partition(adapter.clean(frame), ["nonexistent"])
    assert list(parts) == ["all"]


def test_reduce_aggregate_produces_monthly_rollups(frame):
    adapter = LocalFallbackAdapter()
    parts = adapter.partition(adapter.clean(frame), ["region"])
    agg = adapter.reduce_aggregate(parts)
    assert not agg.empty
    assert {"period", "region", "temp_c_mean"} <= set(agg.columns)


def test_write_partitions_sanitizes_keys(tmp_path, frame):
    adapter = LocalFallbackAdapter()
    parts = {"r1|co2_ppm": adapter.clean(frame)}
    paths = adapter.write_partitions(parts, tmp_path)
    assert paths[0].exists()
    assert "|" not in paths[0].name


def test_hadoop_adapter_keeps_the_same_contract(frame):
    hadoop, local = HadoopAdapter(), LocalFallbackAdapter()
    assert hadoop.clean(frame).equals(local.clean(frame))
    report = hadoop.submit_mapreduce("clean", "raw/*.csv")
    assert report["status"] == "not_configured"
    assert "hdfs://" in report["message"]


def test_pipeline_requires_administrator(analyst_user):
    with pytest.raises(PermissionDenied):
        run_batch_pipeline(user=analyst_user)


def test_pipeline_runs_and_is_retriggerable(admin_user, climate_corpus, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path)
    first = run_batch_pipeline(user=admin_user, adapter_name="local")
    assert first["status"] == pipelines.SUCCESS
    assert first["stats"]["weather_rows"] > 0
    assert first["stats"]["aggregates_upserted"] > 0

    count_after_first = get_collection("batch_aggregates").count_documents({})
    second = run_batch_pipeline(user=admin_user, adapter_name="local")
    assert second["status"] == pipelines.SUCCESS
    # Aggregates upsert on (region, period, source) — a re-run must not duplicate.
    assert get_collection("batch_aggregates").count_documents({}) == count_after_first


def test_pipeline_writes_partitions_to_disk(admin_user, climate_corpus, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path)
    run = run_batch_pipeline(user=admin_user, adapter_name="local")
    out_dir = Path(run["stats"]["output_dir"])
    assert out_dir.is_dir()
    assert list(out_dir.rglob("part_*.csv"))
    assert (out_dir / "aggregates.csv").exists()


def test_pipeline_ledger_records_the_run(admin_user, climate_corpus, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path)
    run_batch_pipeline(user=admin_user, adapter_name="local")
    runs = pipelines.recent_runs(5, job_type=pipelines.BATCH_CLEAN)
    assert runs
    assert runs[0]["triggered_by"] == "admin_test"
    assert runs[0]["finished_at"] is not None
