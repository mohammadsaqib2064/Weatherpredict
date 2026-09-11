"""MongoDB client, collections and indexes."""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

from weatherpredict import cache, settings

logger = logging.getLogger("weatherpredict.mongo")

CLIMATE_COLLECTIONS = (
    "satellite_imagery",
    "weather_station_records",
    "sensor_readings",
    "ml_predictions",
    "anomalies",
    "batch_aggregates",
)

APP_COLLECTIONS = (
    "users",
    "notifications",
    "alert_rules",
    "support_tickets",
    "feedback",
    "pipeline_runs",
    "ingestion_jobs",
    "ml_artifacts",
)

COLLECTIONS = CLIMATE_COLLECTIONS + APP_COLLECTIONS


@lru_cache(maxsize=1)
def get_client() -> MongoClient:
    client = MongoClient(
        settings.MONGODB_URI,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
        # Datetimes come back UTC-aware so app code never mixes naive/aware values.
        tz_aware=True,
    )
    client.admin.command("ping")
    logger.info("Connected to MongoDB at %s", settings.MONGODB_URI)
    return client


def get_db() -> Database:
    return get_client()[settings.MONGODB_DB]


def get_collection(name: str) -> Collection:
    if name not in COLLECTIONS:
        raise ValueError(f"Unknown collection: {name}")
    return get_db()[name]


def ensure_indexes() -> None:
    db = get_db()

    # --- climate ---
    db.weather_station_records.create_index([("region", ASCENDING), ("observed_at", DESCENDING)])
    db.weather_station_records.create_index([("station_id", ASCENDING), ("observed_at", DESCENDING)])
    db.sensor_readings.create_index([("region", ASCENDING), ("metric", ASCENDING), ("observed_at", DESCENDING)])
    db.sensor_readings.create_index([("sensor_id", ASCENDING), ("observed_at", DESCENDING)])
    db.satellite_imagery.create_index([("region", ASCENDING), ("acquired_at", DESCENDING)])
    db.satellite_imagery.create_index([("scene_id", ASCENDING)], unique=True)
    db.anomalies.create_index([("region", ASCENDING), ("observed_at", DESCENDING)])
    db.anomalies.create_index(
        [("region", ASCENDING), ("metric", ASCENDING), ("observed_at", ASCENDING)],
        unique=True,
        name="anomaly_identity_unique",
    )
    db.ml_predictions.create_index([("region", ASCENDING), ("generated_at", DESCENDING)])
    db.batch_aggregates.create_index([("region", ASCENDING), ("period", ASCENDING), ("metric", ASCENDING)])

    # --- operational ---
    db.users.create_index([("username", ASCENDING)], unique=True, name="user_username_unique")
    db.notifications.create_index([("username", ASCENDING), ("created_at", DESCENDING)])
    db.notifications.create_index([("is_read", ASCENDING)])
    db.alert_rules.create_index([("metric", ASCENDING), ("active", ASCENDING)])
    db.alert_rules.create_index([("name", ASCENDING)], unique=True, name="alert_rule_name_unique")
    db.support_tickets.create_index([("created_at", DESCENDING)])
    db.support_tickets.create_index([("created_by", ASCENDING), ("status", ASCENDING)])
    db.feedback.create_index([("created_at", DESCENDING)])
    db.pipeline_runs.create_index([("started_at", DESCENDING)])
    db.pipeline_runs.create_index([("job_type", ASCENDING), ("status", ASCENDING)])
    db.ingestion_jobs.create_index([("created_at", DESCENDING)])
    db.ml_artifacts.create_index(
        [("name", ASCENDING), ("version", ASCENDING)], unique=True, name="ml_artifact_identity_unique"
    )
    logger.info("MongoDB indexes ensured")


def insert_many_safe(collection: str, docs: list[dict[str, Any]]) -> int:
    if not docs:
        return 0
    result = get_collection(collection).insert_many(docs, ordered=False)
    return len(result.inserted_ids)


_PING_CACHE_KEY = "wp:mongo:ping"
_PING_CACHE_SECONDS = 10


def ping(use_cache: bool = True) -> bool:
    """Report MongoDB reachability.

    A single page can ask several services whether Mongo is up; the result is
    cached briefly so those callers share one round-trip instead of one each.
    """
    if use_cache:
        cached = cache.get(_PING_CACHE_KEY)
        if cached is not None:
            return cached
    try:
        get_client().admin.command("ping")
        alive = True
    except Exception as exc:  # noqa: BLE001
        logger.error("MongoDB ping failed: %s", exc)
        alive = False
    if use_cache:
        cache.set(_PING_CACHE_KEY, alive, _PING_CACHE_SECONDS)
    return alive


def collection_counts() -> dict[str, int]:
    """Exact document counts for every known collection (used by the console)."""
    if not ping():
        return {}
    db = get_db()
    existing = set(db.list_collection_names())
    return {name: db[name].count_documents({}) for name in COLLECTIONS if name in existing}
