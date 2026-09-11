"""EarthScape CSS and HTML helpers for Streamlit."""
from __future__ import annotations

import html
from typing import Any, Iterable, Sequence

import streamlit as st

from weatherpredict.ui import tokens as t

_CSS = f"""
<style>
:root {{
  --ocean-950: {t.OCEAN_950};
  --ocean-900: {t.OCEAN_900};
  --ocean-800: {t.OCEAN_800};
  --ocean-700: {t.OCEAN_700};
  --glacier-400: {t.GLACIER_400};
  --glacier-300: {t.GLACIER_300};
  --glacier-100: {t.GLACIER_100};
  --sand-50: {t.SAND_50};
  --sand-100: {t.SAND_100};
  --ink-900: {t.INK_900};
  --ink-700: {t.INK_700};
  --ink-500: {t.INK_500};
  --coral-600: {t.CORAL_600};
  --ok-600: {t.OK_600};
  --warn-600: {t.WARN_600};
  --surface: {t.SURFACE};
  --line: {t.LINE};
  --radius: 6px;
  /* Type scale */
  --fs-12: 0.75rem;  --fs-14: 0.875rem; --fs-16: 1rem;   --fs-20: 1.25rem;
  --fs-24: 1.5rem;   --fs-32: 2rem;     --fs-40: 2.5rem; --fs-56: 3.5rem;
  --font-display: {t.FONT_DISPLAY};
  --font-body: {t.FONT_BODY};
}}

html, body, .stApp {{ font-family: var(--font-body), "Source Sans", sans-serif; }}
.stApp {{ background: var(--sand-50); color: var(--ink-900); }}
/* Icon glyphs only */
[data-testid="stIconMaterial"],
.material-symbols-rounded,
.material-symbols-outlined {{
  font-family: "Material Symbols Rounded", "Material Symbols Outlined", sans-serif !important;
  font-weight: 400 !important;
  letter-spacing: normal !important;
  font-variation-settings: "FILL" 0, "wght" 400, "GRAD" 0, "opsz" 24 !important;
  font-style: normal !important;
  -webkit-font-smoothing: antialiased;
}}

/* Headings */
h1, h2, h3, h4, .wp-display {{
  font-family: var(--font-display) !important;
  letter-spacing: normal;
  color: var(--ocean-900);
  font-weight: 600;
}}
h1 {{ font-size: var(--fs-32) !important; line-height: 1.12; }}
h2 {{ font-size: var(--fs-24) !important; }}
h3 {{ font-size: var(--fs-20) !important; }}
h4 {{ font-size: var(--fs-16) !important; }}
p, li, label, .stMarkdown {{ font-size: var(--fs-16); }}

.block-container {{ padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1420px; }}

/* Sidebar */
section[data-testid="stSidebar"] {{
  background: linear-gradient(180deg, var(--ocean-950), var(--ocean-900) 55%, var(--ocean-800));
  border-right: 3px solid var(--glacier-400);
}}
section[data-testid="stSidebar"] {{ color: #EAF3F8; }}
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] span,
section[data-testid="stSidebar"] a,
section[data-testid="stSidebar"] li {{ color: #EAF3F8; }}
section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3 {{ color: #FFFFFF; }}
section[data-testid="stSidebar"] a {{
  color: rgba(234, 243, 248, 0.82) !important;
  border-radius: 4px;
}}
section[data-testid="stSidebar"] a:hover {{ background: rgba(126, 182, 212, 0.16); }}
section[data-testid="stSidebar"] [aria-current="page"] {{
  background: rgba(126, 182, 212, 0.22) !important;
  color: #FFFFFF !important;
}}

/* --- masthead --------------------------------------------------------- */
.wp-masthead {{
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 1.5rem;
  align-items: end;
  padding-bottom: 0.9rem;
  margin-bottom: 1.4rem;
  border-bottom: 1px solid var(--line);
}}
.wp-eyebrow {{
  font-size: var(--fs-12);
  letter-spacing: 0.09em;
  text-transform: uppercase;
  color: var(--ink-500);
  font-weight: 600;
  margin: 0 0 0.3rem;
}}
.wp-masthead h1 {{ margin: 0; font-size: var(--fs-40) !important; }}
.wp-lead {{ color: var(--ink-700); max-width: 68ch; margin: 0.4rem 0 0; font-size: var(--fs-16); }}
.wp-masthead-meta {{ text-align: right; font-size: var(--fs-14); color: var(--ink-500); line-height: 1.5; }}
.wp-masthead-meta strong {{ display: block; color: var(--ocean-900); font-family: var(--font-display); }}

/* --- stat strip ------------------------------------------------------- */
.wp-stats {{ display: grid; gap: 0.7rem; margin-bottom: 1.2rem; }}
.wp-stat {{
  background: var(--surface);
  border: 1px solid var(--line);
  border-left: 3px solid var(--ocean-800);
  padding: 0.85rem 1rem;
}}
.wp-stat.is-alert {{ border-left-color: var(--coral-600); }}
.wp-stat .wp-stat-label {{
  font-size: var(--fs-12);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--ink-500);
  margin-bottom: 0.3rem;
  font-weight: 600;
}}
.wp-stat .wp-stat-value {{
  font-family: var(--font-display);
  font-variant-numeric: tabular-nums;
  font-feature-settings: "tnum";
  font-size: var(--fs-32);
  line-height: 1;
  color: var(--ocean-900);
  font-weight: 600;
}}
.wp-stat.is-alert .wp-stat-value {{ color: var(--coral-600); }}
.wp-stat .wp-stat-hint {{ margin-top: 0.35rem; font-size: var(--fs-12); color: var(--ink-500); }}

/* --- health bar ------------------------------------------------------- */
.wp-health {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 0.7rem;
  padding: 0.8rem 1rem;
  background: var(--surface);
  border: 1px solid var(--line);
  border-left: 3px solid var(--ok-600);
  margin-bottom: 1.2rem;
}}
.wp-health.is-attention {{ border-left-color: var(--warn-600); }}
.wp-health.is-critical, .wp-health.is-degraded {{ border-left-color: var(--coral-600); }}
.wp-health-item .wp-stat-label {{ font-size: var(--fs-12); }}
.wp-health-item .wp-health-value {{
  font-family: var(--font-display);
  font-size: var(--fs-16);
  font-weight: 600;
  color: var(--ocean-900);
  font-variant-numeric: tabular-nums;
}}
.wp-dot {{
  display: inline-block; width: 8px; height: 8px; border-radius: 50%;
  background: var(--ok-600); margin-right: 0.35rem;
}}
.is-attention .wp-dot {{ background: var(--warn-600); }}
.is-critical .wp-dot, .is-degraded .wp-dot {{ background: var(--coral-600); }}

/* --- panels & chips --------------------------------------------------- */
.wp-panel {{
  background: var(--surface);
  border: 1px solid var(--line);
  padding: 1rem 1.1rem;
  margin-bottom: 1rem;
}}
.wp-panel-head {{
  display: flex; justify-content: space-between; align-items: baseline;
  gap: 1rem; margin-bottom: 0.7rem;
}}
.wp-panel-head h3 {{ margin: 0; }}
.wp-panel-head .wp-meta {{ color: var(--ink-500); font-size: var(--fs-12); }}
.wp-section-rule {{
  border: 0; border-top: 1px solid var(--line); margin: 1.6rem 0 1.1rem;
}}
.wp-chip {{
  display: inline-block;
  font-size: var(--fs-12);
  font-weight: 600;
  letter-spacing: 0.03em;
  text-transform: uppercase;
  padding: 0.14rem 0.42rem;
  border-radius: 3px;
  background: var(--glacier-100);
  color: var(--ocean-800);
}}
.wp-chip.is-success {{ background: rgba(47,111,94,0.12); color: var(--ok-600); }}
.wp-chip.is-failed  {{ background: rgba(217,107,76,0.14); color: var(--coral-600); }}
.wp-chip.is-warn    {{ background: rgba(196,138,42,0.14); color: var(--warn-600); }}
.wp-note {{ color: var(--ink-500); font-size: var(--fs-14); }}
.wp-caveat {{
  border-left: 3px solid var(--warn-600);
  background: rgba(196,138,42,0.07);
  padding: 0.6rem 0.85rem;
  font-size: var(--fs-14);
  color: var(--ink-700);
  margin: 0.5rem 0 1rem;
}}

/* --- controls --------------------------------------------------------- */
.stButton > button, .stFormSubmitButton > button, .stDownloadButton > button {{
  font-family: var(--font-body);
  font-weight: 600;
  font-size: var(--fs-14);
  border-radius: var(--radius);
  border: 1px solid rgba(11,61,92,0.28);
  background: var(--surface);
  color: var(--ocean-900);
  transition: background 120ms ease, border-color 120ms ease;
}}
.stButton > button:hover, .stFormSubmitButton > button:hover {{
  background: var(--glacier-100); border-color: var(--ocean-700); color: var(--ocean-900);
}}
.stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] {{
  background: var(--ocean-900); border-color: var(--ocean-900); color: #FFFFFF;
}}
.stButton > button[kind="primary"]:hover, .stFormSubmitButton > button[kind="primary"]:hover {{
  background: var(--ocean-800); border-color: var(--ocean-800); color: #FFFFFF;
}}
div[data-testid="stDataFrame"], div[data-testid="stTable"] {{
  font-variant-numeric: tabular-nums;
  border: 1px solid var(--line);
}}
div[data-testid="stMetricValue"] {{
  font-family: var(--font-display);
  font-variant-numeric: tabular-nums;
  color: var(--ocean-900);
}}
[data-testid="stExpander"] details {{ border: 1px solid var(--line); background: var(--surface); }}

/* --- login ------------------------------------------------------------ */
.wp-auth-rail {{
  background:
    linear-gradient(165deg, rgba(7,37,54,0.55), rgba(11,61,92,0.86)),
    url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160' viewBox='0 0 160 160'%3E%3Cpath fill='none' stroke='%237EB6D4' stroke-opacity='0.25' d='M0 80h160M80 0v160M20 20l120 120M140 20L20 140'/%3E%3C/svg%3E"),
    linear-gradient(180deg, var(--ocean-950), var(--ocean-800));
  color: #F4FAFD;
  padding: 2rem 1.9rem;
  min-height: 420px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}}
.wp-auth-rail h1 {{ color: #FFFFFF !important; font-size: var(--fs-40) !important; max-width: 13ch; margin: 0.6rem 0; }}
.wp-auth-rail .wp-eyebrow {{ color: var(--glacier-300); }}
.wp-auth-rail p {{ color: var(--glacier-300); max-width: 36ch; font-size: var(--fs-14); }}
.wp-auth-rail .wp-rail-foot {{
  font-size: var(--fs-12); color: rgba(168,208,230,0.85);
  border-top: 1px solid rgba(126,182,212,0.28); padding-top: 0.8rem;
}}
.wp-cred {{
  font-variant-numeric: tabular-nums;
  font-size: var(--fs-12);
  color: var(--ink-500);
  border-top: 1px solid var(--line);
  padding-top: 0.7rem;
  margin-top: 0.8rem;
}}
</style>
"""


