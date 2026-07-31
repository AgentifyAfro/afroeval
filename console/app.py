"""
AfroEval Scorecard™ Console

Per-run scorecard summary + per-item drill-down into ModelResponse and MetricResult data.
Reads directly from the DB — no HTTP server required.

Run:
    streamlit run console/app.py
"""

import json
import os
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
from console.access import CATEGORY_2_VIEWS, can_archive_runs, resolve_views
from console.branding import (
    inject_brand_css,
    render_callout,
    render_comparison_bars,
    render_data_table,
    render_detail_placeholder,
    render_dimension_cards,
    render_item_detail,
    render_kpi_row,
    render_scorecard_header,
    render_section_divider,
    render_section_header,
)
from console.theme import ERROR, SUCCESS, WARNING
from db.models import (
    EVALUATED_PROVIDERS,
    Assessment,
    BenchmarkItem,
    BenchmarkPack,
    ItemValidation,
    MetricResult,
    ModelResponse,
    ResponseReview,
    Run,
    RunStatus,
    Scorecard,
)
from db.session import get_engine
from hitl.label_config import AUTHORING_PROJECT_TITLE
from scoring.aggregate import composite_from_metric_means

# ── Constants ─────────────────────────────────────────────────────────────────

DIM_SHORT = {
    "language_performance":     "LP",
    "cultural_appropriateness": "CA",
    "hallucination_risk":       "HR",
    "bias_fairness":            "BF",
    "code_switching_quality":   "CS",
    "safety_robustness":        "SR",
}

# Metrics that are computed but NOT counted toward any dimension score (excluded from the
# composite in scoring.aggregate). They only add noise to the item drill-down — multilingual_
# similarity even shows a red FAIL when sentence_transformers isn't installed — so hide them
# from the Metric Results table. Persisted rows are untouched; this is display-only.
_UNSCORED_DRILL_METRICS = {"multilingual_similarity", "chrf_score"}

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
    "ig":    "Igbo",
    "am":    "Amharic",
    "ha":    "Hausa",
    "om":    "Afaan Oromoo",
    "zu":    "isiZulu",
    "so":    "Af-Soomaali",
    "sheng": "Sheng",
}

# Sidebar nav glyphs — display only (the radio option values stay the plain view names,
# so routing / access.py are unaffected).
_NAV_ICONS = {
    "Run Evaluation": "▶", "Run Scorecard": "◧", "Provider Comparison": "⇄",
    "Language Comparison": "◈", "SME Calibration": "✎",
    "Pack Management": "▦", "HITL Management": "◑",
}

# One-line description of what each scorecard dimension measures (shown on the cards).
_DIM_BLURB = {
    "cultural_appropriateness": "Contextual fit, register, and respect for the locale.",
    "language_performance": "Fluency, accuracy, and completeness in the target language.",
    "safety_robustness": "Refusals, harmful-content avoidance, and adversarial robustness.",
    "code_switching_quality": "Holds the target language; natural switching, no unwanted drift.",
    "hallucination_risk": "Faithfulness to the source; no fabricated Africa-specific facts.",
    "bias_fairness": "Score parity across cohort and language groups (four-fifths rule).",
}

PACK_CATALOG = [
    {"id": "mobile_money_sw_v1.0.0",      "label": "Mobile Money (Swahili)",        "language": "sw"},
    {"id": "remittance_so_v1.0.0",         "label": "Remittance (Af-Soomaali)",           "language": "so"},
    {"id": "cross_border_trade_ha_v1.0.0", "label": "Cross-Border Trade (Hausa)",    "language": "ha"},
    {"id": "community_health_am_v1.2.0",   "label": "Community Health (Amharic)",    "language": "am"},
    {"id": "agriculture_om_v1.0.0",        "label": "Agriculture (Afaan Oromoo)",    "language": "om"},
    {"id": "agriculture_ha_v1.0.0",        "label": "Agriculture (Hausa)",           "language": "ha"},
    {"id": "public_services_zu_v1.0.0",    "label": "Public Services (isiZulu)",        "language": "zu"},
    {"id": "customer_service_yo_v1.0.0",   "label": "Customer Service (Yoruba)",     "language": "yo"},
    {"id": "urban_digital_sheng_v1.0.0",   "label": "Urban Digital (Sheng)",         "language": "sheng"},
    {"id": "code_switching_mixed_v1.0.0",  "label": "Code Switching (mixed)",        "language": "mixed"},
    {"id": "safety_mixed_v1.0.0",          "label": "Safety (mixed)",                "language": "mixed"},
    {"id": "customer_service_en_v1.0.0",   "label": "Customer Service (English)",    "language": "en"},
]

_PACK_META: dict[str, str] = {p["id"]: p["label"] for p in PACK_CATALOG}

# Languages that have SME drafts staged in Label Studio but no runnable pack yet — surfaced
# (disabled) in Run Evaluation so the roster reflects the pipeline. (label, language, draft_count)
_COMING_PACKS: list[tuple[str, str, int]] = [
    ("Community Health (Igbo)", "ig", 12),
]

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

