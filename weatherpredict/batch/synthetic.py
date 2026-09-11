"""Synthetic realistic climate dataset generator."""
from __future__ import annotations

import csv
import math
import random
from datetime import datetime, timedelta, timezone as dt_timezone
from typing import Any

from weatherpredict import pipelines, settings
from weatherpredict.auth import User, require
from weatherpredict.db import get_collection, insert_many_safe

REGIONS = {
    "pacific_nw": {"lat": 47.6, "lon": -122.3, "base_temp": 11.0, "precip_base": 2.5},
    "southwest": {"lat": 33.4, "lon": -112.0, "base_temp": 23.0, "precip_base": 0.4},
    "great_lakes": {"lat": 41.9, "lon": -87.6, "base_temp": 10.0, "precip_base": 2.0},
    "southeast": {"lat": 33.7, "lon": -84.4, "base_temp": 18.0, "precip_base": 3.2},
    "northeast": {"lat": 40.7, "lon": -74.0, "base_temp": 12.5, "precip_base": 2.8},
}


def _seasonal_temp(base: float, day_of_year: int, lat: float) -> float:
    # Northern hemisphere seasonal cycle
    seasonal = -math.cos(2 * math.pi * (day_of_year - 15) / 365.0) * (8 + abs(lat) / 20)
    noise = random.gauss(0, 1.8)
    return base + seasonal + noise


def generate_synthetic_dataset(
    years: int = 3,
    seed: int = 42,
    user: User | None = None,
    clear_existing: bool = False,
) -> dict[str, Any]:
    """Generate multi-year synthetic climate data. Administrators only."""
    require(user, "generate_data")
    random.seed(seed)
    run = pipelines.start_run(
        pipelines.SYNTHETIC, adapter="generator", triggered_by=user.username if user else None
    )
    try:
        end = datetime.now(tz=dt_timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        start = end - timedelta(days=365 * years)

        weather_docs: list[dict[str, Any]] = []
        sensor_docs: list[dict[str, Any]] = []
        sat_docs: list[dict[str, Any]] = []

        day = start
        while day <= end:
            doy = day.timetuple().tm_yday
            for region, meta in REGIONS.items():
                temp = _seasonal_temp(meta["base_temp"], doy, meta["lat"])
                # Believable heat anomaly spikes (~1.5% of days)
                if random.random() < 0.015:
                    temp += random.uniform(8, 14)
                precip = max(0.0, random.gauss(meta["precip_base"], meta["precip_base"]))
                if random.random() < 0.08:
                    precip = 0.0
                station_id = f"STN-{region[:3].upper()}-01"
                weather_docs.append(
                    {
                        "station_id": station_id,
                        "region": region,
                        "name": f"{region} primary",
                        "lat": meta["lat"],
                        "lon": meta["lon"],
                        "observed_at": day,
                        "temp_c": round(temp, 2),
                        "precip_mm": round(precip, 2),
                        "humidity_pct": round(min(100, max(10, random.gauss(65, 12))), 1),
                        "wind_ms": round(max(0, random.gauss(3.5, 1.2)), 2),
                        "pressure_hpa": round(random.gauss(1013, 6), 1),
                        "missing_fields": [],
                        "source": "synthetic",
                    }
                )
                # Occasional missing humidity
                if random.random() < 0.03:
                    weather_docs[-1]["humidity_pct"] = None
                    weather_docs[-1]["missing_fields"] = ["humidity_pct"]

                for metric, unit, base in [
                    ("co2_ppm", "ppm", 415 + (day - start).days * 0.006),
                    ("soil_moisture", "pct", 35),
                    ("uv_index", "index", 5),
                ]:
                    value = base + random.gauss(0, base * 0.03 if metric != "uv_index" else 1.2)
                    if metric == "uv_index":
                        value = max(0, value + 2 * math.sin(2 * math.pi * doy / 365))
                    if metric == "co2_ppm" and random.random() < 0.01:
                        value += random.uniform(20, 40)  # anomaly
                    sensor_docs.append(
                        {
                            "sensor_id": f"ENV-{region[:3].upper()}-{metric[:3].upper()}",
                            "region": region,
                            "metric": metric,
                            "value": round(float(value), 3),
                            "unit": unit,
                            "observed_at": day,
                            "quality": "good",
                            "source": "synthetic",
                        }
                    )

                # Weekly satellite scene
                if day.weekday() == 0:
                    sat_docs.append(
                        {
                            "scene_id": f"SC_{region}_{day.strftime('%Y%m%d')}",
                            "satellite": random.choice(["Landsat-8", "Sentinel-2", "MODIS"]),
                            "region": region,
                            "acquired_at": day + timedelta(hours=18),
                            "cloud_cover_pct": round(min(100, max(0, random.gauss(25, 20))), 1),
                            "bands": ["B2", "B3", "B4", "B5"],
                            "bbox": [
                                meta["lon"] - 1,
                                meta["lat"] - 1,
                                meta["lon"] + 1,
                                meta["lat"] + 1,
                            ],
                            "storage_uri": f"local://data/synthetic/{region}/{day.strftime('%Y%m%d')}.tif",
                            "quality_flags": [],
                            "source": "synthetic",
                        }
                    )
            day += timedelta(days=1)

        if clear_existing:
            for name in ("weather_station_records", "sensor_readings", "satellite_imagery"):
                get_collection(name).delete_many({"source": "synthetic"})

        w = insert_many_safe("weather_station_records", weather_docs)
        s = insert_many_safe("sensor_readings", sensor_docs)
        # Satellite scenes upsert on scene_id
        coll = get_collection("satellite_imagery")
        sat_count = 0
        for d in sat_docs:
            coll.update_one({"scene_id": d["scene_id"]}, {"$set": d}, upsert=True)
            sat_count += 1

        # Also write a CSV sample for offline inspection
        out = settings.DATA_DIR / "synthetic"
        out.mkdir(parents=True, exist_ok=True)
        with (out / "weather_sample.csv").open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(
                fh,
                fieldnames=[
                    "station_id",
                    "region",
                    "observed_at",
                    "temp_c",
                    "precip_mm",
                    "humidity_pct",
                    "wind_ms",
                    "pressure_hpa",
                ],
            )
            writer.writeheader()
            for row in weather_docs[::30]:
                writer.writerow(
                    {
                        "station_id": row["station_id"],
                        "region": row["region"],
                        "observed_at": row["observed_at"].isoformat(),
                        "temp_c": row["temp_c"],
                        "precip_mm": row["precip_mm"],
                        "humidity_pct": row["humidity_pct"],
                        "wind_ms": row["wind_ms"],
                        "pressure_hpa": row["pressure_hpa"],
                    }
                )

        return pipelines.finish_run(
            run,
            pipelines.SUCCESS,
            {
                "weather": w,
                "sensors": s,
                "satellite": sat_count,
                "years": years,
                "regions": list(REGIONS.keys()),
            },
        )
    except Exception as exc:  # noqa: BLE001
        pipelines.finish_run(run, pipelines.FAILED, error=str(exc))
        raise
