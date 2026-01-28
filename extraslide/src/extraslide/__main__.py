"""CLI entry point for extraslide.

Usage:
    python -m extraslide pull <presentation_id_or_url> [output_dir]
    python -m extraslide diff <folder>
    python -m extraslide push <folder>
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

from extraslide.client import SlidesClient
from extraslide.credentials import CredentialsManager
from extraslide.transport import GoogleSlidesTransport, LocalFileTransport


def parse_presentation_id(id_or_url: str) -> str:
    """Extract presentation ID from a URL or return as-is if already an ID.

    Supports URLs like:
    - https://docs.google.com/presentation/d/PRESENTATION_ID/edit
    - https://docs.google.com/presentation/d/PRESENTATION_ID/edit#slide=id.xxx
    - https://docs.google.com/presentation/d/PRESENTATION_ID/
    """
    url_pattern = r"docs\.google\.com/presentation/d/([a-zA-Z0-9_-]+)"
    match = re.search(url_pattern, id_or_url)
    if match:
        return match.group(1)
    # Assume it's already an ID
    return id_or_url


async def cmd_pull(args: argparse.Namespace) -> int:
    """Pull a presentation to local files."""
    presentation_id = parse_presentation_id(args.presentation)
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
    transport = GoogleSlidesTransport(access_token=token_obj.access_token)
    client = SlidesClient(transport)

    print(f"Pulling presentation: {presentation_id}")

    try:
        files = await client.pull(
            presentation_id,
            output_path,
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
    """Show changes between current SML and pristine copy."""
    folder_path = Path(args.folder)

    if not folder_path.exists():
        print(f"Error: Folder not found: {folder_path}", file=sys.stderr)
        return 1

    # Create a dummy transport - diff doesn't need network access
    # We just need a SlidesClient instance to call diff()
    transport = LocalFileTransport(folder_path.parent)
    client = SlidesClient(transport)

    try:
        requests = client.diff(folder_path)

        if not requests:
            print("No changes detected")
            return 0

        # Output JSON to stdout
        print(json.dumps({"requests": requests}, indent=2))
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


async def cmd_push(args: argparse.Namespace) -> int:
    """Apply changes to Google Slides."""
    folder_path = Path(args.folder)

    if not folder_path.exists():
        print(f"Error: Folder not found: {folder_path}", file=sys.stderr)
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
    transport = GoogleSlidesTransport(access_token=token_obj.access_token)
    client = SlidesClient(transport)

    print(f"Pushing changes from: {folder_path}")

    try:
        response = await client.push(folder_path)

        if response.get("message") == "No changes detected":
            print("No changes to apply")
            return 0

        replies = response.get("replies", [])
        print(f"Successfully applied {len(replies)} changes")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    finally:
        await transport.close()


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        prog="extraslide",
        description="Transform Google Slides to/from SML (Slide Markup Language)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # pull subcommand
    pull_parser = subparsers.add_parser(
        "pull",
        help="Pull a presentation to local files",
    )
    pull_parser.add_argument(
        "presentation",
        help="Presentation ID or full Google Slides URL",
    )
    pull_parser.add_argument(
        "output",
        nargs="?",
        default=None,
        help="Output directory (defaults to ./<presentation_id>/)",
    )
    pull_parser.add_argument(
        "--no-raw",
        action="store_true",
        help="Don't save raw API response to .raw/ folder",
    )
    pull_parser.set_defaults(func=cmd_pull)

    # diff subcommand
    diff_parser = subparsers.add_parser(
        "diff",
        help="Show changes (outputs batchUpdate JSON to stdout)",
    )
    diff_parser.add_argument(
        "folder",
        help="Path to the presentation folder",
    )
    diff_parser.set_defaults(func=cmd_diff)

    # push subcommand
    push_parser = subparsers.add_parser(
        "push",
        help="Apply changes to Google Slides",
    )
    push_parser.add_argument(
        "folder",
        help="Path to the presentation folder",
    )
    push_parser.set_defaults(func=cmd_push)

    args = parser.parse_args()
    result: int = asyncio.run(args.func(args))
    return result


if __name__ == "__main__":
    sys.exit(main())
