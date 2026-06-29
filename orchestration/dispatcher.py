"""
Evaluation orchestration — run scheduling and evaluator dispatch.

The dispatcher is the only place that knows about both the ingestion layer
and the evaluators. It wires them together without either module knowing
about the other (module contract).

Sprint 1: live model connectors, LLM-judge evaluators, connector routing by provider.
Sprint 2: parallel connector calls (ThreadPoolExecutor) + parallel evaluator calls
          (asyncio.gather + semaphore). ModelResponse/MetricResult persistence deferred
          to Sprint 3 (requires benchmark items seeded in DB for FK chain).
"""

import asyncio
import uuid
from datetime import datetime

import structlog

from scoring.engine import DEFAULT_METRIC_WEIGHTS, DEFAULT_WEIGHTS, compute_composite_score

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
    from ingestion.anthropic_connector import AnthropicConnector
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
    elif model_provider == "anthropic":
        return AnthropicConnector(
            api_key=cfg.anthropic_api_key,
            model=cfg.anthropic_default_model,
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


def _build_deepeval_model(cfg):
    """Build the Azure-backed DeepEval model for AnswerRelevancy/GEval/Faithfulness. None if not configured."""
    try:
        from deepeval.models import AzureOpenAIModel
    except ImportError:
        logger.warning("deepeval not installed — DeepEval-backed evaluators will use stub fallback")
        return None

    if cfg.ail_judge_provider == "azure_openai" and cfg.azure_openai_api_key:
        return AzureOpenAIModel(
            model=cfg.azure_openai_deployment_name,
            deployment_name=cfg.azure_openai_deployment_name,
            api_key=cfg.azure_openai_api_key,
            base_url=cfg.azure_openai_endpoint,
            api_version=cfg.azure_openai_api_version,
        )
    logger.warning("DeepEval model not configured — DeepEval-backed evaluators will use stub fallback")
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

    Sprint 2: parallel connector + evaluator calls.
    Sprint 3: ModelResponse + MetricResult persistence (requires benchmark items in DB).
    """
    from api.settings import get_settings
    from benchmarks.ids import stable_item_uuid as _item_uuid
    from db.models import Assessment, BenchmarkItem, MetricResult, ModelResponse, Run, RunStatus, Scorecard
    from db.session import get_engine
    from sqlmodel import Session, select

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

                # ── Step 3: Get model responses (parallel via ThreadPoolExecutor) ──
                connector = _build_connector(assessment.model_provider, cfg)
                # Run connector in a thread so the event loop stays responsive.
                raw_responses = await asyncio.to_thread(connector.get_responses, all_items)

                # ── Step 3b: Persist ModelResponse rows ───────────────────────
                # Only write rows for items that have been seeded into benchmark_items.
                # Runs against un-seeded packs still work — persistence is just skipped.
                item_uuids = [_item_uuid(item["id"]) for item in all_items]
                seeded_ids = set(
                    session.exec(
                        select(BenchmarkItem.id).where(BenchmarkItem.id.in_(item_uuids))
                    ).all()
                )
                response_id_by_idx: dict[int, uuid.UUID] = {}
                for idx, (raw, item) in enumerate(zip(raw_responses, all_items)):
                    item_db_id = _item_uuid(item["id"])
                    if item_db_id in seeded_ids:
                        mr = ModelResponse(
                            id=uuid.uuid4(),
                            run_id=uuid.UUID(run_id),
                            item_id=item_db_id,
                            raw_output=raw.raw_output,
                            latency_ms=raw.latency_ms,
                            tokens_used=raw.tokens_used,
                        )
                        session.add(mr)
                        response_id_by_idx[idx] = mr.id
                logger.info(
                    "ModelResponse rows queued",
                    run_id=run_id,
                    count=len(response_id_by_idx),
                    skipped=len(all_items) - len(response_id_by_idx),
                )

                # ── Step 4: Evaluate each response (parallel via asyncio.gather) ──
                from ail.code_switching import (
                    LanguagePreservationEvaluator,
                    RegisterMatchEvaluator,
                    SwitchNaturalnessEvaluator,
                )
                from ail.cultural_appropriateness import CulturalAppropriatenessEvaluator
                from ail.hallucination_probes import AfricanHallucinationProbeEvaluator
                from evaluators.bias_fairness import CohortDisparityEvaluator
                from evaluators.hallucination import FaithfulnessEvaluator
                from evaluators.language_performance import (
                    AnswerCompletenessEvaluator,
                    ChrFEvaluator,
                    FluencyEvaluator,
                    MultilingualSimilarityEvaluator,
                    SemanticSimilarityEvaluator,
                )
                from evaluators.safety import (
                    AdversarialRobustnessEvaluator,
                    HarmfulContentEvaluator,
                    RefusalCalibrationEvaluator,
                )

                judge = _build_judge(cfg)
                deepeval_model = _build_deepeval_model(cfg)

                evaluators = [
                    SemanticSimilarityEvaluator(model=deepeval_model),
                    AnswerCompletenessEvaluator(model=deepeval_model),
                    FluencyEvaluator(judge=judge),
                    ChrFEvaluator(),
                    MultilingualSimilarityEvaluator(),
                    FaithfulnessEvaluator(model=deepeval_model),
                    AfricanHallucinationProbeEvaluator(),
                    HarmfulContentEvaluator(judge=judge),
                    RefusalCalibrationEvaluator(judge=judge),
                    AdversarialRobustnessEvaluator(judge=judge),
                    CulturalAppropriatenessEvaluator(judge=judge),
                    RegisterMatchEvaluator(judge=judge),
                    SwitchNaturalnessEvaluator(judge=judge),
                    LanguagePreservationEvaluator(judge=judge),
                ]

                dimension_scores: dict[str, list[float]] = {dim: [] for dim in DEFAULT_WEIGHTS}
                dimension_metric_scores: dict[str, dict[str, list[float]]] = {
                    dim: {name: [] for name in metrics} for dim, metrics in DEFAULT_METRIC_WEIGHTS.items()
                }
                item_counts: dict[str, int] = {dim: 0 for dim in DEFAULT_WEIGHTS}
                item_passed_flags: dict[int, list[bool]] = {idx: [] for idx in range(len(all_items))}

                # Semaphore caps simultaneous LLM-judge (Azure) calls to avoid rate limits.
                _judge_sem = asyncio.Semaphore(10)

                async def _eval_one(raw, item, evaluator):
                    context = {
                        "language": item.get("language", ""),
                        "domain": item.get("domain", ""),
                        "cohort": item.get("cohort", ""),
                    }
                    async with _judge_sem:
                        return await asyncio.to_thread(
                            evaluator.evaluate,
                            prompt=raw.prompt,
                            model_response=raw.raw_output,
                            expected_behavior=item.get("expected_behavior", ""),
                            context=context,
                        )

                tasks = [
                    _eval_one(raw, item, ev)
                    for raw, item in zip(raw_responses, all_items)
                    for ev in evaluators
                ]
                all_outputs = await asyncio.gather(*tasks)

                n_evaluators = len(evaluators)
                for i, output in enumerate(all_outputs):
                    if output.dimension in dimension_scores:
                        dimension_scores[output.dimension].append(output.score)
                        item_counts[output.dimension] += 1

                    dim_metrics = dimension_metric_scores.get(output.dimension)
                    if dim_metrics is not None and output.metric_name in dim_metrics:
                        dim_metrics[output.metric_name].append(output.score)

                    # ── Step 4b: Persist MetricResult rows ────────────────────
                    item_idx = i // n_evaluators
                    item_passed_flags[item_idx].append(output.passed)
                    if item_idx in response_id_by_idx:
                        session.add(MetricResult(
                            id=uuid.uuid4(),
                            response_id=response_id_by_idx[item_idx],
                            dimension=output.dimension,
                            metric_name=output.metric_name,
                            score=output.score,
                            passed=output.passed,
                            reason=output.reason,
                            extra=output.extra,
                        ))

                # ── Step 4c: Run-level bias_fairness via Fairlearn ─────────────
                bias_cohorts = [item.get("cohort", "") for item in all_items]
                bias_outcomes = [
                    (sum(item_passed_flags[idx]) / len(item_passed_flags[idx]) >= 0.5)
                    if item_passed_flags[idx] else False
                    for idx in range(len(all_items))
                ]
                bias_result = CohortDisparityEvaluator().compute_run_disparity(bias_cohorts, bias_outcomes)

                dimension_scores["bias_fairness"] = [bias_result.score] * len(all_items)
                item_counts["bias_fairness"] = len(all_items)

                for idx, response_id in response_id_by_idx.items():
                    session.add(MetricResult(
                        id=uuid.uuid4(),
                        response_id=response_id,
                        dimension=bias_result.dimension,
                        metric_name=bias_result.metric_name,
                        score=bias_result.score,
                        passed=bias_result.passed,
                        reason=bias_result.reason,
                        extra=bias_result.extra,
                    ))

                # ── Step 5: Compute composite score ───────────────────────────
                result = compute_composite_score(
                    dimension_raw_scores=dimension_scores,
                    item_counts=item_counts,
                    dimension_metric_scores=dimension_metric_scores,
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
                # ── Step 6b: Generate PDF and JSON artefacts ──────────────────
                try:
                    from reporting.generator import generate_scorecard_json, generate_scorecard_pdf
                    scorecard.pdf_path  = generate_scorecard_pdf(scorecard, run, assessment)
                    scorecard.json_path = generate_scorecard_json(scorecard, run, assessment)
                    logger.info("Scorecard artefacts generated", run_id=run_id, pdf=scorecard.pdf_path)
                except Exception as exc:
                    # Non-fatal: run is still recorded even if artefact generation fails
                    logger.warning("Scorecard artefact generation failed", run_id=run_id, error=str(exc))

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
