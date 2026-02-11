## Overview

Python client library for obtaining Google API access tokens. Supports two token types for different use cases, both obtained via `CredentialsManager`.

## Public API

### CredentialsManager

The single entry point. Configured via constructor params, environment variables, or `~/.config/extrasuite/gateway.json` (created by skill installer).

```python
from extrasuite.client import CredentialsManager

# ExtraSuite protocol (default if gateway.json exists)
manager = CredentialsManager()

# Explicit server URLs
manager = CredentialsManager(
    auth_url="https://server.example.com/api/token/auth",
    exchange_url="https://server.example.com/api/token/exchange",
)

# Service account file (no server needed)
manager = CredentialsManager(service_account_path="/path/to/sa.json")

# Custom gateway.json path (raises FileNotFoundError if missing)
manager = CredentialsManager(gateway_config_path="/path/to/gateway.json")

# Explicit delegation URLs (for domain-wide delegation)
manager = CredentialsManager(
    auth_url="https://server.example.com/api/token/auth",
    exchange_url="https://server.example.com/api/token/exchange",
    delegation_auth_url="https://server.example.com/api/delegation/auth",
    delegation_exchange_url="https://server.example.com/api/delegation/exchange",
)
```

### get_token() -> Token

Returns a **service account token** for accessing Google Workspace APIs (Sheets, Slides, Docs). The token acts as the user's dedicated service account - it can only access files explicitly shared with that service account.

```python
token = manager.get_token()
# token.access_token - Bearer token for Google APIs
# token.service_account_email - e.g. "user-abc@project.iam.gserviceaccount.com"
# token.expires_at - Unix timestamp
# token.is_valid() - True if not expired (with 60s buffer)
```

**How it works:** Opens a browser to the ExtraSuite server, user authenticates with Google, server impersonates the user's service account and returns a short-lived token. Tokens are cached in `~/.config/extrasuite/token.json`.

### get_oauth_token(scopes, reason) -> OAuthToken

Returns a **user-level OAuth token** via domain-wide delegation, for APIs that require acting as the user (Gmail, Calendar, etc.). Requires the ExtraSuite server to have delegation enabled.

```python
token = manager.get_oauth_token(
    scopes=["gmail.send", "calendar"],  # short names or full URLs
    reason="Send email on behalf of user",
)
# token.access_token - Bearer token scoped to the user
# token.scopes - List of granted scope URLs
# token.expires_at - Unix timestamp
# token.is_valid() - True if not expired (with 60s buffer)
```

**How it works:** Same browser-based OAuth flow, but the server uses domain-wide delegation to generate a token that acts as the authenticated user (not as a service account). Cached separately in `~/.config/extrasuite/oauth_token.json` with scope-aware invalidation.

## CLI

The unified CLI is stateless - auth parameters are passed on each command:

```bash
# Using gateway.json for authentication
extrasuite sheet pull --gateway /path/to/gateway.json <url>

# Using service account
extrasuite sheet pull --service-account /path/to/sa.json <url>

# Default: uses env vars or ~/.config/extrasuite/gateway.json
extrasuite sheet pull <url>

# Offline commands (no auth needed)
extrasuite sheet diff <folder>
extrasuite script lint <folder>
```

## When to use which

| Use case | Method | Token type |
|----------|--------|------------|
| Read/write Sheets, Slides, Docs | `get_token()` | Service account |
| Send email, manage calendar | `get_oauth_token()` | User delegation |
| Any file shared with SA email | `get_token()` | Service account |
| User-scoped API (acts as user) | `get_oauth_token()` | User delegation |

## Configuration precedence

1. Constructor parameters (`auth_url`, `exchange_url`, `delegation_auth_url`, `delegation_exchange_url`, `gateway_config_path`, `service_account_path`)
2. Environment variables (`EXTRASUITE_SERVER_URL`, `EXTRASUITE_AUTH_URL`, `EXTRASUITE_EXCHANGE_URL`, `EXTRASUITE_DELEGATION_AUTH_URL`, `EXTRASUITE_DELEGATION_EXCHANGE_URL`)
3. `~/.config/extrasuite/gateway.json`
4. `SERVICE_ACCOUNT_PATH` env var (fallback, no server needed)

## gateway.json format

```json
{"EXTRASUITE_SERVER_URL": "https://your-server.example.com"}
```

From `EXTRASUITE_SERVER_URL`, the following are derived:
- `{server}/api/token/auth`
- `{server}/api/token/exchange`
- `{server}/api/delegation/auth`
- `{server}/api/delegation/exchange`

Explicit URL keys (`EXTRASUITE_AUTH_URL`, `EXTRASUITE_EXCHANGE_URL`, `EXTRASUITE_DELEGATION_AUTH_URL`, `EXTRASUITE_DELEGATION_EXCHANGE_URL`) override server-derived values.

## Development

```bash
cd client
uv sync
uv run pytest tests/ -v
uv run ruff check . && uv run ruff format .
```
