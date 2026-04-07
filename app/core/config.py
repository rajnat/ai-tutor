from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Adaptive Tutor API"
    environment: str = "development"
    auth_session_days: int = 30
    admin_email_allowlist: str = ""
    auth_cookie_name: str = "adaptive_tutor_session"
    csrf_cookie_name: str = "adaptive_tutor_csrf"
    csrf_header_name: str = "X-CSRF-Token"
    auth_cookie_secure: bool = False
    cors_allowed_origins: str = "http://localhost:3000,http://localhost:3001"
    llm_provider: str = "openai"
    openai_model: str = "gpt-4.1-mini"
    openai_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("ADAPTIVE_TUTOR_OPENAI_API_KEY", "OPENAI_API_KEY"),
    )
    openai_base_url: str = Field(
        default="https://api.openai.com/v1",
        validation_alias=AliasChoices("ADAPTIVE_TUTOR_OPENAI_BASE_URL", "OPENAI_BASE_URL"),
    )
    database_url: str = Field(
        default="sqlite:///./adaptive_tutor.db",
        validation_alias=AliasChoices("ADAPTIVE_TUTOR_DATABASE_URL", "DATABASE_URL"),
    )

    model_config = SettingsConfigDict(env_prefix="ADAPTIVE_TUTOR_", populate_by_name=True)


def get_settings() -> Settings:
    return Settings()
