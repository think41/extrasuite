# Cursor Installation

This guide walks you through installing ExtraSuite skills for [Cursor](https://cursor.com), the AI-powered code editor.

## Prerequisites

1. **Cursor installed** - Download from [cursor.com](https://cursor.com)
2. **Cursor Pro subscription** (for full AI capabilities)
3. **Terminal access** (built into Cursor or system terminal)

## What is Cursor?

Cursor is an AI-powered code editor built on VS Code. It integrates AI capabilities directly into your development workflow, allowing you to code with AI assistance.

## Installation

### Step 1: Sign In to ExtraSuite

1. Open [extrasuite.think41.com](https://extrasuite.think41.com)
2. Click **Sign In** or **Get Started**
3. Authenticate with your Google Workspace account

### Step 2: Run the Install Command

Open Cursor's integrated terminal (`` Ctrl+` `` or `` Cmd+` ``) and run:

=== "macOS / Linux"

    ```bash
    curl -fsSL https://extrasuite.think41.com/api/skills/install/<your-token> | bash
    ```

=== "Windows (PowerShell)"

    ```powershell
    irm "https://extrasuite.think41.com/api/skills/install/<your-token>?ps=true" | iex
    ```

### Step 3: Verify Installation

Check that the skill was installed:

```bash
ls ~/.cursor/skills/gsheets/
```

You should see:

```
SKILL.md
checks.py
verify_access.py
gsheet_utils.py
requirements.txt
```

## How It Works

Cursor's AI can access the skill when you:

1. **Chat with Cursor** (Cmd+L or Ctrl+L) and mention Google Sheets
2. **Use Composer** (Cmd+I or Ctrl+I) for larger tasks
3. **Reference the skill** in your prompts

## Usage Examples

### In Cursor Chat

Press `Cmd+L` (Mac) or `Ctrl+L` (Windows/Linux) to open chat:

```
Read the configuration data from
https://docs.google.com/spreadsheets/d/abc123/edit
and generate TypeScript types for each column.
```

### In Composer

Press `Cmd+I` (Mac) or `Ctrl+I` (Windows/Linux) to open Composer:

```
I need to sync data between my application and a Google Sheet.
The sheet is at https://docs.google.com/spreadsheets/d/abc123/edit

Create a Python module that:
1. Reads the product data from the sheet
2. Validates the data format
3. Exports it as JSON
```

### Code Generation

```
Generate a Python script that updates the metrics sheet at
https://docs.google.com/spreadsheets/d/abc123/edit
with data from my application's database.
```

## Skill Location

The skill is installed to:

```
~/.cursor/skills/gsheets/
```

## Integration with Cursor Rules

You can create a `.cursorrules` file in your project to automatically include Google Sheets context:

```
When working with Google Sheets:
- Use the gsheets skill from ~/.cursor/skills/gsheets/
- Always verify access before operations
- Use formulas instead of hardcoded values
- Batch operations when possible to avoid rate limits
```

## Updating the Skill

To update to the latest version:

1. Open Cursor's terminal
2. Re-run the install command from the ExtraSuite homepage

## Uninstalling

To remove the skill:

```bash
rm -rf ~/.cursor/skills/gsheets
```

## Troubleshooting

### Cursor Doesn't Find the Skill

1. Make sure the skill directory exists
2. Try explicitly mentioning the skill in your prompt:
   ```
   Using the gsheets skill from ~/.cursor/skills/gsheets,
   read the data from [spreadsheet-url]
   ```

### "Permission Denied" When Accessing Spreadsheet

1. Verify you've shared the spreadsheet with your service account email
2. Run the verification script in Cursor's terminal:
   ```bash
   ~/.cursor/skills/gsheets/venv/bin/python ~/.cursor/skills/gsheets/verify_access.py <spreadsheet-url>
   ```

### Token Expired

Tokens expire after 1 hour. The skill will prompt you to re-authenticate when needed.

## Advanced: Custom Cursor Extension

If you frequently work with Google Sheets, consider creating a custom Cursor extension or command that wraps the skill functionality.

---

**Next Steps:**

- [Learn effective prompting techniques](../../user-guide/prompting.md)
- [Understand how to share documents](../../user-guide/sharing.md)
- [Explore the Google Sheets skill reference](../../skills/sheets.md)
