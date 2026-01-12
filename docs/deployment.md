# Deploying Google Workspace Gateway to Cloud Run

This guide covers deploying the GWG server to Google Cloud Run.

## Prerequisites

1. **Google Cloud Project** with billing enabled
2. **gcloud CLI** installed and configured
3. **Docker** installed locally

## Step 1: Enable Required APIs

```bash
gcloud services enable \
  run.googleapis.com \
  bigtable.googleapis.com \
  bigtableadmin.googleapis.com \
  iam.googleapis.com \
  iamcredentials.googleapis.com \
  containerregistry.googleapis.com
```

## Step 2: Create Bigtable Instance

```bash
# Create Bigtable instance (1 node for dev, scale up for production)
gcloud bigtable instances create gwg-auth \
  --display-name="GWG Auth" \
  --cluster-config=id=gwg-auth-c1,zone=us-central1-a,nodes=1

# Create tables
cbt -project=$PROJECT_ID -instance=gwg-auth createtable sessions
cbt -project=$PROJECT_ID -instance=gwg-auth createfamily sessions data

cbt -project=$PROJECT_ID -instance=gwg-auth createtable users
cbt -project=$PROJECT_ID -instance=gwg-auth createfamily users oauth
cbt -project=$PROJECT_ID -instance=gwg-auth createfamily users metadata
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
gcloud iam service-accounts create gwg-server \
  --display-name="GWG Server"

# Grant Bigtable access
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:gwg-server@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/bigtable.user"

# Grant service account admin (for creating user SAs)
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:gwg-server@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountAdmin"

# Grant token creator (for impersonation)
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:gwg-server@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountTokenCreator"
```

## Step 5: Build and Push Docker Image

```bash
# Build the image
docker build -t gcr.io/$PROJECT_ID/gwg-server:latest .

# Push to Container Registry
docker push gcr.io/$PROJECT_ID/gwg-server:latest
```

## Step 6: Deploy to Cloud Run

```bash
gcloud run deploy gwg-server \
  --image=gcr.io/$PROJECT_ID/gwg-server:latest \
  --service-account=gwg-server@$PROJECT_ID.iam.gserviceaccount.com \
  --region=us-central1 \
  --allow-unauthenticated \
  --set-env-vars="ENVIRONMENT=production" \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=$PROJECT_ID" \
  --set-env-vars="BIGTABLE_INSTANCE=gwg-auth" \
  --set-secrets="SECRET_KEY=gwg-secret-key:latest" \
  --set-secrets="GOOGLE_CLIENT_ID=gwg-client-id:latest" \
  --set-secrets="GOOGLE_CLIENT_SECRET=gwg-client-secret:latest"
```

## Step 7: Update OAuth Redirect URI

After deployment, get your Cloud Run URL:

```bash
gcloud run services describe gwg-server --region=us-central1 --format='value(status.url)'
```

Update your OAuth credentials in Google Cloud Console to include:
- `https://your-cloud-run-url/api/auth/callback`

Then update the environment variable:

```bash
gcloud run services update gwg-server \
  --region=us-central1 \
  --set-env-vars="GOOGLE_REDIRECT_URI=https://your-cloud-run-url/api/auth/callback"
```

## Step 8: Store Secrets in Secret Manager

```bash
# Create secrets
echo -n "your-oauth-client-id" | gcloud secrets create gwg-client-id --data-file=-
echo -n "your-oauth-client-secret" | gcloud secrets create gwg-client-secret --data-file=-
echo -n "$(openssl rand -base64 32)" | gcloud secrets create gwg-secret-key --data-file=-

# Grant Cloud Run access to secrets
gcloud secrets add-iam-policy-binding gwg-client-id \
  --member="serviceAccount:gwg-server@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

gcloud secrets add-iam-policy-binding gwg-client-secret \
  --member="serviceAccount:gwg-server@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

gcloud secrets add-iam-policy-binding gwg-secret-key \
  --member="serviceAccount:gwg-server@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

## Verification

Test the deployment:

```bash
# Health check
curl https://your-cloud-run-url/api/health

# Should return: {"status":"healthy","service":"gwg-server"}
```

## Production Recommendations

1. **Enable Cloud Armor** for DDoS protection
2. **Set up Cloud Monitoring** alerts for errors
3. **Enable Cloud Audit Logs** for compliance
4. **Use a custom domain** with managed SSL
5. **Scale Bigtable** based on usage patterns
6. **Set minimum instances** to reduce cold starts:
   ```bash
   gcloud run services update gwg-server --min-instances=1
   ```
