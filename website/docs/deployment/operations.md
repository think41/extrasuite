# Operations Guide

This document covers monitoring, debugging, and troubleshooting for ExtraSuite deployments.

## Monitoring

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
```

### Health Checks

```bash
# Basic health check
curl https://your-domain.com/api/health
# Expected: {"status":"healthy","service":"extrasuite-server"}
```

### List User Service Accounts

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

## Common Issues

### OAuth Scopes Showing Too Many Permissions

**Symptom:** OAuth consent screen asks for "See, edit, configure and delete your Google Cloud data" instead of just email access.

**Cause:** Using `include_granted_scopes="true"` causes Google to include any previously granted scopes.

**Solution:** Users may need to revoke existing app permissions at [myaccount.google.com/permissions](https://myaccount.google.com/permissions) before re-authenticating.

### Firestore "No document to update" Error

**Symptom:**
```
NotFound: 404 No document to update: projects/.../documents/users/email@domain.com
```

**Cause:** Code is using Firestore `update()` method on a document that doesn't exist.

**Solution:** Use `set(merge=True)` instead of `update()` for upsert behavior.

### Email Domain Allowlist Not Working

**Symptom:** Valid email domains are rejected.

**Cause:** The gcloud CLI may interpret commas incorrectly in some shells.

**Solution:** Verify the environment variable is set correctly:
```bash
gcloud run services describe extrasuite-server \
  --region=asia-southeast1 \
  --format="value(spec.template.spec.containers[0].env)"
```

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

## Updating the Deployment

### Update to Latest Version

```bash
gcloud run services update extrasuite-server \
  --region=asia-southeast1 \
  --image=asia-southeast1-docker.pkg.dev/thinker41/extrasuite/server:latest \
  --project=$PROJECT_ID
```

### Update Environment Variables

```bash
gcloud run services update extrasuite-server \
  --region=asia-southeast1 \
  --update-env-vars="KEY=value" \
  --project=$PROJECT_ID
```

### Rollback to Previous Version

```bash
# List revisions
gcloud run revisions list \
  --service=extrasuite-server \
  --region=asia-southeast1 \
  --project=$PROJECT_ID

# Route traffic to a specific revision
gcloud run services update-traffic extrasuite-server \
  --region=asia-southeast1 \
  --to-revisions=extrasuite-server-00001-abc=100 \
  --project=$PROJECT_ID
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

## Secrets Management

### Rotate Secrets

```bash
# Update secret with new value
echo -n "new-value" | gcloud secrets versions add extrasuite-secret-key --data-file=-

# Deploy with new version (Cloud Run auto-updates on next deploy)
gcloud run services update extrasuite-server \
  --region=asia-southeast1 \
  --update-secrets="SECRET_KEY=extrasuite-secret-key:latest" \
  --project=$PROJECT_ID
```

## Service Account Quota

ExtraSuite creates one service account per user. Monitor usage:

```bash
# Count service accounts
gcloud iam service-accounts list --project=$PROJECT_ID | wc -l
```

GCP default quota is 100 service accounts per project. [Request an increase](https://console.cloud.google.com/iam-admin/quotas) if needed.

## Clean Up

To remove all ExtraSuite resources:

```bash
# Delete Cloud Run service
gcloud run services delete extrasuite-server \
  --region=asia-southeast1 \
  --project=$PROJECT_ID

# Delete user service accounts (adjust pattern for your domains)
gcloud iam service-accounts list --project=$PROJECT_ID --format="value(email)" | \
  grep -E '-(ex|co)@' | \
  xargs -I {} gcloud iam service-accounts delete {} --project=$PROJECT_ID --quiet

# Delete Firestore database
gcloud firestore databases delete --database="(default)" --project=$PROJECT_ID

# Delete secrets
for secret in extrasuite-client-id extrasuite-client-secret extrasuite-secret-key; do
  gcloud secrets delete $secret --project=$PROJECT_ID --quiet
done
```

---

## Continue Your Setup

If you arrived here from the Organization Setup guide, return to continue with user onboarding:

[:octicons-arrow-right-24: Continue Organization Setup](../getting-started/organization-setup.md#step-2-install-your-ai-editor)