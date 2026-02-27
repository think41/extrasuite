"""Shared utilities for all CLI domain modules."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_HELP_DIR = Path(__file__).parent.parent / "help"

# Files served by --help; everything else in the module dir is a reference doc.
_HELP_COMMAND_FILES = frozenset(
    {
        "README.md",
        "pull.md",
        "push.md",
        "diff.md",
        "create.md",
        "batchupdate.md",
        "lint.md",
    }
)


def _load_help(module: str | None = None, command: str | None = None) -> str:
    """Load help text from bundled markdown files."""
    if module is None:
        path = _HELP_DIR / "README.md"
    elif command is None:
        path = _HELP_DIR / module / "README.md"
    else:
        path = _HELP_DIR / module / f"{command}.md"
    try:
        return path.read_text("utf-8").strip()
    except FileNotFoundError:
        return ""


def _print_help_topics(module: str, module_dir: Path) -> None:
    """List available reference topics for a module."""
    ref_files = sorted(
        f for f in module_dir.glob("*.md") if f.name not in _HELP_COMMAND_FILES
    )
    if not ref_files:
        print(f"No reference docs available for '{module}'.")
        return
    print(f"Reference docs for '{module}':\n")
    for f in ref_files:
        topic = f.stem
        # First non-empty line after stripping the leading # header
        description = ""
        for line in f.read_text("utf-8").splitlines():
            line = line.strip().lstrip("#").strip()
            if line:
                description = line
                break
        print(f"  extrasuite {module} help {topic:<26} {description}")


def cmd_module_help(args: Any) -> None:
    """Show reference documentation for a module."""
    module = args.command
    module_dir = _HELP_DIR / module
    topic: str | None = getattr(args, "topic", None)

    if topic:
        path = module_dir / f"{topic}.md"
        if not path.exists():
            print(f"Unknown topic '{topic}' for '{module}'.", file=sys.stderr)
            _print_help_topics(module, module_dir)
            sys.exit(1)
        print(path.read_text("utf-8"))
    else:
        _print_help_topics(module, module_dir)


# ---------------------------------------------------------------------------
# URL parsers
# ---------------------------------------------------------------------------


def _parse_spreadsheet_id(id_or_url: str) -> str:
    """Extract spreadsheet ID from URL or return as-is."""
    import re

    match = re.search(r"docs\.google\.com/spreadsheets/d/([a-zA-Z0-9_-]+)", id_or_url)
    return match.group(1) if match else id_or_url


def _parse_presentation_id(id_or_url: str) -> str:
    """Extract presentation ID from URL or return as-is."""
    import re

    match = re.search(r"docs\.google\.com/presentation/d/([a-zA-Z0-9_-]+)", id_or_url)
    return match.group(1) if match else id_or_url


def _parse_form_id(id_or_url: str) -> str:
    """Extract form ID from URL or return as-is."""
    import re

    match = re.search(r"docs\.google\.com/forms/d/(?:e/)?([a-zA-Z0-9_-]+)", id_or_url)
    return match.group(1) if match else id_or_url


def _parse_document_id(id_or_url: str) -> str:
    """Extract document ID from URL or return as-is."""
    import re

    match = re.search(r"docs\.google\.com/document/d/([a-zA-Z0-9_-]+)", id_or_url)
    return match.group(1) if match else id_or_url


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------


def _auth_kwargs(args: Any) -> dict[str, Any]:
    """Build CredentialsManager kwargs from parsed CLI args."""
    kwargs: dict[str, Any] = {}
    if getattr(args, "gateway", None):
        kwargs["gateway_config_path"] = args.gateway
    if getattr(args, "service_account", None):
        kwargs["service_account_path"] = args.service_account
    return kwargs


def _get_token(args: Any, *, reason: str, scope: str) -> str:
    """Get a service account token via CredentialsManager."""
    from extrasuite.client import CredentialsManager

    manager = CredentialsManager(**_auth_kwargs(args))
    token = manager.get_token(reason=reason, scope=scope)
    return token.access_token


def _get_oauth_token(
    args: Any, scopes: list[str], reason: str = "", file_hint: str = ""
) -> str:
    """Get an OAuth token via CredentialsManager."""
    from extrasuite.client import CredentialsManager

    manager = CredentialsManager(**_auth_kwargs(args))
    token = manager.get_oauth_token(scopes=scopes, reason=reason, file_hint=file_hint)
    return token.access_token


def _trusted_contacts_setup(access_token: str) -> Any:
    """Load trusted contacts and set user_domain from the authenticated user's email."""
    from extrasuite.client.gmail_reader import get_user_email
    from extrasuite.client.settings import load_trusted_contacts

    trusted = load_trusted_contacts()
    user_email = get_user_email(access_token)
    if "@" in user_email:
        trusted.user_domain = user_email.split("@", 1)[1].lower()
    return trusted


# ---------------------------------------------------------------------------
# Create helpers
# ---------------------------------------------------------------------------

_CREATE_MIME_TYPES: dict[str, str] = {
    "sheet": "application/vnd.google-apps.spreadsheet",
    "slide": "application/vnd.google-apps.presentation",
    "doc": "application/vnd.google-apps.document",
    "form": "application/vnd.google-apps.form",
}

_FILE_URL_PATTERNS: dict[str, str] = {
    "sheet": "https://docs.google.com/spreadsheets/d/{id}",
    "slide": "https://docs.google.com/presentation/d/{id}",
    "doc": "https://docs.google.com/document/d/{id}",
    "form": "https://docs.google.com/forms/d/{id}",
}


def _cmd_create(file_type: str, args: Any) -> None:
    """Create a Google file and share it with the service account."""
    from extrasuite.client import CredentialsManager
    from extrasuite.client.google_api import create_file_via_drive, share_file

    manager = CredentialsManager(**_auth_kwargs(args))

    # Get OAuth token with drive.file scope — v2 also returns the SA email in response
    oauth_token = manager.get_oauth_token(
        scopes=["drive.file"],
        reason=f"Create {file_type} and share with service account",
    )

    # Determine the service account email to share with.
    # v2: SA email is included in the access token response.
    # v1 (legacy): it isn't, so we fall back to a separate get_token() call.
    if oauth_token.service_account_email:
        sa_email = oauth_token.service_account_email
    else:
        sa_token = manager.get_token(
            reason=f"Get service account email for {file_type} create",
            scope="drive.file",
        )
        sa_email = sa_token.service_account_email
    if not sa_email:
        raise RuntimeError(
            "Could not determine service account email. Cannot share file."
        )

    # Create the file via Drive API
    mime_type = _CREATE_MIME_TYPES[file_type]
    result = create_file_via_drive(oauth_token.access_token, args.title, mime_type)
    file_id = result["id"]

    # Share with service account
    share_file(oauth_token.access_token, file_id, sa_email)

    url = _FILE_URL_PATTERNS[file_type].format(id=file_id)
    print(f"\nCreated {file_type}: {args.title}")
    print(f"URL: {url}")
    print(f"Shared with: {sa_email}")
    print(f"\nTo edit, run: extrasuite {file_type} pull {url}")
