"""Application settings loaded from ``.env``."""
from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _int(name: str, default: int) -> int:
    try:
        return int(_str(name, str(default)))
    except ValueError:
        return default


def _str(name: str, default: str) -> str:
    """Read config from the process env, then Streamlit Cloud secrets."""
    env = os.getenv(name)
    if env and env.strip():
        return env.strip()
    try:
        import streamlit as st

        value = st.secrets.get(name)  # type: ignore[attr-defined]
        if value:
            return str(value).strip()
    except Exception:
        pass
    return default


MONGODB_URI = _str("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DB = _str("MONGODB_DB", "weatherpredict")

ARTIFACT_DIR = BASE_DIR / "ml_artifacts"
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"

ALLOWED_UPLOAD_EXTENSIONS = {".csv", ".json", ".xlsx"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

CACHE_SECONDS = _int("DASHBOARD_CACHE_SECONDS", 45)
ANALYTICS_CACHE_SECONDS = _int("ANALYTICS_CACHE_SECONDS", 300)
REALTIME_POLL_SECONDS = _int("REALTIME_POLL_SECONDS", 5)
MAINTENANCE_MESSAGE = os.getenv("MAINTENANCE_MESSAGE", "").strip()

ORGANIZATION = "EarthScape Climate Agency"

_LOG_CONFIGURED = False


def configure_logging() -> None:
    """Attach console and file handlers once."""
    global _LOG_CONFIGURED
    if _LOG_CONFIGURED:
        return
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("[%(asctime)s] %(levelname)s %(name)s %(message)s")
    root = logging.getLogger("weatherpredict")
    root.setLevel(logging.INFO)
    if not root.handlers:
        stream = logging.StreamHandler()
        stream.setFormatter(fmt)
        root.addHandler(stream)
        try:
            fileh = logging.FileHandler(LOG_DIR / "weatherpredict.log", encoding="utf-8")
            fileh.setFormatter(fmt)
            root.addHandler(fileh)
        except OSError:  # read-only deployment target
            pass
    root.propagate = False
    _LOG_CONFIGURED = True


configure_logging()
