"""Threshold alert rules and in-app notifications."""
from __future__ import annotations

import logging
from datetime import datetime, timezone as dt_timezone
from typing import Any

from bson import ObjectId

from weatherpredict.auth import ADMINISTRATOR, User, list_users, require
from weatherpredict.db import get_collection

logger = logging.getLogger("weatherpredict.notifications")

OPERATORS = {
    "gt": "Greater than",
    "gte": "Greater or equal",
    "lt": "Less than",
    "lte": "Less or equal",
    "abs_gt": "Absolute value greater than",
}
SEVERITIES = ("info", "low", "medium", "high")


def _now() -> datetime:
    return datetime.now(tz=dt_timezone.utc)


def _rules():
    return get_collection("alert_rules")


def _notes():
    return get_collection("notifications")


# --- alert rules -------------------------------------------------------------

def rule_matches(rule: dict[str, Any], value: float, region: str = "") -> bool:
    if not rule.get("active", True):
        return False
    rule_region = rule.get("region") or ""
    if rule_region and region and rule_region != region:
        return False
    op = rule.get("operator", "gt")
    threshold = float(rule.get("threshold", 0))
    if op == "gt":
        return value > threshold
    if op == "gte":
        return value >= threshold
    if op == "lt":
        return value < threshold
    if op == "lte":
        return value <= threshold
    if op == "abs_gt":
        return abs(value) > threshold
    return False


def list_rules(active_only: bool = False) -> list[dict[str, Any]]:
    query = {"active": True} if active_only else {}
    return list(_rules().find(query).sort([("active", -1), ("name", 1)]))


def create_rule(
    name: str,
    metric: str,
    threshold: float,
    operator: str = "gt",
    region: str = "",
    severity: str = "medium",
    active: bool = True,
    created_by: str | None = None,
    acting_user: User | None = None,
) -> dict[str, Any]:
    require(acting_user, "configure_alerts")
    name = (name or "").strip()
    metric = (metric or "").strip()
    if not name or not metric:
        raise ValueError("Rule name and metric are required.")
    if operator not in OPERATORS:
        raise ValueError(f"Unknown operator: {operator}")
    doc = {
        "name": name,
        "metric": metric,
        "operator": operator,
        "threshold": float(threshold),
        "region": (region or "").strip(),
        "severity": severity if severity in SEVERITIES else "medium",
        "active": bool(active),
        "created_by": created_by or (acting_user.username if acting_user else None),
        "created_at": _now(),
    }
    # Name is uniquely indexed: re-submitting an existing rule updates it.
    _rules().update_one({"name": name}, {"$set": doc}, upsert=True)
    logger.info("Alert rule saved name=%s metric=%s %s %s", name, metric, operator, threshold)
    return _rules().find_one({"name": name})


def set_rule_active(name: str, active: bool, acting_user: User | None = None) -> None:
    require(acting_user, "configure_alerts")
    _rules().update_one({"name": name}, {"$set": {"active": bool(active)}})


def delete_rule(name: str, acting_user: User | None = None) -> None:
    require(acting_user, "configure_alerts")
    _rules().delete_one({"name": name})


def seed_default_rules() -> int:
    """Baseline thresholds so a fresh install alerts on something sensible."""
    defaults = [
        {"name": "Extreme heat", "metric": "temp_c", "operator": "gt", "threshold": 35.0, "severity": "high"},
        {"name": "Extreme cold", "metric": "temp_c", "operator": "lt", "threshold": -15.0, "severity": "high"},
        {"name": "High CO2", "metric": "co2_ppm", "operator": "gt", "threshold": 450.0, "severity": "medium"},
        {"name": "Heavy precip", "metric": "precip_mm", "operator": "gt", "threshold": 50.0, "severity": "medium"},
    ]
    created = 0
    for rule in defaults:
        if _rules().find_one({"name": rule["name"]}):
            continue
        _rules().insert_one(
            {**rule, "region": "", "active": True, "created_by": None, "created_at": _now()}
        )
        created += 1
    return created


# --- notifications -----------------------------------------------------------

def create_notification(
    username: str,
    title: str,
    body: str,
    severity: str = "info",
    anomaly_ref: str = "",
) -> dict[str, Any]:
    doc = {
        "username": username,
        "title": title,
        "body": body,
        "severity": severity if severity in SEVERITIES else "info",
        "is_read": False,
        "anomaly_ref": anomaly_ref,
        "created_at": _now(),
    }
    doc["_id"] = _notes().insert_one(doc).inserted_id
    logger.info("Notification created id=%s user=%s", doc["_id"], username)
    return doc


def evaluate_value_against_rules(
    metric: str,
    value: float,
    region: str = "",
    context: str = "",
) -> list[dict[str, Any]]:
    """Create in-app notifications when a threshold rule is breached.

    Administrators receive every matching alert. Analysts receive it only when
    the event region (and the rule's region, if set) matches their focus.
    """
    created: list[dict[str, Any]] = []
    rules = list(_rules().find({"active": True, "metric": metric}))
    if not rules:
        return created
    users = [u for u in list_users() if u.is_active]
    if not users:
        return created

    for rule in rules:
        if not rule_matches(rule, value, region):
            continue
        rule_region = rule.get("region") or ""
        title = f"Alert: {rule['name']}"
        body = (
            f"Metric `{metric}` value {value} in region `{region or 'all'}` "
            f"breached rule {rule['operator']} {rule['threshold']}. {context}"
        ).strip()
        severity = rule.get("severity", "medium")
        for u in users:
            if u.is_analyst:
                focus = u.region_focus or ""
                if focus and region and focus != region:
                    continue
                if focus and rule_region and focus != rule_region:
                    continue
            created.append(create_notification(u.username, title, body, severity))
        logger.info("Alert rule matched: %s value=%s region=%s", rule["name"], value, region)
    return created


def notify_anomaly(anomaly: dict[str, Any]) -> list[dict[str, Any]]:
    metric = anomaly.get("metric", "unknown")
    value = float(anomaly.get("value", 0))
    region = anomaly.get("region", "")
    context = f"Anomaly severity={anomaly.get('severity')}; z={anomaly.get('z_score')}."
    return evaluate_value_against_rules(metric, value, region, context)


def inbox(username: str, limit: int = 100, unread_only: bool = False) -> list[dict[str, Any]]:
    query: dict[str, Any] = {"username": username}
    if unread_only:
        query["is_read"] = False
    return list(_notes().find(query).sort("created_at", -1).limit(limit))


def unread_count(username: str | None = None) -> int:
    query: dict[str, Any] = {"is_read": False}
    if username:
        query["username"] = username
    return _notes().count_documents(query)


def mark_read(notification_id: str | ObjectId, username: str | None = None) -> bool:
    if isinstance(notification_id, str):
        notification_id = ObjectId(notification_id)
    query: dict[str, Any] = {"_id": notification_id}
    if username:
        query["username"] = username
    return _notes().update_one(query, {"$set": {"is_read": True}}).modified_count > 0


def mark_all_read(username: str) -> int:
    return _notes().update_many({"username": username, "is_read": False}, {"$set": {"is_read": True}}).modified_count


def recent_alerts(limit: int = 8) -> list[dict[str, Any]]:
    """Cross-user feed for the Administrator console."""
    return list(_notes().find().sort("created_at", -1).limit(limit))
