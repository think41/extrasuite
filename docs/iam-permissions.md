# IAM Permissions Reference

This document lists all IAM permissions required by the ExtraSuite server.

## Cloud Run Service Account Permissions

The service account running the ExtraSuite server needs the following roles:

### 1. Firestore Access

**Role:** `roles/datastore.user`

**Purpose:** Read and write session data and user credentials in Firestore.

**Permissions included:**
- `datastore.entities.create`
- `datastore.entities.get`
- `datastore.entities.update`
- `datastore.entities.delete`

**Grant command:**
```bash
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:extrasuite-server@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/datastore.user"
```

### 2. Service Account Administration

**Role:** `roles/iam.serviceAccountAdmin`

**Purpose:** Create service accounts for users during first authentication.

**Permissions included:**
- `iam.serviceAccounts.create`
- `iam.serviceAccounts.get`
- `iam.serviceAccounts.list`
- `iam.serviceAccounts.getIamPolicy`
- `iam.serviceAccounts.setIamPolicy`

**Grant command:**
```bash
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:extrasuite-server@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountAdmin"
```

### 3. Token Creation (Impersonation)

**Role:** `roles/iam.serviceAccountTokenCreator`

**Purpose:** Generate short-lived access tokens by impersonating user service accounts.

**Permissions included:**
- `iam.serviceAccounts.generateAccessToken`
- `iam.serviceAccounts.generateIdToken`

**Grant command:**
```bash
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:extrasuite-server@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountTokenCreator"
```

### 4. Secret Manager Access (if using secrets)

**Role:** `roles/secretmanager.secretAccessor`

**Purpose:** Read secrets for OAuth credentials and signing keys.

**Grant command (per secret):**
```bash
gcloud secrets add-iam-policy-binding $SECRET_NAME \
  --member="serviceAccount:extrasuite-server@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

## End-User Permissions (Important!)

**End users do NOT need any GCP project access or IAM roles to use ExtraSuite.**

This is a common point of confusion. Here's why users don't need project membership:

### How It Works

1. **User authenticates** via Google OAuth (requests `cloud-platform` scope)
2. **Server creates a service account** for the user using its own credentials (ADC)
3. **Server grants IAM binding** directly to the user's email address:
   ```
   user:john@example.com → roles/iam.serviceAccountTokenCreator
   ```
   This binding is on the specific service account, not the project.
4. **Server impersonates the SA** using the user's OAuth credentials to generate a token

### Key Insight

In GCP IAM, you can grant permissions to **any Google account** (`user:email@domain.com`), even if they're not a member of the project. The permission is scoped to a specific service account resource.

### What End Users Need

| Requirement | Needed? | Notes |
|-------------|---------|-------|
| GCP Project membership | **No** | IAM bindings work with any Google account |
| GCP Console access | **No** | Users never interact with GCP directly |
| Any project-level IAM roles | **No** | Permissions are per-SA, granted automatically |
| Google Workspace account | **Yes** | For OAuth authentication |

### For Organization Rollout

To enable all employees (e.g., `all@example.com`) to use ExtraSuite:

1. **Configure domain allowlist** on the server:
   ```bash
   ALLOWED_EMAIL_DOMAINS=example.com
   ```

2. **Grant server permissions** (see sections above)

3. **Share Google Workspace resources** with the created service accounts (e.g., share a Google Sheet with `ea-john@project.iam.gserviceaccount.com`)

That's it. No IAM configuration needed for the user group.

## User Service Account Permissions

When ExtraSuite creates a service account for a user, it also grants the user permission to impersonate it:

**Role granted to user:** `roles/iam.serviceAccountTokenCreator`

**Resource:** The user's service account

This allows users to use tools like `gcloud` to generate tokens independently if needed.

## OAuth Scopes

### Server OAuth Scopes

The server uses Application Default Credentials with:
- `https://www.googleapis.com/auth/cloud-platform` - For IAM and Firestore operations

### User OAuth Scopes (during authentication)

Users are prompted to grant:
- `openid` - OpenID Connect
- `https://www.googleapis.com/auth/userinfo.email` - Email address
- `https://www.googleapis.com/auth/userinfo.profile` - Profile info
- `https://www.googleapis.com/auth/cloud-platform` - For impersonation

### Service Account Token Scopes (returned to CLI)

The short-lived tokens include:
- `https://www.googleapis.com/auth/spreadsheets` - Google Sheets access
- `https://www.googleapis.com/auth/drive.readonly` - Google Drive read access
- `https://www.googleapis.com/auth/documents.readonly` - Google Docs read access

## Least Privilege Recommendations

For production environments:

1. **Use separate projects** for ExtraSuite infrastructure and user service accounts if needed for compliance

2. **Restrict token creator scope** to specific service accounts if possible:
   ```bash
   # Instead of project-level, grant on specific SA
   gcloud iam service-accounts add-iam-policy-binding \
     ea-username@$PROJECT_ID.iam.gserviceaccount.com \
     --member="serviceAccount:extrasuite-server@$PROJECT_ID.iam.gserviceaccount.com" \
     --role="roles/iam.serviceAccountTokenCreator"
   ```

3. **Audit regularly** using Cloud Audit Logs to monitor:
   - Service account creation events
   - Token generation events
   - Failed authentication attempts

## Summary Table

| Role | Resource | Purpose |
|------|----------|---------|
| `roles/datastore.user` | Project | Read/write Firestore |
| `roles/iam.serviceAccountAdmin` | Project | Create user SAs |
| `roles/iam.serviceAccountTokenCreator` | Project | Impersonate user SAs |
| `roles/secretmanager.secretAccessor` | Specific secrets | Read OAuth config |
