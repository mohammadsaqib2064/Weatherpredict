"""Validation and parsing for climate data uploads."""
from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime, timezone as dt_timezone
from pathlib import Path
from typing import Any

from weatherpredict import settings

REQUIRED_WEATHER = {"station_id", "region", "observed_at", "temp_c"}
REQUIRED_SENSOR = {"sensor_id", "region", "metric", "value", "observed_at"}
REQUIRED_SATELLITE = {"scene_id", "satellite", "region", "acquired_at"}

DANGEROUS_NAME = re.compile(r"[^\w.\-]+", re.UNICODE)

_DT_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y")


class ValidationError(Exception):
    def __init__(self, message: str, row: int | None = None):
        self.row = row
        super().__init__(message)


def _parse_dt(value: Any) -> datetime:
    if value is None or value == "":
        raise ValidationError("Missing datetime")
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        dt = None
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            for fmt in _DT_FORMATS:
                try:
                    dt = datetime.strptime(text, fmt)
                    break
                except ValueError:
                    continue
        if dt is None:
            raise ValidationError(f"Invalid datetime: {value}")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=dt_timezone.utc)
    return dt.astimezone(dt_timezone.utc)


def _to_float(value: Any, field: str, required: bool = False) -> float | None:
    if value is None or value == "":
        if required:
            raise ValidationError(f"Missing required numeric field: {field}")
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"Invalid number for {field}: {value}") from exc


def sanitize_filename(name: str) -> str:
    safe = Path(name).name
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
    cleaned = "".join(c if c in allowed else "_" for c in safe)
    return cleaned[:200] or "upload.bin"


def sanitize_upload_name(name: str) -> str:
    base = Path(name).name
    cleaned = DANGEROUS_NAME.sub("_", base).strip("._")
    return (cleaned or "upload.bin")[:200]


def is_allowed_upload(name: str) -> bool:
    return Path(name).suffix.lower() in settings.ALLOWED_UPLOAD_EXTENSIONS


def assert_allowed_extension(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in settings.ALLOWED_UPLOAD_EXTENSIONS:
        raise ValidationError(f"Disallowed file type: {ext}")
    return ext


def sniff_is_text_or_xlsx(header: bytes, filename: str) -> bool:
    """Reject files whose bytes contradict their extension."""
    ext = Path(filename).suffix.lower()
    if ext == ".xlsx":
        # ZIP/OOXML signature
        return header.startswith(b"PK")
    if ext in {".csv", ".json"}:
        return b"\x00" not in header[:512]
    return False


def load_records(file_obj, filename: str) -> list[dict[str, Any]]:
    ext = assert_allowed_extension(filename)
    raw = file_obj.read()
    if isinstance(raw, bytes):
        text = raw.decode("utf-8-sig", errors="replace")
    else:
        text = raw

    if ext == ".json":
        data = json.loads(text)
        if isinstance(data, dict) and "records" in data:
            data = data["records"]
        if not isinstance(data, list):
            raise ValidationError("JSON must be a list of records or {records: [...]}")
        return data

    if ext == ".csv":
        reader = csv.DictReader(io.StringIO(text))
        return [dict(row) for row in reader]

    if ext == ".xlsx":
        import openpyxl

        wb = openpyxl.load_workbook(
            io.BytesIO(raw if isinstance(raw, bytes) else text.encode()), read_only=True
        )
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return []
        headers = [str(h).strip() if h is not None else f"col{i}" for i, h in enumerate(rows[0])]
        out = []
        for row in rows[1:]:
            out.append({headers[i]: row[i] for i in range(len(headers))})
        return out

    raise ValidationError(f"Unsupported extension {ext}")


def normalize_weather(row: dict[str, Any], row_num: int) -> dict[str, Any] | None:
    missing = [f for f in REQUIRED_WEATHER if row.get(f) in (None, "")]
    # Graceful: skip fully empty rows
    if all(v in (None, "") for v in row.values()):
        return None
    if missing:
        # Allow partial if station_id + observed_at exist; mark missing fields
        if "station_id" not in row or "observed_at" not in row:
            raise ValidationError(f"Missing critical fields {missing}", row=row_num)

    observed_at = _parse_dt(row.get("observed_at"))
    temp = _to_float(row.get("temp_c"), "temp_c", required=False)
    precip = _to_float(row.get("precip_mm"), "precip_mm")
    humidity = _to_float(row.get("humidity_pct"), "humidity_pct")
    wind = _to_float(row.get("wind_ms"), "wind_ms")
    pressure = _to_float(row.get("pressure_hpa"), "pressure_hpa")

    missing_fields = []
    for name, val in [
        ("temp_c", temp),
        ("precip_mm", precip),
        ("humidity_pct", humidity),
        ("wind_ms", wind),
        ("pressure_hpa", pressure),
    ]:
        if val is None:
            missing_fields.append(name)

    return {
        "station_id": str(row.get("station_id", "")).strip(),
        "region": str(row.get("region", "unknown")).strip() or "unknown",
        "name": str(row.get("name", "")).strip(),
        "lat": _to_float(row.get("lat"), "lat"),
        "lon": _to_float(row.get("lon"), "lon"),
        "observed_at": observed_at,
        "temp_c": temp,
        "precip_mm": precip,
        "humidity_pct": humidity,
        "wind_ms": wind,
        "pressure_hpa": pressure,
        "missing_fields": missing_fields,
        "source": "upload",
    }


def normalize_sensor(row: dict[str, Any], row_num: int) -> dict[str, Any] | None:
    if all(v in (None, "") for v in row.values()):
        return None
    for f in REQUIRED_SENSOR:
        if row.get(f) in (None, ""):
            raise ValidationError(f"Missing required field {f}", row=row_num)
    return {
        "sensor_id": str(row["sensor_id"]).strip(),
        "region": str(row.get("region", "unknown")).strip() or "unknown",
        "metric": str(row["metric"]).strip(),
        "value": _to_float(row["value"], "value", required=True),
        "unit": str(row.get("unit", "")).strip(),
        "observed_at": _parse_dt(row["observed_at"]),
        "quality": str(row.get("quality", "good")).strip() or "good",
        "source": "upload",
    }


def normalize_satellite(row: dict[str, Any], row_num: int) -> dict[str, Any] | None:
    if all(v in (None, "") for v in row.values()):
        return None
    for f in REQUIRED_SATELLITE:
        if row.get(f) in (None, ""):
            raise ValidationError(f"Missing required field {f}", row=row_num)
    bands = row.get("bands", [])
    if isinstance(bands, str):
        bands = [b.strip() for b in bands.split(",") if b.strip()]
    return {
        "scene_id": str(row["scene_id"]).strip(),
        "satellite": str(row["satellite"]).strip(),
        "region": str(row.get("region", "unknown")).strip() or "unknown",
        "acquired_at": _parse_dt(row["acquired_at"]),
        "cloud_cover_pct": _to_float(row.get("cloud_cover_pct"), "cloud_cover_pct"),
        "bands": bands or ["B2", "B3", "B4"],
        "bbox": row.get("bbox") if isinstance(row.get("bbox"), list) else [],
        "storage_uri": str(row.get("storage_uri", "")).strip(),
        "quality_flags": row.get("quality_flags") if isinstance(row.get("quality_flags"), list) else [],
        "source": "upload",
    }
