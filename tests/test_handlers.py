"""Tests for the MCP tool surface: registry integrity + handler wiring.

Handlers are driven through the registry with the module-level client monkeypatched to a
FakeClient recorder (see conftest) — no network, no credentials.
"""

import pytest
from conftest import FakeClient, handler_result

from mcp_server_kalshi import server

EXPECTED_TOOLS = {
    # discovery
    "list_markets",
    "get_market",
    "list_events",
    "get_event",
    "list_series",
    "get_series",
    # research / rules
    "get_market_orderbook",
    "get_market_candlesticks",
    "get_market_trades",
    "get_market_rules",
    "fetch_rules_pdf",
    # environment
    "get_environment",
    # exchange
    "get_exchange_status",
    "get_exchange_schedule",
    # portfolio
    "get_balance",
    "get_positions",
    "get_fills",
    "get_settlements",
    # orders / trading
    "list_orders",
    "get_order",
    "create_order",
    "cancel_order",
    "amend_order",
    "decrease_order",
}


def test_registry_exposes_exactly_the_expected_tools():
    names = {tool.name for tool in server.ToolRegistry.get_tools()}
    assert names == EXPECTED_TOOLS


def test_every_tool_has_a_valid_input_schema():
    for tool in server.ToolRegistry.get_tools():
        schema = tool.inputSchema
        assert schema["type"] == "object", tool.name
        assert isinstance(schema["properties"], dict), tool.name
        assert isinstance(schema["required"], list), tool.name
        assert schema["additionalProperties"] is False, tool.name
        # Required fields must actually be declared as properties.
        assert set(schema["required"]).issubset(schema["properties"]), tool.name
        assert (tool.description or "").strip(), tool.name


def test_get_handler_unknown_tool_raises():
    with pytest.raises(ValueError, match="Unknown tool"):
        server.ToolRegistry.get_handler("does_not_exist")


async def test_get_environment_reports_configured_env():
    handler = server.ToolRegistry.get_handler("get_environment")
    out = handler_result(await handler({}))

    # Mirrors whatever the server module resolved at import; no client call needed.
    assert out["environment"] == server.settings.env_label
    assert out["is_production"] == server.settings.is_production
    assert out["base_url"] == server.settings.rest_base_url
    assert out["has_credentials"] == server.settings.has_credentials


def test_background_info_states_the_resolved_environment():
    # Instructions must assert the environment as fact, not "demo unless configured".
    prod = server._background_info("PROD (real money)", is_production=True)
    demo = server._background_info("DEMO (sandbox)", is_production=False)
    assert "PROD (real money)" in prod and "REAL" in prod
    assert "DEMO (sandbox)" in demo and "simulated" in demo


async def test_list_markets_handler_calls_client(monkeypatch):
    fake = FakeClient(get_markets={"markets": []})
    monkeypatch.setattr(server, "kalshi_client", fake)

    handler = server.ToolRegistry.get_handler("list_markets")
    out = await handler({"status": "open"})

    assert fake.called("get_markets")
    # Validated query params are forwarded (None-valued fields dropped).
    assert fake.calls[0] == ("get_markets", ({"status": "open"},), {})
    assert handler_result(out) == {"markets": []}


async def test_get_market_handler_passes_ticker(monkeypatch):
    fake = FakeClient(get_market={"market": {"ticker": "X-1"}})
    monkeypatch.setattr(server, "kalshi_client", fake)

    handler = server.ToolRegistry.get_handler("get_market")
    await handler({"ticker": "X-1"})

    assert fake.calls == [("get_market", ("X-1",), {})]


async def test_get_market_rules_degrades_gracefully_on_series_error(monkeypatch):
    fake = FakeClient(
        get_market={"market": {"event_ticker": "EV-1", "title": "T", "status": "open"}},
        get_series=RuntimeError("series unavailable"),  # best-effort; must not blow up
        get_event={"event": {"settlement_sources": ["S3"]}},
    )
    monkeypatch.setattr(server, "kalshi_client", fake)

    handler = server.ToolRegistry.get_handler("get_market_rules")
    out = handler_result(await handler({"ticker": "KXELONMARS-99"}))

    assert out["series_ticker"] == "KXELONMARS"
    assert out["settlement_sources"] == ["S3"]  # fell through to the event's sources
    assert out["contract_terms_url"] is None  # series lookup failed, no PDF link


async def test_fetch_rules_pdf_requires_a_source(monkeypatch):
    monkeypatch.setattr(server, "kalshi_client", FakeClient())
    handler = server.ToolRegistry.get_handler("fetch_rules_pdf")
    with pytest.raises(ValueError, match="Provide a url"):
        await handler({})


async def test_fetch_rules_pdf_errors_when_series_lacks_url(monkeypatch):
    fake = FakeClient(get_series={"series": {}})  # no contract_terms_url present
    monkeypatch.setattr(server, "kalshi_client", fake)

    handler = server.ToolRegistry.get_handler("fetch_rules_pdf")
    with pytest.raises(ValueError, match="no contract_terms_url"):
        await handler({"ticker": "KXELONMARS-99"})
