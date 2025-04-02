import mcp.server.stdio
import mcp.types as types
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from .kalshi_client import KalshiAPIClient
from .schema import (
    GetPositionsRequest,
    GetOrdersRequest,
    GetFillsRequest,
    GetBalanceRequest,
    GetSettlementsRequest,
    CreateOrderRequest,
)
from .config import settings
from functools import wraps
from typing import Type, Callable, Any


# Create a server instance
server = Server("kalshi-server")
kalshi_client = KalshiAPIClient(
    base_url=settings.BASE_URL,
    private_key_path=settings.KALSHI_PRIVATE_KEY_PATH,
    api_key=settings.KALSHI_API_KEY.get_secret_value(),
)


class ToolRegistry:
    _tools: dict[str, tuple[types.Tool, Callable]] = {}

    @classmethod
    def register_tool(cls, name: str, description: str, input_schema: Type[Any]):
        def decorator(handler: Callable):
            @wraps(handler)
            async def wrapped_handler(request: dict) -> list[types.TextContent]:
                try:
                    result = await handler(request)
                    return [types.TextContent(type="text", text=str(result))]
                except Exception as e:
                    raise e

            cls._tools[name] = (
                types.Tool(
                    name=name,
                    description=description,
                    inputSchema=input_schema.model_json_schema(),
                ),
                wrapped_handler,
            )
            return wrapped_handler

        return decorator

    @classmethod
    def get_tools(cls) -> list[types.Tool]:
        return [tool for tool, _ in cls._tools.values()]

    @classmethod
    def get_handler(cls, name: str) -> Callable:
        if name not in cls._tools:
            raise ValueError(f"Unknown tool: {name}")
        return cls._tools[name][1]


@ToolRegistry.register_tool(
    name="get_positions",
    description="Get a list of all of your positions",
    input_schema=GetPositionsRequest,
)
async def handle_get_positions(request: dict):
    return await kalshi_client.get_positions(request=GetPositionsRequest(**request))


@ToolRegistry.register_tool(
    name="get_balance",
    description="Get the portfolio balance of the logged-in member in cents",
    input_schema=GetBalanceRequest,
)
async def handle_get_balance(request: dict):
    return await kalshi_client.get_balance()


@ToolRegistry.register_tool(
    name="get_orders",
    description="Get a list of all of your orders",
    input_schema=GetOrdersRequest,
)
async def handle_get_orders(request: dict):
    return await kalshi_client.get_orders(request=GetOrdersRequest(**request))


@ToolRegistry.register_tool(
    name="get_fills",
    description="Get a list of all of your order fills",
    input_schema=GetFillsRequest,
)
async def handle_get_fills(request: dict):
    return await kalshi_client.get_fills(request=GetFillsRequest(**request))


@ToolRegistry.register_tool(
    name="create_order",
    description="Create an order to buy or sell contracts in a market",
    input_schema=CreateOrderRequest,
)
async def handle_create_order(request: dict):
    return await kalshi_client.create_order(request=CreateOrderRequest(**request))


@ToolRegistry.register_tool(
    name="get_settlements",
    description="Get a list of all of your settlements",
    input_schema=GetSettlementsRequest,
)
async def handle_get_settlements(request: dict):
    return await kalshi_client.get_settlements(request=GetSettlementsRequest(**request))


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return ToolRegistry.get_tools()


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    handler = ToolRegistry.get_handler(name)
    return await handler(arguments)


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
