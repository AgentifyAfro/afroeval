"""
Evaluation orchestration — run scheduling and evaluator dispatch.

The dispatcher is the only place that knows about both the ingestion layer
and the evaluators. It wires them together without either module knowing
about the other (module contract).

Sprint 1: live model connectors, LLM-judge evaluators, connector routing by provider.
Sprint 2: ModelResponse + MetricResult persistence, AIL LLM-judge evaluators.
"""

import uuid
from datetime import datetime

import structlog

from scoring.engine import DEFAULT_WEIGHTS, compute_composite_score

logger = structlog.get_logger(__name__)


def _parse_pack_id(pack_id: str) -> tuple[str, str]:
    """
    Parse "mobile_money_sw_v1.0.0" → ("mobile_money_sw", "v1.0.0").
    Splits at the last "_v" separator before the version string.
    """
    idx = pack_id.rfind("_v")
    if idx == -1:
        raise ValueError(
            f"Cannot parse pack_id '{pack_id}' — expected format: <name>_v<version>"
        )
    return pack_id[:idx], pack_id[idx + 1:]


def _build_connector(model_provider: str, cfg):
    """Return the right ingestion connector for the given provider."""
    from ingestion.azure_openai_connector import AzureOpenAIConnector
    from ingestion.openai_connector import OpenAIConnector

    if model_provider == "azure_openai":
        return AzureOpenAIConnector(
            api_key=cfg.azure_openai_api_key,
            endpoint=cfg.azure_openai_endpoint,
            deployment_name=cfg.azure_openai_deployment_name,
            api_version=cfg.azure_openai_api_version,
        )
    elif model_provider == "openai":
        return OpenAIConnector(
            api_key=cfg.openai_api_key,
            model=cfg.openai_default_model,
        )
    elif model_provider == "jsonl_upload":
        raise ValueError(
            "JSONL upload runs are triggered via the /v1/assessments upload endpoint, "
            "not through the live dispatcher. Use JSONLConnector directly."
        )
    else:
        raise ValueError(f"Unsupported model_provider: '{model_provider}'")


def _build_judge(cfg):
    """Build the LLM judge from settings. Returns None if Azure is not configured."""
    from evaluators.llm_judge import LLMJudge

    if cfg.ail_judge_provider == "azure_openai" and cfg.azure_openai_api_key:
        return LLMJudge.from_azure(
            api_key=cfg.azure_openai_api_key,
            endpoint=cfg.azure_openai_endpoint,
            deployment=cfg.azure_openai_deployment_name,
            api_version=cfg.azure_openai_api_version,
        )
    elif cfg.ail_judge_provider == "openai" and cfg.openai_api_key:
        return LLMJudge.from_openai(
            api_key=cfg.openai_api_key,
            model=cfg.ail_judge_model,
        )
    logger.warning("LLM judge not configured — evaluators will use stub fallback")
    return None


def _fail(session, run, message: str) -> None:
    from db.models import RunStatus

    run.status = RunStatus.FAILED
    run.error_message = message
    run.completed_at = datetime.utcnow()
    session.add(run)
    session.commit()
    logger.error("Run failed", run_id=str(run.id), reason=message)


