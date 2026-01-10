# Fabric Server

FastAPI backend for the Fabric AI Executive Assistant Portal.

## Development

```bash
# Install dependencies
uv sync

# Run server
uv run uvicorn fabric.main:app --reload --port 8001

# Run tests
uv run pytest

# Lint
uv run ruff check .

# Format
uv run ruff format .
```

## API Endpoints

- `GET /api/health` - Health check
- `GET /api/health/ready` - Readiness check
- `GET /api/auth/google` - Initiate Google OAuth
- `GET /api/auth/callback` - OAuth callback
- `GET /api/auth/me` - Get current user
- `POST /api/auth/logout` - Logout
- `POST /api/service-account/init` - Initialize service account creation
- `GET /api/service-account/download/{token}` - Download credentials
- `GET /api/service-account/status` - Check service account status
