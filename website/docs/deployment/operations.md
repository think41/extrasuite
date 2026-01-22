# Operations Runbook

This document captures operational knowledge and troubleshooting guidance for ExtraSuite deployments.

## Monitoring and Debugging

### View Logs

```bash
# Recent logs
gcloud run services logs read extrasuite-server \
  --region=asia-southeast1 \
  --project=$PROJECT_ID \
  --limit=50

# Error logs only
gcloud logging read \
  'resource.type="cloud_run_revision" AND resource.labels.service_name="extrasuite-server" AND severity>=ERROR' \
  --project=$PROJECT_ID \
  --limit=20 \
  --format="json"

# Logs with specific message
gcloud logging read \
  'resource.type="cloud_run_revision" AND jsonPayload.message:"OAuth callback"' \
  --project=$PROJECT_ID \
  --limit=10
```

### Health Checks

```bash
# Basic health check
curl https://your-domain.com/api/health
# Expected: {"status":"healthy","service":"extrasuite-server"}

# Readiness check
curl https://your-domain.com/api/health/ready
# Expected: {"status":"ready"}
```

### List Service Accounts

```bash
gcloud iam service-accounts list --project=$PROJECT_ID \
  --format="table(email,displayName)"
```

### Check IAM Permissions

```bash
gcloud projects get-iam-policy $PROJECT_ID \
  --flatten="bindings[].members" \
  --format="table(bindings.role,bindings.members)" \
  --filter="bindings.members:extrasuite-server@$PROJECT_ID.iam.gserviceaccount.com"
```

## Common Issues and Solutions

### OAuth Scopes Showing Too Many Permissions

**Symptom:** OAuth consent screen asks for "See, edit, configure and delete your Google Cloud data" instead of just email access.

**Cause:** Using `include_granted_scopes="true"` causes Google to include any previously granted scopes.

