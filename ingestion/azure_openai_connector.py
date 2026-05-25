"""
Azure OpenAI connector — Sprint 1 implementation.
Phase 0 stub with configuration validation.
"""

from ingestion.base import ModelConnector, ModelResponseRaw


class AzureOpenAIConnector(ModelConnector):

    def __init__(
        self,
        api_key: str,
        endpoint: str,
        deployment_name: str,
        api_version: str = "2024-02-15-preview",
    ):
        self.api_key = api_key
        self.endpoint = endpoint
        self.deployment_name = deployment_name
        self.api_version = api_version

    @property
    def provider_name(self) -> str:
        return "azure_openai"

    def get_responses(self, items: list[dict], **kwargs) -> list[ModelResponseRaw]:
        if not self.api_key or not self.endpoint:
            raise ValueError(
                "AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT must be set. "
                "Check your .env file."
            )
        # Sprint 1: replace with AzureOpenAI client call.
        responses = []
        for item in items:
            responses.append(ModelResponseRaw(
                item_id=item.get("id", ""),
                prompt=item.get("prompt", ""),
                raw_output=f"[STUB] Azure mock response for: {item.get('prompt', '')[:60]}",
            ))
        return responses
