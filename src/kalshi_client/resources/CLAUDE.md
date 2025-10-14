 Each file in the resources folder contains a class pertaining to a group of endpoints in the Kalshi API and a set of Pydantic models defining the input and output schemas of the endpoints. In particular, for each endpoint, the following three entities
  must be implemented:

1. Request Schema (Pydantic Model)

Define the input parameters for the endpoint using Pydantic:

class GetPositionsRequest(BaseModel):
    """Request schema for the GET /trade-api/v2/positions endpoint."""

    limit: Optional[int] = Field(
        default=100,
        ge=1,
        le=1000,
        description="Number of results per page (1-1000, default 100)"
    )
    cursor: Optional[str] = Field(
        default=None,
        description="Pagination cursor for the next page of results"
    )
    status: Optional[str] = Field(
        default=None,
        description="Filter positions by status (open, settled, expired)"
    )
    market_ticker: Optional[str] = Field(
        default=None,
        description="Filter positions by market ticker"
    )
    event_ticker: Optional[str] = Field(
        default=None,
        description="Filter positions by event ticker"
    )

Guidelines:
- Use Optional for optional parameters with default=None
- Add Field() with constraints (ge, le, min_length, etc.) for validation
- IMPORTANT! Include clear descriptions for each field
- Use Literal or Enum for fixed value sets
- Add @field_validator for custom validation logic if needed

2. Response Schema (Pydantic Model)

Define the output structure returned by the endpoint:

class Position(BaseModel):
    """A single position in the portfolio."""

    position_id: str
    market_ticker: str
    event_ticker: str
    side: Literal["yes", "no"]
    quantity: int
    cost_basis_cents: int
    current_value_cents: int
    unrealized_pnl_cents: int
    status: str
    created_time: datetime
    settled_time: Optional[datetime] = None


class GetPositionsResponse(BaseModel):
    """Response from GET /trade-api/v2/positions endpoint."""

    positions: List[Position]
    cursor: Optional[str] = Field(
        default=None,
        description="Cursor for pagination to the next page"
    )

Guidelines:
- Create separate models for nested objects (e.g., Position)
- Match the exact structure returned by the API
- Use List[Model] for arrays of objects
- Include pagination fields (cursor, has_more, etc.) if applicable
- Add helper properties or methods if useful (e.g., @property def is_profitable)

3. Resource Class Method

Implement an asynchronous method that calls the base Kalshi API client:

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ..base import BaseAPIClient


class PositionResource:
    """Position-related endpoints."""

    def __init__(self, client: "BaseAPIClient"):
        self._client = client

    async def list(
        self,
        params: Optional[GetPositionsRequest] = None
    ) -> GetPositionsResponse:
        """Get list of positions in the portfolio.

        Args:
            params: Query parameters for filtering positions

        Returns:
            List of positions with optional pagination cursor

        Raises:
            httpx.HTTPStatusError: If the API request fails

        Example:
            >>> async with client:
            ...     params = GetPositionsRequest(limit=50, status="open")
            ...     response = await client.positions.list(params)
            ...     print(f"Found {len(response.positions)} positions")
        """
        query_params = params.model_dump(exclude_none=True) if params else {}

        response = await self._client._client.get(
            "/trade-api/v2/positions",
            params=query_params
        )
        response.raise_for_status()

        return GetPositionsResponse(**response.json())

Guidelines:
- Method name should be descriptive (e.g., list, get, create, update, delete, cancel)
- Accept request schema as optional parameter (use None if no parameters)
- Use params.model_dump(exclude_none=True) to convert request model to dict and exclude None values
- Call appropriate HTTP method on self._client._client (.get(), .post(), .put(), .delete())
- Always call response.raise_for_status() to handle HTTP errors
- Parse response JSON into response schema using **response.json()
- Add comprehensive docstring with Args, Returns, Raises, and Example sections
- Use type hints for all parameters and return values

Complete Example

Here's a full example of a resource file:

# resources/positions.py
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List, Literal, TYPE_CHECKING

if TYPE_CHECKING:
    from ..base import BaseAPIClient

# ============================================================================
# Schemas
# ============================================================================

class GetPositionsRequest(BaseModel):
    """Request schema for the GET /trade-api/v2/positions endpoint."""

    limit: Optional[int] = Field(
        default=100,
        ge=1,
        le=1000,
        description="Number of results per page (1-1000, default 100)"
    )
    cursor: Optional[str] = Field(
        default=None,
        description="Pagination cursor for the next page of results"
    )
    status: Optional[str] = Field(
        default=None,
        description="Filter positions by status (open, settled, expired)"
    )


class Position(BaseModel):
    """A single position in the portfolio."""

    position_id: str
    market_ticker: str
    side: Literal["yes", "no"]
    quantity: int
    cost_basis_cents: int
    current_value_cents: int
    unrealized_pnl_cents: int
    status: str
    created_time: datetime

    @property
    def is_profitable(self) -> bool:
        """Check if position has positive unrealized PnL."""
        return self.unrealized_pnl_cents > 0


class GetPositionsResponse(BaseModel):
    """Response from GET /trade-api/v2/positions endpoint."""

    positions: List[Position]
    cursor: Optional[str] = None


# ============================================================================
# Resource
# ============================================================================

class PositionResource:
    """Position-related endpoints."""

    def __init__(self, client: "BaseAPIClient"):
        self._client = client

    async def list(
        self,
        params: Optional[GetPositionsRequest] = None
    ) -> GetPositionsResponse:
        """Get list of positions in the portfolio.

        Args:
            params: Query parameters for filtering positions

        Returns:
            List of positions with optional pagination cursor

        Raises:
            httpx.HTTPStatusError: If the API request fails
        """
        query_params = params.model_dump(exclude_none=True) if params else {}

        response = await self._client._client.get(
            "/trade-api/v2/positions",
            params=query_params
        )
        response.raise_for_status()

        return GetPositionsResponse(**response.json())

HTTP Method Patterns

- GET (retrieve): await self._client._client.get(endpoint, params=query_params)
- POST (create): await self._client._client.post(endpoint, json=body)
- PUT (update): await self._client._client.put(endpoint, json=body)
- PATCH (partial update): await self._client._client.patch(endpoint, json=body)
- DELETE (remove): await self._client._client.delete(endpoint)

Naming Conventions

- Request schemas: {Verb}{Resource}Request (e.g., GetPositionsRequest, CreateOrderRequest)
- Response schemas: {Verb}{Resource}Response (e.g., GetPositionsResponse, CreateOrderResponse)
- Domain models: {Resource} (e.g., Position, Order, Market)
- Resource classes: {Resource}Resource (e.g., PositionResource, OrderResource)
- Methods: Use standard CRUD names (list, get, create, update, delete) or action verbs (cancel, execute, settle)
