"""Support tickets and product feedback."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from weatherpredict import support
from weatherpredict.auth import PermissionDenied
from weatherpredict.ui import session, theme

user = session.guard("submit_ticket")

is_admin = user.can("manage_tickets")

theme.masthead(
    "Support & feedback",
    eyebrow="Service desk" if is_admin else "Get help",
    lead=(
        "Work the incoming queue and record responses."
        if is_admin
        else "Raise an issue with the platform team and track its progress."
    ),
    meta=[("visibility", "all tickets" if is_admin else "your tickets")],
)

session.show_flash("support")

tickets = support.list_tickets(user)
open_count = sum(1 for t in tickets if t["status"] in support.OPEN_STATUSES)

theme.stat_strip(
    [
        ("Tickets", len(tickets), "all tickets" if is_admin else "raised by you"),
        ("!Open", open_count, "awaiting response"),
        ("Resolved", sum(1 for t in tickets if t["status"] == "resolved"), ""),
        ("High priority", sum(1 for t in tickets if t.get("priority") == "high"), ""),
    ]
)

queue, submit = st.columns([1.6, 1], gap="large")

with queue:
    theme.section("Ticket queue" if is_admin else "Your tickets")
    if tickets:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Subject": t["subject"],
                        "Status": support.STATUSES.get(t["status"], t["status"]),
                        "Priority": t.get("priority", "medium"),
                        "Raised by": t.get("created_by", "—"),
                        "Assignee": t.get("assignee") or "—",
                        "Created": t.get("created_at"),
                        "Response": (t.get("admin_notes") or "")[:120],
                    }
                    for t in tickets
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.caption("No tickets yet.")

    if is_admin and tickets:
        theme.section("Respond", "Administrator action")
        labels = {str(t["_id"]): f"{t['subject']} ({t['status']})" for t in tickets}
        selected_id = st.selectbox("Ticket", list(labels), format_func=lambda k: labels[k])
        selected = next(t for t in tickets if str(t["_id"]) == selected_id)
        st.markdown(f"**Reported:** {selected['body']}")
        with st.form("respond"):
            status = st.selectbox(
                "Status",
                list(support.STATUSES),
                index=list(support.STATUSES).index(selected["status"]),
                format_func=lambda s: support.STATUSES[s],
            )
            notes = st.text_area("Response to the reporter", value=selected.get("admin_notes", ""))
            if st.form_submit_button("Save response", type="primary"):
                try:
                    support.respond_to_ticket(selected_id, user, status=status, admin_notes=notes)
                    session.flash("support", "Response saved.")
                    st.rerun()
                except PermissionDenied as exc:
                    st.error(str(exc))
    elif tickets:
        theme.section("Responses")
        answered = [t for t in tickets if t.get("admin_notes")]
        if answered:
            for t in answered:
                st.markdown(f"**{t['subject']}** — {support.STATUSES.get(t['status'], t['status'])}")
                st.caption(t["admin_notes"])
        else:
            st.caption("No responses yet.")

with submit:
    theme.section("Raise a ticket")
    with st.form("new_ticket", clear_on_submit=True):
        subject = st.text_input("Subject")
        body = st.text_area("What happened?", height=140)
        priority = st.selectbox(
            "Priority", list(support.PRIORITIES), index=1, format_func=lambda p: support.PRIORITIES[p]
        )
        if st.form_submit_button("Submit ticket", type="primary", use_container_width=True):
            try:
                support.create_ticket(subject, body, user.username, priority)
                session.flash("support", "Ticket submitted.")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))

    theme.section("Product feedback")
    with st.form("feedback", clear_on_submit=True):
        rating = st.slider("Rating", 1, 5, 4)
        message = st.text_area("What would you change?", height=100)
        page_context = st.text_input("Which screen?", placeholder="e.g. Trend prediction")
        if st.form_submit_button("Send feedback", use_container_width=True):
            try:
                support.submit_feedback(user.username, rating, message, page_context)
                session.flash("support", "Thank you — feedback recorded.")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))

    if user.can("view_all_feedback"):
        theme.section("Recent feedback", "Administrator view")
        entries = support.list_feedback(user, limit=25)
        if entries:
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Rating": f["rating"],
                            "From": f.get("username", "—"),
                            "Screen": f.get("page_context") or "—",
                            "Message": f["message"],
                        }
                        for f in entries
                    ]
                ),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.caption("No feedback submitted yet.")
