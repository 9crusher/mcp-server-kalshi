"""Optional read-only tool: ``kalshi_predictit_arb`` (Kalshi <-> PredictIt arbitrage feed).

Off by default. Set ``KALSHI_PREDICTIT_ARB_ENABLED=true`` to register the tool.

The tool reads a third-party scanner that matches Kalshi markets to PredictIt
contracts (state/district/office/party/strike/cycle gating; a party mismatch is a
hard reject), prices both arbitrage directions after each venue's fees (Kalshi
taker ``ceil(7*P*(1-P))`` cents per leg; PredictIt 10% of winning-leg profit plus
5% withdrawal drag) and reports the worst-case net across settlement outcomes.
``executable`` is true only at >= 1c net. Gaps are indicative until checked against
live depth, current fees and resolution equivalence; the Kalshi ticker in each row
can be passed to ``get_market_orderbook`` / ``get_market_rules`` to do that.

Cost and modes
--------------

- **Demo (default):** with no ``X402_WALLET_KEY`` the tool makes no network calls,
  costs nothing and returns ``SAMPLE_RESPONSE`` (fictional pairs and prices, NOT
  real market data; every response says ``sample_data: true``).
- **Live (opt-in, paid):** with ``X402_WALLET_KEY`` set (and ``eth-account``
  installed) each call costs $0.02 USDC on Base, paid via x402 v2 (``exact``
  scheme, EIP-3009 ``TransferWithAuthorization`` signed locally; the key never
  leaves the machine). Payment requirements are refused unless they are Base /
  ``exact`` / Base USDC / ``0 < amount <= KALSHI_PREDICTIT_ARB_MAX_USD_PER_CALL``
  (default 0.02) with a valid ``payTo``, and total spend per server process is
  capped by ``KALSHI_PREDICTIT_ARB_SESSION_BUDGET_USD`` (default 0.20). The signed
  payment is sent once, as unpadded base64url, in ``PAYMENT-SIGNATURE`` and
  ``X-PAYMENT``; a second 402 is an error (no retry loop).

Disclosure: kalshi-predictit-arb is built and operated by Team Takatini.
Docs: https://mastertyrone.github.io/kalshi-predictit-arb/
Client: https://github.com/mastertyrone/kalshi-predictit-arb
"""

import base64
import copy
import json
import secrets
import time
from collections.abc import Callable
from decimal import Decimal, InvalidOperation
from typing import Any, Literal, Protocol

import httpx
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from .kalshi_client.schemas import MCPSchemaBaseModel

TOOL_NAME = "kalshi_predictit_arb"
DEFAULT_URL = (
    "https://x402.bankr.bot/0x69fb671637ed68881f66b9ebf305ec3ef5574f65"
    "/kalshi-predictit-arb"
)
DOCS_URL = "https://mastertyrone.github.io/kalshi-predictit-arb/"
BASE_NETWORKS = ("eip155:8453", "base")
BASE_CHAIN_ID = 8453
BASE_USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
USDC_DECIMALS = 6
CAVEAT = (
    "Indicative until checked against live depth, current fees and resolution "
    "equivalence. Verify the Kalshi leg with get_market_orderbook and "
    "get_market_rules; PredictIt publishes no public depth (size within its "
    "$850/contract limit)."
)
SAMPLE_NOTICE = (
    "SAMPLE DATA: fictional pairs and prices, NOT real market data. Set "
    "X402_WALLET_KEY to query the live feed ($0.02 USDC per call on Base)."
)

