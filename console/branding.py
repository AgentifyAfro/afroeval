"""AgentifyAfro brand layer for the AfroEval Scorecard™ console — CSS + UI helpers.

Pure presentation. No business logic, no data access, no view gating (that stays in
``console/access.py``). All accent / semantic colours are sourced from ``console.theme``
(the single WCAG-tested source of truth) so contrast can't silently regress — see
``tests/test_console_contrast.py``. Structural brand hues (pure-black canvas, the purple→
blue→cyan gradient) are constants here.

Public surface:
    inject_brand_css()                          — one master <style> block; call once, first.
    render_section_header(eyebrow, title, ...)  — eyebrow + title section opener.
    render_section_divider()                    — gradient hairline between sections.
    render_status_badge(label, status) -> str   — branded pill; status in STATUS_ORDER.
"""

import streamlit as st

from console.theme import BORDER, ERROR, LINK, SUCCESS, TEXT_FAINT, WARNING

# ── Structural brand tokens (3-step elevation) ──────────────────────────────────
CANVAS = "#000000"   # pure-black page canvas
SURFACE = "#0A0A0F"  # near-black panels above the canvas
RAISED = "#1A1A24"   # charcoal — cards, table headers, sidebar
CAPTION = TEXT_FAINT  # #A6ABC4 — AA/AAA on every surface (brief's #6B7280 fails on cards)
GRADIENT = "linear-gradient(90deg,#7C3AED 0%,#4169E1 50%,#00CFFF 100%)"
INFO = "#00CFFF"      # cyan — accent/fill only, never body text

# ── Status pills — colours from the tested theme, not the brief's failing literals ──
STATUS_CONFIG = {
    "pass":    (SUCCESS, "PASS"),
    "warning": (WARNING, "ATTENTION"),
    "fail":    (ERROR, "FAIL"),
    "info":    (INFO, "INFO"),
}