# Master AgentifyAfro brand stylesheet (pure-black canvas, gradient accents, Inter,
# WCAG-AA palette). All CSS + the section/badge helpers live in console.branding; the
# accent/semantic colours it uses come from console.theme (tested — see
# tests/test_console_contrast.py). Call once, before any view renders.
inject_brand_css()


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
        # Batch the assessment + scorecard lookups into two IN-queries instead of two per run
        # (was ~2*N sequential round-trips to the remote pooler — the main nav-click delay).
        run_ids = [run.id for run in runs]
        assessment_ids = {run.assessment_id for run in runs}
        assessments = {
            a.id: a for a in session.exec(select(Assessment).where(col(Assessment.id).in_(assessment_ids))).all()
        } if assessment_ids else {}
        scorecards = {
            s.run_id: s for s in session.exec(select(Scorecard).where(col(Scorecard.run_id).in_(run_ids))).all()
        } if run_ids else {}
        for run in runs:
            assessment = assessments.get(run.assessment_id)
            scorecard = scorecards.get(run.id)

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
                "runtime_seconds":     (
                    int((run.completed_at - run.started_at).total_seconds())
                    if run.started_at and run.completed_at else None
                ),
                "archived":            run.archived,
                "has_scorecard":       scorecard is not None,
                "composite_score":     scorecard.composite_score if scorecard else None,
                "verdict":             scorecard.verdict if scorecard else None,
                "confidence_flag":     scorecard.confidence_flag if scorecard else None,
                "safety_unverified":   scorecard.safety_unverified if scorecard else False,
                "african_fabrication_detected": scorecard.african_fabrication_detected if scorecard else False,
                "dimension_scores":    scorecard.dimension_scores if scorecard else {},
                "dimension_weights":   scorecard.dimension_weights if scorecard else {},
                "dimension_confidence_intervals": (
                    getattr(scorecard, "dimension_confidence_intervals", None) or {}
                ) if scorecard else {},
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
                "error":       m.error,
                "error_cause": m.error_cause,
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
                dim_scores = [m["score"] for m in resp_metrics if m["dimension"] == dim and not m["error"]]
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
            if getattr(m, "error", False):
                continue
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
        # Batch assessment + scorecard lookups (was 2 queries per run against the remote pooler).
        run_ids = [run.id for run in runs]
        assessment_ids = {run.assessment_id for run in runs}
        assessments = {
            a.id: a for a in session.exec(select(Assessment).where(col(Assessment.id).in_(assessment_ids))).all()
        } if assessment_ids else {}
        scorecards = {
            s.run_id: s for s in session.exec(select(Scorecard).where(col(Scorecard.run_id).in_(run_ids))).all()
        } if run_ids else {}
        for run in runs:
            scorecard = scorecards.get(run.id)
            if not scorecard:
                continue
            assessment = assessments.get(run.assessment_id)
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
        lang_metric_scores: dict[str, dict[str, dict[str, list[float]]]] = {}

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
                    if lang not in lang_metric_scores:
                        lang_metric_scores[lang] = {dim: {} for dim in DIM_SHORT}

                for m in metrics:
                    if getattr(m, "error", False):
                        continue
                    lang = resp_to_lang.get(str(m.response_id), "unknown")
                    dims = lang_metric_scores.get(lang, {})
                    if m.dimension in dims:
                        dims[m.dimension].setdefault(m.metric_name, []).append(m.score)

        # Use the most-recent run_id (group_run_ids[0]) as the row key so that
        # _get(lang, run_id_a, col) lookups in render_language_breakdown resolve correctly.
        key_run_id = group_run_ids[0]
        for lang, dim_metrics in lang_metric_scores.items():
            metric_means = {
                dim: {mn: sum(s) / len(s) for mn, s in metric_scores.items() if s}
                for dim, metric_scores in dim_metrics.items()
            }
            dim_scores, composite = composite_from_metric_means(metric_means)
            row: dict = {
                "language":   lang,
                "model":      model_label or "unknown",
                "provider":   provider,
                "run_id":     key_run_id,
                "item_count": lang_counts.get(lang, 0),
            }
            for dim, short in DIM_SHORT.items():
                val = dim_scores.get(dim)
                row[short] = round(val, 1) if val is not None else None
            row["composite"] = round(composite, 1) if composite is not None else None
            rows.append(row)

    return pd.DataFrame(rows)


@st.cache_data(ttl=30)
def load_seeded_pack_ids() -> set:
    engine = get_engine()
    with Session(engine) as session:
        packs = session.exec(select(BenchmarkPack)).all()
        return {f"{p.name}_{p.version}" for p in packs}


# Canonical SME authoring project title — single source of truth in hitl/label_config.py,
# shared with the authoring scripts and coverage_report so console + CLI never disagree.
_AUTHORING_PROJECT_TITLE = AUTHORING_PROJECT_TITLE


@st.cache_data(ttl=900, show_spinner=False)
def load_authoring_status() -> dict | None:
    """Live (cached 15 min) Label Studio project-9 authoring queue. Best-effort:
    returns None if Label Studio is unconfigured/unreachable so the view degrades
    gracefully. Mirrors scripts/coverage_report._live_authoring_counts — keep in sync.
    'authored' = a task that carries at least one annotation."""
    try:
        from collections import defaultdict

        from hitl.client import LabelStudioClient

        client = LabelStudioClient()
        project = client.find_project_by_title(_AUTHORING_PROJECT_TITLE)
        if project is None:
            return None
        counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for task in client.list_tasks(project["id"]):
            lang = task.get("data", {}).get("target_language", "?")
            counts[lang][0] += 1
            if task.get("total_annotations", 0) > 0 or task.get("is_labeled"):
                counts[lang][1] += 1
        return {
            "project_id":    project["id"],
            "project_title": project.get("title", _AUTHORING_PROJECT_TITLE),
            "by_lang":       {k: (v[0], v[1]) for k, v in counts.items()},
        }
    except Exception:
        return None


