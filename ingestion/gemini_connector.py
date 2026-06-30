"""
Google Gemini connector — models via the google-genai SDK (v1+).
Parallel item calls via ThreadPoolExecutor, same pattern as other connectors.
"""

import time
from concurrent.futures import ThreadPoolExecutor

import structlog
from google import genai
from google.genai import types

from ingestion.base import ModelConnector, ModelResponseRaw, retry_on_rate_limit

logger = structlog.get_logger(__name__)

_EVAL_SYSTEM_PROMPT = (
    "You are an AI assistant being evaluated for deployment in African markets. "
    "Answer each question accurately, in the same language as the question, "
    "and with cultural context appropriate to the region."
)

_MAX_WORKERS = 5


class GeminiConnector(ModelConnector):

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash", max_tokens: int = 512):
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not set. Check your .env file.")
        self.model_name = model
        self.max_tokens = max_tokens
        self._client = genai.Client(api_key=api_key)
        self._gen_config = types.GenerateContentConfig(
            system_instruction=_EVAL_SYSTEM_PROMPT,
            temperature=0.0,
            max_output_tokens=max_tokens,
        )

    @property
    def provider_name(self) -> str:
        return "gemini"

    def _call_single(self, item: dict) -> ModelResponseRaw:
        item_id = item.get("id", "")
        prompt = item.get("prompt", "")
        try:
            start = time.monotonic()
            response = retry_on_rate_limit(lambda: self._client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=self._gen_config,
            ))
            latency = int((time.monotonic() - start) * 1000)
            raw_output = response.text or ""
            usage = getattr(response, "usage_metadata", None)
            tokens_used = (
                (usage.prompt_token_count or 0) + (usage.candidates_token_count or 0)
                if usage else None
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
        except Exception as exc:
            logger.error("Gemini API error", item_id=item_id, error=str(exc))
            return ModelResponseRaw(item_id=item_id, prompt=prompt, raw_output="", latency_ms=None)

    def get_responses(self, items: list[dict], **kwargs) -> list[ModelResponseRaw]:
        if not items:
            return []
        workers = min(_MAX_WORKERS, len(items))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            return list(pool.map(self._call_single, items))
