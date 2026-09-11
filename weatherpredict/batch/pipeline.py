"""Batch pipeline orchestration."""
from __future__ import annotations

import logging
from datetime import datetime, timezone as dt_timezone
from typing import Any

import pandas as pd

from weatherpredict import pipelines, settings
from weatherpredict.auth import User, require
from weatherpredict.batch.adapters import get_adapter
from weatherpredict.db import get_collection

logger = logging.getLogger("weatherpredict.batch")


def _mongo_to_df(collection: str, limit: int | None = None) -> pd.DataFrame:
    coll = get_collection(collection)
    cursor = coll.find({}, {"_id": 0})
    if limit:
        cursor = cursor.limit(limit)
    docs = list(cursor)
    if not docs:
        return pd.DataFrame()
    return pd.DataFrame(docs)


def run_batch_pipeline(user: User | None = None, adapter_name: str = "local") -> dict[str, Any]:
    """Clean, partition and aggregate the climate corpus. Administrators only."""
    require(user, "run_batch")
    run = pipelines.start_run(
        pipelines.BATCH_CLEAN, adapter=adapter_name, triggered_by=user.username if user else None
    )
    try:
        adapter = get_adapter(adapter_name)
        weather = _mongo_to_df("weather_station_records")
        sensors = _mongo_to_df("sensor_readings")

        stats: dict[str, Any] = {"weather_rows": len(weather), "sensor_rows": len(sensors)}
        stamp = datetime.now(tz=dt_timezone.utc).strftime("%Y%m%d_%H%M%S")
        out_root = settings.DATA_DIR / "processed" / stamp
        out_root.mkdir(parents=True, exist_ok=True)

        aggregate_frames = []
        for label, df, keys in [
            ("weather", weather, ["region"]),
            ("sensor", sensors, ["region", "metric"]),
        ]:
            cleaned = adapter.clean(df)
            partitions = adapter.partition(cleaned, keys)
            paths = adapter.write_partitions(partitions, out_root / label)
            stats[f"{label}_partitions"] = len(paths)
            stats[f"{label}_cleaned"] = len(cleaned)
            agg = adapter.reduce_aggregate(partitions)
            if not agg.empty:
                aggregate_frames.append(agg.assign(source=label))

        if aggregate_frames:
            aggregates = pd.concat(aggregate_frames, ignore_index=True)
            coll = get_collection("batch_aggregates")
            # Upsert on (region, period, source) so re-runs replace rather than append.
            docs = aggregates.to_dict(orient="records")
            for d in docs:
                for k, v in list(d.items()):
                    if hasattr(v, "item"):
                        d[k] = v.item()
                filt = {
                    "region": d.get("region"),
                    "period": d.get("period"),
                    "source": d.get("source"),
                }
                coll.update_one(filt, {"$set": d}, upsert=True)
            stats["aggregates_upserted"] = len(docs)
            aggregates.to_csv(out_root / "aggregates.csv", index=False)
        else:
            stats["aggregates_upserted"] = 0

        stats["output_dir"] = str(out_root)
        logger.info("Batch pipeline success: %s", stats)
        return pipelines.finish_run(run, pipelines.SUCCESS, stats)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Batch pipeline failed")
        return pipelines.finish_run(run, pipelines.FAILED, error=str(exc))
