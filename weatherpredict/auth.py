"""Authentication and role-based access control."""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone as dt_timezone
from typing import Any, Iterable

import bcrypt
from pymongo import ASCENDING

from weatherpredict import settings
from weatherpredict.db import get_collection

logger = logging.getLogger("weatherpredict.auth")

ADMINISTRATOR = "ADMINISTRATOR"
ANALYST = "ANALYST"
ROLES = (ADMINISTRATOR, ANALYST)
ROLE_LABELS = {ADMINISTRATOR: "Administrator", ANALYST: "Analyst"}

MAX_PASSWORD_BYTES = 72  # bcrypt only hashes the first 72 bytes
MIN_PASSWORD_LENGTH = 8

USERNAME_RE = re.compile(r"^[A-Za-z0-9_.@+-]{3,150}$")


class AuthError(Exception):
    """Login or account-state failure."""


class PermissionDenied(Exception):
    """The authenticated role may not perform this action."""


# --- permission matrix -------------------------------------------------------
# Gating is data, not markup: pages and mutating actions both consult this.
PERMISSIONS: dict[str, tuple[str, ...]] = {
    # Administrator-only
    "manage_users": (ADMINISTRATOR,),
    "generate_data": (ADMINISTRATOR,),
    "run_batch": (ADMINISTRATOR,),
    "train_ml": (ADMINISTRATOR,),
    "configure_alerts": (ADMINISTRATOR,),
    "manage_tickets": (ADMINISTRATOR,),
    "view_admin_console": (ADMINISTRATOR,),
    "view_all_feedback": (ADMINISTRATOR,),
    "persist_anomalies": (ADMINISTRATOR,),
    # Shared
    "ingest_data": (ADMINISTRATOR, ANALYST),
    "view_analytics": (ADMINISTRATOR, ANALYST),
    "view_realtime": (ADMINISTRATOR, ANALYST),
    "emit_realtime_tick": (ADMINISTRATOR, ANALYST),
    "view_notifications": (ADMINISTRATOR, ANALYST),
    "submit_ticket": (ADMINISTRATOR, ANALYST),
    "view_workspace": (ADMINISTRATOR, ANALYST),
}


@dataclass(frozen=True)
class User:
    username: str
    role: str
    email: str = ""
    is_active: bool = True
    organization: str = settings.ORGANIZATION
    region_focus: str = ""
    created_at: datetime | None = None
    last_login: datetime | None = None
    extra: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def is_administrator(self) -> bool:
        return self.role == ADMINISTRATOR

    @property
    def is_analyst(self) -> bool:
        return self.role == ANALYST

    @property
    def role_label(self) -> str:
        return ROLE_LABELS.get(self.role, self.role.title())

    def can(self, action: str) -> bool:
        return can(self, action)

    def to_session(self) -> dict[str, Any]:
        return {
            "username": self.username,
            "role": self.role,
            "email": self.email,
            "region_focus": self.region_focus,
            "organization": self.organization,
        }


def _users():
    return get_collection("users")


def _now() -> datetime:
    return datetime.now(tz=dt_timezone.utc)


def _to_user(doc: dict[str, Any] | None) -> User | None:
    if not doc:
        return None
    return User(
        username=doc["username"],
        role=doc.get("role", ANALYST),
        email=doc.get("email", "") or "",
        is_active=bool(doc.get("is_active", True)),
        organization=doc.get("organization") or settings.ORGANIZATION,
        region_focus=doc.get("region_focus", "") or "",
        created_at=doc.get("created_at"),
        last_login=doc.get("last_login"),
    )


# --- password hashing --------------------------------------------------------

def hash_password(raw: str) -> str:
    if raw is None:
        raise AuthError("Password required.")
    encoded = raw.encode("utf-8")
    if len(encoded) > MAX_PASSWORD_BYTES:
        raise AuthError(f"Password must be at most {MAX_PASSWORD_BYTES} bytes.")
    return bcrypt.hashpw(encoded, bcrypt.gensalt(rounds=12)).decode("ascii")


def _verify_django_pbkdf2(raw: str, encoded: str) -> bool:
    """Verify a legacy ``pbkdf2_sha256$iterations$salt$hash`` hash."""
    try:
        algorithm, iterations, salt, digest = encoded.split("$", 3)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    try:
        derived = hashlib.pbkdf2_hmac("sha256", raw.encode("utf-8"), salt.encode("ascii"), int(iterations))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(base64.b64encode(derived).decode("ascii"), digest)


def verify_password(raw: str, encoded: str) -> bool:
    if not raw or not encoded:
        return False
    if encoded.startswith(("$2a$", "$2b$", "$2y$")):
        try:
            return bcrypt.checkpw(raw.encode("utf-8")[:MAX_PASSWORD_BYTES], encoded.encode("ascii"))
        except ValueError:
            return False
    if encoded.startswith("pbkdf2_sha256$"):
        return _verify_django_pbkdf2(raw, encoded)
    return False


def needs_rehash(encoded: str) -> bool:
    return not encoded.startswith(("$2a$", "$2b$", "$2y$"))


# --- account management ------------------------------------------------------

def get_user(username: str) -> User | None:
    if not username:
        return None
    return _to_user(_users().find_one({"username": username}))


def list_users(role: str | None = None) -> list[User]:
    query = {"role": role} if role else {}
    docs = _users().find(query).sort("username", ASCENDING)
    return [u for u in (_to_user(d) for d in docs) if u]


