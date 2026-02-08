# Skills Overview

ExtraSuite provides skills that enable AI agents to declaratively edit Google Workspace files. Each skill teaches your AI agent the pull-edit-diff-push workflow for a specific file type.

## Available Skills

| Skill | Status | Description |
|-------|--------|-------------|
| [Google Sheets](sheets.md) | :material-check-circle:{ .text-green } **Stable** | Read, write, and manipulate spreadsheets via TSV + JSON |
| [Google Docs](docs.md) | :material-check-circle:{ .text-green } **Stable** | Create and edit documents via structured local files |
| [Google Slides](slides.md) | :material-check-circle:{ .text-green } **Stable** | Build and edit presentations via SML (Slide Markup Language) |
| [Google Forms](forms.md) | :material-check-circle:{ .text-green } **Stable** | Create and edit forms via JSON |
| Google Apps Script | :material-clock:{ .text-gray } **Upcoming** | Manage bound scripts attached to Workspace files |

## What is a Skill?

A skill is a package that contains:

- **SKILL.md** - Instructions for the AI agent
- **Utility scripts** - Python code for common operations
- **Requirements** - Dependencies needed to run the skill
- **Authentication helpers** - Token management and verification

When your AI agent encounters a task related to a skill (like working with a spreadsheet), it reads the skill instructions and uses the provided utilities.

## The Core Workflow

All skills follow the same **pull-edit-diff-push** workflow:

```mermaid
graph LR
    A[Pull] --> B[Edit Locally]
    B --> C[Diff / Preview]
    C --> D[Push to Google]
```

This is a declarative approach - like Terraform for Google Workspace:

1. **Pull** downloads the Google file into a compact, LLM-friendly local representation
2. **Edit** - the agent modifies local files (TSV, SML XML, JSON) rather than making API calls
3. **Diff** compares local edits against the original and generates the `batchUpdate` API request (dry run)
4. **Push** applies the computed changes to the Google file

The agent never needs to understand Google's API request format. It just edits files.

## Why Declarative?

| Benefit | Explanation |
|---------|-------------|
| **Simpler for agents** | Edit a TSV file or XML markup instead of constructing complex API JSON |
| **Safer** | No code generation or execution needed. No arbitrary network calls. |
| **Auditable** | Changes are visible in Google Drive version history under the agent's identity |
| **Token-efficient** | Compact file formats minimize LLM token usage |
| **Consistent** | Same workflow across Sheets, Docs, Slides, and Forms |

## Skill Installation Location

Skills are installed in platform-specific directories:

| Platform | Location |
|----------|----------|
| Claude Code | `~/.claude/skills/` |
| Codex CLI | `~/.codex/skills/` |
| Gemini CLI | `~/.gemini/skills/` |
| Cursor | `~/.cursor/skills/` |

## Skill Updates

Skills are updated when you re-run the install command from ExtraSuite:

```bash
curl -fsSL https://extrasuite.think41.com/api/skills/install/<your-token> | bash
```

This downloads the latest version of all skills.

## Troubleshooting

### Skill Not Recognized

If your AI agent doesn't recognize the skill:

1. Verify the skill is installed:
   ```bash
   ls ~/.claude/skills/
   ```

2. Try explicitly referencing the skill in your prompt:
   ```
   Using ExtraSuite, read the data from...
   ```

### Environment Issues

If the skill fails to run:

1. Run the checks script:
   ```bash
   python3 ~/.claude/skills/<skill>/checks.py
   ```

2. Verify Python is installed:
   ```bash
   python3 --version
   ```

3. Recreate the virtual environment:
   ```bash
   rm -rf ~/.claude/skills/<skill>/venv
   python3 ~/.claude/skills/<skill>/checks.py
   ```

### Authentication Issues

If authentication fails:

1. Clear cached tokens:
   ```bash
   rm -f ~/.config/extrasuite/token.json
   ```

2. Re-authenticate via the ExtraSuite website
