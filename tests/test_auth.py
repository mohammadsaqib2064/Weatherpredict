"""Authentication and role-based access control."""
from __future__ import annotations

import base64
import hashlib

import pytest

from weatherpredict import auth
from weatherpredict.auth import ADMINISTRATOR, ANALYST, AuthError, PermissionDenied


def _django_pbkdf2(password: str, salt: str = "testsalt", iterations: int = 1000) -> str:
    derived = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), iterations)
    return f"pbkdf2_sha256${iterations}${salt}${base64.b64encode(derived).decode()}"


def test_password_is_hashed_not_stored_plaintext(admin_user):
    from weatherpredict.db import get_collection

    doc = get_collection("users").find_one({"username": "admin_test"})
    assert doc["password_hash"].startswith("$2b$")
    assert "AdminPass123!" not in doc["password_hash"]


def test_login_succeeds_for_both_roles(admin_user, analyst_user):
    assert auth.authenticate("admin_test", "AdminPass123!").role == ADMINISTRATOR
    assert auth.authenticate("analyst_test", "AnalystPass123!").role == ANALYST


def test_login_fails_with_wrong_password(admin_user):
    with pytest.raises(AuthError):
        auth.authenticate("admin_test", "not-the-password")


def test_login_fails_for_unknown_user():
    with pytest.raises(AuthError):
        auth.authenticate("ghost", "whatever")


def test_deactivated_account_cannot_sign_in(admin_user, analyst_user):
    auth.set_active("analyst_test", False, acting_user=admin_user)
    with pytest.raises(AuthError, match="deactivated"):
        auth.authenticate("analyst_test", "AnalystPass123!")


def test_legacy_django_hash_verifies_and_upgrades_to_bcrypt():
    """Accounts migrated from SQLite keep working and are re-hashed on login."""
    from weatherpredict.db import get_collection

    legacy = _django_pbkdf2("LegacyPass123!")
    auth.create_user("legacy_user", password=None, password_hash=legacy, role=ANALYST)
    assert auth.verify_password("LegacyPass123!", legacy)
    assert auth.needs_rehash(legacy)

    auth.authenticate("legacy_user", "LegacyPass123!")
    stored = get_collection("users").find_one({"username": "legacy_user"})["password_hash"]
    assert stored.startswith("$2b$")
    assert auth.authenticate("legacy_user", "LegacyPass123!").username == "legacy_user"


def test_duplicate_username_rejected(admin_user):
    with pytest.raises(AuthError, match="already exists"):
        auth.create_user("admin_test", "AnotherPass123!", role=ANALYST)


def test_weak_password_rejected():
    with pytest.raises(AuthError, match="at least 8"):
        auth.create_user("shorty", "abc", role=ANALYST)


@pytest.mark.parametrize(
    "action",
    ["manage_users", "generate_data", "run_batch", "train_ml", "configure_alerts", "view_admin_console"],
)
def test_analyst_denied_admin_actions(analyst_user, action):
    assert not analyst_user.can(action)
    with pytest.raises(PermissionDenied):
        auth.require(analyst_user, action)


@pytest.mark.parametrize(
    "action",
    ["manage_users", "generate_data", "run_batch", "train_ml", "configure_alerts", "view_admin_console"],
)
def test_administrator_allowed_admin_actions(admin_user, action):
    assert admin_user.can(action)
    assert auth.require(admin_user, action) is admin_user


@pytest.mark.parametrize("action", ["view_analytics", "view_realtime", "ingest_data", "submit_ticket"])
def test_shared_actions_allowed_for_both(admin_user, analyst_user, action):
    assert admin_user.can(action)
    assert analyst_user.can(action)


def test_analyst_cannot_change_roles(admin_user, analyst_user):
    with pytest.raises(PermissionDenied):
        auth.set_role("admin_test", ANALYST, acting_user=analyst_user)
    assert auth.get_user("admin_test").role == ADMINISTRATOR


def test_analyst_cannot_create_users(analyst_user):
    with pytest.raises(PermissionDenied):
        auth.admin_create_user(analyst_user, username="sneaky", password="Password123!", role=ADMINISTRATOR)
    assert auth.get_user("sneaky") is None


def test_admin_cannot_demote_or_deactivate_self(admin_user):
    with pytest.raises(AuthError):
        auth.set_role("admin_test", ANALYST, acting_user=admin_user)
    with pytest.raises(AuthError):
        auth.set_active("admin_test", False, acting_user=admin_user)


def test_admin_can_change_analyst_role_and_access(admin_user, analyst_user):
    auth.set_role("analyst_test", ADMINISTRATOR, acting_user=admin_user)
    assert auth.get_user("analyst_test").role == ADMINISTRATOR
    auth.set_active("analyst_test", False, acting_user=admin_user)
    assert auth.get_user("analyst_test").is_active is False


def test_unknown_permission_raises(admin_user):
    with pytest.raises(KeyError):
        auth.can(admin_user, "not_a_real_action")


def test_anonymous_is_denied_everything():
    with pytest.raises(PermissionDenied):
        auth.require(None, "view_analytics")
