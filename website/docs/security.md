# Security

ExtraSuite is designed to make automated agents useful **without removing control from employees**. This document explains the security model from both employee and administrator perspectives.

## The Core Principle

!!! info "Key Security Guarantee"
    **ExtraSuite agents can only access what you explicitly share with them.**

If you don't share a document with your agent, the agent cannot access it. Period.

## What This Means for You

Each employee is assigned a dedicated virtual agent with its own email address. If you share a Google Doc or Google Sheet with your agent's email address, the agent can access **only that document**, and only with the permission level you choose (view, comment, or edit).

### You Stay in Control

<div class="grid cards" markdown>

-   :material-close-circle:{ .lg .middle } **Revoke Access Instantly**

    ---

    Remove the agent from any document's sharing settings in Google Drive. Access is revoked immediately.

-   :material-history:{ .lg .middle } **Full Transparency**

    ---

    All edits appear clearly in version history under the agent's identity. You can see exactly what changed.

-   :material-undo:{ .lg .middle } **Easy Rollback**

    ---

    Use Google's built-in version controls to undo any changes made by the agent.

</div>

!!! tip "ExtraSuite does not bypass Google Workspace permissions"
    Authorization is enforced by Google Drive itself, not by ExtraSuite. We coordinate with Google's security model but never override it.

---

## Security Model (Technical Details)

### Identity and Access Control

**One service account per employee:**

- Each service account represents exactly one employee's agent
- Service accounts have **no default permissions**
- Access exists only when an employee explicitly shares a document

**Explicit, user-controlled authorization:**

- Employees control access using standard Google Drive sharing
- Read, comment, and edit permissions are defined by the employee
- Access can be revoked immediately via Google Drive

**No inherited or transitive access:**

- Agent access is not inherited from document collaborators
- If an employee does not explicitly share a document, the agent cannot access it

**Email domain allowlist:**

- Organizations can restrict authentication to specific email domains
- Users outside allowed domains cannot authenticate
- Prevents unauthorized users from creating service accounts

### Token and Credential Handling

**Typed command protocol:**

Every token request uses a **typed command** — a structured object declaring the exact operation the agent intends to perform (e.g. `sheet.pull`, `gmail.compose`, `calendar.view`). The server uses the command type to determine what credential to issue. No credential is issued speculatively or in bulk.

**Two credential types, minimum scope:**

| Command category | Credential issued | Scope |
|---|---|---|
| `sheet.*`, `doc.*`, `slide.*`, `form.*`, `drive.ls`, `drive.search` | Service account token | Files shared with the per-user SA |
| `gmail.*`, `calendar.*`, `script.*`, `contacts.*`, `drive.file.*` | Delegated access token | Exactly the OAuth scope(s) required for that command |

- Service account tokens give the agent access only to files explicitly shared with its service account
- Delegated tokens impersonate the user for a single scope; the scope allowlist is controlled by the administrator

**Short-lived Google access tokens:**

- Google access tokens expire after **1 hour** (configurable)
- Tokens are generated on demand and never stored server-side or client-side
- The agent cannot refresh a token — it must request a new one via the server

**Session token (stored locally):**

- After the initial browser-based login, the client stores a **session token** in `~/.config/extrasuite/` (valid 30 days)
- The session token authenticates the client to the ExtraSuite server only — it is never sent to Google APIs
- Session tokens are stored as SHA-256 hashes in Firestore; the raw token never touches the database
- Sessions can be listed and revoked at any time via `extrasuite auth sessions`

**No private key material:**

- ExtraSuite does not use downloaded service account key files
- No Google private keys or refresh tokens are exposed to agents or clients

**Agent intent logging:**

Every token request includes a `reason` field — the agent's stated purpose for the operation. The server logs the user email, command type, command context, and reason to an audit log before issuing any token. This creates a record of not just *what* was accessed, but *why* the agent claimed it was needed.

