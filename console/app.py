"""
AfroEval Scorecard™ — Operator Console (Streamlit).

Allows a founder/operator to:
  1. Configure an assessment (model, benchmark pack, settings)
  2. Upload a JSONL or connect a model via API key
  3. Run the assessment
  4. View results and scores
  5. Download the PDF scorecard and JSON export

Run with: streamlit run console/app.py
"""

import httpx
import streamlit as st

API_BASE = "http://localhost:8000/v1"

st.set_page_config(
    page_title="AfroEval Scorecard™",
    page_icon="🌍",
    layout="wide",
)

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown(
    """
    <div style='background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
    padding: 2rem; border-radius: 12px; margin-bottom: 2rem;'>
    <h1 style='color: #e94560; margin: 0;'>AfroEval Scorecard™</h1>
    <p style='color: #a8b2d8; margin: 0.5rem 0 0 0;'>
    Africa-first AI Evaluation Platform · AgentifyAfro.ai</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ── Sidebar: API health ───────────────────────────────────────────────────────
with st.sidebar:
    st.subheader("System Status")
    try:
        resp = httpx.get(f"{API_BASE}/health", timeout=3)
        if resp.status_code == 200:
            st.success(f"API: Online ({resp.json()['environment']})")
        else:
            st.error("API: Unhealthy")
    except Exception:
        st.error("API: Offline — start with `uvicorn api.main:app --reload`")

    st.divider()
    st.markdown("**Methodology version:** v1.0")
    st.markdown("**Benchmark packs:** loading in Sprint 1")

# ── Main tabs ─────────────────────────────────────────────────────────────────
tab_configure, tab_run, tab_results = st.tabs([
    "1. Configure Assessment",
    "2. Run",
    "3. Results & Scorecard",
])

# ── Tab 1: Configure ──────────────────────────────────────────────────────────
with tab_configure:
    st.header("Configure Assessment")

    col1, col2 = st.columns(2)

    with col1:
        assessment_name = st.text_input(
            "Assessment Name",
            placeholder="e.g. GPT-4o Kenya Mobile Money Eval — May 2026",
        )
        provider = st.selectbox(
            "Model Provider",
            ["openai", "azure_openai", "gemini", "jsonl_upload"],
        )
        model_id = st.text_input(
            "Model Identifier",
            placeholder="e.g. gpt-4o or Azure deployment name",
        )

    with col2:
        st.markdown("**Benchmark Pack Selection**")
        st.info(
            "Benchmark packs load from `benchmarks/packs/`. "
            "Run `python scripts/seed_benchmarks.py` to regenerate dev packs. "
            "Full SME-validated packs replace these in Sprint 2."
        )
        pack_ids = st.multiselect(
            "Select Benchmark Packs",
            options=[
                "mobile_money_sw_v1.0.0",
                "customer_service_yo_v1.0.0",
                "community_health_am_v1.0.0",
                "agriculture_ha_v1.0.0",
                "code_switching_mixed_v1.0.0",
                "safety_mixed_v1.0.0",
            ],
            help="Select one or more versioned benchmark packs. Use all 6 for full coverage.",
        )

    if provider == "jsonl_upload":
        uploaded_file = st.file_uploader(
            "Upload JSONL evaluation results",
            type=["jsonl", "json"],
            help="Format: one JSON object per line with item_id, prompt, model_output fields.",
        )
    else:
        st.text_input(
            "API Key (stored in session only — not persisted)",
            type="password",
            key="api_key_input",
        )

    if st.button("Create Assessment", type="primary", disabled=not assessment_name):
        try:
            payload = {
                "name": assessment_name,
                "model_provider": provider,
                "model_identifier": model_id,
                "benchmark_pack_ids": pack_ids,
            }
            resp = httpx.post(f"{API_BASE}/assessments", json=payload, timeout=10)
            if resp.status_code == 201:
                assessment = resp.json()
                st.session_state["current_assessment_id"] = assessment["id"]
                st.success(f"Assessment created: `{assessment['id']}`")
                st.json(assessment)
            else:
                st.error(f"Error: {resp.text}")
        except Exception as e:
            st.error(f"Could not reach API: {e}")

# ── Tab 2: Run ────────────────────────────────────────────────────────────────
with tab_run:
    st.header("Run Assessment")

    assessment_id = st.text_input(
        "Assessment ID",
        value=st.session_state.get("current_assessment_id", ""),
        placeholder="Paste assessment ID from Configure tab",
    )

    if st.button("Submit Run", type="primary", disabled=not assessment_id):
        try:
            resp = httpx.post(
                f"{API_BASE}/runs",
                json={"assessment_id": assessment_id},
                timeout=15,
            )
            if resp.status_code == 202:
                run = resp.json()
                st.session_state["current_run_id"] = run["id"]
                st.success(f"Run submitted: `{run['id']}` — Status: `{run['status']}`")
                st.info(
                    "The orchestration dispatcher is a Phase 0 stub. "
                    "Full execution runs in Sprint 1. Poll /v1/runs/{id} for status."
                )
                st.json(run)
            else:
                st.error(f"Error: {resp.text}")
        except Exception as e:
            st.error(f"Could not reach API: {e}")

    # Status polling
    run_id_check = st.text_input(
        "Check Run Status",
        value=st.session_state.get("current_run_id", ""),
        placeholder="Run ID",
    )
    if st.button("Refresh Status") and run_id_check:
        try:
            resp = httpx.get(f"{API_BASE}/runs/{run_id_check}", timeout=5)
            if resp.status_code == 200:
                st.json(resp.json())
            else:
                st.error(resp.text)
        except Exception as e:
            st.error(str(e))

# ── Tab 3: Results ────────────────────────────────────────────────────────────
with tab_results:
    st.header("Assessment Results")

    run_id_results = st.text_input(
        "Run ID",
        value=st.session_state.get("current_run_id", ""),
        placeholder="Run ID to fetch scorecard",
    )

    if st.button("Load Scorecard") and run_id_results:
        try:
            resp = httpx.get(f"{API_BASE}/scorecards/{run_id_results}", timeout=10)
            if resp.status_code == 200:
                sc = resp.json()
                score = sc["composite_score"]
                verdict = sc["verdict"]

                verdict_color = {
                    "Deployment-Ready": "green",
                    "Conditional": "orange",
                    "Not-Ready": "red",
                    "High-Risk": "darkred",
                }.get(verdict, "grey")

                st.markdown(
                    f"<h2 style='color:{verdict_color}'>AfroEval Score: {score}/100 — {verdict}</h2>",
                    unsafe_allow_html=True,
                )
                st.markdown(f"**Confidence:** `{sc['confidence_flag']}`")

                st.subheader("Dimension Scores")
                for dim, dim_score in sc["dimension_scores"].items():
                    weight = sc["dimension_weights"].get(dim, 0) * 100
                    st.metric(
                        label=f"{dim.replace('_', ' ').title()} (weight: {weight:.0f}%)",
                        value=f"{dim_score:.1f}/100",
                        delta=f"{dim_score - 60:.1f} vs threshold" if dim_score < 80 else None,
                        delta_color="inverse",
                    )

                if sc["remediation_roadmap"]:
                    st.subheader("Remediation Roadmap")
                    for item in sc["remediation_roadmap"]:
                        with st.expander(
                            f"[{item['priority'].upper()}] {item['dimension']} — {item['current_score']:.1f}/100"
                        ):
                            st.write(item["recommendation"])
                            st.caption(f"Estimated effort: {item['estimated_effort']}")

                st.divider()
                st.download_button(
                    "Download JSON Export",
                    data=str(sc),
                    file_name="afroeval_scorecard.json",
                    mime="application/json",
                )
            elif resp.status_code == 404:
                st.warning("No scorecard found for this run. The run may not be complete yet.")
            else:
                st.error(resp.text)
        except Exception as e:
            st.error(f"Could not reach API: {e}")


def main():
    pass  # Entry point for pyproject.toml script
