# MCP Server Kalshi


To install deps run `uv pip install -e .`

## Local Development

### UVX
To run in MCP inspector
```
npx @modelcontextprotocol/inspector uv --directory /Users/alexanderruchti/git/mcp-server-kalshi run start
```

To run in claud desktop, update your MCP config to:
```
{
    "mcpServers": {
        "kalshi": {
            "command": "uv",
            "args": [ 
            "--directory",
            "/<path to repo root directory>,
            "run",
            "start"
            ],
            "env": {
                "KALSHI_PRIVATE_KEY_PATH": "PATH TO YOUR RSA KEY FILE",
                "KALSHI_API_KEY": "<YOUR KALSHI API KEY>",
                "BASE_URL": "https://demo-api.kalshi.co"
            }
        }
    }
}
```



