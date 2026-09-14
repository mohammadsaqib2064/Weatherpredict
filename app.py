"""WeatherPredict Streamlit entrypoint. Run with: streamlit run app.py"""
from __future__ import annotations

import streamlit as st

from weatherpredict import notifications, settings
from weatherpredict.auth import ADMINISTRATOR, AuthError
from weatherpredict.db import ensure_indexes, ping
from weatherpredict.ui import session, theme

st.set_page_config(
    page_title="WeatherPredict — EarthScape Climate Agency",
    page_icon=":material/globe_asia:",
    layout="wide",
    initial_sidebar_state="collapsed",
)
theme.inject()

if settings.MAINTENANCE_MESSAGE:
    st.warning(settings.MAINTENANCE_MESSAGE)


# --- login -------------------------------------------------------------------

def render_login() -> None:
    """Brand rail + sign-in form."""
    rail, form = st.columns([1.05, 1], gap="large")
    with rail:
        theme._html(
            """
            <div class="wp-auth-rail">
              <div>
                <p class="wp-eyebrow">EarthScape Climate Agency</p>
                <h1>Climate signal, not noise.</h1>
                <p>Satellite metadata, weather-station records and environmental
                   sensor streams — ingested, reconciled and scored for anomalies
                   across five monitored regions.</p>
              </div>
              <div class="wp-rail-foot">
                Batch + near-real-time pipelines · Regional trend models ·
                Seasonal anomaly baselines · Threshold alerting
              </div>
            </div>
            """
        )
    with form:
        theme._html('<p class="wp-eyebrow">Restricted system</p>')
        st.markdown("### Sign in")
        theme._html(
            '<p class="wp-note">Accounts are issued by an Administrator. '
            "Access is scoped to your assigned role.</p>"
        )
        with st.form("login", clear_on_submit=False):
            username = st.text_input("Username", autocomplete="username")
            password = st.text_input("Password", type="password", autocomplete="current-password")
            submitted = st.form_submit_button("Sign in", type="primary", use_container_width=True)
        if submitted:
            try:
                session.login(username, password)
                st.rerun()
            except AuthError as exc:
                st.error(str(exc))
            except Exception as exc:  # noqa: BLE001 — Mongo unreachable, etc.
                st.error(f"Sign-in unavailable: {exc}")

        _mongo_ok = ping()
        if not _mongo_ok:
            st.warning("MongoDB is unreachable — start it before signing in.")
        theme._html(
            '<div class="wp-cred"><strong>Demo accounts</strong><br>'
            "admin / AdminPass123! — Administrator<br>"
            "analyst / AnalystPass123! — Analyst</div>"
        )


user = session.current_user()
if user is None:
    # Must call st.navigation before stop — otherwise Streamlit lists every
    # file in pages/ as a public sidebar (what Cloud was showing on first load).
    st.navigation(
        [st.Page(render_login, title="Sign in", default=True)],
        position="hidden",
    ).run()
    st.stop()

try:
    ensure_indexes()
except Exception:  # noqa: BLE001 — console health will surface Mongo issues
    pass


# --- navigation --------------------------------------------------------------

def page(path: str, title: str, icon: str, **kwargs) -> st.Page:
    return st.Page(f"pages/{path}", title=title, icon=f":material/{icon}:", **kwargs)


shared_investigation = [
    page("explore.py", "Data exploration", "explore"),
    page("trends.py", "Trend prediction", "trending_up"),
    page("anomalies.py", "Anomaly investigation", "warning"),
    page("correlations.py", "Correlation analysis", "grid_on"),
    page("live.py", "Live sensor feed", "sensors"),
]
shared_operations = [
    page("ingest.py", "Data ingestion", "upload_file"),
    page("notifications.py", "Notifications", "notifications"),
    page("support.py", "Support & feedback", "support_agent"),
]

if user.role == ADMINISTRATOR:
    nav = {
        "Operations": [
            page("console.py", "Administrator console", "monitoring", default=True),
            page("data_ops.py", "Data & pipeline management", "database"),
            page("users.py", "User management", "manage_accounts"),
            page("alerts.py", "Alert rules", "notification_important"),
        ],
        "Investigation": shared_investigation,
        "Intake & support": shared_operations,
    }
else:
    nav = {
        "Workspace": [page("workspace.py", "Analyst workspace", "workspaces", default=True)],
        "Investigation": shared_investigation,
        "Intake & support": shared_operations,
    }

with st.sidebar:
    theme._html(
        """
        <div style="padding:0.2rem 0 0.9rem;border-bottom:1px solid rgba(126,182,212,0.28);margin-bottom:0.8rem;">
          <div style="font-family:'Source Sans',sans-serif;font-size:1.15rem;font-weight:700;color:#fff;">
            WeatherPredict</div>
          <div style="font-size:0.72rem;letter-spacing:0.06em;text-transform:uppercase;color:#A8D0E6;">
            EarthScape Climate Agency</div>
        </div>
        """
    )

navigation = st.navigation(nav, position="sidebar")

try:
    unread = notifications.unread_count(user.username)
except Exception:  # noqa: BLE001
    unread = 0

with st.sidebar:
    theme._html(
        f"""
        <div style="border-top:1px solid rgba(126,182,212,0.28);margin-top:0.9rem;padding-top:0.8rem;">
          <div style="font-size:0.9rem;font-weight:600;color:#fff;">{theme._esc(user.username)}</div>
          <div style="font-size:0.7rem;letter-spacing:0.06em;text-transform:uppercase;color:#A8D0E6;">
            {theme._esc(user.role_label)}{' · ' + theme._esc(user.region_focus.replace('_', ' ')) if user.region_focus else ''}</div>
          <div style="font-size:0.78rem;color:#A8D0E6;margin-top:0.35rem;">
            {'Unread alerts: ' + str(unread) if unread else 'No unread alerts'}</div>
        </div>
        """
    )
    if st.button("Sign out", use_container_width=True):
        session.logout()
        st.rerun()

navigation.run()
