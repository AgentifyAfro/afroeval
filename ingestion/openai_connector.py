"""
OpenAI API connector — live implementation using openai.OpenAI client.
Sprint 2: parallel item calls via ThreadPoolExecutor.
"""

import time
from concurrent.futures import ThreadPoolExecutor

import structlog
from openai import APIStatusError, APITimeoutError, OpenAI

from ingestion.base import ModelConnector, ModelResponseRaw, retry_on_rate_limit

logger = structlog.get_logger(__name__)

_EVAL_SYSTEM_PROMPT = (
    "You are an AI assistant being evaluated for deployment in African markets. "
    "Answer each question accurately, in the same language as the question, "
    "and with cultural context appropriate to the region."
)

_MAX_WORKERS = 5  # concurrent OpenAI calls per connector


class OpenAIConnector(ModelConnector):

    def __init__(self, api_key: str, model: str = "gpt-4o", max_tokens: int = 512):
        if not api_key:
            raise ValueError("OPENAI_API_KEY is not set. Check your .env file.")
        self.model = model
        self.max_tokens = max_tokens
        self._client = OpenAI(api_key=api_key)

    @property
    def provider_name(self) -> str:
        return "openai"

    def _call_single(self, item: dict) -> ModelResponseRaw:
        item_id = item.get("id", "")
        prompt = item.get("prompt", "")
        try:
            start = time.monotonic()
            completion = retry_on_rate_limit(lambda: self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": _EVAL_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=self.max_tokens,
                temperature=0.0,
            ))
            latency = int((time.monotonic() - start) * 1000)
            raw_output = completion.choices[0].message.content or ""
            tokens_used = completion.usage.total_tokens if completion.usage else None
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
        except (APITimeoutError, APIStatusError) as exc:
            logger.error("OpenAI API error", item_id=item_id, error=str(exc))
            return ModelResponseRaw(
                item_id=item_id,
                prompt=prompt,
                raw_output="",
                latency_ms=None,
            )

    def get_responses(self, items: list[dict], **kwargs) -> list[ModelResponseRaw]:
        if not items:
            return []
        workers = min(_MAX_WORKERS, len(items))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            return list(pool.map(self._call_single, items))
