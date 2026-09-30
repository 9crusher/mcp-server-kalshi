"""Tests for the optional kalshi_predictit_arb tool.

Offline only: demo mode must make no network calls, live mode is exercised against an
``httpx.MockTransport`` fake x402 server, and signing uses a throwaway
``Account.create()`` key (those tests skip when eth-account is not installed).
"""

import base64
import json
from pathlib import Path

import httpx
import pytest
from conftest import handler_result
from pydantic import ValidationError

from mcp_server_kalshi import kalshi_predictit_arb as arb
from mcp_server_kalshi import server

FIXTURE = Path(__file__).parent / "fixtures" / "kalshi_predictit_arb_sample.json"
PAY_TO = "0x" + "ab" * 20
LIVE_BODY = {
    "q": "senate",
    "mode": "opportunities",
    "opportunities": [
        {
            "event": "LIVE-TEST event",
            "kalshi": {"ticker": "LIVE-TEST-1"},
            "best_direction": {"net_yield_c": 2.5, "net_yield_pct": 2.6},
            "executable": True,
        }
    ],
    "stats": {"pairs_evaluated": 1, "executable": 1},
    "fetched_at": "2026-01-01T00:00:00Z",
}


def _requirement(**overrides):
    requirement = {
        "scheme": "exact",
        "network": "eip155:8453",
        "amount": "20000",
        "asset": arb.BASE_USDC,
        "payTo": PAY_TO,
        "maxTimeoutSeconds": 60,
        "extra": {"name": "USD Coin", "version": "2"},
    }
    requirement.update(overrides)
    return requirement


def _required(accepts):
    return {"x402Version": 2, "resource": {"url": arb.DEFAULT_URL}, "accepts": accepts}


def _b64(obj, urlsafe=False, pad=True):
    raw = json.dumps(obj).encode()
    enc = base64.urlsafe_b64encode(raw) if urlsafe else base64.b64encode(raw)
    text = enc.decode()
    return text if pad else text.rstrip("=")


class FakeX402Server:
    """402 until a PAYMENT-SIGNATURE header arrives, then 200 (unless always_402)."""

    def __init__(self, required, variant="header", always_402=False):
        self.required = required
        self.variant = variant
        self.always_402 = always_402
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if "PAYMENT-SIGNATURE" in request.headers and not self.always_402:
            headers = {"PAYMENT-RESPONSE": _b64({"success": True})}
            return httpx.Response(200, json=LIVE_BODY, headers=headers)
        if self.variant == "body":
            return httpx.Response(402, json=self.required)
        urlsafe = self.variant == "urlsafe"
        header = _b64(self.required, urlsafe=urlsafe, pad=not urlsafe)
        return httpx.Response(402, headers={"PAYMENT-REQUIRED": header})


class RecordingSigner:
    """Stand-in signer (no eth-account needed) that records every signing request."""

    address = "0x" + "11" * 20

    def __init__(self):
        self.calls: list[dict] = []

    def sign_typed_data(self, typed_data):
        self.calls.append(typed_data)
        return "0x" + "00" * 65


def _client(signer, server_, **kwargs):
    return arb.KalshiPredictItArbClient(
        signer, transport=httpx.MockTransport(server_), **kwargs
    )


async def _call(client, **request):
    handler = arb.make_handler(client)
    return await handler(request)


@pytest.fixture
def no_network(monkeypatch):
    async def _blocked(*args, **kwargs):
        raise AssertionError("network call attempted in demo mode")

    monkeypatch.setattr(httpx.AsyncClient, "send", _blocked)


@pytest.fixture
def clean_env(monkeypatch):
    for name in arb.ArbSettings.model_fields:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def registry(monkeypatch):
    """The real ToolRegistry with its tool map copied, so registration can't leak."""
    monkeypatch.setattr(server.ToolRegistry, "_tools", dict(server.ToolRegistry._tools))
    return server.ToolRegistry


@pytest.fixture
def eth_signer():
    pytest.importorskip("eth_account")
    from eth_account import Account

    return arb.EthAccountSigner(Account.create().key.hex())


