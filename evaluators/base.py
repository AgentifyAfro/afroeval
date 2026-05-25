"""
Module contract: every evaluator in AfroEval implements this interface.

The contract guarantees:
- Each evaluator declares its dimension and metric name.
- evaluate() takes a prompt + model response + expected behavior and returns a MetricOutput.
- No evaluator reaches into another module's internals.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class MetricOutput:
    """Normalized output from any evaluator."""
    dimension: str            # e.g. "language_performance"
    metric_name: str          # e.g. "semantic_similarity"
    score: float              # 0.0–1.0 (raw; scoring engine scales to 0–100)
    passed: bool
    reason: str = ""          # Human-readable evidence
    extra: dict = field(default_factory=dict)


class BaseEvaluator(ABC):
    """Base class all evaluators must extend."""

    @property
    @abstractmethod
    def dimension(self) -> str:
        """The AfroEval dimension this evaluator contributes to."""

    @property
    @abstractmethod
    def metric_name(self) -> str:
        """Unique name for this metric within the dimension."""

    @abstractmethod
    def evaluate(
        self,
        prompt: str,
        model_response: str,
        expected_behavior: str,
        context: dict | None = None,
    ) -> MetricOutput:
        """
        Score one model response against one benchmark item.

        context may carry language, domain, cohort, or other item metadata.
        """
