# Operations Runbook

This document captures operational knowledge and lessons learned from deploying and operating ExtraSuite.

## Deployment Configuration

### Current Deployment

| Component | Value |
|-----------|-------|
| Project ID | `thinker41` |
| Region | `asia-southeast1` (Singapore) |
| Cloud Run Service | `extrasuite` |
| Service URL | `https://extrasuite.think41.com` |
| Custom Domain | `extrasuite.think41.com` |
| Firestore Database | `(default)` in `asia-southeast1` |
| Service Account | `extrasuite-server@thinker41.iam.gserviceaccount.com` |

### Domain Configuration

| Domain | Abbreviation | Purpose |
|--------|--------------|---------|
| think41.com | `t41` | Primary domain |
| recruit41.com | `r41` | Recruitment platform |
| mindlap.dev | `mlap` | Development domain |

Service accounts are named: `{username}-{domain_abbrev}@thinker41.iam.gserviceaccount.com`

Example: `sripathi-t41@thinker41.iam.gserviceaccount.com` for `sripathi@think41.com`

## Common Issues and Solutions

### 1. OAuth Scopes Showing Too Many Permissions

**Symptom:** OAuth consent screen asks for "See, edit, configure and delete your Google Cloud data" instead of just email access.

**Cause:** Using `include_granted_scopes="true"` in the OAuth flow causes Google to include any previously granted scopes from the same OAuth client.

**Solution:** Remove `include_granted_scopes` from the authorization URL. Users may need to revoke existing app permissions at https://myaccount.google.com/permissions before re-authenticating.

**Code location:** `extrasuite_server/api.py` in `start_token_auth()`

### 2. OAuth Callback Returns 500 Error with Scope Warning

**Symptom:**
```
Warning: Scope has changed from "openid userinfo.email" to "openid userinfo.email cloud-platform..."
```

**Cause:** The `oauthlib` library raises a Warning (treated as exception) when the scopes returned by Google don't match what was requested.

**Solution:** Same as above - remove `include_granted_scopes` parameter.

### 3. Firestore "No document to update" Error

**Symptom:**
```
NotFound: 404 No document to update: projects/thinker41/databases/(default)/documents/users/email@domain.com
```

**Cause:** Using Firestore `update()` method on a document that doesn't exist. This happens for new users in a fresh database.

**Solution:** Use `set(merge=True)` instead of `update()` for upsert behavior.

**Code location:** `extrasuite_server/database.py` in `update_service_account_email()`

### 4. Email Domain Allowlist Not Working

**Symptom:** Valid email domains are rejected. Logs show domains as a single semicolon-separated string:
```
"allowed_domains": ["think41.com;recruit41.com;mindlap.dev"]
```

**Cause:** The gcloud CLI interprets commas as value separators. Using semicolons to avoid this doesn't work because the code expects comma-separated values.

**Solution:** Use gcloud's alternate delimiter syntax:
```bash
gcloud run services update extrasuite \
  --update-env-vars='^@^ALLOWED_EMAIL_DOMAINS=think41.com,recruit41.com,mindlap.dev'
```

The `^@^` prefix changes the delimiter to `@` instead of `,`.

### 5. Firestore Database Recreation Delay

**Symptom:** After deleting a Firestore database, attempting to recreate it immediately fails:
```
FAILED_PRECONDITION: Database ID '(default)' is not available. Please retry in X seconds.
```

**Cause:** Firestore requires a cooldown period (~4-5 minutes) after database deletion.

**Solution:** Wait for the cooldown period before recreating. The error message indicates how long to wait.

### 6. Custom Domain SSL Certificate Pending

**Symptom:** Custom domain (e.g., `extrasuite.think41.com`) doesn't work. HTTPS connection fails with SSL errors.

**Cause:** Google-managed SSL certificates take 15-30 minutes to provision after DNS is configured.

**Diagnosis:**
```bash
# Check domain mapping status
gcloud beta run domain-mappings describe \
  --domain=extrasuite.think41.com \
  --region=asia-southeast1 \
  --project=thinker41 \
  --format="yaml(status.conditions)"

# Verify DNS is correct
dig extrasuite.think41.com CNAME +short
# Should return: ghs.googlehosted.com.
```

