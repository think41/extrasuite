# Deployment Guide

ExtraSuite is designed to be deployed as a self-hosted service on Google Cloud Platform. This guide covers deploying your own instance.

## Deployment Options

| Option | Best For | Complexity |
|--------|----------|------------|
| **[Cloud Run](cloud-run.md)** | Production workloads | Medium |
| Local Development | Testing and development | Low |

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

Before deploying ExtraSuite, you'll need:

### Google Cloud Platform

1. **GCP Project** with billing enabled
2. **gcloud CLI** installed and configured
3. **Required APIs** enabled:
   - Cloud Run
   - Firestore
   - IAM
   - IAM Credentials
   - Container Registry

### OAuth Credentials

1. **Google OAuth Client** configured in Cloud Console
2. **OAuth consent screen** set up (internal or external)

### Domain (Optional)

- Custom domain with DNS access for production deployments

## Quick Start

```bash
# Clone the repository
git clone https://github.com/think41/extrasuite.git
cd extrasuite/extrasuite-server

# Set up environment
cp .env.template .env
# Edit .env with your configuration

# Deploy to Cloud Run
gcloud run deploy extrasuite-server \
  --source . \
  --region asia-southeast1 \
  --allow-unauthenticated
```

See [Cloud Run Deployment](cloud-run.md) for complete instructions.

## Configuration

### Required Environment Variables

| Variable | Description |
|----------|-------------|
| `GOOGLE_CLIENT_ID` | OAuth 2.0 Client ID |
| `GOOGLE_CLIENT_SECRET` | OAuth 2.0 Client Secret |
| `GOOGLE_CLOUD_PROJECT` | GCP Project ID |
| `SECRET_KEY` | Session signing key |

### Optional Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ALLOWED_EMAIL_DOMAINS` | Comma-separated allowed domains | All domains |
| `DOMAIN_ABBREVIATIONS` | JSON mapping for SA naming | Hash-based |
| `GOOGLE_REDIRECT_URI` | OAuth callback URL | Auto-detected |
| `ENVIRONMENT` | `development` or `production` | `production` |

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

## Operational Guides

- **[IAM Permissions](iam-permissions.md)** - Complete IAM role reference
- **[Operations](operations.md)** - Runbook and troubleshooting

## Local Development

For development and testing:

```bash
cd extrasuite-server
uv sync
uv run uvicorn extrasuite_server.main:app --reload --port 8001
```

See the main [README](https://github.com/think41/extrasuite) for development setup.

## Support

For deployment issues:

1. Check the [Operations Runbook](operations.md) for common issues
2. Review Cloud Run logs for errors
3. Contact your infrastructure team
