"""Shared utilities for all CLI domain modules."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    from extrasuite.client.credentials import Credential

_HELP_DIR = Path(__file__).parent.parent / "help"

# Maps plural CLI names (used in subparser/dispatch) to help directory names
_HELP_MODULE_MAP: dict[str, str] = {
    "docs": "doc",
    "sheets": "sheet",
    "slides": "slide",
    "forms": "form",
}

# Files served by --help; everything else in the module dir is a reference doc.
_HELP_COMMAND_FILES = frozenset(
    {
        "README.md",
        "pull.md",
        "pull-md.md",
        "push.md",
        "push-md.md",
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
    else:
        module_dir = _HELP_MODULE_MAP.get(module, module)
        if command is None:
            path = _HELP_DIR / module_dir / "README.md"
        else:
            path = _HELP_DIR / module_dir / f"{command}.md"
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
    module_dir_name = _HELP_MODULE_MAP.get(module, module)
    module_dir = _HELP_DIR / module_dir_name
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


def _parse_drive_file_id(id_or_url: str) -> str:
    """Extract file ID from any Google Drive/Docs/Sheets/Slides/Forms URL.

    Tries all known URL patterns. Falls back to returning the input as-is if
    no pattern matches (assumes it is already a raw file ID).
    """
    import re

    patterns = [
        r"docs\.google\.com/spreadsheets/d/([a-zA-Z0-9_-]+)",
        r"docs\.google\.com/presentation/d/([a-zA-Z0-9_-]+)",
        r"docs\.google\.com/document/d/([a-zA-Z0-9_-]+)",
        r"docs\.google\.com/forms/d/(?:e/)?([a-zA-Z0-9_-]+)",
        r"drive\.google\.com/(?:file/d/|open\?id=)([a-zA-Z0-9_-]+)",
        r"script\.google\.com/(?:d/)?([a-zA-Z0-9_-]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, id_or_url)
        if match:
            return match.group(1)
    return id_or_url


_URL_PARSERS: dict[str, Callable[[str], str]] = {
    "sheet": _parse_spreadsheet_id,
    "slide": _parse_presentation_id,
    "doc": _parse_document_id,
    "form": _parse_form_id,
    "script": _parse_drive_file_id,
}


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


def _get_reason(args: Any, *, default: str) -> str:
    """Resolve the reason string for a token request.

    Precedence: --reason CLI flag > EXTRASUITE_REASON env var > hardcoded default.
    """
    import os

    return (
        getattr(args, "reason", None)
        or os.environ.get("EXTRASUITE_REASON", "")
        or default
    )


def _get_credential(args: Any, *, command: dict[str, Any], reason: str) -> Credential:
    """Obtain a credential for the given typed command via CredentialsManager."""
    from extrasuite.client import CredentialsManager

    manager = CredentialsManager(**_auth_kwargs(args))
    return manager.get_credential(command=command, reason=reason)


def _trusted_contacts_setup(access_token: str) -> Any:
    """Load trusted contacts and set user_domain from the authenticated user's email."""
    from extrasuite.client.gmail_reader import get_user_email
    from extrasuite.client.settings import load_trusted_contacts

    trusted = load_trusted_contacts()
    user_email = get_user_email(access_token)
    if "@" in user_email:
        trusted.user_domain = user_email.split("@", 1)[1].lower()
    return trusted


_SETTINGS_PATH = Path.home() / ".config" / "extrasuite" / "settings.toml"


def _cmd_share(file_type: str, args: Any) -> None:
    """Share a Google file with one or more trusted email addresses."""
    from extrasuite.client.google_api import share_file
    from extrasuite.client.settings import load_trusted_contacts

    # 1. Load trusted contacts (no user_domain injection — settings.toml is explicit)
    trusted = load_trusted_contacts()

    # 2. Validate all emails before any API call
    untrusted = [e for e in args.emails if not trusted.is_trusted(e)]
    if untrusted:
        for e in untrusted:
            print(f"Error: {e} is not in your trusted contacts list.", file=sys.stderr)
        print(
            f"Edit {_SETTINGS_PATH} to add trusted domains or emails.",
            file=sys.stderr,
        )
        sys.exit(1)

    # 3. Parse file ID using type-specific URL parser
    file_id = _URL_PARSERS[file_type](args.url)

    # 4. Get DWD credential for drive.file.share
    reason = _get_reason(args, default=f"Share {file_type} with users")
    cred = _get_credential(
        args,
        command={
            "type": "drive.file.share",
            "file_url": args.url,
            "file_name": "",
            "share_with": args.emails,
        },
        reason=reason,
    )
    access_token = cred.token

    # 5. Share with each email, collect results
    role = args.role
    for email in args.emails:
        share_file(access_token, file_id, email, role=role)
        print(f"Shared with {email} ({role})")


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


def _cmd_create(file_type: str, args: Any) -> tuple[str, str]:
    """Create a Google file and share it with the service account.

    Returns (file_id, url).
    """
    from extrasuite.client import CredentialsManager
    from extrasuite.client.google_api import create_file_via_drive, share_file

    manager = CredentialsManager(**_auth_kwargs(args))

    # Get credential for drive.file.create — SA email is always in metadata
    reason = _get_reason(
        args, default=f"Create {file_type} and share with service account"
    )
    cred = manager.get_credential(
        command={
            "type": "drive.file.create",
            "file_name": args.title,
            "file_type": file_type,
        },
        reason=reason,
    )
    oauth_token_access = cred.token
    sa_email = cred.service_account_email
    if not sa_email:
        raise RuntimeError(
            "Could not determine service account email. Cannot share file."
        )

    copy_from = getattr(args, "copy_from", None)

    if copy_from:
        from extrasuite.client.google_api import copy_drive_file

        source_id = _parse_drive_file_id(copy_from)
        result = copy_drive_file(oauth_token_access, source_id, title=args.title)
    else:
        # Create the file via Drive API
        mime_type = _CREATE_MIME_TYPES[file_type]
        result = create_file_via_drive(oauth_token_access, args.title, mime_type)

    file_id = result["id"]

    # Share with service account
    share_file(oauth_token_access, file_id, sa_email)

    url = _FILE_URL_PATTERNS[file_type].format(id=file_id)
    print(f"\nCreated {file_type}: {args.title}")
    print(f"URL: {url}")
    print(f"Shared with: {sa_email}")
    return file_id, url
