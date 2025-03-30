import httpx
import asyncio
from typing import Dict, Any, Optional, Union
from abc import ABC, abstractmethod
import base64
import time
from typing import Dict, List, Optional, Union, Literal
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.backends import default_backend
from cryptography.exceptions import InvalidSignature


def load_private_key_from_file(file_path: str) -> rsa.RSAPrivateKey:
    """Load RSA private key from file."""
    with open(file_path, "rb") as key_file:
        private_key = serialization.load_pem_private_key(
            key_file.read(), password=None, backend=default_backend()
        )
    return private_key


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


class BaseAPIClient(ABC):
    """A base async api client"""

    def __init__(
        self,
        base_url: str,
        private_key_path: str,
        api_key: Optional[str] = None,
        timeout: int = 30,
    ):
        """
        Initialize the async API client.

        Args:
            base_url: The base URL for the API
            api_key: Optional API key for authentication
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.private_key = load_private_key_from_file(private_key_path)
        self.api_key = api_key

        # Create an async client session that will be reused
        self.client = httpx.AsyncClient(base_url=self.base_url, timeout=timeout)

    def get_auth_headers(self, method: str, endpoint: str) -> Dict[str, str]:
        """Generate authentication headers for Kalshi API requests."""
        timestamp = str(int(time.time() * 1000))
        msg_string = timestamp + method + endpoint
        signature = sign_pss_text(self.private_key, msg_string)

        return {
            "KALSHI-ACCESS-KEY": self.api_key,
            "KALSHI-ACCESS-SIGNATURE": signature,
            "KALSHI-ACCESS-TIMESTAMP": timestamp,
            "Content-Type": "application/json",
        }

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        await self.close()

    async def close(self):
        """Close the underlying HTTP session."""
        await self.client.aclose()

    async def _handle_response(self, response: httpx.Response) -> Dict[str, Any]:
        """
        Handle the API response.

        Args:
            response: The httpx response object

        Returns:
            Parsed JSON response

        Raises:
            HTTPStatusError: If the response contains an HTTP error status
        """
        # Raise exception for 4XX/5XX responses
        response.raise_for_status()

        # Return JSON response if present, otherwise empty dict
        if response.text:
            return response.json()
        return {}

    async def get(
        self, endpoint: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Send an async GET request to the API.

        Args:
            endpoint: API endpoint (without the base URL)
            params: Optional query parameters

        Returns:
            API response as dictionary
        """
        headers = self.get_auth_headers("GET", endpoint)

        url = f"{endpoint}"
        response = await self.client.get(url, params=params, headers=headers)
        return await self._handle_response(response)


class KalshiAPIClient(BaseAPIClient):
    """A client for the Kalshi API"""

    def __init__(self, **kwargs):
        """Initialize the Kalshi API client with configured credentials"""
        super().__init__(**kwargs)

    async def get_markets(
        self,
        limit: int = 100,
        cursor: Optional[str] = None,
        event_ticker: Optional[str] = None,
        series_ticker: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get a list of markets from Kalshi API.

        Args:
            limit: Number of results per page (1-1000, default 100)
            cursor: Pagination cursor for the next page of results
            event_ticker: Filter markets by event ticker
            series_ticker: Filter markets by series ticker
            status: Filter markets by status (unopened, open, closed, settled)

        Returns:
            Dictionary containing markets data
        """
        params = {"limit": limit}

        if cursor:
            params["cursor"] = cursor
        if event_ticker:
            params["event_ticker"] = event_ticker
        if series_ticker:
            params["series_ticker"] = series_ticker
        if status:
            params["status"] = status

        return await self.get("/trade-api/v2/markets", params)

    async def get_positions(
        self,
        limit: int = 100,
        cursor: Optional[str] = None,
        status: Optional[Literal["open", "settled", "expired"]] = None,
        market_ticker: Optional[str] = None,
        event_ticker: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get all market positions for the member.

        Args:
            limit: Number of results per page (1-1000, default 100)
            cursor: Pagination cursor for the next page of results
            status: Filter positions by status (open, settled, expired)
            market_ticker: Filter positions by market ticker
            event_ticker: Filter positions by event ticker

        Returns:
            Dictionary containing positions data
        """
        params = {"limit": limit}

        if cursor:
            params["cursor"] = cursor
        if status:
            params["status"] = status
        if market_ticker:
            params["market_ticker"] = market_ticker
        if event_ticker:
            params["event_ticker"] = event_ticker

        return await self.get("/trade-api/v2/portfolio/positions", params)