# ---- Fixture / defaults ------------------------------------------------------------
def test_fixture_is_fictional_and_matches_embedded_sample():
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert fixture == arb.SAMPLE_RESPONSE
    assert "NOT real market data" in fixture["_notice"]
    assert all(r["event"].startswith("SAMPLE") for r in fixture["opportunities"])


def test_settings_defaults_are_off_demo_and_capped(clean_env):
    settings = arb.ArbSettings(_env_file=None)
    assert settings.KALSHI_PREDICTIT_ARB_ENABLED is False
    assert settings.X402_WALLET_KEY is None
    assert settings.KALSHI_PREDICTIT_ARB_MAX_USD_PER_CALL == 0.02
    client = arb.build_client(settings)
    assert client.live is False
    assert client.max_atomic == 20000
    assert arb.KalshiPredictItArbClient().max_atomic == 20000


# ---- Registration ------------------------------------------------------------------
def test_tool_is_not_registered_by_default():
    assert arb.TOOL_NAME not in {t.name for t in server.ToolRegistry.get_tools()}


def test_register_if_enabled_is_a_noop_when_disabled(registry, clean_env):
    before = set(registry._tools)
    assert arb.register_if_enabled(registry, arb.ArbSettings(_env_file=None)) is False
    assert set(registry._tools) == before


def test_register_if_enabled_registers_a_read_only_tool(registry, clean_env):
    settings = arb.ArbSettings(_env_file=None, KALSHI_PREDICTIT_ARB_ENABLED=True)
    assert arb.register_if_enabled(registry, settings) is True
    tool = next(t for t in registry.get_tools() if t.name == arb.TOOL_NAME)
    schema = tool.inputSchema
    assert set(schema["properties"]) == {"q", "limit", "mode"}
    assert schema["required"] == []
    assert schema["additionalProperties"] is False
    assert schema["properties"]["mode"]["enum"] == ["opportunities", "all"]
    assert schema["properties"]["limit"]["maximum"] == 25
    assert "$0.02" in tool.description and "Team Takatini" in tool.description
    if tool.annotations is not None:
        assert tool.annotations.readOnlyHint is True
        assert tool.annotations.destructiveHint is False


async def test_registered_tool_runs_through_call_tool(registry, clean_env, no_network):
    settings = arb.ArbSettings(_env_file=None, KALSHI_PREDICTIT_ARB_ENABLED=True)
    arb.register_if_enabled(registry, settings)
    out = handler_result(await server.handle_call_tool(arb.TOOL_NAME, {"q": "senate"}))
    assert out["mode"] == "demo" and out["sample_data"] is True
    assert out["summary"]["kalshi_tickers"] == ["SAMPLE-SENATEYY-26-D"]

    bad = await server.handle_call_tool(arb.TOOL_NAME, {"limit": 99})
    assert bad[0].text.startswith(f"Error in {arb.TOOL_NAME}:")


def test_empty_key_stays_in_demo(clean_env):
    settings = arb.ArbSettings(_env_file=None, X402_WALLET_KEY="  ")
    assert arb.build_client(settings).live is False


def test_live_mode_needs_explicit_key(clean_env):
    pytest.importorskip("eth_account")
    from eth_account import Account

    key = Account.create().key.hex()
    client = arb.build_client(arb.ArbSettings(_env_file=None, X402_WALLET_KEY=key))
    assert client.live is True
    assert key not in repr(client.signer)


# ---- Demo mode ---------------------------------------------------------------------
async def test_demo_output_shape_and_no_network(no_network):
    out = await _call(arb.KalshiPredictItArbClient())
    assert out["source"] == "kalshi-predictit-arb"
    assert out["mode"] == "demo" and out["sample_data"] is True
    assert "NOT real market data" in out["notice"]
    assert out["query"] == {"q": "", "limit": 10, "mode": "opportunities"}
    assert out["cost"]["paid_usd"] == 0
    assert out["cost"]["max_usd_per_call"] == 0.02
    assert out["summary"] == {
        "returned": 2,
        "executable": 2,
        "best_net_yield_c": 3.1,
        "kalshi_tickers": ["SAMPLE-GOVPARTYXX-26-R", "SAMPLE-SENATEYY-26-D"],
    }
    assert all(r["executable"] for r in out["opportunities"])
    assert "get_market_orderbook" in out["caveat"]
    assert out["docs"] == arb.DOCS_URL


