from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.personalization.selection_policy import SelectionExecution, SelectionStrategy

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

    # Sign in with Google (OAuth 2.0 authorization code + PKCE).
    #
    # Empty CLIENT_ID or CLIENT_SECRET disables the whole feature: the routes answer
    # 404 and the SPA never shows the button. What Google does with the resulting
    # identity depends on the organization's `workspace_mode`, not on config — see
    # src/services/google_oauth.py.
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    #: Absolute URL of this API's callback, registered verbatim as an authorized
    #: redirect URI in the Google Cloud console. Google rejects the exchange on any
    #: mismatch, down to the trailing slash. Empty means "derive it from the incoming
    #: request", which is right behind a single known front door and wrong behind a
    #: proxy that rewrites Host, so set it explicitly in any real deployment.
    GOOGLE_REDIRECT_URI: str = ""
    #: Where the browser lands after the callback has set the session cookie. A path
    #: on the SPA, not a URL, so it cannot be turned into an open redirect.
    GOOGLE_POST_LOGIN_PATH: str = "/"
    #: Where the browser lands when the callback refuses the identity. The reason
    #: travels as a `google_error` query parameter for the SPA to translate.
    GOOGLE_LOGIN_ERROR_PATH: str = "/login"

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
    # Empty selects the provider's own default (Azure: es-ES-ElviraNeural).
    TTS_VOICE: str = ""
    TTS_LANGUAGE: str = "es"
    TTS_CACHE_DIR: str = "data/tts_cache"
    # Azure Speech intentionally has no inferred public-cloud endpoint: deployments may
    # use sovereign clouds or private endpoints, so both values must be explicit.
    TTS_AZURE_REGION: str = ""
    TTS_AZURE_ENDPOINT: str = ""
    TTS_TIMEOUT_SECONDS: float = Field(default=30.0, gt=0)

    # Rich media artifacts (NotebookLM spine).
    #
    # Generated bytes (podcast mp3, infographic/cover png, video mp4) are stored on disk
    # keyed by content hash, mirroring TTS_CACHE_DIR: the same render is never written
    # twice and the asset route can be cached hard.
    MEDIA_ASSETS_DIR: str = "data/media_assets"
    # Images extracted from uploaded documents (the customer's OWN diagrams and photos),
    # kept so a course can reuse them instead of inventing an illustration. A separate
    # store from MEDIA_ASSETS_DIR on purpose: these are source material and die with the
    # document they came from, while generated assets outlive it. In Docker this points
    # inside the `uploads` volume rather than at a fourth one — same lifetime as the
    # original file, same ownership repair, no new mount to get wrong.
    SOURCE_IMAGES_DIR: str = "data/source_images"
    # Image generation. Default is NotebookLM's actual engine family ("Nano Banana");
    # gpt-image-1 on the existing OpenAI key is the fallback selectable per call.
    IMAGE_MODEL: str = "openrouter/google/gemini-2.5-flash-image"
    IMAGE_FALLBACK_MODEL: str = "gpt-image-1"
    # The image provider's own key. Set it when the image account is NOT the text account:
    # without it the image call falls back to OPENROUTER_API_KEY (openrouter/* models) or
    # LLM_API_KEY (everything else), which silently sends e.g. a Groq key to OpenAI for
    # gpt-image-1. See src/services/media/images.api_key_for.
    IMAGE_API_KEY: str = ""
    # Read by litellm for openrouter/* models. Lives in the repo-root .env.
    OPENROUTER_API_KEY: str = ""

    # Audio Overview / Podcast generator (roadmap §2a).
    #
    # The script agent goes through litellm like every other LLM call. Left BLANK it uses
    # the app's main LLM_MODEL (same provider/key as the rest of the app) — the portable
    # default, so a DeepSeek/Ollama-only deployment works out of the box. Set it explicitly
    # (e.g. "gpt-4o-mini") only when a cheaper dedicated model reachable with the SAME key
    # is wanted; a value whose provider does not match LLM_API_KEY will fail the call.
    PODCAST_SCRIPT_MODEL: str = ""
    # ElevenLabs Text-to-Dialogue model id for the primary (single-call) voice path.
    PODCAST_DIALOGUE_MODEL: str = "eleven_v3"
    # The two fixed demo voices. Config-overridable so a deployment can pick its own hosts.
    # Defaults are ElevenLabs multilingual voices (Sarah / Antoni) that speak Spanish well.
    PODCAST_VOICE_A: str = "EXAVITQu4vr4xnSDxMaL"
    PODCAST_VOICE_B: str = "ErXwobaYiN019PkySvjV"

    # Slide Deck and Infographic content agents (roadmap §2c / §2d). Like the podcast
    # script agent, each is a small strict-JSON litellm call and defaults to the cheap
    # gpt-4o-mini rather than the course-generation model. The KEY discipline (§2d): the
    # facts these produce are structured JSON we render ourselves — never text baked into a
    # generated image.
    # Left BLANK these use the app's main LLM_MODEL (same key), like PODCAST_SCRIPT_MODEL —
    # the portable default. Set explicitly only for a cheaper model reachable with the SAME
    # key as LLM_API_KEY.
    SLIDES_MODEL: str = ""
    INFOGRAPHIC_MODEL: str = ""

    # Video Overview generator (roadmap §2b): narrated slides as HTML, NOT a real video
    # model. It reuses the slide deck content stage, then a small strict-JSON litellm call
    # writes one short narration line per slide (grounded, carrying citation_ids). Defaults
    # to the cheap gpt-4o-mini, like the other media content agents. The per-slide voice
    # reuses the podcast TTS path (single host = PODCAST_VOICE_A); no separate voice config.
    VIDEO_NARRATION_MODEL: str = "gpt-4o-mini"

    # File uploads
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE_MB: int = 50

    # App
    DEBUG: bool = False
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]
    LOG_LEVEL: str = "INFO"

    # Bootstrap
    #: Minutes that the public `POST /setup` stays open after a boot with no owner.
    #: 0 disables the limit. See src/core/setup_window.py for why there is one at all.
    SETUP_WINDOW_MINUTES: int = 30
    ADMIN_EMAIL: str | None = None
    ADMIN_PASSWORD: str | None = None
    ORG_NAME: str | None = None
    # How this deployment is used. Read only when creating the organization on a
    # fresh deployment; existing organizations keep their stored value. A stable
    # per-deployment capability, never inferred from user count. See
    # docs/design/audience-modes.md.
    WORKSPACE_MODE: Literal["organization", "individual"] = "organization"

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

    # Resolve the learning ExperienceIntent against the complete component inventory,
    # then expose only the 3-5 renderer-safe candidates to the generation prompt.
    # The inventory remains complete; this flag only narrows the LLM boundary.
    RUNTIME_COMPONENT_SHORTLIST: bool = True
    # Versioned policy applied to the real pedagogically-gated ranking. top5/v1 preserves
    # the pre-policy runtime behaviour. dual-agent and conditional-specialist are forced
    # to shadow until the runtime has an independent second producer/ranking.
    RUNTIME_SELECTION_STRATEGY: SelectionStrategy = SelectionStrategy.TOP5
    RUNTIME_SELECTION_EXECUTION: SelectionExecution = SelectionExecution.LIVE

    # Isolated rollout for on-the-fly EpisodeBrief generation. Render identities are
    # partitioned so adaptive episodes never reuse or overwrite ScreenScheme renders.
    ADAPTIVE_EPISODES: bool = False

    #: At startup, delete a bounded batch of cached renders that a PROMPT_VERSION bump
    #: made unreachable and that nothing references. Off leaves them on disk forever;
    #: the reclamation is optional by design, because it is a deletion. See
    #: src/services/render_retention.py for exactly what it will and will not remove.
    RENDER_CACHE_SWEEP: bool = True

    #: Force the onboarding wizard for learners without a completed profile. Off is a
    #: testing convenience: learners enter straight to their home on the default profile
    #: bucket (they can still onboard later). The frontend reads this via /setup/status.
    ONBOARDING_ENABLED: bool = True

    # Router semantico de funciones de contenido (prototipo, fases 3/4 de
    # docs/design/arquitectura-componentes-funcional.md). Cuando esta activo,
    # decide_formato hace una llamada corta que clasifica QUE HACE el material
    # (contrastar / variar / explorar) y antepone esa senal a las deterministas. Las tres
    # funciones que ya cubren las regex no se le preguntan: son gratis y estan calibradas.
    # Set SEMANTIC_ROUTER=true en .env para activarlo.
    SEMANTIC_ROUTER: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("SECRET_KEY")
    @classmethod
    def _validate_secret_key(cls, value: str, info) -> str:
        environment = info.data.get("ENVIRONMENT", "development")
        if environment == "production":
            # The length check alone was not enough: the development default is 47
            # characters, so it sailed through. Compose demands the variable
            # (`${SECRET_KEY:?...}`), but a deployment outside Compose — uvicorn direct, k8s,
            # systemd — booted in production with a key published in this repository.
            # That key derives, via PBKDF2, the Fernet key that encrypts each
            # organization's LLM provider credentials, which is the whole point of
            # src/core/secrets.py.
            if value == _DEV_SECRET_KEY:
                raise ValueError(
                    "SECRET_KEY is still the development default. Generate one: "
                    'python -c "import secrets; print(secrets.token_urlsafe(32))"'
                )
            if len(value) < 32:
                raise ValueError(
                    "SECRET_KEY must be at least 32 characters in production"
                )
        return value


settings = Settings()
