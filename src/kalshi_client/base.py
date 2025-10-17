import httpx
import base64
import time
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.backends import default_backend


def load_private_key_from_file(file_path: str) -> str:
    """Load RSA private key from file."""
    with open(file_path, "rb") as key_file:
        private_key = serialization.load_pem_private_key(
            key_file.read(), password=None, backend=default_backend()
        )
    return str(private_key)


def sign_pss_text(private_key: rsa.RSAPrivateKey, text: str) -> str:
    """Sign text using RSA-PSS algorithm."""
    signature = private_key.sign(
        text.encode(),
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH
        ),
        hashes.SHA256(),
    )
    return base64.b64encode(signature).decode()


class KalshiAuth(httpx.Auth):
    """Custom auth handler for Kalshi API."""

    def __init__(self, private_key: str | None, api_key: str | None):
        self._private_key: str | None = private_key
        self._api_key: str | None = api_key

    def auth_flow(self, request: httpx.Request):
        # Extract method and path for signature
        method = request.method
        endpoint = request.url.raw_path.decode()

        timestamp = str(int(time.time() * 1000))
        msg_string = timestamp + method + endpoint
        signature = sign_pss_text(self._private_key, msg_string)

        # Add headers to request
        request.headers["KALSHI-ACCESS-KEY"] = self._api_key or ""
        request.headers["KALSHI-ACCESS-SIGNATURE"] = signature
        request.headers["KALSHI-ACCESS-TIMESTAMP"] = timestamp

        yield request


class BaseAPIClient:
    """A base async api client"""

    def __init__(
        self,
        base_url: str,
        private_key_path: str,
        api_key: str | None = None,
        timeout: int = 30,
    ):
        """
        Initialize the async API client.

        Args:
            base_url: The base URL for the API
            api_key: Optional API key for authentication
            timeout: Request timeout in seconds
        """
        self._base_url: str = base_url.rstrip("/")
        self._timeout: int = timeout
        self._private_key: rsa.RSAPrivateKey = load_private_key_from_file(
            private_key_path
        )
        self._api_key: str | None = api_key
        self._client: httpx.AsyncClient | None = None

    def get_auth_headers(self, method: str, endpoint: str) -> Dict[str, str]:
        """Generate authentication headers for Kalshi API requests."""
        timestamp = str(int(time.time() * 1000))
        msg_string = timestamp + method + endpoint
        signature = sign_pss_text(self._private_key, msg_string)

        return {
            "KALSHI-ACCESS-KEY": self._api_key or "",
            "KALSHI-ACCESS-SIGNATURE": signature,
            "KALSHI-ACCESS-TIMESTAMP": timestamp,
            "Content-Type": "application/json",
        }

    async def __aenter__(self):
        auth = KalshiAuth(self._private_key, self._api_key)
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=self._timeout,
            auth=auth,
            headers={"Content-Type": "application/json"},
        )
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()
