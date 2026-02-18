"""Unified CLI for ExtraSuite.

Usage:
    extrasuite sheet    pull|diff|push|create|batchUpdate
    extrasuite slide    pull|diff|push|create
    extrasuite doc      pull|diff|push|create
    extrasuite form     pull|diff|push|create
    extrasuite script   pull|diff|push|create|lint
    extrasuite gmail    compose
    extrasuite calendar view
    extrasuite contacts sync|search|touch
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any

_HELP_DIR = Path(__file__).parent / "help"


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


def _parse_spreadsheet_id(id_or_url: str) -> str:
    """Extract spreadsheet ID from URL or return as-is."""
    match = re.search(r"docs\.google\.com/spreadsheets/d/([a-zA-Z0-9_-]+)", id_or_url)
    return match.group(1) if match else id_or_url


def _parse_presentation_id(id_or_url: str) -> str:
    """Extract presentation ID from URL or return as-is."""
    match = re.search(r"docs\.google\.com/presentation/d/([a-zA-Z0-9_-]+)", id_or_url)
    return match.group(1) if match else id_or_url


def _parse_form_id(id_or_url: str) -> str:
    """Extract form ID from URL or return as-is."""
    match = re.search(r"docs\.google\.com/forms/d/(?:e/)?([a-zA-Z0-9_-]+)", id_or_url)
    return match.group(1) if match else id_or_url


def _parse_document_id(id_or_url: str) -> str:
    """Extract document ID from URL or return as-is."""
    match = re.search(r"docs\.google\.com/document/d/([a-zA-Z0-9_-]+)", id_or_url)
    return match.group(1) if match else id_or_url


def _auth_kwargs(args: Any) -> dict[str, Any]:
    """Build CredentialsManager kwargs from parsed CLI args."""
    kwargs: dict[str, Any] = {}
    if getattr(args, "gateway", None):
        kwargs["gateway_config_path"] = args.gateway
    if getattr(args, "service_account", None):
        kwargs["service_account_path"] = args.service_account
    return kwargs


def _get_token(args: Any) -> str:
    """Get a service account token via CredentialsManager."""
    from extrasuite.client import CredentialsManager

    manager = CredentialsManager(**_auth_kwargs(args))
    token = manager.get_token()
    return token.access_token


def _get_oauth_token(args: Any, scopes: list[str], reason: str = "") -> str:
    """Get an OAuth token via CredentialsManager."""
    from extrasuite.client import CredentialsManager

    manager = CredentialsManager(**_auth_kwargs(args))
    token = manager.get_oauth_token(scopes=scopes, reason=reason)
    return token.access_token


# --- Sheet commands ---


def cmd_sheet_pull(args: Any) -> None:
    """Pull a Google Sheet."""
    from extrasheet import GoogleSheetsTransport, SheetsClient

    spreadsheet_id = _parse_spreadsheet_id(args.url)
    output_dir = Path(args.output_dir) if args.output_dir else Path()
    access_token = _get_token(args)
    max_rows = 0 if args.no_limit else args.max_rows

    async def _run() -> None:
        transport = GoogleSheetsTransport(access_token)
        client = SheetsClient(transport)
        try:
            files = await client.pull(
                spreadsheet_id,
                output_dir,
                max_rows=max_rows,
                save_raw=not args.no_raw,
            )
            print(f"\nPulled {len(files)} files to {output_dir / spreadsheet_id}/")
        finally:
            await transport.close()

    asyncio.run(_run())


def cmd_sheet_diff(args: Any) -> None:
    """Preview changes to a Google Sheet."""
    from extrasheet import SheetsClient

    client = SheetsClient.__new__(SheetsClient)
    _diff_result, requests, validation = client.diff(args.folder)

    if validation.blocks:
        print("BLOCKED:", file=sys.stderr)
        for msg in validation.blocks:
            print(f"  - {msg}", file=sys.stderr)
        sys.exit(1)

    if validation.warnings:
        print("Warnings:", file=sys.stderr)
        for msg in validation.warnings:
            print(f"  - {msg}", file=sys.stderr)
        print("Use --force to push anyway.", file=sys.stderr)

    if not requests:
        print("No changes detected.")
    else:
        print(json.dumps(requests, indent=2))


def cmd_sheet_push(args: Any) -> None:
    """Push changes to a Google Sheet."""
    from extrasheet import GoogleSheetsTransport, SheetsClient

    access_token = _get_token(args)

    async def _run() -> None:
        transport = GoogleSheetsTransport(access_token)
        client = SheetsClient(transport)
        try:
            result = client.push(args.folder, force=args.force)
            if asyncio.iscoroutine(result):
                result = await result
            print(result.message)
            if not result.success:
                sys.exit(1)
        finally:
            await transport.close()

    asyncio.run(_run())


def cmd_sheet_batchupdate(args: Any) -> None:
    """Execute raw batchUpdate requests."""
    from extrasheet import GoogleSheetsTransport

    spreadsheet_id = _parse_spreadsheet_id(args.url)
    requests_path = Path(args.requests_file)
    if not requests_path.exists():
        print(f"Error: File not found: {requests_path}", file=sys.stderr)
        sys.exit(1)

    requests_data = json.loads(requests_path.read_text())
    if isinstance(requests_data, dict) and "requests" in requests_data:
        requests_list = requests_data["requests"]
    elif isinstance(requests_data, list):
        requests_list = requests_data
    else:
        print(
            "Error: Expected a list of requests or {requests: [...]}", file=sys.stderr
        )
        sys.exit(1)

    access_token = _get_token(args)

    async def _run() -> None:
        transport = GoogleSheetsTransport(access_token)
        try:
            response = await transport.batch_update(spreadsheet_id, requests_list)
            print(f"Applied {len(requests_list)} requests.")
            if args.verbose:
                print(json.dumps(response, indent=2))
        finally:
            await transport.close()

    asyncio.run(_run())


# --- Slide commands ---


def cmd_slide_pull(args: Any) -> None:
    """Pull a Google Slides presentation."""
    from extraslide import GoogleSlidesTransport, SlidesClient

    presentation_id = _parse_presentation_id(args.url)
    output_dir = Path(args.output_dir) if args.output_dir else Path()
    access_token = _get_token(args)

    async def _run() -> None:
        transport = GoogleSlidesTransport(access_token)
        client = SlidesClient(transport)
        try:
            files = await client.pull(
                presentation_id,
                output_dir,
                save_raw=not args.no_raw,
            )
            print(f"\nPulled {len(files)} files to {output_dir / presentation_id}/")
        finally:
            await transport.close()

    asyncio.run(_run())


def cmd_slide_diff(args: Any) -> None:
    """Preview changes to a Google Slides presentation."""
    from extraslide import SlidesClient

    async def _run() -> None:
        client = SlidesClient.__new__(SlidesClient)
        requests = await client.diff(args.folder)
        if not requests:
            print("No changes detected.")
        else:
            print(json.dumps(requests, indent=2))

    asyncio.run(_run())


def cmd_slide_push(args: Any) -> None:
    """Push changes to a Google Slides presentation."""
    from extraslide import GoogleSlidesTransport, SlidesClient

    access_token = _get_token(args)

    async def _run() -> None:
        transport = GoogleSlidesTransport(access_token)
        client = SlidesClient(transport)
        try:
            response = await client.push(args.folder)
            count = len(response.get("replies", []))
            print(f"Push successful. Applied {count} changes.")
        finally:
            await transport.close()

    asyncio.run(_run())


# --- Form commands ---


def cmd_form_pull(args: Any) -> None:
    """Pull a Google Form."""
    from extraform import FormsClient, GoogleFormsTransport

    form_id = _parse_form_id(args.url)
    output_dir = Path(args.output_dir) if args.output_dir else Path()
    access_token = _get_token(args)

    async def _run() -> None:
        transport = GoogleFormsTransport(access_token)
        client = FormsClient(transport)
        try:
            result = await client.pull(
                form_id,
                output_dir,
                include_responses=args.responses,
                max_responses=args.max_responses,
                save_raw=not args.no_raw,
            )
            print(
                f"\nPulled {len(result.files_written)} files to {output_dir / form_id}/"
            )
        finally:
            await transport.close()

    asyncio.run(_run())


def cmd_form_diff(args: Any) -> None:
    """Preview changes to a Google Form."""
    from extraform import FormsClient

    client = FormsClient.__new__(FormsClient)
    _diff_result, requests = client.diff(Path(args.folder))
    if not requests:
        print("No changes detected.")
    else:
        print(json.dumps(requests, indent=2))


def cmd_form_push(args: Any) -> None:
    """Push changes to a Google Form."""
    from extraform import FormsClient, GoogleFormsTransport

    access_token = _get_token(args)

    async def _run() -> None:
        transport = GoogleFormsTransport(access_token)
        client = FormsClient(transport)
        try:
            result = await client.push(Path(args.folder), force=args.force)
            print(result.message)
            if not result.success:
                sys.exit(1)
        finally:
            await transport.close()

    asyncio.run(_run())


# --- Script commands ---


def cmd_script_pull(args: Any) -> None:
    """Pull a Google Apps Script project."""
    from extrascript import GoogleAppsScriptTransport, ScriptClient
    from extrascript.client import parse_script_id

    script_id = parse_script_id(args.url)
    output_dir = Path(args.output_dir) if args.output_dir else Path()
    access_token = _get_oauth_token(
        args,
        scopes=["script.projects"],
        reason="Pull Apps Script project",
    )

    async def _run() -> None:
        transport = GoogleAppsScriptTransport(access_token)
        client = ScriptClient(transport)
        try:
            files = await client.pull(
                script_id,
                output_dir,
                save_raw=not args.no_raw,
            )
            print(f"\nPulled {len(files)} files to {output_dir / script_id}/")
        finally:
            await transport.close()

    asyncio.run(_run())


def cmd_script_diff(args: Any) -> None:
    """Preview changes to a Google Apps Script project."""
    from extrascript import ScriptClient

    client = ScriptClient.__new__(ScriptClient)
    diff_result = client.diff(args.folder)
    if not diff_result.has_changes:
        print("No changes detected.")
    else:
        if diff_result.added:
            print(f"Added: {', '.join(diff_result.added)}")
        if diff_result.removed:
            print(f"Removed: {', '.join(diff_result.removed)}")
        if diff_result.modified:
            print(f"Modified: {', '.join(diff_result.modified)}")


def cmd_script_push(args: Any) -> None:
    """Push changes to a Google Apps Script project."""
    from extrascript import GoogleAppsScriptTransport, ScriptClient

    access_token = _get_oauth_token(
        args,
        scopes=["script.projects"],
        reason="Push Apps Script project",
    )

    async def _run() -> None:
        transport = GoogleAppsScriptTransport(access_token)
        client = ScriptClient(transport)
        try:
            if not args.skip_lint:
                lint_result = client.lint(args.folder)
                if lint_result.error_count > 0:
                    print("Lint errors found:", file=sys.stderr)
                    for d in lint_result.diagnostics:
                        print(f"  {d}", file=sys.stderr)
                    sys.exit(1)
                if lint_result.warning_count > 0:
                    print("Lint warnings:")
                    for d in lint_result.diagnostics:
                        print(f"  {d}")

            result = await client.push(args.folder)
            print(result.message)
            if not result.success:
                sys.exit(1)
        finally:
            await transport.close()

    asyncio.run(_run())


def cmd_script_create(args: Any) -> None:
    """Create a new Apps Script project."""
    from extrascript import GoogleAppsScriptTransport, ScriptClient
    from extrascript.client import parse_file_id

    access_token = _get_oauth_token(
        args,
        scopes=["script.projects"],
        reason="Create Apps Script project",
    )
    parent_id = parse_file_id(args.bind_to) if args.bind_to else None
    output_dir = Path(args.output_dir) if args.output_dir else Path()

    async def _run() -> None:
        transport = GoogleAppsScriptTransport(access_token)
        client = ScriptClient(transport)
        try:
            files = await client.create(
                args.title,
                output_dir,
                parent_id=parent_id,
            )
            print(f"Created project with {len(files)} files.")
        finally:
            await transport.close()

    asyncio.run(_run())


def cmd_script_lint(args: Any) -> None:
    """Lint an Apps Script project."""
    from extrascript import ScriptClient

    client = ScriptClient.__new__(ScriptClient)
    result = client.lint(args.folder)
    if result.diagnostics:
        for d in result.diagnostics:
            print(d)
        if result.error_count > 0:
            sys.exit(1)
    else:
        print("No lint issues found.")


# --- Doc commands ---


def cmd_doc_pull(args: Any) -> None:
    """Pull a Google Doc."""
    from extradoc import DocsClient, GoogleDocsTransport

    document_id = _parse_document_id(args.url)
    output_dir = Path(args.output_dir) if args.output_dir else Path()
    access_token = _get_token(args)

    async def _run() -> None:
        transport = GoogleDocsTransport(access_token)
        client = DocsClient(transport)
        try:
            files = await client.pull(
                document_id,
                output_dir,
                save_raw=not args.no_raw,
            )
            print(f"\nPulled {len(files)} files to {output_dir / document_id}/")
        finally:
            await transport.close()

    asyncio.run(_run())


def cmd_doc_diff(args: Any) -> None:
    """Preview changes to a Google Doc."""
    from extradoc import DocsClient

    client = DocsClient.__new__(DocsClient)
    _document_id, requests, _change_tree, comment_ops = client.diff(args.folder)
    has_changes = bool(requests) or comment_ops.has_operations
    if not has_changes:
        print("No changes detected.")
    else:
        if requests:
            print(json.dumps(requests, indent=2))
        if comment_ops.has_operations:
            parts: list[str] = []
            if comment_ops.new_comments:
                parts.append(f"{len(comment_ops.new_comments)} new comment(s)")
            if comment_ops.new_replies:
                parts.append(f"{len(comment_ops.new_replies)} new reply/replies")
            if comment_ops.resolves:
                parts.append(f"{len(comment_ops.resolves)} comment(s) to resolve")
            print("Comment operations: " + ", ".join(parts))


def cmd_doc_push(args: Any) -> None:
    """Push changes to a Google Doc."""
    from extradoc import DocsClient, GoogleDocsTransport

    access_token = _get_token(args)

    async def _run() -> None:
        transport = GoogleDocsTransport(access_token)
        client = DocsClient(transport)
        try:
            result = await client.push(args.folder, force=args.force)
            print(result.message)
            if not result.success:
                sys.exit(1)
        finally:
            await transport.close()

    asyncio.run(_run())


# --- Create commands ---

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

    # Get service account email
    sa_token = manager.get_token()
    sa_email = sa_token.service_account_email

    # Get OAuth token with drive.file scope (only allowed drive scope)
    oauth_token = manager.get_oauth_token(
        scopes=["drive.file"],
        reason=f"Create {file_type} and share with service account",
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


def cmd_sheet_create(args: Any) -> None:
    """Create a new Google Sheet."""
    _cmd_create("sheet", args)


def cmd_slide_create(args: Any) -> None:
    """Create a new Google Slides presentation."""
    _cmd_create("slide", args)


def cmd_doc_create(args: Any) -> None:
    """Create a new Google Doc."""
    _cmd_create("doc", args)


def cmd_form_create(args: Any) -> None:
    """Create a new Google Form."""
    _cmd_create("form", args)


# --- Gmail commands ---


def _parse_email_file_args(
    file_path: Path,
) -> tuple[list[str], str, str, list[str] | None, list[str] | None]:
    """Read and parse an email markdown file. Returns (to, subject, body, cc, bcc)."""
    from extrasuite.client.google_api import parse_email_file

    if not file_path.exists():
        print(f"Error: File not found: {file_path}", file=sys.stderr)
        sys.exit(1)

    content = file_path.read_text()
    metadata, body = parse_email_file(content)

    if "to" not in metadata:
        print("Error: 'to' field is required in front matter.", file=sys.stderr)
        sys.exit(1)
    if "subject" not in metadata:
        print("Error: 'subject' field is required in front matter.", file=sys.stderr)
        sys.exit(1)

    to = [addr.strip() for addr in metadata["to"].split(",")]
    subject = metadata["subject"]
    cc = (
        [addr.strip() for addr in metadata["cc"].split(",")]
        if metadata.get("cc")
        else None
    )
    bcc = (
        [addr.strip() for addr in metadata["bcc"].split(",")]
        if metadata.get("bcc")
        else None
    )
    return to, subject, body, cc, bcc


def cmd_gmail_compose(args: Any) -> None:
    """Save an email draft from a markdown file with front matter."""
    from extrasuite.client.google_api import create_gmail_draft

    to, subject, body, cc, bcc = _parse_email_file_args(Path(args.file))

    access_token = _get_oauth_token(
        args,
        scopes=["gmail.compose"],
        reason="Save email draft",
    )

    result = create_gmail_draft(
        access_token, to=to, subject=subject, body=body, cc=cc, bcc=bcc
    )
    draft_id = result.get("id", "")
    print(f"Draft saved (id: {draft_id})")


def cmd_gmail_edit_draft(args: Any) -> None:
    """Update an existing Gmail draft from a markdown file with front matter."""
    from extrasuite.client.google_api import update_gmail_draft

    to, subject, body, cc, bcc = _parse_email_file_args(Path(args.file))

    access_token = _get_oauth_token(
        args,
        scopes=["gmail.compose"],
        reason="Edit email draft",
    )

    update_gmail_draft(
        access_token,
        draft_id=args.draft_id,
        to=to,
        subject=subject,
        body=body,
        cc=cc,
        bcc=bcc,
    )
    print(f"Draft updated (id: {args.draft_id})")


# --- Contacts commands ---


def cmd_contacts_sync(args: Any) -> None:
    """Sync Google Contacts to local DB."""
    from extrasuite.client.contacts import _CONTACTS_SCOPES, sync

    access_token = _get_oauth_token(
        args,
        scopes=_CONTACTS_SCOPES,
        reason="Sync Google Contacts",
    )
    people_count, other_count = sync(access_token, verbose=True)
    print(f"Synced {people_count} contacts and {other_count} other contacts.")


def cmd_contacts_search(args: Any) -> None:
    """Search local contacts DB."""
    from extrasuite.client.contacts import _DB_PATH, _is_stale, _open_db, search

    queries: list[str] = args.queries
    if not queries:
        print("No search queries provided.", file=sys.stderr)
        sys.exit(1)

    # Check staleness before prompting for auth — avoids browser popup when not needed
    needs_sync = not _DB_PATH.exists()
    if not needs_sync:
        needs_sync = _is_stale(_open_db())

    token = None
    if needs_sync:
        from extrasuite.client.contacts import _CONTACTS_SCOPES

        token = _get_oauth_token(
            args,
            scopes=_CONTACTS_SCOPES,
            reason="Sync Google Contacts",
        )

    results = search(queries, token=token, auto_sync=needs_sync)
    print(json.dumps(results, indent=2))


def cmd_contacts_touch(args: Any) -> None:
    """Record that these email addresses were contacted."""
    from extrasuite.client.contacts import touch

    emails: list[str] = args.emails
    if not emails:
        print("No email addresses provided.", file=sys.stderr)
        sys.exit(1)

    touch(emails)
    print(f"Recorded interaction with {len(emails)} contact(s).")


# --- Calendar commands ---


def cmd_calendar_view(args: Any) -> None:
    """View calendar events for a time range."""
    from extrasuite.client.google_api import (
        format_events_markdown,
        list_calendar_events,
        parse_time_value,
    )

    time_min, time_max = parse_time_value(args.when)
    access_token = _get_oauth_token(
        args,
        scopes=["calendar"],
        reason="View calendar events",
    )

    events = list_calendar_events(
        access_token,
        calendar_id=args.calendar,
        time_min=time_min,
        time_max=time_max,
    )

    print(format_events_markdown(events))


# --- Argument Parser ---


def build_parser() -> Any:
    """Build the argument parser."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="extrasuite",
        description=_load_help(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command")

    # Shared auth flags for commands that need authentication
    auth_parent = argparse.ArgumentParser(add_help=False)
    auth_parent.add_argument(
        "--gateway", metavar="PATH", help="Path to gateway.json with server URLs"
    )
    auth_parent.add_argument(
        "--service-account",
        metavar="PATH",
        help="Path to service account JSON key file",
    )

    # --- sheet ---
    sheet_parser = subparsers.add_parser(
        "sheet",
        help="Google Sheets operations",
        description=_load_help("sheet"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sheet_sub = sheet_parser.add_subparsers(dest="subcommand")

    sp = sheet_sub.add_parser(
        "pull",
        help="Download a spreadsheet",
        parents=[auth_parent],
        description=_load_help("sheet", "pull"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("url", help="Spreadsheet URL or ID")
    sp.add_argument("output_dir", nargs="?", help="Output directory (default: .)")
    sp.add_argument(
        "--max-rows", type=int, default=100, help="Max rows per sheet (default: 100)"
    )
    sp.add_argument("--no-limit", action="store_true", help="Fetch all rows")
    sp.add_argument(
        "--no-raw", action="store_true", help="Don't save raw API responses"
    )

    sp = sheet_sub.add_parser(
        "diff",
        help="Offline debugging tool - show pending changes",
        description=_load_help("sheet", "diff"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("folder", help="Spreadsheet folder path")

    sp = sheet_sub.add_parser(
        "push",
        help="Apply changes",
        parents=[auth_parent],
        description=_load_help("sheet", "push"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("folder", help="Spreadsheet folder path")
    sp.add_argument("-f", "--force", action="store_true", help="Push despite warnings")

    sp = sheet_sub.add_parser(
        "batchUpdate",
        help="Advanced: execute raw batchUpdate requests (sort, move, etc.)",
        parents=[auth_parent],
        description=_load_help("sheet", "batchupdate"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("url", help="Spreadsheet URL or ID")
    sp.add_argument("requests_file", help="JSON file with requests")
    sp.add_argument("-v", "--verbose", action="store_true", help="Print API response")

    sp = sheet_sub.add_parser(
        "create",
        help="Create a new spreadsheet",
        parents=[auth_parent],
        description=_load_help("sheet", "create"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("title", help="Spreadsheet title")

    sp = sheet_sub.add_parser(
        "help",
        help="Show reference documentation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("topic", nargs="?", help="Topic name (omit to list all)")

    # --- slide ---
    slide_parser = subparsers.add_parser(
        "slide",
        help="Google Slides operations",
        description=_load_help("slide"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    slide_sub = slide_parser.add_subparsers(dest="subcommand")

    sp = slide_sub.add_parser(
        "pull",
        help="Download a presentation",
        parents=[auth_parent],
        description=_load_help("slide", "pull"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("url", help="Presentation URL or ID")
    sp.add_argument("output_dir", nargs="?", help="Output directory (default: .)")
    sp.add_argument(
        "--no-raw", action="store_true", help="Don't save raw API responses"
    )

    sp = slide_sub.add_parser(
        "diff",
        help="Offline debugging tool - show pending changes",
        description=_load_help("slide", "diff"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("folder", help="Presentation folder path")

    sp = slide_sub.add_parser(
        "push",
        help="Apply changes",
        parents=[auth_parent],
        description=_load_help("slide", "push"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("folder", help="Presentation folder path")

    sp = slide_sub.add_parser(
        "create",
        help="Create a new presentation",
        parents=[auth_parent],
        description=_load_help("slide", "create"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("title", help="Presentation title")

    sp = slide_sub.add_parser(
        "help",
        help="Show reference documentation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("topic", nargs="?", help="Topic name (omit to list all)")

    # --- form ---
    form_parser = subparsers.add_parser(
        "form",
        help="Google Forms operations",
        description=_load_help("form"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    form_sub = form_parser.add_subparsers(dest="subcommand")

    sp = form_sub.add_parser(
        "pull",
        help="Download a form",
        parents=[auth_parent],
        description=_load_help("form", "pull"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("url", help="Form URL or ID")
    sp.add_argument("output_dir", nargs="?", help="Output directory (default: .)")
    sp.add_argument("--responses", action="store_true", help="Include form responses")
    sp.add_argument(
        "--max-responses", type=int, default=100, help="Max responses to fetch"
    )
    sp.add_argument(
        "--no-raw", action="store_true", help="Don't save raw API responses"
    )

    sp = form_sub.add_parser(
        "diff",
        help="Offline debugging tool - show pending changes",
        description=_load_help("form", "diff"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("folder", help="Form folder path")

    sp = form_sub.add_parser(
        "push",
        help="Apply changes",
        parents=[auth_parent],
        description=_load_help("form", "push"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("folder", help="Form folder path")
    sp.add_argument("-f", "--force", action="store_true", help="Push despite warnings")

    sp = form_sub.add_parser(
        "create",
        help="Create a new form",
        parents=[auth_parent],
        description=_load_help("form", "create"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("title", help="Form title")

    sp = form_sub.add_parser(
        "help",
        help="Show reference documentation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("topic", nargs="?", help="Topic name (omit to list all)")

    # --- script ---
    script_parser = subparsers.add_parser(
        "script",
        help="Google Apps Script operations",
        description=_load_help("script"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    script_sub = script_parser.add_subparsers(dest="subcommand")

    sp = script_sub.add_parser(
        "pull",
        help="Download a script project",
        parents=[auth_parent],
        description=_load_help("script", "pull"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("url", help="Script URL or ID")
    sp.add_argument("output_dir", nargs="?", help="Output directory (default: .)")
    sp.add_argument(
        "--no-raw", action="store_true", help="Don't save raw API responses"
    )

    sp = script_sub.add_parser(
        "diff",
        help="Show which files changed (offline)",
        description=_load_help("script", "diff"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("folder", help="Script project folder path")

    sp = script_sub.add_parser(
        "push",
        help="Apply changes",
        parents=[auth_parent],
        description=_load_help("script", "push"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("folder", help="Script project folder path")
    sp.add_argument("--skip-lint", action="store_true", help="Skip lint before push")

    sp = script_sub.add_parser(
        "create",
        help="Create a new script project",
        parents=[auth_parent],
        description=_load_help("script", "create"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("title", help="Project title")
    sp.add_argument("output_dir", nargs="?", help="Output directory (default: .)")
    sp.add_argument("--bind-to", help="Google Drive file URL or ID to bind to")

    sp = script_sub.add_parser(
        "lint",
        help="Lint script files (offline)",
        description=_load_help("script", "lint"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("folder", help="Script project folder path")

    sp = script_sub.add_parser(
        "help",
        help="Show reference documentation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("topic", nargs="?", help="Topic name (omit to list all)")

    # --- doc ---
    doc_parser = subparsers.add_parser(
        "doc",
        help="Google Docs operations",
        description=_load_help("doc"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    doc_sub = doc_parser.add_subparsers(dest="subcommand")

    sp = doc_sub.add_parser(
        "pull",
        help="Download a document",
        parents=[auth_parent],
        description=_load_help("doc", "pull"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("url", help="Document URL or ID")
    sp.add_argument("output_dir", nargs="?", help="Output directory (default: .)")
    sp.add_argument(
        "--no-raw", action="store_true", help="Don't save raw API responses"
    )

    sp = doc_sub.add_parser(
        "diff",
        help="Offline debugging tool - show pending changes",
        description=_load_help("doc", "diff"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("folder", help="Document folder path")

    sp = doc_sub.add_parser(
        "push",
        help="Apply changes",
        parents=[auth_parent],
        description=_load_help("doc", "push"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("folder", help="Document folder path")
    sp.add_argument("-f", "--force", action="store_true", help="Push despite warnings")
    sp.add_argument("--verify", action="store_true", help="Pull after push to verify")

    sp = doc_sub.add_parser(
        "create",
        help="Create a new document",
        parents=[auth_parent],
        description=_load_help("doc", "create"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("title", help="Document title")

    sp = doc_sub.add_parser(
        "help",
        help="Show reference documentation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("topic", nargs="?", help="Topic name (omit to list all)")

    # --- gmail ---
    gmail_parser = subparsers.add_parser(
        "gmail",
        help="Gmail operations",
        description=_load_help("gmail"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    gmail_sub = gmail_parser.add_subparsers(dest="subcommand")

    sp = gmail_sub.add_parser(
        "compose",
        help="Save an email draft from a markdown file",
        parents=[auth_parent],
        description=_load_help("gmail", "compose"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("file", help="Markdown file with front matter")

    sp = gmail_sub.add_parser(
        "edit-draft",
        help="Update an existing Gmail draft from a markdown file",
        parents=[auth_parent],
        description=_load_help("gmail", "edit-draft"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("draft_id", help="Draft ID to update (from compose output)")
    sp.add_argument("file", help="Markdown file with front matter")

    sp = gmail_sub.add_parser(
        "help",
        help="Show reference documentation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("topic", nargs="?", help="Topic name (omit to list all)")

    # --- calendar ---
    calendar_parser = subparsers.add_parser(
        "calendar",
        help="Google Calendar operations",
        description=_load_help("calendar"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    calendar_sub = calendar_parser.add_subparsers(dest="subcommand")

    sp = calendar_sub.add_parser(
        "view",
        help="View calendar events",
        parents=[auth_parent],
        description=_load_help("calendar", "view"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument(
        "--calendar",
        default="primary",
        help="Calendar ID (default: primary)",
    )
    sp.add_argument(
        "--when",
        default="today",
        help="Time range: today, tomorrow, yesterday, this-week, next-week, or YYYY-MM-DD (default: today)",
    )

    sp = calendar_sub.add_parser(
        "help",
        help="Show reference documentation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("topic", nargs="?", help="Topic name (omit to list all)")

    # --- contacts ---
    contacts_parser = subparsers.add_parser(
        "contacts",
        help="Google Contacts operations (sync, search, touch)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    contacts_sub = contacts_parser.add_subparsers(dest="subcommand")

    contacts_sub.add_parser(
        "sync",
        help="Sync contacts from Google to local DB",
        parents=[auth_parent],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    sp = contacts_sub.add_parser(
        "search",
        help="Search local contacts (auto-syncs if needed)",
        parents=[auth_parent],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument(
        "queries",
        nargs="+",
        metavar="QUERY",
        help='One or more search strings, e.g. "Alice company" "Bob corp"',
    )

    sp = contacts_sub.add_parser(
        "touch",
        help="Record that these email addresses were contacted",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument(
        "emails",
        nargs="+",
        metavar="EMAIL",
        help="Email addresses to mark as contacted",
    )

    return parser


# Command dispatch table
_COMMANDS: dict[tuple[str, str | None], Any] = {
    ("sheet", "pull"): cmd_sheet_pull,
    ("sheet", "diff"): cmd_sheet_diff,
    ("sheet", "push"): cmd_sheet_push,
    ("sheet", "create"): cmd_sheet_create,
    ("sheet", "batchUpdate"): cmd_sheet_batchupdate,
    ("slide", "pull"): cmd_slide_pull,
    ("slide", "diff"): cmd_slide_diff,
    ("slide", "push"): cmd_slide_push,
    ("slide", "create"): cmd_slide_create,
    ("form", "pull"): cmd_form_pull,
    ("form", "diff"): cmd_form_diff,
    ("form", "push"): cmd_form_push,
    ("form", "create"): cmd_form_create,
    ("script", "pull"): cmd_script_pull,
    ("script", "diff"): cmd_script_diff,
    ("script", "push"): cmd_script_push,
    ("script", "create"): cmd_script_create,
    ("script", "lint"): cmd_script_lint,
    ("doc", "pull"): cmd_doc_pull,
    ("doc", "diff"): cmd_doc_diff,
    ("doc", "push"): cmd_doc_push,
    ("doc", "create"): cmd_doc_create,
    ("gmail", "compose"): cmd_gmail_compose,
    ("gmail", "edit-draft"): cmd_gmail_edit_draft,
    ("calendar", "view"): cmd_calendar_view,
    ("contacts", "sync"): cmd_contacts_sync,
    ("contacts", "search"): cmd_contacts_search,
    ("contacts", "touch"): cmd_contacts_touch,
    ("sheet", "help"): cmd_module_help,
    ("slide", "help"): cmd_module_help,
    ("form", "help"): cmd_module_help,
    ("script", "help"): cmd_module_help,
    ("doc", "help"): cmd_module_help,
    ("gmail", "help"): cmd_module_help,
    ("calendar", "help"): cmd_module_help,
}


def main() -> None:
    """Main entry point."""
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    subcommand = getattr(args, "subcommand", None)

    if not subcommand:
        # Print subparser help
        for action in parser._subparsers._actions:
            if isinstance(action, type(parser._subparsers._actions[0])):
                sub = action.choices.get(args.command)
                if sub:
                    sub.print_help()
                    sys.exit(1)
        parser.print_help()
        sys.exit(1)

    handler = _COMMANDS.get((args.command, subcommand))

    if handler is None:
        print(f"Unknown command: {args.command} {subcommand or ''}", file=sys.stderr)
        sys.exit(1)

    try:
        handler(args)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(130)
    except ValueError as e:
        error_msg = str(e)
        print(f"Error: {error_msg}", file=sys.stderr)
        if "No authentication method configured" in error_msg:
            print(
                "\nRun with --help for authentication options.",
                file=sys.stderr,
            )
        sys.exit(1)
    except TimeoutError:
        print("Error: Operation timed out.", file=sys.stderr)
        print(
            "Tip: Use --service-account for headless environments.",
            file=sys.stderr,
        )
        sys.exit(1)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
