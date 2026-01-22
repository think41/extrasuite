# Deploying to Cloud Run

This guide covers deploying the ExtraSuite server to Google Cloud Run.

## Prerequisites

1. **Google Cloud Project** with billing enabled
2. **gcloud CLI** installed and configured

## Step 1: Enable Required APIs

```bash
export PROJECT_ID=your-project-id

gcloud services enable \
  run.googleapis.com \
  firestore.googleapis.com \
  iam.googleapis.com \
  iamcredentials.googleapis.com \
  secretmanager.googleapis.com \
  --project=$PROJECT_ID
```

## Step 2: Create Firestore Database

```bash
gcloud firestore databases create --location=asia-southeast1 --project=$PROJECT_ID
```

Collections are created automatically on first use.

## Step 3: Create OAuth 2.0 Credentials

1. Go to [Google Cloud Console > APIs & Services > Credentials](https://console.cloud.google.com/apis/credentials)
2. Click **Create Credentials** > **OAuth client ID**
3. Select **Web application**
4. Add authorized redirect URIs:
   - `https://your-domain.com/api/auth/callback`
   - `http://localhost:8001/api/auth/callback` (for development)
5. Save the **Client ID** and **Client Secret**

## Step 4: Create Service Account for Cloud Run

```bash
# Create service account
gcloud iam service-accounts create extrasuite-server \
  --display-name="ExtraSuite Server" \
  --project=$PROJECT_ID

# Grant Firestore access
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:extrasuite-server@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/datastore.user"

# Grant service account admin (for creating user SAs)
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:extrasuite-server@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountAdmin"

# Grant token creator (for impersonation)
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:extrasuite-server@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountTokenCreator"
```

## Step 5: Store Secrets in Secret Manager

```bash
# Create secrets (replace with your actual values)
echo -n "your-oauth-client-id" | gcloud secrets create extrasuite-client-id \
  --data-file=- --project=$PROJECT_ID
echo -n "your-oauth-client-secret" | gcloud secrets create extrasuite-client-secret \
  --data-file=- --project=$PROJECT_ID
echo -n "$(openssl rand -base64 32)" | gcloud secrets create extrasuite-secret-key \
  --data-file=- --project=$PROJECT_ID

# Grant Cloud Run access to secrets
for secret in extrasuite-client-id extrasuite-client-secret extrasuite-secret-key; do
  gcloud secrets add-iam-policy-binding $secret \
    --member="serviceAccount:extrasuite-server@$PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor" \
    --project=$PROJECT_ID
done
```

## Step 6: Deploy to Cloud Run

```bash
gcloud run deploy extrasuite-server \
  --image=asia-southeast1-docker.pkg.dev/thinker41/extrasuite/server:latest \
  --service-account=extrasuite-server@$PROJECT_ID.iam.gserviceaccount.com \
  --region=asia-southeast1 \
  --allow-unauthenticated \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=$PROJECT_ID" \
  --set-env-vars="BASE_DOMAIN=your-domain.com" \
  --set-secrets="SECRET_KEY=extrasuite-secret-key:latest" \
  --set-secrets="GOOGLE_CLIENT_ID=extrasuite-client-id:latest" \
  --set-secrets="GOOGLE_CLIENT_SECRET=extrasuite-client-secret:latest" \
  --project=$PROJECT_ID
```

## Step 7: Update OAuth Redirect URI

Get your Cloud Run URL:

```bash
SERVICE_URL=$(gcloud run services describe extrasuite-server \
  --region=asia-southeast1 \
  --project=$PROJECT_ID \
  --format='value(status.url)')
echo $SERVICE_URL
```

Update your OAuth credentials in Google Cloud Console to include:
`https://your-cloud-run-url/api/auth/callback`

If not using a custom domain, update the BASE_DOMAIN:

```bash
# Extract domain from URL (removes https://)
DOMAIN=$(echo $SERVICE_URL | sed 's|https://||')

gcloud run services update extrasuite-server \
  --region=asia-southeast1 \
  --update-env-vars="BASE_DOMAIN=$DOMAIN" \
  --project=$PROJECT_ID
```

## Step 8: Configure Email Domain Allowlist (Optional)

Restrict authentication to specific email domains:

```bash
gcloud run services update extrasuite-server \
  --region=asia-southeast1 \
  --update-env-vars="ALLOWED_EMAIL_DOMAINS=example.com,company.org" \
  --project=$PROJECT_ID
```

## Step 9: Configure Domain Abbreviations (Optional)

Service accounts are named using the user's email local part plus a domain abbreviation:

```bash
gcloud run services update extrasuite-server \
  --region=asia-southeast1 \
  --update-env-vars='DOMAIN_ABBREVIATIONS={"example.com":"ex","company.org":"co"}' \
  --project=$PROJECT_ID
```

Example: `john@example.com` creates service account `john-ex@project.iam.gserviceaccount.com`

If a domain is not in the mapping, a 4-character hash is used as fallback.

## Verification

Test the deployment:

```bash
# Health check
curl $SERVICE_URL/api/health
# Expected: {"status":"healthy","service":"extrasuite-server"}
```

## Custom Domain

To use a custom domain:

```bash
# Create domain mapping
gcloud beta run domain-mappings create \
  --service=extrasuite-server \
  --domain=extrasuite.yourdomain.com \
  --region=asia-southeast1 \
  --project=$PROJECT_ID

# Configure DNS: Add CNAME record
# extrasuite.yourdomain.com -> ghs.googlehosted.com

# Check status (SSL cert takes 15-30 minutes)
gcloud beta run domain-mappings describe \
  --domain=extrasuite.yourdomain.com \
  --region=asia-southeast1 \
  --project=$PROJECT_ID
```

After the domain is configured, update the BASE_DOMAIN:

```bash
gcloud run services update extrasuite-server \
  --region=asia-southeast1 \
  --update-env-vars="BASE_DOMAIN=extrasuite.yourdomain.com" \
  --project=$PROJECT_ID
```

## Using a Specific Version

Instead of `latest`, you can pin to a specific version:

```bash
# Use a specific release
--image=asia-southeast1-docker.pkg.dev/thinker41/extrasuite/server:v1.0.0

# Use a specific commit
--image=asia-southeast1-docker.pkg.dev/thinker41/extrasuite/server:sha-abc1234

# Use latest from main branch
--image=asia-southeast1-docker.pkg.dev/thinker41/extrasuite/server:main
```

## Production Recommendations

1. **Enable Cloud Armor** for DDoS protection
2. **Set up Cloud Monitoring** alerts for errors
3. **Enable Cloud Audit Logs** for compliance
4. **Set minimum instances** to reduce cold starts:
   ```bash
   gcloud run services update extrasuite-server \
     --region=asia-southeast1 \
     --min-instances=1 \
     --project=$PROJECT_ID
   ```
5. **Configure Firestore TTL** for automatic cleanup of expired OAuth states:
   ```bash
   gcloud firestore fields ttls update expire_at \
     --collection-group=oauth_states \
     --enable-ttl \
     --project=$PROJECT_ID
   ```

---

**Next:** Review [IAM Permissions](iam-permissions.md) for a complete permission reference.
