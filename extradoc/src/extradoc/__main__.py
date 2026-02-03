"""CLI entry point for extradoc.

Usage:
    python -m extradoc pull <document_id_or_url> [output_dir]
    python -m extradoc diff <folder>
    python -m extradoc push <folder>
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

from extrasuite.client import CredentialsManager

from extradoc.client import DocsClient
from extradoc.transport import GoogleDocsTransport, LocalFileTransport


def parse_document_id(id_or_url: str) -> str:
    """Extract document ID from a URL or return as-is if already an ID."""
    # Pattern to match Google Docs URLs
    # https://docs.google.com/document/d/DOCUMENT_ID/edit...
    url_pattern = r"docs\.google\.com/document/d/([a-zA-Z0-9_-]+)"
    match = re.search(url_pattern, id_or_url)
    if match:
        return match.group(1)
    # Assume it's already an ID
    return id_or_url


async def cmd_pull(args: argparse.Namespace) -> int:
    """Pull a document to local files."""
    document_id = parse_document_id(args.document)
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
    transport = GoogleDocsTransport(access_token=token_obj.access_token)
    client = DocsClient(transport)

    print(f"Pulling document: {document_id}")

    try:
        files = await client.pull(
            document_id,
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
    """Show changes between current files and pristine (dry run)."""
    folder = Path(args.folder)

    if not folder.exists():
        print(f"Error: Folder not found: {folder}", file=sys.stderr)
        return 1

    # diff() doesn't need a real transport since it's local-only
    transport = LocalFileTransport(folder.parent)
    client = DocsClient(transport)

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
            f"\n# {len(requests)} request(s) for document {diff_result.document_id}",
            file=sys.stderr,
        )

        # Return error code if blocked
        if not validation.can_push:
            return 1

        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    finally:
        await transport.close()


async def cmd_push(args: argparse.Namespace) -> int:
    """Apply changes to Google Docs."""
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
    transport = GoogleDocsTransport(access_token=token_obj.access_token)
    client = DocsClient(transport)

    try:
        result = await client.push(folder, force=args.force)

        if result.success:
            if result.changes_applied == 0:
                print("No changes to apply.")
            else:
                print(
                    f"Successfully applied {result.changes_applied} changes to document {result.document_id}"
                )
            return 0
        else:
            print(f"Push failed: {result.message}", file=sys.stderr)
            return 1

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    finally:
        await transport.close()


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        prog="extradoc",
        description="Transform Google Docs to LLM-friendly file format",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # pull subcommand
    pull_parser = subparsers.add_parser(
        "pull",
        help="Pull a document to local files",
    )
    pull_parser.add_argument(
        "document",
        help="Document ID or full Google Docs URL",
    )
    pull_parser.add_argument(
        "output",
        nargs="?",
        default=None,
        help="Output directory (defaults to ./<document_id>/)",
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
        help="Path to document folder (containing document.html)",
    )
    diff_parser.set_defaults(func=cmd_diff)

    # push subcommand
    push_parser = subparsers.add_parser(
        "push",
        help="Apply changes to Google Docs",
    )
    push_parser.add_argument(
        "folder",
        help="Path to document folder (containing document.html)",
    )
    push_parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Force push despite warnings (blocks still prevent push)",
    )
    push_parser.set_defaults(func=cmd_push)

    args = parser.parse_args()
    result: int = asyncio.run(args.func(args))
    return result


if __name__ == "__main__":
    sys.exit(main())
