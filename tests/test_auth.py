"""Tests for RSA-PSS and Ed25519 signing and the Kalshi auth header/signing-path construction."""

import base64

import httpx
import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, padding, rsa

from mcp_server_kalshi.kalshi_client.base import KalshiAuth, sign_pss_text, sign_text


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


def test_sign_text_rsa_still_uses_pss_max_salt():
    key = _make_key()
    msg = "1700000000000GET/trade-api/v2/portfolio/balance"
    sig = sign_text(key, msg)
    key.public_key().verify(
        base64.b64decode(sig),
        msg.encode(),
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH
        ),
        hashes.SHA256(),
    )


def test_sign_text_ed25519_verifies_with_public_key():
    key = ed25519.Ed25519PrivateKey.generate()
    msg = "1700000000000GET/trade-api/v2/portfolio/balance"
    sig = base64.b64decode(sign_text(key, msg))
    assert len(sig) == 64
    key.public_key().verify(sig, msg.encode())


def test_auth_flow_ed25519_signs_path_without_query():
    key = ed25519.Ed25519PrivateKey.generate()
    auth = KalshiAuth(key, "my-key-id")
    request = httpx.Request(
        "GET",
        "https://demo-api.kalshi.co/trade-api/v2/portfolio/orders?limit=5&status=resting",
    )

    signed_request = next(auth.auth_flow(request))

    assert signed_request.headers["KALSHI-ACCESS-KEY"] == "my-key-id"
    ts = signed_request.headers["KALSHI-ACCESS-TIMESTAMP"]
    sig = signed_request.headers["KALSHI-ACCESS-SIGNATURE"]
    key.public_key().verify(
        base64.b64decode(sig), (ts + "GET/trade-api/v2/portfolio/orders").encode()
    )


def test_sign_text_rejects_unsupported_key_type():
    key = ec.generate_private_key(ec.SECP256R1())
    with pytest.raises(ValueError, match="RSA or Ed25519"):
        sign_text(key, "1700000000000GET/trade-api/v2/portfolio/balance")  # type: ignore[arg-type]


def test_load_ed25519_private_key_pkcs8(tmp_path):
    from mcp_server_kalshi.kalshi_client.base import load_private_key_from_file

    key = ed25519.Ed25519PrivateKey.generate()
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    # Same banner as a PKCS#8 RSA key, so the type must come from the parsed key.
    assert pem.startswith(b"-----BEGIN PRIVATE KEY-----")
    key_file = tmp_path / "ed25519.key"
    key_file.write_bytes(pem)

    loaded = load_private_key_from_file(str(key_file))
    assert isinstance(loaded, ed25519.Ed25519PrivateKey)
