"""
Language Performance evaluators — Dimension weight: 25%.

Measures how accurately and fluently the model responds in the target language.
Sub-metric weights (Methodology v1.0, Section 2.1) — see scoring/engine.py
DEFAULT_METRIC_WEIGHTS for how these combine into the dimension score:
  semantic_similarity   50%  DeepEval AnswerRelevancyMetric
  answer_completeness   30%  DeepEval GEval
  fluency               20%  Custom LLM-judge

chrF++ (sacrebleu) and multilingual sentence-embedding similarity also run and
persist as MetricResult rows for visibility, but aren't in the documented
weight table above, so they don't count toward the dimension score.
"""

from __future__ import annotations

import functools

try:
    from deepeval.metrics import AnswerRelevancyMetric, GEval
    from deepeval.models import DeepEvalBaseLLM
    from deepeval.test_case import LLMTestCase, SingleTurnParams
except ImportError:
    class DeepEvalBaseLLM:  # stub so type annotations resolve when deepeval is absent
        pass
    AnswerRelevancyMetric = None
    GEval = None
    LLMTestCase = None
    SingleTurnParams = None

from evaluators.base import BaseEvaluator, MetricOutput
from evaluators.llm_judge import LLMJudge


class SemanticSimilarityEvaluator(BaseEvaluator):
    """
    Measures semantic alignment between model output and expected behavior.
    Uses DeepEval's AnswerRelevancyMetric when a model is provided; falls back
    to token overlap for tests / when no model is configured.
    """

    def __init__(self, model: DeepEvalBaseLLM | None = None):
        self._model = model

    @property
    def dimension(self) -> str:
        return "language_performance"

    @property
    def metric_name(self) -> str:
        return "semantic_similarity"

    def evaluate(
        self,
        prompt: str,
        model_response: str,
        expected_behavior: str,
        context: dict | None = None,
    ) -> MetricOutput:
        if self._model:
            try:
                metric = AnswerRelevancyMetric(threshold=0.6, model=self._model, async_mode=False)
                test_case = LLMTestCase(input=prompt, actual_output=model_response)
                metric.measure(test_case)
                score = metric.score
                reason = metric.reason or "No reason provided."
            except Exception as exc:
                score, reason = 0.5, f"AnswerRelevancyMetric unavailable: {exc}"
        else:
            # Stub fallback — token overlap (used when no model is configured)
            expected_tokens = set(expected_behavior.lower().split())
            response_tokens = set(model_response.lower().split())
            overlap = len(expected_tokens & response_tokens)
            score = min(overlap / max(len(expected_tokens), 1), 1.0)
            reason = f"Token overlap: {overlap}/{len(expected_tokens)} expected tokens matched."

        return MetricOutput(
            dimension=self.dimension,
            metric_name=self.metric_name,
            score=score,
            passed=score >= 0.6,
            reason=reason,
        )


class AnswerCompletenessEvaluator(BaseEvaluator):
    """Does the model response address all required elements of the expected behavior?"""

    _EVALUATION_STEPS = [
        "Identify each required element present in the expected output.",
        "Check whether the actual output addresses each required element accurately.",
        "Penalize missing, vague, or incorrect coverage of any required element.",
        "Penalize responses given in the wrong language for the input.",
    ]

    def __init__(self, model: DeepEvalBaseLLM | None = None):
        self._model = model

    @property
    def dimension(self) -> str:
        return "language_performance"

    @property
    def metric_name(self) -> str:
        return "answer_completeness"

    def evaluate(
        self,
        prompt: str,
        model_response: str,
        expected_behavior: str,
        context: dict | None = None,
    ) -> MetricOutput:
        if self._model:
            try:
                metric = GEval(
                    name="answer_completeness",
                    criteria=(
                        "Does the actual output completely address all required elements "
                        "of the expected output, in the appropriate language?"
                    ),
                    evaluation_steps=self._EVALUATION_STEPS,
                    evaluation_params=[
                        SingleTurnParams.INPUT,
                        SingleTurnParams.ACTUAL_OUTPUT,
                        SingleTurnParams.EXPECTED_OUTPUT,
                    ],
                    model=self._model,
                    threshold=0.5,
                    async_mode=False,
                )
                test_case = LLMTestCase(
                    input=prompt, actual_output=model_response, expected_output=expected_behavior
                )
                metric.measure(test_case)
                score = metric.score
                reason = metric.reason or "No reason provided."
            except Exception as exc:
                score, reason = 0.5, f"GEval unavailable: {exc}"
        else:
            not_empty = bool(model_response.strip())
            score = 0.5 if not_empty else 0.0
            reason = "Stub — DeepEval model not configured."

        return MetricOutput(
            dimension=self.dimension,
            metric_name=self.metric_name,
            score=score,
            passed=score >= 0.5,
            reason=reason,
        )


