"""
Language Performance evaluators — Dimension weight: 25%.

Measures how accurately and fluently the model responds in the target language.
Wraps DeepEval's AnswerRelevancyMetric and a custom African-language fluency check.

Sprint 1 implementation: semantic similarity stub (DeepEval wired in Sprint 1).
"""

from evaluators.base import BaseEvaluator, MetricOutput


class SemanticSimilarityEvaluator(BaseEvaluator):
    """
    Measures semantic alignment between model output and expected behavior.
    Full DeepEval integration in Sprint 1; stub runs standalone for scaffolding.
    """

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
        # Sprint 1: wire DeepEval AnswerRelevancyMetric here.
        # Stub: basic keyword overlap as a placeholder score.
        expected_tokens = set(expected_behavior.lower().split())
        response_tokens = set(model_response.lower().split())
        overlap = len(expected_tokens & response_tokens)
        score = min(overlap / max(len(expected_tokens), 1), 1.0)
        return MetricOutput(
            dimension=self.dimension,
            metric_name=self.metric_name,
            score=score,
            passed=score >= 0.6,
            reason=f"Token overlap: {overlap}/{len(expected_tokens)} expected tokens matched.",
        )


class AnswerCompletenessEvaluator(BaseEvaluator):
    """Does the model response address all required elements of the expected behavior?"""

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
        # Sprint 1: integrate DeepEval GEval or custom LLM-judge.
        not_empty = bool(model_response.strip())
        score = 0.5 if not_empty else 0.0
        return MetricOutput(
            dimension=self.dimension,
            metric_name=self.metric_name,
            score=score,
            passed=score >= 0.5,
            reason="Stub — LLM-judge wired in Sprint 1.",
        )
