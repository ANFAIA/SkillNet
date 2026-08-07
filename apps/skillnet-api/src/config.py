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

    # Vision model for describing images in uploaded PDFs. Must support
    # multimodal input (image_url message type). When empty, image description
    # is disabled and PDFs are processed text-only — no error, just no image
    # descriptions in the document. Gemini Flash, GPT-4o, Claude Sonnet all work.
    VISION_MODEL: str | None = None

    # Provider retries. Read only by src/llm/client.py.
    #
    # These exist as settings because the right values are a property of the *plan*, not
    # of the code: a tokens-per-minute quota resets after a minute, so a backoff that
    # gives up in twelve seconds cannot succeed. Measured on Groq's free tier
    # (6000 TPM) on 2026-07-27: a course generation died at `review_quality` against a
    # limit the provider itself said would clear in 27.91 s.
    LLM_MAX_ATTEMPTS: int = 5
    #: Only used when the provider does not say how long to wait; it usually does.
    LLM_RETRY_BASE_SECONDS: float = 4.0
    #: Ceiling on a single wait. Above a minute, a TPM window has already reset.
    LLM_RETRY_MAX_WAIT_SECONDS: float = 90.0

    # Reasoning models (o-series, gpt-oss, deepseek-reasoner...) emit their chain of
    # thought into a separate field that is billed against the SAME `max_tokens` as the
    # answer. Measured on Groq's openai/gpt-oss-120b at max_tokens=1200: it sometimes
    # spent the whole budget thinking and returned an empty `content`, which the runtime
    # read as an invalid program and sent through the repair loop for nothing.
    # Both knobs are settings and not constants because tuning them is a prompt-tuning
    # session's business, and a redeploy per experiment is what kills that loop.
    # `none` = never send the parameter. Read only by src/llm/client.py.
    LLM_REASONING_EFFORT: Literal["none", "low", "medium", "high"] = "low"
    # Extra completion budget handed to a reasoning model on top of what the call site
    # asked for. The call site's number budgets the *answer*; the thinking is invisible
    # to it. 0 disables the headroom (the empty-response retry still applies).
    LLM_REASONING_TOKEN_HEADROOM: int = 2048

    # v2 recorded-fixture LLM (no API keys needed). Fixtures live inside the package
    # so they travel into the Docker image with `src`.
    LLM_FIXTURE_DIR: str = "src/llm/fixture_data"
    LLM_FIXTURE_MODE: Literal["replay", "record"] = "replay"

    # Embeddings
    #
    # `EMBEDDING_DIMENSIONS` **describes** the schema, it does not decide it. The
    # `document_chunks.embedding` column is `vector(768)`, pinned by hand in migration
    # 0008, and the ORM deliberately declares `Vector()` with no size so the database stays
    # the only place that number lives.
    #
    # What this setting does is tell the *provider* how many dimensions to return. So it has
    # to match the column, and nothing in Python enforces that — Postgres rejects the
    # INSERT, and `services/embedding_check.py` compares the two at startup precisely
    # because that rejection is otherwise invisible. Moving to a model with a different
    # dimension is a migration plus a re-ingestion, not a `.env` edit; 0008 records what
    # happened when this number was read from the environment.
    #
    # The default pair is chosen so that **one OpenAI key is enough**:
    # `text-embedding-3-small` returns 1536 out of the box, but it accepts the
    # `dimensions` parameter and `EmbeddingService` sends it, so it returns 768 and fits
    # the column with no migration. Any model whose native output is already 768
    # (multilingual-e5-base, nomic-embed-text, paraphrase-multilingual) does just as well.
    EMBEDDING_BASE_URL: str = "https://api.openai.com/v1"
    EMBEDDING_API_KEY: str = ""
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIMENSIONS: int = 768

    # TTS (provider-agnostic, follows the litellm pattern)
    TTS_PROVIDER: str = "disabled"
    TTS_API_KEY: str = ""
    TTS_VOICE: str = "alloy"
    TTS_LANGUAGE: str = "es"
    TTS_CACHE_DIR: str = "data/tts_cache"

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

    # Dialect asked of the LLM and parser used. One valid value in this PR.
    RENDER_BACKEND: Literal["openui"] = "openui"
    # OpenUI's reactive layer ($state, Query, Mutation, Action, builtins). OFF, and the
    # price of switching it on is stated in docs/design/openui-adoption.md §3: the model
    # has to be taught the whole reactive syntax at once (the prompt flags do not split),
    # and a structural property ("the grammar cannot express it") turns into a contract to
    # re-verify on every @openuidev release. Read by src.render.gate.check_program.
    RENDER_ALLOW_REACTIVE: bool = False

    # Multi-agent render pipeline (experimental). When true, genera_ui uses four
    # specialized agents instead of one monolithic call. Falls back to monolithic
    # on retry. Set MULTI_AGENT_RENDER=true in .env to activate.
    MULTI_AGENT_RENDER: bool = False

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
