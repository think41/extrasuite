## Overview

FastAPI server that provides per-user service accounts and short-lived access tokens for Google APIs. Also hosts the UI for skill installation.

## Key Files

| File | Purpose |
|------|---------|
| `src/extrasuite/server/main.py` | FastAPI app entry point, middleware, exception handlers |
| `src/extrasuite/server/api.py` | Route definitions for auth and token endpoints |
| `src/extrasuite/server/token_generator.py` | Service account creation and token generation |
| `src/extrasuite/server/database.py` | Firestore operations for user/service account data |
| `src/extrasuite/server/config.py` | Environment configuration via pydantic-settings |
| `src/extrasuite/server/skills.py` | Skill distribution endpoints |
| `skills/` | Agent skill definitions (SKILL.md files) |

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/auth/login` | Start OAuth flow from UI |
| GET | `/api/token/auth?port=<port>` | CLI entry point - starts OAuth (port 1024-65535) |
| POST | `/api/token/exchange` | Exchange auth code for short-lived token |
| GET | `/api/auth/callback` | OAuth callback handler |
| GET | `/api/health` | Health check |

## Development

### Local Development

```bash
cd server
uv sync
uv run uvicorn extrasuite.server.main:app --reload --port 8001
```

### Environment Setup

Copy `.env.template` to `.env` and configure:
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` - OAuth credentials
- `GOOGLE_CLOUD_PROJECT` - GCP project for service account creation
- `SECRET_KEY` - For signing state tokens

Server uses Application Default Credentials (ADC) for service account management and Firestore access.

### Firestore Setup

Firestore collections are created automatically on first use.

```bash
gcloud services enable firestore.googleapis.com --project=<project>
gcloud firestore databases create --location=asia-south1 --project=<project>
```

### Running Tests

```bash
uv run pytest tests/ -v
uv run ruff check . && uv run ruff format .
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

**Public image:** `asia-southeast1-docker.pkg.dev/thinker41/extrasuite/server`

| Trigger | Tags |
|---------|------|
| Push to branch | `<branch-name>`, `sha-<commit>` |
| Git tag `v*` | `<version>`, `latest` |
| Pull request | Build only (no push) |

### Deploy from a branch

```bash
gcloud run deploy extrasuite-server \
  --image asia-southeast1-docker.pkg.dev/thinker41/extrasuite/server:<branch-name> \
  --region asia-southeast1 \
  --project <your-project>
```

### Creating a Release

```bash
git tag v1.0.0
git push origin v1.0.0
```