**Solution:** Wait for certificate provisioning. When `CertificateProvisioned` condition shows `status: 'True'`, HTTPS will work.

**Note:** HTTP works immediately (redirects to HTTPS), but HTTPS requires the certificate.

### 7. IAM Policy Binding Fails Without --condition=None

**Symptom:**
```
ERROR: Adding a binding without specifying a condition to a policy containing conditions is prohibited
```

**Cause:** The project has existing IAM bindings with conditions. gcloud requires explicit `--condition=None` when adding unconditional bindings.

**Solution:** Add `--condition=None` to the command:
```bash
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:sa@project.iam.gserviceaccount.com" \
  --role="roles/some.role" \
  --condition=None
```

## CI/CD Configuration

### Cloud Build Trigger

Automatic deployments are configured via Cloud Build:

| Setting | Value |
|---------|-------|
| Trigger Name | `extrasuite-deploy-main` |
| Repository | `think41/extrasuite` |
| Branch | `^main$` |
| Config File | `extrasuite-server/cloudbuild.yaml` |
| Service Account | `extrasuite-cloudbuild@thinker41.iam.gserviceaccount.com` |

**How it works:** Push to `main` branch triggers automatic build and deployment to Cloud Run.

### Cloud Build Service Account Permissions

The `extrasuite-cloudbuild` service account has these permissions:

| Role | Resource | Purpose |
|------|----------|---------|
| `roles/artifactregistry.writer` | Project | Push images to GCR |
| `roles/run.admin` | Project | Deploy to Cloud Run & set IAM |
| `roles/logging.logWriter` | Project | Write build logs |
| `roles/iam.serviceAccountUser` | Runtime SA | Act as `extrasuite-server` |

### View Build Status

```bash
# List recent builds
gcloud builds list --project=thinker41 --limit=5

# View specific build logs
gcloud builds log BUILD_ID --project=thinker41

# Stream logs for running build
gcloud builds log BUILD_ID --project=thinker41 --stream
```

## Deployment Commands

### Full Redeployment (Manual)

```bash
# Set variables
PROJECT=thinker41
REGION=asia-southeast1
SERVICE=extrasuite

# Build and push image
cd extrasuite-server
gcloud builds submit --tag gcr.io/$PROJECT/$SERVICE:latest --project=$PROJECT

# Deploy
gcloud run deploy $SERVICE \
  --image=gcr.io/$PROJECT/$SERVICE:latest \
  --service-account=extrasuite-server@$PROJECT.iam.gserviceaccount.com \
  --region=$REGION \
  --allow-unauthenticated \
  --set-env-vars="ENVIRONMENT=production,GOOGLE_CLOUD_PROJECT=$PROJECT" \
  --set-env-vars='^@^ALLOWED_EMAIL_DOMAINS=think41.com,recruit41.com,mindlap.dev' \
  --set-env-vars='^@^DOMAIN_ABBREVIATIONS={"think41.com":"t41","recruit41.com":"r41","mindlap.dev":"mlap"}' \
  --set-secrets="SECRET_KEY=extrasuite-secret-key:latest,GOOGLE_CLIENT_ID=extrasuite-google-client-id:latest,GOOGLE_CLIENT_SECRET=extrasuite-google-client-secret:latest" \
  --project=$PROJECT

# Update OAuth redirect URI
SERVICE_URL=$(gcloud run services describe $SERVICE --region=$REGION --project=$PROJECT --format='value(status.url)')
gcloud run services update $SERVICE \
  --region=$REGION \
  --update-env-vars="GOOGLE_REDIRECT_URI=$SERVICE_URL/api/auth/callback" \
  --project=$PROJECT
```

### Clean Slate Deployment

When you need to delete everything and start fresh:

```bash
# 1. Delete Cloud Run service
gcloud run services delete $SERVICE --region=$REGION --project=$PROJECT --quiet

# 2. Delete Firestore database
gcloud firestore databases delete --database="(default)" --project=$PROJECT --quiet

# 3. Delete user service accounts (pattern: *-t41, *-r41, *-mlap)
gcloud iam service-accounts list --project=$PROJECT --format="value(email)" | \
  grep -E '-(t41|r41|mlap)@' | \
  xargs -I {} gcloud iam service-accounts delete {} --project=$PROJECT --quiet

# 4. Delete container images
gcloud container images list-tags gcr.io/$PROJECT/$SERVICE --format="get(digest)" | \
  while read digest; do
    gcloud container images delete "gcr.io/$PROJECT/$SERVICE@$digest" --quiet --force-delete-tags
  done

# 5. Wait for Firestore cooldown (~5 minutes)
sleep 300

# 6. Recreate Firestore database
gcloud firestore databases create --location=$REGION --project=$PROJECT

# 7. Proceed with deployment (see above)
```