# Fictional SAMPLE data, NOT real market data. Kept identical to
# tests/fixtures/kalshi_predictit_arb_sample.json (asserted by the tests).
SAMPLE_RESPONSE: dict[str, Any] = {
    "_notice": "SAMPLE DATA for offline demo/tests only. Fictional pairs and prices, NOT "
    "real market data.",
    "q": "",
    "mode": "all",
    "opportunities": [
        {
            "event": "SAMPLE State XX governor party winner? - Republican",
            "match_score": 0.74,
            "kalshi": {
                "ticker": "SAMPLE-GOVPARTYXX-26-R",
                "yes_bid_c": 61,
                "yes_ask_c": 62,
            },
            "predictit": {
                "market": "SAMPLE State XX governor party winner?",
                "contract": "Republican",
                "yes_ask_c": 70,
                "no_ask_c": 33,
                "position_limit_usd": 850,
            },
            "best_direction": {
                "direction": "YES_KALSHI__NO_PREDICTIT",
                "kalshi_price_c": 62,
                "predictit_price_c": 33,
                "stake_c": 95,
                "raw_spread_c": 5,
                "net_if_yes_wins_c": 3.1,
                "net_if_no_wins_c": 5.4,
                "net_yield_c": 3.1,
                "net_yield_pct": 3.26,
                "fees": {
                    "kalshi_taker_c": 2,
                    "predictit_profit_fee_c": 6.7,
                    "predictit_withdrawal_drag_c": 3.35,
                },
            },
            "days_to_settlement": 120,
            "roc_annualized_pct": 9.9,
            "executable": True,
            "liquidity": {
                "vwap_buy_c": {"100": 62, "500": 62, "1000": 63},
                "book_depth_usd": 12000.0,
            },
            "slippage_ok_100": True,
        },
        {
            "event": "SAMPLE State YY Senate winner? - Democratic",
            "match_score": 0.69,
            "kalshi": {
                "ticker": "SAMPLE-SENATEYY-26-D",
                "yes_bid_c": 44,
                "yes_ask_c": 45,
            },
            "predictit": {
                "market": "SAMPLE Which party will win the YY Senate " "race?",
                "contract": "Democratic",
                "yes_ask_c": 41,
                "no_ask_c": 61,
                "position_limit_usd": 850,
            },
            "best_direction": {
                "direction": "YES_PREDICTIT__NO_KALSHI",
                "kalshi_price_c": 56,
                "predictit_price_c": 41,
                "stake_c": 97,
                "raw_spread_c": 3,
                "net_if_yes_wins_c": 1.2,
                "net_if_no_wins_c": 1.4,
                "net_yield_c": 1.2,
                "net_yield_pct": 1.24,
                "fees": {
                    "kalshi_taker_c": 2,
                    "predictit_profit_fee_c": 5.9,
                    "predictit_withdrawal_drag_c": 2.95,
                },
            },
            "days_to_settlement": 400,
            "roc_annualized_pct": 1.1,
            "executable": True,
            "liquidity": {
                "vwap_buy_c": {"100": 56, "500": 57, "1000": 57},
                "book_depth_usd": 4000.0,
            },
            "slippage_ok_100": True,
        },
        {
            "event": "SAMPLE District ZZ-01 House winner? - Republican",
            "match_score": 0.66,
            "kalshi": {
                "ticker": "SAMPLE-HOUSEZZ01-26-R",
                "yes_bid_c": 80,
                "yes_ask_c": 81,
            },
            "predictit": {
                "market": "SAMPLE ZZ-01 House race",
                "contract": "Republican",
                "yes_ask_c": 83,
                "no_ask_c": 19,
                "position_limit_usd": 850,
            },
            "best_direction": {
                "direction": "YES_KALSHI__NO_PREDICTIT",
                "kalshi_price_c": 81,
                "predictit_price_c": 19,
                "stake_c": 100,
                "raw_spread_c": 0,
                "net_if_yes_wins_c": -2.0,
                "net_if_no_wins_c": 4.3,
                "net_yield_c": -2.0,
                "net_yield_pct": -2.0,
                "fees": {
                    "kalshi_taker_c": 2,
                    "predictit_profit_fee_c": 8.1,
                    "predictit_withdrawal_drag_c": 4.05,
                },
            },
            "days_to_settlement": 400,
            "roc_annualized_pct": -1.8,
            "executable": False,
            "liquidity": {
                "vwap_buy_c": {"100": 81, "500": 82, "1000": 82},
                "book_depth_usd": 2500.0,
            },
            "slippage_ok_100": False,
        },
        {"event": "SAMPLE record with missing fields (clients must tolerate " "this)"},
    ],
    "stats": {
        "pairs_evaluated": 4,
        "executable": 2,
        "kalshi_markets_scanned": 4,
        "predictit_contracts_scanned": 4,
        "duration_ms": 0,
    },
    "fetched_at": "2026-01-01T00:00:00.000Z",
}


