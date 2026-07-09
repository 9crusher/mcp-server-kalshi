# MCP Server Kalshi

<!-- mcp-name: io.github.9crusher/mcp-server-kalshi -->

An MCP server that gives Claude Code and other agent harnesses a first-class interface to
[Kalshi](https://kalshi.com). It is built for end-to-end trading: browse markets, research them, read the *exact* settlement
rules (including pulling the contract-terms PDFs), and execute trades — all through MCP tools.

## Highlights

- **Discovery** — `list_markets`, `get_market`, `list_events`, `get_event`, `list_series`,
  `get_series`. (Kalshi has no free-text search; `list_markets` filters are the search.)
- **Research** — `get_market_orderbook`, `get_market_candlesticks`, `get_market_trades`.
- **Deep rules** — `get_market_rules` consolidates a market's `rules_primary`/`rules_secondary`,
  early-close conditions, settlement sources, and series prohibitions; `fetch_rules_pdf`
  downloads and extracts the text of the actual legal contract PDF so the agent can read it.
- **Exchange** — `get_exchange_status`, `get_exchange_schedule` (is the market open, and its hours).
- **Portfolio** — `get_balance`, `get_positions`, `get_fills`, `get_settlements`.
- **Trading** — `create_order`, `cancel_order`, `amend_order`, `decrease_order`,
  plus `list_orders` / `get_order`.

### Safety by default

- The server targets Kalshi's **demo (sandbox)** environment unless you explicitly set
  `KALSHI_ENV=prod`.
- Order-placing tools (`create_order`, `amend_order`) require `confirm=true`. Without it they
  return a **preview** — a human-readable summary and the exact payload — and place nothing.
- Credentials are **optional**: all market/rules tools work unauthenticated. Only portfolio
  and order tools need an API key + RSA private key.

### Intuitive order model

Kalshi's V2 order API quotes everything from the YES leg (`bid`/`ask` in fixed-point dollars).
This server exposes the natural model instead — `action` (buy/sell) + `side` (yes/no) + a whole
**cents** limit price — and translates it (including the buy-NO ⇄ sell-YES price inversion).

## Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `KALSHI_ENV` | `demo` | `demo` (sandbox) or `prod` (real money). Derives the base URL. |
| `KALSHI_API_KEY` | _(none)_ | Kalshi API key ID. Required only for authenticated tools. |
| `KALSHI_PRIVATE_KEY_PATH` | _(none)_ | Path to your RSA private key `.pem`. Required for authenticated tools. |
| `BASE_URL` | _(derived)_ | Optional explicit REST base override (must include `/trade-api/v2`). |

See `.env-example`. Get API credentials at
[docs.kalshi.com/getting_started/api_keys](https://docs.kalshi.com/getting_started/api_keys)
and a demo account via the
[demo environment guide](https://docs.kalshi.com/getting_started/test_in_demo).

### Claude Desktop (uvx)

```json
"mcpServers": {
  "kalshi": {
    "command": "uvx",
    "args": ["mcp-server-kalshi"],
    "env": {
      "KALSHI_ENV": "demo",
      "KALSHI_API_KEY": "<YOUR KALSHI API KEY>",
      "KALSHI_PRIVATE_KEY_PATH": "PATH TO YOUR RSA KEY FILE"
    }
  }
}
```

### Claude Desktop (Docker)

```json
"mcpServers": {
  "kalshi": {
    "command": "docker",
    "args": ["run", "--rm", "-i",
      "--mount", "type=bind,src=/Users/username,dst=/Users/username",
      "-e", "KALSHI_ENV", "-e", "KALSHI_API_KEY", "-e", "KALSHI_PRIVATE_KEY_PATH",
      "mcp-server-kalshi"],
    "env": {
      "KALSHI_ENV": "demo",
      "KALSHI_API_KEY": "<YOUR KALSHI API KEY>",
      "KALSHI_PRIVATE_KEY_PATH": "PATH TO YOUR RSA KEY FILE"
    }
  }
}
```

## Local Development

1. Create a `.env` file (see `.env-example`).
2. Install deps: `uv sync` (add `--extra dev` for dev tools). Requires Python 3.10+.
3. Run: `uv run start`.
4. Test: `uv run pytest`.

### MCP Inspector

```bash
npx @modelcontextprotocol/inspector uv --directory /path/to/mcp-server-kalshi run start
```

## Testing & code quality

```bash
uv sync --extra dev              # install dev tools (ruff, mypy, pytest, ...)
uv run pytest                    # run the test suite
uv run pytest --cov              # tests with a coverage report
uv run ruff check src tests      # lint
uv run black src tests           # format (add --check to verify only)
uv run mypy                      # type check
uv run pre-commit install        # (once) run ruff + black on every commit
```

Tests are pure/offline — they exercise the order translation and confirm-gate, the HTTP client
(via an injected `httpx.MockTransport`), the MCP tool registry, config, and PDF extraction, all
without touching the live Kalshi API. CI (`.github/workflows/ci.yml`) runs ruff + black + mypy +
pytest across Python 3.10–3.13 on every push/PR, and releases are gated on that same suite.

## Authentication

Requests are signed with RSA-PSS (MGF1-SHA256, max salt). Each authenticated request sends
`KALSHI-ACCESS-KEY`, `KALSHI-ACCESS-TIMESTAMP`, and `KALSHI-ACCESS-SIGNATURE`, where the signed
message is `timestamp_ms + METHOD + path` (path includes `/trade-api/v2`, excludes the query
string).
