# Authentication API Specification

This document defines the protocol for authenticating AI agents and issuing short-lived service account tokens. It is designed to be **implementation-agnostic** — organizations can implement this specification using their own authentication systems, access policies, and infrastructure.

## Overview

The ExtraSuite authentication protocol enables AI agents running on user devices to obtain short-lived Google Cloud service account tokens. The protocol is designed around these principles:

1. **User Authentication** — Verify the user's identity through your organization's authentication mechanism
2. **Access Control** — Apply your organization's policies to determine who can obtain tokens
3. **Localhost Redirect** — Securely deliver credentials to the CLI running on the user's device
4. **Short-lived Tokens** — Issue tokens with limited lifetime to minimize exposure

```
┌──────────────┐                      ┌──────────────────┐
│  AI Agent    │                      │  Your Auth       │
│  (CLI)       │                      │  Server          │
│              │                      │                  │
│  1. Start    │─────────────────────▶│  2. Authenticate │
│     local    │  GET /auth?port=N    │     user         │
│     server   │                      │                  │
│              │                      │  3. Apply access │
│              │                      │     policies     │
│              │                      │                  │
│  5. Receive  │◀─────────────────────│  4. Redirect to  │
│     code     │  localhost:N?code=X  │     localhost    │
│              │                      │                  │
│  6. Exchange │─────────────────────▶│  7. Generate     │
│     code     │  POST /exchange      │     token        │
│              │◀─────────────────────│                  │
│  8. Use      │      {token, ...}    │                  │
│     token    │                      │                  │
└──────────────┘                      └──────────────────┘
```

## Why This Design?

### Problem: AI Agents Need Google API Access

AI agents need to call Google APIs (Sheets, Docs, Slides, Drive) on behalf of users. Traditional OAuth flows don't work well because:

- Agents run as CLI tools, not web applications
- Users don't want to grant long-lived access to agents
- Organizations want to control which employees can use this capability

### Solution: Server-Mediated Token Issuance

Instead of the AI agent obtaining OAuth tokens directly, a trusted server:

1. Authenticates the user (using your existing auth system)
2. Applies access policies (your rules about who can use this)
3. Issues a short-lived token for a dedicated service account

This gives organizations full control over authentication and authorization while providing agents with the tokens they need.

---

## Protocol Specification

### Endpoint 1: Start Authentication

**Purpose:** Initiate the authentication flow. The server should authenticate the user, apply access policies, and ultimately redirect to the CLI's local server.

```
GET /api/token/auth?port=<port>
```

#### Request

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `port` | integer | Yes | Port number where the CLI is listening (1024-65535) |

#### Server Behavior

The server MUST:

1. **Validate the port parameter**
   - Reject if port is outside the valid range (1024-65535)
   - Reject if port is not a valid integer

2. **Authenticate the user**
   - Use your organization's authentication mechanism
   - This could be OAuth, SAML, SSO, session cookies, etc.
   - If user is not authenticated, initiate your auth flow

3. **Apply access policies**
   - Check if the authenticated user is allowed to obtain tokens
   - Apply any organization-specific rules (department, role, etc.)
   - Show any required interstitials (terms of service, notices, etc.)

4. **Generate an authorization code**
   - Create a short-lived, single-use authorization code
   - Associate it with the user's service account email
   - Code MUST expire within 2 minutes (recommended: 120 seconds)
   - Code MUST be single-use (invalidated after first exchange)

5. **Redirect to localhost**
   - Redirect the browser to: `http://localhost:<port>/on-authentication?code=<auth_code>`
   - Include the authorization code as a query parameter

#### Responses

**Success (Redirect):**
```
HTTP/1.1 302 Found
Location: http://localhost:8085/on-authentication?code=abc123xyz...
```

**Error - Invalid Port:**
```
HTTP/1.1 400 Bad Request
Content-Type: application/json

{
  "error": "invalid_request",
  "error_description": "Port must be between 1024 and 65535"
}
```

**Error - Access Denied:**
```
HTTP/1.1 403 Forbidden
Content-Type: application/json

{
  "error": "access_denied",
  "error_description": "User is not authorized to obtain tokens"
}
```

