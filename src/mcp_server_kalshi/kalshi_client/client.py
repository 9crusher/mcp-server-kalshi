from typing import Any

from .base import BaseAPIClient


def series_ticker_from_market(ticker: str) -> str:
    """Best-effort derivation of a series ticker from a market ticker.

    Kalshi tickers are ``SERIES-EVENTSUFFIX[-STRIKE...]`` (e.g. ``KXELONMARS-99`` →
    ``KXELONMARS``, ``HIGHNY-24JAN01-T60`` → ``HIGHNY``), so the series is the segment
    before the first hyphen.
    """
    return ticker.split("-", 1)[0]


def build_create_order_payload(
    *,
    ticker: str,
    action: str,
    side: str,
    count: float,
    limit_price_cents: int,
    time_in_force: str = "good_till_canceled",
    self_trade_prevention_type: str = "taker_at_cross",
    post_only: bool = False,
    reduce_only: bool = False,
    client_order_id: str | None = None,
    expiration_ts: int | None = None,
) -> dict:
    """Translate an intuitive (action, side, cents) order into the Kalshi V2 payload.

    Kalshi's V2 order endpoint quotes everything from the YES leg via a book ``side`` of
    ``bid`` (buy YES) or ``ask`` (sell YES). We accept the natural buy/sell + yes/no model
    with a whole-cent limit price for the chosen outcome, and convert:

    | action | side | book side | YES-leg price |
    |--------|------|-----------|---------------|
    | buy    | yes  | bid       | cents         |
    | sell   | yes  | ask       | cents         |
    | buy    | no   | ask       | 100 - cents   |
    | sell   | no   | bid       | 100 - cents   |

    (Buying NO @ p ≡ selling YES @ 1-p, since YES + NO = $1.)
    """
    action = action.lower()
    side = side.lower()
    yes_leg_cents = limit_price_cents if side == "yes" else 100 - limit_price_cents
    book_side = "bid" if (action, side) in {("buy", "yes"), ("sell", "no")} else "ask"

    payload: dict[str, Any] = {
        "ticker": ticker,
        "side": book_side,
        "count": str(count) if count != int(count) else str(int(count)),
        "price": f"{yes_leg_cents / 100:.4f}",
        "time_in_force": time_in_force,
        "self_trade_prevention_type": self_trade_prevention_type,
    }
    if client_order_id:
        payload["client_order_id"] = client_order_id
    if post_only:
        payload["post_only"] = True
    if reduce_only:
        payload["reduce_only"] = True
    if expiration_ts:
        payload["expiration_time"] = expiration_ts
    return payload


def build_amend_order_payload(
    *,
    ticker: str,
    action: str,
    side: str,
    count: float,
    limit_price_cents: int,
    updated_client_order_id: str | None = None,
) -> dict:
    """Build the Kalshi V2 amend body, using the same YES-leg translation as create."""
    action = action.lower()
    side = side.lower()
    yes_leg_cents = limit_price_cents if side == "yes" else 100 - limit_price_cents
    book_side = "bid" if (action, side) in {("buy", "yes"), ("sell", "no")} else "ask"

    payload: dict[str, Any] = {
        "ticker": ticker,
        "side": book_side,
        "price": f"{yes_leg_cents / 100:.4f}",
        "count": str(count) if count != int(count) else str(int(count)),
    }
    if updated_client_order_id:
        payload["updated_client_order_id"] = updated_client_order_id
    return payload


def build_decrease_order_payload(
    reduce_by: float | None = None, reduce_to: float | None = None
) -> dict:
    """Build the Kalshi V2 decrease body. Exactly one of reduce_by / reduce_to required."""
    if (reduce_by is None) == (reduce_to is None):
        raise ValueError("Provide exactly one of reduce_by or reduce_to.")
    if reduce_by is not None:
        return {
            "reduce_by": (
                str(reduce_by) if reduce_by != int(reduce_by) else str(int(reduce_by))
            )
        }
    assert reduce_to is not None  # guaranteed by the exactly-one check above
    return {
        "reduce_to": (
            str(reduce_to) if reduce_to != int(reduce_to) else str(int(reduce_to))
        )
    }


