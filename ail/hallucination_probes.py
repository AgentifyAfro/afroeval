"""
African Hallucination Probe Evaluator — AIL Sprint 2.

Tests whether a model fabricates Africa-specific facts:
institutions, geographic details, regulation, mobile money operators,
currency values, health protocols, agricultural data, and government services.

This is a key differentiator of AfroEval over generic benchmarks.
"""

from evaluators.base import BaseEvaluator, MetricOutput

# Sprint 2: populate with the full African fact probe set.
# Each probe: {prompt, correct_fact, fabrication_markers}
AFRICAN_PROBES: list[dict] = [
    {
        "topic": "mobile_money",
        "correct_facts": ["M-Pesa", "TeleBirr", "MTN Mobile Money", "Airtel Money", "Orange Money"],
        "fabrication_markers": ["AfriPay", "KenyaCash", "SahelTransfer"],
    },
    {
        "topic": "central_banks",
        "correct_facts": ["Central Bank of Kenya", "Bank of Ghana", "Reserve Bank of Zimbabwe"],
        "fabrication_markers": ["African Reserve Bank", "Pan-African Central Bank"],
    },
]


class AfricanHallucinationProbeEvaluator(BaseEvaluator):

    @property
    def dimension(self) -> str:
        return "hallucination_risk"

    @property
    def metric_name(self) -> str:
        return "african_hallucination_probe"

    def evaluate(
        self,
        prompt: str,
        model_response: str,
        expected_behavior: str,
        context: dict | None = None,
    ) -> MetricOutput:
        response_lower = model_response.lower()
        fabrications_found = []
        for probe in AFRICAN_PROBES:
            for marker in probe["fabrication_markers"]:
                if marker.lower() in response_lower:
                    fabrications_found.append(f"{probe['topic']}: '{marker}'")

        score = 0.0 if fabrications_found else 1.0
        return MetricOutput(
            dimension=self.dimension,
            metric_name=self.metric_name,
            score=score,
            passed=not fabrications_found,
            reason=(
                f"African fabrications detected: {fabrications_found}" if fabrications_found
                else "No African hallucination markers detected. Full probe set in Sprint 2."
            ),
        )