async def test_demo_filters_and_tolerates_missing_fields(no_network):
    client = arb.KalshiPredictItArbClient()
    everything = await _call(client, mode="all", limit=25)
    assert everything["summary"]["returned"] == 4
    assert everything["summary"]["executable"] == 2
    assert everything["summary"]["best_net_yield_c"] == 3.1
    assert len(everything["summary"]["kalshi_tickers"]) == 3  # one row has no kalshi
    governor = await _call(client, mode="all", q="Governor")
    assert governor["summary"]["returned"] == 1
    assert (await _call(client, mode="all", limit=1))["summary"]["returned"] == 1
    none = await _call(client, q="no-such-market")
    assert none["summary"] == {
        "returned": 0,
        "executable": 0,
        "best_net_yield_c": None,
        "kalshi_tickers": [],
    }


@pytest.mark.parametrize(
    "request_", [{"limit": 0}, {"limit": 26}, {"mode": "bogus"}, {"limit": "x"}]
)
async def test_invalid_input_is_rejected(request_, no_network):
    with pytest.raises(ValidationError):
        await _call(arb.KalshiPredictItArbClient(), **request_)


# ---- Live mode: 402 -> sign -> retry ------------------------------------------------
async def test_402_sign_retry_with_stub_signer():
    signer = RecordingSigner()
    fake = FakeX402Server(_required([_requirement()]))
    client = _client(signer, fake)
    out = await _call(client, q="senate", limit=5)

    assert len(fake.requests) == 2
    assert "PAYMENT-SIGNATURE" not in fake.requests[0].headers
    assert fake.requests[1].url.params["q"] == "senate"
    assert fake.requests[1].url.params["limit"] == "5"
    header = fake.requests[1].headers["PAYMENT-SIGNATURE"]
    assert fake.requests[1].headers["X-PAYMENT"] == header
    assert not set("+/=") & set(header)
    assert len(signer.calls) == 1

    assert (
        out["mode"] == "live" and out["sample_data"] is False and out["notice"] is None
    )
    assert out["cost"]["paid_usd"] == 0.02
    assert out["summary"]["kalshi_tickers"] == ["LIVE-TEST-1"]
    assert client.spent_atomic == 20000
    assert client.last_payment_response == {"success": True}


@pytest.mark.parametrize("variant", ["header", "urlsafe", "body"])
async def test_402_sign_retry_signature_recovers(eth_signer, variant):
    from eth_account import Account
    from eth_account.messages import encode_typed_data

    requirement = _requirement()
    fake = FakeX402Server(_required([requirement]), variant=variant)
    await _call(_client(eth_signer, fake))

    header = fake.requests[1].headers["PAYMENT-SIGNATURE"]
    assert not set("+/=") & set(header)
    payload = json.loads(base64.urlsafe_b64decode(header + "=" * (-len(header) % 4)))
    assert payload["x402Version"] == 2
    assert payload["accepted"] == requirement
    assert payload["resource"] == {"url": arb.DEFAULT_URL}
    auth = payload["payload"]["authorization"]
    assert auth["from"] == eth_signer.address
    assert auth["to"] == PAY_TO
    assert auth["value"] == "20000"
    assert all(isinstance(value, str) for value in auth.values())
    assert int(auth["validBefore"]) - int(auth["validAfter"]) == 660
    assert auth["nonce"].startswith("0x") and len(auth["nonce"]) == 66

    message = {
        "from": auth["from"],
        "to": auth["to"],
        "value": int(auth["value"]),
        "validAfter": int(auth["validAfter"]),
        "validBefore": int(auth["validBefore"]),
        "nonce": bytes.fromhex(auth["nonce"][2:]),
    }
    typed = arb.build_typed_data(requirement, message)
    assert typed["domain"]["chainId"] == 8453
    signable = encode_typed_data(full_message=typed)
    signature = payload["payload"]["signature"]
    assert Account.recover_message(signable, signature=signature) == eth_signer.address


