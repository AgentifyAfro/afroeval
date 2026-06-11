"""
OpenAI API connector — live implementation using openai.OpenAI client.
Sprint 1: real chat completion loop with per-item error handling and cost tracking.
"""

import time

import structlog
from openai import APIStatusError, APITimeoutError, OpenAI

from ingestion.base import ModelConnector, ModelResponseRaw

logger = structlog.get_logger(__name__)

_EVAL_SYSTEM_PROMPT = (
    "You are an AI assistant being evaluated for deployment in African markets. "
    "Answer each question accurately, in the same language as the question, "
    "and with cultural context appropriate to the region."
)


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

    def get_responses(self, items: list[dict], **kwargs) -> list[ModelResponseRaw]:
        responses = []
        for item in items:
            item_id = item.get("id", "")
            prompt = item.get("prompt", "")
            try:
                start = time.monotonic()
                completion = self._client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": _EVAL_SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=self.max_tokens,
                    temperature=0.0,
                )
                latency = int((time.monotonic() - start) * 1000)
                raw_output = completion.choices[0].message.content or ""
                tokens_used = completion.usage.total_tokens if completion.usage else None
                logger.info(
                    "Model response received",
                    item_id=item_id,
                    latency_ms=latency,
                    tokens=tokens_used,
                )
                responses.append(ModelResponseRaw(
                    item_id=item_id,
                    prompt=prompt,
                    raw_output=raw_output,
                    latency_ms=latency,
                    tokens_used=tokens_used,
                ))
            except (APITimeoutError, APIStatusError) as exc:
                logger.error("OpenAI API error", item_id=item_id, error=str(exc))
                responses.append(ModelResponseRaw(
                    item_id=item_id,
                    prompt=prompt,
                    raw_output="",
                    latency_ms=None,
                ))
        return responses
