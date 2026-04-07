from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Adaptive Tutor API"
    environment: str = "development"
    auth_session_days: int = 30
    database_url: str = Field(
        default="sqlite:///./adaptive_tutor.db",
        validation_alias=AliasChoices("ADAPTIVE_TUTOR_DATABASE_URL", "DATABASE_URL"),
    )

    model_config = SettingsConfigDict(env_prefix="ADAPTIVE_TUTOR_")


def get_settings() -> Settings:
    return Settings()
