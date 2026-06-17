"""
AfroEval Scorecard™ Console

Per-run scorecard summary + per-item drill-down into ModelResponse and MetricResult data.
Reads directly from the DB — no HTTP server required.

Run:
    streamlit run console/app.py
"""

import json
import sys
import uuid
from collections import defaultdict
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))

from benchmarks.ids import stable_item_uuid
from benchmarks.loader import PACKS_DIR
from db.models import Assessment, BenchmarkItem, MetricResult, ModelResponse, ResponseReview, Run, Scorecard
from db.session import get_engine
from sqlmodel import Session, col, select

# ── Constants ─────────────────────────────────────────────────────────────────

DIM_SHORT = {
    "language_performance":     "LP",
    "cultural_appropriateness": "CA",
    "hallucination_risk":       "HR",
    "bias_fairness":            "BF",
    "code_switching_quality":   "CS",
    "safety_robustness":        "SR",
}

PROVIDER_SHORT = {
    "azure_openai": "Azure",
    "openai":       "OpenAI",
    "anthropic":    "Anthropic",
    "gemini":       "Gemini",
    "jsonl_upload": "Upload",
}

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="AfroEval Console",
    page_icon="🌍",
    layout="wide",
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
def load_runs_summary() -> list[dict]:
    """Return lightweight metadata for the 50 most recent runs."""
    engine = get_engine()
    rows = []
    with Session(engine) as session:
        runs = session.exec(select(Run).order_by(Run.created_at.desc()).limit(50)).all()
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
                "has_scorecard":       scorecard is not None,
                "composite_score":     scorecard.composite_score if scorecard else None,
                "verdict":             scorecard.verdict if scorecard else None,
                "confidence_flag":     scorecard.confidence_flag if scorecard else None,
                "dimension_scores":    scorecard.dimension_scores if scorecard else {},
                "dimension_weights":   scorecard.dimension_weights if scorecard else {},
                "remediation_roadmap": scorecard.remediation_roadmap if scorecard else [],
                "pack_ids":            assessment.benchmark_pack_ids if assessment else [],
                "model":               assessment.model_identifier if assessment else "",
            })
    return rows


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
def load_provider_comparison() -> list[dict]:
    """All completed scorecards with assessment metadata, grouped for cross-provider comparison."""
    engine = get_engine()
    rows = []
    with Session(engine) as session:
        runs = session.exec(
            select(Run).where(Run.status == "completed").order_by(Run.created_at.desc())
        ).all()
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
                "dimension_scores": scorecard.dimension_scores or {},
                "dimension_weights": scorecard.dimension_weights or {},
            })
    return rows


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


def render_calibration_view() -> None:
    st.title("🌍 AfroEval Scorecard™ Console")
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


# ── Main ──────────────────────────────────────────────────────────────────────

def render_run_scorecard() -> None:
    st.title("🌍 AfroEval Scorecard™ Console")

    # Sidebar: run selector
    with st.sidebar:
        st.header("Evaluation Runs")

        all_runs  = load_runs_summary()
        completed = [r for r in all_runs if r["has_scorecard"]]
        if not completed:
            st.warning("No completed runs with scorecards found.")
            return

        labels = [r["label"] for r in completed]
        idx = st.selectbox(
            "Select run",
            range(len(labels)),
            format_func=lambda i: labels[i],
            label_visibility="collapsed",
        )
        selected = completed[idx]

    run_id = selected["run_id"]

    # Scorecard header metrics
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Composite Score", f"{selected['composite_score']:.1f} / 100")
    c2.metric("Verdict", _verdict_badge(selected["verdict"]))
    c3.metric("Confidence", selected["confidence_flag"])
    c4.metric("Model", selected["model"])
    c5.metric("Packs", len(selected["pack_ids"]))

    st.divider()

    # Dimension scores
    st.subheader("Dimension Scores")
    dim_scores  = selected["dimension_scores"]
    dim_weights = selected["dimension_weights"]
    dcols = st.columns(3)
    for i, (dim, score) in enumerate(sorted(dim_scores.items(), key=lambda x: x[1])):
        weight = dim_weights.get(dim, 0)
        with dcols[i % 3]:
            st.metric(
                label=f"{dim.replace('_', ' ').title()} ({weight:.0%})",
                value=f"{score:.1f}",
                delta="⚠ Below 60" if score < 60 else "OK",
                delta_color="inverse" if score < 60 else "normal",
            )

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
    st.title("🌍 AfroEval Scorecard™ Console")
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


def main() -> None:
    with st.sidebar:
        st.header("View")
        view = st.radio(
            "View",
            ["Run Scorecard", "Provider Comparison", "SME Calibration"],
            label_visibility="collapsed",
        )
        if st.button("🔄 Refresh", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
        st.divider()

    if view == "Provider Comparison":
        render_provider_comparison()
    elif view == "SME Calibration":
        render_calibration_view()
    else:
        render_run_scorecard()


if __name__ == "__main__":
    main()
