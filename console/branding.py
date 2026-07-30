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

from console.theme import BORDER, ERROR, LINK, SUCCESS, TEXT_FAINT, TEXT_MUTED, WARNING

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
         color:{CAPTION}; margin-bottom:8px; }}
    .brand-sec-title {{ font-size:22px; font-weight:700; color:#FFFFFF; line-height:1.2; margin:0 0 20px; }}
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

    /* ── sidebar nav — restyle the radio as nav rows (icons+ADMIN come from format_func) ── */
    [data-testid="stSidebar"] [role="radiogroup"] {{ gap:3px; }}
    [data-testid="stSidebar"] [role="radiogroup"] > label {{ width:100%; padding:8px 12px; margin:0;
         border-radius:7px; cursor:pointer; transition:background .15s; }}
    [data-testid="stSidebar"] [role="radiogroup"] > label:hover {{ background:{RAISED}; }}
    [data-testid="stSidebar"] [role="radiogroup"] > label > div:first-child {{ display:none; }}
    [data-testid="stSidebar"] [role="radiogroup"] > label:has(input:checked) {{
         background:{RAISED}; box-shadow:inset 3px 0 0 #7C3AED; }}
    [data-testid="stSidebar"] [role="radiogroup"] label p {{ font-size:14px !important; font-weight:500 !important; }}

    /* ── scorecard hero + KPI + dimension cards (custom components) ── */
    .sc-top {{ display:grid; grid-template-columns:minmax(300px,1.05fr) 2fr; gap:18px; margin-bottom:6px; }}
    @media (max-width:900px) {{ .sc-top {{ grid-template-columns:1fr; }} }}
    .sc-hero {{ background:{SURFACE}; border:1px solid {BORDER}; border-left:4px solid #7C3AED;
         border-radius:0 10px 10px 0; padding:22px 26px; }}
    .sc-hero .lab {{ font-size:11px; font-weight:600; letter-spacing:0.06em; text-transform:uppercase; color:{CAPTION}; }}
    .sc-hero .score {{ font-size:72px; font-weight:700; line-height:1; margin:0.2rem 0; letter-spacing:-0.03em;
         background:{GRADIENT}; -webkit-background-clip:text; background-clip:text; -webkit-text-fill-color:transparent; }}
    .sc-hero .score small {{ font-size:24px; color:{CAPTION}; -webkit-text-fill-color:{CAPTION}; }}
    .sc-kpis {{ display:grid; grid-template-columns:repeat(2,1fr); gap:14px; }}
    @media (min-width:1100px) {{ .sc-kpis {{ grid-template-columns:repeat(4,1fr); }} }}
    .sc-kpi {{ background:{SURFACE}; border:1px solid {BORDER}; border-radius:9px; padding:16px 18px; }}
    .sc-kpi .l {{ font-size:11px; font-weight:600; letter-spacing:0.05em; text-transform:uppercase; color:{CAPTION}; }}
    .sc-kpi .v {{ font-size:26px; font-weight:700; color:#FFFFFF; margin-top:6px; line-height:1.1; }}
    .sc-kpi .v.sm {{ font-size:17px; }}
    .sc-badge {{ display:inline-flex; align-items:center; gap:6px; padding:3px 10px; border-radius:4px;
         font-size:11px; font-weight:600; letter-spacing:0.05em; text-transform:uppercase; }}
    .sc-badge.pass {{ background:{_tint(SUCCESS)}; border:1px solid {SUCCESS}; color:{SUCCESS}; }}
    .sc-badge.warn {{ background:{_tint(WARNING)}; border:1px solid {WARNING}; color:{WARNING}; }}
    .sc-badge.fail {{ background:{_tint(ERROR)}; border:1px solid {ERROR}; color:{ERROR}; }}
    .sc-badge.na   {{ background:{RAISED}; border:1px solid {BORDER}; color:{CAPTION}; }}
    .sc-badge.info {{ background:rgba(0,207,255,0.10); border:1px solid {INFO}; color:{INFO}; }}
    .sc-dims {{ display:grid; grid-template-columns:repeat(2,1fr); gap:12px; }}
    @media (max-width:560px) {{ .sc-dims {{ grid-template-columns:1fr; }} }}
    .sc-dcard {{ background:{SURFACE}; border:1px solid {BORDER}; border-radius:9px; padding:14px 16px; }}
    .sc-dcard .dt {{ display:flex; align-items:baseline; justify-content:space-between; gap:8px; }}
    .sc-dcard .nm {{ font-size:12px; font-weight:600; letter-spacing:0.04em; text-transform:uppercase; color:{CAPTION}; }}
    .sc-dcard .vl {{ font-size:28px; font-weight:700; color:#FFFFFF; line-height:1; margin:0; }}
    .sc-dcard .ci {{ font-size:11px; color:{CAPTION}; font-variant-numeric:tabular-nums; margin-top:2px; }}
    .sc-dcard .obs {{ font-size:12.5px; color:{TEXT_MUTED}; margin-top:8px; line-height:1.5; }}
    .sc-dcard .bar {{ height:5px; border-radius:3px; background:{RAISED}; margin-top:10px; overflow:hidden; }}
    .sc-dcard .bar > i {{ display:block; height:100%; border-radius:3px; background:{GRADIENT}; }}

    /* ── standalone KPI row (Provider / HITL headers) ── */
    .kpi-row {{ display:grid; grid-template-columns:repeat(3,1fr); gap:14px; margin:0 0 6px; }}
    .kpi-row.k2 {{ grid-template-columns:repeat(2,1fr); }}
    .kpi-row.k4 {{ grid-template-columns:repeat(4,1fr); }}
    @media (max-width:760px) {{ .kpi-row, .kpi-row.k2, .kpi-row.k4 {{ grid-template-columns:1fr; }} }}
    .kpi-row .k {{ background:{SURFACE}; border:1px solid {BORDER}; border-radius:9px;
         padding:16px 18px; display:flex; flex-direction:column; gap:6px; }}
    .kpi-row .k .l {{ font-size:11px; font-weight:600; letter-spacing:0.05em; text-transform:uppercase; color:{CAPTION}; }}
    .kpi-row .k .v {{ font-size:26px; font-weight:700; color:#FFFFFF; line-height:1.1; }}
    .kpi-row .k .v.sm {{ font-size:17px; }}
    .kpi-row .k .v.grad {{ background:{GRADIENT}; -webkit-background-clip:text; background-clip:text;
         -webkit-text-fill-color:transparent; }}
    .kpi-row .k .d {{ font-size:12px; font-weight:600; color:{CAPTION}; }}
    .kpi-row .k .d.up {{ color:{SUCCESS}; }}
    .kpi-row .k .d.down {{ color:{WARNING}; }}

    /* ── callout (coverage / methodology notes) ── */
    .brand-callout {{ background:rgba(0,207,255,0.07); border-left:4px solid {INFO}; border-radius:0 8px 8px 0;
         padding:14px 18px; color:{TEXT_MUTED}; font-size:13.5px; line-height:1.55; margin:6px 0; }}
    .brand-callout.warn {{ background:rgba(245,158,11,0.07); border-left-color:{WARNING}; }}
    .brand-callout b {{ color:#FFFFFF; }}
    .brand-callout code {{ background:{RAISED}; padding:1px 6px; border-radius:4px; font-size:12.5px; }}

    /* ── item drill-down detail panel ── */
    .idetail {{ background:{SURFACE}; border:1px solid {BORDER}; border-radius:10px; padding:20px 22px; }}
    .idetail .ihead {{ display:flex; align-items:center; flex-wrap:wrap; gap:8px; margin-bottom:14px; }}
    .idetail .ihead .id {{ font-size:15px; font-weight:700; color:#FFFFFF; font-variant-numeric:tabular-nums; }}
    .idetail .field {{ margin:14px 0; }}
    .idetail .field .fl {{ font-size:11px; font-weight:600; letter-spacing:0.05em; text-transform:uppercase;
         color:{CAPTION}; margin-bottom:5px; }}
    .idetail .field .fc {{ font-size:14px; color:{TEXT_MUTED}; line-height:1.6; }}
    .idetail .field .resp {{ background:{CANVAS}; border:1px solid {BORDER}; border-radius:8px;
         padding:12px 14px; white-space:pre-wrap; }}
    .idetail .mtable {{ width:100%; border-collapse:collapse; font-size:12.5px; margin-top:6px; }}
    .idetail .mtable th {{ text-align:left; font-size:10.5px; letter-spacing:0.04em; text-transform:uppercase;
         color:{CAPTION}; padding:6px 8px; border-bottom:1px solid {BORDER}; font-weight:600; }}
    .idetail .mtable td {{ padding:7px 8px; border-bottom:1px solid {BORDER}; color:{TEXT_MUTED}; vertical-align:top; }}
    .idetail .mtable td.num {{ text-align:right; font-variant-numeric:tabular-nums; color:#FFFFFF; font-weight:600; }}
    .idetail-empty {{ background:{SURFACE}; border:1px dashed {BORDER}; border-radius:10px;
         padding:44px 22px; text-align:center; color:{CAPTION}; font-size:13.5px; }}

    /* ── comparison ranking bars ── */
    .cmp {{ display:flex; flex-direction:column; gap:12px; max-width:720px; }}
    .cmp-row {{ display:grid; grid-template-columns:minmax(140px,240px) 1fr auto; align-items:center; gap:14px; }}
    .cmp-l {{ font-size:13px; color:{TEXT_MUTED}; }}
    .cmp-track {{ height:26px; background:{RAISED}; border-radius:6px; overflow:hidden; }}
    .cmp-fill {{ height:100%; border-radius:6px; }}
    .cmp-fill.f1 {{ background:{GRADIENT}; }}
    .cmp-fill.f2 {{ background:linear-gradient(90deg,#4169E1,#00CFFF); }}
    .cmp-v {{ font-size:14px; font-weight:700; color:#FFFFFF; font-variant-numeric:tabular-nums; }}
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
        f'<div><div class="brand-eyebrow">{eyebrow}</div>'
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
    # Text KPIs use the smaller `.v.sm` (17px); numeric ones (Runtime) use `.v` (26px) — as the mock.
    kpis = "".join(
        f'<div class="sc-kpi"><div class="l">{_esc(lbl)}</div><div class="v{sm}">{_esc(val)}</div></div>'
        for lbl, val, sm in (("Language & Domain", lang_domain, " sm"), ("Confidence", confidence, " sm"),
                             ("Verdict", verdict, " sm"), ("Runtime", runtime or "—", ""))
    )
    st.markdown(
        f'<div class="sc-top"><div class="sc-hero"><div class="lab">Composite score · {_esc(model)}</div>'
        f'<div class="score">{composite:.1f}<small> / 100</small></div>'
        f'<div><span class="sc-badge {vstatus}">{vicon} {_esc(verdict)}</span></div></div>'
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
        obs = f'<div class="obs">{_esc(c["blurb"])}</div>' if c.get("blurb") else ""
        html.append(
            f'<div class="sc-dcard"><div class="dt"><span class="nm">{_esc(c["name"])} '
            f'({c["weight"]:.0%})</span><span class="sc-badge {cls}">{txt}</span></div>'
            f'<div class="vl">{val}</div><div class="ci">{ci_txt}</div>{obs}'
            f'<div class="bar"><i style="width:{width}%"></i></div></div>'
        )
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)


def render_comparison_bars(rows: list[tuple[str, float]], max_value: float = 100.0) -> None:
    """Horizontal ranking bars (descending). rows = [(label, value), ...]; value on max_value scale."""
    html = ['<div class="cmp">']
    for i, (label, val) in enumerate(sorted(rows, key=lambda r: r[1], reverse=True)):
        width = 0.0 if not max_value else max(0.0, min(100.0, val / max_value * 100))
        fill = "f1" if i == 0 else "f2"
        html.append(
            f'<div class="cmp-row"><span class="cmp-l">{_esc(label)}</span>'
            f'<div class="cmp-track"><div class="cmp-fill {fill}" style="width:{width}%"></div></div>'
            f'<span class="cmp-v">{val:.1f}</span></div>'
        )
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)


def render_kpi_row(kpis: list[dict], columns: int = 3) -> None:
    """Row of branded KPI cards (display only). Each kpi dict:
    label, value, sub?(str), trend?('up'|'down'|'flat'), sm?(bool), grad?(bool)."""
    grid = {2: "k2", 4: "k4"}.get(columns, "")
    cells = []
    for k in kpis:
        vcls = "v" + (" sm" if k.get("sm") else "") + (" grad" if k.get("grad") else "")
        sub = ""
        if k.get("sub"):
            trend = k.get("trend", "flat")
            arrow = {"up": "▲ ", "down": "▼ "}.get(trend, "")
            sub = f'<span class="d {trend}">{arrow}{_esc(k["sub"])}</span>'
        cells.append(
            f'<div class="k"><span class="l">{_esc(k["label"])}</span>'
            f'<span class="{vcls}">{_esc(k["value"])}</span>{sub}</div>'
        )
    st.markdown(f'<div class="kpi-row {grid}">{"".join(cells)}</div>', unsafe_allow_html=True)


def render_callout(body_html: str, kind: str = "info") -> None:
    """Left-bordered note. body_html is trusted markup built by the caller (may hold <b>/<code>)."""
    cls = "brand-callout warn" if kind == "warn" else "brand-callout"
    st.markdown(f'<div class="{cls}">{body_html}</div>', unsafe_allow_html=True)


_METRIC_BADGE = {"pass": ("pass", "Pass"), "warn": ("warn", "Attention"), "fail": ("fail", "Fail")}


def render_item_detail(detail: dict) -> None:
    """Drill-down detail panel (custom HTML; data only, no computation). Keys:
    id, cohort?(str), tags?(str), prompt, gloss?(str), expected, response, foot?(str),
    metrics(list of (dimension, metric, score_0_100, status, reason))."""
    m_rows = []
    for dim, metric, score, status, reason in detail.get("metrics", []):
        cls, lbl = _METRIC_BADGE.get(status, ("na", "—"))
        m_rows.append(
            f"<tr><td>{_esc(dim)}</td><td>{_esc(metric)}</td>"
            f'<td class="num">{score:.1f}</td>'
            f'<td><span class="sc-badge {cls}">{lbl}</span></td><td>{_esc(reason)}</td></tr>'
        )
    body = "".join(m_rows) or '<tr><td colspan="5">No metric results for this item.</td></tr>'
    cohort = f'<span class="sc-badge info">{_esc(detail["cohort"])}</span>' if detail.get("cohort") else ""
    tags = (f'<span style="color:{CAPTION};font-size:12px">{_esc(detail["tags"])}</span>'
            if detail.get("tags") else "")
    gloss = (f'<div style="color:{CAPTION};font-size:12px;margin-top:3px">{_esc(detail["gloss"])}</div>'
             if detail.get("gloss") else "")
    foot = (f'<div class="field"><div class="fl">Response metadata</div>'
            f'<div class="fc">{_esc(detail["foot"])}</div></div>' if detail.get("foot") else "")
    st.markdown(
        f'<div class="idetail">'
        f'<div class="ihead"><span class="id">{_esc(detail["id"])}</span>{cohort}{tags}</div>'
        f'<div class="field"><div class="fl">Prompt</div>'
        f'<div class="fc">{_esc(detail["prompt"])}{gloss}</div></div>'
        f'<div class="field"><div class="fl">Expected behavior</div>'
        f'<div class="fc">{_esc(detail["expected"])}</div></div>'
        f'<div class="field"><div class="fl">Model response</div>'
        f'<div class="fc resp">{_esc(detail["response"])}</div></div>'
        f'<div class="field"><div class="fl">Metric results</div>'
        f'<table class="mtable"><thead><tr><th>Dimension</th><th>Metric</th>'
        f'<th style="text-align:right">Score</th><th>Status</th><th>Reason</th></tr></thead>'
        f"<tbody>{body}</tbody></table></div>{foot}</div>",
        unsafe_allow_html=True,
    )


def render_detail_placeholder(message: str) -> None:
    """Dashed empty-state card shown in the detail pane before a row is selected."""
    st.markdown(f'<div class="idetail-empty">{_esc(message)}</div>', unsafe_allow_html=True)
