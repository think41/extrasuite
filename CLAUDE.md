# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Google Workspace Gateway (GWG) is a headless authentication service for CLI tools accessing Google Workspace APIs. It enables users to obtain short-lived service account tokens for interacting with Google Sheets, Docs, and Drive.

The project consists of two packages:
1. **Client Library** (`google-workspace-gateway`) - PyPI package for CLI tools
2. **Server** (`gwg-server`) - FastAPI server for Cloud Run deployment

## Architecture

**Client Flow:**
1. CLI creates `GoogleWorkspaceGateway(server_url="...")` instance
2. Calls `gateway.get_token()` to get a valid access token
3. If cached token exists and is valid, return it
4. Otherwise, start localhost callback server and open browser
5. User authenticates via Google OAuth on the server
6. Server redirects to localhost with short-lived token (1 hour)
7. CLI saves token to `~/.config/google-workspace-gateway/token.json`

**Server Flow:**
1. Receive auth request at `/api/token/auth?port=<port>`
2. If user has valid session, refresh token and redirect
3. Otherwise, redirect to Google OAuth
4. On callback, store OAuth credentials in Firestore
5. Create/retrieve user's service account
6. Impersonate SA to generate short-lived token
7. Redirect to `http://localhost:<port>/on-authentication?token=...`

## Development Commands

### Client Library
```bash
cd client
uv sync
uv run python -c "from google_workspace_gateway import GoogleWorkspaceGateway; print('OK')"
uv run ruff check .
```

### Server (FastAPI)
```bash
cd server
uv sync
uv run uvicorn gwg_server.main:app --reload --port 8001
uv run pytest tests/ -v
uv run ruff check .
uv run ruff format .
```

### Docker
```bash
docker build -t gwg-server:latest .
docker-compose up -d gwg-server              # Production
docker-compose --profile dev up dev-server   # Development
```

## Key Files

### Client Library
- `client/src/google_workspace_gateway/__init__.py` - Package exports
- `client/src/google_workspace_gateway/gateway.py` - `GoogleWorkspaceGateway` class
- `client/examples/` - Usage examples

### Server
- `server/gwg_server/main.py` - FastAPI app entry point
- `server/gwg_server/config.py` - Pydantic settings from environment
- `server/gwg_server/database.py` - Firestore-backed storage
- `server/gwg_server/session.py` - Session management
- `server/gwg_server/auth/api.py` - OAuth callback handler
- `server/gwg_server/token_exchange/api.py` - Token exchange API

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
- `GOOGLE_CLOUD_PROJECT` - GCP project for service account creation
- `SECRET_KEY` - For signing state tokens

Server uses Application Default Credentials (ADC) for service account management and Firestore access.

## Firestore Setup

Firestore collections are created automatically on first use. No manual setup required.

Enable the Firestore API and create a database:
```bash
gcloud services enable firestore.googleapis.com --project=<project>
gcloud firestore databases create --location=asia-south1 --project=<project>
```

## Token Storage

- **Server-side:** OAuth refresh tokens and sessions in Firestore
- **Client-side:** Short-lived SA tokens in `~/.config/google-workspace-gateway/token.json`

## Package Names

| Package | PyPI/Import Name | Directory |
|---------|------------------|-----------|
| Client | `google-workspace-gateway` / `google_workspace_gateway` | `client/` |
| Server | `gwg-server` / `gwg_server` | `server/` |
