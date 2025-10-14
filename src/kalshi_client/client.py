import httpx
from .base import BaseAPIClient
import asyncio
from typing import Dict, Any
from .schemas import (
    GetPositionsRequest,
    GetOrdersRequest,
    GetFillsRequest,
    GetSettlementsRequest,
    CreateOrderRequest,
    GetEventRequest,
)


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

    async def create_order(
        self,
        request: CreateOrderRequest,
    ) -> Dict[str, Any]:
        """
        Create an order to buy or sell contracts in a market.
        """
        params = request.model_dump(exclude_none=True)

        return await self.post("/trade-api/v2/portfolio/orders", params)

    async def get_event(
        self,
        request: GetEventRequest,
    ) -> Dict[str, Any]:
        """
        Get details about a specific event by its ticker.

        Args:
            request: GetEventRequest containing the event_ticker

        Returns:
            Dictionary containing event data including title, description,
            markets, and other metadata.
        """
        event_ticker = request.event_ticker
        endpoint = f"/trade-api/v2/events/{event_ticker}"

        return await self.get(endpoint)
