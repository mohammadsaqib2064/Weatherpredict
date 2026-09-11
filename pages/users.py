"""User management (Administrator)."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from weatherpredict import auth, console
from weatherpredict.auth import ADMINISTRATOR, ANALYST, AuthError, PermissionDenied
from weatherpredict.batch.synthetic import REGIONS
from weatherpredict.ui import session, theme

user = session.guard("manage_users")

counts = auth.count_users()
theme.masthead(
    "User management",
    eyebrow="Administrator",
    lead="Issue accounts, change roles and suspend access. Passwords are stored as bcrypt hashes only.",
    meta=[("accounts", str(counts["total"])), ("active", str(counts["active"]))],
)

session.show_flash("users")

theme.stat_strip(
    [
        ("Total accounts", counts["total"], ""),
        ("Active", counts["active"], "can sign in"),
        ("Deactivated", counts["inactive"], "blocked at login"),
        ("Administrators", counts["administrators"], "full control"),
        ("Analysts", counts["analysts"], "investigation only"),
    ]
)

directory, create = st.columns([1.75, 1], gap="large")

with directory:
    theme.section("Directory", "inline role and access control")
    users = auth.list_users()
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Username": u.username,
                    "Role": u.role_label,
                    "Email": u.email or "—",
                    "Focus": u.region_focus.replace("_", " ") or "—",
                    "Active": "yes" if u.is_active else "no",
                    "Last login": u.last_login,
                }
                for u in users
            ]
        ),
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("#### Modify an account")
    target_name = st.selectbox(
        "Account", [u.username for u in users], key="user_target", label_visibility="collapsed"
    )
    target = next((u for u in users if u.username == target_name), None)
    if target:
        c1, c2, c3 = st.columns([1.2, 1, 1])
        with c1:
            new_role = st.selectbox(
                "Role",
                [ADMINISTRATOR, ANALYST],
                index=0 if target.role == ADMINISTRATOR else 1,
                format_func=lambda r: auth.ROLE_LABELS[r],
                key="user_role",
            )
            if st.button("Apply role", use_container_width=True):
                try:
                    auth.set_role(target.username, new_role, acting_user=user)
                    console.invalidate_cache()
                    session.flash("users", f"{target.username} is now {auth.ROLE_LABELS[new_role]}.")
                    st.rerun()
                except (AuthError, PermissionDenied) as exc:
                    st.error(str(exc))
        with c2:
            st.markdown("**Access**")
            label = "Deactivate" if target.is_active else "Activate"
            if st.button(label, use_container_width=True):
                try:
                    auth.set_active(target.username, not target.is_active, acting_user=user)
                    console.invalidate_cache()
                    session.flash("users", f"{target.username} {label.lower()}d.")
                    st.rerun()
                except (AuthError, PermissionDenied) as exc:
                    st.error(str(exc))
        with c3:
            st.markdown("**Password**")
            with st.popover("Reset", use_container_width=True):
                pwd = st.text_input("New password", type="password", key="user_pwd")
                if st.button("Set password"):
                    try:
                        session.act("manage_users")
                        auth.set_password(target.username, pwd)
                        session.flash("users", f"Password reset for {target.username}.")
                        st.rerun()
                    except (AuthError, PermissionDenied) as exc:
                        st.error(str(exc))
        new_focus = st.selectbox(
            "Region focus",
            ["", *REGIONS.keys()],
            index=(list(REGIONS.keys()).index(target.region_focus) + 1) if target.region_focus in REGIONS else 0,
            format_func=lambda r: r.replace("_", " ").title() if r else "—",
            key="user_focus",
        )
        if st.button("Apply region focus"):
            try:
                auth.set_region_focus(target.username, new_focus, acting_user=user)
                session.flash("users", f"Region focus for {target.username} updated.")
                st.rerun()
            except (AuthError, PermissionDenied) as exc:
                st.error(str(exc))

with create:
    theme.section("Issue an account")
    with st.form("create_user", clear_on_submit=True):
        username = st.text_input("Username")
        email = st.text_input("Email")
        password = st.text_input("Password", type="password", help="Minimum 8 characters.")
        role = st.selectbox(
            "Role", [ANALYST, ADMINISTRATOR], format_func=lambda r: auth.ROLE_LABELS[r]
        )
        region_focus = st.selectbox("Region focus", ["", *REGIONS.keys()], format_func=lambda r: r or "—")
        submitted = st.form_submit_button("Create account", type="primary", use_container_width=True)
    if submitted:
        try:
            auth.admin_create_user(
                user,
                username=username,
                password=password,
                role=role,
                email=email,
                region_focus=region_focus,
            )
            console.invalidate_cache()
            session.flash("users", f"Created {username} as {auth.ROLE_LABELS[role]}.")
            st.rerun()
        except (AuthError, PermissionDenied) as exc:
            st.error(str(exc))

    theme.section("Role capabilities")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Capability": action.replace("_", " ").title(),
                    "Administrator": "yes" if ADMINISTRATOR in roles else "no",
                    "Analyst": "yes" if ANALYST in roles else "no",
                }
                for action, roles in auth.PERMISSIONS.items()
            ]
        ),
        use_container_width=True,
        hide_index=True,
        height=420,
    )
