from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # DB
    database_url: str = Field(
        default="sqlite+pysqlite:///./odds_value.db",
        validation_alias="DATABASE_URL",
    )
    db_echo: bool = False

    # api-sports
    api_sports_key: str | None = Field(default=None, repr=False)
    api_sports_base_url: str = "https://v1.american-football.api-sports.io"

    # odds-api
    odds_api_key: str | None = Field(default=None, repr=False)
    odds_api_base_url: str = "https://api.the-odds-api.com/v4"

    store_ingested_payloads: bool = True

    # -----------------------------
    # Required-key helpers
    # -----------------------------

    def require_api_sports_key(self) -> str:
        if not self.api_sports_key:
            raise RuntimeError("API_SPORTS_KEY is not set. Set it in the environment or .env file.")
        return self.api_sports_key

    def require_odds_api_key(self) -> str:
        if not self.odds_api_key:
            raise RuntimeError("ODDS_API_KEY is not set. Set it in the environment or .env file.")
        return self.odds_api_key


settings = Settings()
