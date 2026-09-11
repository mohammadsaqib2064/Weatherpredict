"""Aggregates for the Administrator console and Analyst workspace."""
from __future__ import annotations

from datetime import datetime, timezone as dt_timezone
from typing import Any

from weatherpredict import cache, ingestion, notifications, pipelines, settings, support
from weatherpredict.auth import User, count_users, list_users
from weatherpredict.db import get_collection, ping
from weatherpredict.scoping import allowed_regions, constrain_region

_EPOCH = datetime.min.replace(tzinfo=dt_timezone.utc)


def invalidate_cache() -> None:
    """Clear cached console aggregates."""
    cache.invalidate()


def _build_system_overview() -> dict[str, Any]:
    mongo_ok = ping()
    if not mongo_ok:
        return {
            "mongo_ok": False,
            "health": "critical",
            "weather_records": 0,
            "sensor_readings": 0,
            "satellite_scenes": 0,
            "anomalies": 0,
            "batch_aggregates": 0,
            "predictions": 0,
            "users": 0,
            "active_users": 0,
            "inactive_users": 0,
            "administrators": 0,
            "analysts": 0,
            "ingestion_jobs": 0,
            "records_imported": 0,
            "records_skipped": 0,
            "ingest_by_status": {},
            "pipeline_runs": 0,
            "pipeline_success_week": 0,
            "pipeline_failed_week": 0,
            "pipeline_running": 0,
            "open_tickets": 0,
            "unread_notifications": 0,
            "alert_rules": 0,
            "recent_pipelines": [],
            "recent_ingestions": [],
            "recent_alerts": [],
            "recent_users": [],
        }

    counts = {
        name: get_collection(name).count_documents({})
        for name in (
            "weather_station_records",
            "sensor_readings",
            "satellite_imagery",
            "anomalies",
            "batch_aggregates",
            "ml_predictions",
        )
    }
    users = count_users()
    pipeline_stats = pipelines.run_stats()
    ingest = ingestion.ingestion_stats()

    health = "degraded"
    if pipeline_stats["running"] == 0 and pipeline_stats["failed_week"] == 0:
        health = "healthy"
    elif pipeline_stats["failed_week"] > 0:
        health = "attention"

    return {
        "mongo_ok": True,
        "health": health,
        "weather_records": counts["weather_station_records"],
        "sensor_readings": counts["sensor_readings"],
        "satellite_scenes": counts["satellite_imagery"],
        "anomalies": counts["anomalies"],
        "batch_aggregates": counts["batch_aggregates"],
        "predictions": counts["ml_predictions"],
        "users": users["total"],
        "active_users": users["active"],
        "inactive_users": users["inactive"],
        "administrators": users["administrators"],
        "analysts": users["analysts"],
        "ingestion_jobs": ingest["jobs"],
        "records_imported": ingest["records_imported"],
        "records_skipped": ingest["records_skipped"],
        "ingest_by_status": ingest["by_status"],
        "pipeline_runs": pipeline_stats["total"],
        "pipeline_success_week": pipeline_stats["success_week"],
        "pipeline_failed_week": pipeline_stats["failed_week"],
        "pipeline_running": pipeline_stats["running"],
        "open_tickets": support.open_ticket_count(),
        "unread_notifications": notifications.unread_count(),
        "alert_rules": len(notifications.list_rules(active_only=True)),
        "recent_pipelines": pipelines.recent_runs(10),
        "recent_ingestions": ingestion.recent_jobs(8),
        "recent_alerts": notifications.recent_alerts(8),
        "recent_users": [
            {
                "username": u.username,
                "email": u.email,
                "role": u.role,
                "is_active": u.is_active,
                "region_focus": u.region_focus,
                "created_at": u.created_at,
            }
            for u in sorted(list_users(), key=lambda u: u.created_at or _EPOCH, reverse=True)[:8]
        ],
    }


def system_overview(refresh: bool = False) -> dict[str, Any]:
    """Cached system-wide counters for the Administrator console."""
    key = f"wp:console:overview:{cache.generation()}"
    return cache.get_or_set(key, _build_system_overview, settings.CACHE_SECONDS, refresh)


def _build_region_temp_summary(limit_regions: int, user: User | None = None) -> list[dict[str, Any]]:
    if not ping():
        return []
    match: dict[str, Any] = {"temp_c": {"$ne": None}}
    allowed = allowed_regions(user)
    if allowed is not None:
        if not allowed:
            return []
        match["region"] = {"$in": allowed}
    pipeline = [
        {"$match": match},
        {
            "$group": {
                "_id": "$region",
                "avg_temp": {"$avg": "$temp_c"},
                "min_temp": {"$min": "$temp_c"},
                "max_temp": {"$max": "$temp_c"},
                "n": {"$sum": 1},
            }
        },
        {"$sort": {"_id": 1}},
        {"$limit": limit_regions},
    ]
    rows = list(get_collection("weather_station_records").aggregate(pipeline))
    return [
        {
            "region": r["_id"],
            "avg_temp": round(r["avg_temp"], 2),
            "min_temp": round(r["min_temp"], 2),
            "max_temp": round(r["max_temp"], 2),
            "n": r["n"],
        }
        for r in rows
    ]


def region_temp_summary(
    limit_regions: int = 8, refresh: bool = False, user: User | None = None
) -> list[dict[str, Any]]:
    """Cached per-region temperature rollup."""
    scope = ",".join(allowed_regions(user) or ["*"])
    key = f"wp:console:region_temp:{limit_regions}:{scope}:{cache.generation()}"
    return cache.get_or_set(
        key,
        lambda: _build_region_temp_summary(limit_regions, user),
        settings.CACHE_SECONDS,
        refresh,
    )


def recent_anomalies_preview(limit: int = 12, user: User | None = None) -> list[dict[str, Any]]:
    if not ping():
        return []
    query: dict[str, Any] = {}
    allowed = allowed_regions(user)
    if allowed is not None:
        if not allowed:
            return []
        query["region"] = {"$in": allowed}
    cursor = get_collection("anomalies").find(query, {"_id": 0}).sort("observed_at", -1).limit(limit)
    out = []
    for doc in cursor:
        observed = doc.get("observed_at")
        out.append(
            {
                "region": doc.get("region", "—"),
                "value": doc.get("value"),
                "baseline": doc.get("baseline"),
                "z_score": doc.get("z_score"),
                "severity": doc.get("severity", "low"),
                "method": doc.get("method", ""),
                "observed_at": observed.isoformat() if hasattr(observed, "isoformat") else str(observed or ""),
            }
        )
    return out


def analyst_exploration_snapshot(user: User | None = None) -> dict[str, Any]:
    """Compact exploration payload for the Analyst workspace hub."""
    overview = system_overview()
    return {
        "overview": overview,
        "regions": region_temp_summary(user=user),
        "anomalies": recent_anomalies_preview(user=user),
        "mongo_ok": overview["mongo_ok"],
    }


def daily_region_frame(region: str, days: int = 365, user: User | None = None) -> list[dict[str, Any]]:
    """Daily temperature/precipitation means for one region — exploration charts."""
    region = constrain_region(user, region) or region
    pipeline = [
        {"$match": {"region": region, "temp_c": {"$ne": None}}},
        {"$sort": {"observed_at": -1}},
        {"$limit": days},
        {
            "$project": {
                "_id": 0,
                "observed_at": 1,
                "temp_c": 1,
                "precip_mm": 1,
                "humidity_pct": 1,
            }
        },
    ]
    rows = list(get_collection("weather_station_records").aggregate(pipeline))
    rows.sort(key=lambda r: r["observed_at"])
    return rows
