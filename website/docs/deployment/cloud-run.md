# Deploying ExtraSuite to Cloud Run

This guide walks you through deploying ExtraSuite to Google Cloud Run. It covers all three credential modes from start to finish in a single place.

---

## Step 0: Choose a Credential Mode

Before touching GCP, decide how ExtraSuite will authenticate agents for Gmail, Calendar, and other user-specific APIs. This choice affects nearly every step.

| Mode | `CREDENTIAL_MODE` | How Gmail/Calendar tokens are issued | Who sets it up |
|------|-------------------|--------------------------------------|----------------|
| Service account + Domain-Wide Delegation | `sa+dwd` *(default)* | Server impersonates users via Google DWD | Workspace admin configures DWD once |
| Service account + OAuth | `sa+oauth` | User consents at login; server stores encrypted refresh token | No admin action needed |
| OAuth only (no service accounts) | `oauth` | User consents at login; server stores encrypted refresh token | No admin action needed |

### Which mode should I use?

**Use `sa+dwd` if:**

- You run a Google Workspace organization (not personal Gmail)
- A Workspace admin can configure the Admin Console (one-time, ~10 minutes)
- You want the cleanest security model: no refresh tokens stored, server never touches user data at rest

**Use `sa+oauth` if:**

- You can't or don't want to involve a Workspace admin
- You still want agent edits attributed to the agent's service account in Drive version history

**Use `oauth` if:**

- You want the minimal setup (no service accounts at all)
- This is for personal use or a small team
- You're OK with Drive edits appearing under the user's name, not the agent's

### Tradeoffs

| Aspect | `sa+dwd` | `sa+oauth` | `oauth` |
|--------|----------|------------|---------|
| Workspace admin required | Yes (one-time) | No | No |
| Drive edits attributed to agent | Yes | Yes | No (appear as user) |
| Refresh token stored in Firestore | No | Yes (AES-256-GCM encrypted) | Yes (AES-256-GCM encrypted) |
| Server compromise risk | Impersonation of any user for delegated scopes | Access to encrypted refresh tokens | Access to encrypted refresh tokens |
| Per-user service accounts created | Yes | Yes | No |
| OAuth consent screen scopes | email only | Gmail/Calendar/etc. | Gmail/Calendar/etc. |

> **Note on agent attribution in `oauth` mode:** Edits appear under the user's own identity in Google Drive version history, not under a dedicated agent identity. If attribution matters to your organization, use `sa+dwd` or `sa+oauth`.

---

## Prerequisites

Before you begin:

