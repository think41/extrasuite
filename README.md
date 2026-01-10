# Fabric - AI Executive Assistant Portal

Fabric is Think41 Technologies' collection of AI skills, agents, utilities, and tools to make employees and engineering teams productive. This portal enables employees to set up their AI Executive Assistant (a Google service account) through a self-service workflow.

## Overview

The AI Executive Assistant (EA) is a service account that allows employees to interact with Google Docs and Sheets via command-line tools. Each employee gets their own EA that:

- Has **no access by default**
- Only accesses documents **explicitly shared** with it
- Can be used with `gdocs` and `gsheets` CLI tools
- Can have access **revoked at any time** by unsharing documents

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Employee's Browser                        │
│  ┌─────────────────────────────────────────────────────┐   │
│  │         Fabric Portal (React Frontend)               │   │
│  │  - Google OAuth login                                │   │
│  │  - Setup instructions & commands                     │   │
│  │  - FAQ & documentation                               │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI Backend                           │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  /api/auth/*           - Google OAuth endpoints      │   │
│  │  /api/service-account/* - SA creation endpoints      │   │
│  │  /api/health/*         - Health checks               │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                Google Cloud Project                          │
│  - Service Account creation (IAM API)                       │
│  - OAuth credentials                                        │
│  - Drive/Docs/Sheets APIs enabled                           │
└─────────────────────────────────────────────────────────────┘
```

## Technology Stack

| Component | Technology |
|-----------|------------|
| Backend | FastAPI (Python 3.12) |
| Frontend | React 18 + TypeScript + Vite |
| Styling | TailwindCSS v4 |
| Package Manager | uv (Python), npm (Node) |
| Linting | ruff |
| Deployment | Docker, Google Cloud Run |

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 20+
- Google Cloud project with OAuth credentials
- Google Cloud service account with IAM Admin permissions

### 1. Clone and Setup

```bash
cd fabric

# Install server dependencies
cd server
uv sync
cd ..

# Install client dependencies
cd client
npm install
cd ..
```

### 2. Configure Environment

Create `server/.env` from the template:

```bash
cp server/.env.template server/.env
```

Edit `server/.env` with your credentials:

```env
# Server
PORT=8001
ENVIRONMENT=development
SECRET_KEY=your-secret-key-here

# Google OAuth (from Google Cloud Console)
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_REDIRECT_URI=http://localhost:8001/api/auth/callback

# Google Cloud Project (for creating service accounts)
GOOGLE_CLOUD_PROJECT=your-project-id
```

### 3. Set Up Admin Service Account

Create a service account with these permissions in your Google Cloud project:
- `iam.serviceAccounts.create`
- `iam.serviceAccountKeys.create`
- `iam.serviceAccounts.get`

Download the JSON key and save it to:
```
server/credentials/admin-service-account.json
```

### 4. Run Development Servers

**Terminal 1 - Backend:**
```bash
cd server
uv run uvicorn fabric.main:app --reload --port 8001
```

**Terminal 2 - Frontend:**
```bash
cd client
npm run dev
```

Access the portal at: http://localhost:5174

## API Endpoints

### Authentication
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/auth/google` | Initiate Google OAuth flow |
| GET | `/api/auth/callback` | OAuth callback handler |
| GET | `/api/auth/me` | Get current user info |
| POST | `/api/auth/logout` | Clear session |

### Service Account
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/service-account/init` | Generate magic token & download commands |
| GET | `/api/service-account/download/{token}` | Download SA credentials (one-time) |
| GET | `/api/service-account/status` | Check if user has a service account |

### Health
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Health check |
| GET | `/api/health/ready` | Readiness check |

## Docker Deployment

### Build and Run

```bash
# Build the image
docker build -t fabric:latest .

# Run with environment variables
docker run -p 8001:8001 \
  -e SECRET_KEY=your-secret-key \
  -e GOOGLE_CLIENT_ID=your-client-id \
  -e GOOGLE_CLIENT_SECRET=your-client-secret \
  -e GOOGLE_CLOUD_PROJECT=your-project-id \
  -v ./credentials:/app/credentials:ro \
  fabric:latest
```

### Docker Compose

```bash
# Production
docker-compose up -d fabric

# Development
docker-compose --profile dev up dev-server
```

## Google Cloud Run Deployment

1. Build and push to Container Registry:
```bash
gcloud builds submit --tag gcr.io/PROJECT_ID/fabric
```

2. Deploy to Cloud Run:
```bash
gcloud run deploy fabric \
  --image gcr.io/PROJECT_ID/fabric \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars "SECRET_KEY=xxx,GOOGLE_CLIENT_ID=xxx,..." \
  --set-secrets "GOOGLE_CLIENT_SECRET=fabric-secrets:latest"
```

## Security Considerations

1. **Ephemeral Tokens**: Magic tokens expire after 5 minutes and are single-use
2. **Private Keys Never Stored**: Service account credentials only downloaded once
3. **Session Cookies**: HTTP-only, secure in production, 24-hour expiry
4. **HTTPS Required**: Enforced in production by Cloud Run
5. **OAuth State**: CSRF protection with time-limited state tokens

## Project Structure

```
fabric/
├── server/                      # FastAPI backend
│   ├── fabric/                  # Application code
│   │   ├── main.py             # FastAPI app entry point
│   │   ├── config.py           # Settings and configuration
│   │   ├── auth/               # Google OAuth
│   │   ├── service_account/    # SA creation
│   │   └── health/             # Health checks
│   ├── tests/                  # Test suite
│   ├── pyproject.toml          # Python dependencies
│   └── .env.template           # Environment template
├── client/                      # React frontend
│   ├── src/
│   │   ├── App.tsx             # Main application
│   │   ├── index.css           # TailwindCSS styles
│   │   └── main.tsx            # Entry point
│   ├── package.json            # Node dependencies
│   └── vite.config.ts          # Vite configuration
├── docs/                        # Documentation
│   ├── PROJECT_PLAN.md         # Architecture & design
│   └── TASKS.md                # Implementation tasks
├── Dockerfile                   # Production container
├── docker-compose.yml           # Container orchestration
└── README.md                    # This file
```

## Development

### Running Tests

```bash
cd server
uv run pytest tests/ -v
```

### Linting

```bash
cd server
uv run ruff check .
uv run ruff format .
```

### Building Client

```bash
cd client
npm run build
```

## License

Proprietary - Think41 Technologies

## Support

For questions or issues, contact the Think41 engineering team.
