# extrasuite

Python client library for ExtraSuite's v2 session-token authentication flow.

## Installation

```bash
pip install extrasuite
```

## Configuration

Use one of these:

1. `EXTRASUITE_SERVER_URL=https://your-server.example.com`
2. `~/.config/extrasuite/gateway.json` containing `{"EXTRASUITE_SERVER_URL": "https://your-server.example.com"}`
3. `CredentialsManager(server_url="https://your-server.example.com")`
4. `CredentialsManager(service_account_path="/path/to/service-account.json")`

## Programmatic Usage

```python
from extrasuite.client import CredentialsManager

manager = CredentialsManager(server_url="https://your-server.example.com")

credential = manager.get_credential(
    command={"type": "sheet.pull", "file_url": "https://docs.google.com/..."},
    reason="User asked to inspect the spreadsheet",
)

print(credential.kind)
print(credential.service_account_email)
print(credential.expires_in_seconds())
```

## Session Flow

1. `CredentialsManager` opens `GET /api/token/auth?port=<port>` in the browser when no valid session exists
2. The browser is redirected to localhost with a short-lived auth code
3. The client exchanges that code at `POST /api/auth/session/exchange`
4. The returned session token is stored in `~/.config/extrasuite/session.json`
5. Each command exchanges the session token at `POST /api/auth/token`

Credential cache files are stored under `~/.config/extrasuite/credentials/`.

## Service Account Mode

For non-interactive environments:

```python
from extrasuite.client import CredentialsManager

manager = CredentialsManager(service_account_path="/path/to/service-account.json")
```

This mode requires:

```bash
pip install google-auth
```
