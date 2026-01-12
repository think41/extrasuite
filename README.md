# Fabric - AI Executive Assistant CLI Authentication

Fabric is Think41 Technologies' headless authentication service for AI CLI tools. It enables employees to obtain short-lived service account tokens for interacting with Google Docs/Sheets via CLI tools (`gdocs`, `gsheets`).

## Overview

The AI Executive Assistant (EA) is a service account that allows employees to interact with Google Docs and Sheets via command-line tools. Each employee gets their own EA that:

- Has **no access by default**
- Only accesses documents **explicitly shared** with it
- Provides **short-lived tokens** (1 hour) for CLI tools
- Can have access **revoked at any time** by unsharing documents

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    CLI Tool (Python)                         │
│  ┌─────────────────────────────────────────────────────┐   │
│  │    fabric_auth.get_token()                           │   │
│  │    - Loads cached token from ~/.config/fabric/       │   │
│  │    - If expired, opens browser for OAuth             │   │
│  │    - Returns short-lived SA token                    │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Fabric API Server                         │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  /api/token/auth     - CLI entry point (→ Google)    │   │
│  │  /api/auth/callback  - OAuth callback (→ CLI)        │   │
│  │  /api/health/*       - Health checks                 │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                Google Cloud Project                          │
│  - Service Account creation (IAM API)                       │
│  - OAuth for user authentication                            │
│  - SA token impersonation                                   │
└─────────────────────────────────────────────────────────────┘
```

## Authentication Flow

1. CLI calls `get_token()` from `cli/fabric_auth.py`
2. Checks for cached token in `~/.config/fabric/token.json`
3. If no valid token, starts localhost callback server
4. Opens browser to `/api/token/auth?redirect=http://localhost:<port>/callback`
5. User authenticates via Google OAuth
6. Server stores OAuth credentials, creates/retrieves user's service account
7. Server impersonates SA to generate short-lived token (1 hour)
8. Browser redirects to localhost with token
9. CLI saves token and returns it

## Quick Start

### CLI Usage

```python
from fabric_auth import get_token

# Get a valid access token (handles auth automatically)
token = get_token()

# Use with gspread
import gspread
from google.oauth2.credentials import Credentials

creds = Credentials(token)
gc = gspread.authorize(creds)
sheet = gc.open("My Spreadsheet").sheet1
```

### Server Setup

```bash
cd server
uv sync
cp .env.template .env
# Edit .env with your credentials
uv run uvicorn fabric.main:app --reload --port 8001
```

## Environment Variables

```bash
# Server
PORT=8001
ENVIRONMENT=development
SECRET_KEY=your-secret-key

# Google OAuth (from Google Cloud Console)
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_REDIRECT_URI=http://localhost:8001/api/auth/callback

# Google Cloud Project (for creating service accounts)
GOOGLE_CLOUD_PROJECT=your-project-id
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/token/auth?redirect=<url>` | Start OAuth flow for CLI |
| GET | `/api/auth/callback` | OAuth callback handler |
| GET | `/api/health` | Health check |
| GET | `/api/health/ready` | Readiness check |

## Project Structure

```
fabric/
├── cli/                        # CLI reference implementation
│   ├── fabric_auth.py         # get_token() entry point
│   ├── example_gsheet.py      # Usage example
│   └── README.md              # CLI documentation
├── server/                     # FastAPI backend
│   ├── fabric/                # Application code
│   │   ├── main.py           # FastAPI app
│   │   ├── config.py         # Settings
│   │   ├── database.py       # SQLAlchemy models
│   │   ├── logging.py        # Loguru setup
│   │   ├── auth/             # OAuth handlers
│   │   ├── token_exchange/   # Token exchange API
│   │   └── health/           # Health checks
│   ├── tests/                # Test suite
│   └── pyproject.toml        # Dependencies
├── Dockerfile                 # Production container
├── docker-compose.yml         # Container orchestration
└── README.md                  # This file
```

## Docker Deployment

```bash
# Build and run
docker build -t fabric:latest .
docker run -p 8001:8001 \
  -e SECRET_KEY=your-secret-key \
  -e GOOGLE_CLIENT_ID=your-client-id \
  -e GOOGLE_CLIENT_SECRET=your-client-secret \
  -e GOOGLE_CLOUD_PROJECT=your-project-id \
  fabric:latest

# Or with docker-compose
docker-compose up -d fabric
```

## Development

```bash
# Server
cd server
uv sync
uv run uvicorn fabric.main:app --reload --port 8001
uv run pytest tests/ -v
uv run ruff check .
uv run ruff format .

# Docker development
docker-compose --profile dev up dev-server
```

## Security

- **Short-lived tokens**: SA tokens expire after 1 hour
- **Localhost redirects only**: CLI callbacks restricted to localhost
- **OAuth state tokens**: CSRF protection with time-limited state
- **Server-side credential storage**: Refresh tokens stored securely in DB
- **No private keys**: Service account keys are never downloaded

## License

Proprietary - Think41 Technologies
