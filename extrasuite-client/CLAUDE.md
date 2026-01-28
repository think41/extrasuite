## Overview

CLI application for authenticating with extrasuite-server. Provides `login` and `logout` commands, and manages token caching for use by extrasheet/extraslide.

## Key Files

| File | Purpose |
|------|---------|
| `src/extrasuite_client/credentials.py` | `CredentialsManager` - handles OAuth flow and token caching |
| `src/extrasuite_client/__init__.py` | Package exports |

## CLI Interface (Desired State)

```bash
# Authenticate with extrasuite-server (opens browser)
python -m extrasuite_client login

# Clear cached credentials
python -m extrasuite_client logout
```

Should also work via `uvx extrasuite-client login/logout`.

## Token Storage

- **Gateway config:** `~/.config/extrasuite/gateway.json` - Server URL configuration
- **Token cache:** `~/.config/extrasuite/token.json` - Short-lived access token (600 permissions)

## How Authentication Works

1. `login` starts a local HTTP server on a random port
2. Opens browser to `<server>/api/token/auth?port=<port>`
3. User authenticates with Google via extrasuite-server
4. Server redirects to `http://localhost:<port>/on-authentication?code=<auth_code>`
5. Client exchanges code via `/api/token/exchange`
6. Server impersonates user's service account, returns short-lived token
7. Token is cached locally in the OS keyring.

When token expires, the flow repeats. If user has a valid server session, SSO may skip the login step.

## Development

```bash
cd extrasuite-client
uv sync
uv run python -c "from extrasuite_client import CredentialsManager; print('OK')"
uv run ruff check .
```

## Current Status

The `CredentialsManager` class is functional and is manually copied into extrasheet/extraslide. Needs to be packaged properly and published to PyPI so it can be used as a proper dependency.

The CLI (`python -m extrasuite_client login/logout`) does not exist yet - currently only the library API is available.
