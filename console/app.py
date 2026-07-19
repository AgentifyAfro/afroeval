"""
AfroEval Scorecard™ Console

Per-run scorecard summary + per-item drill-down into ModelResponse and MetricResult data.
Reads directly from the DB — no HTTP server required.

Run:
    streamlit run console/app.py
"""

import json
import subprocess
import sys
import threading
import time
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlmodel import Session, col, select

from auth.client import (
    AuthServiceUnavailableError,
    AuthUser,
    InvalidCredentialsError,
    SupabaseAuthClient,
)
from benchmarks.ids import stable_item_uuid
from benchmarks.loader import PACKS_DIR
from console.access import can_archive_runs, resolve_views
from db.models import (
    Assessment,
    BenchmarkItem,
    BenchmarkPack,
    MetricResult,
    ModelResponse,
    ResponseReview,
    Run,
    RunStatus,
    Scorecard,
)
from db.session import get_engine

# ── Constants ─────────────────────────────────────────────────────────────────

DIM_SHORT = {
    "language_performance":     "LP",
    "cultural_appropriateness": "CA",
    "hallucination_risk":       "HR",
    "bias_fairness":            "BF",
    "code_switching_quality":   "CS",
    "safety_robustness":        "SR",
}

DIM_WEIGHTS = {
    "language_performance":     "25%",
    "cultural_appropriateness": "20%",
    "hallucination_risk":       "20%",
    "bias_fairness":            "15%",
    "code_switching_quality":   "10%",
    "safety_robustness":        "10%",
}

DIM_LABELS = {
    "language_performance":     "Language Performance",
    "cultural_appropriateness": "Cultural Appropriateness",
    "hallucination_risk":       "Hallucination Risk",
    "bias_fairness":            "Bias & Fairness",
    "code_switching_quality":   "Code Switching Quality",
    "safety_robustness":        "Safety Robustness",
}

PROVIDER_SHORT = {
    "azure_openai": "Azure",
    "openai":       "OpenAI",
    "anthropic":    "Anthropic",
    "gemini":       "Gemini",
    "jsonl_upload": "Upload",
}

LANGUAGE_NAMES = {
    "en":    "English (US)",
    "sw":    "Swahili",
    "yo":    "Yoruba",
    "am":    "Amharic",
    "ha":    "Hausa",
    "om":    "Oromo",
    "zu":    "Zulu",
    "so":    "Somali",
    "sheng": "Sheng",
}

PACK_CATALOG = [
    {"id": "mobile_money_sw_v1.0.0",      "label": "Mobile Money (Swahili)",        "language": "sw"},
    {"id": "remittance_so_v1.0.0",         "label": "Remittance (Somali)",           "language": "so"},
    {"id": "cross_border_trade_ha_v1.0.0", "label": "Cross-Border Trade (Hausa)",    "language": "ha"},
    {"id": "community_health_am_v1.1.0",   "label": "Community Health (Amharic)",    "language": "am"},
    {"id": "agriculture_om_v1.0.0",        "label": "Agriculture (Oromo)",           "language": "om"},
    {"id": "agriculture_ha_v1.0.0",        "label": "Agriculture (Hausa)",           "language": "ha"},
    {"id": "public_services_zu_v1.0.0",    "label": "Public Services (Zulu)",        "language": "zu"},
    {"id": "customer_service_yo_v1.0.0",   "label": "Customer Service (Yoruba)",     "language": "yo"},
    {"id": "urban_digital_sheng_v1.0.0",   "label": "Urban Digital (Sheng)",         "language": "sheng"},
    {"id": "code_switching_mixed_v1.0.0",  "label": "Code Switching (mixed)",        "language": "mixed"},
    {"id": "safety_mixed_v1.0.0",          "label": "Safety (mixed)",                "language": "mixed"},
    {"id": "customer_service_en_v1.0.0",   "label": "Customer Service (English)",    "language": "en"},
]

_PACK_META: dict[str, str] = {p["id"]: p["label"] for p in PACK_CATALOG}

PROVIDER_MODEL_DEFAULTS = {
    "azure_openai": "gpt-4.1-mini",
    "anthropic":    "claude-haiku-4-5-20251001",
    "openai":       "gpt-4o",
    "gemini":       "gemini-2.5-flash",
}

PROJECT_ROOT = Path(__file__).parent.parent

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="AfroEval Console",
    page_icon="🌍",
    layout="wide",
)

# ── Brand logo — top-left header, before the sidebar >> toggle ─────────────────
# agentifyafro-lockup.png is the alpha-keyed (transparent-background) horizontal
# lockup derived from agentifyafro-logo.png — the real "AgentifyAfro.ai" wordmark
# + gradient node mark, with the baked near-black field dropped out so it blends
# into both the sidebar (#1A1A24) and canvas (#0A0A0F) without a box seam. The
# standalone glyph mark is the small icon shown when the sidebar is collapsed.
_ASSETS = PROJECT_ROOT / "assets"
st.logo(
    str(_ASSETS / "agentifyafro-lockup.png"),
    size="large",
    link="https://agentifyafro.ai",
    icon_image=str(_ASSETS / "agentifyafro-mark.png"),
)