def _html(markup: str) -> None:
    """Render HTML via ``st.html`` when available."""
    fn = getattr(st, "html", None)
    if callable(fn):
        fn(markup)
    else:
        st.markdown(markup, unsafe_allow_html=True)


def inject() -> None:
    """Inject the application stylesheet."""
    _html(_CSS)


def _esc(value: Any) -> str:
    return html.escape(str(value))


def masthead(title: str, eyebrow: str = "", lead: str = "", meta: Sequence[tuple[str, str]] = ()) -> None:
    """Page header: eyebrow, display title, optional lead and right-aligned meta."""
    meta_html = "".join(
        f"<div><strong>{_esc(v)}</strong>{_esc(k)}</div>" for k, v in meta
    )
    _html(
        f"""
        <div class="wp-masthead">
          <div>
            {'<p class="wp-eyebrow">' + _esc(eyebrow) + "</p>" if eyebrow else ""}
            <h1>{_esc(title)}</h1>
            {'<p class="wp-lead">' + _esc(lead) + "</p>" if lead else ""}
          </div>
          <div class="wp-masthead-meta">{meta_html}</div>
        </div>
        """
    )


def stat_strip(items: Iterable[tuple[str, Any, str]], columns: int | None = None) -> None:
    """Render ``(label, value, hint)`` cards. Prefix a label with ``!`` for alert styling."""
    items = list(items)
    if not items:
        return
    cols = columns or min(len(items), 5)
    cards = []
    for label, value, hint in items:
        alert = label.startswith("!")
        clean = label[1:] if alert else label
        cards.append(
            f"""<div class="wp-stat{' is-alert' if alert else ''}">
                  <div class="wp-stat-label">{_esc(clean)}</div>
                  <div class="wp-stat-value">{_esc(value)}</div>
                  {'<div class="wp-stat-hint">' + _esc(hint) + '</div>' if hint else ''}
                </div>"""
        )
    _html(
        f'<div class="wp-stats" style="grid-template-columns: repeat({cols}, minmax(0, 1fr));">'
        + "".join(cards)
        + "</div>"
    )


