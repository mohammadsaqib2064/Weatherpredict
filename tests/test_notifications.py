"""Threshold alert rules and the in-app notification inbox."""
from __future__ import annotations

import pytest

from weatherpredict import notifications as notif
from weatherpredict.auth import PermissionDenied


@pytest.fixture
def hot_rule(admin_user):
    return notif.create_rule(
        name="Hot", metric="temp_c", threshold=30, operator="gt", severity="high", acting_user=admin_user
    )


def test_analyst_cannot_configure_rules(analyst_user):
    with pytest.raises(PermissionDenied):
        notif.create_rule(name="Sneaky", metric="temp_c", threshold=1, acting_user=analyst_user)
    assert notif.list_rules() == []


def test_threshold_breach_creates_notification(admin_user, analyst_user, hot_rule):
    created = notif.evaluate_value_against_rules("temp_c", 36.0, "pacific_nw")
    assert len(created) == 2  # one per active account
    assert all(n["title"] == "Alert: Hot" for n in created)
    assert notif.unread_count("analyst_test") == 1


def test_value_below_threshold_creates_nothing(admin_user, hot_rule):
    assert notif.evaluate_value_against_rules("temp_c", 12.0, "pacific_nw") == []
    assert notif.unread_count() == 0


def test_region_scoped_rule_only_fires_in_its_region(admin_user):
    notif.create_rule(
        name="SW heat", metric="temp_c", threshold=30, region="southwest", acting_user=admin_user
    )
    assert notif.evaluate_value_against_rules("temp_c", 40.0, "pacific_nw") == []
    assert notif.evaluate_value_against_rules("temp_c", 40.0, "southwest") != []


@pytest.mark.parametrize(
    "operator,threshold,value,expected",
    [
        ("gt", 30, 31, True),
        ("gt", 30, 30, False),
        ("gte", 30, 30, True),
        ("lt", -15, -16, True),
        ("lte", -15, -15, True),
        ("abs_gt", 3, -4, True),
        ("abs_gt", 3, -2, False),
    ],
)
def test_rule_operators(operator, threshold, value, expected):
    rule = {"active": True, "operator": operator, "threshold": threshold, "region": ""}
    assert notif.rule_matches(rule, value) is expected


def test_inactive_rule_never_matches(admin_user, hot_rule):
    notif.set_rule_active("Hot", False, acting_user=admin_user)
    assert notif.evaluate_value_against_rules("temp_c", 99.0, "pacific_nw") == []


def test_mark_read_and_unread_counts(admin_user, hot_rule):
    notif.evaluate_value_against_rules("temp_c", 40.0, "southeast")
    assert notif.unread_count("admin_test") == 1
    item = notif.inbox("admin_test")[0]
    assert notif.mark_read(item["_id"], username="admin_test") is True
    assert notif.unread_count("admin_test") == 0


def test_mark_all_read(admin_user, hot_rule):
    for _ in range(3):
        notif.evaluate_value_against_rules("temp_c", 40.0, "southeast")
    assert notif.unread_count("admin_test") == 3
    assert notif.mark_all_read("admin_test") == 3
    assert notif.inbox("admin_test", unread_only=True) == []


def test_anomaly_notification_carries_context(admin_user, hot_rule):
    created = notif.notify_anomaly(
        {"metric": "temp_c", "value": 44.2, "region": "southwest", "severity": "high", "z_score": 4.8}
    )
    assert created
    assert "severity=high" in created[0]["body"]


def test_seed_default_rules_is_idempotent():
    assert notif.seed_default_rules() == 4
    assert notif.seed_default_rules() == 0
    assert len(notif.list_rules()) == 4
