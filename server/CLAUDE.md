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

### v2 Session Token Protocol (current)

**Phase 1 — Session establishment** (once per 30 days, browser required):

- `GET /api/token/auth?port=N` — existing endpoint, reused as Phase 1 start. Redirects to Google OAuth. On success redirects to `localhost:{port}/on-authentication?code=X`.
- `POST /api/auth/session/exchange` — exchange auth code for 30-day session token. Stores device fingerprint in Firestore `session_tokens` collection.

**Phase 2 — Headless access token exchange** (every command, no browser):

- `POST /api/auth/token` — validate session token, log request to `access_logs`, dispatch to `TokenGenerator.generate_token()` (SA) or `TokenGenerator.generate_delegated_token()` (DWD) based on pseudo-scope.

**Admin session management:**

- `GET /api/admin/sessions?email=<email>` — list active sessions
- `DELETE /api/admin/sessions/<hash>` — revoke a session
- `POST /api/admin/sessions/revoke-all?email=<email>` — revoke all sessions

All admin endpoints use `Authorization: Bearer <session_token>`. Self-service (own sessions) or admin (`ADMIN_EMAILS` env var).

### v1 Legacy Flows [Deprecated]

These endpoints still work but return `Deprecation: true` and `Sunset: 2026-12-31` headers.

**[Deprecated] Service account flow** (`get_token` in client, legacy):

- `GET /api/token/auth` → `_generate_token_and_redirect()` (api.py)
- `GET /api/auth/callback` (api.py): handles Google OAuth callback
- `POST /api/token/exchange` (api.py): validates auth code, generates SA token

**[Deprecated] Delegation flow** (`get_oauth_token` in client, legacy):

- `GET /api/delegation/auth` (api.py): validates scopes, starts OAuth
- `POST /api/delegation/exchange` (api.py): validates code, generates DWD token

Allowed delegation scopes: `gmail.compose`, `calendar`, `script.projects`, `drive.file`.

### Firestore Collections

| Collection | Document ID | TTL field | Purpose |
|---|---|---|---|
| `users` | email (encoded) | none | user → service account mapping |
| `oauth_states` | state token | `expires_at` (10 min) | CSRF protection |
| `auth_codes` | auth code | `expires_at` (120 sec) | single-use auth delivery |
| `delegation_logs` | auto | `expires_at` (30 days) | legacy DWD audit trail |
| `session_tokens` | SHA-256(raw_token) | `expires_at` (60 days) | 30-day session tokens + 30-day audit |
| `access_logs` | auto | `expires_at` (30 days) | per-request access audit |

### New Environment Variables

| Variable | Default | Description |
|---|---|---|
| `SESSION_TOKEN_EXPIRY_DAYS` | 30 | Session token lifetime in days |
| `ADMIN_EMAILS` | (empty) | CSV of admin email addresses |

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