def health_bar(status: str, items: Iterable[tuple[str, Any]]) -> None:
    state = (status or "healthy").lower()
    cells = "".join(
        f'<div class="wp-health-item"><div class="wp-stat-label">{_esc(label)}</div>'
        f'<div class="wp-health-value">{_esc(value)}</div></div>'
        for label, value in items
    )
    _html(
        f'<div class="wp-health is-{_esc(state)}">'
        f'<div class="wp-health-item"><div class="wp-stat-label">System</div>'
        f'<div class="wp-health-value"><span class="wp-dot"></span>{_esc(state.title())}</div></div>'
        f"{cells}</div>"
    )


def section(title: str, meta: str = "") -> None:
    _html(
        f'<hr class="wp-section-rule"/><div class="wp-panel-head"><h3>{_esc(title)}</h3>'
        f'<span class="wp-meta">{_esc(meta)}</span></div>'
    )


def chip(text: str, kind: str = "") -> str:
    mapping = {
        "success": "is-success",
        "completed": "is-success",
        "failed": "is-failed",
        "running": "is-warn",
        "pending": "is-warn",
        "high": "is-failed",
        "medium": "is-warn",
    }
    return f'<span class="wp-chip {mapping.get(kind or text.lower(), "")}">{_esc(text)}</span>'


def caveat(text: str) -> None:
    """Muted callout for metric caveats."""
    _html(f'<div class="wp-caveat">{_esc(text)}</div>')


def note(text: str) -> None:
    _html(f'<p class="wp-note">{_esc(text)}</p>')
