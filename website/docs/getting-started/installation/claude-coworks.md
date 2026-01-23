# Claude Coworks Installation

This guide walks you through installing ExtraSuite skills for [Claude Coworks](https://claude.ai/coworks), Anthropic's collaborative AI workspace.

## Prerequisites

1. **Claude Coworks access** - Available through [claude.ai/coworks](https://claude.ai/coworks)
2. **Active Claude subscription** (Pro or Team plan required)
3. **Terminal access** for initial setup (macOS, Linux, or Windows)

## What is Claude Coworks?

Claude Coworks is Anthropic's collaborative workspace that allows Claude to work on longer tasks with persistent context. Unlike Claude Code which runs in your terminal, Coworks runs in a browser-based environment.

## Installation

### Step 1: Sign In to ExtraSuite

1. Open [extrasuite.think41.com](https://extrasuite.think41.com)
2. Click **Sign In** or **Get Started**
3. Authenticate with your Google Workspace account
4. **Note your service account email** - you'll need this for sharing documents

### Step 2: Run the Install Command

The install command sets up skills that work across all Claude products:

=== "macOS / Linux"

    ```bash
    curl -fsSL https://extrasuite.think41.com/api/skills/install/<your-token> | bash
    ```

=== "Windows (PowerShell)"

    ```powershell
    irm "https://extrasuite.think41.com/api/skills/install/<your-token>?ps=true" | iex
    ```

### Step 3: Using with Coworks

In Claude Coworks, you can reference the skill in your prompts:

```
I need to work with Google Sheets. Use the gsheets skill to read and
analyze the data in https://docs.google.com/spreadsheets/d/abc123/edit
```

!!! note "Coworks Environment"
    Claude Coworks may have its own skill discovery mechanism. The local installation ensures compatibility and provides the skill files that Coworks can reference.

## How It Works

When working in Coworks:

1. **Mention the spreadsheet URL** in your prompt
2. **Claude recognizes** it needs Google Sheets access
3. **Authentication** happens seamlessly using your ExtraSuite credentials
4. **Claude executes** the requested operations

## Usage Examples

### Long-Running Analysis

```
Analyze the customer data in https://docs.google.com/spreadsheets/d/abc123/edit
over the past 12 months. Create monthly cohort analysis, identify trends,
and generate a summary report with recommendations.
```

### Multi-Step Workflows

```
1. Read the raw sales data from https://docs.google.com/spreadsheets/d/abc123/edit
2. Clean and normalize the data
3. Create a new sheet with aggregated metrics
4. Add charts for visualization
5. Write a summary of key findings
```

### Collaborative Document Updates

```
I'm preparing a quarterly report. Update the metrics sheet at
https://docs.google.com/spreadsheets/d/abc123/edit with the
following data: [your data]

Then format it with proper headers and conditional formatting.
```

## Sharing Documents with Coworks

Since Coworks sessions may run longer than typical Claude Code sessions, make sure to:

1. **Share documents with Editor access** if you want Claude to make changes
2. **Use specific, shared folders** for related documents
3. **Keep your service account email handy** for quick sharing

## Skill Location

The skill files are installed to:

```
~/.claude/skills/gsheets/
```

Coworks shares skill configurations with Claude Code.

## Updating the Skill

To update to the latest version, re-run the install command from the ExtraSuite homepage.

## Troubleshooting

### Coworks Can't Access the Spreadsheet

1. Verify the document is shared with your service account email
2. Check that the sharing permission is set to **Editor** (not just Viewer)
3. Make sure the spreadsheet URL is correct and accessible

### Authentication Issues

If you encounter authentication problems:

1. Clear your browser cookies for extrasuite.think41.com
2. Re-authenticate through the ExtraSuite homepage
3. Re-run the install command to refresh your credentials

### Session Timeout

Coworks sessions can be long-running. If you encounter token expiration:

1. Claude will automatically handle re-authentication
2. You may be prompted to re-authorize if the session exceeds token lifetime

---

## Continue to Quick Start

You've completed the Claude Coworks installation. Continue to the Quick Start guide to learn how to use ExtraSuite:

[:octicons-arrow-right-24: Continue to Start Using ExtraSuite](../index.md#start-using-extrasuite)

---

**Additional Resources:**

- [Learn effective prompting techniques](../../user-guide/prompting.md)
- [Understand how to share documents](../../user-guide/sharing.md)
- [Explore the Google Sheets skill reference](../../skills/sheets.md)
