"""Tests for RSA-PSS signing and the Kalshi auth header/signing-path construction."""

import base64

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from mcp_server_kalshi.kalshi_client.base import KalshiAuth, sign_pss_text


def _make_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def test_sign_pss_text_verifies_with_public_key():
    key = _make_key()
    msg = "1700000000000GET/trade-api/v2/portfolio/balance"
    sig = sign_pss_text(key, msg)
    # A valid signature verifies against the public key (raises if not).
    key.public_key().verify(
        base64.b64decode(sig),
        msg.encode(),
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH
        ),
        hashes.SHA256(),
    )


def test_auth_flow_signs_path_without_query():
    key = _make_key()
    auth = KalshiAuth(key, "my-key-id")
    request = httpx.Request(
        "GET",
        "https://demo-api.kalshi.co/trade-api/v2/portfolio/orders?limit=5&status=resting",
    )

    flow = auth.auth_flow(request)
    signed_request = next(flow)

    assert signed_request.headers["KALSHI-ACCESS-KEY"] == "my-key-id"
    ts = signed_request.headers["KALSHI-ACCESS-TIMESTAMP"]
    sig = signed_request.headers["KALSHI-ACCESS-SIGNATURE"]

    # The signed message must exclude the query string.
    signed_path = "/trade-api/v2/portfolio/orders"
    key.public_key().verify(
        base64.b64decode(sig),
        (ts + "GET" + signed_path).encode(),
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH
        ),
        hashes.SHA256(),
    )


def test_load_private_key_roundtrip(tmp_path):
    from mcp_server_kalshi.kalshi_client.base import load_private_key_from_file

    key = _make_key()
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    key_file = tmp_path / "rsa.key"
    key_file.write_bytes(pem)

    loaded = load_private_key_from_file(str(key_file))
    assert isinstance(loaded, rsa.RSAPrivateKey)  # not a string repr (the old bug)
