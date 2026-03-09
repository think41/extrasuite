# Deployment Guide

ExtraSuite is designed to be deployed as a self-hosted service on Google Cloud Platform. This guide walks you through deploying your own instance.

## What You're Building

When you complete this guide, you'll have:

- A Cloud Run service that authenticates users and issues short-lived access tokens
- A Firestore database to store user records
- OAuth credentials so users can log in with their Google accounts
- A service account with permissions to create user-specific service accounts

```
┌─────────────┐     ┌─────────────────┐     ┌──────────────────┐
│   AI Agent  │────▶│  ExtraSuite     │────▶│  Google Cloud    │
│  (Claude,   │     │  Server         │     │  - Firestore     │
│   Codex)    │◀────│  (Cloud Run)    │◀────│  - IAM           │
└─────────────┘     └─────────────────┘     │  - OAuth         │
                                            └──────────────────┘
```

## Prerequisites Checklist

Before you begin, ensure you have:

| Requirement | Details |
|-------------|---------|
| Google Cloud Project | A project where you have **Owner** or **Editor** role, with billing enabled |
| Google Workspace or Gmail | To test authentication after deployment |

**Optional but recommended:**

| Requirement | Details |
|-------------|---------|
| gcloud CLI | Makes deployment faster. [Install gcloud CLI](https://cloud.google.com/sdk/docs/install) |
| Custom domain | For a professional URL instead of the auto-generated Cloud Run URL |

## Deployment Steps Overview

The deployment process has 8 steps:

| Step | What You'll Do | Time |
|------|----------------|------|
| 1 | Enable Google Cloud APIs | 2 min |
| 2 | Create a Firestore database | 2 min |
| 3 | Configure OAuth consent screen | 5 min |
| 4 | Create OAuth credentials | 3 min |
| 5 | Create a service account for ExtraSuite | 3 min |
| 6 | Store secrets securely | 3 min |
| 7 | Deploy to Cloud Run | 5 min |
| 8 | Verify the deployment | 2 min |

**[Start the Deployment Guide →](cloud-run.md)**

## Docker Image

ExtraSuite publishes official Docker images to Google Artifact Registry:

```
asia-southeast1-docker.pkg.dev/thinker41/extrasuite/server
```

| Tag | When to Use |
|-----|-------------|
| `latest` | Production deployments (latest stable release) |
| `v1.0.0` | Pin to a specific version |
| `main` | Testing latest changes (may be unstable) |

## Additional Resources

- **[IAM Permissions Reference](iam-permissions.md)** - Detailed explanation of required permissions
- **[Operations Guide](operations.md)** - Monitoring, troubleshooting, and maintenance

## Choosing a Credential Mode

Before deploying, choose how the server will authenticate agents for Gmail, Calendar, and other user-specific commands:

| Mode | `CREDENTIAL_MODE` | Best for | Requirements |
|------|-------------------|----------|--------------|
| Service account + DWD | `sa+dwd` *(default)* | Google Workspace organizations with admin access | Workspace admin must enable domain-wide delegation |
| Service account + OAuth | `sa+oauth` | Organizations where DWD is not available | No admin action needed beyond standard OAuth |
| OAuth only | `oauth` | Personal use or minimal setup | No DWD or service accounts; edits appear as the user |

For `sa+oauth` and `oauth` modes, two additional secrets are required:
- `OAUTH_SCOPES` — comma-separated list of Google OAuth scope short names (e.g., `gmail.compose,calendar`)
- `OAUTH_TOKEN_ENCRYPTION_KEY` — 64-char hex AES-256 key for encrypting stored refresh tokens. **Store this in Cloud Run Secret Manager, not as a plain env var.**

Generate the key:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

See the [Authentication API Specification](../api/auth-spec.md) for the full credential mode reference.

## Build Your Own Implementation

This deployment guide is for the reference implementation using Google OAuth and Cloud Run. If you prefer to:

- Use your own authentication mechanism (SAML, SSO, LDAP)
- Apply custom access policies (specific departments, approval workflows)
- Integrate into your existing employee portal

See the **[Authentication API Specification](../api/auth-spec.md)** for the protocol specification. You can implement the two required endpoints in any language or framework while maintaining compatibility with the ExtraSuite client library and skills.
