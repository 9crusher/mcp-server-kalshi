"""Wire-level tests for representative KalshiAPIClient endpoint methods.

Confirms each builds the right path + params/body, through an injected mock transport.
"""

import httpx


async def test_get_market_builds_path(make_client):
    client, requests = make_client(
        lambda req: httpx.Response(200, json={"market": {"ticker": "KXELONMARS-99"}})
    )
    out = await client.get_market("KXELONMARS-99")
    assert out == {"market": {"ticker": "KXELONMARS-99"}}
    assert requests[0].url.path == "/trade-api/v2/markets/KXELONMARS-99"


async def test_get_market_orderbook_omits_depth_when_none(make_client):
    client, requests = make_client(lambda req: httpx.Response(200, json={}))
    await client.get_market_orderbook("X-1")
    assert requests[0].url.path == "/trade-api/v2/markets/X-1/orderbook"
    assert "depth" not in dict(requests[0].url.params)

    await client.get_market_orderbook("X-1", depth=5)
    assert dict(requests[1].url.params) == {"depth": "5"}


async def test_candlesticks_derives_series_and_assembles_params(make_client):
    client, requests = make_client(lambda req: httpx.Response(200, json={}))
    await client.get_market_candlesticks(
        ticker="KXELONMARS-99",
        start_ts=1000,
        end_ts=2000,
        period_interval=60,
    )
    # Series ('KXELONMARS') is derived from the market ticker when not supplied.
    assert (
        requests[0].url.path
        == "/trade-api/v2/series/KXELONMARS/markets/KXELONMARS-99/candlesticks"
    )
    assert dict(requests[0].url.params) == {
        "start_ts": "1000",
        "end_ts": "2000",
        "period_interval": "60",
    }


async def test_candlesticks_honors_explicit_series(make_client):
    client, requests = make_client(lambda req: httpx.Response(200, json={}))
    await client.get_market_candlesticks(
        ticker="KXELONMARS-99",
        start_ts=1,
        end_ts=2,
        period_interval=1,
        series_ticker="OVERRIDE",
    )
    assert requests[0].url.path.startswith("/trade-api/v2/series/OVERRIDE/")


async def test_create_order_posts_payload_when_authenticated(make_client, rsa_key_file):
    import json as _json

    captured = {}

    def responder(req):
        captured["path"] = req.url.path
        captured["body"] = _json.loads(req.content)
        return httpx.Response(200, json={"order": {"order_id": "ord_1"}})

    client, _ = make_client(responder, api_key="key-id", private_key_path=rsa_key_file)
    payload = {"ticker": "X-1", "side": "bid", "price": "0.4000", "count": "3"}
    out = await client.create_order(payload)

    assert out == {"order": {"order_id": "ord_1"}}
    assert captured["path"] == "/trade-api/v2/portfolio/events/orders"
    assert captured["body"] == payload
