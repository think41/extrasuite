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

**Short-lived credentials only:**

- Agents receive OAuth access tokens that expire after **1 hour**
- Tokens cannot be refreshed by the agent
- Must be reissued by the server

**No private key material:**

- ExtraSuite does not use downloaded service account key files
- No private keys or long-lived credentials are exposed to agents or clients

**Scoped Workspace access:**

Issued tokens are scoped only to required Google Workspace APIs:

| API | Permission |
|-----|------------|
| Google Sheets | Read/Write |
| Google Docs | Read/Write |
| Google Slides | Read/Write |
| Google Drive | **Read-only** |

ExtraSuite does not issue broad Google Cloud API permissions.

### CLI Authentication Flow

**Auth code exchange pattern:**

- Tokens are never exposed in browser URLs or history
- Server generates a temporary auth code (valid for 2 minutes)
- CLI exchanges the auth code for the token via POST request
- Auth codes are single-use and deleted immediately

**Localhost binding:**

- The CLI callback server binds to `127.0.0.1` (not `localhost`)
- Prevents DNS rebinding attacks
- Only the local machine can receive the auth code

**Secure token storage:**

- Cached tokens are stored with restrictive file permissions
- Directory: owner read/write/execute only (0700)
- Token file: owner read/write only (0600)

### Server-Side Data

**Minimal data retention:**

- The server stores only the email-to-service-account mapping
- No OAuth access tokens are stored server-side
- Session cookies are signed and stateless

**Automatic expiration:**

| Data Type | Lifetime |
|-----------|----------|
| Access tokens | 1 hour |
| Auth codes | 2 minutes |
| OAuth state tokens | 10 minutes |

---

## Security Constants

| Constant | Value | Description |
|----------|-------|-------------|
| `ACCESS_TOKEN_TTL` | 1 hour | Lifetime of issued access tokens |
| `AUTH_CODE_TTL` | 2 minutes | Lifetime of temporary auth codes |
| `OAUTH_STATE_TTL` | 10 minutes | Lifetime of OAuth state tokens |
| `TOKEN_DIR_PERMISSIONS` | `0700` | Directory permissions for token cache |
| `TOKEN_FILE_PERMISSIONS` | `0600` | File permissions for cached tokens |

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
- ✅ No long-lived credentials are exposed to agents or clients
- ✅ Tokens are never exposed in browser URLs or history

---

## Summary

ExtraSuite's security model is intentionally simple and transparent:

!!! quote "The Security Promise"
    *If an employee does not explicitly share a document with their agent, the agent cannot access it. If the agent edits a document, the employee can see exactly what changed — and undo it.*

This design prioritizes **least privilege**, **auditability**, and **employee trust** while staying fully within Google Workspace's native security model.

---

**Related:**

- [Privacy Policy](legal/privacy.md)
- [Terms of Service](legal/terms.md)
- [FAQ](faq.md)