Administrators can also configure a `DELEGATION_SCOPES` allowlist. Token requests for scopes outside this list are rejected before any Google API call is made.

### Domain-Wide Delegation (Optional)

ExtraSuite optionally supports **domain-wide delegation** for user-specific APIs like Gmail, Calendar, Apps Script, and Contacts. This is an opt-in feature controlled by the `DELEGATION_ENABLED` environment variable.

**How it works:**

- The server impersonates the user via Google's domain-wide delegation mechanism
- The client sends a typed **command object** (e.g. `{"type": "gmail.compose", "to": ["..."], ...}`) and a `reason` string; the server's command registry maps the command type to the required OAuth scope(s)
- The server validates the command type and looks up the exact scope(s) needed — the client never specifies scopes directly
- **Two layers of scope enforcement:**
    1. **Server-side allowlist** (`DELEGATION_SCOPES`) — optional, rejects disallowed scopes before any Google API call
    2. **Google Workspace Admin Console** — authoritative enforcement; if a scope isn't authorized there, the delegation call fails and the server returns 403
- All delegation requests are logged with user email, command type, full command context, reason, and timestamp before any token is issued

**Security model comparison:**

| Aspect | SA-per-user (default) | Domain-wide delegation |
|--------|----------------------|----------------------|
| Token acts as | Service account | User |
| Access scope | Files shared with SA | Delegated scopes (Gmail, Calendar, etc.) |
| Admin control | SA creation | Workspace Admin Console |
| Audit trail | Token generation logs | Delegation request logs with reason |

**Risk analysis:**

- Server compromise could allow impersonation of any user for delegated scopes
- Mitigations: Cloud Run (no SSH, immutable containers), IAM audit logs, no SA key files
- Scopes are enforced at two levels: server-side `DELEGATION_SCOPES` allowlist and Google Workspace Admin Console

### CLI Authentication Flow

**Phase 1 — Initial login (once per 30 days, browser required):**

1. `extrasuite auth login` opens a browser for Google OAuth
2. The server generates a temporary auth code (valid 2 minutes)
3. The CLI exchanges the auth code for a **session token** via POST request
4. Auth codes are single-use and deleted immediately after exchange
5. The session token is stored locally and used to authenticate all subsequent requests

**Phase 2 — Per-command token exchange (headless, no browser):**

1. The CLI sends a typed command + reason to `POST /api/auth/token`, authenticated with the session token in the `Authorization` header (never in the URL or body)
2. The server validates the session token (hash lookup in Firestore), then routes based on command type to issue the appropriate Google access token
3. The CLI uses the returned token for the Google API call and discards it when done

**Localhost binding:**

- The OAuth callback server binds to `127.0.0.1` (not `localhost`)
- Prevents DNS rebinding attacks
- Only the local machine can receive the auth code

**Secure token storage:**

- The session token is stored with restrictive file permissions
- Directory: owner read/write/execute only (0700)
- Token file: owner read/write only (0600)

### Server-Side Data

**Minimal data retention:**

- The server stores the email-to-service-account mapping and session token hashes
- Session tokens are stored as SHA-256 hashes in Firestore (the raw token never touches the database)
- No Google OAuth access tokens are stored server-side — they are generated on demand and returned directly to the client
- Access logs store command type, command context (non-sensitive fields like file URLs), and the agent's stated reason — not file contents or sensitive data

**Automatic expiration:**

| Data Type | Lifetime |
|-----------|----------|
| Session tokens | 30 days active; Firestore document retained for 60 days for audit then auto-deleted |
| Access tokens | 1 hour |
| Auth codes | 2 minutes |
| OAuth state tokens | 10 minutes |

---

## Configurable Security Settings

The following security settings can be configured via environment variables:

### Session Token Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `SESSION_TOKEN_EXPIRY_DAYS` | `30` | Session token lifetime in days |
| `ADMIN_EMAILS` | (empty) | CSV of admin email addresses who can manage any user's sessions |

