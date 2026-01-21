# User Guide

This guide covers everything you need to know to effectively use ExtraSuite with your AI coding assistant.

## Topics

<div class="grid cards" markdown>

-   :material-chat:{ .lg .middle } **[Prompting](prompting.md)**

    ---

    Learn how to write effective prompts for working with Google Sheets. Get better results by providing clear context and specific instructions.

-   :material-share-variant:{ .lg .middle } **[Sharing Documents](sharing.md)**

    ---

    Understand how to share your Google documents with your AI agent and manage permissions effectively.

-   :material-lock-off:{ .lg .middle } **[Revoking Access](revoking-access.md)**

    ---

    Learn how to remove access to specific documents or revoke all access when needed.

</div>

## Key Concepts

### Service Account Email

When you sign up for ExtraSuite, you're assigned a unique **service account email**. This email represents your AI agent in Google Workspace. It looks like:

```
yourname-domain@project.iam.gserviceaccount.com
```

This email is used to:

- Share documents with your AI agent
- Identify changes made by your agent in version history
- Control access on a per-document basis

### Token Lifecycle

ExtraSuite uses short-lived access tokens:

| Token Type | Lifetime | Purpose |
|------------|----------|---------|
| Access Token | 1 hour | API access to Google Workspace |
| Auth Code | 2 minutes | Exchange for access token |
| Install Token | 5 minutes | Skill installation |

When your token expires, you'll be prompted to re-authenticate. This is automatic and typically requires just clicking a link in your browser.

### Permission Levels

When sharing documents, you can choose:

| Permission | What the Agent Can Do |
|------------|----------------------|
| **Viewer** | Read data, download as CSV |
| **Commenter** | Everything in Viewer, plus add comments |
| **Editor** | Full read/write access, modify content |

!!! tip "Least Privilege"
    Start with Viewer access and only grant Editor when you need the agent to make changes.

## Best Practices

### 1. Be Specific in Prompts

Instead of:
> "Update the spreadsheet"

Say:
> "In the Sales worksheet of https://docs.google.com/spreadsheets/d/abc123/edit, add a SUM formula in cell D10 that totals cells D2:D9"

### 2. Include the Full URL

Always include the complete Google Sheets URL in your prompt:
```
https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit
```

### 3. Verify Before Major Changes

For important spreadsheets:
1. Make a copy before large-scale edits
2. Review the agent's plan before execution
3. Check version history after changes

### 4. Use Formulas, Not Values

Ask the agent to use formulas instead of hardcoded values:
```
Add a formula to calculate revenue growth, not a static number
```

This keeps your spreadsheet dynamic and maintainable.

## Quick Reference

### Finding Your Service Account Email

1. Go to [extrasuite.think41.com](https://extrasuite.think41.com)
2. Sign in with your Google account
3. Your service account email is displayed in Step 2

### Checking Shared Documents

To see which documents are shared with your agent:

1. Open [Google Drive](https://drive.google.com)
2. Search for your service account email
3. Or check individual document sharing settings

### Getting Help

- **Installation issues**: See [Installation Guides](../getting-started/installation/index.md)
- **Skill reference**: See [Skills Documentation](../skills/index.md)
- **Security questions**: See [Security](../security.md)
- **Common questions**: See [FAQ](../faq.md)
