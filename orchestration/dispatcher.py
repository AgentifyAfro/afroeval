"""
Evaluation orchestration — run scheduling and evaluator dispatch.

The dispatcher is the only place that knows about both the ingestion layer
and the evaluators. It wires them together without either module knowing
about the other (module contract).

The dispatch flow: route each provider to its live model connector; run connector
calls in parallel (ThreadPoolExecutor) and evaluator calls in parallel
(asyncio.gather + a judge semaphore); and persist ModelResponse/MetricResult rows
for items seeded in the DB (the FK chain requires seeded benchmark items).
"""

import asyncio
import functools
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import structlog

from scoring.engine import DEFAULT_METRIC_WEIGHTS, DEFAULT_WEIGHTS, compute_composite_score

logger = structlog.get_logger(__name__)

# DeepEval-backed metrics each fire several token-heavy internal Azure calls, so
# they run on a dedicated, tighter semaphore (see dispatch_run) to avoid blowing the
# TPM limit — unlike the single-call LLM-judge metrics, which run wider.
_DEEPEVAL_METRIC_NAMES = frozenset({"semantic_similarity", "answer_completeness", "faithfulness"})


def _concurrency_limits(cfg) -> tuple[int, int]:
    """(judge, deepeval) simultaneous-Azure-call limits, sourced from settings.

    Env-tunable via JUDGE_MAX_CONCURRENCY / DEEPEVAL_MAX_CONCURRENCY. Defaults (3, 1)
    preserve the safe values; raise only with Azure TPM headroom.
    """
    return cfg.judge_max_concurrency, cfg.deepeval_max_concurrency


def _eval_pool_size(judge_n: int, deepeval_n: int) -> int:
    """Worker count for the evaluator thread pool.

    Must be >= judge_n + deepeval_n so both semaphores can be saturated at once —
    otherwise the CPU-sized default asyncio.to_thread pool (min(32, cpu+4), only ~5-6 on
    a 1-2 vCPU Cloud box) becomes the real throttle instead of the Azure-TPM-bounded
    semaphores. The +4 covers the run's other incidental to-thread work.
    """
    return judge_n + deepeval_n + 4

# v1.2: metrics that GATE a dimension rather than score it. They are computed and
# persisted for evidence, but contribute no positive score, no coverage and no
# bias pass-rate entry.
_GATE_ONLY_METRICS = frozenset({"african_hallucination_probe"})

# The scored metric that the gate above zeroes out when it fires.
_GATED_TARGET_METRIC = "faithfulness"


def _probe_fired_items(all_outputs: list, n_evaluators: int) -> set[int]:
    """Item indices where the African fabrication probe actually fired (score 0.0).

    Errored or not-applicable probe outputs are NOT treated as fabrication — an
    infra failure must never manufacture a hallucination finding.
    """
    return {
        i // n_evaluators
        for i, out in enumerate(all_outputs)
        if getattr(out, "metric_name", "") in _GATE_ONLY_METRICS
        and getattr(out, "applicable", True)
        and not getattr(out, "error", False)
        and out.score == 0.0
    }


def _gated_metric_score(
    metric_name: str, item_idx: int, score: float, probe_fired_items: set[int]
) -> float:
    """Apply the v1.2 fabrication gate to a single metric score.

    A confirmed African fabrication on an item is a hard fail for that item's
    hallucination score: the gated target metric is forced to 0.0. Every other
    metric — and every ungated item — passes through untouched.
    """
    if metric_name == _GATED_TARGET_METRIC and item_idx in probe_fired_items:
        return 0.0
    return score


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


