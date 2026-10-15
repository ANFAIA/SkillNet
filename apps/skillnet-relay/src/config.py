from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # The only place the GitHub token lives. A fine-grained token with Issues: write on the
    # one repo, or a GitHub App installation token.
    GITHUB_TOKEN: str = ""
    GITHUB_REPO: str = "ANFAIA/SkillNet"

    # The judge. Any litellm model; give it its own key with a spend limit.
    LLM_MODEL: str = "deepseek/deepseek-chat"
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str | None = None

    DB_PATH: str = "/data/relay.db"

    # Off switch: when false every report is refused with 503 and nothing reaches GitHub.
    ENABLED: bool = True

    # Limits. The global one bounds what an abuser can spend; the others keep one instance or
    # one address from using it up for everybody.
    GLOBAL_DAILY_CAP: int = 200
    INSTANCE_DAILY_CAP: int = 20
    IP_HOURLY_CAP: int = 10

    # The raw text of a report is deleted after this many days; the verdict and the issue link stay.
    RAW_RETENTION_DAYS: int = 30


settings = Settings()
