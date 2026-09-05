"""Tests for credential scrubbing and KalshiAPIError sanitization."""

from mcp_server_kalshi.errors import KalshiAPIError, redact_secrets


def test_redact_secrets_empty_or_none():
    assert redact_secrets("") == ""
    assert redact_secrets(None) is None  # type: ignore[arg-type]


def test_redact_secrets_scrubs_keys_and_tokens():
    text_with_rsa = (
        "Error in request: -----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEowIBAAKCAQEA0Y8\n"
        "-----END RSA PRIVATE KEY-----\n"
        "failed."
    )
    scrubbed = redact_secrets(text_with_rsa)
    assert "-----BEGIN RSA PRIVATE KEY-----" not in scrubbed
    assert "[REDACTED RSA PRIVATE KEY]" in scrubbed

    text_with_bearer = "Authorization: Bearer my_secret_token_12345"
    assert "my_secret_token" not in redact_secrets(text_with_bearer)
    assert "Bearer [REDACTED]" in redact_secrets(text_with_bearer)

    text_with_headers = "KALSHI-ACCESS-KEY: secret_api_key_abc"
    assert "secret_api_key_abc" not in redact_secrets(text_with_headers)

    text_with_api_key = '{"api_key": "supersecretkey123"}'
    assert "supersecretkey123" not in redact_secrets(text_with_api_key)


def test_kalshi_api_error_sanitization():
    err = KalshiAPIError(
        status_code=401,
        method="POST",
        path="/portfolio/orders",
        body="Bearer secret_token_abc is invalid",
    )
    assert err.status_code == 401
    assert err.method == "POST"
    assert err.path == "/portfolio/orders"
    assert "secret_token_abc" not in str(err)
    assert "Bearer [REDACTED]" in str(err)

    dict_err = KalshiAPIError(
        status_code=400,
        method="GET",
        path="/test",
        body={"error": "invalid parameter"},
    )
    assert "invalid parameter" in str(dict_err)
