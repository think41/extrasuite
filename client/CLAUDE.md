## Overview

Python client library for obtaining short-lived Google API credentials. All credentials are obtained via `CredentialsManager.get_credential()` using a typed command object.

## Security Constraint: No Auth in Agent Code

**Agents invoking the CLI must never:**
- Read credential files (`~/.config/extrasuite/credentials/`, etc.)
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

# Explicit server URL
manager = CredentialsManager(
    auth_url="https://server.example.com/api/token/auth",
    exchange_url="https://server.example.com/api/token/exchange",
)

# Service account file (no server needed)
manager = CredentialsManager(service_account_path="/path/to/sa.json")

# Custom gateway.json path (raises FileNotFoundError if missing)
manager = CredentialsManager(gateway_config_path="/path/to/gateway.json")
```

### get_credential(*, command, reason) -> Credential

Returns a short-lived `Credential` for the given command. Both arguments are required (keyword-only).

- `command`: a dict with a `"type"` key matching one of the command types in the server's command registry. All other fields are optional context logged for audit.
- `reason`: human-readable description of why the credential is needed. Logged server-side.

```python
from extrasuite.client import CredentialsManager, Credential

manager = CredentialsManager()

# Service account credential for Sheets/Docs/Slides/Drive
cred = manager.get_credential(
    command={"type": "sheet.pull", "file_url": "https://docs.google.com/...", "file_name": "Budget"},
    reason="User wants to review the Q4 budget",
)
# cred.token       - Bearer token for Google APIs
# cred.kind        - "bearer_sa" or "bearer_dwd"
# cred.scopes      - List[str] of OAuth scopes (empty for SA)
# cred.expires_at  - Unix timestamp
# cred.is_valid()  - True if not expired (60s buffer)
# cred.metadata["service_account_email"] - SA email (for Drive sharing)

# Domain-wide delegation credential for Gmail/Calendar
cred = manager.get_credential(
    command={"type": "gmail.compose", "subject": "Q4 report", "recipients": ["alice@company.com"]},
    reason="User asked agent to draft an email",
)
```

**How it works (v2):** Loads the cached session token from `~/.config/extrasuite/session.json`. If valid, POSTs to `POST /api/auth/token` for a headless credential exchange. If no session exists, initiates the Phase 1 browser flow to get a 30-day session first. Credentials are cached per-command-type under `~/.config/extrasuite/credentials/<cmd_type>.json`.

**Service account mode:** If `service_account_path` is configured, generates a token directly from the SA file — no server interaction needed. Only SA-backed commands are supported in this mode.

### Credential dataclass

| Field | Type | Description |
|---|---|---|
| `token` | `str` | Bearer token for Google API calls |
| `kind` | `str` | `"bearer_sa"` or `"bearer_dwd"` |
| `scopes` | `list[str]` | Granted OAuth scopes (empty for SA tokens) |
| `expires_at` | `float` | Unix timestamp of expiry |
| `metadata` | `dict[str, str]` | Provider extras; always includes `service_account_email` |
| `is_valid()` | → `bool` | `True` if not expired with a 60-second buffer |

### SessionToken dataclass

| Field | Type | Description |
|---|---|---|
| `raw_token` | `str` | The 30-day session token (never send to Google directly) |
| `email` | `str` | Authenticated user email |
| `expires_at` | `float` | Unix timestamp of expiry |

### Credential Cache Lifetimes

| Credential type | Server lifetime | Client cache TTL |
|---|---|---|
| SA (service account) | 1 hour | 60 min |
| DWD (domain-wide delegation) | 1 hour | 10 min |
| Session | 30 days | 30 days |

Credentials are cached per command type at `~/.config/extrasuite/credentials/<cmd_type>.json` (0600).

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
extrasuite auth status             # Show session + credential validity
```

### All other commands (use cached session silently)

```bash
# Using gateway.json for authentication
extrasuite sheets pull --gateway /path/to/gateway.json <url>

# Using service account (bypasses session flow entirely)
extrasuite sheets pull --service-account /path/to/sa.json <url>

# Default: uses env vars or ~/.config/extrasuite/gateway.json
extrasuite sheets pull <url>

# Offline commands (no auth needed)
extrasuite sheets diff <folder>
extrasuite script lint <folder>
```

Note: `SERVICE_ACCOUNT_PATH` mode bypasses the session flow entirely and calls Google APIs directly.

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
