"""Configuration loaded from environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # SkillNet API connection
    API_URL: str = "http://localhost:8000"
    SKILLNET_API_KEY: str = ""

    # LLM for the orchestrator
    LLM_BASE_URL: str = "https://api.openai.com/v1"
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "gpt-4o-mini"

    # A2A server
    A2A_PORT: int = 5000
    A2A_AUTH_KEY: str = ""  # bearer token external agents must provide
    A2A_AGENT_URL: str = "http://localhost:5000"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