class PaymentRefused(Exception):
    """No acceptable payment requirement (network, scheme, asset, amount, payTo)."""


class PaymentFailed(Exception):
    """A signed payment was sent but the server still answered 402."""


class ArbSettings(BaseSettings):
    """Settings for the optional tool (environment and/or ``.env``)."""

    KALSHI_PREDICTIT_ARB_ENABLED: bool = Field(
        default=False, description="Register the kalshi_predictit_arb tool."
    )
    X402_WALLET_KEY: SecretStr | None = Field(
        default=None,
        description="Wallet key for live (paid) mode. Unset = offline demo.",
    )
    KALSHI_PREDICTIT_ARB_MAX_USD_PER_CALL: float = Field(
        default=0.02, description="Refuse any single payment above this (USD)."
    )
    KALSHI_PREDICTIT_ARB_SESSION_BUDGET_USD: float = Field(
        default=0.20, description="Refuse payments once this process spent this."
    )
    KALSHI_PREDICTIT_ARB_URL: str = Field(default=DEFAULT_URL)
    KALSHI_PREDICTIT_ARB_TIMEOUT_SECONDS: float = Field(default=30.0)

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


class KalshiPredictItArbRequest(MCPSchemaBaseModel):
    """Query the Kalshi <-> PredictIt cross-venue arbitrage scanner."""

    q: str | None = Field(
        default=None,
        description=(
            "Keyword filter on the matched event, e.g. 'governor', 'senate', a state "
            "name or a Kalshi ticker fragment. Omit to scan everything."
        ),
    )
    limit: int = Field(
        default=10, ge=1, le=25, description="Max pairs evaluated per call (1-25)."
    )
    mode: Literal["opportunities", "all"] = Field(
        default="opportunities",
        description=(
            "'opportunities' returns only executable pairs (>= 1c worst-case net "
            "after fees); 'all' returns every evaluated pair, including negative ones."
        ),
    )


class TypedDataSigner(Protocol):
    address: str

    def sign_typed_data(self, typed_data: dict[str, Any]) -> str: ...


class EthAccountSigner:
    """EIP-712 signer backed by ``eth-account`` (imported lazily)."""

    def __init__(self, private_key: str) -> None:
        try:
            from eth_account import Account
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise RuntimeError(
                "Live mode needs eth-account: pip install eth-account"
            ) from exc
        self._account = Account.from_key(private_key)
        self.address: str = self._account.address

    def sign_typed_data(self, typed_data: dict[str, Any]) -> str:
        from eth_account.messages import encode_typed_data

        signed = self._account.sign_message(encode_typed_data(full_message=typed_data))
        # hexbytes>=1.0 .hex() drops the 0x prefix
        return "0x" + bytes(signed.signature).hex()

    def __repr__(self) -> str:
        return f"EthAccountSigner(address={self.address})"


# ---- x402 helpers ------------------------------------------------------------------
def encode_payment_header(payload: dict[str, Any]) -> str:
    """Unpadded base64url JSON (the form the live endpoint was tested with)."""
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_b64_json(value: str | None) -> Any:
    """Tolerant decode: standard or urlsafe base64, padded or not. None if invalid."""
    if not value:
        return None
    try:
        text = str(value).strip().replace("-", "+").replace("_", "/")
        return json.loads(
            base64.b64decode(text + "=" * (-len(text) % 4), validate=True)
        )
    except (ValueError, TypeError):
        return None


def usd_to_atomic(usd: float | str) -> int:
    try:
        return int(Decimal(str(usd)) * 10**USDC_DECIMALS)
    except (InvalidOperation, ValueError):
        return 0


