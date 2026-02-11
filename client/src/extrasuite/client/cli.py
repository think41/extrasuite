"""Unified CLI for ExtraSuite.

Usage:
    extrasuite sheet pull|diff|push|batchUpdate
    extrasuite slide pull|diff|push
    extrasuite form  pull|diff|push
    extrasuite script pull|diff|push|create|lint
    extrasuite doc   pull|diff|push
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any


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


# --- Epilog text ---

_TOP_EPILOG = """\
Workflow:
  1. extrasuite <type> pull <url>    Download to local folder
  2. Edit files locally
  3. extrasuite <type> diff <folder> Preview changes (dry run)
  4. extrasuite <type> push <folder> Apply changes to Google

Authentication:
  On first use, opens browser for Google login. Cached in ~/.config/extrasuite/.
  Use --gateway or --service-account to provide credentials explicitly.

Examples:
  extrasuite sheet pull https://docs.google.com/spreadsheets/d/abc123
  extrasuite doc push ./1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms
"""

_SHEET_PULL_EPILOG = """\
Folder layout after pull:
  <spreadsheet_id>/
    spreadsheet.json        Start here - title, sheets list, data previews
    <sheet_name>/
      data.tsv              Tab-separated cell values
      formula.json          Cell formulas (only if formulas exist)
      format.json           Cell formatting (only if non-default)
    .pristine/              Original state (do not edit)
"""

_SLIDE_PULL_EPILOG = """\
Folder layout after pull:
  <presentation_id>/
    presentation.json       Start here - title, slide list, dimensions
    styles.json             Theme colors and font styles
    id_mapping.json         Object ID mapping
    slides/
      01/content.sml        Slide content in SML (Slide Markup Language)
      02/content.sml
    .pristine/              Original state (do not edit)
"""

_FORM_PULL_EPILOG = """\
Folder layout after pull:
  <form_id>/
    form.json               The one file to edit - questions, sections, settings
    .pristine/              Original state (do not edit)
"""

_SCRIPT_PULL_EPILOG = """\
Folder layout after pull:
  <script_id>/
    project.json            Project metadata and settings
    Code.js                 Source files (*.js for scripts, *.html for HTML)
    Utilities.js
    .pristine/              Original state (do not edit)
"""

_DOC_PULL_EPILOG = """\
Folder layout after pull:
  <document_id>/
    document.xml            Semantic markup (h1, p, li, table) - edit this
    styles.xml              Named and paragraph styles
    comments.xml            Document comments and replies (if any)
    .pristine/              Original state (do not edit)