**Solution:** Users may need to revoke existing app permissions at [myaccount.google.com/permissions](https://myaccount.google.com/permissions) before re-authenticating.

### Firestore "No document to update" Error

**Symptom:**
```
NotFound: 404 No document to update: projects/.../documents/users/email@domain.com
```

**Cause:** Using Firestore `update()` method on a document that doesn't exist.

**Solution:** This is a code bug. Use `set(merge=True)` instead of `update()` for upsert behavior.

### Email Domain Allowlist Not Working

**Symptom:** Valid email domains are rejected.

**Cause:** The gcloud CLI interprets commas as value separators incorrectly.

**Solution:** Use gcloud's alternate delimiter syntax:
```bash
gcloud run services update extrasuite-server \
  --update-env-vars='^@^ALLOWED_EMAIL_DOMAINS=example.com,company.org'
```

The `^@^` prefix changes the delimiter to `@` instead of `,`.

### Firestore Database Recreation Delay

**Symptom:** After deleting a Firestore database, recreating fails:
```
FAILED_PRECONDITION: Database ID '(default)' is not available. Please retry in X seconds.
```

**Cause:** Firestore requires a cooldown period (~4-5 minutes) after database deletion.

**Solution:** Wait for the cooldown period before recreating.

### Custom Domain SSL Certificate Pending

**Symptom:** Custom domain doesn't work with HTTPS.

**Cause:** Google-managed SSL certificates take 15-30 minutes to provision.

**Diagnosis:**
```bash
gcloud beta run domain-mappings describe \
  --domain=your-domain.com \
  --region=asia-southeast1 \
  --format="yaml(status.conditions)"

# Verify DNS
dig your-domain.com CNAME +short
# Should return: ghs.googlehosted.com.
```

**Solution:** Wait for certificate provisioning. When `CertificateProvisioned` shows `status: 'True'`, HTTPS will work.

### IAM Policy Binding Fails

**Symptom:**
```
ERROR: Adding a binding without specifying a condition to a policy containing conditions is prohibited
```

**Cause:** The project has existing IAM bindings with conditions.

**Solution:** Add `--condition=None` to the command:
```bash
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:sa@project.iam.gserviceaccount.com" \
  --role="roles/some.role" \
  --condition=None
```

## Deployment Commands

### Full Redeployment

```bash
# Set variables
PROJECT=your-project-id
REGION=asia-southeast1
SERVICE=extrasuite-server

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
  --set-secrets="SECRET_KEY=extrasuite-secret-key:latest" \
  --set-secrets="GOOGLE_CLIENT_ID=extrasuite-client-id:latest" \
  --set-secrets="GOOGLE_CLIENT_SECRET=extrasuite-client-secret:latest" \
  --project=$PROJECT

# Update server URL
SERVICE_URL=$(gcloud run services describe $SERVICE \
  --region=$REGION --project=$PROJECT --format='value(status.url)')
gcloud run services update $SERVICE \
  --region=$REGION \
  --update-env-vars="SERVER_URL=$SERVICE_URL" \
  --project=$PROJECT
```

### Clean Slate Deployment

When you need to delete everything and start fresh:

```bash
# 1. Delete Cloud Run service
gcloud run services delete $SERVICE --region=$REGION --project=$PROJECT --quiet

# 2. Delete Firestore database
gcloud firestore databases delete --database="(default)" --project=$PROJECT --quiet

# 3. Delete user service accounts (adjust pattern for your domains)
gcloud iam service-accounts list --project=$PROJECT --format="value(email)" | \
  grep -E '-(ex|co)@' | \
  xargs -I {} gcloud iam service-accounts delete {} --project=$PROJECT --quiet

# 4. Wait for Firestore cooldown (~5 minutes)
sleep 300

# 5. Recreate Firestore database
gcloud firestore databases create --location=$REGION --project=$PROJECT

# 6. Proceed with deployment
```

## CI/CD Operations

### View Build Status

```bash
# List recent builds
gcloud builds list --project=$PROJECT_ID --limit=5

# View specific build logs
gcloud builds log BUILD_ID --project=$PROJECT_ID

# Stream logs for running build
gcloud builds log BUILD_ID --project=$PROJECT_ID --stream
```

### Trigger Manual Build

```bash
cd extrasuite-server
gcloud builds submit --config=cloudbuild.yaml --project=$PROJECT_ID
```

## Testing Authentication Flow

```bash
# Clear token cache
rm -f ~/.config/extrasuite/token.json

# Run test
cd /path/to/extrasuite
PYTHONPATH=extrasuite-client/src python3 extrasuite-client/examples/basic_usage.py \
  --server https://your-domain.com
```

**Three test scenarios:**

1. **First run (no cache):** Token file missing, browser opens, user authenticates
2. **Cached token:** Token file present and valid, no browser needed
3. **Session reuse:** Delete token cache, browser opens, SSO/session skips login prompt

## Environment Variables Reference

| Variable | Description | Example |
|----------|-------------|---------|
| `ENVIRONMENT` | Runtime environment | `production` |
| `GOOGLE_CLOUD_PROJECT` | GCP project ID | `your-project` |
| `GOOGLE_CLIENT_ID` | OAuth client ID | (from Secret Manager) |
| `GOOGLE_CLIENT_SECRET` | OAuth client secret | (from Secret Manager) |
| `SERVER_URL` | Base URL for server | `https://domain.com` |
| `SECRET_KEY` | Session signing key | (from Secret Manager) |
| `ALLOWED_EMAIL_DOMAINS` | Comma-separated domains | `example.com,company.org` |
| `DOMAIN_ABBREVIATIONS` | JSON mapping | `{"example.com":"ex"}` |

## Secrets Management

Secrets stored in Secret Manager:

| Secret Name | Purpose |
|-------------|---------|
| `extrasuite-client-id` | OAuth Client ID |
| `extrasuite-client-secret` | OAuth Client Secret |
| `extrasuite-secret-key` | Session signing key |

### Rotate Secrets

```bash
# Update secret
echo -n "new-value" | gcloud secrets versions add SECRET_NAME --data-file=-

# Deploy with new version
gcloud run services update extrasuite-server \
  --update-secrets="SECRET_KEY=extrasuite-secret-key:latest"
```

## Service Account Quota

ExtraSuite creates one service account per user. Monitor usage:

```bash
# Count service accounts
gcloud iam service-accounts list --project=$PROJECT_ID | wc -l
```

GCP default quota is 100 service accounts per project. Request increase if needed.
