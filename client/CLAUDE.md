## Overview

CLI application for authenticating with extrasuite-server. Provides `login` and `logout` commands, and manages token caching for use by extrasheet/extraslide.

## Key Files

| File | Purpose |
|------|---------|
| `src/extrasuite/client/credentials.py` | `CredentialsManager` - handles OAuth flow and token caching |
| `src/extrasuite/client/__main__.py` | CLI entry point for login/logout commands |
| `src/extrasuite/client/__init__.py` | Package exports |

## CLI Interface

```bash
# Authenticate with extrasuite-server (opens browser)
python -m extrasuite.client login

# Clear cached credentials
python -m extrasuite.client logout

# Also works via uvx or pip install
uvx extrasuite login
extrasuite login
```

## Token Storage

- **Gateway config:** `~/.config/extrasuite/gateway.json` - Server URL configuration
- **Token cache:** OS keyring (macOS Keychain, Windows Credential Locker, Linux Secret Service)

## How Authentication Works

1. `login` starts a local HTTP server on a random port
2. Opens browser to `<server>/api/token/auth?port=<port>`
3. User authenticates with Google via extrasuite-server
4. Server redirects to `http://localhost:<port>/on-authentication?code=<auth_code>`
5. Client exchanges code via `/api/token/exchange`
6. Server impersonates user's service account, returns short-lived token
7. Token is cached securely in the OS keyring

When token expires, the flow repeats. If user has a valid server session, SSO may skip the login step.

## Development

```bash
cd client
uv sync
uv run python -c "from extrasuite.client import CredentialsManager; print('OK')"
uv run ruff check .
uv run pytest tests/ -v
```

## Library API

```python
from extrasuite.client import authenticate, CredentialsManager, Token

# Simple API - uses cached token or triggers OAuth flow
token = authenticate()
print(f"Token: {token.access_token[:50]}...")

# Advanced API - more control over authentication
manager = CredentialsManager()
token = manager.get_token(force_refresh=True)
```
