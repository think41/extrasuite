# Individual Developer Setup

This guide is for developers who want to use ExtraSuite skills for personal use without deploying the full ExtraSuite server.

## Overview

If you're the only user and don't need the token exchange server, you can:

1. Create a Google Cloud service account directly
2. Download the service account key (JSON file)
3. Configure your AI agent to use the key

This approach is simpler but requires managing the service account key yourself.

## Prerequisites

- A Google Cloud project with billing enabled
- `gcloud` CLI installed and authenticated
- An AI coding agent (Claude Code, Codex CLI, or Gemini CLI)

## Step 1: Create a Google Cloud Project

If you don't already have a project:

```bash
gcloud projects create my-extrasuite-project
gcloud config set project my-extrasuite-project
```

## Step 2: Enable Required APIs

```bash
gcloud services enable sheets.googleapis.com
gcloud services enable docs.googleapis.com
gcloud services enable slides.googleapis.com
gcloud services enable drive.googleapis.com
```

## Step 3: Create a Service Account

```bash
gcloud iam service-accounts create extrasuite-agent \
  --display-name="ExtraSuite AI Agent"
```

Note the service account email - it will look like:
`extrasuite-agent@my-extrasuite-project.iam.gserviceaccount.com`

## Step 4: Create and Download a Key

```bash
gcloud iam service-accounts keys create ~/extrasuite-key.json \
  --iam-account=extrasuite-agent@my-extrasuite-project.iam.gserviceaccount.com
```

!!! warning "Security Note"
    This key file provides full access to the service account. Keep it secure:

    - Never commit it to version control
    - Store it in a secure location
    - Consider encrypting it at rest

## Step 5: Configure Your AI Agent

### For Claude Code

Add to your `.claude/settings.json`:

```json
{
  "env": {
    "GOOGLE_APPLICATION_CREDENTIALS": "~/extrasuite-key.json"
  }
}
```

### For Codex CLI

```bash
export GOOGLE_APPLICATION_CREDENTIALS=~/extrasuite-key.json
```

### For Gemini CLI

```bash
export GOOGLE_APPLICATION_CREDENTIALS=~/extrasuite-key.json
```

## Step 6: Share Documents with Your Service Account

Share any Google Sheets, Docs, or Slides you want to access with your service account email address.

1. Open the document in Google Drive
2. Click "Share"
3. Enter your service account email (e.g., `extrasuite-agent@my-extrasuite-project.iam.gserviceaccount.com`)
4. Choose appropriate permissions (Editor for write access, Viewer for read-only)

## Step 7: Install the Skills

Follow the skill-specific installation guides:

- [Google Sheets](../skills/sheets.md)
- [Google Docs](../skills/docs.md)
- [Google Slides](../skills/slides.md)

## Limitations

Compared to the full ExtraSuite server deployment:

| Feature | Individual Setup | Full Server |
|---------|-----------------|-------------|
| Token expiration | Long-lived key | 1-hour tokens |
| User management | Single user | Multi-user |
| Domain restrictions | N/A | Supported |
| Central audit | N/A | Firestore logs |
| Key rotation | Manual | Automatic |

## Next Steps

- [Learn how to prompt effectively](../user-guide/prompting.md)
- [Understand the security model](../security.md)
