# IAM Permissions Reference

This document lists all IAM permissions required by the ExtraSuite server.

## Cloud Run Service Account

The service account running the ExtraSuite server needs the following roles:

### Firestore Access

**Role:** `roles/datastore.user`

**Purpose:** Read and write session data and user credentials in Firestore.

**Permissions included:**

- `datastore.entities.create`
- `datastore.entities.get`
- `datastore.entities.update`
- `datastore.entities.delete`

```bash
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:extrasuite-server@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/datastore.user"
```

### Service Account Administration

**Role:** `roles/iam.serviceAccountAdmin`

**Purpose:** Create service accounts for users during first authentication.

**Permissions included:**

- `iam.serviceAccounts.create`
- `iam.serviceAccounts.get`
- `iam.serviceAccounts.list`
- `iam.serviceAccounts.getIamPolicy`
- `iam.serviceAccounts.setIamPolicy`

```bash
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:extrasuite-server@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountAdmin"
```

### Token Creation (Impersonation)

**Role:** `roles/iam.serviceAccountTokenCreator`

**Purpose:** Generate short-lived access tokens by impersonating user service accounts.

**Permissions included:**

- `iam.serviceAccounts.generateAccessToken`
- `iam.serviceAccounts.generateIdToken`

```bash
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:extrasuite-server@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountTokenCreator"
```

### Secret Manager Access

**Role:** `roles/secretmanager.secretAccessor`

**Purpose:** Read secrets for OAuth credentials and signing keys.

```bash
gcloud secrets add-iam-policy-binding $SECRET_NAME \
  --member="serviceAccount:extrasuite-server@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

## End-User Permissions

!!! important "Users Do NOT Need GCP Access"
    End users do NOT need any GCP project access or IAM roles to use ExtraSuite.

This is a common point of confusion. Here's why users don't need project membership:

### How It Works

1. **User authenticates** via Google OAuth (only `openid` and `userinfo.email` scopes)
2. **Server creates a service account** for the user using its own credentials (ADC)
3. **Server impersonates the SA** using its own ADC to generate a short-lived token
4. **Token is returned** to the CLI for use with Google Workspace APIs

The server acts as a trusted intermediary. Users only need to prove their identity - they don't need any GCP permissions.

### What End Users Need

| Requirement | Needed? | Notes |
|-------------|---------|-------|
| GCP Project membership | **No** | IAM bindings work with any Google account |
| GCP Console access | **No** | Users never interact with GCP directly |
| Any project-level IAM roles | **No** | Permissions are per-SA, granted automatically |
| Google Workspace account | **Yes** | For OAuth authentication |

### Organization Rollout

To enable all employees to use ExtraSuite:

1. **Configure domain allowlist** on the server:
   ```bash
   ALLOWED_EMAIL_DOMAINS=example.com
   ```

2. **Grant server permissions** (see sections above)

3. **Share Google Workspace resources** with the created service accounts

That's it. No IAM configuration needed for the user group.

## OAuth Scopes

### Server OAuth Scopes

The server uses Application Default Credentials with:

- `https://www.googleapis.com/auth/cloud-platform` - For IAM and Firestore operations

### User OAuth Scopes (Authentication)

Users are prompted to grant minimal scopes for identity verification only:

- `openid` - OpenID Connect
- `https://www.googleapis.com/auth/userinfo.email` - Email address

!!! note "No Cloud Access"
    Users do NOT grant `cloud-platform` scope. The server uses its own credentials for all IAM operations.

### Service Account Token Scopes

The short-lived tokens include:

- `https://www.googleapis.com/auth/spreadsheets` - Google Sheets read/write
- `https://www.googleapis.com/auth/documents` - Google Docs read/write
- `https://www.googleapis.com/auth/presentations` - Google Slides read/write
- `https://www.googleapis.com/auth/drive.readonly` - Google Drive read access

## Cloud Build Service Account

For CI/CD deployments, create a dedicated service account with least privileges:

### Artifact Registry Access

**Role:** `roles/artifactregistry.writer`

**Purpose:** Push Docker images to Container Registry.

```bash
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:extrasuite-cloudbuild@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/artifactregistry.writer" \
  --condition=None
```

### Cloud Run Deployment

**Role:** `roles/run.admin`

**Purpose:** Deploy Cloud Run services and set IAM policies.

```bash
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:extrasuite-cloudbuild@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/run.admin" \
  --condition=None
```

### Service Account User

**Role:** `roles/iam.serviceAccountUser` (on runtime SA only)

**Purpose:** Deploy Cloud Run services using the runtime service account.

```bash
gcloud iam service-accounts add-iam-policy-binding \
  extrasuite-server@$PROJECT_ID.iam.gserviceaccount.com \
  --member="serviceAccount:extrasuite-cloudbuild@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountUser"
```

### Logging

**Role:** `roles/logging.logWriter`

**Purpose:** Write Cloud Build logs.

```bash
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:extrasuite-cloudbuild@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/logging.logWriter" \
  --condition=None
```

!!! note "Condition Flag"
    The `--condition=None` flag is required if the project has existing IAM bindings with conditions.

## Summary Tables

### Runtime Service Account (`extrasuite-server`)

| Role | Resource | Purpose |
|------|----------|---------|
| `roles/datastore.user` | Project | Read/write Firestore |
| `roles/iam.serviceAccountAdmin` | Project | Create user SAs |
| `roles/iam.serviceAccountTokenCreator` | Project | Impersonate user SAs |
| `roles/secretmanager.secretAccessor` | Specific secrets | Read OAuth config |

### Cloud Build Service Account (`extrasuite-cloudbuild`)

| Role | Resource | Purpose |
|------|----------|---------|
| `roles/artifactregistry.writer` | Project | Push Docker images |
| `roles/run.admin` | Project | Deploy to Cloud Run & set IAM |
| `roles/iam.serviceAccountUser` | Runtime SA | Act as runtime SA |
| `roles/logging.logWriter` | Project | Write build logs |

## Least Privilege Recommendations

For production environments:

1. **Use separate projects** for ExtraSuite infrastructure and user service accounts if needed for compliance

2. **Restrict token creator scope** to specific service accounts if possible:
   ```bash
   gcloud iam service-accounts add-iam-policy-binding \
     username-ex@$PROJECT_ID.iam.gserviceaccount.com \
     --member="serviceAccount:extrasuite-server@$PROJECT_ID.iam.gserviceaccount.com" \
     --role="roles/iam.serviceAccountTokenCreator"
   ```

3. **Audit regularly** using Cloud Audit Logs to monitor:
   - Service account creation events
   - Token generation events
   - Failed authentication attempts
