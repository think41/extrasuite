# Security Model – Extrasuite

Extrasuite is designed to make automated agents useful **without removing control from employees**.
This document explains what that means in practice, both from an employee perspective and from a security / CISO perspective.

---

## Security constants

| Constant | Value | Description |
|----------|-------|-------------|
| `ACCESS_TOKEN_TTL` | 1 hour (3600 seconds) | Lifetime of issued service account access tokens |
| `AUTH_CODE_TTL` | 120 seconds | Lifetime of temporary auth codes for token exchange |
| `OAUTH_STATE_TTL` | 10 minutes | Lifetime of OAuth state tokens for CSRF protection |
| `TOKEN_DIR_PERMISSIONS` | `0700` | Directory permissions for token cache (owner rwx only) |
| `TOKEN_FILE_PERMISSIONS` | `0600` | File permissions for cached tokens (owner rw only) |
| `DEFAULT_SA_QUOTA` | 100 | Default GCP service account quota per project |

---

## What this means for employees (non-normative)

Extrasuite agents can only access what **you explicitly share** with them.

Each employee is assigned a dedicated virtual agent with its own email address. If you share a Google Doc or Google Sheet with your agent's email address, the agent can access **only that document**, and only with the permission level you choose (view, comment, or edit). If you do not share a document with your agent, the agent cannot access it.

You remain in control at all times:
- You can **revoke access instantly** by removing the agent from the document's sharing settings in Google Drive.
- Any edits made by the agent appear clearly in **version history**, under the agent's identity.
- You can review exactly what changed and **undo** the agent's edits at any time using Google Docs or Sheets' built-in version controls.

Extrasuite does not grant access on your behalf and does not bypass Google Workspace permissions.

---

## Security model (for security, IT, and compliance teams)

### High-level design

Extrasuite assigns a **dedicated Google service account per employee**, representing that employee's virtual agent.

Employees explicitly share documents with their agent's service account email address using standard Google Drive sharing.
This creates a clear, auditable, least-privilege access boundary that is enforced by Google Workspace itself.

When the agent needs to act, Extrasuite issues **short-lived OAuth access tokens (`ACCESS_TOKEN_TTL`)** for that specific service account using **service account impersonation** via Google Cloud IAM.

No long-lived service account keys are used or distributed.

---

### Identity and access control

- **One service account per employee**
  - Each service account represents exactly one employee's agent.
  - Service accounts have no default permissions.
  - Access exists only when an employee explicitly shares a document with their agent.

- **Explicit, user-controlled authorization**
  - Employees control access using standard Google Drive sharing.
  - Read, comment, and edit permissions are defined by the employee.
  - Access can be revoked immediately via Google Drive.

- **No inherited or transitive access**
  - Agent access is not inherited from document collaborators.
  - If an employee does not explicitly share a document with their agent, the agent cannot access it.

- **Email domain allowlist**
  - Organizations can restrict authentication to specific email domains.
  - Users outside the allowed domains cannot authenticate, even with valid Google accounts.
  - This prevents unauthorized users from creating service accounts in the project.

---

### Token issuance and credential handling

- **Token broker architecture**
  - A backend "token broker" service account (running on Cloud Run) issues short-lived access tokens.
  - The broker holds `roles/iam.serviceAccountTokenCreator` at the project level, allowing it to impersonate any service account it creates.
  - The broker uses Application Default Credentials (ADC), not user OAuth credentials.
  - End users do not impersonate service accounts directly.

- **Short-lived credentials only**
  - Agents receive OAuth access tokens that expire after `ACCESS_TOKEN_TTL`.
  - Tokens cannot be refreshed by the agent and must be reissued by the broker.

- **No private key material**
  - Extrasuite does not use downloaded service account key files.
  - No private keys or long-lived credentials are exposed to agents or clients.

