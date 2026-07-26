from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEV_SECRET_KEY = "dev-insecure-secret-key-change-me-in-production"


class Settings(BaseSettings):
    # App environment (validated before SECRET_KEY so its validator can read it)
    ENVIRONMENT: str = "development"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://skillnet:skillnet@localhost:5432/skillnet"

    # Auth
    SECRET_KEY: str = _DEV_SECRET_KEY
    SESSION_LIFETIME_SECONDS: int = 604800
    COOKIE_NAME: str = "skillnet_session"
    COOKIE_SECURE: bool = True

    # LLM (defaults, overridable per org)
    LLM_BASE_URL: str = "https://api.openai.com/v1"
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "gpt-4o-mini"
    LLM_GENERATION_MODEL: str | None = None
    LLM_TUTOR_MODEL: str | None = None
    LLM_EVAL_MODEL: str | None = None
    # v2 two-tier runtime router. Empty -> both tiers fall back to LLM_MODEL.
    LLM_RUNTIME_FAST_MODEL: str | None = None
    LLM_RUNTIME_HEAVY_MODEL: str | None = None

    # v2 recorded-fixture LLM (no API keys needed). Fixtures live inside the package
    # so they travel into the Docker image with `src`.
    LLM_FIXTURE_DIR: str = "src/llm/fixture_data"
    LLM_FIXTURE_MODE: Literal["replay", "record"] = "replay"

    # Embeddings
    EMBEDDING_BASE_URL: str = "https://api.openai.com/v1"
    EMBEDDING_API_KEY: str = ""
    EMBEDDING_MODEL: str = "multilingual-e5-small"
    EMBEDDING_DIMENSIONS: int = 384

    # File uploads
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE_MB: int = 50

    # App
    DEBUG: bool = False
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]
    LOG_LEVEL: str = "INFO"

    # Bootstrap
    ADMIN_EMAIL: str | None = None
    ADMIN_PASSWORD: str | None = None
    ORG_NAME: str | None = None

    # Agent-to-agent internal API key (auto-provisioned on startup)
    A2A_INTERNAL_API_KEY: str | None = None

    # v2 dynamic courses. `off` = production exactly as it is today. Read only by the
    # route guards and by src.services.course_delivery.resolve_delivery.
    DYNAMIC_COURSES_MODE: Literal["off", "shadow", "on"] = "off"
    # Dialect asked of the LLM and parser used. One valid value in this PR.
    RENDER_BACKEND: Literal["openui"] = "openui"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("SECRET_KEY")
    @classmethod
    def _validate_secret_key(cls, value: str, info) -> str:
        environment = info.data.get("ENVIRONMENT", "development")
        if environment == "production" and len(value) < 32:
            raise ValueError(
                "SECRET_KEY must be at least 32 characters in production"
            )
        return value


settings = Settings()
