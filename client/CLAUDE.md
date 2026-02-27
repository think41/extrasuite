## Overview

Python client library for obtaining Google API access tokens. Supports two token types for different use cases, both obtained via `CredentialsManager`.

## Security Constraint: No Auth in Agent Code

**Agents invoking the CLI must never:**
- Read token files (`~/.config/extrasuite/token.json`, etc.)
- Call Google APIs directly (Sheets, Docs, Drive, Gmail, Calendar, etc.)
- Construct OAuth or service account credentials
- Pass raw access tokens between commands

The CLI is the authentication boundary. All auth is handled transparently by
`extrasuite <module> pull/push/create/...`. Agents just run CLI commands.

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

### get_token(*, reason, pseudo_scope="drive.file") -> Token

Returns a **service account token** for accessing Google Workspace APIs (Sheets, Slides, Docs). The token acts as the user's dedicated service account - it can only access files explicitly shared with that service account.

**`reason` is required** (keyword-only argument). Used for server-side audit logging.

```python
token = manager.get_token(reason="Pulling spreadsheet", pseudo_scope="sheet.pull")
# token.access_token - Bearer token for Google APIs
# token.service_account_email - e.g. "user-abc@project.iam.gserviceaccount.com"
# token.expires_at - Unix timestamp
# token.is_valid() - True if not expired (with 60s buffer)
```

**How it works (v2):** Loads cached session token from `~/.config/extrasuite/session.json`. If valid, POSTs to `/api/auth/token` for a headless exchange. If no session, initiates Phase 1 browser flow to get a 30-day session first. SA tokens cached for 60 min in `~/.config/extrasuite/token.json`.

**Legacy (v1):** If no server_base_url configured, falls back to opening browser directly.

### get_oauth_token(scopes, reason="", file_hint="") -> OAuthToken

Returns a **user-level OAuth token** via domain-wide delegation, for APIs that require acting as the user (Gmail, Calendar, etc.). Requires the ExtraSuite server to have delegation enabled.

```python
token = manager.get_oauth_token(
    scopes=["gmail.send", "calendar"],  # short names or full URLs
    reason="Send email on behalf of user",
    file_hint="",  # optional Drive URL or ID
)
# token.access_token - Bearer token scoped to the user
# token.scopes - List of granted scope URLs
# token.expires_at - Unix timestamp (capped at DWD_TOKEN_CACHE_SECONDS=600)
# token.is_valid() - True if not expired (with 60s buffer)
```

**How it works (v2):** Same session-token flow, but dispatches to DWD. Token cache capped at 10 minutes. Cached in `~/.config/extrasuite/oauth_token.json`.

### Dataclasses

| Class | Description | Cache file |
|---|---|---|
| `Token` | SA token (1h lifetime) | `token.json` |
| `OAuthToken` | DWD token (10min cache) | `oauth_token.json` |
| `SessionToken` | 30-day session token | `session.json` |

### Token Cache Lifetimes

| Token type | Lifetime | Cache TTL |
|---|---|---|
| SA (service account) | 1 hour (server) | 60 min |
| DWD (delegation) | 1 hour (server) | 10 min (client cap) |
| Session | 30 days | 30 days |

### headless parameter

```python
manager = CredentialsManager(headless=True)
# Or: EXTRASUITE_HEADLESS=1
```

In headless mode, Phase 1 prints the URL to stderr and reads the auth code from stdin instead of opening a browser.

## CLI

### Auth commands (v2)

```bash
extrasuite auth login              # Browser flow → 30-day session token
extrasuite auth login --headless   # Print URL, prompt for code on stdin
extrasuite auth logout             # Revoke session server-side + clear cache
extrasuite auth status             # Show session + token validity
```

### All other commands (use cached session silently)

```bash
# Using gateway.json for authentication
extrasuite sheet pull --gateway /path/to/gateway.json <url>

# Using service account (bypasses session flow entirely)
extrasuite sheet pull --service-account /path/to/sa.json <url>

# Default: uses env vars or ~/.config/extrasuite/gateway.json
extrasuite sheet pull <url>

# Offline commands (no auth needed)
extrasuite sheet diff <folder>
extrasuite script lint <folder>
```

Note: `SERVICE_ACCOUNT_PATH` mode bypasses the session flow entirely and calls Google APIs directly.

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

## Help Documentation

CLI `--help` text is loaded from bundled markdown files in
`src/extrasuite/client/help/`. The hierarchy mirrors the CLI:

  help/README.md                 extrasuite --help
  help/<module>/README.md        extrasuite <module> --help
  help/<module>/<command>.md     extrasuite <module> <command> --help

Reference files (format-reference.md, sml-reference.md, etc.) are detailed
docs linked from the command help but not directly shown by --help.

To update help text, edit the markdown file. Changes take effect immediately
(no rebuild needed for editable installs).

## Development

```bash
cd client
uv sync
uv run pytest tests/ -v
uv run ruff check . && uv run ruff format .
```
