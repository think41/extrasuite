# Authentication API Specification

This document defines the current ExtraSuite authentication protocol. It is based entirely on the v2 session-token flow used by the reference client.

## Overview

ExtraSuite splits authentication into two phases:

1. Browser login to establish a 30-day ExtraSuite session
2. Headless credential exchange for each typed command

The browser is only required for Phase 1. All command execution after that is headless until the session expires or is revoked.

## Design Goals

1. Authenticate the user with the organization's existing identity system
2. Avoid recurring browser interruptions during agent execution
3. Issue the minimum Google credential needed for each command
4. Keep long-lived secrets out of the client and server database
5. Preserve an audit trail of what was requested and why

## Actors

- Client: the ExtraSuite CLI or client library running on the user's machine
- Server: the ExtraSuite-compatible authentication service
- Browser: used only for interactive login
- Google: OAuth identity provider and token issuer

## Phase 1: Session Establishment

### Step 1: Start browser login

The client starts a localhost callback server on `127.0.0.1:<port>` and opens:

```http
GET /api/token/auth?port=<port>
```

Behavior:

1. Validate `port` is in the allowed range
2. If the browser already has a valid server-side session cookie, skip Google OAuth
3. Otherwise redirect the browser to the identity provider
4. After successful login, create a short-lived auth code
5. Redirect the browser to:

```http
http://localhost:<port>/on-authentication?code=<auth_code>
```

On failure, redirect to:

```http
http://localhost:<port>/on-authentication?error=<error_code>
```

### Step 2: Exchange auth code for session token

The client exchanges the auth code for a 30-day ExtraSuite session token:

```http
POST /api/auth/session/exchange
Content-Type: application/json

{
  "code": "auth_code_from_redirect",
  "device_mac": "0x1234abcd",
  "device_hostname": "laptop",
  "device_os": "Darwin",
  "device_platform": "macOS-15.3-arm64"
}
```

Response:

```json
{
  "session_token": "random_opaque_secret",
  "expires_at": "2026-04-05T11:30:00+00:00",
  "email": "user@example.com"
}
```

Server requirements:

1. Auth codes must be single-use
2. Auth codes must expire quickly (reference implementation: 2 minutes)
3. The server must validate the authenticated email against any domain allowlist
4. The server must ensure the user's service account exists before issuing a session
5. The session token must be stored server-side only as a SHA-256 hash

## Phase 2: Headless Credential Exchange

The client sends the session token in the `Authorization` header and requests credentials for a typed command:

```http
POST /api/auth/token
Authorization: Bearer <session_token>
Content-Type: application/json

{
  "command": {
    "type": "sheet.pull",
    "file_url": "https://docs.google.com/spreadsheets/d/..."
  },
  "reason": "User asked the agent to review the quarterly budget"
}
```

Response:

```json
{
  "credentials": [
    {
      "provider": "google",
      "kind": "bearer_sa",
      "token": "ya29...",
      "expires_at": "2026-03-06T13:45:00+00:00",
      "scopes": [],
      "metadata": {
        "service_account_email": "user-abc@project.iam.gserviceaccount.com"
      }
    }
  ],
  "command_type": "sheet.pull"
}
```

### Credential selection

The server maps `command.type` to the minimum required credential:

- Service-account credential for file operations such as `sheet.*`, `doc.*`, `slide.*`, `form.*`, and read-only Drive listing/search commands
- Domain-wide-delegation credential for user-impersonating commands such as `gmail.*`, `calendar.*`, `contacts.*`, `script.*`, and `drive.file.*`

Scope selection is server-defined. The client does not request raw OAuth scopes directly.

## Command Type Table

The authoritative command-to-credential mapping lives in:

- `server/src/extrasuite/server/command_registry.py`
- `server/src/extrasuite/server/commands.py`

Reference categories:

| Category | Credential kind | Notes |
|---|---|---|
| `sheet.*`, `doc.*`, `slide.*`, `form.*`, `drive.ls`, `drive.search` | `bearer_sa` | Access is limited to files shared with the per-user service account |
| `gmail.*`, `calendar.*`, `contacts.*`, `script.*`, `drive.file.*` | `bearer_dwd` | Scopes are determined by the server's command registry |

## Security Requirements

### Transport

1. All server endpoints must use HTTPS in production
2. The localhost callback must bind to `127.0.0.1`, not a public interface
3. The session token must be sent in the `Authorization` header, not in the body or query string

### Tokens

1. Session tokens should be opaque random secrets with high entropy
2. Session tokens must be stored server-side as hashes, not raw values
3. Google access tokens should remain short-lived (reference implementation: 1 hour)
4. The client should cache credentials only with restrictive file permissions

### Auth codes and state

1. OAuth state must be single-use and short-lived
2. Auth codes must be single-use and short-lived
3. Both values should be deleted immediately after successful consumption

### Auditing

Each `POST /api/auth/token` request should log:

- authenticated user email
- session hash prefix
- command type
- command context
- user-intent `reason`
- client IP
- timestamp

### Scope controls

For DWD-backed commands:

1. The server must derive scopes from `command.type`
2. The optional `DELEGATION_SCOPES` allowlist may reject commands before token generation
3. Google Workspace Admin Console remains the final authority for allowed scopes

## Rate Limits

Suggested defaults from the reference implementation:

| Endpoint | Limit |
|---|---|
| `GET /api/token/auth` | 10 requests per minute per IP |
| `POST /api/auth/session/exchange` | 10 requests per minute per IP |
| `POST /api/auth/token` | 60 requests per minute per IP |
| `GET /api/admin/sessions` | 30 requests per minute per IP |
| `DELETE /api/admin/sessions/{hash}` | 30 requests per minute per IP |
| `POST /api/admin/sessions/revoke-all` | 10 requests per minute per IP |

## Session Management Endpoints

The v2 protocol also includes self-service/admin session management:

### List sessions

```http
GET /api/admin/sessions?email=<email>
Authorization: Bearer <session_token>
```

### Revoke one session

```http
DELETE /api/admin/sessions/{session_hash}
Authorization: Bearer <session_token>
```

### Revoke all sessions

```http
POST /api/admin/sessions/revoke-all?email=<email>
Authorization: Bearer <session_token>
```

Authorization rules:

- Users may manage their own sessions
- Emails in `ADMIN_EMAILS` may manage sessions for any user

## Client Expectations

An ExtraSuite-compatible client should:

1. Read `EXTRASUITE_SERVER_URL` or `gateway.json`
2. Start a localhost callback server for Phase 1
3. Store the returned session token securely on disk
4. Cache short-lived credentials per command type
5. Re-run Phase 1 when the session expires or is revoked

## Reference Implementation

The open-source reference implementation lives in:

- `server/src/extrasuite/server/api.py`
- `server/src/extrasuite/server/database.py`
- `client/src/extrasuite/client/credentials.py`

Those files are the executable reference for this specification.
