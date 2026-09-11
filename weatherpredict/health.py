"""Health snapshot used by the console and ``python -m weatherpredict.health``."""
from __future__ import annotations

import json
import os
import shutil
import sys
from datetime import datetime, timezone as dt_timezone

from weatherpredict import pipelines, settings
from weatherpredict.db import ping


def resource_stats() -> dict:
    disk = shutil.disk_usage(settings.BASE_DIR)
    rss_mb = None
    cpu = None
    try:
        import resource  # Unix only

        rss_mb = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
    except (ImportError, AttributeError):
        pass
    return {
        "pid": os.getpid(),
        "rss_mb": rss_mb,
        "disk_free_gb": round(disk.free / (1024**3), 2),
        "disk_total_gb": round(disk.total / (1024**3), 2),
        "cpu_percent": cpu,
        "single_worker": True,
    }


def status() -> dict:
    mongo_ok = ping(use_cache=False)
    last = None
    try:
        runs = pipelines.recent_runs(1)
        if runs:
            last = {
                "job_type": runs[0].get("job_type"),
                "status": runs[0].get("status"),
                "duration_seconds": runs[0].get("duration_seconds"),
            }
    except Exception:  # noqa: BLE001
        last = None
    payload = {
        "app": "ok" if mongo_ok else "degraded",
        "mongo": mongo_ok,
        "last_pipeline": last,
        "checked_at": datetime.now(tz=dt_timezone.utc).isoformat(),
        "maintenance": settings.MAINTENANCE_MESSAGE or None,
        "resources": resource_stats(),
    }
    return payload


def main() -> int:
    payload = status()
    json.dump(payload, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0 if payload["mongo"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
