"""Support tickets and feedback, including per-role visibility."""
from __future__ import annotations

import pytest

from weatherpredict import support
from weatherpredict.auth import PermissionDenied


def test_ticket_requires_subject_and_body(analyst_user):
    with pytest.raises(ValueError):
        support.create_ticket("", "body", analyst_user.username)
    with pytest.raises(ValueError):
        support.create_ticket("subject", "   ", analyst_user.username)


def test_analyst_sees_only_own_tickets(admin_user, analyst_user):
    support.create_ticket("Analyst issue", "Chart will not load", analyst_user.username)
    support.create_ticket("Admin issue", "Pipeline retry", admin_user.username)

    analyst_view = support.list_tickets(analyst_user)
    assert [t["subject"] for t in analyst_view] == ["Analyst issue"]

    admin_view = support.list_tickets(admin_user)
    assert {t["subject"] for t in admin_view} == {"Analyst issue", "Admin issue"}


def test_administrator_responds_and_status_changes(admin_user, analyst_user):
    ticket = support.create_ticket("Needs help", "Forecast band looks wrong", analyst_user.username)
    updated = support.respond_to_ticket(
        ticket["_id"], admin_user, status="resolved", admin_notes="Band is +/-1.96 x test MAE."
    )
    assert updated["status"] == "resolved"
    assert updated["assignee"] == "admin_test"
    assert "1.96" in updated["admin_notes"]


def test_analyst_cannot_respond_to_tickets(admin_user, analyst_user):
    ticket = support.create_ticket("Needs help", "Something broke", analyst_user.username)
    with pytest.raises(PermissionDenied):
        support.respond_to_ticket(ticket["_id"], analyst_user, status="closed")
    assert support.list_tickets(admin_user)[0]["status"] == "open"


def test_open_ticket_count_excludes_closed(admin_user, analyst_user):
    t1 = support.create_ticket("One", "body", analyst_user.username)
    support.create_ticket("Two", "body", analyst_user.username)
    assert support.open_ticket_count() == 2
    support.respond_to_ticket(t1["_id"], admin_user, status="closed")
    assert support.open_ticket_count() == 1


def test_feedback_rating_bounds(analyst_user):
    with pytest.raises(ValueError):
        support.submit_feedback(analyst_user.username, 6, "too high")
    with pytest.raises(ValueError):
        support.submit_feedback(analyst_user.username, 3, "")
    entry = support.submit_feedback(analyst_user.username, 4, "Useful", "Trend prediction")
    assert entry["rating"] == 4


def test_only_administrators_read_all_feedback(admin_user, analyst_user):
    support.submit_feedback(analyst_user.username, 5, "Great")
    assert len(support.list_feedback(admin_user)) == 1
    with pytest.raises(PermissionDenied):
        support.list_feedback(analyst_user)