async def test_second_402_fails_after_exactly_one_retry():
    fake = FakeX402Server(_required([_requirement()]), always_402=True)
    client = _client(RecordingSigner(), fake)
    with pytest.raises(arb.PaymentFailed):
        await _call(client)
    assert len(fake.requests) == 2
    assert client.spent_atomic == 0


async def test_first_acceptable_requirement_is_used():
    good = _requirement(amount="10000")
    fake = FakeX402Server(_required([_requirement(network="eip155:1"), good]))
    out = await _call(_client(RecordingSigner(), fake))
    header = fake.requests[1].headers["PAYMENT-SIGNATURE"]
    assert arb.decode_b64_json(header)["accepted"] == good
    assert out["cost"]["paid_usd"] == 0.01


# ---- Refusals ----------------------------------------------------------------------
@pytest.mark.parametrize(
    "accepts, needle",
    [
        ([_requirement(network="eip155:1")], "not Base"),
        ([_requirement(network="solana")], "not Base"),
        ([_requirement(scheme="upto")], "not exact"),
        ([_requirement(asset="0x" + "cd" * 20)], "not Base USDC"),
        ([_requirement(amount="20001")], "exceeds cap"),
        ([_requirement(amount="1000000")], "exceeds cap"),
        ([_requirement(amount="0")], "must be positive"),
        ([_requirement(amount="-5")], "must be positive"),
        ([_requirement(amount="abc")], "invalid amount"),
        ([_requirement(payTo="0x123")], "invalid payTo"),
        ([_requirement(payTo="0x" + "zz" * 20)], "invalid payTo"),
        ([_requirement(payTo=None)], "invalid payTo"),
        (["not-a-dict"], "malformed"),
        ([], "no payment requirements"),
        (None, "no payment requirements"),
    ],
)
async def test_refusals_happen_before_signing(accepts, needle):
    required = _required(accepts)
    if accepts is None:
        del required["accepts"]
    signer = RecordingSigner()
    fake = FakeX402Server(required)
    with pytest.raises(arb.PaymentRefused, match=needle):
        await _call(_client(signer, fake))
    assert signer.calls == []
    assert len(fake.requests) == 1


async def test_lower_cap_refuses_the_default_price():
    fake = FakeX402Server(_required([_requirement()]))
    client = _client(RecordingSigner(), fake, max_usd_per_call=0.01)
    with pytest.raises(arb.PaymentRefused, match="exceeds cap 10000"):
        await _call(client)


async def test_session_budget_stops_further_payments():
    signer = RecordingSigner()
    fake = FakeX402Server(_required([_requirement()]))
    client = _client(signer, fake, session_budget_usd=0.03)
    await _call(client)
    with pytest.raises(arb.PaymentRefused, match="session budget"):
        await _call(client)
    assert len(signer.calls) == 1
    assert client.spent_atomic == 20000


async def test_402_without_requirements_is_refused():
    def handler(request):
        return httpx.Response(402, text="pay up")

    with pytest.raises(arb.PaymentRefused, match="without payment requirements"):
        await _call(_client(RecordingSigner(), handler))


# ---- Header codec ------------------------------------------------------------------
def test_outgoing_header_is_unpadded_base64url():
    payload = {"x402Version": 2, "blob": "\xff\xfe>>>???" * 7}
    header = arb.encode_payment_header(payload)
    assert not set("+/=") & set(header)
    assert arb.decode_b64_json(header) == payload


@pytest.mark.parametrize("urlsafe", [False, True])
@pytest.mark.parametrize("pad", [False, True])
def test_incoming_decode_is_tolerant(urlsafe, pad):
    obj = {"accepts": [{"x": "\xff\xfe>>>???"}], "n": 1}
    assert arb.decode_b64_json(_b64(obj, urlsafe=urlsafe, pad=pad)) == obj


@pytest.mark.parametrize("value", [None, "", "!!!not-base64!!!", "e30@@"])
def test_decode_garbage_returns_none(value):
    assert arb.decode_b64_json(value) is None
