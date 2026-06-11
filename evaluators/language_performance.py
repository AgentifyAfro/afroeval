"""
Language Performance evaluators — Dimension weight: 25%.

Measures how accurately and fluently the model responds in the target language.
Sprint 1: LLM-judge semantic similarity and answer completeness.
Sprint 2: per-language BLEU/chrF benchmarking added on top.
"""

from evaluators.base import BaseEvaluator, MetricOutput
from evaluators.llm_judge import LLMJudge


class SemanticSimilarityEvaluator(BaseEvaluator):
    """
    Measures semantic alignment between model output and expected behavior.
    Uses an LLM judge when one is provided; falls back to token overlap for tests.
    """

    def __init__(self, judge: LLMJudge | None = None):
        self._judge = judge

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
        ctx = context or {}

        if self._judge:
            criterion = (
                "Rate the semantic similarity between the model response and the expected behavior.\n\n"
                f"Language: {ctx.get('language', 'unknown')}\n"
                f"Domain: {ctx.get('domain', 'unknown')}\n"
                f"Expected behavior: {expected_behavior}\n"
                f"Model response: {model_response}\n\n"
                "Scoring guide:\n"
                "  1.0 — Identical meaning, fully addresses the expected behavior in the correct language\n"
                "  0.8 — Largely equivalent, minor omissions or slight language deviation\n"
                "  0.6 — Addresses the main point but misses secondary elements\n"
                "  0.4 — Partially relevant, significant gaps or wrong language register\n"
                "  0.2 — Tangentially related or mostly off-topic\n"
                "  0.0 — Completely unrelated, wrong language, or empty\n\n"
                'Respond with: {"score": <float 0.0–1.0>, "reason": "<one sentence>"}'
            )
            score, reason = self._judge.score(criterion)
        else:
            # Stub fallback — token overlap (used when no judge is configured)
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

    def __init__(self, judge: LLMJudge | None = None):
        self._judge = judge

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
        ctx = context or {}

        if self._judge:
            criterion = (
                "Rate whether the model response completely addresses all required elements "
                "of the expected behavior.\n\n"
                f"Language: {ctx.get('language', 'unknown')}\n"
                f"Domain: {ctx.get('domain', 'unknown')}\n"
                f"Expected behavior: {expected_behavior}\n"
                f"Model response: {model_response}\n\n"
                "Scoring guide:\n"
                "  1.0 — All elements present, accurate, and in the appropriate language\n"
                "  0.7 — Most elements present, one minor omission\n"
                "  0.5 — Core answer present but secondary elements missing\n"
                "  0.3 — Only partially answers; key elements missing\n"
                "  0.0 — Does not address the expected behavior at all\n\n"
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
            passed=score >= 0.5,
            reason=reason,
        )