| Requirement | Details |
|-------------|---------|
| Google Cloud Project | A project where you have **Owner** or **Editor** role, with billing enabled |
| Google Workspace account | For testing authentication after deployment. Personal Gmail works for `sa+oauth`/`oauth` modes. |
| gcloud CLI (optional) | Makes deployment faster. [Install gcloud CLI](https://cloud.google.com/sdk/docs/install) |

Set your project ID in the terminal — you'll use this throughout:

```bash
export PROJECT_ID=your-project-id
```

---

## Step 1: Enable Required APIs

=== "gcloud CLI"

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

    For `sa+oauth` or `oauth` mode, also enable the People API (for Contacts):
    ```bash
    gcloud services enable people.googleapis.com --project=$PROJECT_ID
    ```

=== "Google Cloud Console"

    1. Go to **APIs & Services > Library** ([direct link](https://console.cloud.google.com/apis/library))
    2. Search for and enable each of these APIs:
       - Cloud Run Admin API
       - Cloud Firestore API
       - Identity and Access Management (IAM) API
       - IAM Service Account Credentials API
       - Secret Manager API
       - Google Drive API
       - Google Sheets API
       - Google Docs API
       - Google Slides API

---

## Step 2: Create Firestore Database

ExtraSuite uses Firestore to store user records, session data, and (in OAuth modes) encrypted refresh tokens. Collections are created automatically on first run.

=== "gcloud CLI"

    ```bash
    gcloud firestore databases create \
      --location=asia-southeast1 \
      --project=$PROJECT_ID
    ```

    Replace `asia-southeast1` with your preferred [Firestore location](https://cloud.google.com/firestore/docs/locations). Common choices: `us-central1`, `europe-west1`, `asia-southeast1`.

=== "Google Cloud Console"

    1. Go to **Firestore** ([direct link](https://console.cloud.google.com/firestore))
    2. Click **Create Database**
    3. Select **Native mode** (not Datastore mode)
    4. Choose a location close to your users
    5. Click **Create Database**

---

## Step 3: Configure Google OAuth

This is the most confusing part of the setup. Read this section carefully — the choices you make here affect security and user experience.

### What Google OAuth does here

ExtraSuite uses Google OAuth so users can log in with their Google account. The OAuth client is NOT the same as the service account — these are two separate things:

- **OAuth client** (created in this step): used for the user-facing login page. Lives in **APIs & Services > Credentials**.
- **Service account** (created in Step 4): used by the server to create per-user agent accounts. Lives in **IAM & Admin > Service Accounts**.

### Part A: Configure the OAuth consent screen

The consent screen is what users see when they log in to ExtraSuite.

1. Go to **APIs & Services > OAuth consent screen** ([direct link](https://console.cloud.google.com/apis/credentials/consent))

2. **Choose the User Type:**

    !!! important "Internal vs External — this matters"
        - **Internal**: Only users in your Google Workspace organization can log in. **No Google verification required, even for sensitive scopes.** Choose this for company deployments.
        - **External**: Any Google account can log in. For `sa+oauth`/`oauth` modes (which request Gmail/Calendar scopes), Google requires app verification before going to production — a weeks-long process. Alternatively, leave the app in **Testing** mode (max 100 users, users see an "unverified app" warning).

    | Your situation | Recommended |
    |----------------|-------------|
    | Google Workspace org, all users in same domain | **Internal** |
    | Google Workspace org, users across domains | **External** (or separate project per domain) |
    | Personal use / small team with Gmail accounts | **External** + Testing mode |

3. Click **Create**

4. Fill in **App Information:**
   - **App name:** `ExtraSuite` (or your preferred name)
   - **User support email:** Your email address
   - **Developer contact email:** Your email address

5. Click **Save and Continue**

6. **Scopes — this depends on your credential mode:**

    === "`sa+dwd` mode"

        Click **Save and Continue** — no additional scopes needed. In `sa+dwd` mode, ExtraSuite only needs your email address at login. Gmail/Calendar access happens via server-side domain-wide delegation, not user consent.

    === "`sa+oauth` mode"

        Click **Add or Remove Scopes** and add the scopes your users will consent to. These must match `OAUTH_SCOPES` in Step 6.

        In `sa+oauth` mode, **file operations (Sheets, Docs, Slides, Forms)** still use per-user service accounts — those don't need OAuth scopes. You only need scopes for user-impersonating commands:

        | Short name | Full scope URL | Grants access to |
        |-----------|----------------|-----------------|
        | `gmail.compose` | `.../auth/gmail.compose` | Create and send email drafts |
        | `gmail.readonly` | `.../auth/gmail.readonly` | Read emails |
        | `calendar` | `.../auth/calendar` | Read and write calendar |
        | `contacts.readonly` | `.../auth/contacts.readonly` | Read contacts |
        | `contacts.other.readonly` | `.../auth/contacts.other.readonly` | Read other contacts |
        | `script.projects` | `.../auth/script.projects` | Apps Script |
        | `drive.file` | `.../auth/drive.file` | Create and share Drive files |

        Add only the scopes agents will actually use.

    === "`oauth` mode"

        Click **Add or Remove Scopes** and add the scopes your users will consent to. These must match `OAUTH_SCOPES` in Step 6.

        In `oauth` mode, **all commands** use OAuth — no service accounts. You need scopes for both file operations and user-impersonating commands:

        | Short name | Full scope URL | Grants access to |
        |-----------|----------------|-----------------|
        | `spreadsheets` | `.../auth/spreadsheets` | Read and write Google Sheets |
        | `documents` | `.../auth/documents` | Read and write Google Docs |
        | `presentations` | `.../auth/presentations` | Read and write Google Slides |
        | `forms.body` | `.../auth/forms.body` | Read and write Google Forms |
        | `drive.readonly` | `.../auth/drive.readonly` | List and search Drive files |
        | `gmail.compose` | `.../auth/gmail.compose` | Create and send email drafts |
        | `gmail.readonly` | `.../auth/gmail.readonly` | Read emails |
        | `calendar` | `.../auth/calendar` | Read and write calendar |
        | `contacts.readonly` | `.../auth/contacts.readonly` | Read contacts |
        | `contacts.other.readonly` | `.../auth/contacts.other.readonly` | Read other contacts |
        | `script.projects` | `.../auth/script.projects` | Apps Script |
        | `drive.file` | `.../auth/drive.file` | Create and share Drive files |

        Add only the scopes agents will actually use. Unused scopes increase the user-facing consent screen footprint and are a security risk.

    **Scope name format:** Short names are the URL suffix after `https://www.googleapis.com/auth/`. For example, `spreadsheets` becomes `https://www.googleapis.com/auth/spreadsheets`.

    !!! warning "Sensitive scopes and Google verification"
        Gmail and Calendar scopes are classified as **sensitive** by Google. If you chose **External** app type, your app must go through Google's [OAuth app verification](https://support.google.com/cloud/answer/9110914) process (typically 4-8 weeks) before you can have more than 100 users. **Use Internal app type to avoid this entirely.**

7. Click **Save and Continue** through Test Users and Summary.

### Part B: Create the OAuth client

1. Go to **APIs & Services > Credentials** ([direct link](https://console.cloud.google.com/apis/credentials))

2. Click **Create Credentials > OAuth client ID**

3. **Application type:** Select **Web application**

4. **Name:** Enter `ExtraSuite Server`

5. **Authorized redirect URIs:** Click **Add URI** and enter a placeholder:
   ```
   https://placeholder.example.com/api/auth/callback
   ```
   You'll update this with your actual URL after deployment in Step 8.

6. Click **Create**

7. **Copy your credentials:** A dialog shows your **Client ID** and **Client Secret**. Save both — you'll need them in Step 5.

!!! warning "Keep your Client Secret secure"
    Never commit it to version control or share it in plaintext.

---

## Step 4: Create the Server Service Account

ExtraSuite needs a service account to manage per-user agent accounts and issue access tokens.

!!! note "oauth mode: reduced permissions"
    In `oauth` mode, no per-user service accounts are created. Skip the `serviceAccountAdmin` and `serviceAccountTokenCreator` bindings below.

=== "gcloud CLI"

    **Create the service account:**

    ```bash
    gcloud iam service-accounts create extrasuite-server \
      --display-name="ExtraSuite Server" \
      --project=$PROJECT_ID
    ```

    **Grant Firestore access (all modes):**

    ```bash
    gcloud projects add-iam-policy-binding $PROJECT_ID \
      --member="serviceAccount:extrasuite-server@$PROJECT_ID.iam.gserviceaccount.com" \
      --role="roles/datastore.user"
    ```

    **Grant service account management (sa+dwd and sa+oauth modes only):**

    ```bash
    # Permission to create service accounts for each user
    gcloud projects add-iam-policy-binding $PROJECT_ID \
      --member="serviceAccount:extrasuite-server@$PROJECT_ID.iam.gserviceaccount.com" \
      --role="roles/iam.serviceAccountAdmin"

    # Permission to generate access tokens by impersonating user service accounts
    gcloud projects add-iam-policy-binding $PROJECT_ID \
      --member="serviceAccount:extrasuite-server@$PROJECT_ID.iam.gserviceaccount.com" \
      --role="roles/iam.serviceAccountTokenCreator"
    ```

=== "Google Cloud Console"

    1. Go to **IAM & Admin > Service Accounts** ([direct link](https://console.cloud.google.com/iam-admin/serviceaccounts))
    2. Click **Create Service Account**
    3. **Service account name:** `extrasuite-server`
    4. Click **Create and Continue**, then **Done**

    **Grant roles:**

    1. Go to **IAM & Admin > IAM** ([direct link](https://console.cloud.google.com/iam-admin/iam))
    2. Click **Grant Access**
    3. **New principals:** `extrasuite-server@YOUR_PROJECT_ID.iam.gserviceaccount.com`
    4. Assign roles based on mode:
       - All modes: `Cloud Datastore User`
       - `sa+dwd` and `sa+oauth` modes also: `Service Account Admin` and `Service Account Token Creator`
    5. Click **Save**

---

## Step 5: Store Secrets in Secret Manager

=== "gcloud CLI"

    **Core secrets (all modes):**

    ```bash
    # OAuth client credentials from Step 3
    echo -n "YOUR_CLIENT_ID" | gcloud secrets create extrasuite-client-id \
      --data-file=- --project=$PROJECT_ID

    echo -n "YOUR_CLIENT_SECRET" | gcloud secrets create extrasuite-client-secret \
      --data-file=- --project=$PROJECT_ID

    # Session signing key (generate randomly)
    python -c "import secrets; print(secrets.token_urlsafe(32), end='')" | \
      gcloud secrets create extrasuite-secret-key \
      --data-file=- --project=$PROJECT_ID
    ```

    **Encryption key (sa+oauth and oauth modes only):**

    ```bash
    # AES-256 key for encrypting stored OAuth refresh tokens
    python -c "import secrets; print(secrets.token_hex(32), end='')" | \
      gcloud secrets create extrasuite-oauth-key \
      --data-file=- --project=$PROJECT_ID
    ```

    !!! warning "Key rotation"
        If you change `OAUTH_TOKEN_ENCRYPTION_KEY` later, all stored refresh tokens become undecryptable. Users will need to re-run `extrasuite auth login`.

    **Grant the server SA access to read these secrets:**

    ```bash
    # Core secrets
    for secret in extrasuite-client-id extrasuite-client-secret extrasuite-secret-key; do
      gcloud secrets add-iam-policy-binding $secret \
        --member="serviceAccount:extrasuite-server@$PROJECT_ID.iam.gserviceaccount.com" \
        --role="roles/secretmanager.secretAccessor" \
        --project=$PROJECT_ID
    done

    # OAuth key (sa+oauth and oauth modes only)
    gcloud secrets add-iam-policy-binding extrasuite-oauth-key \
      --member="serviceAccount:extrasuite-server@$PROJECT_ID.iam.gserviceaccount.com" \
      --role="roles/secretmanager.secretAccessor" \
      --project=$PROJECT_ID
    ```

=== "Google Cloud Console"

    1. Go to **Security > Secret Manager** ([direct link](https://console.cloud.google.com/security/secret-manager))

    2. Create these secrets (click **Create Secret** for each):
       - `extrasuite-client-id` → paste your OAuth Client ID from Step 3
       - `extrasuite-client-secret` → paste your OAuth Client Secret from Step 3
       - `extrasuite-secret-key` → paste a random string (run `python -c "import secrets; print(secrets.token_urlsafe(32))"`)
       - `extrasuite-oauth-key` *(sa+oauth/oauth modes only)* → paste a 64-char hex string (run `python -c "import secrets; print(secrets.token_hex(32))"`)

    3. For each secret, open it → **Permissions** tab → **Grant Access** → add `extrasuite-server@YOUR_PROJECT_ID.iam.gserviceaccount.com` with role `Secret Manager Secret Accessor`.

---

## Step 6: Deploy to Cloud Run

=== "sa+dwd (gcloud CLI)"

    ```bash
    gcloud run deploy extrasuite-server \
      --image=asia-southeast1-docker.pkg.dev/thinker41/extrasuite/server:latest \
      --service-account=extrasuite-server@$PROJECT_ID.iam.gserviceaccount.com \
      --region=asia-southeast1 \
      --allow-unauthenticated \
      --set-env-vars="GOOGLE_CLOUD_PROJECT=$PROJECT_ID" \
      --set-env-vars="BASE_DOMAIN=placeholder.run.app" \
      --set-env-vars="CREDENTIAL_MODE=sa+dwd" \
      --set-secrets="SECRET_KEY=extrasuite-secret-key:latest" \
      --set-secrets="GOOGLE_CLIENT_ID=extrasuite-client-id:latest" \
      --set-secrets="GOOGLE_CLIENT_SECRET=extrasuite-client-secret:latest" \
      --project=$PROJECT_ID
    ```

=== "sa+oauth (gcloud CLI)"

    ```bash
    gcloud run deploy extrasuite-server \
      --image=asia-southeast1-docker.pkg.dev/thinker41/extrasuite/server:latest \
      --service-account=extrasuite-server@$PROJECT_ID.iam.gserviceaccount.com \
      --region=asia-southeast1 \
      --allow-unauthenticated \
      --set-env-vars="GOOGLE_CLOUD_PROJECT=$PROJECT_ID" \
      --set-env-vars="BASE_DOMAIN=placeholder.run.app" \
      --set-env-vars="CREDENTIAL_MODE=sa+oauth" \
      --set-env-vars="OAUTH_SCOPES=gmail.compose,gmail.readonly,calendar,contacts.readonly,script.projects" \
      --set-secrets="SECRET_KEY=extrasuite-secret-key:latest" \
      --set-secrets="GOOGLE_CLIENT_ID=extrasuite-client-id:latest" \
      --set-secrets="GOOGLE_CLIENT_SECRET=extrasuite-client-secret:latest" \
      --set-secrets="OAUTH_TOKEN_ENCRYPTION_KEY=extrasuite-oauth-key:latest" \
      --project=$PROJECT_ID
    ```

    In `sa+oauth` mode, file operations (Sheets, Docs, Slides, Forms) use service accounts — only include scopes for Gmail/Calendar/etc. Adjust `OAUTH_SCOPES` to match what you configured in the OAuth consent screen (Step 3).

=== "oauth (gcloud CLI)"

    ```bash
    gcloud run deploy extrasuite-server \
      --image=asia-southeast1-docker.pkg.dev/thinker41/extrasuite/server:latest \
      --service-account=extrasuite-server@$PROJECT_ID.iam.gserviceaccount.com \
      --region=asia-southeast1 \
      --allow-unauthenticated \
      --set-env-vars="GOOGLE_CLOUD_PROJECT=$PROJECT_ID" \
      --set-env-vars="BASE_DOMAIN=placeholder.run.app" \
      --set-env-vars="CREDENTIAL_MODE=oauth" \
      --set-env-vars="OAUTH_SCOPES=spreadsheets,documents,presentations,forms.body,drive.readonly,gmail.compose,gmail.readonly,calendar,contacts.readonly,script.projects" \
      --set-secrets="SECRET_KEY=extrasuite-secret-key:latest" \
      --set-secrets="GOOGLE_CLIENT_ID=extrasuite-client-id:latest" \
      --set-secrets="GOOGLE_CLIENT_SECRET=extrasuite-client-secret:latest" \
      --set-secrets="OAUTH_TOKEN_ENCRYPTION_KEY=extrasuite-oauth-key:latest" \
      --project=$PROJECT_ID
    ```

    In `oauth` mode, all commands use OAuth (no service accounts), so `OAUTH_SCOPES` must include both file operation scopes (`spreadsheets`, `documents`, etc.) and user-impersonating scopes. Adjust `OAUTH_SCOPES` to match what you configured in the OAuth consent screen (Step 3).

=== "Google Cloud Console"

    1. Go to **Cloud Run** ([direct link](https://console.cloud.google.com/run)) → **Create Service**
    2. **Container image:** `asia-southeast1-docker.pkg.dev/thinker41/extrasuite/server:latest`
    3. **Service name:** `extrasuite-server`, **Region:** your preferred region
    4. **Authentication:** Allow unauthenticated invocations
    5. Expand **Container(s), Volumes, Networking, Security**
    6. Under **Variables & Secrets**, add environment variables:
       - `GOOGLE_CLOUD_PROJECT` = your project ID
       - `BASE_DOMAIN` = `placeholder.run.app` (update after deployment)
       - `CREDENTIAL_MODE` = `sa+dwd`, `sa+oauth`, or `oauth`
       - `OAUTH_SCOPES` = (OAuth modes only) — for `sa+oauth`: e.g. `gmail.compose,gmail.readonly,calendar`; for `oauth`: also add `spreadsheets,documents,presentations,forms.body,drive.readonly`. See Step 3 for the full scope table.
    7. Reference secrets:
       - `GOOGLE_CLIENT_ID` ← `extrasuite-client-id`
       - `GOOGLE_CLIENT_SECRET` ← `extrasuite-client-secret`
       - `SECRET_KEY` ← `extrasuite-secret-key`
       - `OAUTH_TOKEN_ENCRYPTION_KEY` ← `extrasuite-oauth-key` *(OAuth modes only)*
    8. Under **Security** tab, set **Service account** to `extrasuite-server@...`
    9. Click **Create**

**Get your service URL:**

```bash
SERVICE_URL=$(gcloud run services describe extrasuite-server \
  --region=asia-southeast1 \
  --project=$PROJECT_ID \
  --format='value(status.url)')
echo "Your ExtraSuite URL: $SERVICE_URL"
```

**Update BASE_DOMAIN with your actual URL:**

```bash
DOMAIN=$(echo $SERVICE_URL | sed 's|https://||')
gcloud run services update extrasuite-server \
  --region=asia-southeast1 \
  --update-env-vars="BASE_DOMAIN=$DOMAIN" \
  --project=$PROJECT_ID
```

---

## Step 7 (sa+dwd only): Configure Domain-Wide Delegation

Skip this step if you chose `sa+oauth` or `oauth` mode.

Domain-wide delegation lets the ExtraSuite server impersonate users for Gmail, Calendar, and other user-specific APIs. A Google Workspace admin must authorize this once.

### Find your service account's Unique ID

!!! important "Client ID ≠ Unique ID"
    The Admin Console needs the service account's **numeric Unique ID**, not the OAuth 2.0 Client ID from Step 3. These are different things.

=== "gcloud CLI"

    ```bash
    gcloud iam service-accounts describe \
      extrasuite-server@$PROJECT_ID.iam.gserviceaccount.com \
      --format='value(uniqueId)' \
      --project=$PROJECT_ID
    ```

=== "Google Cloud Console"

    1. Go to **IAM & Admin > Service Accounts**
    2. Click **extrasuite-server**
    3. Under **Details**, copy the **Unique ID** (a long number like `112345678901234567890`)

### Authorize DWD in Google Workspace Admin Console

A Workspace admin must perform this step. See [Google's official DWD setup guide](https://support.google.com/a/answer/162106) for reference.

1. Go to **Admin Console** → **Security** → **Access and data control** → **API Controls** → **Domain-wide Delegation** ([direct link](https://admin.google.com/ac/owl/domainwidedelegation))
2. Click **Add new**
3. **Client ID:** Paste the **numeric Unique ID** from above (NOT the OAuth client ID)
4. **OAuth scopes:** Add the scopes you want to allow, comma-separated:

    ```
    https://www.googleapis.com/auth/gmail.compose,https://www.googleapis.com/auth/gmail.readonly,https://www.googleapis.com/auth/calendar,https://www.googleapis.com/auth/script.projects
    ```

    Only add scopes you actually want agents to access. See the [OAuth Delegation Scopes table](../../CLAUDE.md) for the full list.

5. Click **Authorize**

### (Optional) Restrict DWD scopes server-side

You can add a second layer of scope enforcement on the server side:

```bash
gcloud run services update extrasuite-server \
  --region=asia-southeast1 \
  --update-env-vars="DELEGATION_SCOPES=gmail.compose,gmail.readonly,calendar" \
  --project=$PROJECT_ID
```

If `DELEGATION_SCOPES` is omitted, the Admin Console configuration is the sole enforcement point.

---

## Step 8: Update OAuth Redirect URI and Verify

### Update the redirect URI

Now that you have your actual service URL, update the OAuth client:

1. Go to **APIs & Services > Credentials**
2. Click your OAuth client ID (`ExtraSuite Server`)
3. Under **Authorized redirect URIs:**
   - Remove the placeholder URI
   - Add: `https://YOUR_CLOUD_RUN_URL/api/auth/callback`
4. Click **Save**

### Verify the deployment

```bash
# Health check
curl https://YOUR_CLOUD_RUN_URL/api/health
# Expected: {"status":"healthy","service":"extrasuite-server"}

# Login test
cd /path/to/extrasuite/client
uv run python -m extrasuite.client login
```

Expected login behavior:
1. Browser opens to the login page
2. User authenticates with Google
3. (`sa+oauth`/`oauth` modes) User sees consent screen with the scopes you configured
4. Browser redirects back and closes
5. Terminal prints confirmation

---

## Optional: Restrict Access by Email Domain

```bash
gcloud run services update extrasuite-server \
  --region=asia-southeast1 \
  --update-env-vars="ALLOWED_EMAIL_DOMAINS=yourcompany.com,partner.org" \
  --project=$PROJECT_ID
```

---

## Optional: Custom Domain

```bash
# Map custom domain
gcloud beta run domain-mappings create \
  --service=extrasuite-server \
  --domain=extrasuite.yourdomain.com \
  --region=asia-southeast1 \
  --project=$PROJECT_ID
```

Add a CNAME record: `extrasuite.yourdomain.com` → `ghs.googlehosted.com`

SSL certificate provisioning takes 15-30 minutes. After it's ready, update `BASE_DOMAIN` and the OAuth redirect URI with your custom domain.

---

## Environment Variables Reference

### Required (all modes)

| Variable | Source | Description |
|----------|--------|-------------|
| `GOOGLE_CLIENT_ID` | Secret | OAuth 2.0 Client ID from Step 3 |
| `GOOGLE_CLIENT_SECRET` | Secret | OAuth 2.0 Client Secret from Step 3 |
| `SECRET_KEY` | Secret | Random string for signing session cookies |
| `GOOGLE_CLOUD_PROJECT` | Env var | Your GCP project ID |
| `BASE_DOMAIN` | Env var | Your server domain (without `https://`) |

### Required for `sa+oauth` and `oauth` modes

| Variable | Source | Description |
|----------|--------|-------------|
| `OAUTH_SCOPES` | Env var | Comma-separated scope short names (e.g. `gmail.compose,calendar`) |
| `OAUTH_TOKEN_ENCRYPTION_KEY` | Secret | 64-char hex AES-256 key for encrypting stored refresh tokens |

### Credential mode

| Variable | Default | Description |
|----------|---------|-------------|
| `CREDENTIAL_MODE` | `sa+dwd` | `sa+dwd`, `sa+oauth`, or `oauth` |
| `DELEGATION_SCOPES` | (all allowed) | DWD-only: comma-separated scope short names to allowlist. No effect in OAuth modes. |

### Access control

| Variable | Default | Description |
|----------|---------|-------------|
| `ALLOWED_EMAIL_DOMAINS` | (all) | Comma-separated email domain allowlist |
| `ADMIN_EMAILS` | (none) | CSV of admin email addresses for session management |

### Session and token settings

| Variable | Default | Description |
|----------|---------|-------------|
| `SESSION_TOKEN_EXPIRY_DAYS` | `30` | Session token lifetime in days |
| `TOKEN_EXPIRY_MINUTES` | `60` | Access token lifetime in minutes |
| `FIRESTORE_DATABASE` | `(default)` | Firestore database name |

### Performance

| Variable | Default | Description |
|----------|---------|-------------|
| `THREAD_POOL_SIZE` | `10` | Max threads for blocking I/O |
| `RATE_LIMIT_AUTH` | `10/minute` | Rate limit for auth endpoints |
| `RATE_LIMIT_TOKEN` | `60/minute` | Rate limit for `/api/auth/token` |
| `RATE_LIMIT_ADMIN` | `30/minute` | Rate limit for admin session endpoints |

---

## Next Steps

- **[Operations Guide](operations.md)** — monitoring, updating, and troubleshooting
- **[IAM Permissions Reference](iam-permissions.md)** — detailed explanation of each required role
- **[Authentication API Specification](../api/auth-spec.md)** — protocol details for building custom integrations
