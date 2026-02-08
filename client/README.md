# extrasuite

Python client library for [ExtraSuite](https://github.com/think41/extrasuite) - authentication for declarative Google Workspace editing by AI agents.

ExtraSuite enables agents to declaratively edit Google Sheets, Docs, Slides, and Forms through a consistent pull-edit-diff-push workflow. This client library handles the secure OAuth token exchange that powers it all.

## Installation

```bash
pip install extrasuite
```

## Quick Start

### CLI Authentication

```bash
# Login (opens browser for OAuth)
python -m extrasuite.client login

# Or using the console script
extrasuite login

# Logout (clears cached credentials)
python -m extrasuite.client logout
```

### Programmatic Usage

```python
from extrasuite.client import authenticate

# Get a token - opens browser for authentication if needed
token = authenticate()

# Use the token with Google APIs
import gspread
from google.oauth2.credentials import Credentials

creds = Credentials(token.access_token)
gc = gspread.authorize(creds)
sheet = gc.open("My Spreadsheet").sheet1
```

## Configuration

Authentication can be configured via:

1. **Constructor parameters** (highest priority)
2. **Environment variables**
3. **Gateway config file** `~/.config/extrasuite/gateway.json` (created by skill installation)

### Environment Variables

| Variable | Description |
|----------|-------------|
| `EXTRASUITE_AUTH_URL` | URL to start authentication flow |
| `EXTRASUITE_EXCHANGE_URL` | URL to exchange auth code for token |
| `SERVICE_ACCOUNT_PATH` | Path to service account JSON file (alternative auth) |

### Using CredentialsManager

For more control, use the `CredentialsManager` class directly:

```python
from extrasuite.client import CredentialsManager

manager = CredentialsManager(
    auth_url="https://your-server.example.com/api/token/auth",
    exchange_url="https://your-server.example.com/api/token/exchange",
)

token = manager.get_token()
print(f"Service account: {token.service_account_email}")
print(f"Expires in: {token.expires_in_seconds()} seconds")
```

### Service Account Mode

For non-interactive environments, you can use a service account file:

```python
from extrasuite.client import CredentialsManager

manager = CredentialsManager(service_account_path="/path/to/service-account.json")
token = manager.get_token()
```

Note: Service account mode requires the `google-auth` package:
```bash
pip install google-auth
```

## Token Storage

Tokens are securely stored in the OS keyring:
- **macOS**: Keychain
- **Windows**: Credential Locker
- **Linux**: Secret Service (via libsecret)

## How It Works

1. When you call `authenticate()` or `get_token()`, the client checks the OS keyring for a cached token
2. If no valid cached token exists, it starts a local HTTP server and opens your browser
3. After authentication with the ExtraSuite server, the browser redirects back with an auth code
4. The client exchanges the auth code for a short-lived access token
5. The token is cached in the OS keyring for subsequent calls

Tokens are short-lived (1 hour) and automatically refreshed when expired.

## API Reference

### `authenticate()`

Convenience function to get a token with minimal code.

```python
from extrasuite.client import authenticate

token = authenticate(
    auth_url=None,           # Optional: override auth URL
    exchange_url=None,       # Optional: override exchange URL
    service_account_path=None,  # Optional: use service account instead
    force_refresh=False,     # Force re-authentication
)
```

### `Token`

The token object returned by authentication.

```python
token.access_token          # The OAuth2 access token string
token.service_account_email # Email of the service account
token.expires_at            # Unix timestamp when token expires
token.is_valid()            # Check if token is still valid
token.expires_in_seconds()  # Seconds until expiration
```

## Requirements

- Python 3.10+
- Dependencies: `keyring`, `certifi`

For Google Workspace integration via ExtraSuite packages:
```bash
pip install extrasheet extradoc extraslide extraform
```

## License

MIT - Copyright (c) 2026 Think41 Technologies Pvt. Ltd.
