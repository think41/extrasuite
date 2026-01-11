# Fabric CLI - Reference Implementation

This directory contains the reference implementation for CLI authentication with Fabric.

## Overview

The Fabric Token Exchange flow provides secure, short-lived service account tokens for CLI tools:

1. **No long-lived credentials on your laptop** - Only 1-hour tokens are stored locally
2. **OAuth credentials stay server-side** - Fabric stores your OAuth tokens in its database
3. **Automatic service account provisioning** - SA created on first use

## Files

- `fabric_auth.py` - Core authentication module
- `example_gsheet.py` - Example using Fabric auth with gspread

## Quick Start

### 1. Authenticate

```bash
python fabric_auth.py
```

This will:
1. Open your browser to the Fabric authentication page
2. You sign in with your Google account
3. Fabric creates/reuses your service account
4. A short-lived token (1 hour) is saved to `~/.config/fabric/token.json`

### 2. Use with Google Sheets

```bash
pip install gspread
python example_gsheet.py https://docs.google.com/spreadsheets/d/YOUR_SHEET_ID/edit
```

**Important:** Share your spreadsheet with your service account email first!
Find your SA email in `~/.config/fabric/token.json` after authenticating.

## Integration Guide

### Using fabric_auth in your own scripts

```python
from fabric_auth import get_token, load_cached_token

# Get a valid token (authenticates if needed)
token = get_token()

# Use with gspread
import gspread
from google.oauth2.credentials import Credentials

credentials = Credentials(token=token)
gc = gspread.authorize(credentials)
sheet = gc.open_by_url("https://docs.google.com/spreadsheets/d/...")
```

### Token Lifecycle

- Tokens are valid for **1 hour**
- When a token expires, run `fabric_auth.py` again
- If you're already logged into Fabric, re-authentication is instant (browser opens and closes quickly)

## Configuration

### Custom Fabric Server

```bash
python fabric_auth.py --server https://fabric.yourcompany.com
```

### Force Re-authentication

```bash
python fabric_auth.py --force
```

### Show Token

```bash
python fabric_auth.py --show-token
```

## Token Storage

Tokens are stored in:
```
~/.config/fabric/token.json
```

Contents:
```json
{
  "access_token": "ya29.xxx...",
  "expires_at": 1699876543,
  "expires_in": 3600,
  "service_account_email": "ea-yourname@project.iam.gserviceaccount.com",
  "token_type": "Bearer"
}
```

## Security Notes

- **Tokens expire automatically** - Even if stolen, they only work for 1 hour
- **No GCP access** - The token only allows access to Sheets/Docs/Drive, not other GCP services
- **Your OAuth stays secure** - Refresh tokens are stored on the Fabric server, not your laptop
