from typing import Literal

from pydantic import BaseModel, Field


class MCPSchemaBaseModel(BaseModel):
    @classmethod
    def to_mcp_input_schema(cls) -> dict:
        """Convert this model into a clean MCP Tool inputSchema.

        Flattens ``Optional`` fields (drops the ``anyOf``/null noise pydantic emits) and
        inlines enum ``$ref``s so MCP clients render simple, readable parameter schemas.
        """
        schema = cls.model_json_schema()
        properties = {}
        for name, prop in schema.get("properties", {}).items():
            clean_prop = prop
            if "anyOf" in prop:
                for variant in prop["anyOf"]:
                    if variant.get("type") != "null":
                        clean_prop = dict(variant)
                        if "description" in prop:
                            clean_prop["description"] = prop["description"]
                        break

            if "$ref" in clean_prop:
                ref_key = clean_prop["$ref"].split("/")[-1]
                enum_def = schema.get("$defs", {}).get(ref_key, {})
                clean_prop = {
                    "type": enum_def.get("type", "string"),
                    "enum": enum_def.get("enum", []),
                    "description": prop.get("description"),
                }

            clean_prop.pop("title", None)
            if clean_prop.get("description") is None:
                clean_prop.pop("description", None)
            properties[name] = clean_prop

        return {
            "type": "object",
            "properties": properties,
            "required": schema.get("required", []),
            "additionalProperties": False,
        }


# Shared pagination fields
class _Paginated(MCPSchemaBaseModel):
    limit: int | None = Field(default=None, description="Results per page (1-1000).")
    cursor: str | None = Field(
        default=None, description="Pagination cursor for the next page."
    )


# ---- Discovery ---------------------------------------------------------------------
class ListMarketsRequest(_Paginated):
    """Browse/search markets. Kalshi has no free-text search endpoint; filter with these."""

    event_ticker: str | None = Field(
        default=None, description="Filter by event ticker."
    )
    series_ticker: str | None = Field(
        default=None, description="Filter by series ticker."
    )
    status: Literal["unopened", "open", "closed", "settled"] | None = Field(
        default=None, description="Filter by market status."
    )
    tickers: str | None = Field(
        default=None, description="Comma-separated list of specific market tickers."
    )
    min_close_ts: int | None = Field(
        default=None, description="Only markets closing on/after this Unix timestamp."
    )
    max_close_ts: int | None = Field(
        default=None, description="Only markets closing on/before this Unix timestamp."
    )


class GetMarketRequest(MCPSchemaBaseModel):
    ticker: str = Field(..., description="The market ticker, e.g. 'KXELONMARS-99'.")


class ListEventsRequest(_Paginated):
    series_ticker: str | None = Field(
        default=None, description="Filter by series ticker."
    )
    status: str | None = Field(default=None, description="Filter by event status.")
    with_nested_markets: bool | None = Field(
        default=None, description="Include each event's markets inline."
    )


class GetEventRequest(MCPSchemaBaseModel):
    event_ticker: str = Field(..., description="The event ticker to retrieve.")
    with_nested_markets: bool | None = Field(
        default=None, description="Include the event's markets inline."
    )


class ListSeriesRequest(MCPSchemaBaseModel):
    category: str | None = Field(default=None, description="Filter series by category.")
    tags: str | None = Field(default=None, description="Comma-separated tag filter.")


class GetSeriesRequest(MCPSchemaBaseModel):
    series_ticker: str = Field(
        ..., description="The series ticker, e.g. 'KXELONMARS'. Holds rules PDFs."
    )


# ---- Research / rules --------------------------------------------------------------
class GetMarketOrderbookRequest(MCPSchemaBaseModel):
    ticker: str = Field(..., description="The market ticker.")
    depth: int | None = Field(
        default=None, description="Price levels to return (1-100; omit for all)."
    )


class GetMarketCandlesticksRequest(MCPSchemaBaseModel):
    ticker: str = Field(..., description="The market ticker.")
    period_interval: Literal[1, 60, 1440] = Field(
        default=60, description="Candle size in minutes: 1, 60, or 1440 (1 day)."
    )
    lookback_hours: int | None = Field(
        default=24,
        description="Convenience window ending now. Ignored if start_ts/end_ts are set.",
    )
    start_ts: int | None = Field(
        default=None, description="Explicit start Unix timestamp."
    )
    end_ts: int | None = Field(default=None, description="Explicit end Unix timestamp.")
    series_ticker: str | None = Field(
        default=None,
        description="Override the series ticker (else derived from the market ticker).",
    )


class GetMarketTradesRequest(_Paginated):
    ticker: str = Field(..., description="The market ticker.")
    min_ts: int | None = Field(
        default=None, description="Only trades after this Unix ts."
    )
    max_ts: int | None = Field(
        default=None, description="Only trades before this Unix ts."
    )


class GetMarketRulesRequest(MCPSchemaBaseModel):
    """Consolidated settlement rules for a market (market + parent series)."""

    ticker: str = Field(..., description="The market ticker to explain.")


