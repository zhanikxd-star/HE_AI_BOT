"""Runtime settings. Secrets come only from the environment."""

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LOCAL_JWT_SECRET = "local-only-not-for-production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "local"
    database_url: str = "postgresql+psycopg://hr:hr@localhost:5432/hr"
    jwt_secret: str = ""
    jwt_ttl_minutes: int = 720
    bootstrap_admin_email: str | None = None
    bootstrap_admin_password: str | None = None
    telegram_bot_token: str | None = None
    telegram_bot_username: str | None = "magripaharip_bot"
    corporate_chat_id: str | None = "-1002615527142"
    super_admin_telegram_username: str | None = "Kapanov_30"
    openai_api_key: str | None = None
    notion_api_key: str | None = None
    llm_base_url: str = "https://api.openai.com/v1"
    llm_provider: str = "openai"
    cors_origins: str = "http://localhost:3000"
    worker_interval_seconds: int = 30
    telegram_send_interval_seconds: float = 0.05
    telegram_max_attempts: int = 3

    @field_validator(
        "telegram_bot_token",
        "telegram_bot_username",
        "corporate_chat_id",
        "super_admin_telegram_username",
        "openai_api_key",
        "notion_api_key",
        "bootstrap_admin_email",
        "bootstrap_admin_password",
        mode="before",
    )
    @classmethod
    def empty_to_none(cls, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator("jwt_secret", mode="before")
    @classmethod
    def jwt_blank(cls, value: object) -> str:
        if value is None:
            return ""
        return str(value).strip()

    def resolved_jwt_secret(self) -> str:
        if self.jwt_secret:
            return self.jwt_secret
        if self.app_env == "local":
            return LOCAL_JWT_SECRET
        raise RuntimeError("JWT_SECRET is required when APP_ENV is not local")

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token)

    @property
    def llm_live_configured(self) -> bool:
        return bool(self.openai_api_key) and self.llm_provider == "openai"


@lru_cache
def get_settings() -> Settings:
    return Settings()