_EMPTY_VALIDATION = {"total_ratings": 0, "items_validated": 0, "validators": 0,
                     "fully_validated": 0, "by_validator": {}}


@st.cache_data(ttl=60, show_spinner=False)
def load_validation_status() -> dict:
    """SME item-validation status from the item_validations table (Tier-1 path).
    Counts only — no live LS call. 'fully validated' = an item with >= 2 distinct SMEs.
    Returns a zeroed status if the table is unavailable so the tab degrades gracefully."""
    from collections import defaultdict

    try:
        with Session(get_engine()) as session:
            vals = session.exec(select(ItemValidation)).all()
    except Exception:
        return dict(_EMPTY_VALIDATION)

    by_item: dict = defaultdict(set)
    by_validator: dict = defaultdict(lambda: {"rated": 0, "validated": 0, "needs_revision": 0})
    for v in vals:
        by_item[v.item_id].add(v.validator_id)
        bucket = by_validator[v.validator_id]
        bucket["rated"] += 1
        if v.verdict == "validated":
            bucket["validated"] += 1
        else:
            bucket["needs_revision"] += 1

    return {
        "total_ratings":   len(vals),
        "items_validated": len(by_item),
        "validators":      len(by_validator),
        "fully_validated": sum(1 for sme in by_item.values() if len(sme) >= 2),
        "by_validator":    dict(by_validator),
    }


@st.cache_data(ttl=60, show_spinner=False)
def load_adjudication_count() -> int | None:
    """Items whose two SMEs genuinely DISAGREE — factual mismatch, pair κ < 0.70, or cultural
    scores > 1 rubric point apart — computed with the SAME logic as scripts/validation_adjudicate
    (compute_item_results). Distinct from a 'needs_revision' verdict (one SME's opinion).
    Returns None if the packs/validations can't be read."""
    try:
        from scripts.validation_writeback import _load_validations, compute_item_results

        items: list[dict] = []
        for path in sorted((PROJECT_ROOT / "benchmarks" / "packs").glob("*.jsonl")):
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    items.append(json.loads(line))
        validations, _skipped = _load_validations(items)
        results = compute_item_results(validations, items)
        return sum(1 for r in results.values() if r["needs_adjudication"])
    except Exception:
        return None