class FetchRulesPdfRequest(MCPSchemaBaseModel):
    """Download and extract the text of a market's rules PDF."""

    series_ticker: str | None = Field(
        default=None, description="Series ticker whose contract PDF to fetch."
    )
    ticker: str | None = Field(
        default=None, description="Market ticker (its series' PDF is fetched)."
    )
    url: str | None = Field(
        default=None, description="Direct PDF URL (overrides tickers)."
    )
    document: Literal["contract_terms", "certification"] = Field(
        default="contract_terms",
        description="Which series PDF: 'contract_terms' (contract_terms_url) or 'certification' (contract_url).",
    )


# ---- Exchange ----------------------------------------------------------------------
class EmptyRequest(MCPSchemaBaseModel):
    pass


# ---- Portfolio ---------------------------------------------------------------------
class GetPositionsRequest(_Paginated):
    ticker: str | None = Field(default=None, description="Filter by market ticker.")
    event_ticker: str | None = Field(
        default=None, description="Filter by event ticker."
    )
    count_filter: str | None = Field(
        default=None,
        description="Restrict to positions with non-zero fields (e.g. 'position').",
    )


class GetFillsRequest(_Paginated):
    ticker: str | None = Field(default=None, description="Filter by market ticker.")
    order_id: str | None = Field(default=None, description="Filter by order id.")
    min_ts: int | None = Field(
        default=None, description="Only fills after this Unix ts."
    )
    max_ts: int | None = Field(
        default=None, description="Only fills before this Unix ts."
    )


class GetSettlementsRequest(_Paginated):
    ticker: str | None = Field(default=None, description="Filter by market ticker.")
    event_ticker: str | None = Field(
        default=None, description="Filter by event ticker."
    )
    min_ts: int | None = Field(default=None, description="Only after this Unix ts.")
    max_ts: int | None = Field(default=None, description="Only before this Unix ts.")


# ---- Orders ------------------------------------------------------------------------
class ListOrdersRequest(_Paginated):
    ticker: str | None = Field(default=None, description="Filter by market ticker.")
    event_ticker: str | None = Field(
        default=None, description="Filter by event ticker."
    )
    status: Literal["resting", "canceled", "executed"] | None = Field(
        default=None, description="Filter by order status."
    )
    min_ts: int | None = Field(
        default=None, description="Only orders after this Unix ts."
    )
    max_ts: int | None = Field(
        default=None, description="Only orders before this Unix ts."
    )


class GetOrderRequest(MCPSchemaBaseModel):
    order_id: str = Field(..., description="The order id.")


class CreateOrderRequest(MCPSchemaBaseModel):
    """Place a limit order using the intuitive buy/sell + yes/no model.

    Prices are whole **cents** (1-99) for the outcome you name in ``side``; the server
    translates to Kalshi's YES-leg book side and fixed-point dollar price. Requires
    ``confirm=true`` to actually place — otherwise a preview is returned and nothing is sent.
    """

    ticker: str = Field(..., description="The market ticker to trade.")
    action: Literal["buy", "sell"] = Field(
        ..., description="Buy (open/add) or sell (close/reduce)."
    )
    side: Literal["yes", "no"] = Field(..., description="Which outcome: 'yes' or 'no'.")
    count: float = Field(..., gt=0, description="Number of contracts.")
    limit_price: int = Field(
        ...,
        ge=1,
        le=99,
        description="Limit price in cents (1-99) for the chosen outcome.",
    )
    time_in_force: Literal[
        "good_till_canceled", "immediate_or_cancel", "fill_or_kill"
    ] = Field(default="good_till_canceled", description="How long the order rests.")
    post_only: bool = Field(
        default=False, description="Reject if it would immediately match."
    )
    reduce_only: bool = Field(
        default=False,
        description="Cap size by current position (never flips direction).",
    )
    expiration_ts: int | None = Field(
        default=None,
        description="Optional Unix-seconds expiry (with good_till_canceled).",
    )
    client_order_id: str | None = Field(
        default=None, description="Optional idempotency id; auto-generated if omitted."
    )
    confirm: bool = Field(
        default=False,
        description="Must be true to actually place the order. False returns a preview only.",
    )


class CancelOrderRequest(MCPSchemaBaseModel):
    order_id: str = Field(..., description="The order id to cancel.")


class AmendOrderRequest(MCPSchemaBaseModel):
    """Amend an existing order's price and/or total count (intuitive model + confirm)."""

    order_id: str = Field(..., description="The order id to amend.")
    ticker: str = Field(..., description="The market ticker of the order.")
    action: Literal["buy", "sell"] = Field(..., description="Original order direction.")
    side: Literal["yes", "no"] = Field(..., description="Original outcome side.")
    count: float = Field(..., gt=0, description="New total/max fillable count.")
    limit_price: int = Field(
        ..., ge=1, le=99, description="New limit price in cents (1-99)."
    )
    updated_client_order_id: str | None = Field(
        default=None, description="Optional new client order id."
    )
    confirm: bool = Field(
        default=False,
        description="Must be true to apply. False returns a preview only.",
    )


class DecreaseOrderRequest(MCPSchemaBaseModel):
    """Decrease a resting order's remaining count. Provide exactly one of reduce_by/reduce_to."""

    order_id: str = Field(..., description="The order id to decrease.")
    reduce_by: float | None = Field(default=None, description="Contracts to remove.")
    reduce_to: float | None = Field(
        default=None, description="Target remaining contracts."
    )
