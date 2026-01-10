# Fabric - AI Executive Assistant Portal

## Project Overview

Fabric is Think41 Technologies' collection of AI skills, agents, utilities, and tools to make employees and engineering teams productive. This portal enables employees to set up their AI Executive Assistant (a Google service account) through a self-service workflow.

## How It Works

### Employee Workflow
1. Employee logs in to the Fabric portal using their Google Workspace credentials
2. Portal displays OS-specific shell command with an ephemeral magic token
3. Employee runs the command in their terminal
4. Command calls API, which creates a service account and returns the JSON credentials
5. Command saves the JSON to the appropriate folder on the employee's laptop
6. Portal stores the service account email (not the private key) for tracking

### AI Executive Assistant Concept
- Each employee gets a dedicated service account (their "AI EA")
- The EA has no permissions by default
- Employees explicitly share documents/folders/sheets with their EA's email
- When the employee asks the EA to perform actions (via gdocs/gsheets CLI tools), the EA operates within shared permissions
- Employees can revoke access at any time by unsharing

## Technology Stack

### Server
- **Framework**: FastAPI
- **Package Manager**: uv (Astral)
- **Linter**: ruff
- **Type Checker**: ty
- **Port**: 8001 (non-standard to avoid conflicts)

### Client
- **Framework**: React 18 with TypeScript
- **Build Tool**: Vite
- **Styling**: TailwindCSS
- **Port**: 5174 (non-standard to avoid conflicts)

### Infrastructure
- **Database**: None (stateless APIs)
- **State Management**: Google Cloud Project (service account metadata)
- **Authentication**: Google OAuth 2.0 (Workspace accounts)
- **Deployment**: Docker container on Google Cloud Run

## Project Structure

```
fabric/
├── docs/                    # Documentation
│   ├── PROJECT_PLAN.md     # This file
│   └── TASKS.md            # Task tracking
├── server/                  # FastAPI backend
│   ├── pyproject.toml      # Python dependencies (uv)
│   ├── fabric/             # Main application
│   │   ├── main.py         # FastAPI app entry point
│   │   ├── auth/           # Google OAuth handlers
│   │   ├── service_account/ # Service account creation
│   │   └── health/         # Health check endpoints
│   └── tests/              # Server tests
├── client/                  # React frontend
│   ├── package.json        # npm dependencies
│   ├── vite.config.ts      # Vite configuration
│   ├── tailwind.config.ts  # Tailwind configuration
│   └── src/                # React source code
│       ├── App.tsx         # Main app component
│       ├── pages/          # Page components
│       ├── components/     # Reusable UI components
│       └── lib/            # Utilities
├── Dockerfile              # Multi-stage build
├── docker-compose.yml      # Local development
└── README.md               # Project documentation
```

## API Endpoints

### Authentication
- `GET /api/auth/google` - Initiate Google OAuth flow
- `GET /api/auth/callback` - OAuth callback handler
- `GET /api/auth/me` - Get current user info
- `POST /api/auth/logout` - Logout user

### Service Account
- `POST /api/service-account/init` - Initialize service account creation flow (returns magic token)
- `GET /api/service-account/download/{token}` - Download service account JSON (one-time use)
- `GET /api/service-account/status` - Check if user has a service account

### Health
- `GET /api/health` - Health check
- `GET /api/health/ready` - Readiness check

## Environment Variables

```bash
# Google OAuth
GOOGLE_CLIENT_ID=xxx
GOOGLE_CLIENT_SECRET=xxx
GOOGLE_REDIRECT_URI=http://localhost:8001/api/auth/callback

# Google Cloud Project (for creating service accounts)
GOOGLE_CLOUD_PROJECT=xxx
GOOGLE_APPLICATION_CREDENTIALS=/path/to/admin-service-account.json

# Security
SECRET_KEY=xxx  # For JWT/session tokens
MAGIC_TOKEN_EXPIRY=300  # 5 minutes

# Server
PORT=8001
ENVIRONMENT=development
ALLOWED_ORIGINS=http://localhost:5174
```

## Security Considerations

1. **Magic tokens are ephemeral** - Expire after 5 minutes and single-use
2. **Service account private keys are never stored** - Only downloaded once
3. **Service account emails are stored** - For audit and tracking
4. **OAuth tokens are session-based** - Not persisted
5. **HTTPS required in production** - Enforced by Cloud Run

## Implementation Tasks

See [TASKS.md](./TASKS.md) for detailed task breakdown.
