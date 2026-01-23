# Cursor Installation

This guide walks you through installing ExtraSuite skills for [Cursor](https://cursor.com), the AI-powered code editor.

## Prerequisites

1. **Cursor installed** - Download from [cursor.com](https://cursor.com)
2. **Cursor Pro subscription** (for full AI capabilities)

---

## Step 1: Enable Agent Skills

Agent Skills are currently available in Cursor's Nightly release channel. You need to switch to Nightly to use ExtraSuite skills.

1. Open **Cursor Settings** (`Cmd+Shift+J` on Mac, `Ctrl+Shift+J` on Windows/Linux)
2. Navigate to the **Beta** section
3. Set **Update Channel** to **Nightly**
4. Restart Cursor after the update completes

!!! info "Learn More"
    For more details on Agent Skills, see the [Cursor Agent Skills documentation](https://cursor.com/docs/context/skills).

---

## Step 2: Sign In to ExtraSuite

1. Open [extrasuite.think41.com](https://extrasuite.think41.com) (or your organization's ExtraSuite URL)
2. Click **Sign In** or **Get Started**
3. Authenticate with your Google Workspace account
4. Copy the install command shown on the homepage

---

## Step 3: Install the Skill

Open Cursor's integrated terminal (`` Ctrl+` `` or `` Cmd+` ``) and run the install command:

=== "macOS / Linux"

    ```bash
    curl -fsSL https://extrasuite.think41.com/api/skills/install/<your-token> | bash
    ```

=== "Windows (PowerShell)"

    ```powershell
    irm "https://extrasuite.think41.com/api/skills/install/<your-token>?ps=true" | iex
    ```

The skill will be installed to `~/.cursor/skills/gsheets/`.

!!! note "Token Validity"
    The install token is valid for 5 minutes. Refresh the ExtraSuite page to generate a new one if needed.

---

## Step 4: Restart Cursor

After installation, restart Cursor for the skill to be detected.

---

## Step 5: Verify Installation

### Check Skill Files

```bash
ls ~/.cursor/skills/gsheets/
```

You should see: `SKILL.md`, `checks.py`, `verify_access.py`, `gsheet_utils.py`, `requirements.txt`

### Check in Cursor Settings

1. Open **Cursor Settings** (`Cmd+Shift+J` or `Ctrl+Shift+J`)
2. Navigate to **Rules**
3. The ExtraSuite skill should appear in the **Agent Decides** section

---

## Usage

Once installed, Cursor's AI agent will automatically use the skill when you work with Google Sheets.

### Example Prompts

**In Cursor Chat** (`Cmd+L` or `Ctrl+L`):

```
Read the sales data from https://docs.google.com/spreadsheets/d/abc123/edit
and summarize the top 10 products by revenue.
```

**In Composer** (`Cmd+I` or `Ctrl+I`):

```
Create a Python script that reads data from 
https://docs.google.com/spreadsheets/d/abc123/edit
and exports it as JSON.
```

---

## Troubleshooting

### Skill Not Detected

1. Ensure you're on the **Nightly** update channel
2. Verify the skill directory exists: `ls ~/.cursor/skills/gsheets/`
3. Restart Cursor

### "Permission Denied" Error

Make sure you've shared the Google Sheet with your service account email (shown on the ExtraSuite homepage after sign-in).

### Token Expired

Access tokens expire after 1 hour. The skill will prompt you to re-authenticate when needed.

---

## Continue to Quick Start

You've completed the Cursor installation. Continue to the Quick Start guide to learn how to use ExtraSuite:

[:octicons-arrow-right-24: Continue to Start Using ExtraSuite](../index.md#start-using-extrasuite)

---

## Additional Resources

- [Share your documents](../../user-guide/sharing.md) with your service account
- [Learn effective prompting techniques](../../user-guide/prompting.md)
- [Explore the Google Sheets skill reference](../../skills/sheets.md)
