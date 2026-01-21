# Windows WSL Installation

This guide walks you through installing ExtraSuite skills on Windows using Windows Subsystem for Linux (WSL).

## Prerequisites

1. **Windows 10 version 2004+** or **Windows 11**
2. **WSL 2 installed** with a Linux distribution (Ubuntu recommended)
3. **An AI coding assistant** installed within WSL
4. **Python 3.8+** installed in your WSL environment

## Why Use WSL?

WSL provides a native Linux environment on Windows, offering:

- Better compatibility with Linux-based tools
- Same installation process as macOS/Linux
- Better Python virtual environment handling
- Native bash scripting support

## Setting Up WSL

### Install WSL (if not already installed)

Open PowerShell as Administrator and run:

```powershell
wsl --install
```

This installs WSL 2 with Ubuntu by default. Restart your computer when prompted.

### Verify WSL Installation

```powershell
wsl --list --verbose
```

You should see your Linux distribution listed with VERSION 2.

### Access WSL

Click the Start menu and search for "Ubuntu" (or your installed distribution), or run:

```powershell
wsl
```

## Installation

### Step 1: Set Up Python in WSL

Update packages and install Python:

```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv
```

Verify installation:

```bash
python3 --version
```

### Step 2: Sign In to ExtraSuite

1. Open [extrasuite.think41.com](https://extrasuite.think41.com) in your Windows browser
2. Click **Sign In** or **Get Started**
3. Authenticate with your Google Workspace account

### Step 3: Run the Install Command

In your WSL terminal, paste the macOS/Linux install command:

```bash
curl -fsSL https://extrasuite.think41.com/api/skills/install/<your-token> | bash
```

### Step 4: Verify Installation

Check that the skill was installed:

```bash
ls ~/.claude/skills/gsheets/
```

You should see:

```
SKILL.md
checks.py
verify_access.py
gsheet_utils.py
requirements.txt
```

## Browser Authentication

When the skill needs to authenticate, it will attempt to open a browser. In WSL:

### Option 1: Windows Browser Integration

If you have `wslu` installed (default on recent Ubuntu WSL):

```bash
sudo apt install wslu
```

The `wslview` command will open URLs in your Windows browser automatically.

### Option 2: Manual Authentication

If browser doesn't open automatically:

1. Copy the URL shown in the terminal
2. Paste it in your Windows browser
3. Complete authentication
4. The callback will work automatically

### Option 3: Set Browser Variable

```bash
export BROWSER=wslview
```

Add this to your `~/.bashrc` for persistence.

## Directory Structure

In WSL, skills are installed to your Linux home directory:

```
/home/<your-username>/.claude/skills/gsheets/
```

This is equivalent to `~/.claude/skills/gsheets/`.

## Running AI Agents in WSL

### Claude Code in WSL

Install Claude Code in your WSL environment following the Linux instructions. The skill will be automatically available.

### VS Code + WSL

If you use VS Code with the Remote - WSL extension:

1. Open VS Code
2. Click the green button in the bottom-left corner
3. Select "New WSL Window"
4. The WSL terminal has access to your installed skills

### Cursor + WSL

Cursor can connect to WSL:

1. Install Cursor on Windows
2. Open a folder in WSL using the Remote - WSL extension
3. Use the integrated terminal for skill operations

## Accessing Windows Files

Your Windows files are accessible in WSL at:

```bash
/mnt/c/Users/<your-windows-username>/
```

For example, to access your Windows Documents:

```bash
cd /mnt/c/Users/YourName/Documents
```

## Troubleshooting

### curl Not Found

Install curl:

```bash
sudo apt install curl
```

### Python Virtual Environment Errors

Install venv support:

```bash
sudo apt install python3-venv
```

### Permission Denied on Scripts

Make scripts executable:

```bash
chmod +x ~/.claude/skills/gsheets/*.py
```

### Browser Doesn't Open

Set the browser variable:

```bash
export BROWSER=wslview
# Or use Windows browser directly
export BROWSER="/mnt/c/Program Files/Google/Chrome/Application/chrome.exe"
```

### Network Issues

If you're behind a corporate proxy, configure proxy in WSL:

```bash
export HTTP_PROXY=http://proxy.company.com:8080
export HTTPS_PROXY=http://proxy.company.com:8080
```

### DNS Resolution Problems

If you can't reach external sites, update WSL's DNS:

```bash
sudo nano /etc/resolv.conf
```

Add:
```
nameserver 8.8.8.8
nameserver 8.8.4.4
```

## Performance Tips

### Use WSL 2

WSL 2 has better performance than WSL 1:

```powershell
wsl --set-version Ubuntu 2
```

### Keep Files in WSL Filesystem

For best performance, keep your projects in the Linux filesystem (`~/`) rather than `/mnt/c/`.

## Updating the Skill

To update to the latest version:

```bash
curl -fsSL https://extrasuite.think41.com/api/skills/install/<your-token> | bash
```

## Uninstalling

To remove the skill:

```bash
rm -rf ~/.claude/skills/gsheets
```

---

**Next Steps:**

- [Learn effective prompting techniques](../../user-guide/prompting.md)
- [Understand how to share documents](../../user-guide/sharing.md)
- [Explore the Google Sheets skill reference](../../skills/sheets.md)

---

**Prefer native PowerShell?** See the [Windows (PowerShell) installation guide](windows-powershell.md).
