## Overview

Python client library for obtaining short-lived Google API credentials. All credentials are obtained via `CredentialsManager.get_credential()` using a typed command object.

## Security Constraint: No Auth in Agent Code

**Agents invoking the CLI must never:**
- Read credential files or keyring entries
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
    server_url="https://server.example.com",
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

**How it works (v2):** Loads the session token from the OS keyring (macOS Keychain, Linux SecretService, Windows Credential Locker). If valid, POSTs to `POST /api/auth/token` for a headless credential exchange. If no session exists, initiates the Phase 1 browser flow to get a 30-day session first. Access tokens are never written to disk — they are held only in process memory.

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

### Token Lifetimes

| Token type | Server lifetime | Client-side cap | Stored where |
|---|---|---|---|
| SA (service account) | 1 hour | 60 min | process memory only |
| DWD (domain-wide delegation) | 1 hour | 10 min | process memory only |
| Session | 30 days | 30 days | OS keyring |

Profile metadata (profile name → email, active pointer) is stored in `~/.config/extrasuite/profiles.json` (0600). No tokens in that file.

### headless parameter

```python
manager = CredentialsManager(headless=True)
# Or: EXTRASUITE_HEADLESS=1
```

In headless mode, Phase 1 calls `/api/token/auth` (no port parameter), which displays the auth code on an HTML page instead of redirecting to a localhost callback server. The URL is printed to stderr and the code is read from stdin.

## CLI

### Auth commands (v2)

```bash
extrasuite auth login                        # Browser flow → 30-day session token (keyring)
extrasuite auth login --headless             # Print URL, prompt for code on stdin
extrasuite auth login --profile work         # Log in to a named profile
extrasuite auth logout                       # Revoke session server-side + remove from keyring
extrasuite auth logout --profile work        # Log out a specific profile
extrasuite auth status                       # Show all profiles and session validity
extrasuite auth activate <profile>           # Set the active profile
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

## Configuration precedence

1. Constructor parameters (`server_url`, `gateway_config_path`, `service_account_path`)
2. Environment variables (`EXTRASUITE_SERVER_URL`)
3. `~/.config/extrasuite/gateway.json`
4. `SERVICE_ACCOUNT_PATH` env var (fallback, no server needed)

## gateway.json format

```json
{"EXTRASUITE_SERVER_URL": "https://your-server.example.com"}
```

From `EXTRASUITE_SERVER_URL`, the following are derived:
- `{server}/api/token/auth`
- `{server}/api/auth/session/exchange`
- `{server}/api/auth/token`

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
