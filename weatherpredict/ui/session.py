"""Streamlit session and page-level access control."""
from __future__ import annotations

from typing import Any

import streamlit as st

from weatherpredict import auth
from weatherpredict.auth import AuthError, PermissionDenied, User

SESSION_KEY = "wp_username"


def login(username: str, password: str) -> User:
    """Authenticate and start a session. Raises :class:`AuthError` on failure."""
    user = auth.authenticate(username, password)
    st.session_state[SESSION_KEY] = user.username
    return user


def logout() -> None:
    st.session_state.pop(SESSION_KEY, None)
    for key in [k for k in st.session_state if str(k).startswith("wp_cache_")]:
        st.session_state.pop(key, None)


def current_user() -> User | None:
    username = st.session_state.get(SESSION_KEY)
    if not username:
        return None
    user = auth.get_user(username)
    if user is None or not user.is_active:
        # Account deleted or deactivated mid-session — drop the session.
        st.session_state.pop(SESSION_KEY, None)
        return None
    return user


def require_login() -> User:
    """Stop the page unless a session is active. No data renders before this."""
    user = current_user()
    if user is None:
        st.error("Your session has ended. Sign in again to continue.")
        st.stop()
    return user


def guard(action: str) -> User:
    """Authorize ``action`` for the session user or halt rendering.

    Every page calls this before touching data — navigation is filtered by role
    as well, but the check that actually enforces the boundary is this one.
    """
    user = require_login()
    try:
        auth.require(user, action)
    except PermissionDenied as exc:
        st.error(f"Access denied — {exc}")
        st.caption(
            "This surface is restricted to Administrator accounts. "
            "Ask an Administrator if you need this capability."
        )
        st.stop()
    return user


def act(action: str) -> User:
    """Authorize a mutating action inside a page (button handlers, forms)."""
    user = require_login()
    auth.require(user, action)
    return user


def flash(key: str, message: str, kind: str = "success") -> None:
    st.session_state[f"wp_flash_{key}"] = (kind, message)


def show_flash(key: str) -> None:
    payload: tuple[str, str] | None = st.session_state.pop(f"wp_flash_{key}", None)
    if not payload:
        return
    kind, message = payload
    {"success": st.success, "error": st.error, "info": st.info, "warning": st.warning}.get(
        kind, st.info
    )(message)


def selectable_regions(user: User, catalog) -> list[str]:
    from weatherpredict.scoping import selectable_regions as _sel

    return _sel(user, catalog)


def run_action(action: str, label: str, fn, *args: Any, **kwargs: Any):
    """Run a permission-gated operator action with consistent feedback."""
    try:
        user = act(action)
    except PermissionDenied as exc:
        st.error(f"Access denied — {exc}")
        return None
    try:
        with st.spinner(f"{label}..."):
            return fn(*args, user=user, **kwargs)
    except (AuthError, PermissionDenied) as exc:
        st.error(str(exc))
    except Exception as exc:  # noqa: BLE001
        st.error(f"{label} failed: {exc}")
    return None