class KalshiAPIClient(BaseAPIClient):
    """Async client for the Kalshi Trade API v2.

    Paths below are relative to the version-prefixed base URL configured on the client
    (e.g. ``https://demo-api.kalshi.co/trade-api/v2``).
    """

    # ---- Exchange -----------------------------------------------------------------
    async def get_exchange_status(self) -> Any:
        return await self.get("/exchange/status")

    async def get_exchange_schedule(self) -> Any:
        return await self.get("/exchange/schedule")

    # ---- Markets ------------------------------------------------------------------
    async def get_markets(self, params: dict | None = None) -> Any:
        return await self.get("/markets", params=params)

    async def get_market(self, ticker: str) -> Any:
        return await self.get(f"/markets/{ticker}")

    async def get_market_orderbook(self, ticker: str, depth: int | None = None) -> Any:
        params = {"depth": depth} if depth is not None else None
        return await self.get(f"/markets/{ticker}/orderbook", params=params)

    async def get_market_candlesticks(
        self,
        ticker: str,
        start_ts: int,
        end_ts: int,
        period_interval: int,
        series_ticker: str | None = None,
        include_latest_before_start: bool | None = None,
    ) -> Any:
        series = series_ticker or series_ticker_from_market(ticker)
        params: dict[str, Any] = {
            "start_ts": start_ts,
            "end_ts": end_ts,
            "period_interval": period_interval,
        }
        if include_latest_before_start is not None:
            params["include_latest_before_start"] = include_latest_before_start
        return await self.get(
            f"/series/{series}/markets/{ticker}/candlesticks", params=params
        )

    async def get_market_trades(self, params: dict | None = None) -> Any:
        return await self.get("/markets/trades", params=params)

    # ---- Events -------------------------------------------------------------------
    async def get_events(self, params: dict | None = None) -> Any:
        return await self.get("/events", params=params)

    async def get_event(
        self, event_ticker: str, with_nested_markets: bool | None = None
    ) -> Any:
        params = (
            {"with_nested_markets": with_nested_markets}
            if with_nested_markets is not None
            else None
        )
        return await self.get(f"/events/{event_ticker}", params=params)

    # ---- Series -------------------------------------------------------------------
    async def get_series_list(self, params: dict | None = None) -> Any:
        return await self.get("/series", params=params)

    async def get_series(self, series_ticker: str) -> Any:
        return await self.get(f"/series/{series_ticker}")

    # ---- Portfolio (auth) ---------------------------------------------------------
    async def get_balance(self) -> Any:
        self._require_auth()
        return await self.get("/portfolio/balance")

    async def get_positions(self, params: dict | None = None) -> Any:
        self._require_auth()
        return await self.get("/portfolio/positions", params=params)

    async def get_fills(self, params: dict | None = None) -> Any:
        self._require_auth()
        return await self.get("/portfolio/fills", params=params)

    async def get_settlements(self, params: dict | None = None) -> Any:
        self._require_auth()
        return await self.get("/portfolio/settlements", params=params)

    # ---- Orders: reads (auth) -----------------------------------------------------
    async def get_orders(self, params: dict | None = None) -> Any:
        self._require_auth()
        return await self.get("/portfolio/orders", params=params)

    async def get_order(self, order_id: str) -> Any:
        self._require_auth()
        return await self.get(f"/portfolio/orders/{order_id}")

    # ---- Orders: writes / V2 (auth) -----------------------------------------------
    async def create_order(self, payload: dict) -> Any:
        self._require_auth()
        return await self.post("/portfolio/events/orders", json=payload)

    async def cancel_order(self, order_id: str) -> Any:
        self._require_auth()
        return await self.delete(f"/portfolio/events/orders/{order_id}")

    async def amend_order(self, order_id: str, payload: dict) -> Any:
        self._require_auth()
        return await self.post(
            f"/portfolio/events/orders/{order_id}/amend", json=payload
        )

    async def decrease_order(self, order_id: str, payload: dict) -> Any:
        self._require_auth()
        return await self.post(
            f"/portfolio/events/orders/{order_id}/decrease", json=payload
        )
