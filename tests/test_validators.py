"""Upload parsing and validation, including graceful missing-data handling."""
from __future__ import annotations

import io
import json

import pytest

from weatherpredict.validators import (
    ValidationError,
    assert_allowed_extension,
    load_records,
    normalize_satellite,
    normalize_sensor,
    normalize_weather,
    sanitize_filename,
    sniff_is_text_or_xlsx,
)


def test_weather_row_with_missing_optional_fields_is_kept_and_flagged():
    row = {"station_id": "S1", "region": "pacific_nw", "observed_at": "2024-01-01T00:00:00Z", "temp_c": ""}
    doc = normalize_weather(row, 1)
    assert doc is not None
    assert "temp_c" in doc["missing_fields"]
    assert doc["temp_c"] is None


def test_weather_row_without_station_is_rejected():
    with pytest.raises(ValidationError):
        normalize_weather({"region": "x", "observed_at": "2024-01-01"}, 1)


def test_blank_row_is_skipped_not_failed():
    assert normalize_weather({"station_id": "", "region": "", "observed_at": ""}, 1) is None


def test_invalid_datetime_rejected():
    with pytest.raises(ValidationError, match="Invalid datetime"):
        normalize_weather({"station_id": "S1", "observed_at": "not-a-date", "temp_c": 1}, 1)


def test_naive_datetime_is_treated_as_utc():
    doc = normalize_weather(
        {"station_id": "S1", "region": "r", "observed_at": "2024-06-01 12:00:00", "temp_c": 10}, 1
    )
    assert doc["observed_at"].tzinfo is not None
    assert doc["observed_at"].utcoffset().total_seconds() == 0


def test_sensor_requires_all_fields():
    with pytest.raises(ValidationError):
        normalize_sensor({"sensor_id": "S", "region": "r", "metric": "co2_ppm"}, 1)


def test_sensor_normalizes_types():
    doc = normalize_sensor(
        {
            "sensor_id": "S1",
            "region": "southwest",
            "metric": "co2_ppm",
            "value": "421.5",
            "observed_at": "2024-05-05",
        },
        1,
    )
    assert doc["value"] == pytest.approx(421.5)
    assert doc["source"] == "upload"


def test_satellite_splits_band_string():
    doc = normalize_satellite(
        {
            "scene_id": "SC1",
            "satellite": "Landsat-8",
            "region": "northeast",
            "acquired_at": "2024-05-05T18:00:00Z",
            "bands": "B2, B3, B4",
        },
        1,
    )
    assert doc["bands"] == ["B2", "B3", "B4"]


def test_load_json_records_wrapper():
    payload = json.dumps({"records": [{"station_id": "S1"}]}).encode()
    rows = load_records(io.BytesIO(payload), "wx.json")
    assert rows == [{"station_id": "S1"}]


def test_load_csv():
    csv_bytes = b"station_id,region,observed_at,temp_c\nS1,pacific_nw,2024-01-01,3.2\n"
    rows = load_records(io.BytesIO(csv_bytes), "wx.csv")
    assert rows[0]["station_id"] == "S1"


def test_load_xlsx(tmp_path):
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["station_id", "region", "observed_at", "temp_c"])
    ws.append(["S1", "southeast", "2024-02-02", 18.4])
    path = tmp_path / "wx.xlsx"
    wb.save(path)
    rows = load_records(path.open("rb"), "wx.xlsx")
    assert rows[0]["temp_c"] == 18.4


def test_disallowed_extension_rejected():
    with pytest.raises(ValidationError, match="Disallowed file type"):
        assert_allowed_extension("payload.exe")


def test_content_sniffing_rejects_binary_pretending_to_be_csv():
    assert sniff_is_text_or_xlsx(b"col1,col2\n1,2", "data.csv")
    assert not sniff_is_text_or_xlsx(b"MZ\x00\x00binary", "data.csv")
    assert sniff_is_text_or_xlsx(b"PK\x03\x04", "book.xlsx")
    assert not sniff_is_text_or_xlsx(b"plain text", "book.xlsx")


def test_filename_sanitization_strips_traversal():
    assert sanitize_filename("../../etc/passwd") == "passwd"
    assert sanitize_filename("weird name;rm -rf.csv") == "weird_name_rm_-rf.csv"