#### Sequence Diagram

```
CLI                     Server                    Auth System
 │                         │                           │
 │  GET /auth?port=8085    │                           │
 │────────────────────────▶│                           │
 │                         │                           │
 │                         │  Authenticate user        │
 │                         │──────────────────────────▶│
 │                         │                           │
 │                         │  User identity            │
 │                         │◀──────────────────────────│
 │                         │                           │
 │                         │  Apply access policies    │
 │                         │  (internal)               │
 │                         │                           │
 │                         │  Generate auth code       │
 │                         │  (internal)               │
 │                         │                           │
 │  302 Redirect           │                           │
 │  localhost:8085?code=X  │                           │
 │◀────────────────────────│                           │
 │                         │                           │
```

---

### Endpoint 2: Exchange Code for Token

**Purpose:** Exchange a valid authorization code for a short-lived access token.

```
POST /api/token/exchange
```

#### Request

**Content-Type:** `application/json`

```json
{
  "code": "abc123xyz..."
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `code` | string | Yes | The authorization code received via localhost redirect |

#### Server Behavior

The server MUST:

1. **Validate the authorization code**
   - Verify the code exists and has not expired
   - Verify the code has not been used before
   - Invalidate the code immediately (single-use)

2. **Generate the access token**
   - Create a short-lived access token for the user's service account
   - Token MUST have limited lifetime (recommended: 60 minutes max)
   - Token SHOULD include appropriate scopes for Google APIs

3. **Return token information**
   - Include the access token
   - Include the expiration timestamp
   - Include the service account email

#### Response

**Success:**
```
HTTP/1.1 200 OK
Content-Type: application/json

