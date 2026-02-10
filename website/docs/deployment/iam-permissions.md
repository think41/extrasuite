# IAM Permissions Reference

This reference document explains the IAM roles and permissions required by ExtraSuite.

## Summary

ExtraSuite requires **one service account** (`extrasuite-server`) with **four roles**:

| Role | Purpose |
|------|---------|
| `roles/datastore.user` | Read/write user records in Firestore |
| `roles/iam.serviceAccountAdmin` | Create service accounts for each user |
| `roles/iam.serviceAccountTokenCreator` | Generate short-lived access tokens |
| `roles/secretmanager.secretAccessor` | Read OAuth credentials and secret key |

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

When users log in to ExtraSuite, they grant only:

- `openid` - Standard OpenID Connect
- `userinfo.email` - Access to email address

Users do NOT grant `cloud-platform` or any Google Workspace scopes during login.

### Service Account Token Scopes

The short-lived tokens issued to AI agents include:

- `https://www.googleapis.com/auth/drive.readonly` - Read Google Drive files
- `https://www.googleapis.com/auth/spreadsheets` - Read/write Google Sheets
- `https://www.googleapis.com/auth/documents` - Read/write Google Docs
- `https://www.googleapis.com/auth/presentations` - Read/write Google Slides

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

## Optional: Domain-Wide Delegation

Domain-wide delegation is only needed if you want agents to access user-specific APIs like Gmail, Calendar, or Apps Script. It uses the same `extrasuite-server` service account — no new service account is needed.

### Prerequisites

- The `extrasuite-server` SA already has `roles/iam.serviceAccountTokenCreator` (from the base setup)
- A Google Workspace domain with admin console access

### Configure in Google Workspace Admin Console

1. Go to **Admin Console** → **Security** → **Access and data control** → **API Controls** → **Domain-wide Delegation**
2. Click **Add new**
3. **Client ID:** Enter the OAuth client ID of your `extrasuite-server` service account (find it in IAM & Admin → Service Accounts → click the SA → Details → Unique ID)
4. **OAuth scopes:** Add the scopes you want to allow, comma-separated:
   ```
   https://www.googleapis.com/auth/gmail.send,https://www.googleapis.com/auth/calendar,https://www.googleapis.com/auth/script.projects
   ```
5. Click **Authorize**

### Configure ExtraSuite Server

Enable delegation and optionally restrict scopes:

```bash
gcloud run services update extrasuite-server \
  --region=asia-southeast1 \
  --update-env-vars="DELEGATION_ENABLED=true,DELEGATION_SCOPES=gmail.send,calendar,script.projects" \
  --project=$PROJECT_ID
```

- `DELEGATION_ENABLED=true` activates the delegation endpoints
- `DELEGATION_SCOPES` (optional) restricts which scopes clients can request — an additional layer on top of Workspace Admin Console enforcement
- If `DELEGATION_SCOPES` is omitted, any scope is allowed (Workspace Admin Console is the sole enforcement)

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