- **Scoped Workspace access**
  - Issued tokens are scoped only to the required Google Workspace APIs:
    - Google Sheets (read/write)
    - Google Docs (read/write)
    - Google Slides (read/write)
    - Google Drive (read-only)
  - Extrasuite does not issue broad Google Cloud API permissions.

---

### CLI authentication flow

- **Auth code exchange pattern**
  - Tokens are never exposed in browser URLs or history.
  - Server generates a temporary auth code (valid for `AUTH_CODE_TTL`) and redirects the browser to the CLI with only the auth code.
  - CLI exchanges the auth code for the token via a POST request to `/api/token/exchange`.
  - Auth codes are single-use and deleted immediately upon exchange.

- **Localhost binding**
  - The CLI callback server binds to `127.0.0.1` (not `localhost`) to prevent DNS rebinding attacks.
  - Only the local machine can receive the auth code callback.

- **Secure token storage**
  - Cached tokens are stored with restrictive file permissions:
    - Directory: `TOKEN_DIR_PERMISSIONS` (owner read/write/execute only)
    - Token file: `TOKEN_FILE_PERMISSIONS` (owner read/write only)
  - This prevents other users on multi-user systems from reading token files.

---

### Server-side data storage

- **Minimal data retention**
  - The server stores only the email-to-service-account mapping in Firestore.
  - No OAuth access tokens or refresh tokens are stored server-side.
  - Session cookies are signed and stateless (contain only the user email).

- **OAuth state tokens**
  - Temporary state tokens for CSRF protection expire after `OAUTH_STATE_TTL`.
  - State tokens are one-time use and deleted after consumption.

- **Auth codes**
  - Temporary auth codes for token exchange expire after `AUTH_CODE_TTL`.
  - Auth codes are one-time use and deleted immediately upon exchange.
  - Only the service account email is stored with the auth code; tokens are generated on-demand during exchange.

---

### Auditability and transparency

- **Clear edit attribution**
  - All edits appear in Google Docs and Sheets version history under the agent's service account identity.
  - There is no shared or ambiguous editor identity.

- **Native rollback**
  - Employees can inspect changes and revert them using Google's built-in version history.
  - Extrasuite does not replace or override Google Workspace revision controls.

- **Separation of responsibilities**
  - Authorization is enforced by Google Workspace sharing.
  - Authentication and token issuance are enforced by Google Cloud IAM.
  - Extrasuite coordinates these systems but does not override either.

- **Server-side logging**
  - Token generation events are logged with user email and service account.
  - Authentication failures are logged for security monitoring.

---

### Limitations and non-goals

- **Agent behavior is out of scope**
  - Once a document is shared, what the agent does with that access (logic, prompts, models, workflows) is outside the scope of this security model.
  - Extrasuite ensures *who* can access *what*, not *how* an agent decides to modify content.

- **No prevention of intentional misuse**
  - If an employee grants edit access, the agent can edit within that permission.
  - Extrasuite does not attempt to restrict legitimate user-directed actions.

- **Service account lifecycle**
  - Extrasuite relies on one service account per employee.
  - Organizations are responsible for appropriate lifecycle management, including offboarding and cleanup of inactive agents.
  - GCP projects have a default quota of `DEFAULT_SA_QUOTA` service accounts (can be increased).

---

## Security guarantees

Extrasuite guarantees the following:

- Agents cannot access documents unless an employee explicitly shares them.
- Access is limited to the permission level chosen by the employee.
- All agent edits are attributable, auditable, and reversible using native Google Workspace tools.
- No long-lived credentials are exposed to agents or clients.
- Tokens are never exposed in browser URLs or history (auth code exchange pattern).

---

## Summary

Extrasuite's security model is intentionally simple and transparent:

> *If an employee does not explicitly share a document with their agent, the agent cannot access it.
> If the agent edits a document, the employee can see exactly what changed — and undo it.*

This design prioritizes least privilege, auditability, and employee trust while staying fully within Google Workspace's native security model.
