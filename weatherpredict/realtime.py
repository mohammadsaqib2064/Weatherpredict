"""Simulated sensor ticks and a merged batch/realtime series."""
from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta, timezone as dt_timezone
from typing import Any

from weatherpredict import pipelines
from weatherpredict.auth import User, require
from weatherpredict.batch.synthetic import REGIONS
from weatherpredict.db import get_collection, insert_many_safe
from weatherpredict.notifications import evaluate_value_against_rules
from weatherpredict.scoping import constrain_region

logger = logging.getLogger("weatherpredict.realtime")

LIVE_METRICS = [
    ("co2_ppm", "ppm", 420),
    ("soil_moisture", "pct", 34),
    ("uv_index", "index", 6),
    ("temp_c", "C", None),  # also push live temp as a sensor stream
]


def emit_sensor_tick(n_readings: int = 10, user: User | None = None) -> list[dict[str, Any]]:
    """Emit a burst of near-real-time sensor readings."""
    if user is not None:
        require(user, "emit_realtime_tick")
    now = datetime.now(tz=dt_timezone.utc)
    docs: list[dict[str, Any]] = []
    regions = list(REGIONS.keys())
    for _ in range(n_readings):
        region = random.choice(regions)
        metric, unit, base = random.choice(LIVE_METRICS)
        if base is None:
            base = REGIONS[region]["base_temp"] + random.gauss(0, 2)
        value = float(base) + random.gauss(0, base * 0.02 if metric != "uv_index" else 0.8)
        if random.random() < 0.05:
            value += random.uniform(15, 30)  # spike for alert demos
        doc = {
            "sensor_id": f"LIVE-{region[:3].upper()}-{metric[:3].upper()}",
            "region": region,
            "metric": metric,
            "value": round(value, 3),
            "unit": unit,
            "observed_at": now,
            "quality": "good",
            "source": "realtime",
        }
        docs.append(doc)
        evaluate_value_against_rules(metric, doc["value"], region, context="realtime tick")

    insert_many_safe("sensor_readings", docs)
    pipelines.record_run(
        pipelines.REALTIME_TICK,
        adapter="simulator",
        stats={"emitted": len(docs)},
        triggered_by=user.username if user else None,
    )
    logger.info("Realtime tick emitted %s readings", len(docs))
    return docs


def unified_series(
    region: str,
    metric: str = "temp_c",
    hours: int = 72,
    user: User | None = None,
) -> dict[str, Any]:
    """Merge batch weather/aggregates with recent realtime sensor readings."""
    region = constrain_region(user, region) or region
    since = datetime.now(tz=dt_timezone.utc) - timedelta(hours=hours)
    weather = list(
        get_collection("weather_station_records")
        .find({"region": region, "observed_at": {"$gte": since}}, {"_id": 0})
        .sort("observed_at", 1)
    )
    sensors = list(
        get_collection("sensor_readings")
        .find(
            {"region": region, "metric": metric, "observed_at": {"$gte": since}},
            {"_id": 0},
        )
        .sort("observed_at", 1)
    )
    aggregates = list(
        get_collection("batch_aggregates").find({"region": region}, {"_id": 0}).limit(24)
    )

    points = []
    if metric == "temp_c":
        for w in weather:
            if w.get("temp_c") is not None:
                observed = w["observed_at"]
                points.append(
                    {
                        "t": observed.isoformat() if hasattr(observed, "isoformat") else str(observed),
                        "v": w["temp_c"],
                        "source": w.get("source", "batch"),
                    }
                )
    for s in sensors:
        observed = s["observed_at"]
        points.append(
            {
                "t": observed.isoformat() if hasattr(observed, "isoformat") else str(observed),
                "v": s["value"],
                "source": s.get("source", "realtime"),
            }
        )
    points.sort(key=lambda p: p["t"])
    return {
        "region": region,
        "metric": metric,
        "points": points,
        "aggregates": aggregates,
        "counts": {"weather": len(weather), "sensors": len(sensors), "merged": len(points)},
    }


def latest_readings(limit: int = 15, region: str | None = None) -> list[dict[str, Any]]:
    query: dict[str, Any] = {"source": "realtime"}
    if region:
        query["region"] = region
    return list(
        get_collection("sensor_readings").find(query, {"_id": 0}).sort("observed_at", -1).limit(limit)
    )
