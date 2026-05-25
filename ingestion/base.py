"""
Module contract for model ingestion connectors.

Every connector must implement ModelConnector. The orchestrator calls
get_responses() and receives a normalized list — it never handles
provider-specific formats.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ModelResponseRaw:
    item_id: str
    prompt: str
    raw_output: str
    latency_ms: int | None = None
    tokens_used: int | None = None
    cost_usd: float | None = None


class ModelConnector(ABC):

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Identifier matching ModelProvider enum."""

    @abstractmethod
    def get_responses(
        self,
        items: list[dict],
        **kwargs,
    ) -> list[ModelResponseRaw]:
        """
        Send each benchmark item's prompt to the model.
        Returns one ModelResponseRaw per item, in the same order.
        """
