# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Fabric is Think41 Technologies' AI Executive Assistant portal. It enables employees to self-provision Google service accounts that can interact with Google Docs/Sheets via CLI tools (`gdocs`, `gsheets`). The service accounts have no default permissions - employees explicitly share documents with their EA's email.

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

### Client (React)
```bash
cd client
npm install        # Install dependencies
npm run dev        # Run dev server on port 5174
npm run build      # Production build
```

### Docker
```bash
docker build -t fabric:latest .
docker-compose up -d fabric              # Production
docker-compose --profile dev up dev-server  # Development
```

## Architecture

**Two-service monorepo:**
- `server/` - FastAPI backend (port 8001)
- `client/` - React + TypeScript + Vite frontend (port 5174)

**Key flow:**
1. User authenticates via Google OAuth (`/api/auth/google`)
2. Portal generates ephemeral magic token (`/api/service-account/init`)
3. User runs OS-specific curl command in terminal
4. Command hits one-time download endpoint (`/api/service-account/download/{token}`)
5. Service account created in GCP, credentials saved to `~/.fabric/credentials.json`

**Stateless design:** No database. State lives in:
- GCP (service accounts with traceability in `description` field)
- Signed session cookies (24h expiry)
- In-memory magic tokens (5min expiry, single-use)

## Key Files

- `server/fabric/main.py` - FastAPI app, serves static files in production
- `server/fabric/auth/api.py` - Google OAuth with signed cookie sessions
- `server/fabric/service_account/api.py` - Magic token generation and SA creation
- `server/fabric/config.py` - Pydantic settings from environment
- `client/src/App.tsx` - Full portal UI (login, dashboard, instructions)
- `Dockerfile` - Multi-stage build combining client and server

## Environment Setup

Copy `server/.env.template` to `server/.env` and configure:
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` - OAuth credentials
- `GOOGLE_CLOUD_PROJECT` - GCP project for service account creation
- `SECRET_KEY` - For signing session cookies

Admin service account JSON goes in `server/credentials/admin-service-account.json` (needs `roles/iam.serviceAccountAdmin`).

## Traceability

Service accounts are created with metadata for audit:
- `displayName`: "AI EA for {user_name}"
- `description`: "Owner: {email} | Created: {timestamp} | Via: Fabric Portal"
