"""Pipeline run ledger."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone as dt_timezone
from typing import Any

from bson import ObjectId

from weatherpredict.db import get_collection

logger = logging.getLogger("weatherpredict.pipelines")

BATCH_CLEAN = "batch_clean"
SYNTHETIC = "synthetic"
REALTIME_TICK = "realtime_tick"
ML_TRAIN = "ml_train"

JOB_LABELS = {
    BATCH_CLEAN: "Batch clean & aggregate",
    SYNTHETIC: "Synthetic data generation",
    REALTIME_TICK: "Realtime sensor tick",
    ML_TRAIN: "ML training",
}

RUNNING = "running"
SUCCESS = "success"
FAILED = "failed"


def _now() -> datetime:
    return datetime.now(tz=dt_timezone.utc)


def start_run(job_type: str, adapter: str = "local", triggered_by: str | None = None) -> dict[str, Any]:
    doc = {
        "job_type": job_type,
        "status": RUNNING,
        "adapter": adapter,
        "started_at": _now(),
        "finished_at": None,
        "stats": {},
        "error": "",
        "triggered_by": triggered_by,
    }
    doc["_id"] = get_collection("pipeline_runs").insert_one(doc).inserted_id
    return doc


def finish_run(
    run: dict[str, Any],
    status: str,
    stats: dict[str, Any] | None = None,
    error: str = "",
) -> dict[str, Any]:
    run["status"] = status
    run["stats"] = stats or run.get("stats") or {}
    run["error"] = error
    run["finished_at"] = _now()
    started = run.get("started_at")
    if started and run["finished_at"]:
        run["duration_seconds"] = round((run["finished_at"] - started).total_seconds(), 3)
    get_collection("pipeline_runs").update_one(
        {"_id": run["_id"]},
        {"$set": {k: run[k] for k in ("status", "stats", "error", "finished_at", "duration_seconds") if k in run}},
    )
    level = logger.info if status == SUCCESS else logger.error
    level("Pipeline %s finished status=%s stats=%s", run.get("job_type"), status, run["stats"])
    return run


def record_run(
    job_type: str,
    status: str = SUCCESS,
    adapter: str = "local",
    stats: dict[str, Any] | None = None,
    triggered_by: str | None = None,
) -> dict[str, Any]:
    """One-shot ledger entry for jobs that complete inline (e.g. realtime ticks)."""
    run = start_run(job_type, adapter=adapter, triggered_by=triggered_by)
    return finish_run(run, status, stats)


def recent_runs(limit: int = 50, job_type: str | None = None) -> list[dict[str, Any]]:
    query = {"job_type": job_type} if job_type else {}
    return list(get_collection("pipeline_runs").find(query).sort("started_at", -1).limit(limit))


def run_stats(window_days: int = 7) -> dict[str, int]:
    coll = get_collection("pipeline_runs")
    cutoff = _now() - timedelta(days=window_days)
    return {
        "total": coll.count_documents({}),
        "success_week": coll.count_documents({"status": SUCCESS, "started_at": {"$gte": cutoff}}),
        "failed_week": coll.count_documents({"status": FAILED, "started_at": {"$gte": cutoff}}),
        "running": coll.count_documents({"status": RUNNING}),
    }


def get_run(run_id: str | ObjectId) -> dict[str, Any] | None:
    if isinstance(run_id, str):
        run_id = ObjectId(run_id)
    return get_collection("pipeline_runs").find_one({"_id": run_id})
