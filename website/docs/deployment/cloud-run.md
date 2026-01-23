# Step-by-Step Deployment Guide

This guide walks you through deploying ExtraSuite to Google Cloud Run. Each step includes both **gcloud CLI** commands and **Google Cloud Console** instructions.

---

## Before You Begin

**If using gcloud CLI:** Open a terminal and set your project ID. You'll use this variable throughout the guide.

```bash
export PROJECT_ID=your-project-id
```

**If using Google Cloud Console:** Open [console.cloud.google.com](https://console.cloud.google.com) and select your project from the project dropdown at the top of the page.

---

## Step 1: Enable Required APIs

ExtraSuite needs several Google Cloud APIs to function. This step enables them.

### Using gcloud CLI

```bash
gcloud services enable \
  run.googleapis.com \
  firestore.googleapis.com \
  iam.googleapis.com \
  iamcredentials.googleapis.com \
  secretmanager.googleapis.com \
  drive.googleapis.com \
  sheets.googleapis.com \
  docs.googleapis.com \
  slides.googleapis.com \
  --project=$PROJECT_ID
```

### Using Google Cloud Console

1. Go to **APIs & Services > Library** ([direct link](https://console.cloud.google.com/apis/library))
2. Search for and enable each of the following APIs:
   - Cloud Run Admin API
   - Cloud Firestore API
   - Identity and Access Management (IAM) API
   - IAM Service Account Credentials API
   - Secret Manager API
   - Google Drive API
   - Google Sheets API
   - Google Docs API
   - Google Slides API

**Verify:** After enabling, you should see all APIs listed in **APIs & Services > Enabled APIs**.

---

## Step 2: Create Firestore Database

ExtraSuite uses Firestore to store user records and session data. Collections are created automatically when the server first runs.

### Using gcloud CLI

```bash
gcloud firestore databases create \
  --location=asia-southeast1 \
  --project=$PROJECT_ID
```

!!! note "Choose a location close to your users"
    Replace `asia-southeast1` with your preferred [Firestore location](https://cloud.google.com/firestore/docs/locations). Common choices: `us-central1`, `europe-west1`, `asia-southeast1`.

### Using Google Cloud Console

1. Go to **Firestore** ([direct link](https://console.cloud.google.com/firestore))
2. Click **Create Database**
3. Select **Native mode** (not Datastore mode)
4. Choose a location close to your users
5. Click **Create Database**

**Verify:** The Firestore page should show "No collections yet" - this is expected.

---

## Step 3: Configure OAuth Consent Screen

Before creating OAuth credentials, you must configure the consent screen that users see when logging in.

### Using Google Cloud Console

1. Go to **APIs & Services > OAuth consent screen** ([direct link](https://console.cloud.google.com/apis/credentials/consent))

2. **Select User Type:**
   - Choose **Internal** if all users are in your Google Workspace organization
   - Choose **External** if users have personal Gmail accounts or are from multiple organizations

3. Click **Create**

4. **Fill in App Information:**
   - **App name:** `ExtraSuite` (or your preferred name)
   - **User support email:** Your email address
   - **Developer contact email:** Your email address

5. Click **Save and Continue**

6. **Scopes:** Click **Save and Continue** (no additional scopes needed)

7. **Test users (External only):** Add email addresses of users who can test before verification. Click **Save and Continue**.

8. **Summary:** Review and click **Back to Dashboard**

**Verify:** The OAuth consent screen page should show your app name with "Publishing status" displayed.

---

## Step 4: Create OAuth Credentials

Create the OAuth client ID and secret that ExtraSuite uses to authenticate users.

### Using Google Cloud Console

1. Go to **APIs & Services > Credentials** ([direct link](https://console.cloud.google.com/apis/credentials))

2. Click **Create Credentials > OAuth client ID**

3. **Application type:** Select **Web application**

4. **Name:** Enter `ExtraSuite Server`

5. **Authorized redirect URIs:** Click **Add URI** and enter:
   ```
   https://placeholder.example.com/api/auth/callback
   ```
   (You'll update this with your actual URL after deployment in Step 7)

6. Click **Create**

7. **Save your credentials:** A dialog shows your Client ID and Client Secret. Copy both values - you'll need them in Step 6.

!!! warning "Keep your Client Secret secure"
    The Client Secret is like a password. Don't share it or commit it to version control.

**Verify:** The Credentials page should list your new OAuth client under "OAuth 2.0 Client IDs".

---

## Step 5: Create Service Account for ExtraSuite

ExtraSuite needs a service account with permissions to create user service accounts and generate access tokens.

### Using gcloud CLI

**Create the service account:**

```bash
gcloud iam service-accounts create extrasuite-server \
  --display-name="ExtraSuite Server" \
  --project=$PROJECT_ID
```

**Grant required permissions:**

```bash
# Permission to read/write Firestore
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:extrasuite-server@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/datastore.user"

# Permission to create service accounts for users
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:extrasuite-server@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountAdmin"

# Permission to generate access tokens
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:extrasuite-server@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountTokenCreator"
```

### Using Google Cloud Console

**Create the service account:**

1. Go to **IAM & Admin > Service Accounts** ([direct link](https://console.cloud.google.com/iam-admin/serviceaccounts))
2. Click **Create Service Account**
3. **Service account name:** `extrasuite-server`
4. **Service account ID:** Leave as auto-generated (`extrasuite-server`)
5. Click **Create and Continue**
6. Click **Done** (we'll add roles next)

**Grant permissions:**

1. Go to **IAM & Admin > IAM** ([direct link](https://console.cloud.google.com/iam-admin/iam))
2. Click **Grant Access**
3. **New principals:** Enter `extrasuite-server@YOUR_PROJECT_ID.iam.gserviceaccount.com`
4. **Assign roles:** Add these three roles (click **Add Another Role** between each):
   - `Cloud Datastore User`
   - `Service Account Admin`
   - `Service Account Token Creator`
5. Click **Save**

**Verify:** In **IAM & Admin > IAM**, you should see `extrasuite-server@...` with three roles listed.

---

## Step 6: Store Secrets in Secret Manager

Store your OAuth credentials securely using Secret Manager.

### Using gcloud CLI

```bash
# Store OAuth Client ID
echo -n "YOUR_CLIENT_ID" | gcloud secrets create extrasuite-client-id \
  --data-file=- \
  --project=$PROJECT_ID

# Store OAuth Client Secret
echo -n "YOUR_CLIENT_SECRET" | gcloud secrets create extrasuite-client-secret \
  --data-file=- \
  --project=$PROJECT_ID

# Generate and store a random secret key for session signing
echo -n "$(openssl rand -base64 32)" | gcloud secrets create extrasuite-secret-key \
  --data-file=- \
  --project=$PROJECT_ID
```

Replace `YOUR_CLIENT_ID` and `YOUR_CLIENT_SECRET` with the values from Step 4.

**Grant the service account access to read these secrets:**

```bash
for secret in extrasuite-client-id extrasuite-client-secret extrasuite-secret-key; do
  gcloud secrets add-iam-policy-binding $secret \
    --member="serviceAccount:extrasuite-server@$PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor" \
    --project=$PROJECT_ID
done
```

### Using Google Cloud Console

**Create the secrets:**

1. Go to **Security > Secret Manager** ([direct link](https://console.cloud.google.com/security/secret-manager))

2. Click **Create Secret**
   - **Name:** `extrasuite-client-id`
   - **Secret value:** Paste your OAuth Client ID from Step 4
   - Click **Create Secret**

3. Click **Create Secret** again
   - **Name:** `extrasuite-client-secret`
   - **Secret value:** Paste your OAuth Client Secret from Step 4
   - Click **Create Secret**

4. Click **Create Secret** again
   - **Name:** `extrasuite-secret-key`
   - **Secret value:** Generate a random string (you can use an online generator or run `openssl rand -base64 32` in a terminal)
   - Click **Create Secret**

**Grant access to each secret:**

For each of the three secrets:

1. Click the secret name to open it
2. Go to the **Permissions** tab
3. Click **Grant Access**
4. **New principals:** `extrasuite-server@YOUR_PROJECT_ID.iam.gserviceaccount.com`
5. **Role:** `Secret Manager Secret Accessor`
6. Click **Save**

**Verify:** Each secret should show `extrasuite-server@...` in its Permissions tab.

---

## Step 7: Deploy to Cloud Run

Now deploy ExtraSuite using the pre-built Docker image.

### Using gcloud CLI

```bash
gcloud run deploy extrasuite-server \
  --image=asia-southeast1-docker.pkg.dev/thinker41/extrasuite/server:latest \
  --service-account=extrasuite-server@$PROJECT_ID.iam.gserviceaccount.com \
  --region=asia-southeast1 \
  --allow-unauthenticated \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=$PROJECT_ID" \
  --set-env-vars="BASE_DOMAIN=placeholder.run.app" \
  --set-secrets="SECRET_KEY=extrasuite-secret-key:latest" \
  --set-secrets="GOOGLE_CLIENT_ID=extrasuite-client-id:latest" \
  --set-secrets="GOOGLE_CLIENT_SECRET=extrasuite-client-secret:latest" \
  --project=$PROJECT_ID
```

After deployment, get your service URL:

```bash
SERVICE_URL=$(gcloud run services describe extrasuite-server \
  --region=asia-southeast1 \
  --project=$PROJECT_ID \
  --format='value(status.url)')
echo "Your ExtraSuite URL: $SERVICE_URL"
```

**Update BASE_DOMAIN with your actual URL:**

```bash
# Extract domain from URL (removes https://)
DOMAIN=$(echo $SERVICE_URL | sed 's|https://||')

gcloud run services update extrasuite-server \
  --region=asia-southeast1 \
  --update-env-vars="BASE_DOMAIN=$DOMAIN" \
  --project=$PROJECT_ID
```

### Using Google Cloud Console

1. Go to **Cloud Run** ([direct link](https://console.cloud.google.com/run))

2. Click **Create Service**

3. **Container image:** Enter:
   ```
   asia-southeast1-docker.pkg.dev/thinker41/extrasuite/server:latest
   ```

4. **Service name:** `extrasuite-server`

5. **Region:** Select a region (e.g., `asia-southeast1`)

6. **Authentication:** Select **Allow unauthenticated invocations**

7. Expand **Container(s), Volumes, Networking, Security**

8. Click the **Container** tab, then **Variables & Secrets**

9. **Add environment variables:**
   - Click **Add Variable**
   - Name: `GOOGLE_CLOUD_PROJECT`, Value: Your project ID
   - Click **Add Variable**
   - Name: `BASE_DOMAIN`, Value: `placeholder.run.app` (you'll update this after deployment)

10. **Add secrets:**
    - Click **Reference a Secret**
    - Secret: `extrasuite-client-id`, Referenced as: Environment variable, Name: `GOOGLE_CLIENT_ID`
    - Click **Reference a Secret**
    - Secret: `extrasuite-client-secret`, Referenced as: Environment variable, Name: `GOOGLE_CLIENT_SECRET`
    - Click **Reference a Secret**
    - Secret: `extrasuite-secret-key`, Referenced as: Environment variable, Name: `SECRET_KEY`

11. Click the **Security** tab
    - **Service account:** Select `extrasuite-server@YOUR_PROJECT_ID.iam.gserviceaccount.com`

12. Click **Create**

13. After deployment completes, copy the URL shown (e.g., `https://extrasuite-server-xxxxx-as.a.run.app`)

14. **Update BASE_DOMAIN:**
    - Click **Edit & Deploy New Revision**
    - Go to **Variables & Secrets**
    - Update `BASE_DOMAIN` to your actual domain (without `https://`)
    - Click **Deploy**

---

## Step 8: Update OAuth Redirect URI

Update your OAuth credentials with the actual Cloud Run URL.

### Using Google Cloud Console

1. Go to **APIs & Services > Credentials** ([direct link](https://console.cloud.google.com/apis/credentials))

2. Click your OAuth client ID (`ExtraSuite Server`)

3. Under **Authorized redirect URIs:**
   - Remove the placeholder URI
   - Add your actual URI: `https://YOUR_CLOUD_RUN_URL/api/auth/callback`

4. Click **Save**

---

## Verify Your Deployment

Test that everything is working:

### Health Check

```bash
curl https://YOUR_CLOUD_RUN_URL/api/health
```

Expected response:
```json
{"status":"healthy","service":"extrasuite-server"}
```

### Login Test

1. Open your Cloud Run URL in a browser
2. Click **Login with Google**
3. Complete the OAuth flow
4. You should see your service account email and the installation command

**Congratulations!** ExtraSuite is now deployed. Share your Cloud Run URL with users in your organization.

---

## Optional: Restrict Access by Email Domain

Limit who can authenticate to specific email domains:

### Using gcloud CLI

```bash
gcloud run services update extrasuite-server \
  --region=asia-southeast1 \
  --update-env-vars="ALLOWED_EMAIL_DOMAINS=yourcompany.com,partner.org" \
  --project=$PROJECT_ID
```

### Using Google Cloud Console

1. Go to **Cloud Run > extrasuite-server > Edit & Deploy New Revision**
2. Under **Variables & Secrets**, add or update:
   - Name: `ALLOWED_EMAIL_DOMAINS`
   - Value: `yourcompany.com,partner.org` (comma-separated, no spaces)
3. Click **Deploy**

---

## Optional: Custom Domain

Use your own domain instead of the auto-generated Cloud Run URL.

### Using gcloud CLI

```bash
gcloud beta run domain-mappings create \
  --service=extrasuite-server \
  --domain=extrasuite.yourdomain.com \
  --region=asia-southeast1 \
  --project=$PROJECT_ID
```

**Configure DNS:** Add a CNAME record pointing `extrasuite.yourdomain.com` to `ghs.googlehosted.com`

**Wait for SSL certificate:** This can take 15-30 minutes. Check status:

```bash
gcloud beta run domain-mappings describe \
  --domain=extrasuite.yourdomain.com \
  --region=asia-southeast1 \
  --project=$PROJECT_ID
```

**Update BASE_DOMAIN and OAuth redirect URI** with your custom domain after SSL is provisioned.

### Using Google Cloud Console

1. Go to **Cloud Run > extrasuite-server**
2. Click the **Integrations** tab
3. Click **Add Integration > Custom domains**
4. Follow the prompts to add your domain and configure DNS

---

## Environment Variables Reference

| Variable | Required | Description |
|----------|----------|-------------|
| `GOOGLE_CLIENT_ID` | Yes | OAuth 2.0 Client ID |
| `GOOGLE_CLIENT_SECRET` | Yes | OAuth 2.0 Client Secret |
| `GOOGLE_CLOUD_PROJECT` | Yes | Your GCP project ID |
| `SECRET_KEY` | Yes | Random string for signing session tokens |
| `BASE_DOMAIN` | Yes | Your server's domain (without `https://`) |
| `ALLOWED_EMAIL_DOMAINS` | No | Comma-separated list of allowed email domains |
| `TOKEN_EXPIRY_MINUTES` | No | Access token lifetime (default: 60) |
| `SESSION_COOKIE_EXPIRY_MINUTES` | No | Session duration (default: 1440 = 24 hours) |

---

## Continue Your Setup

You've completed the server deployment (Step 1). Return to the Organization Setup guide to continue with user onboarding:

[:octicons-arrow-right-24: Continue to Step 2: Install Your AI Editor](../getting-started/organization-setup.md#step-2-install-your-ai-editor)

---

**Reference:** Review the [Operations Guide](operations.md) for monitoring and troubleshooting.