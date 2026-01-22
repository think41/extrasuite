# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ExtraSuite is a headless authentication service for CLI tools accessing Google Workspace APIs. It enables users to obtain short-lived service account tokens for interacting with Google Sheets, Docs, and Drive.

The project consists of three packages:
1. **extrasuite-server** - Containerized fastapi based application to provide employee specific service account and short lived acccess tokens that can be used to call google drive/sheets/docs/slides APIs. It also has minimal UI to allow employees to install skills via a command line installation command.
2. **extrasuite-client** - Package that has a CLI based application to call extrasuite-server on behalf of an LLM based agent and provide it shortlived access tokens. 
3. **website** - mkdocs based documentation website, hosted on github pages, automatically deployed to https://extrasuite.think41.com on every commit to main branch.

## User Flow
1.  User logs in to the **extrasuite-server** using OAuth via their google workspace or gmail account 
2.  This creates a 1:1 service acccount for the employee, and grants this service account read permissions for google drive API and read/write permissions to slides/docs/sheets API. We don't create credentials for this service account.
3.  User copies the `<url> | sh` script to install the skill.
4.  User instructs agent to access the sheet
5.  Agent calls `CredentialsManager` in `extrasuite-client` to get a short lived access token
6.  `CredentialsManager` returns the cached token if available, otherwise
7.  `CredentialsManager` starts a http server on random port, then opens browser to `/api/token/auth?port=<port>`. 
8.  Alternatively, it prints the URL and asks user to authenticate.
9.  User is redirected to google to authenticate, and then redirected back to `/api/auth/callback` after authentication
10. `extrasuite-server` `/api/auth/callback` is invoked. It redirects the browser back to http://localhost:<port>/on-authentication?code=<auth_code> and/or displays the <auth_code> to the user.
11. `CredentialsManager` then calls `/api/token/exchange` with the auth code to get the token. 
12. At this point, `extrasuite-server` impersonates the user specific service account using server credentials. Then it returns a short lived access token back to the `CredentialsManager` in `extrasuite-client`.
13. `CredentialsManager` saves the token + service account email + expiry on disk with appropriate linux permissions.
14. `CredentialsManager` provides the token + service account email to the LLM Agent
15. LLM Agent then writes python code to make API calls to google sides/sheets/docs/drive directly from the user's device
16. Once the token expires, the same flow repeats. If the user has a valid session with `extrasuite-server` - the browser will open but authentication against google server will be skipped. This will result in browser opening and closing in a few seconnds.

## Development Commands

### Client Library
```bash
cd extrasuite-client
uv sync
uv run python -c "from extrasuite_client import ExtraSuiteClient; print('OK')"
uv run ruff check .
```

### Server (FastAPI)
```bash
cd extrasuite-server
uv sync
uv run uvicorn extrasuite_server.main:app --reload --port 8001
uv run pytest tests/ -v
uv run ruff check .
uv run ruff format .
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/auth/login` | Start Oauth authentication flow from the UI to login the user |
| GET | `/api/token/auth?port=<port>` | CLI entry point - starts OAuth (port 1024-65535) |
| POST | `/api/token/exchange` | Exchange auth code for token |
| GET | `/api/auth/callback` | OAuth callback - exchanges code for token |
| GET | `/api/health` | Health check |

## Environment Setup

