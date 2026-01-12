# IAM Permissions Reference

This document lists all IAM permissions required by the Google Workspace Gateway server.

## Cloud Run Service Account Permissions

The service account running the GWG server needs the following roles:

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
  --member="serviceAccount:gwg-server@$PROJECT_ID.iam.gserviceaccount.com" \
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
  --member="serviceAccount:gwg-server@$PROJECT_ID.iam.gserviceaccount.com" \
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
  --member="serviceAccount:gwg-server@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountTokenCreator"
```

### 4. Secret Manager Access (if using secrets)

**Role:** `roles/secretmanager.secretAccessor`

**Purpose:** Read secrets for OAuth credentials and signing keys.

**Grant command (per secret):**
```bash
gcloud secrets add-iam-policy-binding $SECRET_NAME \
  --member="serviceAccount:gwg-server@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

## User Service Account Permissions

When GWG creates a service account for a user, it also grants the user permission to impersonate it:

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

1. **Use separate projects** for GWG infrastructure and user service accounts if needed for compliance

2. **Restrict token creator scope** to specific service accounts if possible:
   ```bash
   # Instead of project-level, grant on specific SA
   gcloud iam service-accounts add-iam-policy-binding \
     ea-username@$PROJECT_ID.iam.gserviceaccount.com \
     --member="serviceAccount:gwg-server@$PROJECT_ID.iam.gserviceaccount.com" \
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
