"""Pytest fixtures. Uses ``weatherpredict_test`` so demo data is never dropped."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("MONGODB_DB", "weatherpredict_test")

from weatherpredict import auth, cache, db, ml, settings  # noqa: E402
from weatherpredict.batch.synthetic import generate_synthetic_dataset  # noqa: E402

TEST_DB = "weatherpredict_test"


def pytest_configure() -> None:
    assert settings.MONGODB_DB == TEST_DB, (
        f"Refusing to run: tests target '{settings.MONGODB_DB}', expected '{TEST_DB}'."
    )


@pytest.fixture(scope="session", autouse=True)
def mongo_session():
    """Drop and recreate the test database around the whole session."""
    try:
        client = db.get_client()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"MongoDB unavailable: {exc}")
    client.drop_database(TEST_DB)
    db.ensure_indexes()
    yield client
    client.drop_database(TEST_DB)


@pytest.fixture(autouse=True)
def clean_operational(mongo_session):
    """Reset the operational collections between tests; climate data persists."""
    cache.clear()
    database = db.get_db()
    for name in ("users", "notifications", "alert_rules", "support_tickets", "feedback", "ingestion_jobs"):
        database[name].delete_many({})
    yield


@pytest.fixture
def admin_user():
    return auth.create_user(
        username="admin_test",
        password="AdminPass123!",
        role=auth.ADMINISTRATOR,
        email="admin@test.local",
    )


@pytest.fixture
def analyst_user():
    return auth.create_user(
        username="analyst_test",
        password="AnalystPass123!",
        role=auth.ANALYST,
        email="analyst@test.local",
        region_focus="pacific_nw",
    )


@pytest.fixture(scope="session")
def climate_corpus(mongo_session, tmp_path_factory):
    """Two years of synthetic climate data in the test database."""
    data_dir = tmp_path_factory.mktemp("data")
    original = settings.DATA_DIR
    settings.DATA_DIR = data_dir
    seed_admin = auth.get_user("corpus_admin") or auth.create_user(
        "corpus_admin", "CorpusPass123!", role=auth.ADMINISTRATOR
    )
    run = generate_synthetic_dataset(years=2, seed=7, user=seed_admin, clear_existing=True)
    settings.DATA_DIR = original
    db.get_collection("users").delete_one({"username": "corpus_admin"})
    return run


@pytest.fixture(scope="session")
def trained_models(climate_corpus, tmp_path_factory):
    """Train once per session into a temporary artifact directory."""
    artifact_dir = tmp_path_factory.mktemp("ml_artifacts")
    original = ml.ARTIFACT_DIR
    ml.ARTIFACT_DIR = artifact_dir
    ml.train_trend_models()
    ml.train_anomaly_model()
    yield artifact_dir
    ml.ARTIFACT_DIR = original
