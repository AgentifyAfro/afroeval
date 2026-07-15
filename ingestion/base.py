"""
Module contract for model ingestion connectors.

Every connector must implement ModelConnector. The orchestrator calls
get_responses() and receives a normalized list — it never handles
provider-specific formats.
"""

import random
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

_RATE_LIMIT_MAX_RETRIES = 4
_RATE_LIMIT_BASE_DELAY_S = 2.0

_T = TypeVar("_T")


def is_rate_limit_error(exc: Exception) -> bool:
    """
    True for transient rate-limit errors that are worth retrying.

    Deliberately excludes hard quota exhaustion (`insufficient_quota`): retrying
    a key with no quota never succeeds, so it returns False and the caller fails
    fast instead of sleeping through pointless backoff.
    """
    s = str(exc).lower()
    if "insufficient_quota" in s:
        return False
    if getattr(exc, "status_code", None) == 429:
        return True
    return any(
        token in s
        for token in ("rate limit", "ratelimit", "429", "resource_exhausted", "too many requests")
    )


def retry_on_rate_limit(
    call: Callable[[], _T],
    *,
    max_retries: int = _RATE_LIMIT_MAX_RETRIES,
    base_delay: float = _RATE_LIMIT_BASE_DELAY_S,
    sleep: Callable[[float], None] = time.sleep,
) -> _T:
    """
    Invoke `call()`, retrying with exponential backoff + jitter on transient
    rate-limit errors (see is_rate_limit_error). On a non-rate-limit error, or
    once retries are exhausted, the last exception propagates — so the caller's
    existing except block still handles the final failure (e.g. empty response).

    `sleep` is injectable so tests run without real delays.
    """
    attempt = 0
    while True:
        try:
            return call()
        except Exception as exc:
            if is_rate_limit_error(exc) and attempt < max_retries:
                sleep(base_delay * (2 ** attempt) + random.uniform(0, 1))
                attempt += 1
                continue
            raise


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
