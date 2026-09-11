"""Validate uploads and write climate documents to MongoDB."""
from __future__ import annotations

import logging
from datetime import datetime, timezone as dt_timezone
from typing import Any, BinaryIO

from bson import ObjectId

from weatherpredict.auth import User, require
from weatherpredict.db import get_collection, insert_many_safe
from weatherpredict.notifications import evaluate_value_against_rules
from weatherpredict.validators import (
    ValidationError,
    assert_allowed_extension,
    is_allowed_upload,
    load_records,
    normalize_satellite,
    normalize_sensor,
    normalize_weather,
    sanitize_filename,
    sniff_is_text_or_xlsx,
)

logger = logging.getLogger("weatherpredict.ingestion")

WEATHER = "weather"
SENSOR = "sensor"
SATELLITE = "satellite"

DATA_TYPES = {
    WEATHER: "Weather station",
    SENSOR: "Environmental sensor",
    SATELLITE: "Satellite imagery metadata",
}

NORMALIZERS = {
    WEATHER: (normalize_weather, "weather_station_records"),
    SENSOR: (normalize_sensor, "sensor_readings"),
    SATELLITE: (normalize_satellite, "satellite_imagery"),
}

PENDING, VALIDATING, IMPORTING, COMPLETED, FAILED = (
    "pending",
    "validating",
    "importing",
    "completed",
    "failed",
)


def _now() -> datetime:
    return datetime.now(tz=dt_timezone.utc)


def _jobs():
    return get_collection("ingestion_jobs")


def create_job(filename: str, data_type: str, uploaded_by: str) -> dict[str, Any]:
    if data_type not in DATA_TYPES:
        raise ValidationError(f"Invalid data type: {data_type}")
    doc = {
        "filename": sanitize_filename(filename),
        "data_type": data_type,
        "status": PENDING,
        "uploaded_by": uploaded_by,
        "records_total": 0,
        "records_imported": 0,
        "records_skipped": 0,
        "error_log": "",
        "created_at": _now(),
        "finished_at": None,
    }
    doc["_id"] = _jobs().insert_one(doc).inserted_id
    return doc


def _save_job(job: dict[str, Any], fields: tuple[str, ...]) -> None:
    _jobs().update_one({"_id": job["_id"]}, {"$set": {f: job[f] for f in fields}})


def run_ingestion(job: dict[str, Any], file_obj: BinaryIO) -> dict[str, Any]:
    """Validate and import one uploaded file, updating the job ledger in place."""
    job["status"] = VALIDATING
    job["filename"] = sanitize_filename(job["filename"])
    _save_job(job, ("status", "filename"))

    errors: list[str] = []
    docs: list[dict[str, Any]] = []
    skipped = 0

    try:
        raw_rows = load_records(file_obj, job["filename"])
    except Exception as exc:  # noqa: BLE001
        job["status"] = FAILED
        job["error_log"] = str(exc)
        job["finished_at"] = _now()
        _save_job(job, ("status", "error_log", "finished_at"))
        return job

    job["records_total"] = len(raw_rows)
    normalizer, collection = NORMALIZERS[job["data_type"]]
    job["status"] = IMPORTING
    _save_job(job, ("status", "records_total"))

    for i, row in enumerate(raw_rows, start=1):
        try:
            doc = normalizer(row, i)
            if doc is None:
                skipped += 1
                continue
            docs.append(doc)
        except ValidationError as exc:
            errors.append(f"row {exc.row or i}: {exc}")
            skipped += 1
        except Exception as exc:  # noqa: BLE001
            errors.append(f"row {i}: {exc}")
            skipped += 1

    imported = 0
    if docs:
        if job["data_type"] == SATELLITE:
            # Upsert on scene_id.
            coll = get_collection(collection)
            for d in docs:
                coll.update_one({"scene_id": d["scene_id"]}, {"$set": d}, upsert=True)
                imported += 1
        else:
            imported = insert_many_safe(collection, docs)

        for d in docs:
            if job["data_type"] == WEATHER and d.get("temp_c") is not None:
                evaluate_value_against_rules("temp_c", float(d["temp_c"]), d.get("region", ""))
            if job["data_type"] == SENSOR and d.get("value") is not None:
                evaluate_value_against_rules(
                    d.get("metric", "value"), float(d["value"]), d.get("region", "")
                )

    job["records_imported"] = imported
    job["records_skipped"] = skipped
    job["error_log"] = "\n".join(errors[:200])
    job["status"] = COMPLETED if imported or not errors else FAILED
    job["finished_at"] = _now()
    _save_job(
        job, ("records_imported", "records_skipped", "error_log", "status", "finished_at")
    )
    logger.info(
        "Ingestion job %s finished status=%s imported=%s skipped=%s",
        job["_id"],
        job["status"],
        imported,
        skipped,
    )
    return job


def ingest_upload(
    file_obj: BinaryIO,
    filename: str,
    data_type: str,
    user: User,
) -> dict[str, Any]:
    """Validate and import one uploaded file."""
    require(user, "ingest_data")
    assert_allowed_extension(filename)
    if not is_allowed_upload(filename):
        raise ValidationError("Disallowed upload type")
    header = file_obj.read(512)
    file_obj.seek(0)
    if not sniff_is_text_or_xlsx(header, filename):
        raise ValidationError("File content does not match an allowed climate upload format")
    job = create_job(filename, data_type, user.username)
    return run_ingestion(job, file_obj)


def recent_jobs(limit: int = 50) -> list[dict[str, Any]]:
    return list(_jobs().find().sort("created_at", -1).limit(limit))


def ingestion_stats() -> dict[str, Any]:
    coll = _jobs()
    agg = list(
        coll.aggregate(
            [
                {
                    "$group": {
                        "_id": None,
                        "jobs": {"$sum": 1},
                        "imported": {"$sum": "$records_imported"},
                        "skipped": {"$sum": "$records_skipped"},
                    }
                }
            ]
        )
    )
    totals = agg[0] if agg else {"jobs": 0, "imported": 0, "skipped": 0}
    by_status = {
        row["_id"]: row["n"]
        for row in coll.aggregate([{"$group": {"_id": "$status", "n": {"$sum": 1}}}])
    }
    return {
        "jobs": totals.get("jobs", 0),
        "records_imported": totals.get("imported", 0) or 0,
        "records_skipped": totals.get("skipped", 0) or 0,
        "by_status": by_status,
    }


def get_job(job_id: str | ObjectId) -> dict[str, Any] | None:
    if isinstance(job_id, str):
        job_id = ObjectId(job_id)
    return _jobs().find_one({"_id": job_id})