"""

_PUSH_EPILOG = """\
Compares current files against .pristine/ to generate changes.
After a successful push, re-pull to get the updated .pristine/ state.
"""

_DIFF_EPILOG = """\
Runs locally - no authentication needed, no API calls.
Compares current files against .pristine/ and outputs batchUpdate JSON to stdout.
Equivalent to push --dry-run.
"""


# --- Argument Parser ---


def build_parser() -> Any:
    """Build the argument parser."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="extrasuite",
        description="ExtraSuite - Edit Google Workspace files with AI agents",
        epilog=_TOP_EPILOG,
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
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sheet_sub = sheet_parser.add_subparsers(dest="subcommand")

    sp = sheet_sub.add_parser(
        "pull",
        help="Download a spreadsheet",
        parents=[auth_parent],
        epilog=_SHEET_PULL_EPILOG,
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
        help="Preview changes",
        epilog=_DIFF_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("folder", help="Spreadsheet folder path")

    sp = sheet_sub.add_parser(
        "push",
        help="Apply changes",
        parents=[auth_parent],
        epilog=_PUSH_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("folder", help="Spreadsheet folder path")
    sp.add_argument("-f", "--force", action="store_true", help="Push despite warnings")

    sp = sheet_sub.add_parser(
        "batchUpdate",
        help="Execute raw batchUpdate requests",
        parents=[auth_parent],
    )
    sp.add_argument("url", help="Spreadsheet URL or ID")
    sp.add_argument("requests_file", help="JSON file with requests")
    sp.add_argument("-v", "--verbose", action="store_true", help="Print API response")

    # --- slide ---
    slide_parser = subparsers.add_parser(
        "slide",
        help="Google Slides operations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    slide_sub = slide_parser.add_subparsers(dest="subcommand")

    sp = slide_sub.add_parser(
        "pull",
        help="Download a presentation",
        parents=[auth_parent],
        epilog=_SLIDE_PULL_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("url", help="Presentation URL or ID")
    sp.add_argument("output_dir", nargs="?", help="Output directory (default: .)")
    sp.add_argument(
        "--no-raw", action="store_true", help="Don't save raw API responses"
    )

    sp = slide_sub.add_parser(
        "diff",
        help="Preview changes",
        epilog=_DIFF_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("folder", help="Presentation folder path")

    sp = slide_sub.add_parser(
        "push",
        help="Apply changes",
        parents=[auth_parent],
        epilog=_PUSH_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("folder", help="Presentation folder path")

    # --- form ---
    form_parser = subparsers.add_parser(
        "form",
        help="Google Forms operations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    form_sub = form_parser.add_subparsers(dest="subcommand")

    sp = form_sub.add_parser(
        "pull",
        help="Download a form",
        parents=[auth_parent],
        epilog=_FORM_PULL_EPILOG,
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
        help="Preview changes",
        epilog=_DIFF_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("folder", help="Form folder path")

    sp = form_sub.add_parser(
        "push",
        help="Apply changes",
        parents=[auth_parent],
        epilog=_PUSH_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("folder", help="Form folder path")
    sp.add_argument("-f", "--force", action="store_true", help="Push despite warnings")

    # --- script ---
    script_parser = subparsers.add_parser(
        "script",
        help="Google Apps Script operations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    script_sub = script_parser.add_subparsers(dest="subcommand")

    sp = script_sub.add_parser(
        "pull",
        help="Download a script project",
        parents=[auth_parent],
        epilog=_SCRIPT_PULL_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("url", help="Script URL or ID")
    sp.add_argument("output_dir", nargs="?", help="Output directory (default: .)")
    sp.add_argument(
        "--no-raw", action="store_true", help="Don't save raw API responses"
    )

    sp = script_sub.add_parser(
        "diff",
        help="Preview changes",
        epilog=_DIFF_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("folder", help="Script project folder path")

    sp = script_sub.add_parser(
        "push",
        help="Apply changes",
        parents=[auth_parent],
        epilog=_PUSH_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("folder", help="Script project folder path")
    sp.add_argument("--skip-lint", action="store_true", help="Skip lint before push")

    sp = script_sub.add_parser(
        "create",
        help="Create a new script project",
        parents=[auth_parent],
    )
    sp.add_argument("title", help="Project title")
    sp.add_argument("output_dir", nargs="?", help="Output directory (default: .)")
    sp.add_argument("--bind-to", help="Google Drive file URL or ID to bind to")

    sp = script_sub.add_parser("lint", help="Lint script files")
    sp.add_argument("folder", help="Script project folder path")

    # --- doc ---
    doc_parser = subparsers.add_parser(
        "doc",
        help="Google Docs operations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    doc_sub = doc_parser.add_subparsers(dest="subcommand")

    sp = doc_sub.add_parser(
        "pull",
        help="Download a document",
        parents=[auth_parent],
        epilog=_DOC_PULL_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("url", help="Document URL or ID")
    sp.add_argument("output_dir", nargs="?", help="Output directory (default: .)")
    sp.add_argument(
        "--no-raw", action="store_true", help="Don't save raw API responses"
    )

    sp = doc_sub.add_parser(
        "diff",
        help="Preview changes",
        epilog=_DIFF_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("folder", help="Document folder path")

    sp = doc_sub.add_parser(
        "push",
        help="Apply changes",
        parents=[auth_parent],
        epilog=_PUSH_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sp.add_argument("folder", help="Document folder path")
    sp.add_argument("-f", "--force", action="store_true", help="Push despite warnings")
    sp.add_argument("--verify", action="store_true", help="Pull after push to verify")

    return parser


# Command dispatch table
_COMMANDS: dict[tuple[str, str | None], Any] = {
    ("sheet", "pull"): cmd_sheet_pull,
    ("sheet", "diff"): cmd_sheet_diff,
    ("sheet", "push"): cmd_sheet_push,
    ("sheet", "batchUpdate"): cmd_sheet_batchupdate,
    ("slide", "pull"): cmd_slide_pull,
    ("slide", "diff"): cmd_slide_diff,
    ("slide", "push"): cmd_slide_push,
    ("form", "pull"): cmd_form_pull,
    ("form", "diff"): cmd_form_diff,
    ("form", "push"): cmd_form_push,
    ("script", "pull"): cmd_script_pull,
    ("script", "diff"): cmd_script_diff,
    ("script", "push"): cmd_script_push,
    ("script", "create"): cmd_script_create,
    ("script", "lint"): cmd_script_lint,
    ("doc", "pull"): cmd_doc_pull,
    ("doc", "diff"): cmd_doc_diff,
    ("doc", "push"): cmd_doc_push,
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
