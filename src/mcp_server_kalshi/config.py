from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, SecretStr
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings with environment variable loading and validation."""

    BASE_URL: str = Field(
        default="https://api.elections.kalshi.com",
        description="Base URL for the Kalshi API",
    )
    KALSHI_PRIVATE_KEY_PATH: str = Field(
        default="./rsa.key", description="Path to the Kalshi private key"
    )
    KALSHI_API_KEY: SecretStr = Field(..., description="Kalshi API key")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore")


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