def _tint(hex_: str, alpha: float = 0.12) -> str:
    r, g, b = (int(hex_.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


def inject_brand_css() -> None:
    """Inject the master brand stylesheet. Call once, before any other content."""
    st.markdown(
        f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    html, body, [class*="css"] {{ font-family:'Inter','Segoe UI',system-ui,sans-serif !important; }}
    [data-testid="stToolbarActions"] {{ display:none !important; }}

    /* ── canvas & 3-step elevation ── */
    .stApp {{ background-color:{CANVAS} !important; }}
    .main .block-container {{ padding-top:2rem; }}
    ::-webkit-scrollbar {{ width:8px; height:8px; }}
    ::-webkit-scrollbar-track {{ background:{SURFACE}; }}
    ::-webkit-scrollbar-thumb {{ background:linear-gradient(180deg,#7C3AED,#00CFFF); border-radius:4px; }}

    /* ── sidebar + logo (enlarged) ── */
    [data-testid="stSidebar"] {{ background-color:{SURFACE} !important; border-right:1px solid {BORDER} !important; }}
    [data-testid="stSidebarLogo"] {{ height:4.5rem !important; }}
    [data-testid="stHeaderLogo"]  {{ height:2.5rem !important; }}

    /* ── gradient H1 + headings ── */
    h1 {{ font-weight:700 !important; background:{GRADIENT}; -webkit-background-clip:text; background-clip:text;
         -webkit-text-fill-color:transparent; letter-spacing:-0.02em; }}
    h2, h3 {{ font-weight:600 !important; }}
    .brand-eyebrow {{ font-size:11px; font-weight:600; letter-spacing:0.09em; text-transform:uppercase;
         color:{CAPTION}; margin-bottom:6px; }}
    .brand-sec-title {{ font-size:22px; font-weight:700; color:#FFFFFF; line-height:1.2; margin:0 0 4px; }}
    .gradient-text {{ background:{GRADIENT}; -webkit-background-clip:text; background-clip:text;
         -webkit-text-fill-color:transparent; font-weight:700; }}
    .brand-divider {{ height:1px; background:{GRADIENT}; opacity:0.55; margin:30px 0; }}

    /* ── buttons ── */
    .stButton > button {{ background:linear-gradient(90deg,#7C3AED 0%,#4169E1 100%) !important; color:#FFFFFF !important;
         border:none !important; font-weight:600 !important; border-radius:6px !important; transition:opacity .15s ease !important; }}
    .stButton > button:hover {{ opacity:0.88 !important; border:none !important; }}
    .stButton > button:active {{ opacity:0.72 !important; }}

    /* ── metric tiles ── */
    [data-testid="stMetric"] {{ background-color:{SURFACE} !important; border:1px solid {BORDER} !important;
         border-radius:9px !important; padding:1rem 1.25rem !important; }}
    [data-testid="stMetricValue"] div {{ color:#FFFFFF !important; font-weight:700 !important; }}
    [data-testid="stMetricLabel"] div {{ color:{CAPTION} !important; font-size:0.72rem !important;
         text-transform:uppercase !important; letter-spacing:0.06em !important; font-weight:600 !important; }}
    [data-testid="stMetricDelta"] {{ font-size:0.8rem !important; }}

    /* ── data tables ── */
    [data-testid="stDataFrame"] {{ border:1px solid {BORDER}; border-radius:10px; }}
    [data-testid="stDataFrame"] thead tr th {{ background-color:{RAISED} !important; color:#FFFFFF !important;
         font-size:11px !important; font-weight:600 !important; letter-spacing:0.04em !important; text-transform:uppercase !important; }}
    [data-testid="stDataFrame"] tbody tr:hover td {{ background-color:{RAISED} !important; }}

    /* ── status alerts — brand left-border accents ── */
    .stSuccess, .stError, .stWarning, .stInfo {{ border-radius:0 6px 6px 0 !important; }}
    .stSuccess {{ background-color:{_tint(SUCCESS, 0.09)} !important; border-left:4px solid {SUCCESS} !important; }}
    .stError   {{ background-color:{_tint(ERROR, 0.09)} !important; border-left:4px solid {ERROR} !important; }}
    .stWarning {{ background-color:{_tint(WARNING, 0.09)} !important; border-left:4px solid {WARNING} !important; }}
    .stInfo    {{ background-color:{_tint(INFO, 0.08)} !important; border-left:4px solid {INFO} !important; }}
    a, a:visited {{ color:{LINK} !important; }}
    .stSuccess {{ color:{SUCCESS} !important; }}
    .stError   {{ color:{ERROR} !important; }}
    .stWarning {{ color:{WARNING} !important; }}

    /* ── expanders, inputs, selects, tabs ── */
    [data-testid="stExpander"] {{ background-color:{SURFACE} !important; border:1px solid {BORDER} !important; border-radius:9px !important; }}
    [data-testid="stTextInput"] > div > div > input {{ background-color:{SURFACE} !important; border-color:{BORDER} !important; border-radius:6px !important; }}
    [data-baseweb="select"] > div {{ background-color:{SURFACE} !important; border-color:{BORDER} !important; border-radius:6px !important; }}
    [data-baseweb="select"] > div:focus-within {{ border-color:#7C3AED !important; box-shadow:0 0 0 2px rgba(124,58,237,0.25) !important; }}
    label[data-testid="stWidgetLabel"] p {{ font-size:0.72rem !important; font-weight:600 !important;
         text-transform:uppercase !important; letter-spacing:0.05em !important; color:{CAPTION} !important; }}
    [data-testid="stTabs"] [role="tab"][aria-selected="true"] {{ color:#FFFFFF !important; font-weight:600 !important;
         border-bottom:2px solid #7C3AED !important; }}

    /* ── sidebar role badge + admin markers ── */
    .role-badge {{ display:inline-flex; align-items:center; gap:6px; font-size:11px; font-weight:700;
         padding:5px 11px; border-radius:6px; }}
    .role-badge.op {{ background:{_tint(SUCCESS, 0.10)}; border:1px solid {SUCCESS}; color:{SUCCESS}; }}
    .role-badge.vw {{ background:{RAISED}; border:1px solid {BORDER}; color:{CAPTION}; }}
    .admin-tag {{ font-size:9px; font-weight:700; letter-spacing:0.06em; text-transform:uppercase;
         color:{WARNING}; border:1px solid {_tint(WARNING, 0.5)}; border-radius:4px; padding:1px 5px; margin-left:6px; }}
    </style>
    """,
        unsafe_allow_html=True,
    )


def render_section_header(eyebrow: str, title: str, accent_word: str = "") -> None:
    """A section opener: small uppercase eyebrow over a bold title, one word optionally in gradient."""
    inner = (
        title.replace(accent_word, f'<span class="gradient-text">{accent_word}</span>')
        if accent_word and accent_word in title
        else title
    )
    st.markdown(
        f'<div style="margin-bottom:18px"><div class="brand-eyebrow">{eyebrow}</div>'
        f'<div class="brand-sec-title">{inner}</div></div>',
        unsafe_allow_html=True,
    )


def render_section_divider() -> None:
    """Branded gradient hairline between major sections (replaces st.divider)."""
    st.markdown('<div class="brand-divider"></div>', unsafe_allow_html=True)


def render_status_badge(label: str, status: str) -> str:
    """Return branded pill HTML. status in {'pass','warning','fail','info'}; colours are AA-safe."""
    color, _default = STATUS_CONFIG.get(status, STATUS_CONFIG["info"])
    return (
        f'<span style="display:inline-flex;align-items:center;gap:6px;padding:3px 10px;border-radius:4px;'
        f'background:{_tint(color)};border:1px solid {color};color:{color};font-size:11px;font-weight:600;'
        f'letter-spacing:0.05em;text-transform:uppercase;">{label}</span>'
    )