Copy `extrasuite-server/.env.template` to `extrasuite-server/.env` and configure:
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` - OAuth credentials
- `GOOGLE_CLOUD_PROJECT` - GCP project for service account creation
- `SECRET_KEY` - For signing state tokens

Server uses Application Default Credentials (ADC) for service account management and Firestore access.

## Firestore Setup

Firestore collections are created automatically on first use. No manual setup required.

Enable the Firestore API and create a database:
```bash
gcloud services enable firestore.googleapis.com --project=<project>
gcloud firestore databases create --location=asia-south1 --project=<project>
```

## Token Storage

- **Server-side:** Tokens are not stored on the server. They are generated on demand and returned immediately to the client.
- **Client-side:** Short-lived SA tokens in `~/.config/extrasuite/token.json`

## Testing (Auth Flows)

Use `extrasuite-client/examples/basic_usage.py` to validate the three main flows:

1. **First run (no cache):** token file missing, browser opens, user authenticates.
   ```bash
   rm -f ~/.config/extrasuite/token.json
   PYTHONPATH=extrasuite-client/src python3 extrasuite-client/examples/basic_usage.py \
     --server https://extrasuite.think41.com
   ```
2. **Cached token:** token file present and valid, no browser.
   ```bash
   PYTHONPATH=extrasuite-client/src python3 extrasuite-client/examples/basic_usage.py \
     --server https://extrasuite.think41.com
   ```
3. **Session reuse (no cache, no re-auth):** delete token cache, browser opens, SSO/session skips login.
   ```bash
   rm -f ~/.config/extrasuite/token.json
   PYTHONPATH=extrasuite-client/src python3 extrasuite-client/examples/basic_usage.py \
     --server https://extrasuite.think41.com
   ```

## Exception Handling

The server uses centralized exception handling via FastAPI's `add_exception_handler`. Follow these principles:

1. **Don't catch exceptions just to re-raise as HTTPException(500)** - Let exceptions propagate to the global handler which logs them and returns a safe error response

2. **Only catch exceptions when you can:**
   - Handle them meaningfully (e.g., return `None` to trigger re-auth flow)
   - Add context that would otherwise be missing, then re-raise
   - Handle specific cases (e.g., `HttpError` with status 404 vs other errors)

3. **For non-critical operations**, catch and log but continue (e.g., updating optional metadata)

4. **Use domain exceptions** (`ValueError`, `RefreshError`) rather than `HTTPException` in business logic modules

## CI/CD

Docker images are automatically built and published to Google Artifact Registry via GitHub Actions on every push to `main`.

**Public image location:** `asia-southeast1-docker.pkg.dev/thinker41/extrasuite/server`

**Automatic tagging:**
| Trigger | Tags Created |
|---------|--------------|
| Push to `main` | `main`, `sha-<commit>` |
| Git tag `v*` | `<version>`, `latest` |
| Pull request | Build only (no push) |

### Creating a Release

To create a new release:
```bash
git tag v1.0.0
git push origin v1.0.0
```

GitHub Actions will automatically build and push the image with tags `v1.0.0` and `latest`.

## Internal Deployment (Think41)

The production deployment at `extrasuite.think41.com` is hosted on Cloud Run in project `thinker41`. Deployment is **manual** and decoupled from the GitHub repository.

### Deploy to Production

After pushing changes to `main`, GitHub Actions builds the image. To deploy:

```bash
gcloud run services update extrasuite \
  --project=thinker41 \
  --region=asia-southeast1 \
  --image=asia-southeast1-docker.pkg.dev/thinker41/extrasuite/server:main
```

Or deploy a specific commit:
```bash
gcloud run services update extrasuite \
  --project=thinker41 \
  --region=asia-southeast1 \
  --image=asia-southeast1-docker.pkg.dev/thinker41/extrasuite/server:sha-<commit>
```

### Environment Variables (Production)

Current production configuration:
```
GOOGLE_CLOUD_PROJECT=thinker41
BASE_DOMAIN=extrasuite.think41.com
ALLOWED_EMAIL_DOMAINS=think41.com,recruit41.com,mindlap.dev
DOMAIN_ABBREVIATIONS={"think41.com":"t41","recruit41.com":"r41","mindlap.dev":"mlap"}
```

Secrets are stored in Secret Manager:
- `extrasuite-google-client-id`
- `extrasuite-google-client-secret`
- `extrasuite-secret-key`

### Verify Deployment

```bash
curl https://extrasuite.think41.com/api/health
# Expected: {"status":"healthy","service":"extrasuite-server"}
```

### View Logs

```bash
gcloud run services logs read extrasuite \
  --project=thinker41 \
  --region=asia-southeast1 \
  --limit=50
```

### Rollback

```bash
# List recent revisions
gcloud run revisions list \
  --service=extrasuite \
  --project=thinker41 \
  --region=asia-southeast1

# Route traffic to a previous revision
gcloud run services update-traffic extrasuite \
  --project=thinker41 \
  --region=asia-southeast1 \
  --to-revisions=extrasuite-00040-xyz=100
```
