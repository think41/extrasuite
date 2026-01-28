# ExtraSuite

Secure OAuth token exchange for CLI tools accessing Google Workspace APIs (Sheets, Docs, Drive).

## What is this?

ExtraSuite lets CLI applications obtain short-lived service account tokens to access Google Workspace APIs. Instead of distributing service account keys, users authenticate once via browser, and the server handles token management securely.

**Key Benefits:**
- **No service account keys** - Tokens are short-lived (1 hour) and never stored locally
- **User-scoped access** - Each user gets their own service account with minimal permissions
- **Browser-based auth** - OAuth flow handles authentication securely
- **Audit-friendly** - Service accounts include owner metadata for traceability

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    CLI Tool (Python)                        │
│  ┌─────────────────────────────────────────────────────┐   │
│  │    python -m extrasuite.client login                │   │
│  │    - Opens browser for OAuth authentication         │   │
│  │    - Caches token securely in OS keyring            │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                ExtraSuite Server (Cloud Run)                │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  /api/token/auth     - CLI entry point (→ Google)   │   │
│  │  /api/auth/callback  - OAuth callback (→ CLI)       │   │
│  │  /api/health/*       - Health checks                │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                Google Cloud Project                         │
│  - Service Account creation (IAM API)                      │
│  - OAuth for user authentication                           │
│  - SA token impersonation                                  │
│  - Firestore for credential storage                        │
└─────────────────────────────────────────────────────────────┘
```

## Quick Start

### Install the Client Library

```bash
pip install extrasuite
```

### CLI Authentication

```bash
# Login (opens browser for OAuth)
python -m extrasuite.client login

# Or using the console script
extrasuite login

# Logout (clears cached credentials)
python -m extrasuite.client logout
```

### Use in Your Code

```python
from extrasuite.client import authenticate

# Get a token - opens browser for authentication if needed
token = authenticate()

# Use the token with Google APIs
import gspread
from google.oauth2.credentials import Credentials

creds = Credentials(token.access_token)
gc = gspread.authorize(creds)
sheet = gc.open("My Spreadsheet").sheet1
```

## Project Structure

```
extrasuite/
├── client/                       # Python client library (PyPI: extrasuite)
│   ├── src/extrasuite/client/
│   │   ├── __init__.py
│   │   ├── __main__.py           # CLI: login/logout commands
│   │   └── credentials.py        # CredentialsManager class
│   └── pyproject.toml
│
├── server/                       # FastAPI server (Cloud Run)
│   ├── src/extrasuite/server/
│   │   ├── main.py               # FastAPI app entry point
│   │   ├── config.py             # Pydantic settings
│   │   ├── database.py           # Async Firestore storage
│   │   ├── api.py                # OAuth callback handler
│   │   └── token_generator.py    # SA creation/impersonation
│   └── Dockerfile
│
├── extrasheet/                   # Google Sheets to file converter
├── extraslide/                   # Google Slides to file converter
└── website/                      # MkDocs documentation
```

## Deploying the Server

See the [deployment documentation](https://extrasuite.think41.com/deployment/) for Cloud Run deployment instructions.

### Prerequisites

1. Google Cloud Project with billing enabled
2. OAuth 2.0 credentials (Web application type)
3. Firestore database for credential storage
4. Required IAM permissions

### Quick Deploy

```bash
# Deploy to Cloud Run using pre-built image from GitHub Container Registry
gcloud run deploy extrasuite-server \
  --image=ghcr.io/think41/extrasuite-server:latest \
  --service-account=extrasuite-server@$PROJECT_ID.iam.gserviceaccount.com \
  --region=us-central1 \
  --allow-unauthenticated \
  --set-env-vars="ENVIRONMENT=production,GOOGLE_CLOUD_PROJECT=$PROJECT_ID" \
  --set-secrets="GOOGLE_CLIENT_ID=extrasuite-client-id:latest,GOOGLE_CLIENT_SECRET=extrasuite-client-secret:latest,SECRET_KEY=extrasuite-secret-key:latest"
```

## Development

### Server Development

```bash
cd server
uv sync
uv run uvicorn extrasuite.server.main:app --reload --port 8001
```

### Client Development

```bash
cd client
uv sync
uv run pytest tests/ -v
```

### Run Tests

```bash
cd server
uv run pytest tests/ -v
uv run ruff check .
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/token/auth?port=<port>` | Start OAuth flow for CLI |
| POST | `/api/token/exchange` | Exchange auth code for token |
| GET | `/api/auth/callback` | OAuth callback handler |
| GET | `/api/health` | Health check |

## Security

- **Short-lived tokens**: Service account tokens expire after 1 hour
- **Localhost redirects only**: CLI callbacks restricted to localhost
- **OAuth state tokens**: CSRF protection with time-limited state (10 min)
- **Secure token storage**: Tokens stored in OS keyring (macOS Keychain, Windows Credential Locker, Linux Secret Service)
- **No private keys**: Service account keys are never downloaded

## License

MIT License - see [LICENSE](LICENSE) for details.
