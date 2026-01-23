# Operations Guide

This guide covers monitoring, updating, and troubleshooting your ExtraSuite deployment.

## Monitoring

### View Logs

#### Using gcloud CLI

```bash
# Recent logs (last 50 entries)
gcloud run services logs read extrasuite-server \
  --region=asia-southeast1 \
  --project=$PROJECT_ID \
  --limit=50

# Errors only
gcloud logging read \
  'resource.type="cloud_run_revision" AND resource.labels.service_name="extrasuite-server" AND severity>=ERROR' \
  --project=$PROJECT_ID \
  --limit=20
```

#### Using Google Cloud Console

1. Go to **Cloud Run > extrasuite-server**
2. Click the **Logs** tab

### Health Check

```bash
curl https://YOUR_DOMAIN/api/health
```

Expected response:
```json
{"status":"healthy","service":"extrasuite-server"}
```

### List User Service Accounts

See how many users have been onboarded:

```bash
gcloud iam service-accounts list --project=$PROJECT_ID \
  --format="table(email,displayName)"
```

---

## Updating ExtraSuite

### Update to Latest Version

#### Using gcloud CLI

```bash
gcloud run services update extrasuite-server \
  --region=asia-southeast1 \
  --image=asia-southeast1-docker.pkg.dev/thinker41/extrasuite/server:latest \
  --project=$PROJECT_ID
```

#### Using Google Cloud Console

1. Go to **Cloud Run > extrasuite-server**
2. Click **Edit & Deploy New Revision**
3. Update the container image URL to use `latest` or a specific version
4. Click **Deploy**

### Pin to a Specific Version

For production stability, pin to a version tag:

```bash
gcloud run services update extrasuite-server \
  --region=asia-southeast1 \
  --image=asia-southeast1-docker.pkg.dev/thinker41/extrasuite/server:v1.0.0 \
  --project=$PROJECT_ID
```

### Rollback to Previous Version

```bash
# List available revisions
gcloud run revisions list \
  --service=extrasuite-server \
  --region=asia-southeast1 \
  --project=$PROJECT_ID

# Route all traffic to a previous revision
gcloud run services update-traffic extrasuite-server \
  --region=asia-southeast1 \
  --to-revisions=extrasuite-server-00001-abc=100 \
  --project=$PROJECT_ID
```

---

## Troubleshooting

### OAuth Consent Shows Too Many Permissions

**Symptom:** Users see "See, edit, configure and delete your Google Cloud data" instead of just email access.

**Cause:** Google includes previously granted scopes when `include_granted_scopes` is enabled.

**Solution:** Users should revoke ExtraSuite's access at [myaccount.google.com/permissions](https://myaccount.google.com/permissions), then log in again.

---

### 404 Error: "No document to update"

**Symptom:** Error in logs:
```
NotFound: 404 No document to update: projects/.../documents/users/email@domain.com
```

**Cause:** This is a code bug where `update()` is used instead of `set(merge=True)`.

**Solution:** Update to the latest version of ExtraSuite which fixes this issue.

---

### Email Domain Allowlist Not Working

**Symptom:** Valid email domains are rejected during login.

**Cause:** The `ALLOWED_EMAIL_DOMAINS` environment variable may be malformed.

**Diagnosis:**
```bash
gcloud run services describe extrasuite-server \
  --region=asia-southeast1 \
  --project=$PROJECT_ID \
  --format="yaml(spec.template.spec.containers[0].env)"
```

**Solution:** Ensure domains are comma-separated with no spaces:
```
ALLOWED_EMAIL_DOMAINS=example.com,company.org
```

---

### Custom Domain SSL Certificate Not Working

**Symptom:** HTTPS doesn't work on your custom domain.

**Cause:** Google-managed SSL certificates take 15-30 minutes to provision.

**Diagnosis:**
```bash
gcloud beta run domain-mappings describe \
  --domain=your-domain.com \
  --region=asia-southeast1 \
  --project=$PROJECT_ID \
  --format="yaml(status.conditions)"

# Verify DNS is configured
dig your-domain.com CNAME +short
# Expected: ghs.googlehosted.com.
```

**Solution:** Wait for certificate provisioning. Once `CertificateProvisioned` shows `status: 'True'`, HTTPS will work.

---

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

---

### Firestore Database Recreation Fails

**Symptom:** After deleting a Firestore database, recreating fails with:
```
FAILED_PRECONDITION: Database ID '(default)' is not available. Please retry in X seconds.
```

**Cause:** Firestore requires a cooldown period (~5 minutes) after database deletion.

**Solution:** Wait 5 minutes, then try again.

---

### Service Account Quota Exceeded

**Symptom:** New users cannot onboard.

**Cause:** GCP default quota is 100 service accounts per project.

**Diagnosis:**
```bash
gcloud iam service-accounts list --project=$PROJECT_ID | wc -l
```

**Solution:** [Request a quota increase](https://console.cloud.google.com/iam-admin/quotas) for "Service Accounts per Project".

---

## Secrets Management

### Rotate a Secret

```bash
# Add new version
echo -n "new-secret-value" | gcloud secrets versions add extrasuite-secret-key \
  --data-file=- \
  --project=$PROJECT_ID

# Redeploy to pick up new version
gcloud run services update extrasuite-server \
  --region=asia-southeast1 \
  --update-secrets="SECRET_KEY=extrasuite-secret-key:latest" \
  --project=$PROJECT_ID
```

### View Secret Versions

```bash
gcloud secrets versions list extrasuite-secret-key --project=$PROJECT_ID
```

---

## Testing the Authentication Flow

Use the included test script to verify authentication works:

```bash
# Clear any cached token
rm -f ~/.config/extrasuite/token.json

# Run the test
cd /path/to/extrasuite
PYTHONPATH=extrasuite-client/src python3 extrasuite-client/examples/basic_usage.py \
  --server https://YOUR_DOMAIN
```

**Expected behavior:**

1. Browser opens to the login page
2. User authenticates with Google
3. Browser redirects back and closes
4. Script prints a valid access token

---

## Cleanup

To completely remove ExtraSuite from your project:

```bash
# Delete Cloud Run service
gcloud run services delete extrasuite-server \
  --region=asia-southeast1 \
  --project=$PROJECT_ID \
  --quiet

# Delete user service accounts (adjust pattern for your domain abbreviations)
gcloud iam service-accounts list --project=$PROJECT_ID --format="value(email)" | \
  grep -E '-(ex|co)@' | \
  xargs -I {} gcloud iam service-accounts delete {} --project=$PROJECT_ID --quiet

# Delete the server service account
gcloud iam service-accounts delete extrasuite-server@$PROJECT_ID.iam.gserviceaccount.com \
  --project=$PROJECT_ID --quiet

# Delete Firestore database
gcloud firestore databases delete --database="(default)" --project=$PROJECT_ID --quiet

# Delete secrets
for secret in extrasuite-client-id extrasuite-client-secret extrasuite-secret-key; do
  gcloud secrets delete $secret --project=$PROJECT_ID --quiet
done
```

---

## Getting Help

If you encounter issues not covered here:

1. Check [Cloud Run logs](#view-logs) for error details
2. Search [GitHub Issues](https://github.com/think41/extrasuite/issues)
3. Open a new issue with:
   - Error message from logs
   - Steps to reproduce
   - Your configuration (without secrets)
