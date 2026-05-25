"""
OpenAI API connector — Sprint 1 implementation.

Phase 0 stub: validates configuration and raises a clear error
so the architecture spike can confirm the wiring is correct.
"""

import time

from ingestion.base import ModelConnector, ModelResponseRaw


class OpenAIConnector(ModelConnector):

    def __init__(self, api_key: str, model: str = "gpt-4o"):
        self.api_key = api_key
        self.model = model

    @property
    def provider_name(self) -> str:
        return "openai"

    def get_responses(self, items: list[dict], **kwargs) -> list[ModelResponseRaw]:
        """
        Sprint 1: full OpenAI chat completion loop with retry and cost tracking.
        Phase 0 stub: returns mock responses so the architecture spike passes end-to-end.
        """
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is not set. Check your .env file.")

        responses = []
        for item in items:
            # Phase 0 stub — replace with openai.ChatCompletion call in Sprint 1
            start = time.monotonic()
            mock_output = f"[STUB] Mock response for: {item.get('prompt', '')[:60]}"
            latency = int((time.monotonic() - start) * 1000)
            responses.append(ModelResponseRaw(
                item_id=item.get("id", ""),
                prompt=item.get("prompt", ""),
                raw_output=mock_output,
                latency_ms=latency,
            ))
        return responses
