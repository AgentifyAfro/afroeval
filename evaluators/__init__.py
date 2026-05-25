"""
Evaluators package — open-source metric wrappers.

Each evaluator implements BaseEvaluator. The orchestration layer
dispatches evaluators by dimension. No evaluator reaches into
another module's internals (module contract).
"""

from evaluators.base import BaseEvaluator, MetricOutput
from evaluators.bias_fairness import CohortDisparityEvaluator
from evaluators.hallucination import FaithfulnessEvaluator
from evaluators.language_performance import AnswerCompletenessEvaluator, SemanticSimilarityEvaluator
from evaluators.safety import SafetyEvaluator

__all__ = [
    "BaseEvaluator",
    "MetricOutput",
    "SemanticSimilarityEvaluator",
    "AnswerCompletenessEvaluator",
    "FaithfulnessEvaluator",
    "CohortDisparityEvaluator",
    "SafetyEvaluator",
]

# Registry of all active evaluators — the orchestrator reads this.
EVALUATOR_REGISTRY: list[BaseEvaluator] = [
    SemanticSimilarityEvaluator(),
    AnswerCompletenessEvaluator(),
    FaithfulnessEvaluator(),
    CohortDisparityEvaluator(),
    SafetyEvaluator(),
]
