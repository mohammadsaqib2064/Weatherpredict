"""Simulated real-time layer and the unified batch/realtime view."""
from __future__ import annotations

from weatherpredict import notifications as notif, pipelines, realtime
from weatherpredict.db import get_collection


def test_emit_tick_writes_readings_and_ledger_entry(admin_user):
    before = get_collection("sensor_readings").count_documents({"source": "realtime"})
    docs = realtime.emit_sensor_tick(n_readings=8, user=admin_user)
    after = get_collection("sensor_readings").count_documents({"source": "realtime"})
    assert len(docs) == 8
    assert after - before == 8
    assert all(d["source"] == "realtime" for d in docs)
    runs = pipelines.recent_runs(1, job_type=pipelines.REALTIME_TICK)
    assert runs and runs[0]["stats"]["emitted"] == 8


def test_analyst_may_emit_ticks(analyst_user):
    assert len(realtime.emit_sensor_tick(n_readings=3, user=analyst_user)) == 3


def test_tick_values_are_evaluated_against_alert_rules(admin_user):
    notif.create_rule(
        name="Any reading", metric="co2_ppm", threshold=-1, operator="gt", acting_user=admin_user
    )
    for _ in range(12):
        realtime.emit_sensor_tick(n_readings=4, user=admin_user)
    # co2_ppm is one of four simulated metrics, so a dozen bursts will hit it.
    assert notif.unread_count("admin_test") > 0


def test_unified_series_merges_batch_and_live(admin_user, climate_corpus):
    realtime.emit_sensor_tick(n_readings=20, user=admin_user)
    data = realtime.unified_series("pacific_nw", "temp_c", hours=72)
    assert data["region"] == "pacific_nw"
    assert data["counts"]["merged"] == len(data["points"])
    sources = {p["source"] for p in data["points"]}
    assert sources  # at least one provenance present
    timestamps = [p["t"] for p in data["points"]]
    assert timestamps == sorted(timestamps)


def test_latest_readings_filters_by_region(admin_user):
    realtime.emit_sensor_tick(n_readings=25, user=admin_user)
    rows = realtime.latest_readings(10, region="southwest")
    assert all(r["region"] == "southwest" for r in rows)