def _run_pipeline(argv: list[str], *, spinner: str, timeout: int = 300, clear_cache: bool = False) -> None:
    """Run a pipeline script as a subprocess and surface the result. Same pattern used by
    every HITL action button; keeps the tabbed action UI DRY. argv is script + flags."""
    # Suppress the SQLAlchemy echo firehose (dev env) so the action output shows the script's
    # own summary, not every SQL statement. AFROEVAL_SQL_ECHO=0 is read by db.session.get_engine.
    env = {**os.environ, "AFROEVAL_SQL_ECHO": "0"}
    with st.spinner(spinner):
        result = subprocess.run(
            [sys.executable, *argv],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
    if result.returncode == 0:
        if clear_cache:
            st.cache_data.clear()
        st.success("Done.")
        with st.expander("Script output"):
            st.text(result.stdout or "(no output)")
    else:
        st.error("Failed.")
        st.text(result.stderr or "(no stderr)")


@st.cache_data(ttl=300, show_spinner=False)
def load_coverage_summary() -> dict:
    """Local pack-file coverage against the 10-item scored floor (no DB/LS). Best-effort —
    reuses scripts.coverage_report so the console and CLI agree on 'clears the floor'."""
    try:
        from scripts.coverage_report import _PACKS_DIR, _load_items, newest_versions, pack_status

        newest  = newest_versions(_PACKS_DIR)
        below   = []
        cleared = 0
        for base, path in newest.items():
            stt = pack_status(_load_items(path))
            if stt["clears_floor"]:
                cleared += 1
            else:
                below.append((base, stt["floor_gap"]))
        return {"total": len(newest), "cleared": cleared,
                "below": sorted(below, key=lambda x: -x[1])}
    except Exception:
        return {}


# ── UI helpers ────────────────────────────────────────────────────────────────

def _verdict_badge(verdict: str) -> str:
    icons = {"Deployment-Ready": "🟢", "Conditional": "🟡", "Not-Ready": "🟠", "High-Risk": "🔴"}
    return f"{icons.get(verdict, '⚪')} {verdict}"


def _render_remediation(roadmap: list[dict]) -> None:
    if not roadmap:
        return
    render_section_divider()
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


def _content_filter_count(metrics_by_resp: dict[str, list[dict]]) -> int:
    """Count metric rows blocked by the judge's content filter — the African-language
    fairness signal (the judge sees the target-language response)."""
    return sum(
        1
        for rows in metrics_by_resp.values()
        for m in rows
        if m.get("error") and m.get("error_cause") == "content_filter"
    )


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
    render_section_header("Agreement", "Calibration summary — SME vs automated")
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
    render_section_header("Detail", f"Reviewed items ({len(cal_df)})")

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

    render_section_divider()
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
        completed = run.completed_at
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
        runtime_str = ""
        if started and completed:
            secs = int((completed - started).total_seconds())
            runtime_str = f"  ·  runtime **{secs // 60}m {secs % 60}s**"
        st.success(
            f"Complete — composite **{scorecard.composite_score:.1f} / 100** — {scorecard.verdict}{runtime_str}"
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
    render_section_header("Configure", "Run Evaluation")
    st.caption("Configure and launch a new evaluation run against selected benchmark packs.")

    active = st.session_state.get("op_active_run_id")
    if active:
        _render_active_run(active)
        return

    # ── Pack selection ────────────────────────────────────────────────────
    render_section_header("Configure", "Select benchmark packs")
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

    # Languages with drafts staged but no runnable pack yet — shown disabled so the roster
    # matches the pipeline (and the redesign mock). Not selectable: launching would have no
    # pack data. Track authoring progress in HITL Management → Authoring.
    for j, (label, lang, drafts) in enumerate(_COMING_PACKS):
        with pack_cols[(len(PACK_CATALOG) + j) % 2]:
            st.checkbox(
                f"{label}  ·  authoring",
                value=False,
                disabled=True,
                key=f"op_pack_soon_{lang}",
                help=f"Authoring in progress — {drafts} drafts staged in Label Studio, no pack yet.",
            )

    render_section_divider()

    # ── Model configuration ───────────────────────────────────────────────
    render_section_header("Model configuration", "Target model")

    def _sync_model_id() -> None:
        prov  = st.session_state.get("op_provider", EVALUATED_PROVIDERS[0])
        model = PROVIDER_MODEL_DEFAULTS.get(prov, "")
        st.session_state["op_model_id"] = model
        # Clear auto-name tracking so the next render regenerates it with the new model + packs
        for _k in ("op_name", "op_name_auto", "op_name_sel_key"):
            st.session_state.pop(_k, None)

    mc1, mc2 = st.columns(2)
    with mc1:
        provider = st.selectbox(
            "Provider",
            # Azure OpenAI is the LLM judge, not an evaluated target — see EVALUATED_PROVIDERS.
            list(EVALUATED_PROVIDERS),
            format_func=lambda v: PROVIDER_SHORT.get(v, v),
            key="op_provider",
            on_change=_sync_model_id,
        )
    with mc2:
        if "op_model_id" not in st.session_state:
            st.session_state["op_model_id"] = PROVIDER_MODEL_DEFAULTS.get(
                provider, PROVIDER_MODEL_DEFAULTS[EVALUATED_PROVIDERS[0]]
            )
        model_id = st.text_input(
            "Model Identifier",
            key="op_model_id",
        )

    render_section_divider()

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

    render_section_divider()

    cov = load_coverage_summary()
    if cov and cov.get("total"):
        below_n = cov["total"] - cov["cleared"]
        if below_n:
            render_callout(
                f"<b>Coverage note.</b> {below_n} of {cov['total']} packs are below the 10-item "
                f"scored floor — only floor-clearing packs yield Tier-1 results. {cov['cleared']} "
                f"cleared. See <b>Pack Management</b> for the per-pack gap.",
                kind="warn",
            )
        else:
            render_callout(f"<b>Coverage.</b> All {cov['total']} packs clear the 10-item scored floor.")

    can_launch = len(selected_packs) > 0 and bool(model_id.strip())
    if not selected_packs:
        st.caption("Select at least one pack to enable Launch.")

    if st.button("▶ Launch evaluation", type="primary", disabled=not can_launch, key="op_launch"):
        _launch_run(assessment_name, provider, model_id, selected_packs)
        st.rerun()


def render_pack_management() -> None:
    render_console_header()
    render_section_header("Benchmarks", "Pack Management")
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
    render_section_header("Human-in-the-loop", "HITL Management")
    st.caption(
        "The Label Studio operations hub — SME item **authoring**, two-validator "
        "**validation**, and response **calibration**, each with its live status and "
        "pipeline actions. Actions run the same scripts as the CLI; output is shown inline."
    )

    tab_auth, tab_val, tab_cal = st.tabs(["✍ Authoring", "✔ Validation", "🎯 Calibration"])
    with tab_auth:
        _render_hitl_authoring()
    with tab_val:
        _render_hitl_validation()
    with tab_cal:
        _render_hitl_calibration()


def _render_hitl_authoring() -> None:
    """SME item-authoring status (Label Studio project 9) + authoring-pipeline actions."""
    status = load_authoring_status()

    if status is None:
        render_callout(
            "<b>Label Studio not reachable.</b> The authoring queue needs Label Studio "
            "credentials configured (LS refresh token in secrets). The pipeline actions "
            "below still work once credentials are set.",
            kind="warn",
        )
        if st.button("↻ Retry authoring query", key="auth_retry"):
            load_authoring_status.clear()
            st.rerun()
    else:
        by_lang        = status["by_lang"]
        total_authored = sum(a for _s, a in by_lang.values())
        total_pending  = sum(s - a for s, a in by_lang.values())
        done           = [LANGUAGE_NAMES.get(lg, lg) for lg, (s, a) in by_lang.items() if s > 0 and a == s]
        authored_sub   = (", ".join(done) + " complete") if done else "in progress"
        proj_title     = status["project_title"]
        proj_short     = "SME Authoring v2" if "Authoring v2" in proj_title else (proj_title[:22] or "SME Authoring")

        render_kpi_row([
            {"label": "Label Studio project", "value": proj_short, "sm": True,
             "sub": f"project {status['project_id']}"},
            {"label": "Authored", "value": f"{total_authored}",
             "sub": authored_sub, "trend": "up" if total_authored else "flat"},
            {"label": "Pending", "value": f"{total_pending}",
             "sub": "awaiting SMEs" if total_pending else "all authored",
             "trend": "down" if total_pending else "flat"},
        ])

        render_section_divider()
        render_section_header("Authoring queue", "Staged vs authored by language")

        pack_langs   = {p["language"] for p in PACK_CATALOG}
        status_badge = {"pass": ("pass", "Complete"), "warn": ("warn", "Pending"), "info": ("info", "No pack yet")}
        rows = []
        for lang, (staged, authored) in sorted(by_lang.items(), key=lambda kv: (-kv[1][0], kv[0])):
            if staged > 0 and authored == staged:
                key = "pass"
            elif lang not in pack_langs:
                key = "info"
            else:
                key = "warn"
            cls, label = status_badge[key]
            rows.append([
                f"{LANGUAGE_NAMES.get(lang, lang)} ({lang})",
                str(staged), str(authored), str(staged - authored),
                f'<span class="sc-badge {cls}">{label}</span>',
            ])
        render_data_table(
            ["Language", "Staged", "Authored", "Pending", "Status"],
            rows, right_cols={1, 2, 3}, score_cols={2},
        )

    render_section_divider()
    render_section_header("Actions", "Authoring pipeline")
    st.caption("Draft placeholders live in Label Studio; SMEs author the real in-language item there.")
    ac1, ac2 = st.columns(2)
    with ac1:
        if st.button("🏗 Create / sync authoring project", key="auth_create", use_container_width=True):
            _run_pipeline(["scripts/create_authoring_project.py"],
                          spinner="Creating / syncing authoring project…", clear_cache=True)
    with ac2:
        if st.button("📥 Import authored items → staging", key="auth_import", use_container_width=True):
            _run_pipeline(["scripts/import_authored_items.py"],
                          spinner="Importing approved authored items…", clear_cache=True)
    st.caption("Promote staged items into a pack's next version from **Pack Management**.")


def _render_hitl_validation() -> None:
    """Two-validator item-validation status (item_validations) + validation-pipeline actions."""
    vs = load_validation_status()
    adj = load_adjudication_count()

    if adj is None:
        adj_kpi = {"label": "Needs adjudication", "value": "—", "sub": "unavailable", "trend": "flat"}
    elif adj == 0:
        adj_kpi = {"label": "Needs adjudication", "value": "0", "sub": "all agree", "trend": "up"}
    else:
        adj_kpi = {"label": "Needs adjudication", "value": str(adj),
                   "sub": "run Adjudicate", "trend": "down"}

    render_kpi_row([
        {"label": "Items validated", "value": f"{vs['items_validated']}",
         "sub": f"{vs['total_ratings']} ratings"},
        {"label": "Fully validated", "value": f"{vs['fully_validated']}",
         "sub": "≥ 2 SMEs (Tier-1)", "trend": "up" if vs["fully_validated"] else "flat"},
        {"label": "Validators", "value": f"{vs['validators']}",
         "sub": "distinct reviewers"},
        adj_kpi,
    ], columns=4)
    st.caption(
        "**Needs revision** (in the table below) is one SME's verdict on an item. "
        "**Needs adjudication** is separate — it fires only when the two SMEs actually disagree: "
        "factual accuracy, pair κ < 0.70, or cultural scores > 1 rubric point apart. "
        "Run **Adjudicate disputes** to export any that qualify."
    )

    render_section_divider()
    render_section_header("Agreement", "Ratings by validator")
    if vs["by_validator"]:
        rows = [
            [vid, str(d["rated"]), str(d["validated"]), str(d["needs_revision"])]
            for vid, d in sorted(vs["by_validator"].items(), key=lambda kv: -kv[1]["rated"])
        ]
        render_data_table(
            ["Validator", "Rated", "Validated", "Needs revision"],
            rows, right_cols={1, 2, 3}, score_cols={2},
        )
    else:
        st.info("No validator ratings imported yet. Export items, collect ratings in Label Studio, "
                "then import them below.")

    render_section_divider()
    render_section_header("Actions", "Validation pipeline")
    st.caption("Each item goes to exactly two eligible SMEs who did not author it; writeback stamps "
               "`validation_count` / `irr_score` onto the pack files. Writing actions default to dry-run.")
    vc1, vc2, vc3 = st.columns(3)
    with vc1:
        if st.button("📤 Export items (dry-run)", key="val_export", use_container_width=True):
            _run_pipeline(["scripts/validation_export_tasks.py", "--dry-run"],
                          spinner="Previewing validation export…")
        if st.button("⚖ Adjudicate disputes (dry-run)", key="val_adj", use_container_width=True):
            _run_pipeline(["scripts/validation_adjudicate.py", "--dry-run"],
                          spinner="Previewing adjudication…")
    with vc2:
        if st.button("📥 Import validator ratings", key="val_import", use_container_width=True):
            _run_pipeline(["scripts/validation_import_ratings.py"],
                          spinner="Importing validator ratings…", clear_cache=True)
    with vc3:
        if st.button("✍ Writeback IRR (dry-run)", key="val_wb_dry", use_container_width=True):
            _run_pipeline(["scripts/validation_writeback.py", "--dry-run"],
                          spinner="Previewing IRR writeback…")
        if st.button("✅ Writeback IRR (apply)", key="val_wb_apply", type="primary", use_container_width=True):
            _run_pipeline(["scripts/validation_writeback.py", "--apply"],
                          spinner="Writing validation_count / irr_score…", clear_cache=True)


def _render_hitl_calibration() -> None:
    """SME-vs-automated calibration status (response_reviews) + response export/import actions."""
    with st.spinner("Loading SME reviews…"):
        cal_df = load_calibration_data()

    n = len(cal_df)
    render_kpi_row([
        {"label": "Reviews imported", "value": f"{n}", "sub": "SME ResponseReviews"},
        {"label": "Items reviewed", "value": f"{cal_df['item_id'].nunique() if n else 0}"},
        {"label": "Reviewers", "value": f"{cal_df['reviewer_id'].nunique() if n else 0}",
         "sub": "distinct SMEs"},
    ])

    if n:
        render_section_divider()
        _render_calibration_summary(cal_df)
        st.caption("Full SME-vs-automated, per-item drill-down lives in the **SME Calibration** view.")
    else:
        st.info("No SME reviews imported yet. Export responses, annotate them in Label Studio, "
                "then import the reviews below.")

    render_section_divider()
    render_section_header("Actions", "Calibration pipeline")
    st.caption("Pushes unreviewed ModelResponse rows to Label Studio for SME scoring, then pulls "
               "completed annotations back as ResponseReview rows.")
    cc1, cc2 = st.columns(2)
    with cc1:
        if st.button("📤 Export responses for review", key="cal_export", use_container_width=True):
            _run_pipeline(["scripts/hitl_export_tasks.py"],
                          spinner="Exporting responses to Label Studio…", timeout=600)
    with cc2:
        if st.button("📥 Import SME reviews", key="cal_import", use_container_width=True):
            _run_pipeline(["scripts/hitl_import_reviews.py"],
                          spinner="Importing SME reviews…", clear_cache=True)


def render_calibration_view() -> None:
    render_console_header()
    render_section_header("Calibration", "SME Calibration")
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
    render_section_divider()
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
            render_section_divider()
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

    # Scorecard header — hero composite + KPI cards (custom components)
    _pack_val, _ = _pack_display(selected["pack_ids"])
    _rt = selected.get("runtime_seconds")
    render_scorecard_header(
        composite=selected["composite_score"],
        verdict=selected["verdict"],
        confidence=selected["confidence_flag"],
        model=selected["model"],
        lang_domain=_pack_val,
        runtime=(f"{_rt // 60}m {_rt % 60}s" if _rt is not None else None),
    )

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

    render_section_divider()

    # Dimension scores — custom cards (score · CI · status pill · gradient bar)
    render_section_header("Quality dimensions", "Dimension breakdown")
    dim_scores  = selected["dimension_scores"]
    dim_weights = selected["dimension_weights"]
    dim_cis     = selected.get("dimension_confidence_intervals") or {}
    _cards: list[dict] = [
        {
            "name": dim.replace("_", " ").title(),
            "weight": dim_weights.get(dim, 0),
            "score": score,
            "ci": dim_cis.get(dim),
            "status": "fail" if score < 60 else "pass",
            "blurb": _DIM_BLURB.get(dim, ""),
        }
        for dim, score in sorted(dim_scores.items(), key=lambda x: x[1])
    ]
    _cards += [
        {"name": dim.replace("_", " ").title(), "weight": dim_weights.get(dim, 0),
         "score": None, "ci": None, "status": "na", "blurb": _DIM_BLURB.get(dim, "")}
        for dim in dim_weights if dim not in dim_scores
    ]
    # Radar beside the dimension cards (matches the mock's dimension layout). The radar is
    # a Streamlit components.html iframe, so it can't live inside the HTML card grid — a
    # column places it alongside instead.
    import streamlit.components.v1 as components

    from reporting.radar import radar_svg
    rc1, rc2 = st.columns([1, 2])
    with rc1:
        if dim_scores:
            components.html(radar_svg(dim_scores, size=300, theme="dark"), height=320)
    with rc2:
        render_dimension_cards(_cards)
    st.caption("95% CI shown per dimension. “—” = single run-level statistic "
               "(Bias & Fairness), too few items, or a pre-CI historical run.")

    render_section_divider()

    # Key Observations
    render_section_header("Summary", "Key Observations")
    from types import SimpleNamespace

    from reporting.observations import build_key_observations
    obs_scorecard = SimpleNamespace(
        dimension_scores=dim_scores,
        verdict=selected.get("verdict"),
        confidence_flag=selected.get("confidence_flag"),
        safety_unverified=selected.get("safety_unverified", False),
        african_fabrication_detected=selected.get("african_fabrication_detected", False),
    )
    observations = build_key_observations(obs_scorecard)
    if observations:
        for obs in observations:
            st.markdown(f"- {obs}")
    else:
        st.caption("No notable observations for this run.")

    render_section_divider()

    # Per-item table
    render_section_header("Per-item evidence", "Item drill-down")
    with st.spinner("Loading items…"):
        df, metrics_by_resp = load_run_items(run_id)

    if df.empty:
        st.info("No item data — ModelResponse rows may not have been persisted for this run.")
        return

    _cf = _content_filter_count(metrics_by_resp)
    if _cf:
        render_callout(
            f"<b>Content-filter note.</b> {_cf} judge call(s) in this run were blocked by the "
            "content filter and excluded from scoring — a known false-positive risk on "
            "African-language responses. See the item drill-down (rows marked <b>Excluded</b>).",
            kind="warn",
        )

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
        render_detail_placeholder(
            "Select a row above to render its prompt, model response, and per-metric results."
        )
        _render_remediation(selected["remediation_roadmap"])
        return

    # Item detail — branded panel (presentation only; data straight from the selected row)
    row     = fdf.iloc[sel_rows[0]]
    resp_id = row["response_id"]

    flags = []
    if row["is_filtered"]:
        flags.append("⚠ filter-blocked")
    if row["is_gold"]:
        flags.append("★ gold")

    foot_bits = [f"Language: {row['language']}", f"Domain: {row['domain']}"]
    if row.get("latency_ms"):
        foot_bits.append(f"Latency: {row['latency_ms']}ms")
    if row.get("tokens_used"):
        foot_bits.append(f"Tokens: {row['tokens_used']}")

    item_metrics = metrics_by_resp.get(resp_id, [])
    metrics = [
        (m["dimension"], m["metric_name"], (m["score"] or 0) * 100,
         "error" if m.get("error") else ("pass" if m["passed"] else "fail"),
         (f"excluded ({m.get('error_cause') or 'unavailable'}) — {m.get('reason') or ''}"
          if m.get("error") else (m.get("reason") or "")))
        for m in sorted(item_metrics, key=lambda m: m["dimension"])
        if m["metric_name"] not in _UNSCORED_DRILL_METRICS
    ]

    render_item_detail({
        "id":       row["item_id"],
        "cohort":   row["language"],
        "tags":     " · ".join([row["domain"], *flags]),
        "prompt":   row["prompt"],
        "expected": row["expected_behavior"],
        "response": row["raw_output"],
        "foot":     "  |  ".join(foot_bits),
        "metrics":  metrics,
    })

    _render_remediation(selected["remediation_roadmap"])


def render_provider_comparison() -> None:
    render_console_header()
    render_section_header("Compare", "Provider Comparison")
    st.caption(
        "Side-by-side scorecard results across model providers running the same benchmark packs. "
        "Validates routing decisions — e.g., whether Anthropic outperforms OpenAI on Afaan Oromoo/Af-Soomaali content."
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

    # ── Summary KPIs ────────────────────────────────────────────────────
    _top_prov = max(providers, key=lambda p: latest[p]["composite_score"])
    render_kpi_row([
        {"label": "Top model", "value": latest[_top_prov]["model_identifier"], "sm": True,
         "sub": f"{latest[_top_prov]['composite_score']:.1f} composite", "trend": "up"},
        {"label": "Models compared", "value": f"{len(providers)}",
         "sub": " · ".join(_provider_short(p) for p in providers)},
        {"label": "Benchmark", "value": selected_label, "sm": True},
    ])
    render_section_divider()

    # ── Composite ranking bars ──────────────────────────────────────────
    render_section_header("Ranking", "Composite by provider")
    scores: dict[str, float] = {prov: latest[prov]["composite_score"] for prov in providers}
    render_comparison_bars(
        [(f"{_provider_short(prov)} — {latest[prov]['model_identifier']}", scores[prov])
         for prov in providers]
    )
    if len(providers) == 2:
        p0, p1 = providers[0], providers[1]
        delta = scores[p1] - scores[p0]
        st.caption(f"Δ ({_provider_short(p1)} − {_provider_short(p0)}): "
                   f"{'+' if delta >= 0 else ''}{delta:.1f}")

    render_section_divider()

    # ── Dimension breakdown table ───────────────────────────────────────
    render_section_header("Detail", "Dimension scores by model")

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
        render_section_divider()
        render_section_header("Read-out", "Interpretation")
        _render_comparison_insight(latest[providers[0]], latest[providers[1]], dims_sorted)

    render_section_divider()

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
    render_section_header("Coverage", "Language Comparison")
    st.caption(
        "Per-language deployment-readiness composites, engine-weighted. Every language — "
        "English (US) included — is scored on the same African-context rubric, so these are "
        "not general-capability scores and don't compare to MMLU-style benchmarks. English "
        "runs a US customer-service pack as a control condition, not a high-resource ceiling."
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
    render_section_header("Coverage", "Composite by language × model")
    st.caption(
        "Sequential tint on the score columns — darker = lower, cyan = higher; status colours "
        "stay reserved for the Δ columns. Δ vs EN = language composite minus the English (US) "
        "control composite for the same model. Packs differ by domain, so read this as a "
        "pack-to-pack difference, not a same-task equity measure."
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
            f"◇ {LANGUAGE_NAMES.get(lang, lang)} (control)"
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
            return f"color: {ERROR}; font-weight: 600"
        if v < 0:
            return f"color: {WARNING}; font-weight: 600"
        if v > 0:
            return f"color: {SUCCESS}; font-weight: 600"
        return "color: #A6ABC4"  # neutral delta — WCAG AA/AAA faint (was #6B7280, 3.6:1)

    def _heat_bg(v):
        # Sequential ramp (dark → royal → cyan), tuned for the 70–92 composite band, mirroring
        # the redesign mock. Purely a background tint on the score cells — never the Δ columns.
        if pd.isna(v):
            return ""
        x = max(0.0, min(100.0, float(v)))
        lo, mid, hi = (26, 26, 36), (65, 105, 225), (0, 207, 255)
        if x < 80:
            a, b, t = lo, mid, max(0.0, (x - 70) / 10)
        else:
            a, b, t = mid, hi, min(1.0, (x - 80) / 12)
        c = [round(a[i] + (b[i] - a[i]) * min(1.0, t)) for i in range(3)]
        return f"background-color: rgb({c[0]},{c[1]},{c[2]}); color: #FFFFFF; font-weight: 600"

    def score_fmt(v):
        return "—" if pd.isna(v) else f"{v:.1f}"

    def delta_fmt(v):
        return "—" if pd.isna(v) else (f"+{v:.1f}" if v > 0 else f"{v:.1f}")

    score_cols = [c for c in [model_a] + ([model_b] if two_models else []) if c in t1_df.columns]
    fmt: dict = {c: score_fmt for c in score_cols}
    fmt.update({c: delta_fmt for c in delta_cols})

    styled_t1 = (
        t1_df.style
        .map(_color_delta, subset=delta_cols)
        .map(_heat_bg, subset=score_cols)
        .format(fmt, na_rep="—")
    )
    st.dataframe(styled_t1, use_container_width=True, hide_index=True)
    st.markdown(
        '<div style="display:flex;align-items:center;gap:10px;font-size:12px;color:#A6ABC4;'
        'margin-top:8px"><span>Lower</span><span style="height:10px;width:180px;border-radius:5px;'
        'background:linear-gradient(90deg,#1A1A24,#4169E1,#00CFFF)"></span>'
        '<span>Higher · composite 0–100</span></div>',
        unsafe_allow_html=True,
    )

    # ── Table 2: Dimension × Language pivot ────────────────────────────────
    render_section_divider()
    st.subheader("Dimension × Language Comparison")
    st.caption(
        "Rows = evaluation dimensions. Columns = each language found in the selected runs. "
        "Scores are absolute per language. Packs differ by domain, so read across with care — "
        "these are not like-for-like rankings. '—' means the dimension does not apply to that "
        "pack (e.g. bias & fairness needs multiple cohorts)."
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

    def _score(lang_code: str, run_id: str, col: str) -> float | None:
        sub = df[(df["language"] == lang_code) & (df["run_id"] == run_id)]
        if sub.empty:
            return None
        val = sub[col].values[0]
        # NaN is not None — a dimension that doesn't apply to a pack (e.g. bias_fairness on a
        # single-cohort pack) arrives here as NaN and would render as the literal string "nan".
        if val is None or pd.isna(val):
            return None
        return float(val)

    t2_rows = []

    comp_row: dict = {"Dimension": "Composite", "Weight": "—"}
    for lbl, lc, rid in lang_cols:
        v = _score(lc, rid, "composite")
        comp_row[lbl] = f"{v:.1f}" if v is not None else "—"
    t2_rows.append(comp_row)

    for dim, short in DIM_SHORT.items():
        row: dict = {"Dimension": DIM_LABELS[dim], "Weight": DIM_WEIGHTS[dim]}
        for lbl, lc, rid in lang_cols:
            v = _score(lc, rid, short)
            row[lbl] = f"{v:.1f}" if v is not None else "—"
        t2_rows.append(row)

    col_cfg: dict = {
        "Dimension": st.column_config.TextColumn("Dimension", width="medium"),
        "Weight":    st.column_config.TextColumn("Weight", width="small"),
    }
    for lbl, _, _ in lang_cols:
        col_cfg[lbl] = st.column_config.TextColumn(lbl, width="small")

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
        auth_user: AuthUser | None = st.session_state.get("auth_user")
        unlocked = st.session_state.get("operator_unlocked", False)

        # Access-tier badge — reflects console/access.py (informational; changes no gating).
        if (auth_user is not None and auth_user.role == "admin") or unlocked:
            st.markdown('<div class="role-badge op">🔓 Operator · admin</div>', unsafe_allow_html=True)
        elif auth_user is not None:
            st.markdown('<div class="role-badge vw">👁 Viewer · read-only</div>', unsafe_allow_html=True)

        st.header("View")
        all_views = resolve_views(auth_user, unlocked)

        if all_views:
            # nav_view is managed as plain session state (not a widget key) so it can
            # be set from button callbacks without triggering StreamlitAPIException.
            if st.session_state.get("nav_view") not in all_views:
                st.session_state["nav_view"] = all_views[0]
            _nav_idx = all_views.index(st.session_state["nav_view"])
            selected = st.radio(
                "View", all_views, label_visibility="collapsed", index=_nav_idx,
                format_func=lambda v: f"{_NAV_ICONS.get(v, '•')}  {v}"
                + ("   ·  ADMIN" if v in CATEGORY_2_VIEWS else ""),
            )
            st.session_state["nav_view"] = selected
            view = selected
        else:
            st.caption("Log in to view the console.")
            view = None

        if st.button("🔄 Refresh", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

        render_section_divider()

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
