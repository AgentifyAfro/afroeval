"""
Bias & Fairness evaluators — Dimension weight: 15%.

Wraps Fairlearn to measure performance disparities across user cohorts
(formal/informal economy, rural/urban, language proficiency levels).

Sprint 2: informal-economy cohort logic via the Africa Intelligence Layer.
"""

from evaluators.base import BaseEvaluator, MetricOutput


class CohortDisparityEvaluator(BaseEvaluator):
    """
    Measures whether model performance differs significantly across demographic cohorts.
    Requires a set of responses with cohort labels; single-item mode returns a pass-through.
    """

    @property
    def dimension(self) -> str:
        return "bias_fairness"

    @property
    def metric_name(self) -> str:
        return "cohort_disparity"

    def evaluate(
        self,
        prompt: str,
        model_response: str,
        expected_behavior: str,
        context: dict | None = None,
    ) -> MetricOutput:
        # Sprint 2: Fairlearn MetricFrame across cohorts wired here.
        # Single-item stub: score based on cohort presence in context.
        cohort = (context or {}).get("cohort", "unknown")
        score = 0.75  # Neutral until full cohort set is evaluated
        return MetricOutput(
            dimension=self.dimension,
            metric_name=self.metric_name,
            score=score,
            passed=True,
            reason=f"Single-item pass-through for cohort '{cohort}'. Fairlearn wired in Sprint 2.",
        )
