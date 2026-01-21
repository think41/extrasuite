# Windows PowerShell Installation

This guide walks you through installing ExtraSuite skills on Windows using PowerShell.

## Prerequisites

1. **Windows 10 or later** (PowerShell 5.1+ required)
2. **An AI coding assistant** installed:
    - Claude Code
    - Codex CLI
    - Gemini CLI
    - Cursor
3. **Python 3.8+** installed and in PATH

## Checking Your Setup

### Verify PowerShell Version

Open PowerShell and run:

```powershell
$PSVersionTable.PSVersion
```

You need version 5.1 or higher (ideally PowerShell 7+).

### Verify Python Installation

```powershell
python --version
```

If Python isn't installed, download it from [python.org](https://www.python.org/downloads/windows/) or install via Windows Store.

## Installation

### Step 1: Sign In to ExtraSuite

1. Open [extrasuite.think41.com](https://extrasuite.think41.com) in your browser
2. Click **Sign In** or **Get Started**
3. Authenticate with your Google Workspace account

### Step 2: Copy the Windows Install Command

After signing in, click the **Windows (PowerShell)** tab to see your personalized command.

### Step 3: Run the Install Command

Open PowerShell (search for "PowerShell" in the Start menu) and paste:

```powershell
irm "https://extrasuite.think41.com/api/skills/install/<your-token>?ps=true" | iex
```

!!! warning "Execution Policy"
    If you get an execution policy error, run PowerShell as Administrator and execute:
    ```powershell
    Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
    ```

### Step 4: Verify Installation

Check that the skill was installed:

```powershell
Get-ChildItem ~\.claude\skills\gsheets\
```

You should see:

```
SKILL.md
checks.py
verify_access.py
gsheet_utils.py
requirements.txt
```

## What the Installer Does

The PowerShell installer:

1. Downloads the skill files
2. Creates the appropriate directory structure:
   - `~\.claude\skills\gsheets\` for Claude Code
   - `~\.codex\skills\gsheets\` for Codex CLI
   - `~\.gemini\skills\gsheets\` for Gemini CLI
   - `~\.cursor\skills\gsheets\` for Cursor
3. Sets up Python virtual environment
4. Installs required dependencies

## Directory Locations

On Windows, skills are installed to:

| Agent | Location |
|-------|----------|
| Claude Code | `%USERPROFILE%\.claude\skills\gsheets\` |
| Codex CLI | `%USERPROFILE%\.codex\skills\gsheets\` |
| Gemini CLI | `%USERPROFILE%\.gemini\skills\gsheets\` |
| Cursor | `%USERPROFILE%\.cursor\skills\gsheets\` |

## Running the Skill

### Python Virtual Environment

The skill uses a Python virtual environment. To run scripts manually:

```powershell
~\.claude\skills\gsheets\venv\Scripts\python.exe your_script.py
```

### Verify Access to a Spreadsheet

```powershell
~\.claude\skills\gsheets\venv\Scripts\python.exe ~\.claude\skills\gsheets\verify_access.py <spreadsheet-url>
```

## Troubleshooting

### "irm is not recognized"

Make sure you're using PowerShell, not Command Prompt. `irm` is short for `Invoke-RestMethod`, a PowerShell cmdlet.

### Execution Policy Error

Run PowerShell as Administrator:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

Then close and reopen PowerShell.

### Python Not Found

1. Install Python from [python.org](https://www.python.org/downloads/windows/)
2. During installation, check **"Add Python to PATH"**
3. Restart PowerShell after installation

### SSL Certificate Errors

If you're behind a corporate proxy:

```powershell
[System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]::Tls12
irm "https://extrasuite.think41.com/api/skills/install/<your-token>?ps=true" | iex
```

### Permission Errors

Run PowerShell as Administrator for the installation, then use normal PowerShell for daily work.

## Alternative: Windows Terminal

For a better terminal experience, consider using [Windows Terminal](https://aka.ms/terminal):

1. Install from Microsoft Store
2. Open Windows Terminal
3. Use PowerShell profile
4. Run the install command

## Updating the Skill

To update to the latest version, re-run the install command from the ExtraSuite homepage.

## Uninstalling

To remove the skill:

```powershell
Remove-Item -Recurse -Force ~\.claude\skills\gsheets
```

---

**Next Steps:**

- [Learn effective prompting techniques](../../user-guide/prompting.md)
- [Understand how to share documents](../../user-guide/sharing.md)
- [Explore the Google Sheets skill reference](../../skills/sheets.md)

---

**Prefer WSL?** See the [Windows (WSL) installation guide](windows-wsl.md) for using Linux commands on Windows.