{
  "token": "ya29.a0AfH6SMB...",
  "expires_at": "2026-01-23T14:30:00Z",
  "service_account": "user-abc@project.iam.gserviceaccount.com"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `token` | string | The access token for Google API calls |
| `expires_at` | string | ISO 8601 timestamp when the token expires |
| `service_account` | string | Email of the service account (for sharing files) |

**Error - Invalid Code:**
```
HTTP/1.1 400 Bad Request
Content-Type: application/json

{
  "error": "invalid_grant",
  "error_description": "Authorization code is invalid or expired"
}
```

**Error - Code Already Used:**
```
HTTP/1.1 400 Bad Request
Content-Type: application/json

{
  "error": "invalid_grant",
  "error_description": "Authorization code has already been used"
}
```

---

### Localhost Callback Format

The CLI starts a temporary HTTP server on localhost to receive the authorization code. The server redirects the browser to this endpoint after successful authentication.

```
GET http://localhost:<port>/on-authentication?code=<auth_code>
```

#### Query Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `code` | string | Authorization code to exchange for a token |
| `error` | string | (Optional) Error code if authentication failed |
| `error_description` | string | (Optional) Human-readable error message |

#### Success Case

```
GET http://localhost:8085/on-authentication?code=abc123xyz...
```

The CLI should:
1. Extract the `code` parameter
2. Close the local HTTP server
3. Call the token exchange endpoint
4. Cache the resulting token

#### Error Case

```
GET http://localhost:8085/on-authentication?error=access_denied&error_description=User%20not%20authorized
```

The CLI should:
1. Display the error to the user
2. Close the local HTTP server
3. Exit with an appropriate error code

---

## Security Requirements

### Authorization Code Requirements

| Requirement | Value | Rationale |
|-------------|-------|-----------|
| Lifetime | ≤ 120 seconds | Minimize window for interception |
| Usage | Single-use | Prevent replay attacks |
| Entropy | ≥ 256 bits | Prevent guessing |
| Storage | Server-side only | Code never stored on client |

### Access Token Requirements

| Requirement | Value | Rationale |
|-------------|-------|-----------|
| Lifetime | ≤ 60 minutes | Limit exposure if compromised |
| Scope | Minimum necessary | Principle of least privilege |
| Refresh | Not supported | User re-authenticates for new token |

### Transport Security

| Requirement | Description |
|-------------|-------------|
| HTTPS Required | All server endpoints MUST use HTTPS |
| Localhost Exception | Redirect to localhost MAY use HTTP (browser enforces same-origin) |
| Certificate Validation | Clients MUST validate server certificates |

### Rate Limiting

Implementations SHOULD apply rate limiting to prevent abuse:

| Endpoint | Recommended Limit |
|----------|-------------------|
| `/api/token/auth` | 10 requests per minute per IP |
| `/api/token/exchange` | 20 requests per minute per IP |

---

## Implementation Guide

### What You Need to Implement

1. **User Authentication**
   - Integrate with your existing identity provider (OAuth, SAML, LDAP, etc.)
   - Manage user sessions (cookies, tokens, etc.)

2. **Access Control**
   - Define who can obtain tokens (all employees, specific groups, etc.)
   - Implement any approval workflows or interstitials

3. **Service Account Management**
   - Create and manage Google Cloud service accounts for users
   - Each user should have their own dedicated service account
   - Service accounts need appropriate IAM roles for Google APIs

4. **Token Generation**
   - Use Google Cloud IAM to generate short-lived access tokens
   - Impersonate user service accounts using your server's credentials

5. **Code Storage**
   - Store authorization codes securely (database, cache, etc.)
   - Implement expiration and single-use semantics

### Service Account Setup

Each user needs a dedicated service account with these roles:

| Role | Purpose |
|------|---------|
| `roles/drive.readonly` | Read access to Google Drive (file metadata) |
| `roles/sheets.editor` | Read/write access to Google Sheets |
| `roles/docs.editor` | Read/write access to Google Docs |
| `roles/slides.editor` | Read/write access to Google Slides |

Your server's service account needs:

| Role | Purpose |
|------|---------|
| `roles/iam.serviceAccountAdmin` | Create service accounts for users |
| `roles/iam.serviceAccountTokenCreator` | Generate tokens for user service accounts |

### Token Generation (Google Cloud)

To generate a short-lived token for a user's service account:

```python
from google.auth import impersonated_credentials
from google.oauth2 import service_account

# Your server's credentials
server_credentials = service_account.Credentials.from_service_account_file(
    'server-sa-key.json'
)

# Impersonate the user's service account
target_credentials = impersonated_credentials.Credentials(
    source_credentials=server_credentials,
    target_principal='user-sa@project.iam.gserviceaccount.com',
    target_scopes=[
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/documents',
        'https://www.googleapis.com/auth/presentations',
        'https://www.googleapis.com/auth/drive.readonly',
    ],
    lifetime=3600,  # 1 hour
)

# Refresh to get the actual token
target_credentials.refresh(google.auth.transport.requests.Request())
access_token = target_credentials.token
expiry = target_credentials.expiry
```

---

## Client Implementation

The reference client implementation is available at:
[`client/src/extrasuite/client/credentials.py`](https://github.com/think41/extrasuite/blob/main/client/src/extrasuite/client/credentials.py)

### Key Client Responsibilities

1. **Start a local HTTP server** on a random available port
2. **Open the browser** to the server's auth endpoint with the port number
3. **Wait for the redirect** to receive the authorization code
4. **Exchange the code** for a token via POST request
5. **Cache the token** locally with appropriate file permissions (0600)
6. **Return cached tokens** when still valid (with 60-second buffer)

### Fallback for Headless Environments

If the browser cannot be opened (headless server, SSH session):

1. Print the authentication URL to stdout
2. Optionally accept the authorization code via stdin
3. Display the code on the callback page for manual copy/paste

---

## Compatibility with ExtraSuite Reference Implementation

The reference implementation at [github.com/think41/extrasuite](https://github.com/think41/extrasuite) implements this specification with:

- Google OAuth for user authentication
- Firestore for code storage
- Google Cloud Run for hosting
- Automatic service account provisioning

If you implement this specification, your server will be compatible with:

- The `extrasuite` client library
- All ExtraSuite skills (gsheetx, gslidex, gdocx)
- Any AI agent that uses the ExtraSuite protocol

---

## Example Flows

### Flow 1: First-Time User

```
1. User: "Read my spreadsheet"
2. Agent invokes skill, which calls CredentialsManager
3. CredentialsManager finds no cached token
4. CredentialsManager starts local server on port 8085
5. CredentialsManager opens browser to:
   https://your-server.com/api/token/auth?port=8085
6. Server redirects to your login page
7. User logs in with corporate SSO
8. Server checks user is in "AI Tools" group (your policy)
9. Server generates auth code "abc123"
10. Server redirects browser to:
    http://localhost:8085/on-authentication?code=abc123
11. CredentialsManager receives code
12. CredentialsManager POSTs to /api/token/exchange
13. Server returns token + expiry + service account email
14. CredentialsManager caches token, returns to agent
15. Agent uses token to read spreadsheet
```

### Flow 2: Returning User (Valid Session)

```
1. User: "Update the sales report"
2. Agent invokes skill, CredentialsManager finds expired token
3. CredentialsManager starts local server on port 9012
4. CredentialsManager opens browser to:
   https://your-server.com/api/token/auth?port=9012
5. Server recognizes user's session cookie (still valid)
6. Server skips login, generates new auth code
7. Server redirects to localhost:9012
8. Browser opens briefly and closes
9. CredentialsManager exchanges code for new token
10. Agent updates spreadsheet
```

### Flow 3: Access Denied

```
1. User: "Read my spreadsheet"
2. Agent invokes skill, CredentialsManager starts auth flow
3. Browser opens to server
4. User logs in successfully
5. Server checks policies: user not in allowed group
6. Server redirects to:
   http://localhost:8085/on-authentication?error=access_denied&error_description=...
7. CredentialsManager displays error
8. Agent reports: "Access denied - contact your administrator"
```

---

## Delegation Protocol (Optional)

The delegation protocol enables AI agents to obtain **user-level** access tokens for APIs like Gmail, Calendar, and Apps Script. Unlike the service account flow above (where tokens act as a service account), delegation tokens act **as the user** via Google's domain-wide delegation.

This protocol mirrors the service account flow — same localhost redirect pattern, same auth code exchange — but with different endpoints and response format.

### Prerequisites

- Domain-wide delegation configured in Google Workspace Admin Console
- Server has `DELEGATION_ENABLED=true`
- Optionally, `DELEGATION_SCOPES` restricts which scopes can be requested

### Endpoint 1: Start Delegation Authentication

**Purpose:** Initiate the delegation flow. The server resolves scope names, validates against the optional allowlist, authenticates the user, and redirects to the CLI's local server.

```
GET /api/delegation/auth?port=<port>&scopes=<scopes>&reason=<reason>
```

#### Request

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `port` | integer | Yes | Port number where the CLI is listening (1024-65535) |
| `scopes` | string | Yes | Comma-separated scope names (e.g., `gmail.send,calendar`) |
| `reason` | string | No | Human-readable reason for the request (logged for audit) |

**Scope names** are short identifiers that map to full Google OAuth scope URLs by prefixing `https://www.googleapis.com/auth/`. For example:

| Short name | Full scope URL |
|------------|---------------|
| `gmail.send` | `https://www.googleapis.com/auth/gmail.send` |
| `gmail.readonly` | `https://www.googleapis.com/auth/gmail.readonly` |
| `calendar` | `https://www.googleapis.com/auth/calendar` |
| `calendar.readonly` | `https://www.googleapis.com/auth/calendar.readonly` |
| `drive` | `https://www.googleapis.com/auth/drive` |
| `drive.readonly` | `https://www.googleapis.com/auth/drive.readonly` |
| `script.projects` | `https://www.googleapis.com/auth/script.projects` |

#### Server Behavior

The server MUST:

1. **Check if delegation is enabled** — return 404 if not
2. **Resolve and validate scopes**
   - Prefix each short name with `https://www.googleapis.com/auth/`
   - If `DELEGATION_SCOPES` allowlist is configured, reject scopes not in the list (400)
3. **Authenticate the user** (same as service account flow)
4. **Generate a delegation authorization code**
   - Associate it with the user's email, requested scopes, and reason
   - Same TTL and single-use requirements as service account auth codes
5. **Redirect to localhost** — same format as service account flow

#### Responses

**Success (Redirect):**
```
HTTP/1.1 302 Found
Location: http://localhost:8085/on-authentication?code=abc123xyz...
```

**Error - Delegation Not Enabled:**
```
HTTP/1.1 404 Not Found
Content-Type: application/json

{
  "detail": "Domain-wide delegation is not enabled on this server"
}
```

**Error - Disallowed Scope:**
```
HTTP/1.1 400 Bad Request
Content-Type: application/json

{
  "detail": "Disallowed scopes: gmail.send"
}
```

---

### Endpoint 2: Exchange Code for Delegation Token

**Purpose:** Exchange a valid delegation authorization code for a user-level access token.

```
POST /api/delegation/exchange
```

#### Request

**Content-Type:** `application/json`

```json
{
  "code": "abc123xyz..."
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `code` | string | Yes | The delegation authorization code received via localhost redirect |

#### Server Behavior

The server MUST:

1. **Validate the authorization code** (same requirements as service account flow)
2. **Log the delegation request** for audit (user email, scopes, reason, timestamp)
3. **Generate a delegated access token**
   - Build a JWT with `sub` set to the user's email and requested scopes
   - Sign the JWT using the server's service account via IAM `signBlob` API
   - Exchange the signed JWT at Google's token endpoint for an access token
   - If delegation fails (e.g., scope not authorized in Workspace Admin Console), return 403
4. **Return token information**

#### Response

**Success:**
```
HTTP/1.1 200 OK
Content-Type: application/json

{
  "access_token": "ya29.a0AfH6SMB...",
  "expires_at": "2026-01-23T14:30:00Z",
  "scopes": [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar"
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `access_token` | string | The access token for Google API calls (acts as the user) |
| `expires_at` | string | ISO 8601 timestamp when the token expires |
| `scopes` | array | List of granted scope URLs |

**Error - Invalid Code:**
```
HTTP/1.1 400 Bad Request
Content-Type: application/json

{
  "detail": "Invalid or expired auth code"
}
```

**Error - Delegation Failed:**
```
HTTP/1.1 403 Forbidden
Content-Type: application/json

{
  "detail": "Domain-wide delegation failed. The requested scopes may not be authorized in Google Workspace Admin Console."
}
```

---

### Delegation Security Requirements

All security requirements from the service account flow apply (auth code TTL, single-use, entropy, transport security, rate limiting).

Additionally:

| Requirement | Value | Rationale |
|-------------|-------|-----------|
| Scope allowlist | Optional (`DELEGATION_SCOPES`) | Defense-in-depth on top of Workspace Admin Console |
| Audit logging | All requests logged | User, scopes, reason, timestamp recorded |
| Workspace Admin enforcement | Required | Google rejects unauthorized scopes at token generation |

### Delegation Example Flow

```
1. User: "Send this report via email"
2. Agent needs gmail.send scope
3. Agent calls CredentialsManager.get_oauth_token(["gmail.send"], reason="sending report")
4. CredentialsManager starts local server on port 8085
5. CredentialsManager opens browser to:
   https://your-server.com/api/delegation/auth?port=8085&scopes=gmail.send&reason=sending+report
6. Server validates scopes against DELEGATION_SCOPES allowlist (if configured)
7. Server authenticates user (or uses existing session)
8. Server generates delegation auth code with {email, scopes, reason}
9. Server redirects browser to:
   http://localhost:8085/on-authentication?code=abc123
10. CredentialsManager receives code
11. CredentialsManager POSTs to /api/delegation/exchange
12. Server logs delegation request, generates token via domain-wide delegation
13. Server returns {access_token, expires_at, scopes}
14. Agent uses token to send email via Gmail API
```

---

## Changelog

| Version | Date | Changes |
|---------|------|---------|
| 1.1 | 2026-02-10 | Add delegation protocol specification |
| 1.0 | 2026-01-23 | Initial specification |
