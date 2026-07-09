import base64
import time
from typing import Any

import httpx
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa


def load_private_key_from_file(file_path: str) -> rsa.RSAPrivateKey:
    """Load an RSA private key object from a PEM file."""
    with open(file_path, "rb") as key_file:
        private_key = serialization.load_pem_private_key(
            key_file.read(), password=None, backend=default_backend()
        )
    if not isinstance(private_key, rsa.RSAPrivateKey):
        raise ValueError(
            f"Expected an RSA private key in {file_path}, got {type(private_key).__name__}"
        )
    return private_key


def sign_pss_text(private_key: rsa.RSAPrivateKey, text: str) -> str:
    """Sign text with RSA-PSS (MGF1-SHA256, max salt) and base64-encode it.

    This is the signature scheme Kalshi requires for the KALSHI-ACCESS-SIGNATURE header.
    """
    signature = private_key.sign(
        text.encode(),
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH
        ),
        hashes.SHA256(),
    )
    return base64.b64encode(signature).decode()


class KalshiAuth(httpx.Auth):
    """Signs each request with the Kalshi API-key headers.

    The signed message is ``timestamp_ms + METHOD + path`` where ``path`` includes the
    ``/trade-api/v2`` prefix but EXCLUDES the query string.
    """

    def __init__(self, private_key: rsa.RSAPrivateKey, api_key: str):
        self._private_key = private_key
        self._api_key = api_key

    def auth_flow(self, request: httpx.Request):
        method = request.method
        # raw_path includes the query string; Kalshi signs the path only.
        path = request.url.raw_path.decode().split("?", 1)[0]
        timestamp = str(int(time.time() * 1000))
        msg_string = timestamp + method + path
        signature = sign_pss_text(self._private_key, msg_string)

        request.headers["KALSHI-ACCESS-KEY"] = self._api_key
        request.headers["KALSHI-ACCESS-SIGNATURE"] = signature
        request.headers["KALSHI-ACCESS-TIMESTAMP"] = timestamp
        yield request


class KalshiAPIError(Exception):
    """Raised when the Kalshi API returns a non-2xx response, carrying the error body."""

    def __init__(self, status_code: int, method: str, path: str, body: Any):
        self.status_code = status_code
        self.method = method
        self.path = path
        self.body = body
        super().__init__(f"Kalshi API {status_code} on {method} {path}: {body}")


class BaseAPIClient:
    """A minimal async HTTP client for the Kalshi Trade API.

    ``base_url`` must be the fully-qualified API base including the version prefix, e.g.
    ``https://demo-api.kalshi.co/trade-api/v2``. Endpoint paths passed to the request
    helpers are relative to that (e.g. ``/portfolio/balance``).

    Authentication is optional: when both ``api_key`` and ``private_key_path`` are
    provided every request is RSA-PSS signed; otherwise requests are sent unsigned, which
    is fine for public market-data endpoints. Authenticated endpoints raise a clear error
    if creds are missing.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        private_key_path: str | None = None,
        timeout: int = 30,
    ):
        self._base_url: str = base_url.rstrip("/")
        self._timeout: int = timeout
        self._api_key: str | None = api_key
        self._private_key: rsa.RSAPrivateKey | None = (
            load_private_key_from_file(private_key_path) if private_key_path else None
        )
        self._client: httpx.AsyncClient | None = None

    @property
    def has_credentials(self) -> bool:
        return self._api_key is not None and self._private_key is not None

    def _ensure_client(self) -> httpx.AsyncClient:
        """Lazily create the persistent httpx client (attaching auth when available)."""
        if self._client is None:
            # Inline (rather than self.has_credentials) so the types narrow to non-None.
            auth = (
                KalshiAuth(self._private_key, self._api_key)
                if self._private_key is not None and self._api_key is not None
                else None
            )
            self._client = httpx.AsyncClient(
                timeout=self._timeout,
                auth=auth,
                headers={"Content-Type": "application/json"},
            )
        return self._client

    def _require_auth(self) -> None:
        if not self.has_credentials:
            raise ValueError(
                "This action requires Kalshi credentials. Set KALSHI_API_KEY and "
                "KALSHI_PRIVATE_KEY_PATH in the server environment."
            )

    async def _request(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        json: dict | None = None,
    ) -> Any:
        client = self._ensure_client()
        url = self._base_url + path
        response = await client.request(method, url, params=params, json=json)
        if response.is_error:
            try:
                body: Any = response.json()
            except Exception:
                body = response.text
            raise KalshiAPIError(response.status_code, method, path, body)
        if not response.content:
            return {}
        return response.json()

    async def get(self, path: str, params: dict | None = None) -> Any:
        return await self._request("GET", path, params=params)

    async def post(self, path: str, json: dict | None = None) -> Any:
        return await self._request("POST", path, json=json)

    async def delete(self, path: str, params: dict | None = None) -> Any:
        return await self._request("DELETE", path, params=params)

    async def patch(self, path: str, json: dict | None = None) -> Any:
        return await self._request("PATCH", path, json=json)

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self):
        self._ensure_client()
        return self

    async def __aexit__(self, *args):
        await self.aclose()
