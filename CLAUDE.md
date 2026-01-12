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
4. Open browser to `/api/token/auth?redirect=http://localhost:<port>/callback`
5. User authenticates via Google OAuth
6. Server creates/retrieves service account and impersonates it
7. Server redirects to localhost with short-lived token (1 hour)
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
- `server/fabric/database.py` - SQLAlchemy models for OAuth credential storage

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/token/auth?redirect=<url>` | CLI entry point - starts OAuth |
| GET | `/api/auth/callback` | OAuth callback - exchanges code for token |
| GET | `/api/health` | Health check |
| GET | `/api/health/ready` | Readiness check |

## Environment Setup

Copy `server/.env.template` to `server/.env` and configure:
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` - OAuth credentials
- `GOOGLE_CLOUD_PROJECT` - GCP project for service account creation
- `SECRET_KEY` - For signing state tokens

Server uses Application Default Credentials (ADC) for service account management.

## Service Account Traceability

Service accounts are created with metadata for audit:
- `displayName`: "AI EA for {user_name}"
- `description`: "Owner: {email} | Created: {timestamp} | Via: Fabric"

## Token Storage

- **Server-side:** OAuth refresh tokens stored in SQLite (`fabric.db`)
- **Client-side:** Short-lived SA tokens cached in `~/.config/fabric/token.json`
