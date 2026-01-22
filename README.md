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
│  │    ExtraSuiteClient.get_token()                     │   │
│  │    - Loads cached token from ~/.config/extrasuite/  │   │
│  │    - If expired, opens browser for OAuth            │   │
│  │    - Returns short-lived SA token                   │   │
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
pip install extrasuite-client
```

### Use in Your Code

```python
from extrasuite_client import ExtraSuiteClient

# Create client (server_url is required)
client = ExtraSuiteClient(
    server_url="https://your-extrasuite-server.example.com"
)

# Get a token - opens browser for authentication if needed
token = client.get_token()

# Use the token with Google APIs
import gspread
from google.oauth2.credentials import Credentials

creds = Credentials(token)
gc = gspread.authorize(creds)
sheet = gc.open("My Spreadsheet").sheet1
```

## Project Structure

```
extrasuite/
├── extrasuite-client/             # Python client library (PyPI)
│   ├── src/extrasuite_client/
│   │   ├── __init__.py
│   │   └── gateway.py             # ExtraSuiteClient class
│   └── examples/
│       └── basic_usage.py
│
├── extrasuite-server/             # FastAPI server (Cloud Run)
│   ├── extrasuite_server/
│   │   ├── main.py               # FastAPI app entry point
│   │   ├── config.py             # Pydantic settings
│   │   ├── database.py           # Async Firestore storage
│   │   ├── google_auth.py        # OAuth callback handler
│   │   ├── token_exchange.py     # Token exchange API
│   │   └── service_account.py    # SA creation/impersonation
│   └── Dockerfile
│
├── docs/                          # Documentation
│   ├── deployment.md             # Cloud Run deployment guide
│   └── iam-permissions.md        # Required IAM permissions
│
└── LICENSE
```

## Deploying the Server

See [docs/deployment.md](docs/deployment.md) for Cloud Run deployment instructions.

### Prerequisites

1. Google Cloud Project with billing enabled
2. OAuth 2.0 credentials (Web application type)
3. Firestore database for credential storage
4. Required IAM permissions (see [docs/iam-permissions.md](docs/iam-permissions.md))

**Note:** End users do not need any GCP project access or IAM roles. See [End-User Permissions](docs/iam-permissions.md#end-user-permissions-important) for details.

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
cd extrasuite-server
uv sync
uv run uvicorn extrasuite_server.main:app --reload --port 8001
```

### Run Tests

```bash
cd extrasuite-server
uv run pytest tests/ -v
uv run ruff check .
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/token/auth?port=<port>` | Start OAuth flow for CLI |
| GET | `/api/auth/callback` | OAuth callback handler |
| GET | `/api/health` | Health check |
| GET | `/api/health/ready` | Readiness check |

## Environment Variables

### Server

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GOOGLE_CLIENT_ID` | Yes | - | OAuth 2.0 client ID |
| `GOOGLE_CLIENT_SECRET` | Yes | - | OAuth 2.0 client secret |
| `GOOGLE_CLOUD_PROJECT` | Yes | - | GCP project for service accounts |
| `SECRET_KEY` | Yes | - | Key for signing state tokens |
| `SERVER_URL` | No | `http://localhost:8001` | Base URL for server (OAuth redirect URI computed from this) |
| `FIRESTORE_DATABASE` | No | `(default)` | Firestore database name |
| `ALLOWED_EMAIL_DOMAINS` | No | - | Comma-separated list of allowed email domains |
| `ENVIRONMENT` | No | `development` | `development` or `production` |

## Security

- **Short-lived tokens**: Service account tokens expire after 1 hour
- **Localhost redirects only**: CLI callbacks restricted to localhost
- **OAuth state tokens**: CSRF protection with time-limited state (10 min)
- **Server-side credential storage**: Refresh tokens stored securely in Firestore
- **No private keys**: Service account keys are never downloaded

## License

MIT License - see [LICENSE](LICENSE) for details.
