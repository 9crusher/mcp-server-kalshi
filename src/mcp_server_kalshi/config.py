from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Kalshi Trade API base URLs. See https://docs.kalshi.com/getting_started/api_environments
ENV_REST_BASE = {
    "prod": "https://api.elections.kalshi.com/trade-api/v2",
    "demo": "https://demo-api.kalshi.co/trade-api/v2",
}
ENV_WS_BASE = {
    "prod": "wss://api.elections.kalshi.com/trade-api/ws/v2",
    "demo": "wss://demo-api.kalshi.co/trade-api/ws/v2",
}


class Settings(BaseSettings):
    """Application settings loaded from environment variables and/or a .env file.

    Safety-by-default: the server targets Kalshi's DEMO (sandbox) environment unless
    ``KALSHI_ENV=prod`` is set explicitly. Credentials are optional so that public
    market/rules tools work with no keys configured; authenticated tools fail with a
    clear error when creds are absent.
    """

    KALSHI_ENV: Literal["demo", "prod"] = Field(
        default="demo",
        description="Which Kalshi environment to target. 'demo' (sandbox, default) or 'prod' (real money).",
    )
    # Optional explicit override of the REST base URL. When unset it is derived from KALSHI_ENV.
    BASE_URL: str | None = Field(
        default=None,
        description="Explicit REST base URL override (including /trade-api/v2). Derived from KALSHI_ENV when unset.",
    )
    KALSHI_API_KEY: SecretStr | None = Field(
        default=None,
        description="Kalshi API key ID (required only for authenticated tools).",
    )
    KALSHI_PRIVATE_KEY_PATH: str | None = Field(
        default=None,
        description="Path to the Kalshi RSA private key PEM file (required only for authenticated tools).",
    )

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    @property
    def rest_base_url(self) -> str:
        """Resolved REST base URL (explicit override wins, else derived from env)."""
        if self.BASE_URL:
            return self.BASE_URL.rstrip("/")
        return ENV_REST_BASE[self.KALSHI_ENV]

    @property
    def ws_base_url(self) -> str:
        return ENV_WS_BASE[self.KALSHI_ENV]

    @property
    def has_credentials(self) -> bool:
        return (
            self.KALSHI_API_KEY is not None and self.KALSHI_PRIVATE_KEY_PATH is not None
        )

    @property
    def is_production(self) -> bool:
        # Treat an explicit prod override URL as production too.
        if self.BASE_URL:
            return "demo" not in self.BASE_URL.lower()
        return self.KALSHI_ENV == "prod"

    @property
    def env_label(self) -> str:
        return "PROD (real money)" if self.is_production else "DEMO (sandbox)"

    def api_key_value(self) -> str | None:
        return self.KALSHI_API_KEY.get_secret_value() if self.KALSHI_API_KEY else None


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings instance (constructed lazily on first use)."""
    return Settings()
