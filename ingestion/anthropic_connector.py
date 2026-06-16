"""
Anthropic connector — Claude models via the Anthropic Messages API.
Parallel item calls via ThreadPoolExecutor, same pattern as OpenAI connector.
"""

import time
from concurrent.futures import ThreadPoolExecutor

import structlog
from anthropic import Anthropic, APIStatusError, APITimeoutError, RateLimitError

from ingestion.base import ModelConnector, ModelResponseRaw

logger = structlog.get_logger(__name__)

_EVAL_SYSTEM_PROMPT = (
    "You are an AI assistant being evaluated for deployment in African markets. "
    "Answer each question accurately, in the same language as the question, "
    "and with cultural context appropriate to the region."
)

_MAX_WORKERS = 5  # concurrent Anthropic calls per connector


class AnthropicConnector(ModelConnector):

    def __init__(self, api_key: str, model: str = "claude-haiku-4-5-20251001", max_tokens: int = 512):
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY is not set. Check your .env file.")
        self.model = model
        self.max_tokens = max_tokens
        self._client = Anthropic(api_key=api_key)

    @property
    def provider_name(self) -> str:
        return "anthropic"

    def _call_single(self, item: dict) -> ModelResponseRaw:
        item_id = item.get("id", "")
        prompt = item.get("prompt", "")
        try:
            start = time.monotonic()
            message = self._client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=_EVAL_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
            )
            latency = int((time.monotonic() - start) * 1000)
            raw_output = message.content[0].text if message.content else ""
            tokens_used = (
                message.usage.input_tokens + message.usage.output_tokens
                if message.usage else None
            )
            logger.info(
                "Model response received",
                item_id=item_id,
                latency_ms=latency,
                tokens=tokens_used,
            )
            return ModelResponseRaw(
                item_id=item_id,
                prompt=prompt,
                raw_output=raw_output,
                latency_ms=latency,
                tokens_used=tokens_used,
            )
        except RateLimitError as exc:
            logger.warning("Anthropic rate limit", item_id=item_id, error=str(exc))
            return ModelResponseRaw(item_id=item_id, prompt=prompt, raw_output="", latency_ms=None)
        except (APITimeoutError, APIStatusError) as exc:
            logger.error("Anthropic API error", item_id=item_id, error=str(exc))
            return ModelResponseRaw(item_id=item_id, prompt=prompt, raw_output="", latency_ms=None)

    def get_responses(self, items: list[dict], **kwargs) -> list[ModelResponseRaw]:
        if not items:
            return []
        workers = min(_MAX_WORKERS, len(items))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            return list(pool.map(self._call_single, items))
