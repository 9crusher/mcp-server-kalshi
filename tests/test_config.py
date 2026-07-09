"""Tests for Settings: URL resolution, prod/demo detection, credentials, and caching.

Settings are constructed with ``_env_file=None`` so the developer's real ``.env`` never leaks
into assertions.
"""

from mcp_server_kalshi.config import Settings, get_settings


def _settings(**kwargs) -> Settings:
    return Settings(_env_file=None, **kwargs)


def test_rest_base_url_derived_from_env():
    assert _settings(KALSHI_ENV="demo").rest_base_url == (
        "https://demo-api.kalshi.co/trade-api/v2"
    )
    assert _settings(KALSHI_ENV="prod").rest_base_url == (
        "https://api.elections.kalshi.com/trade-api/v2"
    )


def test_base_url_override_wins_and_is_stripped():
    s = _settings(BASE_URL="https://proxy.internal/trade-api/v2/")
    assert s.rest_base_url == "https://proxy.internal/trade-api/v2"


def test_is_production_from_env():
    assert _settings(KALSHI_ENV="prod").is_production is True
    assert _settings(KALSHI_ENV="demo").is_production is False


def test_is_production_uses_demo_heuristic_on_override():
    # An explicit override URL containing "demo" is treated as non-prod even without KALSHI_ENV.
    assert (
        _settings(BASE_URL="https://demo-api.kalshi.co/trade-api/v2").is_production
        is False
    )
    assert (
        _settings(
            BASE_URL="https://api.elections.kalshi.com/trade-api/v2"
        ).is_production
        is True
    )


def test_env_label():
    assert _settings(KALSHI_ENV="prod").env_label == "PROD (real money)"
    assert _settings(KALSHI_ENV="demo").env_label == "DEMO (sandbox)"


def test_has_credentials_and_api_key_value():
    none = _settings()
    assert none.has_credentials is False
    assert none.api_key_value() is None

    both = _settings(KALSHI_API_KEY="key-id", KALSHI_PRIVATE_KEY_PATH="/tmp/k.pem")
    assert both.has_credentials is True
    assert both.api_key_value() == "key-id"

    partial = _settings(KALSHI_API_KEY="key-id")
    assert partial.has_credentials is False


def test_get_settings_is_cached():
    assert get_settings() is get_settings()
