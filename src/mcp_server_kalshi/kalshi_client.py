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
from .schema import GetPositionsRequest, GetOrdersRequest, GetFillsRequest, GetSettlementsRequest


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

    async def get_positions(
        self,
        request: GetPositionsRequest,
    ) -> Dict[str, Any]:
        """
        Get all market positions for the member.

        Args:
            request: GetPositionsRequest

        Returns:
            Dictionary containing positions data
        """
        params = request.model_dump(exclude_none=True)

        return await self.get("/trade-api/v2/portfolio/positions", params)

    async def get_balance(self) -> Dict[str, Any]:
        """
        Get the portfolio balance of the logged-in member in cents.

        Returns:
            Dictionary containing balance data including available balance,
            portfolio value, total returns, etc.
        """
        return await self.get("/trade-api/v2/portfolio/balance")

    async def get_orders(
        self,
        request: GetOrdersRequest,
    ) -> Dict[str, Any]:
        """
        Get all orders for the member.

        """
        params = request.model_dump(exclude_none=True)

        return await self.get("/trade-api/v2/portfolio/orders", params)

    async def get_fills(
        self,
        request: GetFillsRequest,
    ) -> Dict[str, Any]:
        """
        Get all fills for the member.

        Args:
            request: GetFillsRequest

        Returns:
            Dictionary containing fills data
        """
        params = request.model_dump(exclude_none=True)

        return await self.get("/trade-api/v2/portfolio/fills", params)

    async def get_settlements(
        self,
        request: GetSettlementsRequest,
    ) -> Dict[str, Any]:
        """
        Get all settlements for the member.

        Args:
            request: GetSettlementsRequest

        Returns:
            Dictionary containing settlements data
        """
        params = request.model_dump(exclude_none=True)

        return await self.get("/trade-api/v2/portfolio/settlements", params)
