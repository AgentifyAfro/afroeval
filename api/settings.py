from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    afroeval_env: str = "development"
    afroeval_secret_key: str = "dev-secret-change-in-production"
    afroeval_log_level: str = "INFO"

    # Database
    database_url: str = "postgresql://afroeval:afroeval@localhost:5432/afroeval_dev"

    # Model connectors
    openai_api_key: str = ""
    openai_default_model: str = "gpt-4o"

    azure_openai_api_key: str = ""
    azure_openai_endpoint: str = ""
    azure_openai_api_version: str = "2025-01-01-preview"
    azure_openai_deployment_name: str = "gpt-4.1-mini"

    anthropic_api_key: str = ""
    anthropic_default_model: str = "claude-haiku-4-5-20251001"

    gemini_api_key: str = ""

    # Africa Intelligence Layer judge
    ail_judge_model: str = "gpt-4.1-mini"
    ail_judge_provider: str = "azure_openai"

    # Reporting
    scorecard_output_dir: str = "./output/scorecards"

    # HITL
    label_studio_url: str = "http://localhost:8080"
    label_studio_api_key: str = ""

    @property
    def is_production(self) -> bool:
        return self.afroeval_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
