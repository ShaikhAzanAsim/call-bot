"""Environment-driven settings. Secrets stay in the environment, never in code."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    database_url: str = "sqlite:///./data/patients.db"
    seed_on_startup: bool = True
    vapi_webhook_secret: str = ""
    vapi_assistant_id: str = ""
    vapi_model: str = "gpt-4o-mini"
    vapi_voice_provider: str = "vapi"
    vapi_voice_id: str = "Elliot"
    public_base_url: str = ""
    draft_resume_hours: int = 24
    census_timeout_seconds: float = 1.5
    simulate_db_write_failure: bool = False
    log_level: str = "INFO"
    eval_llm_api_key: str = ""
    eval_llm_base_url: str = "https://api.openai.com/v1"
    eval_llm_model: str = "gpt-4o-mini"

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()


ROOT = Path(__file__).resolve().parent.parent
PROMPT_PATH = ROOT / "app" / "voice" / "prompts" / "system_prompt.md"
ZIP3_PATH = ROOT / "app" / "services" / "data" / "zip3_by_state.json"
