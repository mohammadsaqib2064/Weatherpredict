"""End-to-end ingestion: validation, import, ledger and permission gating."""
from __future__ import annotations

import io
import json

import pytest

from weatherpredict import ingestion
from weatherpredict.auth import PermissionDenied
from weatherpredict.db import get_collection
from weatherpredict.validators import ValidationError

GOOD_ROWS = [
    {
        "station_id": "TEST-1",
        "region": "test_region",
        "observed_at": "2024-07-01T12:00:00Z",
        "temp_c": 21.5,
        "precip_mm": 0.2,
    },
    {
        "station_id": "TEST-1",
        "region": "test_region",
        "observed_at": "2024-07-02T12:00:00Z",
        "temp_c": 22.1,
    },
]


def _upload(payload: bytes, name: str, data_type: str, user):
    return ingestion.ingest_upload(io.BytesIO(payload), name, data_type, user)


def test_good_json_file_imports(admin_user):
    before = get_collection("weather_station_records").count_documents({"region": "test_region"})
    job = _upload(json.dumps(GOOD_ROWS).encode(), "wx.json", ingestion.WEATHER, admin_user)
    after = get_collection("weather_station_records").count_documents({"region": "test_region"})
    assert job["status"] == ingestion.COMPLETED
    assert job["records_imported"] == 2
    assert job["records_skipped"] == 0
    assert after - before == 2


def test_bad_file_is_rejected_and_recorded(admin_user):
    payload = json.dumps(
        [
            {"station_id": "OK", "region": "test_region", "observed_at": "2024-07-03", "temp_c": 5},
            {"region": "test_region", "temp_c": "banana"},  # no station_id, no timestamp
            {"station_id": "BAD", "observed_at": "definitely-not-a-date", "temp_c": 1},
        ]
    ).encode()
    job = _upload(payload, "mixed.json", ingestion.WEATHER, admin_user)
    assert job["records_imported"] == 1
    assert job["records_skipped"] == 2
    assert "row 2" in job["error_log"]
    assert "row 3" in job["error_log"]


def test_disallowed_extension_is_refused_before_any_write(admin_user):
    with pytest.raises(ValidationError, match="Disallowed file type"):
        _upload(b"whatever", "payload.exe", ingestion.WEATHER, admin_user)
    assert get_collection("ingestion_jobs").count_documents({}) == 0


def test_binary_masquerading_as_csv_is_refused(admin_user):
    with pytest.raises(ValidationError, match="does not match"):
        _upload(b"MZ\x00\x00\x00binary", "payload.csv", ingestion.WEATHER, admin_user)


def test_csv_with_blank_rows_is_graceful(admin_user):
    csv_bytes = (
        b"station_id,region,observed_at,temp_c,humidity_pct\n"
        b"TEST-2,test_region,2024-08-01,19.0,\n"
        b",,,,\n"
        b"TEST-2,test_region,2024-08-02,20.0,55\n"
    )
    job = _upload(csv_bytes, "wx.csv", ingestion.WEATHER, admin_user)
    assert job["records_imported"] == 2
    assert job["records_skipped"] == 1
    assert job["status"] == ingestion.COMPLETED
    doc = get_collection("weather_station_records").find_one({"station_id": "TEST-2", "temp_c": 19.0})
    assert "humidity_pct" in doc["missing_fields"]


def test_satellite_upload_upserts_on_scene_id(admin_user):
    payload = json.dumps(
        [
            {
                "scene_id": "TEST-SCENE-1",
                "satellite": "Sentinel-2",
                "region": "test_region",
                "acquired_at": "2024-04-01T10:00:00Z",
                "cloud_cover_pct": 12.0,
            }
        ]
    ).encode()
    _upload(payload, "scenes.json", ingestion.SATELLITE, admin_user)
    _upload(payload, "scenes.json", ingestion.SATELLITE, admin_user)
    assert get_collection("satellite_imagery").count_documents({"scene_id": "TEST-SCENE-1"}) == 1


def test_sensor_upload_writes_readings(admin_user):
    payload = json.dumps(
        [
            {
                "sensor_id": "TEST-SENSOR",
                "region": "test_region",
                "metric": "co2_ppm",
                "value": 430.2,
                "observed_at": "2024-04-01T10:00:00Z",
            }
        ]
    ).encode()
    job = _upload(payload, "sensors.csv".replace(".csv", ".json"), ingestion.SENSOR, admin_user)
    assert job["records_imported"] == 1
    assert get_collection("sensor_readings").count_documents({"sensor_id": "TEST-SENSOR"}) == 1


def test_analyst_may_ingest_but_anonymous_may_not(analyst_user):
    job = _upload(json.dumps(GOOD_ROWS[:1]).encode(), "wx.json", ingestion.WEATHER, analyst_user)
    assert job["records_imported"] == 1
    with pytest.raises(PermissionDenied):
        ingestion.ingest_upload(io.BytesIO(b"[]"), "wx.json", ingestion.WEATHER, None)


def test_ingestion_stats_roll_up(admin_user):
    _upload(json.dumps(GOOD_ROWS).encode(), "a.json", ingestion.WEATHER, admin_user)
    _upload(json.dumps(GOOD_ROWS).encode(), "b.json", ingestion.WEATHER, admin_user)
    stats = ingestion.ingestion_stats()
    assert stats["jobs"] == 2
    assert stats["records_imported"] == 4
    assert stats["by_status"]["completed"] == 2
