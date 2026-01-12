# Google Workspace Gateway

Secure OAuth token exchange for CLI tools accessing Google Workspace APIs (Sheets, Docs, Drive).

## What is this?

Google Workspace Gateway (GWG) lets CLI applications obtain short-lived service account tokens to access Google Workspace APIs. Instead of distributing service account keys, users authenticate once via browser, and the gateway handles token management securely.

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
│  │    GoogleWorkspaceGateway.get_token()               │   │
│  │    - Loads cached token from ~/.config/gwg/         │   │
│  │    - If expired, opens browser for OAuth            │   │
│  │    - Returns short-lived SA token                   │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    GWG Server (Cloud Run)                   │
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
pip install google-workspace-gateway
```

### Use in Your Code

```python
from google_workspace_gateway import GoogleWorkspaceGateway

# Create gateway client (server_url is required)
gateway = GoogleWorkspaceGateway(
    server_url="https://your-gwg-server.example.com"
)

# Get a token - opens browser for authentication if needed
token = gateway.get_token()

# Use the token with Google APIs
import gspread
from google.oauth2.credentials import Credentials

creds = Credentials(token)
gc = gspread.authorize(creds)
sheet = gc.open("My Spreadsheet").sheet1
```

## Project Structure

```
google-workspace-gateway/
├── client/                    # Python client library (PyPI)
│   ├── src/google_workspace_gateway/
│   │   ├── __init__.py
│   │   └── gateway.py         # GoogleWorkspaceGateway class
│   └── examples/
│       ├── basic_usage.py
│       └── gsheet_example.py
│
├── server/                    # FastAPI server (Cloud Run)
│   ├── gwg_server/
│   │   ├── main.py           # FastAPI app entry point
│   │   ├── config.py         # Pydantic settings
│   │   ├── database.py       # Async Firestore storage
│   │   ├── google_auth.py    # OAuth callback handler
│   │   ├── token_exchange.py # Token exchange API
│   │   ├── session.py        # Session management
│   │   └── service_account.py # SA creation/impersonation
│   └── Dockerfile.dev
│
├── docs/                      # Documentation
│   ├── deployment.md         # Cloud Run deployment guide
│   └── iam-permissions.md    # Required IAM permissions
│
├── Dockerfile                 # Production container
└── docker-compose.yml         # Local development
```

## Deploying the Server

See [docs/deployment.md](docs/deployment.md) for Cloud Run deployment instructions.

### Prerequisites

1. Google Cloud Project with billing enabled
2. OAuth 2.0 credentials (Web application type)
3. Firestore database for credential storage
4. Required IAM permissions (see [docs/iam-permissions.md](docs/iam-permissions.md))

### Quick Deploy

```bash
# Build and push container
docker build -t gcr.io/$PROJECT_ID/gwg-server:latest .
docker push gcr.io/$PROJECT_ID/gwg-server:latest

# Deploy to Cloud Run
gcloud run deploy gwg-server \
  --image=gcr.io/$PROJECT_ID/gwg-server:latest \
  --region=us-central1 \
  --allow-unauthenticated \
  --set-env-vars="GOOGLE_CLIENT_ID=$CLIENT_ID,GOOGLE_CLIENT_SECRET=$CLIENT_SECRET,GOOGLE_CLOUD_PROJECT=$PROJECT_ID"
```

## Development

### Server Development

```bash
cd server
uv sync
uv run uvicorn gwg_server.main:app --reload --port 8001
```

### Docker Development

```bash
docker-compose --profile dev up dev-server
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
| `GOOGLE_REDIRECT_URI` | No | `http://localhost:8001/api/auth/callback` | OAuth redirect URI |
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
