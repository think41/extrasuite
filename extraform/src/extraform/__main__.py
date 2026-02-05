"""CLI entry point for ExtraForm."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from typing import NoReturn

from extraform.client import FormsClient
from extraform.exceptions import ExtraFormError
from extraform.transport import GoogleFormsTransport, LocalFileTransport


def main() -> NoReturn:
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        prog="extraform",
        description="Pull, edit, and push Google Forms using local files",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # pull command
    pull_parser = subparsers.add_parser(
        "pull",
        help="Download a Google Form to a local folder",
    )
    pull_parser.add_argument(
        "form_url",
        help="Google Form URL or ID",
    )
    pull_parser.add_argument(
        "output_dir",
        nargs="?",
        default=".",
        help="Output directory (default: current directory)",
    )
    pull_parser.add_argument(
        "--responses",
        action="store_true",
        help="Include form responses",
    )
    pull_parser.add_argument(
        "--max-responses",
        type=int,
        default=100,
        help="Maximum responses to fetch (default: 100)",
    )
    pull_parser.add_argument(
        "--no-raw",
        action="store_true",
        help="Don't save raw API responses",
    )

    # diff command
    diff_parser = subparsers.add_parser(
        "diff",
        help="Show changes as batchUpdate JSON (dry run)",
    )
    diff_parser.add_argument(
        "folder",
        help="Form folder to diff",
    )

    # push command
    push_parser = subparsers.add_parser(
        "push",
        help="Apply changes to Google Form",
    )
    push_parser.add_argument(
        "folder",
        help="Form folder to push",
    )
    push_parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Force push even with warnings",
    )

    args = parser.parse_args()

    try:
        if args.command == "pull":
            asyncio.run(cmd_pull(args))
        elif args.command == "diff":
            cmd_diff(args)
        elif args.command == "push":
            asyncio.run(cmd_push(args))
    except ExtraFormError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nAborted", file=sys.stderr)
        sys.exit(130)

    sys.exit(0)


async def cmd_pull(args: argparse.Namespace) -> None:
    """Execute the pull command."""
    # Parse form ID from URL
    form_id = parse_form_id(args.form_url)

    # Get credentials
    token = get_access_token()

    # Create transport and client
    transport = GoogleFormsTransport(token)

    try:
        client = FormsClient(transport)

        result = await client.pull(
            form_id=form_id,
            output_dir=Path(args.output_dir),
            include_responses=args.responses,
            max_responses=args.max_responses,
            save_raw=not args.no_raw,
        )

        # Print results
        print(f"Pulled form {result.form_id}")
        print("Files written:")
        for path in result.files_written:
            print(f"  {path}")
        if result.responses_count > 0:
            print(f"Responses: {result.responses_count}")

    finally:
        await transport.close()


def cmd_diff(args: argparse.Namespace) -> None:
    """Execute the diff command."""
    folder = Path(args.folder)

    if not folder.exists():
        print(f"Error: Folder not found: {folder}", file=sys.stderr)
        sys.exit(1)

    # Use local transport (no API calls needed for diff)
    transport = LocalFileTransport(folder.parent)
    client = FormsClient(transport)

    diff_result, requests = client.diff(folder)

    if not requests:
        print("No changes detected", file=sys.stderr)
        return

    # Output batchUpdate JSON to stdout
    output = {"requests": requests}
    print(json.dumps(output, indent=2))

    # Summary to stderr
    print(f"\n# {len(requests)} request(s) to apply", file=sys.stderr)
    for req in requests:
        req_type = list(req.keys())[0]
        print(f"#   - {req_type}", file=sys.stderr)


async def cmd_push(args: argparse.Namespace) -> None:
    """Execute the push command."""
    folder = Path(args.folder)

    if not folder.exists():
        print(f"Error: Folder not found: {folder}", file=sys.stderr)
        sys.exit(1)

    # Get credentials
    token = get_access_token()

    # Create transport and client
    transport = GoogleFormsTransport(token)

    try:
        client = FormsClient(transport)

        result = await client.push(folder, force=args.force)

        if result.success:
            if result.changes_applied > 0:
                print(f"Pushed {result.changes_applied} change(s) to form {result.form_id}")
            else:
                print("No changes to push")
        else:
            print(f"Push failed: {result.message}", file=sys.stderr)
            sys.exit(1)

    finally:
        await transport.close()


def parse_form_id(url_or_id: str) -> str:
    """Parse form ID from URL or return as-is if already an ID.

    Supported formats:
    - https://docs.google.com/forms/d/1FAIpQLSd.../edit
    - https://docs.google.com/forms/d/e/1FAIpQLSd.../viewform
    - 1FAIpQLSd... (just the ID)
    """
    # Try to extract from URL
    patterns = [
        # Standard edit URL
        r"docs\.google\.com/forms/d/([a-zA-Z0-9_-]+)",
        # Published form URL (starts with /e/)
        r"docs\.google\.com/forms/d/e/([a-zA-Z0-9_-]+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, url_or_id)
        if match:
            return match.group(1)

    # Assume it's already an ID
    return url_or_id


def get_access_token() -> str:
    """Get access token from extrasuite credentials.

    Returns:
        The access token string.

    Raises:
        ExtraFormError: If authentication fails.
    """
    try:
        # Import extrasuite client for authentication
        from extrasuite.client import authenticate
    except ImportError as e:
        raise ExtraFormError("extrasuite package not installed. Run: pip install extrasuite") from e

    try:
        token = authenticate()
        return token.access_token
    except Exception as e:
        raise ExtraFormError(f"Authentication failed: {e}") from e


if __name__ == "__main__":
    main()
