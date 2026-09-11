"""Role-based data scoping — Analysts only read their assigned region."""
from __future__ import annotations

import pytest

from weatherpredict.auth import PermissionDenied
from weatherpredict.scoping import constrain_region, mongo_region_filter, selectable_regions


def test_administrator_is_unrestricted(admin_user):
    assert constrain_region(admin_user, "southwest") == "southwest"
    assert constrain_region(admin_user, None) is None
    assert mongo_region_filter(admin_user, None) == {}
    assert selectable_regions(admin_user, ["a", "b"]) == ["a", "b"]


def test_analyst_is_limited_to_region_focus(analyst_user):
    assert constrain_region(analyst_user, None) == "pacific_nw"
    assert constrain_region(analyst_user, "pacific_nw") == "pacific_nw"
    with pytest.raises(PermissionDenied):
        constrain_region(analyst_user, "southwest")
    assert mongo_region_filter(analyst_user, None) == {"region": "pacific_nw"}
    assert selectable_regions(analyst_user, ["pacific_nw", "southwest"]) == ["pacific_nw"]


def test_analyst_without_focus_sees_nothing(admin_user):
    from weatherpredict import auth

    blank = auth.create_user("nofocus", "AnalystPass123!", role=auth.ANALYST, region_focus="")
    with pytest.raises(PermissionDenied, match="No region"):
        constrain_region(blank, None)


def test_stored_anomalies_respect_scope(admin_user, analyst_user, climate_corpus):
    from weatherpredict import ml
    from weatherpredict.db import get_collection

    coll = get_collection("anomalies")
    coll.delete_many({"metric": "temp_c", "observed_at": {"$in": ["2020-01-01", "2020-01-02"]}})
    coll.insert_many(
        [
            {"region": "pacific_nw", "metric": "temp_c", "observed_at": "2020-01-01", "severity": "high", "z_score": 4},
            {"region": "southwest", "metric": "temp_c", "observed_at": "2020-01-02", "severity": "high", "z_score": 4},
        ]
    )
    all_rows = ml.stored_anomalies(user=admin_user)
    scoped = ml.stored_anomalies(user=analyst_user)
    assert {r["region"] for r in all_rows} >= {"pacific_nw", "southwest"}
    assert {r["region"] for r in scoped} == {"pacific_nw"}


def test_alert_does_not_notify_analyst_in_other_region(admin_user, analyst_user):
    from weatherpredict import notifications as notif

    notif.create_rule(
        name="Hot", metric="temp_c", threshold=30, operator="gt", severity="high", acting_user=admin_user
    )
    created = notif.evaluate_value_against_rules("temp_c", 40.0, "southwest")
    users = {n["username"] for n in created}
    assert "admin_test" in users
    assert "analyst_test" not in users
