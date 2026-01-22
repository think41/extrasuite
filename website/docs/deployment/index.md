# Deployment Guide

ExtraSuite is designed to be deployed as a self-hosted service on Google Cloud Platform. This guide covers deploying your own instance.

## Quick Start

```bash
# Set your project ID
export PROJECT_ID=your-project-id

# Deploy using the pre-built image
gcloud run deploy extrasuite-server \
  --image=asia-southeast1-docker.pkg.dev/thinker41/extrasuite/server:latest \
  --region=asia-southeast1 \
  --allow-unauthenticated \
  --project=$PROJECT_ID
```

See [Cloud Run Deployment](cloud-run.md) for complete setup instructions including OAuth configuration.

## Architecture Overview

```
┌─────────────┐     ┌─────────────────┐     ┌──────────────────┐
│   CLI Tool  │────▶│  ExtraSuite     │────▶│  Google Cloud    │
│  (Claude,   │     │  Server         │     │  - Firestore     │
│   Codex)    │◀────│  (Cloud Run)    │◀────│  - IAM           │
└─────────────┘     └─────────────────┘     │  - OAuth         │
                                            └──────────────────┘
```

## Prerequisites

### Google Cloud Platform

1. **GCP Project** with billing enabled
2. **gcloud CLI** installed and configured
3. **Required APIs**:
   - Cloud Run
   - Firestore
   - IAM
   - IAM Credentials
   - Secret Manager

### OAuth Credentials

1. **Google OAuth Client** configured in Cloud Console
2. **OAuth consent screen** set up (internal or external)

### Domain (Optional)

- Custom domain with DNS access for production deployments

## Docker Images

Pre-built Docker images are available from Google Artifact Registry:

```
asia-southeast1-docker.pkg.dev/thinker41/extrasuite/server
```

**Available tags:**

| Tag | Description |
|-----|-------------|
| `latest` | Latest stable release |
| `v1.0.0` | Specific version |
| `main` | Latest from main branch |
| `sha-abc1234` | Specific commit |

## Environment Variables

### Required

| Variable | Description |
|----------|-------------|
| `GOOGLE_CLIENT_ID` | OAuth 2.0 Client ID |
| `GOOGLE_CLIENT_SECRET` | OAuth 2.0 Client Secret |
| `GOOGLE_CLOUD_PROJECT` | GCP Project ID for service accounts and Firestore |
| `SECRET_KEY` | Session signing key (use a long random string) |
| `BASE_DOMAIN` | Domain of your server (e.g., `extrasuite.example.com`) |

### Optional

| Variable | Description | Default |
|----------|-------------|---------|
| `SERVER_URL` | Full base URL for server | Derived from `BASE_DOMAIN` as `https://{BASE_DOMAIN}` |
| `FIRESTORE_DATABASE` | Firestore database name | `(default)` |
| `ALLOWED_EMAIL_DOMAINS` | Comma-separated allowed domains | All domains |
| `DOMAIN_ABBREVIATIONS` | JSON mapping for SA naming | Hash-based |

### Session Cookie Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `SESSION_COOKIE_NAME` | Cookie name | `session` |
| `SESSION_COOKIE_EXPIRY_MINUTES` | Session duration | `1440` (24 hours) |
| `SESSION_COOKIE_SAME_SITE` | SameSite policy | `lax` |
| `SESSION_COOKIE_HTTPS_ONLY` | HTTPS-only cookies | `true` |
| `SESSION_COOKIE_DOMAIN` | Cookie domain | Value of `BASE_DOMAIN` |

### Token Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `TOKEN_EXPIRY_MINUTES` | Access token lifetime | `60` (1 hour) |

## Security Considerations

### IAM Permissions

The ExtraSuite server requires specific IAM roles. See [IAM Permissions](iam-permissions.md) for details.

**Key principle:** End users do NOT need any GCP project access. The server acts as a trusted intermediary.

### Secret Management

- Store OAuth credentials in Secret Manager
- Generate strong random keys for session signing
- Rotate secrets periodically

### Network Security

- Always use HTTPS in production
- Consider Cloud Armor for DDoS protection
- Enable VPC Service Controls for sensitive environments

## Deployment Guides

- **[Cloud Run Deployment](cloud-run.md)** - Step-by-step deployment guide
- **[IAM Permissions](iam-permissions.md)** - Complete IAM role reference
- **[Operations](operations.md)** - Troubleshooting and common issues

## Local Development

For development and testing:

```bash
cd extrasuite-server
cp .env.template .env
# Edit .env with your configuration

uv sync
uv run uvicorn extrasuite_server.main:app --reload --port 8001
```

Set `SERVER_URL=http://localhost:8001` for local development.

## Building from Source

If you prefer to build your own image:

```bash
git clone https://github.com/think41/extrasuite.git
cd extrasuite

# Build the image
docker build -t my-extrasuite-server:latest .

# Push to your registry
docker tag my-extrasuite-server:latest gcr.io/$PROJECT_ID/extrasuite-server:latest
docker push gcr.io/$PROJECT_ID/extrasuite-server:latest
```

## Support

For deployment issues:

1. Check the [Operations guide](operations.md) for common issues
2. Review Cloud Run logs for errors
3. Open an issue on [GitHub](https://github.com/think41/extrasuite/issues)
