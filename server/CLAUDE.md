## Overview

FastAPI server that authenticates users in a Google Workspace domain and issues short-lived access tokens for AI agents. Agents call Google APIs either via a per-user service account (Sheets, Docs, Slides, Drive) or via a scoped delegated token when service accounts are insufficient (Gmail, Calendar, Apps Script).

## Key Documents

| Document | What it covers |
|----------|---------------|
| [`website/docs/api/auth-spec.md`](../website/docs/api/auth-spec.md) | Full protocol spec: endpoints, request/response format, security requirements, sequence diagrams |
| [`website/docs/security.md`](../website/docs/security.md) | Security model, token lifetimes, delegation risks, audit trail |
| [`client/src/extrasuite/client/credentials.py`](../client/src/extrasuite/client/credentials.py) | Client-side: local server, browser open, token caching — the other half of the flow |

## Key Files

| File | Purpose |
|------|---------|
| `src/extrasuite/server/api.py` | Route definitions for all auth and token endpoints |
| `src/extrasuite/server/token_generator.py` | Service account creation and token generation |
| `src/extrasuite/server/database.py` | Firestore: session state, auth codes, user→SA mapping |
| `src/extrasuite/server/main.py` | FastAPI app, middleware, exception handlers |
| `src/extrasuite/server/config.py` | Environment config via pydantic-settings |

## Auth Flows

See [`auth-spec.md`](../website/docs/api/auth-spec.md) for the full protocol. The server-side implementation maps as follows:

**Service account flow** (`get_token` in the client):

- `GET /api/token/auth` → `_generate_token_and_redirect()` (api.py): ensures SA exists, generates single-use auth code, redirects to `localhost:{port}/on-authentication?code=X`
- `GET /api/auth/callback` (api.py): handles Google OAuth callback, validates ID token + email domain, sets session cookie, then calls `_generate_token_and_redirect()`
- `POST /api/token/exchange` (api.py): validates auth code (single-use, 2-min TTL via Firestore), calls `TokenGenerator.generate_token_for_service_account()`
- `TokenGenerator.ensure_service_account(user_email)` (token_generator.py): looks up or creates per-user SA in IAM; `_do_impersonation()` uses `google.auth.impersonated_credentials` to produce a 1-hour token

**Delegation flow** (`get_oauth_token` in the client, for Gmail/Calendar/Apps Script):

- `GET /api/delegation/auth` (api.py): validates scopes against server allowlist, then same redirect pattern as above
- `POST /api/delegation/exchange` (api.py): validates code, calls `TokenGenerator.generate_delegated_token()`
- `TokenGenerator.generate_delegated_token(user_email, scopes)` (token_generator.py): builds a JWT (`iss`=server SA, `sub`=user email), signs via IAM `signBlob`, exchanges for access token at Google's token endpoint. All delegation requests are logged (user, scopes, reason, timestamp).

Allowed delegation scopes: `gmail.compose`, `calendar`, `script.projects`, `drive.file`.

## Exception Handling

Centralized via FastAPI's `add_exception_handler`. Principles:

- Let unexpected exceptions propagate to the global handler — it logs them and returns a safe error response
- Only catch when you can handle meaningfully, add context before re-raising, or handle specific cases (e.g. `HttpError` 404 vs others)
- Use domain exceptions (`ValueError`, `RefreshError`, `TokenGeneratorError`) in business logic — not `HTTPException`

## Development

```bash
cd server
uv sync
uv run uvicorn extrasuite.server.main:app --reload --port 8001
```

Copy `.env.template` to `.env`:
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` — OAuth credentials
- `GOOGLE_CLOUD_PROJECT` — GCP project for SA creation and Firestore
- `SECRET_KEY` — signs state tokens

Server uses Application Default Credentials (ADC) for SA management and Firestore. Firestore collections are created automatically on first use:
```bash
gcloud services enable firestore.googleapis.com --project=<project>
gcloud firestore databases create --location=asia-south1 --project=<project>
```

## CI/CD

Docker images published to `asia-southeast1-docker.pkg.dev/thinker41/extrasuite/server` on every push to `main`. Tags: `<branch-name>`, `sha-<commit>`. Git tag `v*` → `<version>` + `latest`.

```bash
gcloud run deploy extrasuite-server \
  --image asia-southeast1-docker.pkg.dev/thinker41/extrasuite/server:<branch-name> \
  --region asia-southeast1
```

## Future: Simplify the Server ([#20](https://github.com/think41/extrasuite/issues/20))

The server currently also distributes skills and generates per-user install scripts. This is incidental complexity. The direction is to strip it down to auth only — public skills, no install scripts, no `gateway.json` seeding. See [issue #20](https://github.com/think41/extrasuite/issues/20).
