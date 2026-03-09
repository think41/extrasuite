# ExtraSuite Server

FastAPI backend for ExtraSuite's v2 session-token authentication flow.

## Development

```bash
# Install dependencies
uv sync

# Run server
uv run uvicorn extrasuite.server.main:app --reload --port 8001

# Run tests
uv run pytest tests/ -v

# Lint
uv run ruff check .

# Format
uv run ruff format .
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/token/auth?port=<port>` | Phase 1 browser entry point |
| GET | `/api/auth/login` | Phase 1 browser entry point (UI flow) |
| GET | `/api/auth/callback` | Google OAuth callback |
| POST | `/api/auth/session/exchange` | Exchange auth code for 30-day session token |
| POST | `/api/auth/token` | Exchange session token for Google credential(s) |
| POST | `/api/auth/oauth/revoke` | Revoke stored OAuth refresh token (OAuth modes only) |
| GET | `/api/admin/sessions?email=<email>` | List active sessions (self-service or admin) |
| DELETE | `/api/admin/sessions/<hash>` | Revoke a session by hash |
| POST | `/api/admin/sessions/revoke-all?email=<email>` | Revoke all sessions for an email |
| GET | `/api/health` | Health check (Firestore connectivity) |

## Environment Variables

See `.env.template` for full configuration. Key variables:

### Required

| Variable | Description |
|----------|-------------|
| `SECRET_KEY` | For signing session cookies |
| `GOOGLE_CLIENT_ID` | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | Google OAuth client secret |
| `GOOGLE_CLOUD_PROJECT` | GCP project for service account creation and Firestore |

### Server Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `BASE_DOMAIN` | (none) | Server domain (e.g., `extrasuite.example.com`). Derives SERVER_URL and cookie domain. |
| `SERVER_URL` | `http://localhost:8001` | Full server URL (overrides BASE_DOMAIN) |
| `ALLOWED_EMAIL_DOMAINS` | (none, all allowed) | Comma-separated email domain allowlist |
| `FIRESTORE_DATABASE` | `(default)` | Firestore database name |

### Credential Mode

| Variable | Default | Description |
|----------|---------|-------------|
| `CREDENTIAL_MODE` | `sa+dwd` | Auth strategy: `sa+dwd`, `sa+oauth`, or `oauth`. See below. |
| `OAUTH_SCOPES` | (none) | Required when `CREDENTIAL_MODE != sa+dwd`. Comma-separated short scope names. |
| `OAUTH_TOKEN_ENCRYPTION_KEY` | (none) | Required when `CREDENTIAL_MODE != sa+dwd`. 64-char hex AES-256 key. |
| `DELEGATION_SCOPES` | (none, all allowed) | DWD scope allowlist. Only applies in `sa+dwd` mode. |

**Credential modes:**
- `sa+dwd` — per-user service account for files; domain-wide delegation for Gmail/Calendar/etc. Requires Workspace admin to enable DWD.
- `sa+oauth` — per-user service account for files; user OAuth token for Gmail/Calendar/etc. No DWD needed.
- `oauth` — user OAuth token for all commands. No service accounts or DWD needed. Edits appear as the user (not the agent) in Drive version history.

### Session and Token Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `SESSION_TOKEN_EXPIRY_DAYS` | `30` | Session token lifetime in days |
| `TOKEN_EXPIRY_MINUTES` | `60` | Access token lifetime in minutes |
| `ADMIN_EMAILS` | (none) | CSV of admin email addresses for session management |

### Performance

| Variable | Default | Description |
|----------|---------|-------------|
| `THREAD_POOL_SIZE` | `10` | Max threads for blocking I/O (DWD signing, OAuth exchange, SA impersonation) |
| `RATE_LIMIT_AUTH` | `10/minute` | Rate limit for auth endpoints |
| `RATE_LIMIT_TOKEN` | `60/minute` | Rate limit for `/api/auth/token` |
| `RATE_LIMIT_ADMIN` | `30/minute` | Rate limit for admin session endpoints |

## Database

Uses Firestore to store:
- Service account email mappings (and encrypted OAuth refresh tokens in OAuth modes)
- OAuth state tokens (10-minute TTL)
- Auth codes (2-minute TTL)
- Session token hashes (30-day active + 30-day audit TTL)
- Access logs (30-day TTL)

Firestore TTL policies and composite indexes are created automatically at server startup. Grant the server's service account `roles/datastore.indexAdmin` to enable this; otherwise create them manually (see `firestore_setup.py`).
