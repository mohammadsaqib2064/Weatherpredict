"""Alert-rule configuration — Administrator only."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from weatherpredict import notifications
from weatherpredict.auth import PermissionDenied
from weatherpredict.batch.synthetic import REGIONS
from weatherpredict.ui import session, theme

user = session.guard("configure_alerts")

theme.masthead(
    "Alert rules",
    eyebrow="Administrator",
    lead=(
        "Thresholds evaluated on every ingestion row, every real-time tick and every "
        "newly detected anomaly. A breach raises an in-app notification for all active accounts."
    ),
)

session.show_flash("alerts")

rules = notifications.list_rules()
active = [r for r in rules if r.get("active")]
theme.stat_strip(
    [
        ("Rules configured", len(rules), ""),
        ("Active", len(active), "evaluated on write"),
        ("Metrics covered", len({r["metric"] for r in rules}), ""),
        ("!Unread notifications", notifications.unread_count(), "all accounts"),
    ]
)

listing, editor = st.columns([1.6, 1], gap="large")

with listing:
    theme.section("Configured rules")
    if rules:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Rule": r["name"],
                        "Metric": r["metric"],
                        "Condition": f"{r['operator']} {r['threshold']}",
                        "Region": r.get("region") or "all",
                        "Severity": r.get("severity", "medium"),
                        "Active": "yes" if r.get("active") else "no",
                        "Created by": r.get("created_by") or "—",
                    }
                    for r in rules
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )
        st.markdown("#### Toggle or remove")
        target = st.selectbox("Rule", [r["name"] for r in rules], label_visibility="collapsed")
        selected = next(r for r in rules if r["name"] == target)
        c1, c2 = st.columns(2)
        with c1:
            label = "Deactivate" if selected.get("active") else "Activate"
            if st.button(label, use_container_width=True):
                try:
                    notifications.set_rule_active(target, not selected.get("active"), acting_user=user)
                    session.flash("alerts", f"Rule '{target}' {label.lower()}d.")
                    st.rerun()
                except PermissionDenied as exc:
                    st.error(str(exc))
        with c2:
            if st.button("Delete rule", use_container_width=True):
                try:
                    notifications.delete_rule(target, acting_user=user)
                    session.flash("alerts", f"Rule '{target}' deleted.")
                    st.rerun()
                except PermissionDenied as exc:
                    st.error(str(exc))
    else:
        st.caption("No alert rules configured.")

with editor:
    theme.section("Define a rule", "an existing name updates that rule")
    with st.form("create_rule", clear_on_submit=True):
        name = st.text_input("Rule name")
        metric = st.selectbox(
            "Metric", ["temp_c", "precip_mm", "humidity_pct", "co2_ppm", "soil_moisture", "uv_index"]
        )
        operator = st.selectbox(
            "Operator", list(notifications.OPERATORS), format_func=lambda o: notifications.OPERATORS[o]
        )
        threshold = st.number_input("Threshold", value=35.0, step=0.5)
        region = st.selectbox("Region", ["", *REGIONS.keys()], format_func=lambda r: r or "All regions")
        severity = st.selectbox("Severity", ["low", "medium", "high"], index=1)
        submitted = st.form_submit_button("Save rule", type="primary", use_container_width=True)
    if submitted:
        try:
            notifications.create_rule(
                name=name,
                metric=metric,
                threshold=threshold,
                operator=operator,
                region=region,
                severity=severity,
                acting_user=user,
            )
            session.flash("alerts", f"Rule '{name}' saved.")
            st.rerun()
        except (ValueError, PermissionDenied) as exc:
            st.error(str(exc))

    theme.section("Test a value")
    st.caption("Evaluates the value against active rules and raises real notifications if breached.")
    test_metric = st.selectbox("Metric to test", sorted({r["metric"] for r in rules}) or ["temp_c"])
    test_value = st.number_input("Value", value=40.0, step=0.5, key="test_value")
    test_region = st.selectbox(
        "Region context", ["", *REGIONS.keys()], format_func=lambda r: r or "All regions", key="test_region"
    )
    if st.button("Evaluate", use_container_width=True):
        created = notifications.evaluate_value_against_rules(
            test_metric, float(test_value), test_region, context="manual rule test"
        )
        if created:
            st.success(f"{len(created)} notification(s) raised across active accounts.")
        else:
            st.info("No active rule matched that value.")
