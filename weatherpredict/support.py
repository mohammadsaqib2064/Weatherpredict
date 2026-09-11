"""Support tickets and product feedback."""
from __future__ import annotations

import logging
from datetime import datetime, timezone as dt_timezone
from typing import Any

from bson import ObjectId

from weatherpredict.auth import User, require
from weatherpredict.db import get_collection

logger = logging.getLogger("weatherpredict.support")

STATUSES = {
    "open": "Open",
    "in_progress": "In progress",
    "resolved": "Resolved",
    "closed": "Closed",
}
PRIORITIES = {"low": "Low", "medium": "Medium", "high": "High"}
OPEN_STATUSES = ("open", "in_progress")


def _now() -> datetime:
    return datetime.now(tz=dt_timezone.utc)


def _tickets():
    return get_collection("support_tickets")


def _feedback():
    return get_collection("feedback")


def create_ticket(
    subject: str,
    body: str,
    created_by: str,
    priority: str = "medium",
) -> dict[str, Any]:
    subject = (subject or "").strip()
    body = (body or "").strip()
    if not subject or not body:
        raise ValueError("Subject and description are both required.")
    doc = {
        "subject": subject,
        "body": body,
        "status": "open",
        "priority": priority if priority in PRIORITIES else "medium",
        "created_by": created_by,
        "assignee": None,
        "admin_notes": "",
        "created_at": _now(),
        "updated_at": _now(),
    }
    doc["_id"] = _tickets().insert_one(doc).inserted_id
    logger.info("Support ticket created id=%s by=%s", doc["_id"], created_by)
    return doc


def list_tickets(user: User, limit: int = 100) -> list[dict[str, Any]]:
    """Administrators see the whole queue; Analysts only their own tickets."""
    query = {} if user.is_administrator else {"created_by": user.username}
    return list(_tickets().find(query).sort("created_at", -1).limit(limit))


def respond_to_ticket(
    ticket_id: str | ObjectId,
    acting_user: User,
    status: str | None = None,
    admin_notes: str | None = None,
) -> dict[str, Any] | None:
    require(acting_user, "manage_tickets")
    if isinstance(ticket_id, str):
        ticket_id = ObjectId(ticket_id)
    updates: dict[str, Any] = {"updated_at": _now(), "assignee": acting_user.username}
    if status:
        if status not in STATUSES:
            raise ValueError(f"Unknown status: {status}")
        updates["status"] = status
    if admin_notes is not None:
        updates["admin_notes"] = admin_notes
    _tickets().update_one({"_id": ticket_id}, {"$set": updates})
    return _tickets().find_one({"_id": ticket_id})


def open_ticket_count() -> int:
    return _tickets().count_documents({"status": {"$in": list(OPEN_STATUSES)}})


def submit_feedback(username: str, rating: int, message: str, page_context: str = "") -> dict[str, Any]:
    rating = int(rating)
    if not 1 <= rating <= 5:
        raise ValueError("Rating must be between 1 and 5.")
    message = (message or "").strip()
    if not message:
        raise ValueError("Feedback message is required.")
    doc = {
        "username": username,
        "rating": rating,
        "message": message,
        "page_context": page_context,
        "created_at": _now(),
    }
    doc["_id"] = _feedback().insert_one(doc).inserted_id
    return doc


def list_feedback(acting_user: User, limit: int = 50) -> list[dict[str, Any]]:
    require(acting_user, "view_all_feedback")
    return list(_feedback().find().sort("created_at", -1).limit(limit))