async def dispatch_run(run_id: str) -> None:
    """
    Orchestrate a full evaluation run:
      1. Load Assessment + Run from DB; mark RUNNING.
      2. Load benchmark items from versioned JSONL packs.
      3. Route to the right model connector; get responses.
      4. Build LLM judge; call all evaluators per item.
      5. Compute composite score via the scoring engine.
      6. Persist the Scorecard.
      7. Mark run COMPLETED.

    Sprint 2: add ModelResponse + MetricResult persistence.
    """
    from api.settings import get_settings
    from db.models import Assessment, Run, RunStatus, Scorecard
    from db.session import get_engine
    from sqlmodel import Session

    engine = get_engine()

    try:
        with Session(engine) as session:
            run = session.get(Run, uuid.UUID(run_id))
            if not run:
                logger.error("Run not found", run_id=run_id)
                return

            assessment = session.get(Assessment, run.assessment_id)
            if not assessment:
                _fail(session, run, "Assessment not found")
                return

            # ── Step 1: Mark RUNNING ──────────────────────────────────────────
            run.status = RunStatus.RUNNING
            run.started_at = datetime.utcnow()
            session.add(run)
            session.commit()
            logger.info("Run started", run_id=run_id, assessment=assessment.name)

            try:
                cfg = get_settings()

                # ── Step 2: Load benchmark items ──────────────────────────────
                from benchmarks.loader import load_pack

                all_items: list[dict] = []
                for pack_id in assessment.benchmark_pack_ids:
                    name, version = _parse_pack_id(pack_id)
                    try:
                        items = load_pack(name, version)
                        all_items.extend(items)
                        logger.info("Pack loaded", pack_id=pack_id, item_count=len(items))
                    except FileNotFoundError:
                        logger.warning("Pack not found — skipping", pack_id=pack_id)

                if not all_items:
                    raise ValueError(
                        "No benchmark items loaded. "
                        "Check pack IDs and run: python scripts/seed_benchmarks.py"
                    )

                # ── Step 3: Get model responses ───────────────────────────────
                connector = _build_connector(assessment.model_provider, cfg)
                raw_responses = connector.get_responses(all_items)

                # ── Step 4: Evaluate each response ────────────────────────────
                from ail.code_switching import CodeSwitchingEvaluator
                from ail.cultural_appropriateness import CulturalAppropriatenessEvaluator
                from ail.hallucination_probes import AfricanHallucinationProbeEvaluator
                from evaluators.bias_fairness import CohortDisparityEvaluator
                from evaluators.hallucination import FaithfulnessEvaluator
                from evaluators.language_performance import (
                    AnswerCompletenessEvaluator,
                    SemanticSimilarityEvaluator,
                )
                from evaluators.safety import SafetyEvaluator

                judge = _build_judge(cfg)

                evaluators = [
                    SemanticSimilarityEvaluator(judge=judge),
                    AnswerCompletenessEvaluator(judge=judge),
                    FaithfulnessEvaluator(judge=judge),
                    AfricanHallucinationProbeEvaluator(),
                    CohortDisparityEvaluator(),
                    SafetyEvaluator(),
                    CulturalAppropriatenessEvaluator(),
                    CodeSwitchingEvaluator(),
                ]

                dimension_scores: dict[str, list[float]] = {dim: [] for dim in DEFAULT_WEIGHTS}
                item_counts: dict[str, int] = {dim: 0 for dim in DEFAULT_WEIGHTS}

                for raw, item in zip(raw_responses, all_items):
                    context = {
                        "language": item.get("language", ""),
                        "domain": item.get("domain", ""),
                        "cohort": item.get("cohort", ""),
                    }
                    for evaluator in evaluators:
                        output = evaluator.evaluate(
                            prompt=raw.prompt,
                            model_response=raw.raw_output,
                            expected_behavior=item.get("expected_behavior", ""),
                            context=context,
                        )
                        if output.dimension in dimension_scores:
                            dimension_scores[output.dimension].append(output.score)
                            item_counts[output.dimension] += 1

                # ── Step 5: Compute composite score ───────────────────────────
                result = compute_composite_score(
                    dimension_raw_scores=dimension_scores,
                    item_counts=item_counts,
                )
                logger.info(
                    "Scoring complete",
                    run_id=run_id,
                    score=result.composite_score,
                    verdict=result.verdict,
                    confidence=result.confidence_flag,
                )

                # ── Step 6: Persist Scorecard ─────────────────────────────────
                scorecard = Scorecard(
                    id=uuid.uuid4(),
                    run_id=uuid.UUID(run_id),
                    composite_score=result.composite_score,
                    verdict=result.verdict,
                    confidence_flag=result.confidence_flag,
                    dimension_scores=result.dimension_scores,
                    dimension_weights=result.dimension_weights,
                    failing_examples=result.failing_examples,
                    remediation_roadmap=result.remediation_roadmap,
                    benchmark_pack_version=",".join(assessment.benchmark_pack_ids),
                    methodology_version=result.methodology_version,
                )
                session.add(scorecard)

                # ── Step 7: Mark COMPLETED ────────────────────────────────────
                run.status = RunStatus.COMPLETED
                run.completed_at = datetime.utcnow()
                session.add(run)
                session.commit()
                logger.info("Run completed", run_id=run_id, score=result.composite_score)

            except Exception as exc:
                _fail(session, run, str(exc))

    except Exception as exc:
        logger.error("dispatch_run setup error", run_id=run_id, error=str(exc))
