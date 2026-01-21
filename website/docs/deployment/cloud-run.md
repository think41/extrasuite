# Deploying to Cloud Run

This guide covers deploying the ExtraSuite server to Google Cloud Run.

## Prerequisites

1. **Google Cloud Project** with billing enabled
2. **gcloud CLI** installed and configured
3. **Docker** installed locally (optional, for local builds)

## Step 1: Enable Required APIs

```bash
export PROJECT_ID=your-project-id

gcloud services enable \
  run.googleapis.com \
  firestore.googleapis.com \
  iam.googleapis.com \
  iamcredentials.googleapis.com \
  containerregistry.googleapis.com \
  secretmanager.googleapis.com \
  --project=$PROJECT_ID
```

## Step 2: Create Firestore Database

```bash
# Create Firestore database (collections are created automatically on first use)
gcloud firestore databases create --location=asia-southeast1 --project=$PROJECT_ID
```

## Step 3: Create OAuth 2.0 Credentials

1. Go to [Google Cloud Console > APIs & Services > Credentials](https://console.cloud.google.com/apis/credentials)
2. Click **Create Credentials** > **OAuth client ID**
3. Select **Web application**
4. Add authorized redirect URIs:
   - `https://your-cloud-run-url/api/auth/callback`
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
# Create secrets
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

## Step 6: Build and Deploy

### Option A: Deploy from Source

```bash
cd extrasuite-server

gcloud run deploy extrasuite-server \
  --source . \
  --service-account=extrasuite-server@$PROJECT_ID.iam.gserviceaccount.com \
  --region=asia-southeast1 \
  --allow-unauthenticated \
  --set-env-vars="ENVIRONMENT=production" \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=$PROJECT_ID" \
  --set-secrets="SECRET_KEY=extrasuite-secret-key:latest" \
  --set-secrets="GOOGLE_CLIENT_ID=extrasuite-client-id:latest" \
  --set-secrets="GOOGLE_CLIENT_SECRET=extrasuite-client-secret:latest" \
  --project=$PROJECT_ID
```

### Option B: Build and Push Docker Image

```bash
cd extrasuite-server

# Build the image
docker build -t gcr.io/$PROJECT_ID/extrasuite-server:latest .

# Push to Container Registry
docker push gcr.io/$PROJECT_ID/extrasuite-server:latest

# Deploy
gcloud run deploy extrasuite-server \
  --image=gcr.io/$PROJECT_ID/extrasuite-server:latest \
  --service-account=extrasuite-server@$PROJECT_ID.iam.gserviceaccount.com \
  --region=asia-southeast1 \
  --allow-unauthenticated \
  --set-env-vars="ENVIRONMENT=production" \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=$PROJECT_ID" \
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

Then update the environment variable:

```bash
gcloud run services update extrasuite-server \
  --region=asia-southeast1 \
  --update-env-vars="GOOGLE_REDIRECT_URI=$SERVICE_URL/api/auth/callback" \
  --project=$PROJECT_ID
```

## Step 8: Configure Email Domain Allowlist

Restrict authentication to specific email domains:

```bash
gcloud run services update extrasuite-server \
  --region=asia-southeast1 \
  --update-env-vars='^@^ALLOWED_EMAIL_DOMAINS=example.com,company.org' \
  --project=$PROJECT_ID
```

!!! note "Delimiter Syntax"
    The `^@^` prefix changes the delimiter to `@` instead of `,` to handle comma-separated values properly.

## Step 9: Configure Domain Abbreviations

Service accounts are named using the user's email local part plus a domain abbreviation:

```bash
gcloud run services update extrasuite-server \
  --region=asia-southeast1 \
  --update-env-vars='^@^DOMAIN_ABBREVIATIONS={"example.com":"ex","company.org":"co"}' \
  --project=$PROJECT_ID
```

Example: `john@example.com` → `john-ex@project.iam.gserviceaccount.com`

## Verification

Test the deployment:

```bash
# Health check
curl $SERVICE_URL/api/health
# Expected: {"status":"healthy","service":"extrasuite-server"}

# Readiness check
curl $SERVICE_URL/api/health/ready
# Expected: {"status":"ready"}
```

## CI/CD with Cloud Build

### Create Cloud Build Service Account

```bash
# Create the Cloud Build service account
gcloud iam service-accounts create extrasuite-cloudbuild \
  --display-name="ExtraSuite Cloud Build" \
  --project=$PROJECT_ID

# Grant necessary permissions
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:extrasuite-cloudbuild@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/artifactregistry.writer" \
  --condition=None

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:extrasuite-cloudbuild@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/run.admin" \
  --condition=None

gcloud iam service-accounts add-iam-policy-binding \
  extrasuite-server@$PROJECT_ID.iam.gserviceaccount.com \
  --member="serviceAccount:extrasuite-cloudbuild@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountUser" \
  --project=$PROJECT_ID

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:extrasuite-cloudbuild@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/logging.logWriter" \
  --condition=None
```

### Configure Build Trigger

1. Go to [Cloud Build Triggers](https://console.cloud.google.com/cloud-build/triggers)
2. Click **Create Trigger**
3. Configure:
   - **Event:** Push to branch (e.g., `^main$`)
   - **Source:** Your repository
   - **Configuration:** `extrasuite-server/cloudbuild.yaml`
   - **Service account:** `extrasuite-cloudbuild@$PROJECT_ID.iam.gserviceaccount.com`

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

## Production Recommendations

1. **Enable Cloud Armor** for DDoS protection
2. **Set up Cloud Monitoring** alerts for errors
3. **Enable Cloud Audit Logs** for compliance
4. **Set minimum instances** to reduce cold starts:
   ```bash
   gcloud run services update extrasuite-server --min-instances=1
   ```
5. **Configure Firestore TTL** for automatic cleanup:
   ```bash
   gcloud firestore fields ttls update expire_at \
     --collection-group=oauth_states \
     --enable-ttl \
     --project=$PROJECT_ID
   ```

---

**Next:** Review [IAM Permissions](iam-permissions.md) for a complete permission reference.
