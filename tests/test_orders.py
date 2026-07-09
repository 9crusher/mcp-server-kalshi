"""Tests for the friendly->V2 order translation and the confirm-gate guardrail."""

import pytest

from mcp_server_kalshi.kalshi_client.client import (
    build_amend_order_payload,
    build_create_order_payload,
    build_decrease_order_payload,
    series_ticker_from_market,
)


def test_series_ticker_derivation():
    assert series_ticker_from_market("KXELONMARS-99") == "KXELONMARS"
    assert series_ticker_from_market("HIGHNY-24JAN01-T60") == "HIGHNY"


@pytest.mark.parametrize(
    "action,side,cents,expected_book_side,expected_price",
    [
        ("buy", "yes", 12, "bid", "0.1200"),  # buy YES -> bid at yes price
        ("sell", "yes", 12, "ask", "0.1200"),  # sell YES -> ask at yes price
        ("buy", "no", 30, "ask", "0.7000"),  # buy NO @30 == sell YES @70
        ("sell", "no", 30, "bid", "0.7000"),  # sell NO @30 == buy YES @70
    ],
)
def test_create_order_translation(
    action, side, cents, expected_book_side, expected_price
):
    payload = build_create_order_payload(
        ticker="KXELONMARS-99",
        action=action,
        side=side,
        count=10,
        limit_price_cents=cents,
    )
    assert payload["side"] == expected_book_side
    assert payload["price"] == expected_price
    assert payload["count"] == "10"
    assert payload["ticker"] == "KXELONMARS-99"
    assert payload["time_in_force"] == "good_till_canceled"
    assert payload["self_trade_prevention_type"] == "taker_at_cross"


def test_create_order_optional_fields():
    payload = build_create_order_payload(
        ticker="X-1",
        action="buy",
        side="yes",
        count=2.5,
        limit_price_cents=50,
        post_only=True,
        client_order_id="abc",
        expiration_ts=1234,
    )
    assert payload["count"] == "2.5"
    assert payload["post_only"] is True
    assert payload["client_order_id"] == "abc"
    assert payload["expiration_time"] == 1234


def test_amend_payload_uses_same_translation():
    payload = build_amend_order_payload(
        ticker="X-1", action="buy", side="no", count=5, limit_price_cents=40
    )
    assert payload == {"ticker": "X-1", "side": "ask", "price": "0.6000", "count": "5"}


def test_decrease_payload_requires_exactly_one():
    assert build_decrease_order_payload(reduce_by=3) == {"reduce_by": "3"}
    assert build_decrease_order_payload(reduce_to=1) == {"reduce_to": "1"}
    with pytest.raises(ValueError):
        build_decrease_order_payload()
    with pytest.raises(ValueError):
        build_decrease_order_payload(reduce_by=1, reduce_to=2)


class _SpyClient:
    """Records create_order calls so we can assert the guardrail never places on preview."""

    def __init__(self):
        self.create_calls = []

    async def create_order(self, payload):
        self.create_calls.append(payload)
        return {"order": {"order_id": "ord_1", "status": "resting"}}


async def test_create_order_preview_does_not_place(monkeypatch):
    from mcp_server_kalshi import server

    spy = _SpyClient()
    monkeypatch.setattr(server, "kalshi_client", spy)

    out = await server.handle_create_order(
        {"ticker": "X-1", "action": "buy", "side": "yes", "count": 3, "limit_price": 40}
    )
    result = out[0].text
    assert "preview" in result.lower()
    assert "confirm=true" in result
    assert spy.create_calls == []  # nothing placed


async def test_create_order_confirm_places(monkeypatch):
    from mcp_server_kalshi import server

    spy = _SpyClient()
    monkeypatch.setattr(server, "kalshi_client", spy)

    out = await server.handle_create_order(
        {
            "ticker": "X-1",
            "action": "buy",
            "side": "yes",
            "count": 3,
            "limit_price": 40,
            "confirm": True,
        }
    )
    assert len(spy.create_calls) == 1
    assert spy.create_calls[0]["side"] == "bid"
    assert spy.create_calls[0]["price"] == "0.4000"
    assert "placed" in out[0].text.lower()
