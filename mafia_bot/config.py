from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    bot_token: str = Field(alias="BOT_TOKEN")
    database_url: str = Field(
        default="sqlite+aiosqlite:///data/mafia.db",
        alias="DATABASE_URL",
    )
    admins: list[int] = Field(default_factory=list, alias="ADMINS")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    web_enabled: bool = Field(default=True, alias="WEB_ENABLED")
    web_host: str = Field(default="0.0.0.0", alias="WEB_HOST")
    web_port: int = Field(default=8000, alias="WEB_PORT")
    public_base_url: str = Field(default="http://localhost:8000", alias="PUBLIC_BASE_URL")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @field_validator("admins", mode="before")
    @classmethod
    def parse_admins(cls, value: str | list[int] | None) -> list[int]:
        if value is None or value == "":
            return []
        if isinstance(value, list):
            return value
        return [int(item.strip()) for item in value.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
