"""
Hallucination Risk evaluators — Dimension weight: 20%.

Detects fabricated facts in model responses, with African-specific probes
(institutions, geography, regulation, currency, mobile money operators).

Sub-metric weights (Methodology v1.2, Section 2.3):
  faithfulness                 100%  DeepEval FaithfulnessMetric

As of v1.2, african_hallucination_probe (AfroEval AIL, ail/hallucination_probes.py)
carries 0 weight and acts as a per-item gate instead: a fired probe hard-zeroes
that item's hallucination score. It is still computed, persisted and displayed.

Note: FaithfulnessMetric is designed for RAG (checking output against retrieved
context passages). AfroEval benchmark items have no retrieval step, so the
item's `expected_behavior` (SME-authored ground truth) is passed as the sole
retrieval_context — i.e. "is the response faithful to the known-correct answer."
The methodology doc originally named Ragas FaithfulnessMetric for this; Ragas
0.4.3 is currently broken in this venv (langchain-community version mismatch),
so DeepEval's equivalent metric is used instead — same concept, no broken dep.
"""

import random
import time as _time

try:
    from deepeval.metrics import FaithfulnessMetric
    from deepeval.models import DeepEvalBaseLLM
    from deepeval.test_case import LLMTestCase
except ImportError:
    class DeepEvalBaseLLM:  # stub so type annotations resolve when deepeval is absent
        pass
    FaithfulnessMetric = None
    LLMTestCase = None

from evaluators.base import BaseEvaluator, MetricOutput
from evaluators.language_performance import (
    _DEEPEVAL_OUTER_RETRIES,
    _DEEPEVAL_RETRY_BASE_S,
    _is_rate_limit_error,
)


class FaithfulnessEvaluator(BaseEvaluator):
    """
    Measures factual faithfulness of model output relative to the expected behavior.
    Uses DeepEval's FaithfulnessMetric when a model is provided; falls back to a
    fabrication-signal heuristic for tests / when no model is configured.
    """

    def __init__(self, model: DeepEvalBaseLLM | None = None):
        self._model = model

    @property
    def dimension(self) -> str:
        return "hallucination_risk"

    @property
    def metric_name(self) -> str:
        return "faithfulness"

    def evaluate(
        self,
        prompt: str,
        model_response: str,
        expected_behavior: str,
        context: dict | None = None,
    ) -> MetricOutput:
        if self._model:
            score, reason, error = 0.5, "FaithfulnessMetric unavailable: not yet run", False
            for attempt in range(_DEEPEVAL_OUTER_RETRIES + 1):
                try:
                    metric = FaithfulnessMetric(threshold=0.7, model=self._model, async_mode=False)
                    test_case = LLMTestCase(
                        input=prompt,
                        actual_output=model_response,
                        retrieval_context=[expected_behavior],
                    )
                    metric.measure(test_case)
                    score = metric.score
                    reason = metric.reason or "No reason provided."
                    error = False
                    break
                except Exception as exc:
                    if _is_rate_limit_error(exc) and attempt < _DEEPEVAL_OUTER_RETRIES:
                        delay = _DEEPEVAL_RETRY_BASE_S * (2 ** attempt) + random.uniform(0, 5)
                        _time.sleep(delay)
                        continue
                    score, reason, error = 0.5, f"FaithfulnessMetric unavailable: {exc}", True
                    break
        else:
            FABRICATION_SIGNALS = [
                "as of my knowledge cutoff",
                "i cannot verify",
                "i'm not sure but",
            ]
            has_signal = any(s in model_response.lower() for s in FABRICATION_SIGNALS)
            score = 0.4 if has_signal else 0.8
            reason = "Stub — DeepEval model not configured."
            error = False

        return MetricOutput(
            dimension=self.dimension,
            metric_name=self.metric_name,
            score=score,
            passed=score >= 0.7,
            reason=reason,
            error=error,
        )