# Brand CSS — AgentifyAfro dark theme + Inter font + gradient accents.
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    /* ── Base font ─────────────────────────────────────────────── */
    html, body, [class*="css"] {
        font-family: 'Inter', 'Segoe UI', system-ui, sans-serif !important;
    }

    /* ── Hide Cloud toolbar ─────────────────────────────────────── */
    [data-testid="stToolbarActions"] { display: none !important; }

    /* ── Canvas ─────────────────────────────────────────────────── */
    .stApp { background-color: #0A0A0F !important; }
    .main .block-container { padding-top: 2rem; }

    /* ── Sidebar ─────────────────────────────────────────────────── */
    [data-testid="stSidebar"] {
        background-color: #1A1A24 !important;
        border-right: 1px solid #2D2D3D !important;
    }

    /* ── Brand logo — bump past st.logo's "large" preset (32px) ─────── */
    [data-testid="stSidebarLogo"] { height: 3.5rem !important; }
    [data-testid="stHeaderLogo"]  { height: 2.25rem !important; }

    /* ── H1 — gradient title text ────────────────────────────────── */
    h1 {
        font-weight: 700 !important;
        background: linear-gradient(90deg, #7C3AED 0%, #4169E1 50%, #00CFFF 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        letter-spacing: -0.02em;
    }
    h2, h3 { font-weight: 600 !important; }

    /* ── Buttons — gradient primary ──────────────────────────────── */
    .stButton > button {
        background: linear-gradient(90deg, #7C3AED 0%, #4169E1 100%) !important;
        color: #FFFFFF !important;
        border: none !important;
        font-weight: 600 !important;
        border-radius: 6px !important;
        transition: opacity 0.15s ease !important;
    }
    .stButton > button:hover { opacity: 0.85 !important; border: none !important; }
    .stButton > button:active { opacity: 0.70 !important; }

    /* ── Metric cards ─────────────────────────────────────────────── */
    [data-testid="stMetric"] {
        background-color: #1A1A24 !important;
        border-radius: 8px !important;
        padding: 1rem 1.25rem !important;
        border: 1px solid #2D2D3D !important;
    }
    [data-testid="stMetricValue"] div { color: #00CFFF !important; font-weight: 700 !important; }
    [data-testid="stMetricLabel"] div {
        color: #6B7280 !important;
        font-size: 0.72rem !important;
        text-transform: uppercase !important;
        letter-spacing: 0.06em !important;
        font-weight: 500 !important;
    }

    /* ── Status alerts — brand palette ───────────────────────────── */
    .stSuccess { background-color: rgba(16,185,129,0.10) !important; color: #10B981 !important; }
    .stError   { background-color: rgba(239,68,68,0.10) !important; }
    .stWarning { background-color: rgba(245,158,11,0.10) !important; }
    .stInfo    { background-color: rgba(0,207,255,0.08) !important; }

    /* ── Expanders ─────────────────────────────────────────────────── */
    [data-testid="stExpander"] {
        background-color: #1A1A24 !important;
        border: 1px solid #2D2D3D !important;
        border-radius: 8px !important;
    }

    /* ── Selectbox / text input ────────────────────────────────────── */
    [data-testid="stSelectbox"] > div > div { border-color: #2D2D3D !important; border-radius: 6px !important; }
    [data-testid="stTextInput"] > div > div > input {
        background-color: #1A1A24 !important;
        border-color: #2D2D3D !important;
        border-radius: 6px !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def render_console_header() -> None:
    """Brand header: globe emoji in its natural color (kept outside the h1's gradient-clip)
    + gradient-text title, used at the top of every console view."""
    st.markdown(
        '<div style="display:flex;align-items:center;gap:0.5rem;margin-bottom:0.25rem;">'
        '<span style="font-size:2rem;line-height:1;">\U0001F30D</span>'
        '<h1 style="margin:0;">AfroEval Scorecard&trade; Console</h1>'
        '</div>',
        unsafe_allow_html=True,
    )


# ── Cached data loaders ───────────────────────────────────────────────────────

@st.cache_data(ttl=60)
def build_string_id_map() -> dict[str, str]:
    """Reverse-lookup {item_uuid_str: string_id} built from local JSONL files."""
    mapping = {}
    for pack_path in PACKS_DIR.glob("*.jsonl"):
        with pack_path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                item = json.loads(line)
                sid = item.get("id", "")
                if sid:
                    mapping[str(stable_item_uuid(sid))] = sid
    return mapping


@st.cache_data(ttl=30)
def load_runs_summary(include_archived: bool = False) -> list[dict]:
    """Return lightweight metadata for the 50 most recent runs.

    Archived runs are excluded unless include_archived=True (admin "Show archived").
    """
    engine = get_engine()
    rows = []
    with Session(engine) as session:
        query = select(Run)
        if not include_archived:
            query = query.where(Run.archived == False)  # noqa: E712 — SQLAlchemy needs ==
        runs = session.exec(query.order_by(Run.created_at.desc()).limit(50)).all()
        for run in runs:
            assessment = session.get(Assessment, run.assessment_id)
            scorecard = session.exec(
                select(Scorecard).where(Scorecard.run_id == run.id)
            ).first()

            name = assessment.name if assessment else "Unknown"
            if scorecard:
                label = f"{name} — {scorecard.composite_score:.1f} ({scorecard.verdict})"
            else:
                label = f"{name} — {run.status}"

            rows.append({
                "run_id":              str(run.id),
                "label":               label,
                "created_at":          str(run.created_at),
                "status":              run.status,
                "archived":            run.archived,
                "has_scorecard":       scorecard is not None,
                "composite_score":     scorecard.composite_score if scorecard else None,
                "verdict":             scorecard.verdict if scorecard else None,
                "confidence_flag":     scorecard.confidence_flag if scorecard else None,
                "safety_unverified":   scorecard.safety_unverified if scorecard else False,
                "african_fabrication_detected": scorecard.african_fabrication_detected if scorecard else False,
                "dimension_scores":    scorecard.dimension_scores if scorecard else {},
                "dimension_weights":   scorecard.dimension_weights if scorecard else {},
                "remediation_roadmap": scorecard.remediation_roadmap if scorecard else [],
                "pack_ids":            assessment.benchmark_pack_ids if assessment else [],
                "model":               assessment.model_identifier if assessment else "",
            })
    return rows


@st.cache_data(ttl=60)
def _scorecard_pdf_bytes(run_id: str) -> bytes | None:
    """Render the scorecard PDF on demand from DB rows — no disk path to go
    stale, survives restarts/redeploys since Postgres is the only durable state.
    """
    from reporting.generator import generate_scorecard_pdf_bytes

    engine = get_engine()
    with Session(engine) as session:
        run = session.get(Run, uuid.UUID(run_id))
        if run is None:
            return None
        scorecard = session.exec(select(Scorecard).where(Scorecard.run_id == run.id)).first()
        assessment = session.get(Assessment, run.assessment_id)
        if scorecard is None or assessment is None:
            return None
        return generate_scorecard_pdf_bytes(scorecard, run, assessment)


@st.cache_data(ttl=30)
def load_run_items(run_id: str) -> tuple[pd.DataFrame, dict[str, list[dict]]]:
    """
    Return (df, metrics_by_response_id).
    df has one row per ModelResponse with per-dimension aggregate scores (0–100).
    metrics_by_response_id maps response_id -> list of MetricResult dicts.
    """
    string_id_map = build_string_id_map()
    engine = get_engine()

    with Session(engine) as session:
        responses = session.exec(
            select(ModelResponse).where(ModelResponse.run_id == uuid.UUID(run_id))
        ).all()
        if not responses:
            return pd.DataFrame(), {}

        response_ids = [r.id for r in responses]
        item_ids     = [r.item_id for r in responses]

        items = session.exec(
            select(BenchmarkItem).where(col(BenchmarkItem.id).in_(item_ids))
        ).all()
        item_map = {str(item.id): item for item in items}

        metrics = session.exec(
            select(MetricResult).where(col(MetricResult.response_id).in_(response_ids))
        ).all()

        metrics_by_resp: dict[str, list[dict]] = {}
        for m in metrics:
            key = str(m.response_id)
            metrics_by_resp.setdefault(key, []).append({
                "dimension":   m.dimension,
                "metric_name": m.metric_name,
                "score":       m.score,
                "passed":      m.passed,
                "reason":      m.reason,
            })

        rows = []
        for r in responses:
            item = item_map.get(str(r.item_id))
            string_id   = string_id_map.get(str(r.item_id), str(r.item_id)[:8] + "…")
            is_filtered = "[AFROEVAL NOTE:" in (r.raw_output or "")

            row: dict = {
                "item_id":           string_id,
                "response_id":       str(r.id),
                "language":          item.language if item else "",
                "domain":            item.domain if item else "",
                "is_gold":           item.is_gold if item else False,
                "prompt":            item.prompt if item else "",
                "expected_behavior": item.expected_behavior if item else "",
                "raw_output":        r.raw_output or "",
                "latency_ms":        r.latency_ms,
                "tokens_used":       r.tokens_used,
                "is_filtered":       is_filtered,
            }

            resp_metrics = metrics_by_resp.get(str(r.id), [])
            for dim, short in DIM_SHORT.items():
                dim_scores = [m["score"] for m in resp_metrics if m["dimension"] == dim]
                row[short] = round(sum(dim_scores) / len(dim_scores) * 100, 1) if dim_scores else None

            rows.append(row)

    return pd.DataFrame(rows), metrics_by_resp


@st.cache_data(ttl=30)
def load_calibration_data() -> pd.DataFrame:
    """
    One row per SME ResponseReview (hitl/ pipeline), with the automated MetricResult
    mean per dimension alongside it for comparison. Cross-run — calibration is a
    question about the metrics themselves, not any one evaluation run.
    """
    string_id_map = build_string_id_map()
    engine = get_engine()

    with Session(engine) as session:
        reviews = session.exec(select(ResponseReview)).all()
        if not reviews:
            return pd.DataFrame()

        response_ids = list({r.response_id for r in reviews})
        responses = session.exec(
            select(ModelResponse).where(col(ModelResponse.id).in_(response_ids))
        ).all()
        response_map = {r.id: r for r in responses}

        item_ids = [r.item_id for r in responses]
        items = session.exec(
            select(BenchmarkItem).where(col(BenchmarkItem.id).in_(item_ids))
        ).all()
        item_map = {item.id: item for item in items}

        metrics = session.exec(
            select(MetricResult).where(col(MetricResult.response_id).in_(response_ids))
        ).all()
        automated_by_resp_dim: dict[tuple, list[float]] = {}
        for m in metrics:
            automated_by_resp_dim.setdefault((m.response_id, m.dimension), []).append(m.score)

        rows = []
        for review in reviews:
            resp = response_map.get(review.response_id)
            item = item_map.get(resp.item_id) if resp else None
            string_id = (
                string_id_map.get(str(resp.item_id), str(resp.item_id)[:8] + "…") if resp else "?"
            )

            row: dict = {
                "response_id": str(review.response_id),
                "item_id":     string_id,
                "run_id":      str(resp.run_id) if resp else "",
                "reviewer_id": review.reviewer_id,
                "language":    item.language if item else "",
                "domain":      item.domain if item else "",
                "prompt":      item.prompt if item else "",
                "raw_output":  resp.raw_output if resp else "",
                "reviewed_at": str(review.created_at),
            }

            for dim in DIM_SHORT:
                sme_score = getattr(review, f"{dim}_score")
                rationale = getattr(review, f"{dim}_rationale")
                auto_scores = automated_by_resp_dim.get((review.response_id, dim), [])
                auto_mean = sum(auto_scores) / len(auto_scores) if auto_scores else None

                row[f"sme_{dim}"]       = sme_score
                row[f"auto_{dim}"]      = auto_mean
                row[f"delta_{dim}"]     = (
                    sme_score - auto_mean if sme_score is not None and auto_mean is not None else None
                )
                row[f"rationale_{dim}"] = rationale

            rows.append(row)

    return pd.DataFrame(rows)


@st.cache_data(ttl=30)
def load_provider_comparison(include_archived: bool = False) -> list[dict]:
    """All completed scorecards with assessment metadata, grouped for cross-provider comparison.

    Archived runs are excluded unless include_archived=True. Also feeds the
    Language Comparison view, so archiving a run removes it from both.
    """
    engine = get_engine()
    rows = []
    with Session(engine) as session:
        query = select(Run).where(Run.status == "completed")
        if not include_archived:
            query = query.where(Run.archived == False)  # noqa: E712 — SQLAlchemy needs ==
        runs = session.exec(query.order_by(Run.created_at.desc())).all()
        for run in runs:
            scorecard = session.exec(
                select(Scorecard).where(Scorecard.run_id == run.id)
            ).first()
            if not scorecard:
                continue
            assessment = session.get(Assessment, run.assessment_id)
            if not assessment:
                continue
            pack_ids = sorted(assessment.benchmark_pack_ids or [])
            rows.append({
                "run_id":           str(run.id),
                "name":             assessment.name,
                "model_provider":   assessment.model_provider,
                "model_identifier": assessment.model_identifier,
                "pack_ids":         pack_ids,
                "pack_label":       " + ".join(pack_ids) if pack_ids else "(no packs)",
                "completed_at":     run.completed_at.strftime("%Y-%m-%d %H:%M UTC") if run.completed_at else "",
                "composite_score":  scorecard.composite_score,
                "verdict":          scorecard.verdict,
                "confidence_flag":  scorecard.confidence_flag,
                "safety_unverified": scorecard.safety_unverified,
                "african_fabrication_detected": scorecard.african_fabrication_detected,
                "dimension_scores": scorecard.dimension_scores or {},
                "dimension_weights": scorecard.dimension_weights or {},
            })
    return rows


@st.cache_data(ttl=30)
def load_language_breakdown(run_ids_a: tuple[str, ...], run_ids_b: tuple[str, ...]) -> pd.DataFrame:
    """
    Aggregate MetricResult scores per language across ALL runs for two models.
    Returns one row per (language, model-group) with per-dimension means (0–100) and a composite.
    The first run_id in each tuple is stored as the row key so downstream _get lookups work.
    """
    engine = get_engine()
    rows = []

    for group_run_ids in [run_ids_a, run_ids_b]:
        if not group_run_ids:
            continue

        model_label: str | None = None
        provider: str = ""
        lang_counts:    dict[str, int]                  = {}
        lang_dim_scores: dict[str, dict[str, list[float]]] = {}

        for run_id_str in group_run_ids:
            with Session(engine) as session:
                run = session.get(Run, uuid.UUID(run_id_str))
                if not run:
                    continue
                assessment = session.get(Assessment, run.assessment_id)
                if model_label is None:
                    model_label = assessment.model_identifier if assessment else run_id_str[:8]
                    provider    = assessment.model_provider if assessment else ""

                responses = session.exec(
                    select(ModelResponse).where(ModelResponse.run_id == uuid.UUID(run_id_str))
                ).all()
                if not responses:
                    continue

                response_ids = [r.id for r in responses]
                item_ids     = [r.item_id for r in responses]

                items = session.exec(
                    select(BenchmarkItem).where(col(BenchmarkItem.id).in_(item_ids))
                ).all()
                item_map = {str(item.id): item for item in items}

                metrics = session.exec(
                    select(MetricResult).where(col(MetricResult.response_id).in_(response_ids))
                ).all()

                resp_to_lang: dict[str, str] = {}
                for r in responses:
                    item = item_map.get(str(r.item_id))
                    lang = item.language if item else "unknown"
                    resp_to_lang[str(r.id)] = lang
                    lang_counts[lang] = lang_counts.get(lang, 0) + 1
                    if lang not in lang_dim_scores:
                        lang_dim_scores[lang] = {dim: [] for dim in DIM_SHORT}

                for m in metrics:
                    lang = resp_to_lang.get(str(m.response_id), "unknown")
                    if m.dimension in lang_dim_scores.get(lang, {}):
                        lang_dim_scores[lang][m.dimension].append(m.score)

        # Use the most-recent run_id (group_run_ids[0]) as the row key so that
        # _get(lang, run_id_a, col) lookups in render_language_breakdown resolve correctly.
        key_run_id = group_run_ids[0]
        for lang, dim_data in lang_dim_scores.items():
            row: dict = {
                "language":   lang,
                "model":      model_label or "unknown",
                "provider":   provider,
                "run_id":     key_run_id,
                "item_count": lang_counts.get(lang, 0),
            }
            dim_means = []
            for dim, short in DIM_SHORT.items():
                scores = dim_data[dim]
                mean   = round(sum(scores) / len(scores) * 100, 1) if scores else None
                row[short] = mean
                if mean is not None:
                    dim_means.append(mean)
            row["composite"] = round(sum(dim_means) / len(dim_means), 1) if dim_means else None
            rows.append(row)

    return pd.DataFrame(rows)


@st.cache_data(ttl=30)
def load_seeded_pack_ids() -> set:
    engine = get_engine()
    with Session(engine) as session:
        packs = session.exec(select(BenchmarkPack)).all()
        return {f"{p.name}_{p.version}" for p in packs}


# ── UI helpers ────────────────────────────────────────────────────────────────

def _verdict_badge(verdict: str) -> str:
    icons = {"Deployment-Ready": "🟢", "Conditional": "🟡", "Not-Ready": "🟠", "High-Risk": "🔴"}
    return f"{icons.get(verdict, '⚪')} {verdict}"


def _render_remediation(roadmap: list[dict]) -> None:
    if not roadmap:
        return
    st.divider()
    st.subheader("Remediation Roadmap")
    priority_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}
    priority_rank = {"high": 0, "medium": 1, "low": 2}
    for item in sorted(roadmap, key=lambda x: priority_rank.get(x.get("priority", "low"), 2)):
        p   = item.get("priority", "medium")
        dim = item.get("dimension", "").replace("_", " ").title()
        with st.expander(f"{priority_icon.get(p, '⚪')} [{p.upper()}] {dim}"):
            st.write(item.get("recommendation", ""))
            st.caption(f"Estimated effort: {item.get('estimated_effort', 'unknown')}")


def _provider_short(provider: str) -> str:
    return PROVIDER_SHORT.get(provider, provider)


def _render_comparison_insight(row_a: dict, row_b: dict, dims: list[str]) -> None:
    delta = row_b["composite_score"] - row_a["composite_score"]
    winner = row_b if delta >= 0 else row_a
    loser  = row_a if delta >= 0 else row_b
    abs_delta = abs(delta)

    if abs_delta < 2.0:
        st.info(
            "Composite scores are within 2 points — providers perform similarly on these packs. "
            "Check dimension-level deltas for more nuance."
        )
        return

    gains: list[tuple[str, float]] = []
    for dim in dims:
        d = row_b["dimension_scores"].get(dim, 0) - row_a["dimension_scores"].get(dim, 0)
        if abs(d) >= 3.0:
            gains.append((dim, d))
    gains.sort(key=lambda x: abs(x[1]), reverse=True)

    parts = [
        f"**{_provider_short(winner['model_provider'])} ({winner['model_identifier']})** "
        f"scores **{abs_delta:.1f} points higher** than "
        f"**{_provider_short(loser['model_provider'])} ({loser['model_identifier']})**."
    ]
    if gains:
        top_strs = []
        for dim, d in gains[:3]:
            sign = "+" if d >= 0 else ""
            top_strs.append(f"{dim.replace('_', ' ').title()} ({sign}{d:.1f})")
        parts.append(f"Largest dimension gaps: {', '.join(top_strs)}.")
    parts.append(
        f"**Recommendation:** For this pack combination, routing to "
        f"**{_provider_short(winner['model_provider'])}** yields better results."
    )
    st.markdown("  \n\n".join(parts))


def _agreement_badge(mean_delta: float) -> str:
    abs_delta = abs(mean_delta)
    if abs_delta < 0.10:
        return "🟢 Close"
    elif abs_delta < 0.20:
        return "🟡 Moderate"
    return "🔴 Diverging"


def _render_calibration_summary(cal_df: pd.DataFrame) -> None:
    st.subheader("Calibration Summary — SME vs Automated, by Dimension")
    summary_rows = []
    for dim in DIM_SHORT:
        sme_col, auto_col, delta_col = f"sme_{dim}", f"auto_{dim}", f"delta_{dim}"
        valid = cal_df[[sme_col, auto_col, delta_col]].dropna()
        if valid.empty:
            continue
        mean_delta = valid[delta_col].mean()
        summary_rows.append({
            "Dimension":      dim.replace("_", " ").title(),
            "Reviews":        len(valid),
            "SME Mean":       f"{valid[sme_col].mean() * 100:.1f}",
            "Automated Mean": f"{valid[auto_col].mean() * 100:.1f}",
            "Mean Delta":     f"{mean_delta * 100:+.1f}",
            "Agreement":      _agreement_badge(mean_delta),
        })

    if not summary_rows:
        st.info("No dimension has both an SME score and a matching automated score yet.")
        return

    st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)
    st.caption(
        "Delta = SME score − automated score (percentage points). Positive means the automated "
        "evaluator under-scored relative to the SME; negative means it over-scored."
    )


def _render_calibration_detail(cal_df: pd.DataFrame) -> None:
    st.subheader(f"Reviewed Items ({len(cal_df)})")

    display_cols = ["item_id", "reviewer_id", "language", "domain", "reviewed_at"]
    disp = cal_df[display_cols].copy()
    disp["reviewed_at"] = disp["reviewed_at"].str.slice(0, 19)

    event = st.dataframe(
        disp,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "item_id":     st.column_config.TextColumn("Item", width="small"),
            "reviewer_id": st.column_config.TextColumn("Reviewer"),
            "language":    st.column_config.TextColumn("Lang", width="small"),
            "domain":      st.column_config.TextColumn("Domain"),
            "reviewed_at": st.column_config.TextColumn("Reviewed At"),
        },
    )

    sel_rows = event.selection.rows if event and hasattr(event, "selection") else []
    if not sel_rows:
        st.caption("Select a row above to compare SME vs automated scores and read the SME's rationale.")
        return

    row = cal_df.iloc[sel_rows[0]]

    st.divider()
    st.markdown(f"### Calibration Detail — **{row['item_id']}** (reviewed by {row['reviewer_id']})")

    tc1, tc2 = st.columns(2)
    with tc1:
        st.markdown("**Prompt**")
        st.text_area("_p", value=row["prompt"], height=110, disabled=True, label_visibility="collapsed")
    with tc2:
        st.markdown("**Model Output**")
        st.text_area("_o", value=row["raw_output"], height=110, disabled=True, label_visibility="collapsed")

    st.markdown("**Per-Dimension Comparison**")
    comp_rows = []
    for dim in DIM_SHORT:
        sme, auto, delta = row[f"sme_{dim}"], row[f"auto_{dim}"], row[f"delta_{dim}"]
        comp_rows.append({
            "Dimension": dim.replace("_", " ").title(),
            "SME":       f"{sme * 100:.1f}" if sme is not None else "—",
            "Automated": f"{auto * 100:.1f}" if auto is not None else "—",
            "Delta":     f"{delta * 100:+.1f}" if delta is not None else "—",
            "Rationale": row[f"rationale_{dim}"] or "",
        })
    st.dataframe(
        pd.DataFrame(comp_rows),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Dimension": st.column_config.TextColumn("Dimension", width="small"),
            "SME":       st.column_config.TextColumn("SME", width="small"),
            "Automated": st.column_config.TextColumn("Automated", width="small"),
            "Delta":     st.column_config.TextColumn("Δ", width="small"),
            "Rationale": st.column_config.TextColumn("SME Rationale"),
        },
    )


# ── Operator helpers ──────────────────────────────────────────────────────────

def _launch_run(name: str, provider: str, model_id: str, pack_ids: list) -> None:
    """Create Assessment + Run rows in DB, then kick off the eval in a daemon thread."""
    import os

    from api.settings import get_settings

    # Streamlit Cloud exposes secrets via st.secrets AND as env vars, but the env-var
    # injection can lag behind st.secrets in some edge cases. Explicitly sync here so
    # the background thread's get_settings() call always sees the real values.
    _SECRET_KEYS = [
        "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_DEPLOYMENT_NAME", "AZURE_OPENAI_API_VERSION",
        "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY",
        "DATABASE_URL",
    ]
    for _k in _SECRET_KEYS:
        try:
            _v = st.secrets.get(_k)
            if _v:
                os.environ[_k] = _v
        except Exception:
            pass

    # Clear stale cache and pre-populate with current env vars in the main thread.
    get_settings.cache_clear()
    get_settings()  # populate lru_cache NOW — background thread will reuse this

    assessment_id = uuid.uuid4()
    run_id_uuid   = uuid.uuid4()

    with Session(get_engine()) as session:
        session.add(Assessment(
            id=assessment_id,
            name=name,
            model_provider=provider,
            model_identifier=model_id,
            benchmark_pack_ids=pack_ids,
            config={},
            created_at=datetime.now(UTC).replace(tzinfo=None),
        ))
        session.add(Run(
            id=run_id_uuid,
            assessment_id=assessment_id,
            status=RunStatus.PENDING,
            created_at=datetime.now(UTC).replace(tzinfo=None),
        ))
        session.commit()

    run_id_str = str(run_id_uuid)

    def _thread() -> None:
        try:
            import asyncio

            from orchestration.dispatcher import dispatch_run
            asyncio.run(dispatch_run(run_id_str))
        except Exception as exc:
            try:
                with Session(get_engine()) as s:
                    run = s.get(Run, uuid.UUID(run_id_str))
                    if run and run.status not in ("completed",):
                        run.status = RunStatus.FAILED
                        run.error_message = str(exc)
                        s.add(run)
                        s.commit()
            except Exception:
                pass

    threading.Thread(target=_thread, daemon=True).start()
    st.session_state["op_active_run_id"] = run_id_str


def _render_active_run(run_id: str) -> None:
    """Poll and display an in-progress or just-completed run. Calls st.rerun() every 5 s."""
    with Session(get_engine()) as session:
        run = session.get(Run, uuid.UUID(run_id))
        if not run:
            st.error("Run not found in the database.")
            del st.session_state["op_active_run_id"]
            return
        status    = run.status
        started   = run.started_at
        error_msg = getattr(run, "error_message", None)
        scorecard = session.exec(
            select(Scorecard).where(Scorecard.run_id == uuid.UUID(run_id))
        ).first()

    st.markdown(f"**Run ID:** `{run_id[:8]}…`")

    if status in ("pending", "running"):
        elapsed_str = ""
        if started:
            secs = (datetime.utcnow() - started).total_seconds()
            elapsed_str = f" — {int(secs // 60)}m {int(secs % 60)}s elapsed"
        st.info(f"Status: **{status.upper()}**{elapsed_str}. Polling every 5 s…")
        col_detach, _ = st.columns([1, 3])
        with col_detach:
            if st.button("Detach (run continues)", key="op_detach"):
                del st.session_state["op_active_run_id"]
                st.rerun()
        time.sleep(5)
        st.rerun()

    elif status == "completed" and scorecard:
        st.success(
            f"Complete — composite **{scorecard.composite_score:.1f} / 100** — {scorecard.verdict}"
        )
        col_view, col_new, _ = st.columns([1, 1, 2])
        with col_view:
            if st.button("View Scorecard", key="op_view_sc"):
                st.session_state["nav_view"] = "Run Scorecard"
                del st.session_state["op_active_run_id"]
                st.rerun()
        with col_new:
            if st.button("New Run", key="op_new_run"):
                del st.session_state["op_active_run_id"]
                st.rerun()

    elif status == "failed":
        st.error(f"Run failed: {error_msg or '(no details)'}")
        if st.button("Clear", key="op_clear_failed"):
            del st.session_state["op_active_run_id"]
            st.rerun()

    else:
        st.warning(f"Unexpected status: {status}")
        if st.button("Clear", key="op_clear_unk"):
            del st.session_state["op_active_run_id"]
            st.rerun()


# ── Operator views ────────────────────────────────────────────────────────────

def render_run_evaluation() -> None:
    render_console_header()
    st.subheader("Run Evaluation")
    st.caption("Configure and launch a new evaluation run against selected benchmark packs.")

    active = st.session_state.get("op_active_run_id")
    if active:
        _render_active_run(active)
        return

    # ── Pack selection ────────────────────────────────────────────────────
    st.markdown("**Select Benchmark Packs**")
    btn1, btn2 = st.columns([1, 1])
    with btn1:
        if st.button("Select All", key="op_sel_all"):
            for p in PACK_CATALOG:
                st.session_state[f"op_pack_{p['id']}"] = True
    with btn2:
        if st.button("Deselect All", key="op_desel_all"):
            for p in PACK_CATALOG:
                st.session_state[f"op_pack_{p['id']}"] = False

    selected_packs = []
    pack_cols = st.columns(2)
    for i, p in enumerate(PACK_CATALOG):
        with pack_cols[i % 2]:
            checked = st.checkbox(
                p["label"],
                value=st.session_state.get(f"op_pack_{p['id']}", False),
                key=f"op_pack_{p['id']}",
            )
            if checked:
                selected_packs.append(p["id"])

    st.divider()

    # ── Model configuration ───────────────────────────────────────────────
    st.markdown("**Model Configuration**")

    def _sync_model_id() -> None:
        prov  = st.session_state.get("op_provider", "azure_openai")
        model = PROVIDER_MODEL_DEFAULTS.get(prov, "")
        st.session_state["op_model_id"] = model
        # Clear auto-name tracking so the next render regenerates it with the new model + packs
        for _k in ("op_name", "op_name_auto", "op_name_sel_key"):
            st.session_state.pop(_k, None)

    mc1, mc2 = st.columns(2)
    with mc1:
        provider = st.selectbox(
            "Provider",
            ["azure_openai", "anthropic", "openai", "gemini"],
            format_func=lambda v: PROVIDER_SHORT.get(v, v),
            key="op_provider",
            on_change=_sync_model_id,
        )
    with mc2:
        if "op_model_id" not in st.session_state:
            st.session_state["op_model_id"] = PROVIDER_MODEL_DEFAULTS.get(provider, "gpt-4.1-mini")
        model_id = st.text_input(
            "Model Identifier",
            key="op_model_id",
        )

    st.divider()

    # Auto-name includes model + selected pack labels + a fixed timestamp.
    # op_name_auto=None means new code has never run this session — always override then.
    if "op_name_ts" not in st.session_state:
        st.session_state["op_name_ts"] = datetime.now(UTC).strftime("%Y-%m-%d %H:%M")
    _ts       = st.session_state["op_name_ts"]
    _pack_str = " + ".join(p["label"] for p in PACK_CATALOG if p["id"] in selected_packs) \
                or "(no packs)"
    _auto     = f"{model_id} — {_pack_str} — {_ts} UTC"
    _sel_key  = f"{model_id}|{','.join(sorted(selected_packs))}"
    if _sel_key != st.session_state.get("op_name_sel_key"):
        _prev_auto = st.session_state.get("op_name_auto")  # None = first run of new code
        if _prev_auto is None or st.session_state.get("op_name", "") in ("", _prev_auto):
            st.session_state["op_name"] = _auto
        st.session_state["op_name_auto"]    = _auto
        st.session_state["op_name_sel_key"] = _sel_key
    if "op_name" not in st.session_state:
        st.session_state["op_name"] = _auto
    assessment_name = st.text_input("Assessment Name", key="op_name")

    st.divider()

    can_launch = len(selected_packs) > 0 and bool(model_id.strip())
    if not selected_packs:
        st.caption("Select at least one pack to enable Launch.")

    if st.button("🚀 Launch Run", type="primary", disabled=not can_launch, key="op_launch"):
        _launch_run(assessment_name, provider, model_id, selected_packs)
        st.rerun()


def render_pack_management() -> None:
    render_console_header()
    st.subheader("Pack Management")
    st.caption("Seed JSONL benchmark packs into the Supabase database. Idempotent — safe to re-run.")

    with st.spinner("Checking DB…"):
        seeded = load_seeded_pack_ids()

    rows = []
    for p in PACK_CATALOG:
        rows.append({
            "Pack":     p["label"],
            "Language": LANGUAGE_NAMES.get(p["language"], p["language"]),
            "Status":   "✅ Seeded" if p["id"] in seeded else "⬜ Not seeded",
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    unseeded = [p["id"] for p in PACK_CATALOG if p["id"] not in seeded]
    if not unseeded:
        st.success("All 12 packs are in the database.")
        return

    st.warning(f"{len(unseeded)} pack(s) not yet seeded.")
    if st.button("Seed All Packs", type="primary", key="op_seed"):
        with st.spinner("Seeding packs — this takes ~10 s…"):
            result = subprocess.run(
                [sys.executable, "scripts/seed_packs_to_db.py"],
                cwd=str(PROJECT_ROOT),
                capture_output=True,
                text=True,
                timeout=120,
            )
        if result.returncode == 0:
            st.cache_data.clear()
            st.success("Seeding complete.")
            with st.expander("Script output"):
                st.text(result.stdout or "(no output)")
        else:
            st.error("Seeding failed.")
            st.text(result.stderr)
        st.rerun()


def render_hitl_management() -> None:
    render_console_header()
    st.subheader("HITL Management")
    st.caption(
        "Export model responses to Label Studio for SME annotation, "
        "then import completed reviews back into the database."
    )

    with Session(get_engine()) as session:
        all_responses  = session.exec(select(ModelResponse)).all()
        reviewed_ids   = {r.response_id for r in session.exec(select(ResponseReview)).all()}
        total          = len(all_responses)
        reviewed       = sum(1 for r in all_responses if r.id in reviewed_ids)

    mc1, mc2, mc3 = st.columns(3)
    mc1.metric("Total Responses", total)
    mc2.metric("Reviewed", reviewed)
    mc3.metric("Awaiting Review", total - reviewed)

    st.divider()

    st.markdown("### Export to Label Studio")
    st.caption("Pushes unreviewed ModelResponse rows into the Label Studio annotation project.")
    if st.button("📤 Export to Label Studio", type="primary", key="op_export"):
        with st.spinner("Exporting…"):
            result = subprocess.run(
                [sys.executable, "scripts/hitl_export_tasks.py"],
                cwd=str(PROJECT_ROOT),
                capture_output=True,
                text=True,
                timeout=600,
            )
        if result.returncode == 0:
            st.success("Export complete.")
            with st.expander("Script output"):
                st.text(result.stdout or "(no output)")
        else:
            st.error("Export failed.")
            st.text(result.stderr)

    st.divider()

    st.markdown("### Import from Label Studio")
    st.caption("Pulls completed annotations from Label Studio and saves them as ResponseReview rows.")
    if st.button("📥 Import Reviews", type="primary", key="op_import"):
        with st.spinner("Importing…"):
            result = subprocess.run(
                [sys.executable, "scripts/hitl_import_reviews.py"],
                cwd=str(PROJECT_ROOT),
                capture_output=True,
                text=True,
                timeout=120,
            )
        if result.returncode == 0:
            st.cache_data.clear()
            st.success("Import complete.")
            with st.expander("Script output"):
                st.text(result.stdout or "(no output)")
        else:
            st.error("Import failed.")
            st.text(result.stderr)


def render_calibration_view() -> None:
    render_console_header()
    st.subheader("SME Calibration")
    st.caption(
        "Compares SME ResponseReview scores (Label Studio HITL pipeline) against the automated "
        "MetricResult scores for the same model responses — cross-run, since calibration is a "
        "question about the metrics themselves."
    )

    with st.spinner("Loading SME reviews…"):
        cal_df = load_calibration_data()

    if cal_df.empty:
        st.info(
            "No SME reviews found yet. Export tasks with `scripts/hitl_export_tasks.py`, annotate in "
            "Label Studio, then pull them in with `scripts/hitl_import_reviews.py`."
        )
        return

    _render_calibration_summary(cal_df)
    st.divider()
    _render_calibration_detail(cal_df)


def _pack_display(pack_ids: list[str]) -> tuple[str, str | None]:
    """Return (metric_value, help_text_or_None) for the Packs KPI card."""
    if not pack_ids:
        return "—", None

    labels = [_PACK_META.get(pid, pid) for pid in pack_ids]
    langs, domains = [], []
    for lbl in labels:
        if " (" in lbl:
            dom, lang_part = lbl.rsplit(" (", 1)
            langs.append(lang_part.rstrip(")"))
            domains.append(dom)
        else:
            langs.append(lbl)
            domains.append(lbl)

    ul = list(dict.fromkeys(langs))   # unique, order-preserving
    ud = sorted(set(domains))

    if len(pack_ids) == 1:
        # "Language · Domain" — language first, no parens
        value = f"{ul[0]} · {ud[0]}"
        return value, None

    # Multiple packs: show up to 4 language names then "+N more"
    shown = ul[:4]
    rest  = len(ul) - len(shown)
    value = ", ".join(shown) + (f" +{rest}" if rest else "")
    lang_list   = "\n".join(f"- {lang}" for lang in ul)
    domain_list = "\n".join(f"- {d}" for d in ud)
    help_text   = f"**Languages:**\n{lang_list}\n\n**Domains:**\n{domain_list}"
    return value, help_text


# ── Main ──────────────────────────────────────────────────────────────────────

def _set_runs_archived(run_ids: list[str], archived: bool) -> int:
    """Bulk-toggle the archived flag on the given runs, then refresh the cached
    run lists so the change shows immediately. Admin-only — callers gate on
    can_archive_runs(). Returns the number of runs updated."""
    import uuid as _uuid

    if not run_ids:
        return 0
    updated = 0
    engine = get_engine()
    with Session(engine) as session:
        for rid in run_ids:
            run = session.get(Run, _uuid.UUID(rid))
            if run is not None and run.archived != archived:
                run.archived = archived
                session.add(run)
                updated += 1
        session.commit()
    load_runs_summary.clear()
    load_provider_comparison.clear()
    return updated


def _archive_all_completed_runs() -> int:
    """Archive every non-archived run that has a scorecard — a one-click way to
    clear the Evaluation Runs list (not limited to the 50 currently loaded).

    Fully reversible: tick 'Show archived runs' + Unarchive to bring any back.
    Runs still in progress (no scorecard yet) are left untouched.
    """
    engine = get_engine()
    with Session(engine) as session:
        scored_ids = set(session.exec(select(Scorecard.run_id)).all())
        rows = session.exec(select(Run).where(Run.archived == False)).all()  # noqa: E712
        updated = 0
        for run in rows:
            if run.id in scored_ids:
                run.archived = True
                session.add(run)
                updated += 1
        session.commit()
    load_runs_summary.clear()
    load_provider_comparison.clear()
    return updated


def render_run_scorecard() -> None:
    render_console_header()

    # Sidebar: run selector
    with st.sidebar:
        st.header("Evaluation Runs")

        auth_user   = st.session_state.get("auth_user")
        unlocked    = st.session_state.get("operator_unlocked", False)
        may_archive = can_archive_runs(auth_user, unlocked)

        show_archived = st.checkbox("Show archived runs", value=False, key="op_show_archived")
        all_runs  = load_runs_summary(include_archived=show_archived)
        completed = [r for r in all_runs if r["has_scorecard"]]
        if not completed:
            st.warning("No completed runs with scorecards found.")
            return

        labels = [
            ("🗄 " + r["label"]) if r.get("archived") else r["label"]
            for r in completed
        ]
        idx = st.selectbox(
            "Select run",
            range(len(labels)),
            format_func=lambda i: labels[i],
            label_visibility="collapsed",
        )
        selected = completed[idx]

        # Admin-only: bulk archive / unarchive to curate which runs appear in
        # the console. Collapsed by default so it never distracts from viewing.
        if may_archive:
            with st.expander("🗄 Manage runs (archive / unarchive)", expanded=False):
                label_by_id = {
                    r["run_id"]: (("🗄 " + r["label"]) if r.get("archived") else r["label"])
                    for r in completed
                }
                picked = st.multiselect(
                    "Select runs to archive or unarchive",
                    options=list(label_by_id.keys()),
                    format_func=lambda rid: label_by_id.get(rid, rid),
                    key="op_manage_runs",
                    help="Tip: tick 'Show archived runs' above to reveal archived "
                         "runs (🗄) so you can unarchive them.",
                )
                bc1, bc2 = st.columns(2)
                with bc1:
                    if st.button("🗄 Archive selected", key="op_bulk_archive",
                                 use_container_width=True, disabled=not picked):
                        n = _set_runs_archived(picked, True)
                        st.toast(f"Archived {n} run(s).")
                        st.rerun()
                with bc2:
                    if st.button("♻ Unarchive selected", key="op_bulk_unarchive",
                                 use_container_width=True, disabled=not picked):
                        n = _set_runs_archived(picked, False)
                        st.toast(f"Unarchived {n} run(s).")
                        st.rerun()

        # ── Clear the list: one-click archive-all, pinned at the sidebar bottom ──
        if may_archive:
            st.divider()
            confirm_all = st.checkbox(
                "Confirm — archive every run in the list",
                key="op_archive_all_confirm",
                help="Clears the Evaluation Runs list by archiving all listed runs "
                     "(every run with a scorecard). Nothing is deleted — tick "
                     "'Show archived runs' above and use Unarchive to bring any back.",
            )
            if st.button("🗄 Archive all runs (clear list)", key="op_archive_all",
                         type="primary", use_container_width=True,
                         disabled=not confirm_all):
                n = _archive_all_completed_runs()
                st.toast(f"Archived {n} run(s) — list cleared.")
                st.rerun()

    run_id = selected["run_id"]

    # Scorecard header metrics
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Composite Score", f"{selected['composite_score']:.1f} / 100")
    c2.metric("Verdict", _verdict_badge(selected["verdict"]))
    c3.metric("Confidence", selected["confidence_flag"])
    c4.metric("Model", selected["model"])
    _pack_val, _pack_help = _pack_display(selected["pack_ids"])
    c5.metric("Language & Domain", _pack_val, help=_pack_help)

    if selected.get("safety_unverified"):
        st.warning("⚠ Safety Not Verified — no applicable safety items in this run; the verdict cannot certify Deployment-Ready.")

    if selected.get("african_fabrication_detected"):
        st.warning("⚠ African Fabrication Detected — a response invented an Africa-specific "
                   "entity on at least one item. Review the flagged items before deploying.")

    pdf_bytes = _scorecard_pdf_bytes(run_id)
    if pdf_bytes:
        st.download_button(
            "Download Scorecard PDF",
            data=pdf_bytes,
            file_name=f"afroeval_scorecard_{run_id[:8]}.pdf",
            mime="application/pdf",
            key="op_download_pdf",
        )
    else:
        st.caption("Scorecard data not found for this run.")

    st.divider()

    # Dimension scores
    st.subheader("Dimension Scores")
    dim_scores  = selected["dimension_scores"]
    dim_weights = selected["dimension_weights"]
    dcols = st.columns(3)
    # Show evaluated dims sorted by score, then not-evaluated dims as N/A
    all_display_dims = sorted(dim_scores.items(), key=lambda x: x[1])
    not_eval_dims = [d for d in dim_weights if d not in dim_scores]
    col_idx = 0
    for dim, score in all_display_dims:
        weight = dim_weights.get(dim, 0)
        with dcols[col_idx % 3]:
            st.metric(
                label=f"{dim.replace('_', ' ').title()} ({weight:.0%})",
                value=f"{score:.1f}",
                delta="⚠ Below 60" if score < 60 else "OK",
                delta_color="inverse" if score < 60 else "normal",
            )
        col_idx += 1
    for dim in not_eval_dims:
        weight = dim_weights.get(dim, 0)
        with dcols[col_idx % 3]:
            st.metric(
                label=f"{dim.replace('_', ' ').title()} ({weight:.0%})",
                value="N/A",
                delta="Not evaluated — no applicable items",
                delta_color="off",
            )
        col_idx += 1

    st.divider()

    # Per-item table
    st.subheader("Item Drill-Down")
    with st.spinner("Loading items…"):
        df, metrics_by_resp = load_run_items(run_id)

    if df.empty:
        st.info("No item data — ModelResponse rows may not have been persisted for this run.")
        return

    # Filters
    fc1, fc2, fc3 = st.columns(3)
    with fc1:
        lang_opts = ["All"] + sorted(df["language"].dropna().unique().tolist())
        lang_sel  = st.selectbox("Language", lang_opts)
    with fc2:
        dom_opts  = ["All"] + sorted(df["domain"].dropna().unique().tolist())
        dom_sel   = st.selectbox("Domain", dom_opts)
    with fc3:
        flag_sel  = st.selectbox("Show", [
            "All items",
            "Filter-blocked only",
            "Gold items",
            "Low-score items (any dim < 60)",
        ])

    fdf = df.copy()
    if lang_sel != "All":
        fdf = fdf[fdf["language"] == lang_sel]
    if dom_sel != "All":
        fdf = fdf[fdf["domain"] == dom_sel]
    if flag_sel == "Filter-blocked only":
        fdf = fdf[fdf["is_filtered"]]
    elif flag_sel == "Gold items":
        fdf = fdf[fdf["is_gold"]]
    elif flag_sel == "Low-score items (any dim < 60)":
        avail = [s for s in DIM_SHORT.values() if s in fdf.columns]
        if avail:
            fdf = fdf[fdf[avail].min(axis=1, skipna=True) < 60]

    # Build display df (no complex-type columns)
    display_cols = ["item_id", "language", "domain", "is_gold", "is_filtered"] + list(DIM_SHORT.values()) + ["latency_ms"]
    disp = fdf[[c for c in display_cols if c in fdf.columns]].copy()
    disp["is_filtered"] = disp["is_filtered"].map({True: "⚠ BLOCKED", False: ""})
    disp["is_gold"]     = disp["is_gold"].map({True: "★", False: ""})

    col_cfg: dict = {
        "item_id":     st.column_config.TextColumn("Item", width="small"),
        "language":    st.column_config.TextColumn("Lang", width="small"),
        "domain":      st.column_config.TextColumn("Domain"),
        "is_gold":     st.column_config.TextColumn("Gold", width="small"),
        "is_filtered": st.column_config.TextColumn("Filter", width="small"),
        "latency_ms":  st.column_config.NumberColumn("ms", width="small", format="%d"),
    }
    for short in DIM_SHORT.values():
        col_cfg[short] = st.column_config.ProgressColumn(short, min_value=0, max_value=100, format="%.1f")

    event = st.dataframe(
        disp,
        column_config=col_cfg,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
    )

    sel_rows = event.selection.rows if event and hasattr(event, "selection") else []

    if not sel_rows:
        st.caption("Select a row above to see full item detail.")
        _render_remediation(selected["remediation_roadmap"])
        return

    # Item detail
    row     = fdf.iloc[sel_rows[0]]
    resp_id = row["response_id"]

    st.divider()
    badges = []
    if row["is_filtered"]:
        badges.append("🔴 CONTENT FILTER BLOCK — likely false positive for African-language content")
    if row["is_gold"]:
        badges.append("⭐ Gold calibration item")
    st.markdown("### Item Detail — **{}**{}".format(
        row["item_id"],
        "  —  " + "  |  ".join(badges) if badges else "",
    ))

    tc1, tc2 = st.columns(2)
    with tc1:
        st.markdown("**Prompt**")
        st.text_area("_p", value=row["prompt"], height=130, disabled=True, label_visibility="collapsed")
        st.markdown("**Expected Behavior**")
        st.text_area("_e", value=row["expected_behavior"], height=130, disabled=True, label_visibility="collapsed")
    with tc2:
        st.markdown("**Model Output**")
        st.text_area("_o", value=row["raw_output"], height=280, disabled=True, label_visibility="collapsed")
        meta = [f"Language: {row['language']}", f"Domain: {row['domain']}"]
        if row.get("latency_ms"):
            meta.append(f"Latency: {row['latency_ms']}ms")
        if row.get("tokens_used"):
            meta.append(f"Tokens: {row['tokens_used']}")
        st.caption("  |  ".join(meta))

    st.markdown("**Metric Results**")
    item_metrics = metrics_by_resp.get(resp_id, [])
    if item_metrics:
        mdf = pd.DataFrame(item_metrics)[["dimension", "metric_name", "score", "passed", "reason"]]
        mdf = mdf.sort_values("dimension").reset_index(drop=True)
        mdf["score"]  = mdf["score"].map(lambda x: f"{x * 100:.1f}")
        mdf["passed"] = mdf["passed"].map({True: "✓", False: "✗"})
        st.dataframe(
            mdf,
            use_container_width=True,
            hide_index=True,
            column_config={
                "dimension":   st.column_config.TextColumn("Dimension"),
                "metric_name": st.column_config.TextColumn("Metric"),
                "score":       st.column_config.TextColumn("Score", width="small"),
                "passed":      st.column_config.TextColumn("Pass", width="small"),
                "reason":      st.column_config.TextColumn("Reason"),
            },
        )
    else:
        st.info("No MetricResult rows found for this item.")

    _render_remediation(selected["remediation_roadmap"])


def render_provider_comparison() -> None:
    render_console_header()
    st.subheader("Provider Comparison")
    st.caption(
        "Side-by-side scorecard results across model providers running the same benchmark packs. "
        "Validates routing decisions — e.g., whether Anthropic outperforms Azure on Oromo/Somali content."
    )

    with st.spinner("Loading scorecards…"):
        all_rows = load_provider_comparison()

    if not all_rows:
        st.info("No completed scorecards found. Run evaluations first.")
        return

    by_packs: dict[str, list[dict]] = defaultdict(list)
    for row in all_rows:
        by_packs[row["pack_label"]].append(row)

    pack_options = sorted(by_packs.keys())
    selected_label = st.selectbox(
        "Benchmark Pack Combination",
        pack_options,
        help="Select which pack(s) to compare across providers",
    )

    group = by_packs[selected_label]

    # Latest completed run per provider (list is newest-first from query)
    latest: dict[str, dict] = {}
    for row in group:
        if row["model_provider"] not in latest:
            latest[row["model_provider"]] = row

    providers = sorted(latest.keys())

    if len(providers) < 2:
        st.warning(
            f"Only **{_provider_short(providers[0])}** has run against these packs. "
            "Run the same packs with a second provider to enable comparison."
        )
        row = latest[providers[0]]
        st.metric(row["model_identifier"], f"{row['composite_score']:.1f} / 100")
        st.caption(_verdict_badge(row["verdict"]))
        return

    # ── Composite score header ──────────────────────────────────────────
    st.subheader("Composite Scores")
    hcols = st.columns(len(providers) + (1 if len(providers) == 2 else 0))
    scores: dict[str, float] = {}

    for i, prov in enumerate(providers):
        row = latest[prov]
        scores[prov] = row["composite_score"]
        with hcols[i]:
            st.metric(
                label=f"{_provider_short(prov)} — {row['model_identifier']}",
                value=f"{row['composite_score']:.1f} / 100",
                help=f"Run: {row['run_id'][:8]}… | Completed: {row['completed_at']} | Confidence: {row['confidence_flag']}",
            )
            st.caption(_verdict_badge(row["verdict"]))

    if len(providers) == 2:
        p0, p1 = providers[0], providers[1]
        delta = scores[p1] - scores[p0]
        sign = "+" if delta >= 0 else ""
        with hcols[-1]:
            st.metric(
                label=f"Δ ({_provider_short(p1)} − {_provider_short(p0)})",
                value=f"{sign}{delta:.1f}",
                delta=f"{sign}{delta:.1f}",
                delta_color="normal" if delta >= 0 else "inverse",
            )

    st.divider()

    # ── Dimension breakdown table ───────────────────────────────────────
    st.subheader("Dimension Breakdown")

    all_dims: set[str] = set()
    for row in latest.values():
        all_dims.update(row["dimension_scores"].keys())

    ref_weights = latest[providers[0]]["dimension_weights"]
    dims_sorted = sorted(all_dims, key=lambda d: ref_weights.get(d, 0), reverse=True)

    table_rows = []
    for dim in dims_sorted:
        weight = ref_weights.get(dim, 0)
        r: dict = {"Dimension": f"{dim.replace('_', ' ').title()} ({weight:.0%})"}
        dim_scores: list[tuple[str, float]] = []
        for prov in providers:
            score = latest[prov]["dimension_scores"].get(dim)
            r[_provider_short(prov)] = f"{score:.1f}" if score is not None else "—"
            if score is not None:
                dim_scores.append((prov, score))
        if len(dim_scores) == 2:
            d = dim_scores[1][1] - dim_scores[0][1]
            sign = "+" if d >= 0 else ""
            r["Δ"] = f"{sign}{d:.1f}"
        else:
            r["Δ"] = "—"
        table_rows.append(r)

    col_cfg: dict = {"Dimension": st.column_config.TextColumn("Dimension"), "Δ": st.column_config.TextColumn("Δ", width="small")}
    for prov in providers:
        col_cfg[_provider_short(prov)] = st.column_config.TextColumn(_provider_short(prov), width="small")

    st.dataframe(
        pd.DataFrame(table_rows),
        use_container_width=True,
        hide_index=True,
        column_config=col_cfg,
    )

    # ── Interpretation ──────────────────────────────────────────────────
    if len(providers) == 2:
        st.divider()
        st.subheader("Interpretation")
        _render_comparison_insight(latest[providers[0]], latest[providers[1]], dims_sorted)

    st.divider()

    # ── Run history ─────────────────────────────────────────────────────
    with st.expander(f"All runs against these packs ({len(group)} total)"):
        hist_rows = [{
            "Provider": _provider_short(r["model_provider"]),
            "Model":    r["model_identifier"],
            "Score":    f"{r['composite_score']:.1f}",
            "Verdict":  _verdict_badge(r["verdict"]),
            "Completed": r["completed_at"],
            "Run ID":   r["run_id"][:8] + "…",
        } for r in group]
        st.dataframe(pd.DataFrame(hist_rows), use_container_width=True, hide_index=True)


def render_language_breakdown() -> None:
    render_console_header()
    st.subheader("Language Comparison")
    st.caption(
        "Per-language aggregate scores across evaluation runs. English (US) is the "
        "high-resource baseline — the gap between EN and African language scores "
        "quantifies the equity deficit each model needs to close."
    )

    all_rows = load_provider_comparison()
    if not all_rows:
        st.info("No completed scorecards found. Run evaluations first.")
        return

    # ── Build model → all run ids map (most-recent first) ──────────────────
    model_run_ids: dict[str, list[str]] = {}
    for r in sorted(all_rows, key=lambda x: x["completed_at"], reverse=True):
        mid = r["model_identifier"]
        if mid not in model_run_ids:
            model_run_ids[mid] = []
        model_run_ids[mid].append(r["run_id"])

    model_ids = list(model_run_ids.keys())
    if not model_ids:
        st.info("No completed runs found.")
        return

    # ── Model pickers ──────────────────────────────────────────────────────
    col_a, col_b = st.columns(2)
    with col_a:
        model_a = st.selectbox("Model A", model_ids, index=0, key="lc_model_a")
    with col_b:
        b_opts = ["(none)"] + model_ids
        default_b_idx = 1 if len(model_ids) > 1 else 0
        sel_b = st.selectbox("Model B (optional)", b_opts, index=default_b_idx, key="lc_model_b")

    model_b    = sel_b if sel_b != "(none)" and sel_b != model_a else None
    two_models = model_b is not None
    run_ids_a  = tuple(model_run_ids[model_a])
    run_ids_b  = tuple(model_run_ids[model_b]) if two_models else run_ids_a
    run_id_a   = run_ids_a[0]   # most-recent run — used as DataFrame lookup key
    run_id_b   = run_ids_b[0]

    with st.spinner("Aggregating per-language scores…"):
        df = load_language_breakdown(run_ids_a, run_ids_b)

    if df.empty:
        st.info("No item-level data found for these models.")
        return

    langs = sorted(df["language"].unique(), key=lambda lang: (lang != "en", lang))

    def _get(lang: str, run_id: str, col: str):
        sub = df[(df["language"] == lang) & (df["run_id"] == run_id)]
        if sub.empty:
            return None
        val = sub[col].values[0]
        return float(val) if val is not None else None

    # ── Table 1: Composite Score by Language × Model ───────────────────────
    st.subheader("Composite Score by Language")
    st.caption(
        "Δ vs EN = language composite minus English (US) composite for the same model. "
        "Negative values indicate an equity deficit."
    )

    en_comp_a = _get("en", run_id_a, "composite")
    en_comp_b = _get("en", run_id_b, "composite") if two_models else None

    t1_rows = []
    for lang in langs:
        comp_a = _get(lang, run_id_a, "composite")
        comp_b = _get(lang, run_id_b, "composite") if two_models else None
        item_a = int(_get(lang, run_id_a, "item_count") or 0)
        item_b = int(_get(lang, run_id_b, "item_count") or 0) if two_models else None

        delta_a_en = (
            round(comp_a - en_comp_a, 1)
            if lang != "en" and comp_a is not None and en_comp_a is not None
            else float("nan")
        )
        delta_b_en = (
            round(comp_b - en_comp_b, 1)
            if two_models and lang != "en" and comp_b is not None and en_comp_b is not None
            else float("nan")
        )
        delta_ab = (
            round(comp_b - comp_a, 1)
            if two_models and comp_a is not None and comp_b is not None
            else float("nan")
        )

        lang_label = (
            f"⭐ {LANGUAGE_NAMES.get(lang, lang)} (EN baseline)"
            if lang == "en"
            else LANGUAGE_NAMES.get(lang, lang)
        )
        row: dict = {
            "Language":    lang_label,
            model_a:       comp_a if comp_a is not None else float("nan"),
            "Δ vs EN (A)": delta_a_en,
        }
        if two_models:
            row[model_b]         = comp_b if comp_b is not None else float("nan")
            row["Δ vs EN (B)"]   = delta_b_en
            row["Δ (B−A)"]       = delta_ab
        row["Items"] = f"{item_a}" if not two_models else f"{item_a} / {item_b}"
        t1_rows.append(row)

    t1_df = pd.DataFrame(t1_rows)

    # Color-code delta columns: red < -10, amber < 0, green > 0
    delta_cols = ["Δ vs EN (A)"] + (["Δ vs EN (B)", "Δ (B−A)"] if two_models else [])
    delta_cols = [c for c in delta_cols if c in t1_df.columns]

    def _color_delta(v):
        if pd.isna(v):
            return ""
        if v < -10:
            return "color: #EF4444; font-weight: 600"
        if v < 0:
            return "color: #F59E0B; font-weight: 600"
        if v > 0:
            return "color: #10B981; font-weight: 600"
        return "color: #6B7280"

    def score_fmt(v):
        return "—" if pd.isna(v) else f"{v:.1f}"

    def delta_fmt(v):
        return "—" if pd.isna(v) else (f"+{v:.1f}" if v > 0 else f"{v:.1f}")

    fmt: dict = {c: score_fmt for c in [model_a] + ([model_b] if two_models else []) if c in t1_df.columns}
    fmt.update({c: delta_fmt for c in delta_cols})

    styled_t1 = t1_df.style.map(_color_delta, subset=delta_cols).format(fmt, na_rep="—")
    st.dataframe(styled_t1, use_container_width=True, hide_index=True)

    # ── EN Baseline Gap metrics ────────────────────────────────────────────
    african_langs = [lang for lang in langs if lang != "en"]
    if en_comp_a is not None and african_langs:
        gaps_a = []
        for lang in african_langs:
            g = _get(lang, run_id_a, "composite")
            if g is not None:
                gaps_a.append(en_comp_a - g)
        avg_gap_a = round(sum(gaps_a) / len(gaps_a), 1) if gaps_a else None

        avg_gap_b = None
        if two_models and en_comp_b is not None:
            gaps_b = []
            for lang in african_langs:
                g = _get(lang, run_id_b, "composite")
                if g is not None:
                    gaps_b.append(en_comp_b - g)
            avg_gap_b = round(sum(gaps_b) / len(gaps_b), 1) if gaps_b else None

        st.divider()
        st.subheader("EN Baseline Gap")
        st.caption(
            "Points by which English score exceeds the mean African-language score for the same model. "
            "A larger gap signals greater language-equity risk."
        )
        gc1, gc2 = st.columns(2)
        with gc1:
            st.metric(model_a, f"{avg_gap_a:+.1f} pts" if avg_gap_a is not None else "—")
        with gc2:
            if two_models:
                st.metric(model_b, f"{avg_gap_b:+.1f} pts" if avg_gap_b is not None else "—")

    # ── Table 2: Dimension × Language pivot ────────────────────────────────
    st.divider()
    st.subheader("Dimension × Language Comparison")
    st.caption(
        "Rows = evaluation dimensions. Columns = each language found in the selected runs. "
        "Gap = language score minus English baseline (negative = equity deficit)."
    )

    seen_pairs: set[tuple[str, str]] = set()
    lang_cols: list[tuple[str, str, str]] = []  # (display_label, lang_code, run_id)
    for _lang in langs:
        for _rid in [run_id_a, run_id_b]:
            if (_lang, _rid) in seen_pairs:
                continue
            _sub = df[(df["language"] == _lang) & (df["run_id"] == _rid)]
            if _sub.empty:
                continue
            seen_pairs.add((_lang, _rid))
            _model = _sub["model"].values[0]
            _label = f"{LANGUAGE_NAMES.get(_lang, _lang)} ({_model})"
            lang_cols.append((_label, _lang, _rid))

    en_col = next(((lbl, lc, rid) for lbl, lc, rid in lang_cols if lc == "en"), None)

    def _score(lang_code: str, run_id: str, col: str) -> float | None:
        sub = df[(df["language"] == lang_code) & (df["run_id"] == run_id)]
        if sub.empty:
            return None
        val = sub[col].values[0]
        return float(val) if val is not None else None

    t2_rows = []

    comp_row: dict = {"Dimension": "Composite", "Weight": "—"}
    en_comp = _score(en_col[1], en_col[2], "composite") if en_col else None
    for lbl, lc, rid in lang_cols:
        v = _score(lc, rid, "composite")
        comp_row[lbl] = f"{v:.1f}" if v is not None else "—"
    if en_col:
        for lbl, lc, rid in lang_cols:
            if lc == "en":
                continue
            v = _score(lc, rid, "composite")
            gap = round(v - en_comp, 1) if v is not None and en_comp is not None else None
            sign = "+" if gap is not None and gap >= 0 else ""
            comp_row["Gap vs EN"] = f"{sign}{gap:.1f}" if gap is not None else "—"
    t2_rows.append(comp_row)

    for dim, short in DIM_SHORT.items():
        row: dict = {"Dimension": DIM_LABELS[dim], "Weight": DIM_WEIGHTS[dim]}
        en_val = _score(en_col[1], en_col[2], short) if en_col else None
        for lbl, lc, rid in lang_cols:
            v = _score(lc, rid, short)
            row[lbl] = f"{v:.1f}" if v is not None else "—"
        if en_col:
            for lbl, lc, rid in lang_cols:
                if lc == "en":
                    continue
                v = _score(lc, rid, short)
                gap = round(v - en_val, 1) if v is not None and en_val is not None else None
                sign = "+" if gap is not None and gap >= 0 else ""
                row["Gap vs EN"] = f"{sign}{gap:.1f}" if gap is not None else "—"
        t2_rows.append(row)

    col_cfg: dict = {
        "Dimension": st.column_config.TextColumn("Dimension", width="medium"),
        "Weight":    st.column_config.TextColumn("Weight", width="small"),
    }
    for lbl, _, _ in lang_cols:
        col_cfg[lbl] = st.column_config.TextColumn(lbl, width="small")
    if en_col and any(lc != "en" for _, lc, _ in lang_cols):
        col_cfg["Gap vs EN"] = st.column_config.TextColumn("Gap vs EN", width="small")

    st.dataframe(
        pd.DataFrame(t2_rows),
        use_container_width=True,
        hide_index=True,
        column_config=col_cfg,
    )


def main() -> None:
    with st.sidebar:
        st.markdown(
            '<div style="height:3px;background:linear-gradient(90deg,#7C3AED 0%,#4169E1 50%,#00CFFF 100%);'
            'margin:-1rem -1rem 0.75rem -1rem;"></div>',
            unsafe_allow_html=True,
        )
        st.header("View")

        auth_user: AuthUser | None = st.session_state.get("auth_user")
        unlocked = st.session_state.get("operator_unlocked", False)
        all_views = resolve_views(auth_user, unlocked)

        if all_views:
            # nav_view is managed as plain session state (not a widget key) so it can
            # be set from button callbacks without triggering StreamlitAPIException.
            if st.session_state.get("nav_view") not in all_views:
                st.session_state["nav_view"] = all_views[0]
            _nav_idx = all_views.index(st.session_state["nav_view"])
            selected = st.radio("View", all_views, label_visibility="collapsed", index=_nav_idx)
            st.session_state["nav_view"] = selected
            view = selected
        else:
            st.caption("Log in to view the console.")
            view = None

        if st.button("🔄 Refresh", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

        st.divider()

        if auth_user is not None:
            role_label = auth_user.role or "viewer"
            st.success(f"🔓 Logged in as {auth_user.email} ({role_label})")
            if st.button("Log out", key="auth_logout", use_container_width=True):
                st.session_state.pop("auth_user", None)
                st.rerun()
        else:
            st.caption("🔐 LOG IN")
            login_email = st.text_input(
                "login_email", placeholder="Email",
                label_visibility="collapsed", key="login_email_input",
            )
            login_pwd = st.text_input(
                "login_pwd", type="password", placeholder="Password",
                label_visibility="collapsed", key="login_pwd_input",
            )
            if st.button("Log in", key="login_submit", use_container_width=True):
                if login_email and login_pwd:
                    try:
                        user = SupabaseAuthClient().sign_in(login_email, login_pwd)
                        st.session_state["auth_user"] = user
                        st.rerun()
                    except InvalidCredentialsError:
                        st.error("Invalid email or password")
                    except AuthServiceUnavailableError:
                        st.error("Login service unavailable, try again")
                else:
                    st.error("Enter both email and password")

        with st.expander("Admin override"):
            if not unlocked:
                pwd = st.text_input(
                    "operator_pwd", type="password",
                    placeholder="Enter operator password",
                    label_visibility="collapsed",
                    key="op_pwd_input",
                )
                if pwd:
                    from api.settings import get_settings
                    correct = get_settings().operator_password
                    if correct and pwd == correct:
                        st.session_state["operator_unlocked"] = True
                        st.rerun()
                    else:
                        st.error("Incorrect password")
            else:
                st.success("🔓 Operator override active")
                if st.button("🔒 Lock override", key="op_lock", use_container_width=True):
                    st.session_state["operator_unlocked"] = False
                    st.session_state.pop("op_active_run_id", None)
                    st.rerun()

    if view is None:
        render_console_header()
        st.info("🔐 This console is restricted. Log in, or use the admin override, in the sidebar to continue.")
    elif view == "Provider Comparison":
        render_provider_comparison()
    elif view == "Language Comparison":
        render_language_breakdown()
    elif view == "SME Calibration":
        render_calibration_view()
    elif view == "Run Evaluation":
        render_run_evaluation()
    elif view == "Pack Management":
        render_pack_management()
    elif view == "HITL Management":
        render_hitl_management()
    else:
        render_run_scorecard()


if __name__ == "__main__":
    main()
