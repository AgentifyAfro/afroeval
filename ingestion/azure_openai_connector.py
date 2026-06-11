"""
Azure OpenAI connector — live implementation using openai.AzureOpenAI client.
"""

import time

import structlog
from openai import APIStatusError, APITimeoutError, AzureOpenAI

from ingestion.base import ModelConnector, ModelResponseRaw

logger = structlog.get_logger(__name__)

# System prompt scopes the model to evaluation context so responses are
# grounded in the benchmark domain rather than defaulting to generic help.
_EVAL_SYSTEM_PROMPT = (
    "You are an AI assistant being evaluated for deployment in African markets. "
    "Answer each question accurately, in the same language as the question, "
    "and with cultural context appropriate to the region."
)


class AzureOpenAIConnector(ModelConnector):

    def __init__(
        self,
        api_key: str,
        endpoint: str,
        deployment_name: str,
        api_version: str = "2025-01-01-preview",
        max_tokens: int = 512,
    ):
        if not api_key or not endpoint:
            raise ValueError(
                "AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT must be set. "
                "Check your .env file."
            )
        self.deployment_name = deployment_name
        self.max_tokens = max_tokens
        self._client = AzureOpenAI(
            api_key=api_key,
            azure_endpoint=endpoint,
            api_version=api_version,
        )

    @property
    def provider_name(self) -> str:
        return "azure_openai"

    def get_responses(self, items: list[dict], **kwargs) -> list[ModelResponseRaw]:
        responses = []
        for item in items:
            item_id = item.get("id", "")
            prompt = item.get("prompt", "")
            try:
                start = time.monotonic()
                completion = self._client.chat.completions.create(
                    model=self.deployment_name,
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
                logger.error("Azure OpenAI API error", item_id=item_id, error=str(exc))
                responses.append(ModelResponseRaw(
                    item_id=item_id,
                    prompt=prompt,
                    raw_output="",
                    latency_ms=None,
                ))
        return responses
