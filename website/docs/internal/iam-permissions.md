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

1. **User authenticates** via Google OAuth (only `openid` and `userinfo.email` scopes)
2. **Server creates a service account** for the user using its own credentials (ADC)
3. **Server impersonates the SA** using its own ADC to generate a short-lived token
4. **Token is returned** to the CLI for use with Google Workspace APIs

**Key design:** The server uses its own Application Default Credentials (as Cloud Run's service account) to impersonate all user service accounts. Users only need to prove their identity - they don't need any GCP permissions. No per-user IAM bindings are created.

### Key Insight

The server acts as a trusted intermediary. It has project-level permission to impersonate any service account it creates. Users authenticate to prove their identity, but never receive direct GCP permissions.

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

3. **Share Google Workspace resources** with the created service accounts (e.g., share a Google Sheet with `john-ex@project.iam.gserviceaccount.com` where `ex` is the domain abbreviation)

That's it. No IAM configuration needed for the user group.

## User Service Account Naming

When ExtraSuite creates a service account for a user, it names the SA using the format `{local-part}-{domain-abbrev}` (e.g., `john-ex` for `john@example.com` with abbreviation `ex`).

**Note:** Users do not receive direct IAM permissions on their service account. All token generation goes through the ExtraSuite server.

## OAuth Scopes

### Server OAuth Scopes

The server uses Application Default Credentials with:
- `https://www.googleapis.com/auth/cloud-platform` - For IAM and Firestore operations

### User OAuth Scopes (during authentication)

Users are prompted to grant minimal scopes for identity verification only:
- `openid` - OpenID Connect
- `https://www.googleapis.com/auth/userinfo.email` - Email address

**Note:** Users do NOT grant `cloud-platform` scope. The server uses its own credentials (ADC) for all IAM operations and impersonation.

### Service Account Token Scopes (returned to CLI)

The short-lived tokens include:
- `https://www.googleapis.com/auth/spreadsheets` - Google Sheets read/write
- `https://www.googleapis.com/auth/documents` - Google Docs read/write
- `https://www.googleapis.com/auth/presentations` - Google Slides read/write
- `https://www.googleapis.com/auth/drive.readonly` - Google Drive read access

## Least Privilege Recommendations

For production environments:

1. **Use separate projects** for ExtraSuite infrastructure and user service accounts if needed for compliance

2. **Restrict token creator scope** to specific service accounts if possible:
   ```bash
   # Instead of project-level, grant on specific SA
   gcloud iam service-accounts add-iam-policy-binding \
     username-ex@$PROJECT_ID.iam.gserviceaccount.com \
     --member="serviceAccount:extrasuite-server@$PROJECT_ID.iam.gserviceaccount.com" \
     --role="roles/iam.serviceAccountTokenCreator"
   ```

3. **Audit regularly** using Cloud Audit Logs to monitor:
   - Service account creation events
   - Token generation events
   - Failed authentication attempts

## Summary Table

### Runtime Service Account (`extrasuite-server`)

| Role | Resource | Purpose |
|------|----------|---------|
| `roles/datastore.user` | Project | Read/write Firestore |
| `roles/iam.serviceAccountAdmin` | Project | Create user SAs |
| `roles/iam.serviceAccountTokenCreator` | Project | Impersonate user SAs |
| `roles/secretmanager.secretAccessor` | Specific secrets | Read OAuth config |
