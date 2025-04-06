from pydantic import BaseModel, Field
from typing import Optional, Literal


class MCPSchemaBaseModel(BaseModel):
    @classmethod
    def to_mcp_input_schema(model_class: type["MCPSchemaBaseModel"]) -> dict:
        """Convert a model class to an MCP Tool input schema format

        Args:
            model_class: The class to convert to a tool
            name: The name of the tool
            description: The description of the tool

        Returns:
            An MCP Tool input schema matching the MCP format
        """
        schema = model_class.model_json_schema()

        # Clean up the properties to match MCP format
        properties = {}
        for name, prop in schema.get("properties", {}).items():
            # Handle optional fields (remove anyOf/null combinations)
            if "anyOf" in prop:
                # Get the non-null variant
                for variant in prop["anyOf"]:
                    if variant.get("type") != "null":
                        clean_prop = variant
                        # Preserve description from original prop if it exists
                        if "description" in prop:
                            clean_prop["description"] = prop["description"]
                        break
            else:
                clean_prop = prop

            # Handle enum references by inlining them
            if "$ref" in clean_prop:
                ref_key = clean_prop["$ref"].split("/")[-1]
                if ref_key in schema.get("$defs", {}):
                    enum_def = schema["$defs"][ref_key]
                    clean_prop = {
                        "type": enum_def.get(
                            "type", "string"
                        ),  # Preserve the original type
                        "enum": enum_def.get("enum", []),
                        "description": clean_prop.get("description"),
                    }

            # Remove extra metadata fields
            clean_prop.pop("title", None)

            properties[name] = clean_prop

        return {
            "type": "object",
            "properties": properties,
            "required": schema.get("required", []),
            "additionalProperties": False,
        }


class GetBalanceRequest(MCPSchemaBaseModel):
    """Request schema for the GET /trade-api/v2/balance endpoint."""

    pass


class GetPositionsRequest(MCPSchemaBaseModel):
    """Request schema for the GET /trade-api/v2/positions endpoint."""

    limit: Optional[int] = Field(
        default=100, description="Number of results per page (1-1000, default 100)"
    )
    cursor: Optional[str] = Field(
        default=None, description="Pagination cursor for the next page of results"
    )
    status: Optional[str] = Field(
        default=None, description="Filter positions by status (open, settled, expired)"
    )
    market_ticker: Optional[str] = Field(
        default=None, description="Filter positions by market ticker"
    )
    event_ticker: Optional[str] = Field(
        default=None, description="Filter positions by event ticker"
    )


class GetOrdersRequest(MCPSchemaBaseModel):
    """Request schema for the GET /trade-api/v2/orders endpoint."""

    limit: Optional[int] = Field(
        default=100, description="Number of results per page (1-1000, default 100)"
    )
    cursor: Optional[str] = Field(
        default=None, description="Pagination cursor for the next page of results"
    )
    status: Optional[str] = Field(
        default=None,
        description="Filter orders by status (open, filled, cancelled, etc.)",
    )
    market_ticker: Optional[str] = Field(
        default=None, description="Filter orders by market ticker"
    )
    event_ticker: Optional[str] = Field(
        default=None, description="Filter orders by event ticker"
    )


class GetFillsRequest(MCPSchemaBaseModel):
    """Request schema for the GET /trade-api/v2/portfolio/fills endpoint."""

    limit: Optional[int] = Field(
        default=100, description="Number of results per page (1-1000, default 100)"
    )
    cursor: Optional[str] = Field(
        default=None,
        description="Pagination cursor for the next page of results. The cursor does not store filters, so any filter parameters must be passed again.",
    )
    market_ticker: Optional[str] = Field(
        default=None, description="Filter fills by market ticker"
    )
    order_id: Optional[str] = Field(
        default=None, description="Filter fills by order ID"
    )
    min_ts: Optional[int] = Field(
        default=None, description="Filter fills after this timestamp"
    )
    max_ts: Optional[int] = Field(
        default=None, description="Filter fills before this timestamp"
    )


class CreateOrderRequest(MCPSchemaBaseModel):
    """Request schema for the POST /trade-api/v2/portfolio/orders endpoint.

    This endpoint allows submitting orders to buy or sell contracts in a market.
    All prices are specified in cents (1/100th of a dollar).
    """

    action: Literal["buy", "sell"] = Field(
        ..., description="Specifies if this is a buy or sell order"
    )
    ticker: str = Field(
        ..., description="The ticker of the market the order will be placed in"
    )
    side: Literal["yes", "no"] = Field(
        ..., description="Specifies if this is a 'yes' or 'no' order"
    )
    type: Literal["market", "limit"] = Field(
        ..., description="Specifies if this is a 'market' or 'limit' order"
    )
    count: int = Field(
        ..., description="Number of contracts to be bought or sold", gt=0
    )
    buy_max_cost: Optional[int] = Field(
        default=None,
        description="For market buy orders only. The maximum total cost in cents you're willing to spend.",
        gt=0,
    )
    sell_position_floor: Optional[int] = Field(
        default=None,
        description="For market orders only. If set to 0, prevents the order from flipping your position from long to short or vice versa.",
        ge=0,
    )
    yes_price: Optional[int] = Field(
        default=None,
        description="Required for limit orders. Price in cents (1-99) at which you want to trade the Yes side.",
        ge=1,
        le=99,
    )
    no_price: Optional[int] = Field(
        default=None,
        description="Required for limit orders. Price in cents (1-99) at which you want to trade the No side.",
        ge=1,
        le=99,
    )
    client_order_id: str = Field(
        ...,
        description="Client-provided order identifier. Must be unique among open orders.",
    )
    expiration_ts: Optional[int] = Field(
        default=None,
        description="Unix timestamp in seconds when the order should expire. If not provided, defaults to 24 hours.",
        gt=0,
    )


class GetSettlementsRequest(MCPSchemaBaseModel):
    """Request schema for the GET /trade-api/v2/portfolio/settlements endpoint."""

    limit: Optional[int] = Field(
        default=100, description="Number of results per page (1-1000, default 100)"
    )
    cursor: Optional[str] = Field(
        default=None,
        description="Pagination cursor for the next page of results. The cursor does not store filters, so any filter parameters must be passed again.",
    )
    market_ticker: Optional[str] = Field(
        default=None, description="Filter settlements by market ticker"
    )
    event_ticker: Optional[str] = Field(
        default=None, description="Filter settlements by event ticker"
    )
    min_ts: Optional[int] = Field(
        default=None, description="Filter settlements after this timestamp"
    )
    max_ts: Optional[int] = Field(
        default=None, description="Filter settlements before this timestamp"
    )


class GetEventRequest(MCPSchemaBaseModel):
    """Request schema for the GET /trade-api/v2/events/{event_ticker} endpoint."""

    event_ticker: str = Field(
        ..., description="The ticker of the event to retrieve"
    )

