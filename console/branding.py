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

    /* ── scorecard hero + KPI + dimension cards (custom components) ── */
    .sc-top {{ display:grid; grid-template-columns:minmax(280px,1fr) 2fr; gap:16px; margin-bottom:6px; }}
    @media (max-width:900px) {{ .sc-top {{ grid-template-columns:1fr; }} }}
    .sc-hero {{ background:{SURFACE}; border:1px solid {BORDER}; border-left:4px solid #7C3AED;
         border-radius:0 10px 10px 0; padding:20px 24px; }}
    .sc-hero .lab {{ font-size:11px; font-weight:600; letter-spacing:0.06em; text-transform:uppercase; color:{CAPTION}; }}
    .sc-hero .score {{ font-size:64px; font-weight:700; line-height:1; margin:0.15rem 0; letter-spacing:-0.03em;
         background:{GRADIENT}; -webkit-background-clip:text; background-clip:text; -webkit-text-fill-color:transparent; }}
    .sc-hero .score small {{ font-size:22px; color:{CAPTION}; -webkit-text-fill-color:{CAPTION}; }}
    .sc-kpis {{ display:grid; grid-template-columns:repeat(2,1fr); gap:12px; }}
    @media (min-width:1100px) {{ .sc-kpis {{ grid-template-columns:repeat(4,1fr); }} }}
    .sc-kpi {{ background:{SURFACE}; border:1px solid {BORDER}; border-radius:9px; padding:14px 16px; }}
    .sc-kpi .l {{ font-size:11px; font-weight:600; letter-spacing:0.05em; text-transform:uppercase; color:{CAPTION}; }}
    .sc-kpi .v {{ font-size:17px; font-weight:700; color:#FFFFFF; margin-top:4px; }}
    .sc-badge {{ display:inline-flex; align-items:center; gap:5px; padding:3px 10px; border-radius:4px;
         font-size:11px; font-weight:600; letter-spacing:0.05em; text-transform:uppercase; }}
    .sc-badge.pass {{ background:{_tint(SUCCESS)}; border:1px solid {SUCCESS}; color:{SUCCESS}; }}
    .sc-badge.warn {{ background:{_tint(WARNING)}; border:1px solid {WARNING}; color:{WARNING}; }}
    .sc-badge.fail {{ background:{_tint(ERROR)}; border:1px solid {ERROR}; color:{ERROR}; }}
    .sc-badge.na   {{ background:{RAISED}; border:1px solid {BORDER}; color:{CAPTION}; }}
    .sc-dims {{ display:grid; grid-template-columns:repeat(3,1fr); gap:12px; }}
    @media (max-width:820px) {{ .sc-dims {{ grid-template-columns:1fr; }} }}
    .sc-dcard {{ background:{SURFACE}; border:1px solid {BORDER}; border-radius:9px; padding:14px 16px; }}
    .sc-dcard .dt {{ display:flex; align-items:baseline; justify-content:space-between; gap:8px; }}
    .sc-dcard .nm {{ font-size:11px; font-weight:600; letter-spacing:0.04em; text-transform:uppercase; color:{CAPTION}; }}
    .sc-dcard .vl {{ font-size:30px; font-weight:700; color:#FFFFFF; line-height:1; margin:6px 0 2px; }}
    .sc-dcard .ci {{ font-size:11px; color:{CAPTION}; font-variant-numeric:tabular-nums; }}
    .sc-dcard .bar {{ height:5px; border-radius:3px; background:{RAISED}; margin-top:10px; overflow:hidden; }}
    .sc-dcard .bar > i {{ display:block; height:100%; border-radius:3px; background:{GRADIENT}; }}
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


def _esc(s: object) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


_VERDICT_STATUS = {
    "Deployment-Ready": ("pass", "✓"), "Conditional": ("warn", "◐"),
    "Not-Ready": ("warn", "△"), "High-Risk": ("fail", "✕"),
}


def render_scorecard_header(
    composite: float, verdict: str, confidence: str, model: str,
    lang_domain: str, runtime: str | None = None,
) -> None:
    """Hero composite score (gradient) + a row of KPI cards. Data only; no computation."""
    vstatus, vicon = _VERDICT_STATUS.get(verdict, ("na", "•"))
    rt = (f'<div style="color:{CAPTION};font-size:12px;margin-top:9px">⏱ Runtime {_esc(runtime)}</div>'
          if runtime else "")
    kpis = "".join(
        f'<div class="sc-kpi"><div class="l">{_esc(lbl)}</div><div class="v">{_esc(val)}</div></div>'
        for lbl, val in (("Verdict", verdict), ("Confidence", confidence),
                         ("Model", model), ("Language & Domain", lang_domain))
    )
    st.markdown(
        f'<div class="sc-top"><div class="sc-hero"><div class="lab">Composite score · {_esc(model)}</div>'
        f'<div class="score">{composite:.1f}<small> / 100</small></div>'
        f'<div><span class="sc-badge {vstatus}">{vicon} {_esc(verdict)}</span></div>{rt}</div>'
        f'<div class="sc-kpis">{kpis}</div></div>',
        unsafe_allow_html=True,
    )


def render_dimension_cards(cards: list[dict]) -> None:
    """Grid of dimension cards. Each card: name, weight(0-1), score(float|None), ci(tuple|None), status."""
    _badge = {"pass": ("pass", "OK"), "fail": ("fail", "Below 60"), "na": ("na", "N/A")}
    html = ['<div class="sc-dims">']
    for c in cards:
        cls, txt = _badge.get(c["status"], ("na", "—"))
        val = "N/A" if c["score"] is None else f'{c["score"]:.1f}'
        ci = c.get("ci")
        ci_txt = f"95% CI {ci[0]:.1f}–{ci[1]:.1f}" if ci else "95% CI —"
        width = 0 if c["score"] is None else max(0.0, min(100.0, float(c["score"])))
        html.append(
            f'<div class="sc-dcard"><div class="dt"><span class="nm">{_esc(c["name"])} '
            f'({c["weight"]:.0%})</span><span class="sc-badge {cls}">{txt}</span></div>'
            f'<div class="vl">{val}</div><div class="ci">{ci_txt}</div>'
            f'<div class="bar"><i style="width:{width}%"></i></div></div>'
        )
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)
