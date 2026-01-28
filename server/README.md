# ExtraSuite Server

FastAPI backend for ExtraSuite - secure OAuth token exchange for CLI tools.

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
| GET | `/api/token/auth?port=<port>` | CLI entry point - starts OAuth flow |
| GET | `/api/auth/callback` | OAuth callback - exchanges code for SA token |
| GET | `/api/health` | Health check |
| GET | `/api/health/ready` | Readiness check |

## Environment Variables

See `.env.template` for required configuration:

| Variable | Required | Description |
|----------|----------|-------------|
| `SECRET_KEY` | Yes (production) | For signing OAuth state tokens |
| `GOOGLE_CLIENT_ID` | Yes | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | Yes | Google OAuth client secret |
| `GOOGLE_CLOUD_PROJECT` | Yes | GCP project for service account creation |
| `SERVER_URL` | No | Base URL for server (default: http://localhost:8001) |
| `ALLOWED_EMAIL_DOMAINS` | No | Comma-separated list of allowed email domains |
| `FIRESTORE_DATABASE` | No | Firestore database name (default: `(default)`) |

## Database

Uses Firestore to store:
- User OAuth credentials (refresh tokens)
- Service account email mappings
- OAuth state tokens (CSRF protection)

Collections are created automatically on first use.
