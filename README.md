# MCP Server Kalshi
This is an MCP server for the Kalshi REST API

## Configuration

### Claud Desktop
<details>
<summary>Setting up with UVX</summary>
```
"mcpServers": {
  "kalshi": {
    "command": "uvx",
    "args": ["mcp-server-kalshi"],
    "env": {
        "KALSHI_PRIVATE_KEY_PATH": "PATH TO YOUR RSA KEY FILE",
        "KALSHI_API_KEY": "<YOUR KALSHI API KEY>",
        "BASE_URL": "https://api.elections.kalshi.com""
    }
  }
}
```
</details>

<details>
<summary>Setting up with Docker</summary>
1. Build the container from root directory `docker build -t mcp-server-kalshi .`

2. Configure client to run the container (ensure the bind command gives the container access to your rsa key files)
```
"mcpServers": {
  "kalshi": {
    "command": "docker",
    "args": ["run", "--rm", "-i", "--mount", "type=bind,src=/Users/username,dst=/Users/username", "-e", "KALSHI_PRIVATE_KEY_PATH", "-e", "KALSHI_API_KEY","-e", "BASE_URL", "mcp-server-kalshi"],
    "env": {
        "KALSHI_PRIVATE_KEY_PATH": "PATH TO YOUR RSA KEY FILE",
        "KALSHI_API_KEY": "<YOUR KALSHI API KEY>",
        "BASE_URL": "https://api.elections.kalshi.com""
    }
  }
}
```
</details>


## Local Development
1. Create a `.env` file in the root directory with the following variables
* `BASE_URL` The kalshi API URL
* `KALSHI_API_KEY` The API key for the corresponding environment
* `KALSHI_PRIVATE_KEY_PATH` A filepath to a file containing your Kalshi RSA private key

2. Install deps via `uv pip install -e .` Dev deps can be installed with `uv pip install -e .[dev]`
3. Run with `uv run start`

### Getting Kalshi API Creds
To get Kalshi API creds, follow the instrictions [here](https://trading-api.readme.io/reference/api-keys)


### Getting a Test Account
You may want to run the server against a kalshi demo account. To get an account, follow the instructions [here](https://trading-api.readme.io/reference/creating-a-demo-account)

Then, set `BASE_URL=https://demo-api.kalshi.co`for this MCP server and update your `KALSHI_API_KEY` and `KALSHI_PRIVATE_KEY_PATH` to point towards credentials generated in the testing environment


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







