"""
Azure OpenAI connector — live implementation using openai.AzureOpenAI client.
Sprint 2: parallel item calls via ThreadPoolExecutor.
"""

import time
from concurrent.futures import ThreadPoolExecutor

import structlog
from openai import APIStatusError, APITimeoutError, AzureOpenAI, BadRequestError

from ingestion.base import ModelConnector, ModelResponseRaw, retry_on_rate_limit

logger = structlog.get_logger(__name__)

_EVAL_SYSTEM_PROMPT = (
    "You are an AI assistant being evaluated for deployment in African markets. "
    "Answer each question accurately, in the same language as the question, "
    "and with cultural context appropriate to the region."
)

_MAX_WORKERS = 5  # concurrent Azure calls per connector


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
            timeout=60.0,
        )

    @property
    def provider_name(self) -> str:
        return "azure_openai"

    def _call_single(self, item: dict) -> ModelResponseRaw:
        item_id = item.get("id", "")
        prompt = item.get("prompt", "")
        try:
            start = time.monotonic()
            completion = retry_on_rate_limit(lambda: self._client.chat.completions.create(
                model=self.deployment_name,
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
        except BadRequestError as exc:
            # Catch content filter (400 ResponsibleAIPolicyViolation) before the
            # generic APIStatusError so we can return a labeled placeholder.
            # Azure's filter has poor calibration for African languages — a legitimate
            # response about fraud prevention or utility connections can be blocked.
            # Returning "" silently tanks all dimension scores; a labeled placeholder
            # lets evaluators produce a traceable low score instead.
            body = getattr(exc, "body", {}) or {}
            inner = (body.get("innererror") or {})
            if inner.get("code") == "ResponsibleAIPolicyViolation":
                filter_result = inner.get("content_filter_result", {})
                logger.warning(
                    "Content filter blocked model response — likely false positive for African-language content",
                    item_id=item_id,
                    filter_result=filter_result,
                )
                return ModelResponseRaw(
                    item_id=item_id,
                    prompt=prompt,
                    raw_output=(
                        "[AFROEVAL NOTE: Azure content filter blocked this response. "
                        "This is a known false-positive pattern for African-language "
                        "evaluation content. The model attempted to respond but was "
                        "prevented by the content moderation system.]"
                    ),
                    latency_ms=None,
                )
            logger.error("Azure bad request", item_id=item_id, error=str(exc))
            return ModelResponseRaw(
                item_id=item_id, prompt=prompt, raw_output="", latency_ms=None
            )

        except (APITimeoutError, APIStatusError) as exc:
            logger.error("Azure OpenAI API error", item_id=item_id, error=str(exc))
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
