# Fabric Server

FastAPI backend for the Fabric CLI authentication service.

## Development

```bash
# Install dependencies
uv sync

# Run server
uv run uvicorn fabric.main:app --reload --port 8001

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
| GET | `/api/token/auth?redirect=<url>` | CLI entry point - starts OAuth flow |
| GET | `/api/auth/callback` | OAuth callback - exchanges code for SA token |
| GET | `/api/health` | Health check |
| GET | `/api/health/ready` | Readiness check |

## Environment Variables

See `.env.template` for required configuration:

- `SECRET_KEY` - For signing OAuth state tokens
- `GOOGLE_CLIENT_ID` - Google OAuth client ID
- `GOOGLE_CLIENT_SECRET` - Google OAuth client secret
- `GOOGLE_REDIRECT_URI` - OAuth callback URL
- `GOOGLE_CLOUD_PROJECT` - GCP project for service account creation

## Database

Uses SQLite (`fabric.db`) to store:
- User OAuth credentials (refresh tokens)
- Service account email mappings

The database is created automatically on first run.
