# Privacy Policy

*Last updated: January 2025*

## Overview

ExtraSuite is an internal authentication service operated by Think41 for employees of authorized organizations. This policy explains what information we collect and how we use it.

## Information We Collect

We collect minimal information necessary to provide the authentication service:

- **Email address** - Your Google Workspace email address, used to identify your account and restrict access to authorized domains.
- **Service account mapping** - A record linking your email to your dedicated service account.

## What We Do NOT Collect or Access

ExtraSuite does **not** collect, store, or access:

- **Document contents** - ExtraSuite does not read, store, or access your Google Docs, Sheets, or Drive files.
- **Personal files** - We have no access to your personal data stored in Google Workspace.
- **Usage data** - We do not track how you use the tokens we generate.
- **Access tokens** - Tokens are generated on-demand and never stored server-side.

!!! note "Separation of Concerns"
    ExtraSuite only facilitates token creation. The CLI tools or LLM agents that use these tokens are responsible for their own data handling.

## How We Use Your Information

- Authenticate you via Google OAuth
- Verify your email domain is authorized
- Generate short-lived service account tokens (valid for 1 hour)
- Maintain your session to avoid repeated authentication

## Data Storage and Retention

- Data is stored in Google Cloud Firestore within our GCP project
- Session data is automatically deleted after 30 days of inactivity
- Generated access tokens expire after 1 hour and are not stored server-side

## Data Sharing

We do not sell, share, or disclose your information to third parties. Your data is used solely for operating this authentication service.

## Your Rights

You can:

- **Request access** to your stored data
- **Request deletion** of your data (contact your IT administrator)
- **Revoke access** to any document at any time through Google Drive

## Security

- All data is transmitted over HTTPS
- Tokens are never exposed in URLs or browser history
- Service account credentials are managed by Google Cloud IAM
- See our [Security documentation](../security.md) for details

## Changes to This Policy

We may update this policy periodically. Continued use of the service after changes constitutes acceptance of the modified policy.

## Contact

For questions about this privacy policy:

- Contact your IT administrator
- Reach out via internal support channels
