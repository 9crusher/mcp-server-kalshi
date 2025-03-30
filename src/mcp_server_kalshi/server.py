import mcp.server.stdio
import mcp.types as types
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from .kalshi_client import KalshiAPIClient
from .config import settings


# Create a server instance
server = Server("kalshi-server")
kalshi_client = KalshiAPIClient(
    base_url=settings.BASE_URL,
    private_key_path=settings.KALSHI_PRIVATE_KEY_PATH,
    api_key=settings.KALSHI_API_KEY.get_secret_value(),
)


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return [
    types.Tool(
        name="get_markets",
        description="Get a list of markets",
        inputSchema={
            "type": "object",
            "properties": {},
            "additionalProperties": False
        }
    ),
    types.Tool(
        name="get_positions",
        description="Get a list of all of your positions",
        inputSchema={
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Number of results per page (1-1000)",
                    "default": 100
                },
                "cursor": {
                    "type": "string",
                    "description": "Pagination cursor for the next page of results"
                },
                "status": {
                    "type": "string",
                    "description": "Filter positions by status",
                    "enum": ["open", "settled", "expired"]
                },
                "market_ticker": {
                    "type": "string",
                    "description": "Filter positions by market ticker"
                },
                "event_ticker": {
                    "type": "string",
                    "description": "Filter positions by event ticker"
                }
            },
            "required": [],
            "additionalProperties": False
        },
    )
]


@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict
) -> list[types.TextContent]:
    if name == "get_markets":
        try:
            markets_data = await kalshi_client.get_markets()
            return [types.TextContent(type="text", text=str(markets_data))]
        except Exception as e:
            return [types.TextContent(type="text", text=f"Error fetching market data: {str(e)}")]
    elif name == "get_positions":
        try:
            positions_data = await kalshi_client.get_positions(
                limit=arguments.get("limit", 100),
                cursor=arguments.get("cursor"),
                status=arguments.get("status"),
                market_ticker=arguments.get("market_ticker"),
                event_ticker=arguments.get("event_ticker"),
            )
            return [types.TextContent(type="text", text=str(positions_data))]
        except Exception as e:
            return [types.TextContent(type="text", text=f"Error: {str(e)}")]


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

def main():
    import asyncio
    asyncio.run(run())
