"""Tests for BaseAPIClient's HTTP verbs, JSON/empty/error handling, and auth guard.

All requests go through an injected httpx.MockTransport (see conftest.make_client) — no network.
"""

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from mcp_server_kalshi.kalshi_client.base import (
    KalshiAPIError,
    load_private_key_from_file,
)
from mcp_server_kalshi.kalshi_client.client import KalshiAPIClient


async def test_verbs_map_to_http_methods(make_client):
    client, requests = make_client(lambda req: httpx.Response(200, json={"ok": True}))

    assert await client.get("/a") == {"ok": True}
    assert await client.post("/b", json={"x": 1}) == {"ok": True}
    assert await client.delete("/c") == {"ok": True}
    assert await client.patch("/d", json={"y": 2}) == {"ok": True}

    assert [(r.method, r.url.path) for r in requests] == [
        ("GET", "/trade-api/v2/a"),
        ("POST", "/trade-api/v2/b"),
        ("DELETE", "/trade-api/v2/c"),
        ("PATCH", "/trade-api/v2/d"),
    ]


async def test_get_forwards_query_params(make_client):
    client, requests = make_client(lambda req: httpx.Response(200, json={}))
    await client.get("/markets", params={"status": "open", "limit": 5})
    assert dict(requests[0].url.params) == {"status": "open", "limit": "5"}


async def test_post_forwards_json_body(make_client):
    import json as _json

    client, requests = make_client(lambda req: httpx.Response(200, json={}))
    await client.post("/orders", json={"ticker": "X-1", "count": "3"})
    assert _json.loads(requests[0].content) == {"ticker": "X-1", "count": "3"}


async def test_empty_body_returns_empty_dict(make_client):
    # A 200 with no content (e.g. some DELETEs) must yield {} rather than raising on json().
    client, _ = make_client(lambda req: httpx.Response(200))
    assert await client.delete("/portfolio/events/orders/abc") == {}


async def test_error_response_raises_kalshi_api_error(make_client):
    client, _ = make_client(
        lambda req: httpx.Response(400, json={"error": {"code": "bad_request"}})
    )
    with pytest.raises(KalshiAPIError) as exc_info:
        await client.get("/markets/NOPE")

    err = exc_info.value
    assert err.status_code == 400
    assert err.method == "GET"
    assert err.path == "/markets/NOPE"
    assert err.body == {"error": {"code": "bad_request"}}


async def test_error_response_falls_back_to_text_body(make_client):
    # Non-JSON error bodies are surfaced as text, not swallowed.
    client, _ = make_client(lambda req: httpx.Response(502, text="upstream boom"))
    with pytest.raises(KalshiAPIError) as exc_info:
        await client.get("/x")
    assert exc_info.value.body == "upstream boom"


async def test_authenticated_method_requires_credentials():
    # No credentials configured -> authed endpoint raises a clear ValueError before any HTTP.
    client = KalshiAPIClient(base_url="https://demo-api.kalshi.co/trade-api/v2")
    assert client.has_credentials is False
    with pytest.raises(ValueError, match="requires Kalshi credentials"):
        await client.get_balance()


def test_load_private_key_rejects_non_rsa_key(tmp_path):
    # A valid PEM that isn't RSA (here EC) must be rejected, not silently accepted.
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    key_file = tmp_path / "ec.pem"
    key_file.write_bytes(pem)

    with pytest.raises(ValueError, match="RSA"):
        load_private_key_from_file(str(key_file))
