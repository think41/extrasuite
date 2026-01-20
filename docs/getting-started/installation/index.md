# Installation Guide

ExtraSuite supports multiple AI coding assistants and operating systems. Choose the guide that matches your setup.

## Supported Platforms

### AI Agents

| Platform | Status | Installation Guide |
|----------|--------|-------------------|
| **Claude Code** | :material-check-circle:{ .text-green } Supported | [View Guide](claude-code.md) |
| **Codex CLI** | :material-check-circle:{ .text-green } Supported | [View Guide](codex.md) |
| **Gemini CLI** | :material-check-circle:{ .text-green } Supported | [View Guide](gemini-cli.md) |
| **Claude Coworks** | :material-check-circle:{ .text-green } Supported | [View Guide](claude-coworks.md) |
| **Cursor** | :material-check-circle:{ .text-green } Supported | [View Guide](cursor.md) |

### Operating Systems

| OS | Installation Method |
|----|-------------------|
| **macOS** | `curl \| bash` |
| **Linux** | `curl \| bash` |
| **Windows (PowerShell)** | `irm \| iex` - [View Guide](windows-powershell.md) |
| **Windows (WSL)** | `curl \| bash` - [View Guide](windows-wsl.md) |

## Universal Install Process

Regardless of which AI agent you use, the installation process is the same:

### Step 1: Sign In to ExtraSuite

Visit [extrasuite.think41.com](https://extrasuite.think41.com) and sign in with your Google Workspace account.

### Step 2: Copy Your Install Command

After signing in, you'll see a personalized install command. The command includes a token that:

- Is unique to your account
- Is valid for 5 minutes
- Installs the skill for all supported AI agents at once

### Step 3: Run the Command

=== "macOS / Linux"

    Open Terminal and paste the command:

    ```bash
    curl -fsSL https://extrasuite.think41.com/api/skills/install/<your-token> | bash
    ```

=== "Windows (PowerShell)"

    Open PowerShell and paste the command:

    ```powershell
    irm "https://extrasuite.think41.com/api/skills/install/<your-token>?ps=true" | iex
    ```

### Step 4: Verify Installation

The installer will confirm which skills were installed and where.

## What Gets Installed

The installer creates skill files in the standard locations for each AI agent:

| Agent | Skill Location |
|-------|---------------|
| Claude Code | `~/.claude/skills/gsheets/` |
| Codex CLI | `~/.codex/skills/gsheets/` |
| Gemini CLI | `~/.gemini/skills/gsheets/` |
| Cursor | `~/.cursor/skills/gsheets/` |

Each skill directory contains:

- `SKILL.md` - Instructions for the AI agent
- `checks.py` - Environment verification script
- `verify_access.py` - Spreadsheet access verification
- `gsheet_utils.py` - Utility functions
- `requirements.txt` - Python dependencies

## Troubleshooting

### Token Expired

If you see an error about an invalid or expired token, refresh the ExtraSuite homepage to get a new install command.

### Permission Denied

On macOS/Linux, you may need to ensure curl has execute permissions:

```bash
chmod +x /usr/bin/curl
```

### Firewall Issues

Make sure your firewall allows HTTPS connections to `extrasuite.think41.com`.

### Multiple Agents

The install script automatically detects and installs for all supported agents on your system. If you only want to install for specific agents, see the platform-specific guides.

---

Choose your platform for detailed instructions:

- [Claude Code](claude-code.md)
- [Codex CLI](codex.md)
- [Gemini CLI](gemini-cli.md)
- [Claude Coworks](claude-coworks.md)
- [Cursor](cursor.md)
- [Windows (PowerShell)](windows-powershell.md)
- [Windows (WSL)](windows-wsl.md)