def count_users() -> dict[str, int]:
    coll = _users()
    return {
        "total": coll.count_documents({}),
        "active": coll.count_documents({"is_active": True}),
        "inactive": coll.count_documents({"is_active": False}),
        "administrators": coll.count_documents({"role": ADMINISTRATOR}),
        "analysts": coll.count_documents({"role": ANALYST}),
    }


def create_user(
    username: str,
    password: str,
    role: str = ANALYST,
    email: str = "",
    region_focus: str = "",
    is_active: bool = True,
    password_hash: str | None = None,
    created_at: datetime | None = None,
) -> User:
    username = (username or "").strip()
    if not USERNAME_RE.match(username):
        raise AuthError("Username must be 3-150 chars: letters, digits and . _ @ + - only.")
    if role not in ROLES:
        raise AuthError(f"Unknown role: {role}")
    if password_hash is None:
        if not password or len(password) < MIN_PASSWORD_LENGTH:
            raise AuthError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
        password_hash = hash_password(password)
    if _users().find_one({"username": username}):
        raise AuthError(f"Username '{username}' already exists.")
    doc = {
        "username": username,
        "password_hash": password_hash,
        "role": role,
        "email": (email or "").strip(),
        "is_active": bool(is_active),
        "organization": settings.ORGANIZATION,
        "region_focus": (region_focus or "").strip(),
        "created_at": created_at or _now(),
        "updated_at": _now(),
        "last_login": None,
    }
    _users().insert_one(doc)
    logger.info("User created username=%s role=%s", username, role)
    return _to_user(doc)


def set_password(username: str, password: str) -> None:
    if not password or len(password) < MIN_PASSWORD_LENGTH:
        raise AuthError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    result = _users().update_one(
        {"username": username},
        {"$set": {"password_hash": hash_password(password), "updated_at": _now()}},
    )
    if result.matched_count == 0:
        raise AuthError(f"No such user: {username}")


def set_role(username: str, role: str, acting_user: User | None = None) -> None:
    require(acting_user, "manage_users")
    if role not in ROLES:
        raise AuthError(f"Unknown role: {role}")
    if acting_user and acting_user.username == username and role != ADMINISTRATOR:
        raise AuthError("You cannot demote your own Administrator role.")
    result = _users().update_one({"username": username}, {"$set": {"role": role, "updated_at": _now()}})
    if result.matched_count == 0:
        raise AuthError(f"No such user: {username}")
    logger.info("Role changed username=%s role=%s", username, role)


def set_active(username: str, is_active: bool, acting_user: User | None = None) -> None:
    require(acting_user, "manage_users")
    if acting_user and acting_user.username == username and not is_active:
        raise AuthError("You cannot deactivate your own account.")
    result = _users().update_one(
        {"username": username}, {"$set": {"is_active": bool(is_active), "updated_at": _now()}}
    )
    if result.matched_count == 0:
        raise AuthError(f"No such user: {username}")
    logger.info("User %s %s", username, "activated" if is_active else "deactivated")


def set_region_focus(username: str, region_focus: str, acting_user: User | None = None) -> None:
    """Administrators may assign any account; Analysts may update only themselves."""
    if acting_user is None:
        raise PermissionDenied("Authentication required.")
    if acting_user.username != username:
        require(acting_user, "manage_users")
    result = _users().update_one(
        {"username": username},
        {"$set": {"region_focus": (region_focus or "").strip(), "updated_at": _now()}},
    )
    if result.matched_count == 0:
        raise AuthError(f"No such user: {username}")


def admin_create_user(acting_user: User | None, **kwargs) -> User:
    """User creation from the admin console — permission-checked."""
    require(acting_user, "manage_users")
    kwargs.pop("phone", None)
    return create_user(**kwargs)


# --- login -------------------------------------------------------------------

def authenticate(username: str, password: str) -> User:
    """Return the user on success; raise :class:`AuthError` otherwise."""
    username = (username or "").strip()
    doc = _users().find_one({"username": username})
    if not doc or not verify_password(password, doc.get("password_hash", "")):
        logger.warning("Failed login attempt username=%s", username or "<blank>")
        raise AuthError("Invalid username or password.")
    if not doc.get("is_active", True):
        raise AuthError("This account is deactivated. Contact an Administrator.")

    updates: dict[str, Any] = {"last_login": _now()}
    if needs_rehash(doc["password_hash"]):
        # Upgrade legacy pbkdf2 hash to bcrypt.
        updates["password_hash"] = hash_password(password)
        logger.info("Upgraded legacy password hash for %s", username)
    _users().update_one({"username": username}, {"$set": updates})
    doc.update(updates)
    logger.info("Login success username=%s role=%s", username, doc.get("role"))
    return _to_user(doc)


# --- authorization -----------------------------------------------------------

def can(user: User | None, action: str) -> bool:
    if user is None or not user.is_active:
        return False
    allowed = PERMISSIONS.get(action)
    if allowed is None:
        raise KeyError(f"Unknown permission: {action}")
    return user.role in allowed


def require(user: User | None, action: str) -> User:
    """Raise :class:`PermissionDenied` unless ``user`` may perform ``action``."""
    if user is None:
        raise PermissionDenied("Authentication required.")
    if not can(user, action):
        raise PermissionDenied(
            f"{user.role_label} accounts may not perform '{action}'. Administrators only."
        )
    return user


def permitted_actions(user: User | None) -> Iterable[str]:
    if user is None:
        return ()
    return tuple(action for action, roles in PERMISSIONS.items() if user.role in roles)
