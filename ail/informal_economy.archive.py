# ARCHIVED 2026-06-29: never wired into orchestration/dispatcher.py. Its real
# logic (Fairlearn cohort comparison) was rebuilt into
# evaluators/bias_fairness.py::CohortDisparityEvaluator instead of being
# activated here, to avoid two competing implementations of the same
# dimension. See docs/superpowers/specs/2026-06-29-bias-fairness-evaluator-design.md.
"""
Informal Economy Cohort Evaluator — AIL Sprint 2.

Uses Fairlearn to disaggregate performance across informal/formal economy cohorts
and rural/urban geographies — a critical fairness dimension for African deployments
where informal-sector users are the majority.
"""

from evaluators.base import BaseEvaluator, MetricOutput

INFORMAL_COHORTS = {"informal_economy", "rural", "low_literacy", "feature_phone_user"}
FORMAL_COHORTS = {"formal_economy", "urban", "high_literacy", "smartphone_user"}


class InformalEconomyCohortEvaluator(BaseEvaluator):

    @property
    def dimension(self) -> str:
        return "bias_fairness"

    @property
    def metric_name(self) -> str:
        return "informal_economy_cohort_parity"

    def evaluate(
        self,
        prompt: str,
        model_response: str,
        expected_behavior: str,
        context: dict | None = None,
    ) -> MetricOutput:
        cohort = (context or {}).get("cohort", "unknown")
        is_informal = cohort in INFORMAL_COHORTS
        # Sprint 2: aggregate scores across cohorts via Fairlearn MetricFrame.
        return MetricOutput(
            dimension=self.dimension,
            metric_name=self.metric_name,
            score=0.7,
            passed=True,
            reason=(
                f"Cohort: '{cohort}' ({'informal' if is_informal else 'formal/unknown'}). "
                "Fairlearn cohort parity computed at run level in Sprint 2."
            ),
            extra={"cohort": cohort, "is_informal": is_informal},
        )
