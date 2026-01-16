# Deploying ExtraSuite to Cloud Run

This guide covers deploying the ExtraSuite server to Google Cloud Run.

## Prerequisites

1. **Google Cloud Project** with billing enabled
2. **gcloud CLI** installed and configured
3. **Docker** installed locally

## Step 1: Enable Required APIs

```bash
gcloud services enable \
  run.googleapis.com \
  firestore.googleapis.com \
  iam.googleapis.com \
  iamcredentials.googleapis.com \
  containerregistry.googleapis.com
```

## Step 2: Create Firestore Database

```bash
# Create Firestore database (collections are created automatically on first use)
gcloud firestore databases create --location=asia-southeast1
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
  --display-name="ExtraSuite Server"

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

## Step 5: Create Cloud Build Service Account (for CI/CD)

Create a dedicated service account for Cloud Build with least privileges:

```bash
# Create the Cloud Build service account
gcloud iam service-accounts create extrasuite-cloudbuild \
  --display-name="ExtraSuite Cloud Build"

# Grant permission to push images to Container Registry (uses Artifact Registry backend)
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:extrasuite-cloudbuild@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/artifactregistry.writer" \
  --condition=None

# Grant permission to deploy to Cloud Run and set IAM policies (for --allow-unauthenticated)
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:extrasuite-cloudbuild@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/run.admin" \
  --condition=None

# Grant permission to act as the runtime service account during deployment
gcloud iam service-accounts add-iam-policy-binding \
  extrasuite-server@$PROJECT_ID.iam.gserviceaccount.com \
  --member="serviceAccount:extrasuite-cloudbuild@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountUser"

# Grant permission to write build logs
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:extrasuite-cloudbuild@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/logging.logWriter"
```

### Configure Build Trigger

After creating the service account, configure a Cloud Build trigger:

1. Go to [Cloud Build Triggers](https://console.cloud.google.com/cloud-build/triggers)
2. Click **Create Trigger**
3. Configure the trigger:
   - **Event:** Push to branch (e.g., `^main$`)
   - **Source:** Your repository
   - **Configuration:** Cloud Build configuration file
   - **Location:** `extrasuite-server/cloudbuild.yaml`
   - **Service account:** `extrasuite-cloudbuild@$PROJECT_ID.iam.gserviceaccount.com`
4. Optionally override substitution variables:
   - `_REGION`: Target Cloud Run region
   - `_SERVICE_NAME`: Cloud Run service name
   - `_REDIRECT_URI`: OAuth callback URL
   - `_ALLOWED_DOMAINS`: Allowed email domains
   - `_DOMAIN_ABBREVIATIONS`: Domain to abbreviation mapping

## Step 6: Build and Push Docker Image (Manual)

For manual deployments without Cloud Build:

```bash
# Build the image
docker build -t gcr.io/$PROJECT_ID/extrasuite-server:latest .

# Push to Container Registry
docker push gcr.io/$PROJECT_ID/extrasuite-server:latest
```

## Step 7: Deploy to Cloud Run (Manual)

For manual deployments:

```bash
gcloud run deploy extrasuite-server \
  --image=gcr.io/$PROJECT_ID/extrasuite-server:latest \
  --service-account=extrasuite-server@$PROJECT_ID.iam.gserviceaccount.com \
  --region=asia-southeast1 \
  --allow-unauthenticated \
  --set-env-vars="ENVIRONMENT=production" \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=$PROJECT_ID" \
  --set-env-vars="DOMAIN_ABBREVIATIONS={\"example.com\":\"ex\",\"company.org\":\"co\"}" \
  --set-secrets="SECRET_KEY=extrasuite-secret-key:latest" \
  --set-secrets="GOOGLE_CLIENT_ID=extrasuite-client-id:latest" \
  --set-secrets="GOOGLE_CLIENT_SECRET=extrasuite-client-secret:latest"
```

## Step 8: Update OAuth Redirect URI

After deployment, get your Cloud Run URL:

```bash
gcloud run services describe extrasuite-server --region=asia-southeast1 --format='value(status.url)'
```

Update your OAuth credentials in Google Cloud Console to include:
- `https://your-cloud-run-url/api/auth/callback`

Then update the environment variable:

```bash
gcloud run services update extrasuite-server \
  --region=asia-southeast1 \
  --set-env-vars="GOOGLE_REDIRECT_URI=https://your-cloud-run-url/api/auth/callback"
```

## Step 9: Store Secrets in Secret Manager

```bash
# Create secrets
echo -n "your-oauth-client-id" | gcloud secrets create extrasuite-client-id --data-file=-
echo -n "your-oauth-client-secret" | gcloud secrets create extrasuite-client-secret --data-file=-
echo -n "$(openssl rand -base64 32)" | gcloud secrets create extrasuite-secret-key --data-file=-

# Grant Cloud Run access to secrets
gcloud secrets add-iam-policy-binding extrasuite-client-id \
  --member="serviceAccount:extrasuite-server@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

gcloud secrets add-iam-policy-binding extrasuite-client-secret \
  --member="serviceAccount:extrasuite-server@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

gcloud secrets add-iam-policy-binding extrasuite-secret-key \
  --member="serviceAccount:extrasuite-server@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

## Verification

Test the deployment:

```bash
# Health check
curl https://your-cloud-run-url/api/health

# Should return: {"status":"healthy","service":"extrasuite-server"}
```

## Optional Configuration

### Restrict Email Domains

To allow only specific email domains to authenticate:

```bash
gcloud run services update extrasuite-server \
  --region=asia-southeast1 \
  --set-env-vars="ALLOWED_EMAIL_DOMAINS=example.com,company.org"
```

If not set, all email domains are allowed.

### Configure Domain Abbreviations

Service accounts are named using the user's email local part plus a domain abbreviation (e.g., `john-ex@project.iam.gserviceaccount.com` for `john@example.com` with abbreviation `ex`).

Configure domain abbreviations as a JSON object:

```bash
gcloud run services update extrasuite-server \
  --region=asia-southeast1 \
  --set-env-vars='DOMAIN_ABBREVIATIONS={"example.com":"ex","company.org":"co"}'
```

If a domain is not in the mapping, a 4-character hash of the domain is used as fallback.

### Configure Credential Expiry (TTL Policy)

To automatically expire user credentials after a period of inactivity, configure a Firestore TTL policy on the `users` collection:

```bash
gcloud firestore fields ttls update updated_at \
  --collection-group=users \
  --enable-ttl \
  --project=$PROJECT_ID
```

This ensures refresh tokens don't persist indefinitely. Users will need to re-authenticate after credentials expire.

## Production Recommendations

1. **Enable Cloud Armor** for DDoS protection
2. **Set up Cloud Monitoring** alerts for errors
3. **Enable Cloud Audit Logs** for compliance
4. **Use a custom domain** with managed SSL
5. **Set minimum instances** to reduce cold starts:
   ```bash
   gcloud run services update extrasuite-server --min-instances=1
   ```
