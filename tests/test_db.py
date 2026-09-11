"""MongoDB wiring: collection registry, indexes and the console read models."""
from __future__ import annotations

import pytest

from weatherpredict import console
from weatherpredict.db import (
    APP_COLLECTIONS,
    CLIMATE_COLLECTIONS,
    collection_counts,
    ensure_indexes,
    get_collection,
    get_db,
    ping,
)


def test_ping_reports_reachable():
    assert ping(use_cache=False) is True


def test_unknown_collection_is_rejected():
    with pytest.raises(ValueError, match="Unknown collection"):
        get_collection("definitely_not_a_collection")


def test_every_registered_collection_is_addressable():
    for name in CLIMATE_COLLECTIONS + APP_COLLECTIONS:
        assert get_collection(name).name == name


def test_anomaly_identity_index_is_unique():
    ensure_indexes()
    indexes = get_db()["anomalies"].index_information()
    assert "anomaly_identity_unique" in indexes
    identity = indexes["anomaly_identity_unique"]
    assert identity.get("unique") is True
    assert [k for k, _ in identity["key"]] == ["region", "metric", "observed_at"]


def test_ensure_indexes_is_idempotent():
    ensure_indexes()
    ensure_indexes()
    assert "user_username_unique" in get_db()["users"].index_information()


def test_username_uniqueness_is_enforced_by_the_database(admin_user):
    from pymongo.errors import DuplicateKeyError

    ensure_indexes()
    with pytest.raises(DuplicateKeyError):
        get_collection("users").insert_one({"username": "admin_test", "password_hash": "x"})


def test_collection_counts_cover_existing_collections(admin_user):
    counts = collection_counts()
    assert counts.get("users") == 1


def test_system_overview_shape(admin_user, climate_corpus):
    console.invalidate_cache()
    overview = console.system_overview(refresh=True)
    assert overview["mongo_ok"] is True
    assert overview["weather_records"] > 0
    assert overview["users"] == 1
    assert overview["administrators"] == 1
    assert overview["health"] in {"healthy", "attention", "degraded", "critical"}


def test_region_temp_summary_is_cached_and_shaped(climate_corpus):
    console.invalidate_cache()
    rows = console.region_temp_summary(refresh=True)
    assert rows
    row = rows[0]
    assert {"region", "avg_temp", "min_temp", "max_temp", "n"} == set(row)
    assert row["min_temp"] <= row["avg_temp"] <= row["max_temp"]
    # Second call is served from cache and must be identical.
    assert console.region_temp_summary() == rows


def test_daily_region_frame_is_time_ordered(climate_corpus):
    rows = console.daily_region_frame("pacific_nw", days=30)
    assert rows
    stamps = [r["observed_at"] for r in rows]
    assert stamps == sorted(stamps)
