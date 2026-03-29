from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from cryptography.fernet import Fernet
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = Field(default="MCP Hub + Wordstat", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    debug: bool = Field(default=True, alias="DEBUG")
    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8000, alias="PORT")
    base_url: str = Field(default="http://localhost:8000", alias="BASE_URL")
    database_url: str = Field(default="sqlite:///./data/app.db", alias="DATABASE_URL")
    master_encryption_key: str = Field(default="", alias="MASTER_ENCRYPTION_KEY")
    wordstat_api_base_url: str = Field(
        default="https://searchapi.api.cloud.yandex.net/v2/wordstat",
        alias="WORDSTAT_API_BASE_URL",
    )
    admin_username: str = Field(default="admin", alias="ADMIN_USERNAME")
    admin_password: str = Field(default="change_me", alias="ADMIN_PASSWORD")

    @property
    def templates_dir(self) -> Path:
        return Path(__file__).parent / "web" / "templates"

    @property
    def static_dir(self) -> Path:
        return Path(__file__).parent / "static"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if not settings.master_encryption_key:
        settings.master_encryption_key = Fernet.generate_key().decode()
    return settings
