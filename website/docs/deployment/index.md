# Deployment Guide

ExtraSuite is designed to be self-hosted on Google Cloud Platform. The server handles user authentication, issues short-lived access tokens to agents, and manages per-user service accounts.

## What You're Building

```
┌─────────────┐     ┌─────────────────┐     ┌──────────────────┐
│   AI Agent  │────▶│  ExtraSuite     │────▶│  Google Cloud    │
│  (Claude,   │     │  Server         │     │  - Firestore     │
│   Codex)    │◀────│  (Cloud Run)    │◀────│  - IAM           │
└─────────────┘     └─────────────────┘     │  - OAuth         │
                                            └──────────────────┘
```

The server authenticates users via Google OAuth, then issues short-lived tokens agents use to access Google Workspace APIs. Agents never hold long-lived credentials.

## Start Here

**[→ Step-by-Step Deployment Guide](cloud-run.md)**

The deployment guide covers all three credential modes from start to finish, including the Google OAuth consent screen setup (the trickiest part).

Estimated time: 20-30 minutes for `sa+oauth` or `oauth` modes; add ~10 minutes for `sa+dwd` (requires Workspace admin action).

## Docker Image

ExtraSuite publishes official Docker images:

```
asia-southeast1-docker.pkg.dev/thinker41/extrasuite/server
```

| Tag | When to Use |
|-----|-------------|
| `latest` | Production deployments (latest stable release) |
| `v1.0.0` | Pin to a specific version |
| `main` | Testing latest changes (may be unstable) |

## Additional Resources

- **[IAM Permissions Reference](iam-permissions.md)** — detailed explanation of required GCP roles
- **[Operations Guide](operations.md)** — monitoring, updating, troubleshooting, Firestore TTL setup
- **[Authentication API Specification](../api/auth-spec.md)** — protocol specification for building custom server implementations

## Build Your Own Implementation

This guide covers the reference implementation using Google OAuth and Cloud Run. If you prefer to use your own authentication mechanism (SAML, SSO, LDAP), or integrate into an existing employee portal, see the **[Authentication API Specification](../api/auth-spec.md)**. You can implement the two required endpoints in any language while maintaining compatibility with the ExtraSuite client library.
