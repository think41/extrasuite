# Getting Started

Welcome to ExtraSuite! This guide will help you set up your AI agent to work with Google Workspace in minutes.

## Prerequisites

Before you begin, make sure you have:

1. **An AI coding assistant** installed on your computer:
    - [Claude Code](https://claude.ai/code) (requires paid plan)
    - [Codex CLI](https://openai.com/index/introducing-codex/) (requires Plus plan or higher)
    - [Gemini CLI](https://ai.google.dev/gemini-api/docs/aistudio-quickstart) (requires paid API key)
    - [Claude Coworks](https://claude.ai/coworks) (requires paid plan)
    - [Cursor](https://cursor.com) (AI-powered code editor)

2. **A terminal application**:
    - **macOS**: Terminal (search in Spotlight) or iTerm2
    - **Linux**: Terminal, Konsole, or your preferred terminal
    - **Windows**: PowerShell or Windows Terminal with WSL

3. **Access to ExtraSuite** (authorized email domain)

## Quick Start

### 1. Sign In

Visit [extrasuite.think41.com](https://extrasuite.think41.com) and sign in with your Google Workspace account.

### 2. Install the Skill

After signing in, you'll see a personalized install command. Copy and run it in your terminal:

=== "macOS / Linux"

    ```bash
    curl -fsSL https://extrasuite.think41.com/api/skills/install/<token> | bash
    ```

=== "Windows (PowerShell)"

    ```powershell
    irm "https://extrasuite.think41.com/api/skills/install/<token>?ps=true" | iex
    ```

!!! note "Token Validity"
    The install command contains a personalized token valid for 5 minutes. Refresh the page to generate a new one if needed.

### 3. Share Your Document

Copy your service account email (shown on the homepage after sign-in) and share your Google Sheet:

1. Open your Google Sheet
2. Click **Share**
3. Paste your service account email
4. Choose permission level (Viewer, Commenter, or Editor)
5. Click **Send**

### 4. Start Working

Open your AI agent and describe what you need:

```
Read the sales data from https://docs.google.com/spreadsheets/d/abc123/edit
and create a summary of Q4 revenue by region.
```

## What's Next?

- **[Installation Guides](installation/index.md)** - Platform-specific instructions
- **[User Guide](../user-guide/index.md)** - Learn effective prompting techniques
- **[Skills Reference](../skills/index.md)** - Detailed documentation for each skill

## Troubleshooting

### "Spreadsheet not found" Error

Make sure you've shared the document with your service account email. The email looks like:
`yourname-domain@project.iam.gserviceaccount.com`

### "Authentication required" Error

Your token may have expired (tokens last 1 hour). The skill will automatically prompt you to re-authenticate.

### Install Command Not Working

1. Make sure you're using the correct command for your OS
2. The token in the URL expires after 5 minutes - refresh the page for a new one
3. Check that your terminal has internet access

---

Need more help? Check the [FAQ](../faq.md) or contact your IT administrator.
