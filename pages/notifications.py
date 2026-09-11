"""Notification inbox — threshold and anomaly alerts for the signed-in account."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from weatherpredict import notifications as notif
from weatherpredict.ui import session, theme

user = session.guard("view_notifications")

theme.masthead(
    "Notifications",
    eyebrow="Alerts",
    lead="In-app alerts raised when an ingested value, a live tick or a new anomaly breaches a threshold rule.",
    meta=[("account", user.username)],
)

session.show_flash("notifications")

unread = notif.unread_count(user.username)
items = notif.inbox(user.username, limit=200)

theme.stat_strip(
    [
        ("!Unread", unread, "needs review"),
        ("Total", len(items), "last 200"),
        ("High severity", sum(1 for n in items if n.get("severity") == "high"), ""),
        ("Medium", sum(1 for n in items if n.get("severity") == "medium"), ""),
    ]
)

action_col, filter_col = st.columns([1, 3])
with action_col:
    if st.button("Mark all read", disabled=unread == 0, use_container_width=True):
        count = notif.mark_all_read(user.username)
        session.flash("notifications", f"{count} notification(s) marked as read.")
        st.rerun()
with filter_col:
    only_unread = st.toggle("Show unread only", value=False)

visible = [n for n in items if not only_unread or not n.get("is_read")]

if not visible:
    st.info("Nothing to review. Alerts appear here when a rule threshold is breached.")
    st.stop()

theme.section("Inbox", f"{len(visible)} shown")
st.dataframe(
    pd.DataFrame(
        [
            {
                "Read": "" if n.get("is_read") else "unread",
                "Severity": n.get("severity", "info"),
                "Alert": n.get("title", ""),
                "Detail": n.get("body", ""),
                "Received": n.get("created_at"),
            }
            for n in visible
        ]
    ),
    use_container_width=True,
    hide_index=True,
    height=420,
)

theme.section("Mark an item read")
pending = [n for n in items if not n.get("is_read")]
if pending:
    labels = {
        str(n["_id"]): f"{n.get('title', '')} — {n.get('created_at')}" for n in pending
    }
    choice = st.selectbox("Notification", list(labels), format_func=lambda k: labels[k])
    if st.button("Mark read"):
        notif.mark_read(choice, username=user.username)
        session.flash("notifications", "Notification marked as read.")
        st.rerun()
else:
    st.caption("No unread notifications.")
