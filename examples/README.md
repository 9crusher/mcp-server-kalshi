# Examples

## `kalshi_predictit_arb_offline.py` (optional third-party tool)

An optional, read-only MCP tool, `kalshi_predictit_arb`, that reads a Kalshi <-> PredictIt
cross-venue arbitrage scanner. It is **off by default**; nothing changes for existing users
unless they set `KALSHI_PREDICTIT_ARB_ENABLED=true`.

Disclosure: kalshi-predictit-arb is built and operated by Team Takatini. It is a
third-party, paid data feed, not part of Kalshi.
Docs: https://mastertyrone.github.io/kalshi-predictit-arb/ ·
Client: https://github.com/mastertyrone/kalshi-predictit-arb

### What it returns

For each matched pair: the Kalshi ticker and quotes, the PredictIt market/contract and
quotes, the better arbitrage direction with fee breakdown (Kalshi taker
`ceil(7*P*(1-P))`c per leg; PredictIt 10% of winning-leg profit plus 5% withdrawal drag),
the worst-case net across settlement outcomes (`net_yield_c`, `net_yield_pct`),
`executable` (true only at >= 1c net), days to settlement, annualized ROC and Kalshi depth.
The tool wraps that in a stable envelope: `mode` (`demo`/`live`), `sample_data`, `query`,
`cost`, `summary` (count, executable count, best net, Kalshi tickers), `opportunities`,
`stats`, `fetched_at`, `caveat`.

Gaps are indicative until checked against live depth, current fees and resolution
equivalence. The Kalshi tickers can be passed straight to `get_market_orderbook` and
`get_market_rules`; PredictIt publishes no public depth.

Inputs: `q` (keyword, optional), `limit` (1-25, default 10), `mode`
(`opportunities` = executable only, default; `all` = every evaluated pair).

### Cost

| Setup | Network | Cost |
|-------|---------|------|
| `KALSHI_PREDICTIT_ARB_ENABLED=true`, no `X402_WALLET_KEY` | none | free; fictional SAMPLE data (`sample_data: true`) |
| plus `X402_WALLET_KEY` and `pip install eth-account` | live feed | **$0.02 USDC per call** on Base, paid via x402 |

Live-mode safeguards: payment requirements are refused unless they are Base
(`eip155:8453`) / scheme `exact` / Base USDC (`0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`)
/ `0 < amount <= KALSHI_PREDICTIT_ARB_MAX_USD_PER_CALL` (default `0.02`) with a valid
`payTo`; an empty `accepts` list is refused; spend per server process is capped by
`KALSHI_PREDICTIT_ARB_SESSION_BUDGET_USD` (default `0.20`). The EIP-3009 authorization is
signed locally (the key never leaves the machine) and sent once, as unpadded base64url, in
`PAYMENT-SIGNATURE` and `X-PAYMENT`; a second 402 is returned as an error. Use a dedicated
low-balance wallet.

| Variable | Default | Purpose |
|----------|---------|---------|
| `KALSHI_PREDICTIT_ARB_ENABLED` | `false` | Register the tool. |
| `X402_WALLET_KEY` | _(none)_ | Enables live (paid) mode. Unset/empty = offline demo. |
| `KALSHI_PREDICTIT_ARB_MAX_USD_PER_CALL` | `0.02` | Per-call payment cap. |
| `KALSHI_PREDICTIT_ARB_SESSION_BUDGET_USD` | `0.20` | Total spend cap per server process. |
| `KALSHI_PREDICTIT_ARB_TIMEOUT_SECONDS` | `30` | HTTP timeout (the feed can cold-start slowly). |

### Run the offline example

```bash
uv run python examples/kalshi_predictit_arb_offline.py
uv run python examples/kalshi_predictit_arb_offline.py --q governor --mode all
```

It starts the server over stdio with the tool enabled and `X402_WALLET_KEY` forced empty,
so it never makes a network call or a payment.
