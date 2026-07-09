# AGENTS.md

Guidance for AI agents (Claude Code, Cursor, etc.) working in this repo. Human-oriented
usage/config lives in `README.md`; this file is the map + the conventions + the gotchas.

## What this is

An MCP server that exposes the [Kalshi](https://kalshi.com) prediction-market Trade API v2
as MCP tools, built for deep end-to-end trading (discover → research → read settlement rules →
trade). Python 3.10+, `uv`, `mcp` low-level `Server`, `httpx`, `pydantic`.

## Build / test / verify

```bash
uv sync --extra dev          # install (Python 3.10+)
uv run start                 # run the server over stdio
uv run pytest                # run the test suite  <- the feedback loop
uv run pytest --cov          # tests with a coverage report
uv run ruff check src tests  # lint (import order, pyflakes, pyupgrade, bugbear)
uv run black src tests       # format
uv run mypy                  # type check
uv run pre-commit install    # (once) run ruff+black on every commit
```

Run `uv run pytest` before declaring any change done. Tests are pure/offline — they exercise
the order translation, the confirm-gate, the HTTP client (via an injected `httpx.MockTransport`),
the tool registry, config, and PDF extraction, all by monkeypatching or mocking. Make no network
calls. Keep it that way: never hit the live Kalshi API from a test. CI (`.github/workflows/ci.yml`)
runs ruff + black + mypy + pytest across Python 3.10–3.13 on every push/PR, and releases are
gated on that same suite.

## Architecture (the 60-second map)

Data flows request → schema → client → server → MCP:

```
config.py                     Settings (env/.env). Safety default: KALSHI_ENV=demo.
kalshi_client/
  base.py                     BaseAPIClient (async httpx) + KalshiAuth (RSA-PSS signing)
                              + KalshiAPIError. Auth is OPTIONAL (public tools work keyless).
  client.py                   KalshiAPIClient: one async method per REST endpoint, PLUS the
                              build_*_order_payload() translators (see "cents model" below).
  schemas.py                  Pydantic request models. All extend MCPSchemaBaseModel, whose
                              to_mcp_input_schema() emits clean MCP inputSchemas.
  pdf.py                      fetch_pdf_text() — download + extract a contract-terms PDF.
server.py                     ToolRegistry (@register_tool decorator) defines every tool;
                              handlers validate the dict against a schema and call the client.
                              KALSHI_BACKGROUND_INFO is the server's MCP `instructions`.
```

Tool registration is a decorator, not FastMCP: `@ToolRegistry.register_tool(name=…,
description=…, input_schema=…, read_only=…, destructive=…)`. `list_tools`/`call_tool` at the
bottom of `server.py` serve whatever the registry collected.

## The one workflow you'll repeat: add a tool for an API endpoint

Do these four edits, in order, then test. (Match the existing entries in each file — they are
the template.)

1. **`kalshi_client/schemas.py`** — add a request model extending `MCPSchemaBaseModel` (or
   `_Paginated` if the endpoint paginates). Every field is a `Field(...)` with a description
   and correct required/optional (`Optional[...] = Field(default=None, ...)`). Use `Literal`
   for enums. Field docs become the tool's parameter docs, so make them comprehensive.
2. **`kalshi_client/client.py`** — add one `async def` on `KalshiAPIClient` calling
   `self.get/post/delete(path, params=/json=)`. Add `self._require_auth()` as the first line
   for any portfolio/order endpoint.
3. **`server.py`** — register a handler with `@ToolRegistry.register_tool(...)`. Validate with
   `Model(**request)` (or the `_params(request, Model)` helper for query-param GETs) and call
   the client. Set `read_only=False, destructive=True` for anything that mutates orders.
4. **`tests/`** — add coverage (see `tests/test_orders.py` for the monkeypatch-the-client
   pattern). No network.

Then: `uv run pytest`.

## Non-obvious rules — get these wrong and it's a real bug

- **Cents ↔ YES-leg model.** Tools expose the intuitive `action` (buy/sell) + `side` (yes/no)
  + whole-**cents** `limit_price`. Kalshi V2 quotes everything from the YES leg as a `bid`/`ask`
  in fixed-point dollars. `build_create_order_payload` / `build_amend_order_payload` do the
  translation, including the inversion **buy-NO @ p ≡ sell-YES @ (100−p)**. Don't reimplement
  this inline — reuse the builders, and if you touch them, update the parametrized tests.
- **`confirm=true` gate.** `create_order` / `amend_order` return a *preview* (human summary +
  exact `kalshi_v2_payload`) and place **nothing** unless `confirm=true`. This guardrail is
  covered by tests (`test_create_order_preview_does_not_place`) — preserve it.
- **Demo by default.** `KALSHI_ENV` defaults to `demo` (sandbox). `prod` is real money. Every
  order response is tagged with `settings.env_label`; keep that visible to the caller.
- **Auth signing.** `KalshiAuth` signs `timestamp_ms + METHOD + path`, where `path` includes
  `/trade-api/v2` but **excludes the query string**. RSA-PSS, MGF1-SHA256, max salt. Don't
  change the signed-message shape without matching `tests/test_auth.py`.
- **Public vs authed.** Market/rules/discovery tools work with no credentials. Portfolio/order
  methods call `self._require_auth()` and error clearly when keys are absent.

## Conventions

- Functional style; the notable class is `KalshiAPIClient` (endpoint methods) — keep new
  endpoints as methods there. `snake_case` files/functions.
- Endpoint methods return the raw parsed JSON (`Any`); shaping/among-resources joins happen in
  the server handler (see `handle_get_market_rules`).
- Don't duplicate the Kalshi domain primer — it lives once in `KALSHI_BACKGROUND_INFO`
  (`server.py`) and is shipped as the server's MCP `instructions`.