### Domain Mapping

```bash
# Create domain mapping
gcloud beta run domain-mappings create \
  --service=$SERVICE \
  --domain=extrasuite.think41.com \
  --region=$REGION \
  --project=$PROJECT

# Configure DNS (add CNAME record):
# extrasuite.think41.com -> ghs.googlehosted.com

# Check status
gcloud beta run domain-mappings describe \
  --domain=extrasuite.think41.com \
  --region=$REGION \
  --project=$PROJECT
```

## Monitoring and Debugging

### View Logs

```bash
# Recent logs
gcloud run services logs read $SERVICE --region=$REGION --project=$PROJECT --limit=50

# Error logs only
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="extrasuite" AND severity>=ERROR' \
  --project=$PROJECT --limit=20 --format="json"

# Logs with specific message
gcloud logging read 'resource.type="cloud_run_revision" AND jsonPayload.message:"OAuth callback"' \
  --project=$PROJECT --limit=10
```

### Health Check

```bash
# Use custom domain (Cloud Run URL may return 404 when domain mapping is configured)
curl https://extrasuite.think41.com/api/health
# Expected: {"status":"healthy","service":"extrasuite-server"}
```

### List Service Accounts

```bash
gcloud iam service-accounts list --project=$PROJECT --format="table(email,displayName)"
```

### Check IAM Permissions

```bash
gcloud projects get-iam-policy $PROJECT \
  --flatten="bindings[].members" \
  --format="table(bindings.role,bindings.members)" \
  --filter="bindings.members:extrasuite-server@$PROJECT.iam.gserviceaccount.com"
```

## Required IAM Roles

The `extrasuite-server` service account requires:

| Role | Purpose |
|------|---------|
| `roles/datastore.user` | Read/write Firestore |
| `roles/iam.serviceAccountAdmin` | Create user service accounts |
| `roles/iam.serviceAccountTokenCreator` | Impersonate user service accounts |
| `roles/secretmanager.secretAccessor` | Read secrets (per-secret binding) |

## Secrets

Secrets are stored in Secret Manager:

| Secret Name | Purpose |
|-------------|---------|
| `extrasuite-google-client-id` | OAuth Client ID |
| `extrasuite-google-client-secret` | OAuth Client Secret |
| `extrasuite-secret-key` | Session signing key |

## Testing Authentication Flow

```bash
# Clear token cache
rm -f ~/.config/extrasuite/token.json

# Run test
cd /path/to/extrasuite
PYTHONPATH=extrasuite-client/src python3 extrasuite-client/examples/basic_usage.py \
  --server https://extrasuite.think41.com
```

**Three test scenarios:**

1. **First run (no cache):** Token file missing, browser opens, user authenticates
2. **Cached token:** Token file present and valid, no browser needed
3. **Session reuse:** Delete token cache, browser opens, SSO/session skips login prompt

## Environment Variables Reference

| Variable | Description | Example |
|----------|-------------|---------|
| `ENVIRONMENT` | Runtime environment | `production` |
| `GOOGLE_CLOUD_PROJECT` | GCP project ID | `thinker41` |
| `GOOGLE_CLIENT_ID` | OAuth client ID | (from Secret Manager) |
| `GOOGLE_CLIENT_SECRET` | OAuth client secret | (from Secret Manager) |
| `GOOGLE_REDIRECT_URI` | OAuth callback URL | `https://extrasuite.think41.com/api/auth/callback` |
| `SECRET_KEY` | Session signing key | (from Secret Manager) |
| `ALLOWED_EMAIL_DOMAINS` | Comma-separated domains | `think41.com,recruit41.com,mindlap.dev` |
| `DOMAIN_ABBREVIATIONS` | JSON mapping | `{"think41.com":"t41",...}` |
