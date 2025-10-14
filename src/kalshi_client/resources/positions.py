# resources/positions.py
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from ..base import BaseAPIClient


class GetPositionsRequest(BaseModel):
    """Request schema for the GET /trade-api/v2/portfolio/positions endpoint."""

    cursor: Optional[str] = Field(
        default=None, description="Pagination pointer to the next page of records"
    )
    limit: Optional[int] = Field(
        default=100,
        ge=1,
        le=1000,
        description="Number of results per page (1-1000, default 100)",
    )
    count_filter: Optional[str] = Field(
        default=None, description="Filters positions with non-zero values"
    )
    settlement_status: Optional[str] = Field(
        default=None, description="Settlement status of markets"
    )
    ticker: Optional[str] = Field(
        default=None, description="Filter by specific market ticker"
    )
    event_ticker: Optional[str] = Field(
        default=None, description="Filter by specific event ticker"
    )


class EventPosition(BaseModel):
    """A single event-level position in the portfolio."""

    event_ticker: str = Field(description="Unique identifier for the event")
    event_exposure: int = Field(description="Cost of aggregate event position in cents")
    event_exposure_dollars: str = Field(
        description="Cost of aggregate event position in dollars"
    )
    fees_paid: int = Field(description="Fees paid on fill orders, in cents")
    fees_paid_dollars: str = Field(description="Fees paid on fill orders, in dollars")
    realized_pnl: int = Field(description="Locked in profit and loss, in cents")
    realized_pnl_dollars: str = Field(
        description="Locked in profit and loss, in dollars"
    )
    resting_order_count: int = Field(description="Aggregate size of resting orders")
    total_cost: int = Field(description="Total spent on event in cents")
    total_cost_dollars: str = Field(description="Total spent on event in dollars")

    @property
    def is_profitable(self) -> bool:
        """Check if event position has positive realized PnL."""
        return self.realized_pnl > 0


class MarketPosition(BaseModel):
    """A single market-level position in the portfolio."""

    ticker: str = Field(description="Unique identifier for the market")
    position: int = Field(
        description="Number of contracts bought (negative = NO, positive = YES)"
    )
    market_exposure: int = Field(
        description="Cost of aggregate market position in cents"
    )
    market_exposure_dollars: str = Field(
        description="Cost of aggregate market position in dollars"
    )
    fees_paid: int = Field(description="Fees paid on fill orders, in cents")
    fees_paid_dollars: str = Field(description="Fees paid on fill orders, in dollars")
    realized_pnl: int = Field(description="Locked in profit and loss, in cents")
    realized_pnl_dollars: str = Field(
        description="Locked in profit and loss, in dollars"
    )
    resting_orders_count: int = Field(description="Aggregate size of resting orders")
    total_traded: int = Field(description="Total spent on market in cents")
    total_traded_dollars: str = Field(description="Total spent on market in dollars")
    last_updated_ts: datetime = Field(description="Last time position was updated")

    @property
    def is_profitable(self) -> bool:
        """Check if market position has positive realized PnL."""
        return self.realized_pnl > 0

    @property
    def is_yes_position(self) -> bool:
        """Check if this is a YES position (positive position count)."""
        return self.position > 0

    @property
    def is_no_position(self) -> bool:
        """Check if this is a NO position (negative position count)."""
        return self.position < 0


class GetPositionsResponse(BaseModel):
    """Response from GET /trade-api/v2/portfolio/positions endpoint."""

    cursor: Optional[str] = Field(
        default=None, description="Cursor for pagination to the next page"
    )
    event_positions: List[EventPosition] = Field(
        default_factory=list, description="List of event-level positions"
    )
    market_positions: List[MarketPosition] = Field(
        default_factory=list, description="List of market-level positions"
    )

    @property
    def total_event_exposure_cents(self) -> int:
        """Calculate total event exposure across all positions in cents."""
        return sum(pos.event_exposure for pos in self.event_positions)

    @property
    def total_market_exposure_cents(self) -> int:
        """Calculate total market exposure across all positions in cents."""
        return sum(pos.market_exposure for pos in self.market_positions)

    @property
    def total_realized_pnl_cents(self) -> int:
        """Calculate total realized PnL across all market positions in cents."""
        return sum(pos.realized_pnl for pos in self.market_positions)


# ============================================================================
# Resource
# ============================================================================


class PositionResource:
    """Position-related endpoints."""

    def __init__(self, client: BaseAPIClient):
        self._client = client

    async def list(
        self, params: Optional[GetPositionsRequest] = None
    ) -> GetPositionsResponse:
        """Get list of positions in the portfolio.

        This endpoint returns both event-level and market-level positions
        for the authenticated member. Positions include information about
        contract holdings, exposures, realized PnL, and fees paid.

        Args:
            params: Query parameters for filtering positions

        Returns:
            List of event positions and market positions with optional pagination cursor

        Raises:
            httpx.HTTPStatusError: If the API request fails

        Example:
            >>> async with client:
            ...     params = GetPositionsRequest(limit=50, settlement_status="settled")
            ...     response = await client.positions.list(params)
            ...     print(f"Found {len(response.market_positions)} market positions")
            ...     print(f"Total PnL: ${response.total_realized_pnl_cents / 100:.2f}")
        """
        query_params = params.model_dump(exclude_none=True) if params else {}

        response = await self._client._client.get(
            "/trade-api/v2/portfolio/positions", params=query_params
        )
        response.raise_for_status()

        return GetPositionsResponse(**response.json())
