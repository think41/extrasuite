# google-workspace-gateway

Python client library for [Google Workspace Gateway](https://github.com/anthropics/google-workspace-gateway) - secure OAuth token exchange for CLI tools.

## Installation

```bash
pip install google-workspace-gateway
```

## Quick Start

```python
from google_workspace_gateway import GoogleWorkspaceGateway

# Create gateway client (server_url is required)
gateway = GoogleWorkspaceGateway(
    server_url="https://your-gwg-server.example.com"
)

# Get a token - opens browser for authentication if needed
token = gateway.get_token()

# Use the token with Google APIs
import gspread
from google.oauth2.credentials import Credentials

creds = Credentials(token)
gc = gspread.authorize(creds)
sheet = gc.open("My Spreadsheet").sheet1
```

## Configuration

The `GoogleWorkspaceGateway` class accepts the following parameters:

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `server_url` | Yes | - | URL of the Google Workspace Gateway server |
| `token_cache_path` | No | `~/.config/google-workspace-gateway/token.json` | Path to cache tokens |
| `callback_timeout` | No | `120` | OAuth callback timeout in seconds |

## How It Works

1. When you call `get_token()`, the client first checks for a cached token
2. If no valid cached token exists, it starts a local HTTP server
3. Opens your browser to the Google Workspace Gateway server for OAuth
4. After authentication, the server redirects back to your local server with a token
5. The token is cached for subsequent calls

Tokens are short-lived (1 hour) and automatically refreshed when expired.

## Examples

See the [examples/](examples/) directory for complete examples:

- `basic_usage.py` - Simple token retrieval
- `gsheet_example.py` - Using with Google Sheets via gspread

## Requirements

- Python 3.10+
- No external dependencies (stdlib only)

For Google Sheets integration, install:
```bash
pip install gspread google-auth
```

## License

MIT
