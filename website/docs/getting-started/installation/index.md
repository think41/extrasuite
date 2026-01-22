# Installation Guide

ExtraSuite supports multiple AI coding assistants and operating systems. This guide covers installing the ExtraSuite skill for each platform.

---

## Before You Begin

Make sure you've completed the initial setup for your path:

=== "Organizations"

    Complete **Steps 1-3** of the [Organization Setup](../organization-setup.md):
    
    1. :material-check: ExtraSuite server deployed
    2. :material-check: AI editor installed
    3. :material-check: Signed up and have your service account email
    
    Then continue with [Step 4: Install the Skill](../organization-setup.md#step-4-install-the-skill)

=== "Individuals"

    Complete **Steps 1-5** of the [Individual Setup](../individual-setup.md):
    
    1. :material-check: AI editor installed
    2. :material-check: Google Cloud project created
    3. :material-check: Required APIs enabled
    4. :material-check: Service account created
    5. :material-check: Key file downloaded and configured
    
    Then continue with [Step 7: Install the Skills](../individual-setup.md#step-7-install-the-skills)

---

## Supported Platforms

### AI Coding Assistants

| Platform | Requirements | Guide |
|----------|--------------|-------|
| **Cursor** | Pro subscription | [:octicons-arrow-right-24: View Guide](cursor.md) |
| **Claude Code** | Pro or Team plan | [:octicons-arrow-right-24: View Guide](claude-code.md) |
| **Codex CLI** | Plus plan or higher | [:octicons-arrow-right-24: View Guide](codex.md) |
| **Gemini CLI** | Paid API key | [:octicons-arrow-right-24: View Guide](gemini-cli.md) |
| **Claude Coworks** | Pro or Team plan | [:octicons-arrow-right-24: View Guide](claude-coworks.md) |

### Operating Systems

| OS | Installation Method | Guide |
|----|---------------------|-------|
| **macOS** | `curl \| bash` | See platform guides above |
| **Linux** | `curl \| bash` | See platform guides above |
| **Windows (PowerShell)** | `irm \| iex` | [:octicons-arrow-right-24: View Guide](windows-powershell.md) |
| **Windows (WSL)** | `curl \| bash` | [:octicons-arrow-right-24: View Guide](windows-wsl.md) |

---

## Installation Methods

### Method 1: Organization Install (Recommended for Teams)

After signing in to your ExtraSuite server, you'll see a personalized install command:

=== "macOS / Linux"

    ```bash
    curl -fsSL https://your-extrasuite-url/api/skills/install/<your-token> | bash
    ```

=== "Windows (PowerShell)"

    ```powershell
    irm "https://your-extrasuite-url/api/skills/install/<your-token>?ps=true" | iex
    ```

!!! note "Token Validity"
    The install token is valid for **5 minutes**. Refresh the page to generate a new one if needed.

### Method 2: Individual Install (Manual)

For individual developers without a server:

1. Clone or download the skills from [GitHub](https://github.com/think41/extrasuite/tree/main/skills)

2. Copy to your AI agent's skill directory:

=== "Cursor"
    ```bash
    mkdir -p ~/.cursor/skills
    cp -r /path/to/extrasuite/skills/gsheets ~/.cursor/skills/
    ```

=== "Claude Code"
    ```bash
    mkdir -p ~/.claude/skills
    cp -r /path/to/extrasuite/skills/gsheets ~/.claude/skills/
    ```

=== "Codex CLI"
    ```bash
    mkdir -p ~/.codex/skills
    cp -r /path/to/extrasuite/skills/gsheets ~/.codex/skills/
    ```

=== "Gemini CLI"
    ```bash
    mkdir -p ~/.gemini/skills
    cp -r /path/to/extrasuite/skills/gsheets ~/.gemini/skills/
    ```

---

## What Gets Installed

The installer creates skill files in the standard location for each AI agent:

| Agent | Skill Location |
|-------|---------------|
| Cursor | `~/.cursor/skills/gsheets/` |
| Claude Code | `~/.claude/skills/gsheets/` |
| Codex CLI | `~/.codex/skills/gsheets/` |
| Gemini CLI | `~/.gemini/skills/gsheets/` |
| Claude Coworks | `~/.claude-coworks/skills/gsheets/` |

Each skill directory contains:

| File | Purpose |
|------|---------|
| `SKILL.md` | Instructions for the AI agent |
| `checks.py` | Environment verification script |
| `verify_access.py` | Spreadsheet access verification |
| `gsheet_utils.py` | Utility functions |
| `requirements.txt` | Python dependencies |

---

## Verify Installation

After installation, verify the skill files are in place:

```bash
# Replace with your agent's skill directory
ls ~/.cursor/skills/gsheets/
```

Expected output:
```
SKILL.md
checks.py
gsheet_utils.py
requirements.txt
verify_access.py
```

---

## Updating the Skill

To update to the latest version:

=== "Organizations"

    Re-run the install command from your ExtraSuite homepage.

=== "Individuals"

    Pull the latest version from GitHub and copy the files again.

---

## Uninstalling

To remove the skill:

```bash
# Replace with your agent's skill directory
rm -rf ~/.cursor/skills/gsheets
```

---

## Troubleshooting

### Token Expired

If you see "invalid or expired token":

1. Go back to your ExtraSuite homepage
2. Refresh the page to get a new install command
3. Run the new command

### Permission Denied

On macOS/Linux, ensure curl has internet access:

```bash
curl -I https://google.com
```

If blocked, check your firewall settings.

### Skill Not Recognized

If your AI agent doesn't recognize the skill:

1. Verify the skill directory exists
2. Check that `SKILL.md` is present
3. Restart your AI agent
4. Try explicitly mentioning the skill in your prompt

### Multiple Agents

The organization installer automatically detects and installs for all supported agents on your system. For individual setup, repeat the manual installation for each agent you use.

---

## Platform Guides

Choose your platform for detailed instructions:

<div class="grid cards" markdown>

-   :material-cursor-default-click:{ .lg .middle } **Cursor**

    ---

    AI-powered code editor with built-in agent skills.

    [:octicons-arrow-right-24: Installation Guide](cursor.md)

-   :material-robot:{ .lg .middle } **Claude Code**

    ---

    Anthropic's AI coding assistant.

    [:octicons-arrow-right-24: Installation Guide](claude-code.md)

-   :material-code-braces:{ .lg .middle } **Codex CLI**

    ---

    OpenAI's command-line coding assistant.

    [:octicons-arrow-right-24: Installation Guide](codex.md)

-   :material-google:{ .lg .middle } **Gemini CLI**

    ---

    Google's AI coding assistant.

    [:octicons-arrow-right-24: Installation Guide](gemini-cli.md)

-   :material-account-group:{ .lg .middle } **Claude Coworks**

    ---

    Collaborative AI workspace.

    [:octicons-arrow-right-24: Installation Guide](claude-coworks.md)

-   :material-microsoft-windows:{ .lg .middle } **Windows**

    ---

    PowerShell and WSL installation guides.

    [:octicons-arrow-right-24: PowerShell Guide](windows-powershell.md) | [:octicons-arrow-right-24: WSL Guide](windows-wsl.md)

</div>

---

## Next Steps

After installation, continue with your setup path:

- **Organizations:** [Step 5: Share Your Document](../organization-setup.md#step-5-share-your-document)
- **Individuals:** [Step 8: Share Documents and Start Using](../individual-setup.md#step-8-share-documents-and-start-using)

Or learn more about using ExtraSuite:

- **[Prompting Tips](../../user-guide/prompting.md)** - Write effective prompts
- **[Sharing Documents](../../user-guide/sharing.md)** - Share with your AI agent
- **[Skills Reference](../../skills/index.md)** - Detailed skill documentation
