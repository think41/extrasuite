"""CLI entry point for extrasheet.

Usage:
    python -m extrasheet pull <spreadsheet_id_or_url> [output_dir]
    python -m extrasheet diff <folder>
    python -m extrasheet push <folder>
    python -m extrasheet batchUpdate <spreadsheet_id_or_url> <requests.json>
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

from extrasuite.client import CredentialsManager

from extrasheet.client import SheetsClient
from extrasheet.exceptions import DiffError
from extrasheet.transport import GoogleSheetsTransport, LocalFileTransport


def parse_spreadsheet_id(id_or_url: str) -> str:
    """Extract spreadsheet ID from a URL or return as-is if already an ID."""
    # Pattern to match Google Sheets URLs
    # https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit...
    url_pattern = r"docs\.google\.com/spreadsheets/d/([a-zA-Z0-9_-]+)"
    match = re.search(url_pattern, id_or_url)
    if match:
        return match.group(1)
    # Assume it's already an ID
    return id_or_url


async def cmd_pull(args: argparse.Namespace) -> int:
    """Pull a spreadsheet to local files."""
    spreadsheet_id = parse_spreadsheet_id(args.spreadsheet)
    output_path = Path(args.output) if args.output else Path()

    # Get token via CredentialsManager
    print("Authenticating...")
    try:
        manager = CredentialsManager()
        token_obj = manager.get_token()
    except Exception as e:
        print(f"Authentication failed: {e}", file=sys.stderr)
        return 1

    # Create transport and client
    transport = GoogleSheetsTransport(access_token=token_obj.access_token)
    client = SheetsClient(transport)

    # Determine max_rows
    max_rows = args.max_rows
    if args.no_limit:
        max_rows = 1_000_000  # Effectively unlimited

    print(f"Pulling spreadsheet: {spreadsheet_id} (max {max_rows} rows per sheet)")

    try:
        files = await client.pull(
            spreadsheet_id,
            output_path,
            max_rows=max_rows,
            save_raw=not args.no_raw,
        )
        print(f"\nWrote {len(files)} files to {output_path}:")
        for path in files:
            print(f"  {path}")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    finally:
        await transport.close()


async def cmd_diff(args: argparse.Namespace) -> int:
    """Show changes between current files and pristine (dry run)."""
    folder = Path(args.folder)

    if not folder.exists():
        print(f"Error: Folder not found: {folder}", file=sys.stderr)
        return 1

    # diff() doesn't need a real transport since it's local-only
    transport = LocalFileTransport(folder.parent)
    client = SheetsClient(transport)

    try:
        diff_result, requests, validation = client.diff(folder)

        # Show validation results
        if validation.blocks:
            print("# BLOCKED - cannot push due to errors:", file=sys.stderr)
            for block in validation.blocks:
                print(f"#   ERROR: {block}", file=sys.stderr)
            print(file=sys.stderr)

        if validation.warnings:
            print("# WARNINGS (use --force to push anyway):", file=sys.stderr)
            for warning in validation.warnings:
                print(f"#   WARNING: {warning}", file=sys.stderr)
            print(file=sys.stderr)

        if not requests:
            print("No changes detected.")
            return 0

        # Output batchUpdate JSON to stdout
        output = {"requests": requests}
        print(json.dumps(output, indent=2))

        # Print summary to stderr so it doesn't interfere with JSON
        print(
            f"\n# {len(requests)} request(s) for spreadsheet {diff_result.spreadsheet_id}",
            file=sys.stderr,
        )

        # Return error code if blocked
        if not validation.can_push:
            return 1

        return 0

    except DiffError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    finally:
        await transport.close()


async def cmd_push(args: argparse.Namespace) -> int:
    """Apply changes to Google Sheets."""
    folder = Path(args.folder)

    if not folder.exists():
        print(f"Error: Folder not found: {folder}", file=sys.stderr)
        return 1

    # Get token via CredentialsManager
    print("Authenticating...")
    try:
        manager = CredentialsManager()
        token_obj = manager.get_token()
    except Exception as e:
        print(f"Authentication failed: {e}", file=sys.stderr)
        return 1

    # Create transport and client
    transport = GoogleSheetsTransport(access_token=token_obj.access_token)
    client = SheetsClient(transport)

    try:
        result = await client.push(folder, force=args.force)

        if result.success:
            if result.changes_applied == 0:
                print("No changes to apply.")
            else:
                print(
                    f"Successfully applied {result.changes_applied} changes to spreadsheet {result.spreadsheet_id}"
                )
            return 0
        else:
            print(f"Push failed: {result.message}", file=sys.stderr)
            return 1

    except DiffError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    finally:
        await transport.close()


async def cmd_batch_update(args: argparse.Namespace) -> int:
    """Execute batchUpdate requests directly against Google Sheets API."""
    spreadsheet_id = parse_spreadsheet_id(args.spreadsheet)
    requests_file = Path(args.requests_file)

    if not requests_file.exists():
        print(f"Error: Requests file not found: {requests_file}", file=sys.stderr)
        return 1

    # Load requests from JSON file
    try:
        with requests_file.open() as f:
            payload = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {requests_file}: {e}", file=sys.stderr)
        return 1

    requests = payload.get("requests", [])
    if not requests:
        print("No requests to execute.")
        return 0

    # Get token via CredentialsManager
    print("Authenticating...")
    try:
        manager = CredentialsManager()
        token_obj = manager.get_token()
    except Exception as e:
        print(f"Authentication failed: {e}", file=sys.stderr)
        return 1

    # Create transport
    transport = GoogleSheetsTransport(access_token=token_obj.access_token)

    try:
        print(f"Executing {len(requests)} requests on spreadsheet {spreadsheet_id}...")
        response = await transport.batch_update(spreadsheet_id, requests)

        print(f"Successfully executed {len(requests)} requests.")
        print("\nNote: Local files are now stale. Run 'extrasheet pull' to refresh.")

        if args.verbose:
            print("\nResponse:")
            print(json.dumps(response, indent=2))

        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    finally:
        await transport.close()


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        prog="extrasheet",
        description="Transform Google Sheets to LLM-friendly file format",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # pull subcommand
    pull_parser = subparsers.add_parser(
        "pull",
        help="Pull a spreadsheet to local files",
    )
    pull_parser.add_argument(
        "spreadsheet",
        help="Spreadsheet ID or full Google Sheets URL",
    )
    pull_parser.add_argument(
        "output",
        nargs="?",
        default=None,
        help="Output directory (defaults to ./<spreadsheet_id>/)",
    )
    pull_parser.add_argument(
        "--max-rows",
        type=int,
        default=100,
        help="Maximum number of rows to fetch per sheet (default: 100)",
    )
    pull_parser.add_argument(
        "--no-limit",
        action="store_true",
        help="Fetch all rows (may timeout on large spreadsheets)",
    )
    pull_parser.add_argument(
        "--no-raw",
        action="store_true",
        help="Don't save raw API responses to .raw/ folder",
    )
    pull_parser.set_defaults(func=cmd_pull)

    # diff subcommand
    diff_parser = subparsers.add_parser(
        "diff",
        help="Show changes between current files and pristine (dry run)",
    )
    diff_parser.add_argument(
        "folder",
        help="Path to spreadsheet folder (containing spreadsheet.json)",
    )
    diff_parser.set_defaults(func=cmd_diff)

    # push subcommand
    push_parser = subparsers.add_parser(
        "push",
        help="Apply changes to Google Sheets",
    )
    push_parser.add_argument(
        "folder",
        help="Path to spreadsheet folder (containing spreadsheet.json)",
    )
    push_parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Force push despite warnings (blocks still prevent push)",
    )
    push_parser.set_defaults(func=cmd_push)

    # batchUpdate subcommand
    batch_update_parser = subparsers.add_parser(
        "batchUpdate",
        help="Execute batchUpdate requests directly against Google Sheets API",
    )
    batch_update_parser.add_argument(
        "spreadsheet",
        help="Spreadsheet ID or full Google Sheets URL",
    )
    batch_update_parser.add_argument(
        "requests_file",
        help="Path to JSON file containing batchUpdate requests",
    )
    batch_update_parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print API response",
    )
    batch_update_parser.set_defaults(func=cmd_batch_update)

    args = parser.parse_args()
    result: int = asyncio.run(args.func(args))
    return result


if __name__ == "__main__":
    sys.exit(main())