def _amount(requirement: dict[str, Any]) -> Any:
    # v2 uses 'amount'; v1 used 'maxAmountRequired'
    return requirement.get("amount", requirement.get("maxAmountRequired"))


def refusal_reason(requirement: Any, max_atomic: int) -> str | None:
    if not isinstance(requirement, dict):
        return "malformed requirement"
    if requirement.get("network") not in BASE_NETWORKS:
        return f"network {requirement.get('network')!r} is not Base"
    if requirement.get("scheme") != "exact":
        return f"scheme {requirement.get('scheme')!r} is not exact"
    if str(requirement.get("asset", "")).lower() != BASE_USDC.lower():
        return f"asset {requirement.get('asset')!r} is not Base USDC"
    raw = _amount(requirement)
    try:
        amount = int(raw)
    except (TypeError, ValueError):
        return f"invalid amount {raw!r}"
    if amount <= 0:
        return f"amount {amount} must be positive"
    if amount > max_atomic:
        return f"amount {amount} exceeds cap {max_atomic}"
    pay_to = requirement.get("payTo")
    if not (isinstance(pay_to, str) and pay_to.startswith("0x") and len(pay_to) == 42):
        return f"invalid payTo {pay_to!r}"
    try:
        int(pay_to[2:], 16)
    except ValueError:
        return f"invalid payTo {pay_to!r}"
    return None


def select_requirement(accepts: Any, max_atomic: int) -> dict[str, Any]:
    if not accepts or not isinstance(accepts, list):
        raise PaymentRefused("402 response offered no payment requirements")
    reasons = []
    for requirement in accepts:
        reason = refusal_reason(requirement, max_atomic)
        if reason is None:
            return requirement
        reasons.append(reason)
    raise PaymentRefused("; ".join(reasons))


def build_authorization(
    payer: str, requirement: dict[str, Any], now: int | None = None
) -> dict[str, Any]:
    now = int(time.time()) if now is None else int(now)
    return {
        "from": payer,
        "to": requirement["payTo"],
        "value": int(_amount(requirement)),
        "validAfter": now - 600,
        "validBefore": now + int(requirement.get("maxTimeoutSeconds") or 60),
        "nonce": secrets.token_bytes(32),
    }


def build_typed_data(
    requirement: dict[str, Any], authorization: dict[str, Any]
) -> dict[str, Any]:
    extra = requirement.get("extra") or {}
    return {
        "types": {
            "EIP712Domain": [
                {"name": "name", "type": "string"},
                {"name": "version", "type": "string"},
                {"name": "chainId", "type": "uint256"},
                {"name": "verifyingContract", "type": "address"},
            ],
            "TransferWithAuthorization": [
                {"name": "from", "type": "address"},
                {"name": "to", "type": "address"},
                {"name": "value", "type": "uint256"},
                {"name": "validAfter", "type": "uint256"},
                {"name": "validBefore", "type": "uint256"},
                {"name": "nonce", "type": "bytes32"},
            ],
        },
        "primaryType": "TransferWithAuthorization",
        "domain": {
            "name": extra.get("name") or "USD Coin",
            "version": extra.get("version") or "2",
            "chainId": BASE_CHAIN_ID,
            "verifyingContract": requirement["asset"],
        },
        "message": authorization,
    }


def build_payment_payload(
    requirement: dict[str, Any],
    resource: Any,
    authorization: dict[str, Any],
    signature: str,
) -> dict[str, Any]:
    return {
        "x402Version": 2,
        "resource": resource,
        "accepted": requirement,
        "payload": {
            "signature": signature if signature.startswith("0x") else f"0x{signature}",
            "authorization": {
                "from": authorization["from"],
                "to": authorization["to"],
                "value": str(authorization["value"]),
                "validAfter": str(authorization["validAfter"]),
                "validBefore": str(authorization["validBefore"]),
                "nonce": "0x" + authorization["nonce"].hex(),
            },
        },
    }


