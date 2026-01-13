#!/usr/bin/env python3
"""
Google Sheets Skill - Environment Setup and Validation

This script uses only Python standard library modules.
Run with: python3 checks.py

On success, prints the path to the venv Python interpreter.
On failure, prints error messages and instructions.

Exit codes:
  0 - Success, environment ready
  1 - Error (see output for details)
"""

import json
import os
import subprocess
import sys
import venv
from pathlib import Path


# Configuration
SKILL_DIR = Path(__file__).parent.resolve()
VENV_DIR = SKILL_DIR / "venv"
REQUIREMENTS_FILE = SKILL_DIR / "requirements.txt"

# Python interpreter path (cross-platform)
if sys.platform == "win32":
    VENV_PYTHON = VENV_DIR / "Scripts" / "python.exe"
    VENV_PIP = VENV_DIR / "Scripts" / "pip.exe"
else:
    VENV_PYTHON = VENV_DIR / "bin" / "python"
    VENV_PIP = VENV_DIR / "bin" / "pip"


def error(message, instructions=None):
    """Print error and optional instructions, then exit."""
    print(f"ERROR: {message}", file=sys.stderr)
    if instructions:
        print("\nINSTRUCTIONS:", file=sys.stderr)
        for line in instructions:
            print(f"  {line}", file=sys.stderr)
    sys.exit(1)


def info(message):
    """Print info message to stderr (keep stdout clean for machine output)."""
    print(f"[gsheet-skill] {message}", file=sys.stderr)


def check_python_version():
    """Ensure Python 3.8+ is available."""
    if sys.version_info < (3, 8):
        error(
            f"Python 3.8+ required, found {sys.version_info.major}.{sys.version_info.minor}",
            ["Install Python 3.8 or later from https://www.python.org/downloads/"]
        )


def create_venv():
    """Create virtual environment if it doesn't exist."""
    if VENV_DIR.exists() and VENV_PYTHON.exists():
        return False  # Already exists

    info(f"Creating virtual environment at {VENV_DIR}")
    try:
        venv.create(VENV_DIR, with_pip=True)
    except Exception as e:
        error(
            f"Failed to create virtual environment: {e}",
            [
                "Ensure you have write permissions to the skill directory",
                f"Try manually: python3 -m venv {VENV_DIR}"
            ]
        )

    if not VENV_PYTHON.exists():
        error(
            "Virtual environment created but Python interpreter not found",
            [f"Expected at: {VENV_PYTHON}"]
        )

    return True  # Newly created


def install_dependencies():
    """Install dependencies from requirements.txt."""
    if not REQUIREMENTS_FILE.exists():
        error(
            f"requirements.txt not found at {REQUIREMENTS_FILE}",
            ["Ensure requirements.txt exists in the skill directory"]
        )

    # Check if gspread is already installed
    check_cmd = [str(VENV_PYTHON), "-c", "import gspread; print(gspread.__version__)"]
    result = subprocess.run(check_cmd, capture_output=True, text=True)
    if result.returncode == 0:
        return False  # Already installed

    info("Installing dependencies...")
    pip_cmd = [
        str(VENV_PYTHON), "-m", "pip", "install",
        "--quiet", "--upgrade", "-r", str(REQUIREMENTS_FILE)
    ]
    result = subprocess.run(pip_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        error(
            f"Failed to install dependencies: {result.stderr}",
            [
                f"Try manually: {VENV_PYTHON} -m pip install -r {REQUIREMENTS_FILE}",
                "Check your internet connection"
            ]
        )
    return True  # Newly installed


def main():
    """Run all checks and setup."""
    check_python_version()

    venv_created = create_venv()
    deps_installed = install_dependencies()

    if venv_created:
        info("Virtual environment created")
    if deps_installed:
        info("Dependencies installed")

    # Success - print machine-readable output to stdout
    output = {
        "status": "ok",
        "venv_python": str(VENV_PYTHON),
        "skill_dir": str(SKILL_DIR),
        "message": "Environment ready. Use verify_access.py to test spreadsheet access."
    }
    print(json.dumps(output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
