"""MongoDB and artifact backup. ``python -m weatherpredict.backup``."""
from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timedelta, timezone as dt_timezone
from pathlib import Path

from weatherpredict import settings
from weatherpredict.db import COLLECTIONS, get_collection, ping

BACKUP_ROOT = settings.BASE_DIR / "backups"
KEEP_DAYS = 14


def _stamp() -> str:
    return datetime.now(tz=dt_timezone.utc).strftime("%Y%m%d_%H%M%S")


def _json_dump(dest: Path) -> dict[str, int]:
    dest.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    for name in COLLECTIONS:
        docs = []
        for doc in get_collection(name).find():
            doc["_id"] = str(doc.get("_id"))
            docs.append(doc)
        (dest / f"{name}.json").write_text(json.dumps(docs, default=str), encoding="utf-8")
        counts[name] = len(docs)
    return counts


def run_backup() -> Path:
    stamp = _stamp()
    folder = BACKUP_ROOT / stamp
    mongo_dir = folder / "mongo"
    mongo_dir.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    method = "json"
    dump = shutil.which("mongodump")
    if dump:
        result = subprocess.run(
            [dump, "--uri", settings.MONGODB_URI, "--db", settings.MONGODB_DB, "--out", str(mongo_dir)],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            method = "mongodump"
            counts = {n: get_collection(n).estimated_document_count() for n in COLLECTIONS} if ping() else {}
        else:
            counts = _json_dump(mongo_dir)
    else:
        counts = _json_dump(mongo_dir)

    artifacts = settings.ARTIFACT_DIR
    if artifacts.exists():
        shutil.copytree(artifacts, folder / "ml_artifacts", dirs_exist_ok=True)

    manifest = {
        "created_at": datetime.now(tz=dt_timezone.utc).isoformat(),
        "mongodb_db": settings.MONGODB_DB,
        "method": method,
        "counts": counts,
        "mongo_ok": ping(use_cache=False),
    }
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    _prune()
    return folder


def _prune() -> None:
    cutoff = datetime.now(tz=dt_timezone.utc) - timedelta(days=KEEP_DAYS)
    if not BACKUP_ROOT.exists():
        return
    for child in BACKUP_ROOT.iterdir():
        if not child.is_dir():
            continue
        try:
            stamped = datetime.strptime(child.name, "%Y%m%d_%H%M%S").replace(tzinfo=dt_timezone.utc)
        except ValueError:
            continue
        if stamped < cutoff:
            shutil.rmtree(child, ignore_errors=True)


def main() -> int:
    folder = run_backup()
    print(f"Backup written to {folder}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
