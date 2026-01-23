# Gemini CLI Installation

This guide walks you through installing ExtraSuite skills for [Gemini CLI](https://ai.google.dev/gemini-api/docs/aistudio-quickstart), Google's AI coding assistant.

## Prerequisites

1. **Gemini CLI installed** - Follow the [official installation guide](https://ai.google.dev/gemini-api/docs/aistudio-quickstart)
2. **Google AI API key** (requires paid tier for production use)
3. **Terminal access** (macOS, Linux, or Windows with WSL)

## Installation

### Step 1: Sign In to ExtraSuite

1. Open [extrasuite.think41.com](https://extrasuite.think41.com)
2. Click **Sign In** or **Get Started**
3. Authenticate with your Google Workspace account

### Step 2: Run the Install Command

After signing in, copy the install command shown on the homepage:

=== "macOS / Linux"

    ```bash
    curl -fsSL https://extrasuite.think41.com/api/skills/install/<your-token> | bash
    ```

=== "Windows (WSL)"

    ```bash
    curl -fsSL https://extrasuite.think41.com/api/skills/install/<your-token> | bash
    ```

### Step 3: Verify Installation

Check that the skill was installed:

```bash
ls ~/.gemini/skills/gsheets/
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

When you mention a Google Sheets URL or ask Gemini to work with spreadsheets, it will:

1. **Detect the skill** - Gemini reads the `SKILL.md` file for instructions
2. **Set up the environment** - Run `checks.py` to create a virtual environment
3. **Authenticate** - Opens browser if token is missing or expired
4. **Execute your request** - Uses the gspread library to interact with Google Sheets

## Usage Examples

### Reading Data

```
Read the sales data from https://docs.google.com/spreadsheets/d/abc123/edit
and summarize the top 10 products by revenue.
```

### Writing Data

```
Update cell B5 in https://docs.google.com/spreadsheets/d/abc123/edit
with the formula =SUM(B2:B4)
```

### Data Transformation

```
Take the raw data in Sheet1 of https://docs.google.com/spreadsheets/d/abc123/edit
and create a pivot table in Sheet2 showing revenue by month and product category.
```

## Skill Location

The skill is installed to:

```
~/.gemini/skills/gsheets/
```

This is the standard location where Gemini CLI looks for skills.

## Integration with Google Ecosystem

Since both Gemini CLI and ExtraSuite use Google authentication, the integration is seamless. Your Google Workspace credentials work across both systems.

!!! tip "Same Google Account"
    For the best experience, use the same Google account for both Gemini CLI and ExtraSuite authentication.

## Updating the Skill

To update to the latest version, re-run the install command from the ExtraSuite homepage.

## Uninstalling

To remove the skill:

```bash
rm -rf ~/.gemini/skills/gsheets
```

## Troubleshooting

### Gemini Doesn't Recognize the Skill

Make sure the skill directory exists and contains `SKILL.md`:

```bash
cat ~/.gemini/skills/gsheets/SKILL.md | head -20
```

### "Permission Denied" When Accessing Spreadsheet

1. Verify you've shared the spreadsheet with your service account email
2. Run the verification script:
   ```bash
   ~/.gemini/skills/gsheets/venv/bin/python ~/.gemini/skills/gsheets/verify_access.py <spreadsheet-url>
   ```

### Token Expired

Tokens expire after 1 hour. Gemini will automatically prompt you to re-authenticate when needed.

## Advanced Configuration

### Custom Skill Location

If you need to install to a different location, set the `GEMINI_SKILLS_DIR` environment variable before running the installer:

```bash
export GEMINI_SKILLS_DIR=/path/to/custom/skills
curl -fsSL https://extrasuite.think41.com/api/skills/install/<your-token> | bash
```

---

## Continue to Quick Start

You've completed the Gemini CLI installation. Continue to the Quick Start guide to learn how to use ExtraSuite:

[:octicons-arrow-right-24: Continue to Start Using ExtraSuite](../index.md#start-using-extrasuite)

---

**Additional Resources:**

- [Learn effective prompting techniques](../../user-guide/prompting.md)
- [Understand how to share documents](../../user-guide/sharing.md)
- [Explore the Google Sheets skill reference](../../skills/sheets.md)
