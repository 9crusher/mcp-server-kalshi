import mcp.server.stdio
import mcp.types as types
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from kalshi_client import KalshiAPIClient

# Create a server instance
server = Server("kalshi-server")
client = KalshiAPIClient()


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="get_market",
            description="Get information about a specific Kalshi market",
            inputSchema={
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "description": "The ticker symbol of the market"}
                },
                "required": ["ticker"]
            }
        )
    ]


@server.call_tool()
async def handle_call_tool(
    name: str,
    arguments: dict
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    if name == "get_market":
        ticker = arguments["ticker"]

        try:
            # Get markets data filtered by ticker
            markets_data = await client.get_markets(event_ticker=ticker)
            return [types.TextContent(type="text", text=str(markets_data))]
        except Exception as e:
            return [types.TextContent(type="text", text=f"Error fetching market data: {str(e)}")] 
    raise ValueError(f"Tool not found: {name}")


async def run():
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="kalshi-server",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(run())