# ---- Client ------------------------------------------------------------------------
class KalshiPredictItArbClient:
    """Fetches the feed: offline sample without a signer, x402-paid GET with one."""

    def __init__(
        self,
        signer: TypedDataSigner | None = None,
        *,
        url: str = DEFAULT_URL,
        max_usd_per_call: float = 0.02,
        session_budget_usd: float = 0.20,
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.signer = signer
        self.url = url
        self.max_atomic = usd_to_atomic(max_usd_per_call)
        self.budget_atomic = usd_to_atomic(session_budget_usd)
        self.spent_atomic = 0
        self.timeout = timeout
        self.transport = transport
        self.last_payment_response: Any = None

    @property
    def live(self) -> bool:
        return self.signer is not None

    async def scan(self, q: str | None, limit: int, mode: str) -> dict[str, Any]:
        """Return the raw response dict; ``paid_atomic`` is added in live mode."""
        if not self.live:
            return sample_scan(q, limit, mode)
        params: dict[str, Any] = {"limit": limit, "mode": mode}
        if q:
            params["q"] = q
        async with httpx.AsyncClient(
            transport=self.transport, timeout=self.timeout
        ) as client:
            return await self._paid_get(client, params)

    async def _paid_get(
        self, client: httpx.AsyncClient, params: dict[str, Any]
    ) -> dict[str, Any]:
        assert self.signer is not None
        response = await client.get(self.url, params=params)
        paid = 0
        if response.status_code == 402:
            required = decode_b64_json(response.headers.get("PAYMENT-REQUIRED"))
            if required is None:
                try:
                    required = response.json()
                except ValueError:
                    required = None
            if not isinstance(required, dict):
                raise PaymentRefused("402 response without payment requirements")
            requirement = select_requirement(required.get("accepts"), self.max_atomic)
            amount = int(_amount(requirement))
            if self.spent_atomic + amount > self.budget_atomic:
                raise PaymentRefused(
                    f"session budget exhausted ({self.spent_atomic} + {amount} > "
                    f"{self.budget_atomic} atomic USDC)"
                )
            authorization = build_authorization(self.signer.address, requirement)
            signature = self.signer.sign_typed_data(
                build_typed_data(requirement, authorization)
            )
            payload = build_payment_payload(
                requirement,
                required.get("resource") or {"url": self.url},
                authorization,
                signature,
            )
            header = encode_payment_header(payload)
            response = await client.get(
                self.url,
                params=params,
                headers={"PAYMENT-SIGNATURE": header, "X-PAYMENT": header},
            )
            if response.status_code == 402:
                raise PaymentFailed(f"payment not accepted: {response.text[:200]}")
            # Count the spend once the payment was accepted (or not rejected).
            self.spent_atomic += amount
            paid = amount
            self.last_payment_response = decode_b64_json(
                response.headers.get("PAYMENT-RESPONSE")
            )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            data = {}
        data["paid_atomic"] = paid
        return data


def sample_scan(q: str | None, limit: int, mode: str) -> dict[str, Any]:
    """Filter the fictional sample the way the live endpoint filters real data."""
    data = copy.deepcopy(SAMPLE_RESPONSE)
    rows = [row for row in data.get("opportunities", []) if isinstance(row, dict)]
    if mode == "opportunities":
        rows = [row for row in rows if row.get("executable") is True]
    words = (q or "").lower().split()
    if words:
        rows = [r for r in rows if all(w in json.dumps(r).lower() for w in words)]
    data["opportunities"] = rows[:limit]
    data["q"] = q or ""
    data["mode"] = mode
    return data


def _net(row: dict[str, Any], key: str) -> float | None:
    best = row.get("best_direction")
    if not isinstance(best, dict):
        return None
    try:
        return float(best[key])
    except (KeyError, TypeError, ValueError):
        return None


def shape_result(
    data: dict[str, Any],
    request: KalshiPredictItArbRequest,
    *,
    live: bool,
    max_atomic: int,
) -> dict[str, Any]:
    """Stable, tool-friendly output (tolerant of missing/unknown fields)."""
    rows = [r for r in data.get("opportunities") or [] if isinstance(r, dict)]
    executable = [r for r in rows if r.get("executable") is True]
    yields = [y for y in (_net(r, "net_yield_c") for r in rows) if y is not None]
    tickers = [
        r["kalshi"]["ticker"]
        for r in rows
        if isinstance(r.get("kalshi"), dict) and r["kalshi"].get("ticker")
    ]
    paid = int(data.get("paid_atomic") or 0)
    return {
        "source": "kalshi-predictit-arb",
        "mode": "live" if live else "demo",
        "sample_data": not live,
        "notice": None if live else SAMPLE_NOTICE,
        "query": {"q": request.q or "", "limit": request.limit, "mode": request.mode},
        "cost": {
            "paid_usd": paid / 10**USDC_DECIMALS,
            "price_usd_per_call": 0.02,
            "max_usd_per_call": max_atomic / 10**USDC_DECIMALS,
            "network": "Base (USDC, x402 exact)" if live else "none (offline demo)",
        },
        "summary": {
            "returned": len(rows),
            "executable": len(executable),
            "best_net_yield_c": max(yields) if yields else None,
            "kalshi_tickers": tickers,
        },
        "opportunities": rows,
        "stats": data.get("stats"),
        "fetched_at": data.get("fetched_at"),
        "caveat": CAVEAT,
        "docs": DOCS_URL,
    }


DESCRIPTION = (
    "Optional third-party feed (kalshi-predictit-arb, operated by Team Takatini): Kalshi "
    "markets matched to PredictIt contracts with both arbitrage directions priced after "
    "each venue's fees and the worst-case net across outcomes. Inputs: q (keyword), "
    "limit (1-25), mode (opportunities|all). COST: offline demo with fictional sample "
    "data by default (free, no network); live only when X402_WALLET_KEY is set, then "
    "$0.02 USDC per call on Base via x402, capped per call and per session. Read-only; "
    "places no orders. Verify the Kalshi leg with get_market_orderbook/get_market_rules."
)


def make_handler(
    client: KalshiPredictItArbClient,
) -> Callable[[dict], Any]:
    async def handle_kalshi_predictit_arb(request: dict) -> dict[str, Any]:
        req = KalshiPredictItArbRequest(**request)
        data = await client.scan(req.q, req.limit, req.mode)
        return shape_result(data, req, live=client.live, max_atomic=client.max_atomic)

    return handle_kalshi_predictit_arb


def build_client(settings: ArbSettings) -> KalshiPredictItArbClient:
    secret = settings.X402_WALLET_KEY
    key = secret.get_secret_value().strip() if secret else ""
    signer = EthAccountSigner(key) if key else None  # empty/unset -> offline demo
    return KalshiPredictItArbClient(
        signer,
        url=settings.KALSHI_PREDICTIT_ARB_URL,
        max_usd_per_call=settings.KALSHI_PREDICTIT_ARB_MAX_USD_PER_CALL,
        session_budget_usd=settings.KALSHI_PREDICTIT_ARB_SESSION_BUDGET_USD,
        timeout=settings.KALSHI_PREDICTIT_ARB_TIMEOUT_SECONDS,
    )


def register(registry: Any, client: KalshiPredictItArbClient) -> None:
    """Register the tool on a ``ToolRegistry``-like class."""
    registry.register_tool(
        name=TOOL_NAME,
        description=DESCRIPTION,
        input_schema=KalshiPredictItArbRequest,
        read_only=True,
        destructive=False,
    )(make_handler(client))


def register_if_enabled(registry: Any, settings: ArbSettings | None = None) -> bool:
    """Register the tool only when ``KALSHI_PREDICTIT_ARB_ENABLED`` is true."""
    settings = settings or ArbSettings()
    if not settings.KALSHI_PREDICTIT_ARB_ENABLED:
        return False
    register(registry, build_client(settings))
    return True
