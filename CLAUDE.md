# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ExtraSuite is a headless authentication service for CLI tools accessing Google Workspace APIs. It enables users to obtain short-lived service account tokens for interacting with Google Sheets, Docs, and Drive.

The project consists of two packages:
1. **Client Library** (`extrasuite-client`) - PyPI package for CLI tools
2. **Server** (`extrasuite-server`) - FastAPI server for Cloud Run deployment

## Architecture

**Client Flow:**
1. CLI creates `ExtraSuiteClient(server_url="...")` instance
2. Calls `client.get_token()` to get a valid access token
3. If cached token exists and is valid, return it
4. Otherwise, start localhost callback server and open browser
5. User authenticates via Google OAuth on the server
6. Server redirects to localhost with auth code
7. CLI exchanges auth code for token via POST to `/api/token/exchange`
8. CLI saves token to `~/.config/extrasuite/token.json`

**Server Flow:**
1. Receive auth request at `/api/token/auth?port=<port>`
2. If user has valid session, proceed to step 5
3. Otherwise, redirect to Google OAuth
4. On callback, verify identity and set session cookie
5. Create service account if needed (email→SA mapping stored in Firestore)
6. Generate auth code, store with SA email, redirect to `http://localhost:<port>/on-authentication?code=...`
7. CLI exchanges auth code for token via POST to `/api/token/exchange`
8. Server generates token on-demand via SA impersonation (token never stored)

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

### Docker (Local Development)
```bash
# Build locally from repo root (includes skills/ folder)
docker build -t extrasuite-server:latest .
docker run -p 8080:8080 --env-file extrasuite-server/.env extrasuite-server:latest

# Or pull the pre-built image from GHCR
docker pull ghcr.io/think41/extrasuite-server:latest
docker run -p 8080:8080 --env-file extrasuite-server/.env ghcr.io/think41/extrasuite-server:latest
```

## Key Files

### Client Library
- `extrasuite-client/src/extrasuite_client/__init__.py` - Package exports
- `extrasuite-client/src/extrasuite_client/gateway.py` - `ExtraSuiteClient` class
- `extrasuite-client/examples/` - Usage examples

### Server
- `extrasuite-server/extrasuite_server/main.py` - FastAPI app entry point
- `extrasuite-server/extrasuite_server/config.py` - Pydantic settings from environment
- `extrasuite-server/extrasuite_server/database.py` - Async Firestore storage
- `extrasuite-server/extrasuite_server/api.py` - OAuth callback handler and token exchange API
- `extrasuite-server/extrasuite_server/token_generator.py` - SA creation and impersonation
- `extrasuite-server/extrasuite_server/logging.py` - Structured logging configuration

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/token/auth?port=<port>` | CLI entry point - starts OAuth (port 1024-65535) |
| POST | `/api/token/exchange` | Exchange auth code for token |
| GET | `/api/auth/callback` | OAuth callback - exchanges code for token |
| GET | `/api/health` | Health check |
| GET | `/api/health/ready` | Readiness check |

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

- **Server-side:** Session cookies and email→SA mappings in Firestore
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

## Package Names

| Package | PyPI/Import Name | Directory |
|---------|------------------|-----------|
| Client | `extrasuite-client` / `extrasuite_client` | `extrasuite-client/` |
| Server | `extrasuite-server` / `extrasuite_server` | `extrasuite-server/` |

## Security Configuration

### Email Domain Allowlist

Restrict authentication to specific email domains by setting:
```bash
ALLOWED_EMAIL_DOMAINS=example.com,company.org
```

If not set, all domains are allowed.

### Firestore TTL Policies

Configure TTL policies for automatic cleanup of expired documents:

**Short-lived collections (oauth_states, auth_codes):**
```bash
# OAuth states expire after 10 minutes
gcloud firestore fields ttls update expire_at \
  --collection-group=oauth_states \
  --enable-ttl \
  --project=<project>

# Auth codes expire after 120 seconds
gcloud firestore fields ttls update expire_at \
  --collection-group=auth_codes \
  --enable-ttl \
  --project=<project>
```

**User records (optional, for inactive user cleanup):**
```bash
# Users expire after 7 days of inactivity
gcloud firestore fields ttls update updated_at \
  --collection-group=users \
  --enable-ttl \
  --project=<project>
```

Note: Firestore TTL deletion is eventual (typically within 24 hours). The application also validates expiration in-code for immediate enforcement.

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

Docker images are automatically built and published to GitHub Container Registry (GHCR) via GitHub Actions.

**Image location:** `ghcr.io/think41/extrasuite-server`

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

## Known Limitations

### Service Account Quota

ExtraSuite creates one service account per user. GCP projects have a quota of 100 service accounts by default (can be increased to ~200).

For deployments expecting more users:
- Monitor SA count: `gcloud iam service-accounts list --project=<project> | wc -l`
- Request quota increase via GCP console
- Consider implementing SA pooling for high-scale deployments