### Access Token Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `TOKEN_EXPIRY_MINUTES` | `60` (1 hour) | Access token lifetime in minutes |

### Server URL Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `BASE_DOMAIN` | (none) | Server domain (e.g., `extrasuite.example.com`) |
| `SERVER_URL` | Derived from `BASE_DOMAIN` | Full server URL. If `BASE_DOMAIN` is set, defaults to `https://{BASE_DOMAIN}` |

!!! tip "Production Configuration"
    For production deployments, set `BASE_DOMAIN` to your server's domain. This automatically configures `SERVER_URL` with HTTPS and sets the session cookie domain appropriately.

!!! warning "Local Development"
    For local development, set `SERVER_URL=http://localhost:8001` explicitly, as HTTPS is not available locally.

---

## Security Constants

| Constant | Value | Description |
|----------|-------|-------------|
| `SESSION_TOKEN_EXPIRY_DAYS` | 30 days (configurable) | Lifetime of 30-day session tokens |
| `ACCESS_TOKEN_TTL` | 1 hour (configurable) | Lifetime of issued access tokens |
| `AUTH_CODE_TTL` | 2 minutes | Lifetime of temporary auth codes |
| `OAUTH_STATE_TTL` | 10 minutes | Lifetime of OAuth state tokens |
| `TOKEN_DIR_PERMISSIONS` | `0700` | Directory permissions for credential cache |
| `TOKEN_FILE_PERMISSIONS` | `0600` | File permissions for cached credentials |

---

## Auditability and Transparency

### Clear Edit Attribution

All edits appear in Google Docs and Sheets version history under the agent's service account identity. There is no shared or ambiguous editor identity.

### Native Rollback

Employees can inspect changes and revert them using Google's built-in version history. ExtraSuite does not replace or override Google Workspace revision controls.

### Server-Side Logging

- Token generation events are logged with user email and service account
- Authentication failures are logged for security monitoring
- All logs are available through Google Cloud Logging

---

## Limitations and Non-Goals

### Agent Behavior is Out of Scope

Once a document is shared, what the agent does with that access (logic, prompts, models, workflows) is outside the scope of this security model. ExtraSuite ensures **who** can access **what**, not **how** an agent decides to modify content.

### No Prevention of Intentional Misuse

If an employee grants edit access, the agent can edit within that permission. ExtraSuite does not attempt to restrict legitimate user-directed actions.

### Service Account Lifecycle

- ExtraSuite relies on one service account per employee
- Organizations are responsible for appropriate lifecycle management
- Including offboarding and cleanup of inactive agents

---

## Security Guarantees

ExtraSuite guarantees the following:

- ✅ Agents cannot access documents unless an employee explicitly shares them
- ✅ Access is limited to the permission level chosen by the employee
- ✅ All agent edits are attributable, auditable, and reversible using native Google Workspace tools
- ✅ Google access tokens are short-lived (1 hour), generated on demand, and never stored client-side or server-side
- ✅ The local session token (30 days) only authenticates against the ExtraSuite server — it has no Google API access on its own
- ✅ Google access tokens are never exposed in browser URLs or history
- ✅ Every token request is logged with the command type, context, and the agent's stated reason before any token is issued
- ✅ Delegated scopes (if enabled) are allowlisted by the admin at two levels: server config and Google Workspace Admin Console
- ✅ The client declares the intended operation via a typed command; the server determines the scope — agents cannot request arbitrary scopes

---

## Summary

ExtraSuite's security model is intentionally simple and transparent:

!!! quote "The Security Promise"
    *If an employee does not explicitly share a document with their agent, the agent cannot access it. The agent declares what it intends to do — and why — before receiving any credential. If the agent edits a document, the employee can see exactly what changed — and undo it.*

This design prioritizes **least privilege**, **auditability**, and **employee trust** while staying fully within Google Workspace's native security model.

---

**Related:**

- [FAQ](faq.md)
