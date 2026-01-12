# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Fabric is Think41 Technologies' headless authentication service for AI CLI tools. It enables employees to obtain short-lived service account tokens for interacting with Google Docs/Sheets. This is a **headless API** - there is no web UI.

## Architecture

**Single entry point:** `cli/fabric_auth.py` → `get_token()`

**Flow:**
1. CLI calls `get_token()` to get a valid access token
2. If cached token exists and is valid, return it
3. Otherwise, start localhost callback server
4. Open browser to `/api/token/auth?port=<port>` (server constructs localhost URL)
5. User authenticates via Google OAuth
6. Server creates/retrieves service account and impersonates it
7. Server redirects to `http://localhost:<port>/on-authentication` with short-lived token (1 hour)
8. CLI saves token to `~/.config/fabric/token.json` and returns it

## Development Commands

### Server (FastAPI)
```bash
cd server
uv sync                                          # Install dependencies
uv run uvicorn fabric.main:app --reload --port 8001  # Run dev server
uv run pytest tests/ -v                          # Run tests
uv run ruff check .                              # Lint
uv run ruff format .                             # Format
```

### Docker
```bash
docker build -t fabric:latest .
docker-compose up -d fabric              # Production
docker-compose --profile dev up dev-server  # Development
```

## Key Files

- `cli/fabric_auth.py` - **Entry point** - `get_token()` function
- `cli/example_gsheet.py` - Example usage with gspread
- `server/fabric/main.py` - FastAPI app entry point
- `server/fabric/auth/api.py` - OAuth callback handler
- `server/fabric/token_exchange/api.py` - Token exchange API (`/api/token/auth`)
- `server/fabric/config.py` - Pydantic settings from environment
- `server/fabric/database.py` - Bigtable-backed storage for OAuth credentials and sessions
- `server/fabric/session.py` - Session management with Bigtable backend

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/token/auth?port=<port>` | CLI entry point - starts OAuth (port 1024-65535) |
| GET | `/api/auth/callback` | OAuth callback - exchanges code for token |
| GET | `/api/health` | Health check |
| GET | `/api/health/ready` | Readiness check |

## Environment Setup

Copy `server/.env.template` to `server/.env` and configure:
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` - OAuth credentials
- `GOOGLE_CLOUD_PROJECT` - GCP project for service account creation and Bigtable
- `BIGTABLE_INSTANCE` - Bigtable instance name (default: `fabric-auth`)
- `SECRET_KEY` - For signing state tokens

Server uses Application Default Credentials (ADC) for service account management and Bigtable access.

## Bigtable Setup

Create the Bigtable instance and tables:
```bash
# Enable APIs
gcloud services enable bigtable.googleapis.com bigtableadmin.googleapis.com

# Create instance (one node for dev, scale up for production)
gcloud bigtable instances create fabric-auth \
  --display-name="Fabric Auth" \
  --cluster-config=id=fabric-auth-c1,zone=us-central1-a,nodes=1

# Create tables
cbt -project=<project> -instance=fabric-auth createtable sessions
cbt -project=<project> -instance=fabric-auth createfamily sessions data
cbt -project=<project> -instance=fabric-auth createtable users
cbt -project=<project> -instance=fabric-auth createfamily users oauth
cbt -project=<project> -instance=fabric-auth createfamily users metadata
```

## Service Account Traceability

Service accounts are created with metadata for audit:
- `displayName`: "AI EA for {user_name}"
- `description`: "Owner: {email} | Created: {timestamp} | Via: Fabric"

## Token Storage

- **Server-side:** OAuth refresh tokens and sessions stored in Bigtable
  - `sessions` table: session_id -> email mapping (for HTTP sessions)
  - `users` table: email -> OAuth credentials + service account info
- **Client-side:** Short-lived SA tokens cached in `~/.config/fabric/token.json`

## Session-Based Token Refresh

When a user has a valid browser session (30-day cookie), subsequent CLI auth requests
will automatically refresh the SA token using stored OAuth credentials, without
requiring the user to re-authenticate via Google OAuth.