def _build_connector(model_provider: str, cfg, model_override: str | None = None):
    """Return the right ingestion connector for the given provider.

    model_override, when set, takes precedence over the config default — this is
    how multi-model runs work: the assessment stores the intended model_identifier
    and the dispatcher passes it through so each run actually calls a different model.
    """
    from ingestion.anthropic_connector import AnthropicConnector
    from ingestion.azure_openai_connector import AzureOpenAIConnector
    from ingestion.openai_connector import OpenAIConnector

    if model_provider == "azure_openai":
        return AzureOpenAIConnector(
            api_key=cfg.azure_openai_api_key,
            endpoint=cfg.azure_openai_endpoint,
            deployment_name=model_override or cfg.azure_openai_deployment_name,
            api_version=cfg.azure_openai_api_version,
        )
    elif model_provider == "openai":
        return OpenAIConnector(
            api_key=cfg.openai_api_key,
            model=model_override or cfg.openai_default_model,
        )
    elif model_provider == "anthropic":
        return AnthropicConnector(
            api_key=cfg.anthropic_api_key,
            model=model_override or cfg.anthropic_default_model,
        )
    elif model_provider == "gemini":
        from ingestion.gemini_connector import GeminiConnector
        return GeminiConnector(
            api_key=cfg.gemini_api_key,
            model=model_override or "gemini-2.5-flash",
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


def _distinct_item_counts(all_outputs: list, n_evaluators: int) -> dict[str, int]:
    """
    Count the number of distinct ITEMS that produced at least one applicable score
    per dimension. Feeds item_counts → the low_coverage confidence flag.

    all_outputs is the flattened item-major (item × evaluator) grid, so the item a
    given output belongs to is `index // n_evaluators`. Counting outputs directly
    would inflate coverage by the evaluator count (e.g. language_performance has 5
    sub-metrics, so 8 items would look like 40), masking genuine low coverage.
    Not-applicable outputs (e.g. code-switching on a monolingual item) don't count.
    """
    seen: dict[str, set[int]] = {}
    for i, output in enumerate(all_outputs):
        if not getattr(output, "applicable", True):
            continue
        if getattr(output, "error", False):
            continue  # infra-error fallbacks aren't real measurements — not coverage
        if getattr(output, "metric_name", "") in _GATE_ONLY_METRICS:
            continue  # gate-only metrics don't constitute a measurement
        seen.setdefault(output.dimension, set()).add(i // n_evaluators)
    return {dim: len(items) for dim, items in seen.items()}


def _all_responses_empty(raw_responses: list) -> bool:
    """True when there are responses but EVERY one is empty/whitespace.

    Empty raw_output only comes from the connector's error fallback (rate limit / timeout /
    API error such as an out-of-credits 400 or a 401). An all-empty batch therefore means
    the evaluated model call is systematically failing. Scoring it anyway produces a
    misleadingly inflated composite (empty answers trivially look "safe") flagged
    low_coverage — so the run fails loudly instead. A partially-empty batch is left to the
    normal per-metric error-rate / low_coverage machinery.
    """
    if not raw_responses:
        return False
    return all(not (getattr(r, "raw_output", "") or "").strip() for r in raw_responses)


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

    Connector and evaluator calls run in parallel; ModelResponse/MetricResult rows
    are persisted for benchmark items seeded in the DB.
    """
    from sqlmodel import Session, select

    from api.settings import get_settings
    from benchmarks.ids import stable_item_uuid as _item_uuid
    from db.models import (
        Assessment,
        BenchmarkItem,
        MetricResult,
        ModelResponse,
        Run,
        RunStatus,
        Scorecard,
    )
    from db.session import get_engine

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
                connector = _build_connector(
                    assessment.model_provider, cfg,
                    model_override=assessment.model_identifier or None,
                )
                # Run connector in a thread so the event loop stays responsive.
                raw_responses = await asyncio.to_thread(connector.get_responses, all_items)

                # Fail loudly if the model produced nothing at all — otherwise empty
                # responses get scored into a misleadingly inflated, low_coverage scorecard.
                if _all_responses_empty(raw_responses):
                    raise ValueError(
                        f"Model returned no output for all {len(raw_responses)} items — the "
                        f"evaluated model call is failing. Check the provider API key and "
                        f"credits (e.g. Anthropic 'credit balance too low', a 401, a rate-limit "
                        f"storm, or a provider outage). No scorecard was produced."
                    )

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
                    SemanticSimilarityEvaluator(model=deepeval_model, async_mode=cfg.deepeval_async_mode),
                    AnswerCompletenessEvaluator(model=deepeval_model, async_mode=cfg.deepeval_async_mode),
                    FluencyEvaluator(judge=judge),
                    ChrFEvaluator(),
                    MultilingualSimilarityEvaluator(),
                    FaithfulnessEvaluator(model=deepeval_model, async_mode=cfg.deepeval_async_mode),
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

                # LaBSE Phase 1 — judge-divergence (unscored). Per item_idx, remember
                # the LaBSE (multilingual_similarity) and judge semantic_similarity
                # scores, plus a handle to the multilingual row to annotate after.
                labse_by_item: dict[int, float] = {}
                semantic_by_item: dict[int, float] = {}
                multilingual_row_by_item: dict[int, MetricResult] = {}

                # Two semaphores cap simultaneous Azure calls to stay under the TPM
                # limit. Single-call LLM-judge metrics (fluency, cultural, safety,
                # code-switching) run judge-wide. The DeepEval metrics each fire SEVERAL
                # token-heavy internal calls, so they get a dedicated, tighter semaphore —
                # otherwise a few bursting at once blows the TPM (historically 429'd
                # 60-85% of deepeval calls). Both limits are env-tunable (defaults 3 / 1);
                # raise them only with Azure TPM headroom.
                judge_n, deepeval_n = _concurrency_limits(cfg)
                _judge_sem = asyncio.Semaphore(judge_n)
                _deepeval_sem = asyncio.Semaphore(deepeval_n)

                # Evaluator calls are I/O-bound (they wait on Azure), so they need a pool
                # big enough for BOTH semaphores at once. asyncio.to_thread uses the default
                # executor sized to CPU cores (min(32, cpu+4)) — only ~5-6 on a 1-2 vCPU
                # Streamlit Cloud box — which silently caps real concurrency far below the
                # semaphores, so raising TPM/limits does nothing. A dedicated pool sized to
                # the semaphore totals makes the semaphores (bounded by Azure TPM) the real
                # limit, not the host CPU count.
                _eval_pool = ThreadPoolExecutor(
                    max_workers=_eval_pool_size(judge_n, deepeval_n), thread_name_prefix="afroeval-eval"
                )
                _loop = asyncio.get_running_loop()

                async def _eval_one(raw, item, evaluator):
                    context = {
                        "language": item.get("language", ""),
                        "domain": item.get("domain", ""),
                        "cohort": item.get("cohort", ""),
                        "tags": item.get("tags", []),
                    }
                    sem = _deepeval_sem if evaluator.metric_name in _DEEPEVAL_METRIC_NAMES else _judge_sem
                    async with sem:
                        return await _loop.run_in_executor(
                            _eval_pool,
                            functools.partial(
                                evaluator.evaluate,
                                prompt=raw.prompt,
                                model_response=raw.raw_output,
                                expected_behavior=item.get("expected_behavior", ""),
                                context=context,
                            ),
                        )

                tasks = [
                    _eval_one(raw, item, ev)
                    for raw, item in zip(raw_responses, all_items)
                    for ev in evaluators
                ]
                try:
                    all_outputs = await asyncio.gather(*tasks)
                finally:
                    _eval_pool.shutdown(wait=False)

                # Per-metric error tracking for metric_error_rates → confidence_flag.
                _metric_error_counts: dict[str, int] = {}
                _metric_total_counts: dict[str, int] = {}

                n_evaluators = len(evaluators)

                # v1.2: pre-scan for items where the fabrication probe fired, so the
                # faithfulness score for those items is hard-zeroed below. The probe
                # is a gate, not a positive weight (spec 2026-07-17).
                probe_fired_items = _probe_fired_items(all_outputs, n_evaluators)
                african_fabrication_detected = bool(probe_fired_items)
                if african_fabrication_detected:
                    logger.info(
                        "African fabrication probe fired — gating item hallucination scores",
                        run_id=run_id, item_count=len(probe_fired_items),
                    )

                for i, output in enumerate(all_outputs):
                    # item_idx must be derived from position (fixed evaluator grid),
                    # so compute it before any skip to keep the mapping intact.
                    item_idx = i // n_evaluators

                    # Not-applicable metrics (e.g. code-switching on a monolingual
                    # item) are dropped entirely: they don't score, don't count
                    # toward coverage or the bias pass-rate, and aren't persisted.
                    if not output.applicable:
                        continue

                    _metric_total_counts[output.metric_name] = _metric_total_counts.get(output.metric_name, 0) + 1
                    is_error = getattr(output, "error", False)
                    if is_error:
                        _metric_error_counts[output.metric_name] = _metric_error_counts.get(output.metric_name, 0) + 1

                    # ── Step 4b: Persist MetricResult rows ────────────────────
                    # All applicable outputs are persisted — including infra-error
                    # fallbacks — so the item drill-down and SME export still show them
                    # (the export sanitizes error reasons to "unavailable").
                    if item_idx in response_id_by_idx:
                        _mr = MetricResult(
                            id=uuid.uuid4(),
                            response_id=response_id_by_idx[item_idx],
                            dimension=output.dimension,
                            metric_name=output.metric_name,
                            score=output.score,
                            passed=output.passed,
                            reason=output.reason,
                            extra=output.extra,
                            error=output.error,
                            error_cause=getattr(output, "error_cause", None),
                        )
                        session.add(_mr)
                        if not output.error:
                            if output.metric_name == "multilingual_similarity":
                                labse_by_item[item_idx] = output.score
                                multilingual_row_by_item[item_idx] = _mr
                            elif output.metric_name == "semantic_similarity":
                                semantic_by_item[item_idx] = output.score

                    # Infra-error fallbacks (rate limit / content filter / timeout) are
                    # not real measurements: exclude them from the score, pass-rate and
                    # coverage aggregates so a 429 can't drag a dimension toward the 0.5
                    # fallback. They still drive metric_error_rates → low_coverage, and
                    # _distinct_item_counts skips them too (a fully-errored dimension
                    # becomes not_evaluated rather than scoring 0.0).
                    if is_error:
                        # ...with ONE exception: if the fabrication probe fired on
                        # this item, the item WAS measured — by the probe — even
                        # though the judge metric errored. Dropping it would let a
                        # 429 silently erase a confirmed fabrication, which is
                        # exactly the case the gate exists for, so append the 0.0.
                        # Coverage deliberately still excludes it: the probe is a
                        # gate, not a measurement (_GATE_ONLY_METRICS), and the
                        # faithfulness measurement genuinely didn't happen. Net
                        # effect is conservative — the score reflects the
                        # fabrication while coverage stays honestly low.
                        if output.metric_name == _GATED_TARGET_METRIC:
                            dim_metrics = dimension_metric_scores.get(output.dimension)
                            if (
                                dim_metrics is not None
                                and output.metric_name in dim_metrics
                                and item_idx in probe_fired_items
                            ):
                                dim_metrics[output.metric_name].append(
                                    _gated_metric_score(
                                        output.metric_name, item_idx, output.score, probe_fired_items
                                    )
                                )
                        continue

                    if output.dimension in dimension_scores:
                        dimension_scores[output.dimension].append(output.score)

                    dim_metrics = dimension_metric_scores.get(output.dimension)
                    if dim_metrics is not None and output.metric_name in dim_metrics:
                        # v1.2 gate: a detected African fabrication is a hard fail for
                        # that item's hallucination score.
                        dim_metrics[output.metric_name].append(
                            _gated_metric_score(
                                output.metric_name, item_idx, output.score, probe_fired_items
                            )
                        )

                    # v1.2: gate-only metrics are not a measurement — they don't count
                    # toward coverage or the bias pass-rate. Letting the probe into
                    # item_passed_flags would move the verdict through bias_fairness
                    # (an unauthorized channel, double-counting the gate) and, when it
                    # doesn't fire, inject a guaranteed True that dilutes real failures
                    # against the >= 0.5 outcome threshold.
                    if output.metric_name in _GATE_ONLY_METRICS:
                        continue

                    item_passed_flags[item_idx].append(output.passed)

                # LaBSE Phase 1 — annotate divergence per item + count for the scorecard.
                # Unscored: only writes `extra` on the multilingual row and the
                # scorecard's judge_divergence_count; never touches dimension_scores,
                # item_passed_flags, or coverage above.
                from scoring.divergence import count_divergences, run_divergences  # noqa: PLC0415
                # Per-run centering: pass ALL items' (LaBSE, semantic) pairs so the
                # median scale-offset can be removed before flagging (see divergence.py).
                _div_pairs = {
                    _idx: (labse_by_item.get(_idx), semantic_by_item.get(_idx))
                    for _idx in multilingual_row_by_item
                }
                _div_flags = run_divergences(_div_pairs)
                for _idx, _row in multilingual_row_by_item.items():
                    _flag = _div_flags.get(_idx)
                    if _flag is not None:
                        # extra is JSON; copy-update so SQLModel detects the change
                        _row.extra = {**(_row.extra or {}), **_flag}
                # None when LaBSE never produced a comparable row (unavailable) — "not
                # computed", distinct from 0 "computed, none found" (gap G7).
                _divergence_count = (
                    count_divergences(_div_flags.values()) if multilingual_row_by_item else None
                )

                # Coverage = distinct items assessed per dimension (not evaluator
                # outputs), so the low_coverage flag reflects real item counts even
                # for multi-metric dimensions and after applicability filtering.
                item_counts.update(_distinct_item_counts(all_outputs, n_evaluators))

                # Compute per-metric error rates for the confidence_flag check.
                metric_error_rates = {
                    metric: _metric_error_counts.get(metric, 0) / count
                    for metric, count in _metric_total_counts.items()
                    if count > 0
                }

                # ── Step 4c: Run-level bias_fairness via Fairlearn ─────────────
                bias_cohorts = [item.get("cohort", "") for item in all_items]
                bias_languages = [item.get("language", "") for item in all_items]
                bias_outcomes = [
                    (sum(item_passed_flags[idx]) / len(item_passed_flags[idx]) >= 0.5)
                    if item_passed_flags[idx] else False
                    for idx in range(len(all_items))
                ]
                bias_result = CohortDisparityEvaluator().compute_run_disparity(
                    bias_cohorts, bias_outcomes, languages=bias_languages
                )

                if bias_result.applicable:
                    dimension_scores["bias_fairness"] = [bias_result.score] * len(all_items)
                    item_counts["bias_fairness"] = len(all_items)
                    # Persist one MetricResult per response so bias fairness appears
                    # in the drill-down for every item, not just the first one.
                    for resp_id in response_id_by_idx.values():
                        session.add(MetricResult(
                            id=uuid.uuid4(),
                            response_id=resp_id,
                            dimension=bias_result.dimension,
                            metric_name=bias_result.metric_name,
                            score=bias_result.score,
                            passed=bias_result.passed,
                            reason=bias_result.reason,
                            extra=bias_result.extra,
                        ))
                else:
                    # Neither axis qualified: after dropping blanks and groups below
                    # MIN_GROUP_SIZE, both cohort AND language were left with fewer
                    # than 2 comparable groups, so no disparity ratio exists.
                    # item_counts["bias_fairness"] stays at 0 so the scoring engine
                    # treats it as not-evaluated (same path as code-switching on English packs).
                    logger.info(
                        "Bias fairness not applicable — neither cohort nor language "
                        "axis had 2+ qualifying groups",
                        run_id=run_id,
                        reason=bias_result.reason,
                    )

                # ── Step 5: Compute composite score ───────────────────────────
                result = compute_composite_score(
                    dimension_raw_scores=dimension_scores,
                    item_counts=item_counts,
                    dimension_metric_scores=dimension_metric_scores,
                    metric_error_rates=metric_error_rates,
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
                    safety_unverified=result.safety_unverified,
                    african_fabrication_detected=african_fabrication_detected,
                    dimension_scores=result.dimension_scores,
                    dimension_weights=result.dimension_weights,
                    dimension_confidence_intervals=result.dimension_confidence_intervals,
                    failing_examples=result.failing_examples,
                    remediation_roadmap=result.remediation_roadmap,
                    benchmark_pack_version=",".join(assessment.benchmark_pack_ids),
                    methodology_version=result.methodology_version,
                    judge_divergence_count=_divergence_count,
                )
                # ── Step 6b: Generate PDF and JSON artefacts ──────────────────
                # Set completed_at before artefact generation so the timestamp
                # serialized into the JSON reflects the real completion time.
                run.completed_at = datetime.utcnow()
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
