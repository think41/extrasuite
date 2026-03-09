# IAM Permissions Reference

This reference document explains the IAM roles and permissions required by ExtraSuite.

## Summary

ExtraSuite requires **one service account** (`extrasuite-server`). Required roles vary by credential mode:

| Role | `sa+dwd` | `sa+oauth` | `oauth` | Purpose |
|------|----------|------------|---------|---------|
| `roles/datastore.user` | ✅ | ✅ | ✅ | Read/write Firestore (sessions, user records) |
| `roles/iam.serviceAccountAdmin` | ✅ | ✅ | — | Create per-user agent service accounts |
| `roles/iam.serviceAccountTokenCreator` | ✅ | ✅ | — | Generate tokens by impersonating user service accounts |
| `roles/secretmanager.secretAccessor` | ✅ | ✅ | ✅ | Read OAuth credentials and secret key (per-secret binding) |

In `oauth` mode, no per-user service accounts are created. Only Firestore access and Secret Manager access are needed.

## Role Details

### Cloud Datastore User (`roles/datastore.user`)

**What it does:** Allows ExtraSuite to store and retrieve user records and session data in Firestore.

**Scope:** Project-level binding

**Why needed:** When a user logs in, ExtraSuite stores their email and service account email in Firestore. This data persists across sessions.

---

### Service Account Admin (`roles/iam.serviceAccountAdmin`)

**What it does:** Allows ExtraSuite to create, update, and delete service accounts.

**Scope:** Project-level binding

**Why needed:** ExtraSuite creates a dedicated service account for each user on first login (e.g., `john-ex@project.iam.gserviceaccount.com`). This role permits creating these accounts.

**Security note:** While this sounds like a powerful role, it is safe because **creating a service account is separate from granting it permissions**.

`serviceAccountAdmin` allows:

- ✓ Creating service accounts
- ✓ Updating metadata (display name, description)
- ✓ Deleting service accounts
- ✗ Granting IAM roles to service accounts
- ✗ Modifying project IAM policies

To grant any IAM role to a service account, you need `roles/resourcemanager.projectIamAdmin` or specific `setIamPolicy` permissions—which ExtraSuite does not have.

**The service accounts ExtraSuite creates have zero IAM roles.** They cannot access any GCP resources (BigQuery, Cloud Storage, Compute, etc.). They can only access Google Workspace files (Sheets, Docs, Slides) that users explicitly share with them.

---

### Service Account Token Creator (`roles/iam.serviceAccountTokenCreator`)

**What it does:** Allows ExtraSuite to generate short-lived access tokens by impersonating user service accounts.

**Scope:** Project-level binding

**Why needed:** When the CLI requests a token, ExtraSuite impersonates the user's service account to create a time-limited OAuth token. This is the core functionality that makes ExtraSuite work.

**Security note:** Tokens are short-lived (default: 60 minutes) and scoped to Google Workspace APIs only.

---

### Secret Manager Secret Accessor (`roles/secretmanager.secretAccessor`)

**What it does:** Allows ExtraSuite to read specific secrets.

**Scope:** Secret-level binding (not project-level)

**Why needed:** ExtraSuite reads three secrets at startup:

- `extrasuite-client-id` - OAuth Client ID
- `extrasuite-client-secret` - OAuth Client Secret
- `extrasuite-secret-key` - Session signing key

**Security note:** This role is granted only on specific secrets, not all secrets in the project.

---

## End Users Do NOT Need GCP Access

A common misconception is that end users need GCP permissions. They do not.

| Requirement | Needed? |
|-------------|---------|
| GCP project membership | No |
| GCP Console access | No |
| Any IAM roles | No |
| Google Workspace/Gmail account | Yes |

**How it works:**

1. User proves their identity via Google OAuth (only email scope)
2. ExtraSuite uses its own credentials to create the user's service account
3. ExtraSuite generates tokens using its own permissions
4. User receives tokens without ever touching GCP

---

## OAuth Scopes

### User Authentication Scopes

In `sa+dwd` mode, users grant only:

- `openid` — Standard OpenID Connect
- `userinfo.email` — Access to email address

In `sa+oauth` and `oauth` modes, users also grant the workspace scopes configured in `OAUTH_SCOPES` (e.g., Gmail, Calendar). See [Deployment Guide: Step 3](cloud-run.md#step-3-configure-google-oauth) for scope configuration.

Users never grant `cloud-platform` or any GCP-level scopes.

### Service Account Token Scopes

Short-lived tokens issued to agents are scoped to Google Workspace APIs only:

- `https://www.googleapis.com/auth/drive.file` — Drive files shared with the agent
- `https://www.googleapis.com/auth/spreadsheets` — Google Sheets
- `https://www.googleapis.com/auth/documents` — Google Docs
- `https://www.googleapis.com/auth/presentations` — Google Slides

In `sa+oauth`/`oauth` modes, user-impersonating commands (Gmail, Calendar) use the stored OAuth refresh token to obtain scoped access tokens rather than service account tokens.

---

## Least Privilege Considerations

The default setup grants project-level permissions for simplicity. For stricter security:

### Option 1: Separate Projects

Use one project for ExtraSuite infrastructure and another for user service accounts. This isolates user service accounts from the ExtraSuite server.

### Option 2: Conditional Token Creator

Instead of project-level `serviceAccountTokenCreator`, grant it only on specific service accounts:

```bash
gcloud iam service-accounts add-iam-policy-binding \
  USERNAME-ABBR@PROJECT.iam.gserviceaccount.com \
  --member="serviceAccount:extrasuite-server@PROJECT.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountTokenCreator"
```

This requires updating bindings each time a new user is onboarded.

---

## Domain-Wide Delegation (`sa+dwd` mode)

Domain-wide delegation allows the ExtraSuite server to impersonate users for Gmail, Calendar, and Apps Script. This is only relevant in `sa+dwd` mode and requires a Google Workspace admin.

**Setup instructions:** See [Deployment Guide: Step 7 (sa+dwd only)](cloud-run.md#step-7-sadwd-only-configure-domain-wide-delegation).

**Security note:** The Admin Console DWD configuration is the authoritative enforcement point. The server-side `DELEGATION_SCOPES` env var provides an optional second layer that rejects requests before they reach Google.

---

## Audit Logging

Enable Cloud Audit Logs to monitor ExtraSuite activity:

- **Admin Activity logs** (always on): Service account creation
- **Data Access logs** (must enable): Token generation, Firestore reads

View logs in Cloud Logging:

```bash
gcloud logging read 'protoPayload.serviceName="iam.googleapis.com"' \
  --project=$PROJECT_ID \
  --limit=20
```
