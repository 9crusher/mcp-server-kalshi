"""Offline example: call the optional ``kalshi_predictit_arb`` tool over real MCP stdio.

Spawns this repo's server as a subprocess with the tool enabled and
``X402_WALLET_KEY`` forced empty, lists the tools, and calls
``kalshi_predictit_arb``. Nothing touches the network and nothing is paid: the
tool answers from its built-in fictional SAMPLE data (NOT real market data).

    uv run python examples/kalshi_predictit_arb_offline.py
    uv run python examples/kalshi_predictit_arb_offline.py --q governor --mode all

Live mode (paid, $0.02 USDC per call on Base via x402) is configured on the
server with ``X402_WALLET_KEY``; see examples/README.md. This script never
enables it.

Disclosure: kalshi-predictit-arb is built and operated by Team Takatini.
Docs: https://mastertyrone.github.io/kalshi-predictit-arb/
Client: https://github.com/mastertyrone/kalshi-predictit-arb
"""

import argparse
import asyncio
import json
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main(q: str, limit: int, mode: str) -> None:
    env = dict(os.environ)
    env["KALSHI_PREDICTIT_ARB_ENABLED"] = "true"
    env["X402_WALLET_KEY"] = ""  # overrides any .env value: offline demo only
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "mcp_server_kalshi.server"], env=env
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = {tool.name: tool for tool in (await session.list_tools()).tools}
            tool = tools["kalshi_predictit_arb"]
            print(f"tool: {tool.name}\n  {tool.description}\n")
            arguments = {"q": q, "limit": limit, "mode": mode}
            result = await session.call_tool("kalshi_predictit_arb", arguments)
            text = result.content[0].text
            try:
                out = json.loads(text)
            except ValueError:
                raise SystemExit(text) from None
            print(f"mode={out['mode']} sample_data={out['sample_data']}")
            print(f"notice: {out['notice']}")
            print(f"cost: {out['cost']}")
            print(f"summary: {out['summary']}")
            for row in out["opportunities"]:
                best = row.get("best_direction") or {}
                net = best.get("net_yield_c")
                print(
                    f"- {row.get('event')}\n"
                    f"    {best.get('direction', 'n/a')} "
                    f"net {'n/a' if net is None else f'{net}c'} "
                    f"executable={row.get('executable') is True}"
                )
            print(f"caveat: {out['caveat']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--q", default="")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--mode", choices=["opportunities", "all"], default="all")
    args = parser.parse_args()
    asyncio.run(main(args.q, args.limit, args.mode))