class FluencyEvaluator(BaseEvaluator):
    """
    Grammatical acceptability / fluency of the model response in the target language.
    Custom LLM-judge per Methodology v1.0, Section 2.1 (not a DeepEval/Ragas metric —
    this one is judged directly, independent of semantic correctness).
    """

    def __init__(self, judge: LLMJudge | None = None):
        self._judge = judge

    @property
    def dimension(self) -> str:
        return "language_performance"

    @property
    def metric_name(self) -> str:
        return "fluency"

    def evaluate(
        self,
        prompt: str,
        model_response: str,
        expected_behavior: str,
        context: dict | None = None,
    ) -> MetricOutput:
        ctx = context or {}

        if self._judge:
            criterion = (
                "Rate the fluency and grammatical acceptability of the model response "
                "in its own right — independent of whether its content is correct.\n\n"
                f"Language: {ctx.get('language', 'unknown')}\n"
                f"Model response: {model_response}\n\n"
                "Scoring guide:\n"
                "  1.0 — Fully fluent, natural, grammatically correct\n"
                "  0.7 — Minor grammatical issues, still natural-sounding\n"
                "  0.4 — Noticeably awkward or ungrammatical, but understandable\n"
                "  0.0 — Incoherent, wrong language, or unreadable\n\n"
                'Respond with: {"score": <float 0.0–1.0>, "reason": "<one sentence>"}'
            )
            score, reason = self._judge.score(criterion)
        else:
            not_empty = bool(model_response.strip())
            score = 0.5 if not_empty else 0.0
            reason = "Stub — LLM judge not configured."

        return MetricOutput(
            dimension=self.dimension,
            metric_name=self.metric_name,
            score=score,
            passed=score >= 0.6,
            reason=reason,
        )


# ── Deterministic evaluators (no API calls) ───────────────────────────────────

class ChrFEvaluator(BaseEvaluator):
    """
    Character n-gram F-score (chrF++) between model response and expected behavior.

    Works on any script (Latin, Ethiopic, Arabic) and is independent of tokenisation,
    making it well-suited for morphologically rich African languages.
    Requires: sacrebleu
    """

    @property
    def dimension(self) -> str:
        return "language_performance"

    @property
    def metric_name(self) -> str:
        return "chrf_score"

    def evaluate(
        self,
        prompt: str,
        model_response: str,
        expected_behavior: str,
        context: dict | None = None,
    ) -> MetricOutput:
        try:
            import sacrebleu  # noqa: PLC0415
            chrf = sacrebleu.corpus_chrf(
                hypotheses=[model_response],
                references=[[expected_behavior]],
                word_order=2,   # chrF++ (word bigrams on top of char n-grams)
            )
            # chrF score is 0–100; normalise to 0.0–1.0
            score = round(chrf.score / 100.0, 4)
            reason = f"chrF++ = {chrf.score:.1f}/100 (char+word n-gram overlap with reference)"
        except Exception as exc:
            score = 0.0
            reason = f"chrF unavailable: {exc}"

        return MetricOutput(
            dimension=self.dimension,
            metric_name=self.metric_name,
            score=score,
            passed=score >= 0.25,   # chrF is strict — 0.25 (~25/100) is a reasonable pass bar
            reason=reason,
        )


@functools.lru_cache(maxsize=1)
def _get_multilingual_model():
    """Load the multilingual sentence-transformer model once and cache it."""
    from sentence_transformers import SentenceTransformer  # noqa: PLC0415
    return SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")


class MultilingualSimilarityEvaluator(BaseEvaluator):
    """
    Cosine similarity between model response and expected behavior using a
    multilingual sentence-transformer (paraphrase-multilingual-MiniLM-L12-v2).

    Supports 50+ languages including Swahili, Hausa, Amharic, Somali, Zulu.
    Zero API calls — runs locally, unaffected by rate limits or content filters.
    Requires: sentence-transformers
    """

    @property
    def dimension(self) -> str:
        return "language_performance"

    @property
    def metric_name(self) -> str:
        return "multilingual_similarity"

    def evaluate(
        self,
        prompt: str,
        model_response: str,
        expected_behavior: str,
        context: dict | None = None,
    ) -> MetricOutput:
        try:
            import numpy as np  # noqa: PLC0415
            model = _get_multilingual_model()
            embs = model.encode(
                [model_response, expected_behavior],
                convert_to_numpy=True,
                normalize_embeddings=True,
            )
            # Cosine similarity of L2-normalised vectors = dot product
            score = float(np.dot(embs[0], embs[1]))
            score = max(0.0, round(score, 4))   # clamp negative values to 0
            lang = (context or {}).get("language", "?")
            reason = f"Multilingual embedding cosine similarity = {score:.3f} (lang={lang})"
        except Exception as exc:
            score = 0.0
            reason = f"Multilingual similarity unavailable: {exc}"

        return MetricOutput(
            dimension=self.dimension,
            metric_name=self.metric_name,
            score=score,
            passed=score >= 0.5,
            reason=reason,
        )
