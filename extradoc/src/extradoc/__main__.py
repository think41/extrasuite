"""CLI entry point for extradoc.

Usage:
    python -m extradoc pull <document_id_or_url> [output_dir]
    python -m extradoc diff <folder>
    python -m extradoc push <folder>
    python -m extradoc test <folder>
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import zipfile
from pathlib import Path

from extrasuite.client import CredentialsManager

from extradoc.__main__test import run_test_workflow
from extradoc.transport import GoogleDocsTransport
from extradoc.v2.push import PushClient
from extradoc.xml_converter import convert_document_to_xml

# File and directory names
DOCUMENT_XML = "document.xml"
STYLES_XML = "styles.xml"
RAW_DIR = ".raw"
PRISTINE_DIR = ".pristine"
PRISTINE_ZIP = "document.zip"


def parse_document_id(id_or_url: str) -> str:
    """Extract document ID from a URL or return as-is if already an ID."""
    url_pattern = r"docs\.google\.com/document/d/([a-zA-Z0-9_-]+)"
    match = re.search(url_pattern, id_or_url)
    if match:
        return match.group(1)
    return id_or_url


def _create_pristine_copy(
    document_dir: Path,
    written_files: list[Path],
) -> Path:
    """Create a pristine copy of the pulled files for diff/push workflow."""
    pristine_dir = document_dir / PRISTINE_DIR
    pristine_dir.mkdir(parents=True, exist_ok=True)

    zip_path = pristine_dir / PRISTINE_ZIP

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in written_files:
            if any(d in file_path.parts for d in [RAW_DIR, PRISTINE_DIR]):
                continue
            arcname = file_path.relative_to(document_dir)
            zf.write(file_path, arcname)

    return zip_path


async def cmd_pull(args: argparse.Namespace) -> int:
    """Pull a document to local files."""
    document_id = parse_document_id(args.document)
    output_path = Path(args.output) if args.output else Path()

    print("Authenticating...")
    try:
        manager = CredentialsManager()
        token_obj = manager.get_token()
    except Exception as e:
        print(f"Authentication failed: {e}", file=sys.stderr)
        return 1

    transport = GoogleDocsTransport(access_token=token_obj.access_token)

    print(f"Pulling document: {document_id}")

    try:
        document_data = await transport.get_document(document_id)

        document_dir = output_path / document_id
        document_dir.mkdir(parents=True, exist_ok=True)

        written_files: list[Path] = []

        document_xml, styles_xml = convert_document_to_xml(document_data.raw)

        xml_path = document_dir / DOCUMENT_XML
        xml_path.write_text(document_xml, encoding="utf-8")
        written_files.append(xml_path)

        styles_path = document_dir / STYLES_XML
        styles_path.write_text(styles_xml, encoding="utf-8")
        written_files.append(styles_path)

        if not args.no_raw:
            raw_dir = document_dir / RAW_DIR
            raw_dir.mkdir(parents=True, exist_ok=True)
            raw_path = raw_dir / "document.json"
            raw_path.write_text(
                json.dumps(document_data.raw, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            written_files.append(raw_path)

        pristine_path = _create_pristine_copy(document_dir, written_files)
        written_files.append(pristine_path)

        print(f"\nWrote {len(written_files)} files to {output_path}:")
        for path in written_files:
            print(f"  {path}")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    finally:
        await transport.close()


async def cmd_diff(args: argparse.Namespace) -> int:
    """Show changes using v2 diff engine (dry run)."""
    folder = Path(args.folder)

    if not folder.exists():
        print(f"Error: Folder not found: {folder}", file=sys.stderr)
        return 1

    try:
        push_client = PushClient()
        document_id, requests, _ = push_client.diff(folder)

        if not requests:
            print("No changes detected.")
            return 0

        output = {"requests": requests}
        print(json.dumps(output, indent=2))
        print(
            f"\n# {len(requests)} request(s) for document {document_id}",
            file=sys.stderr,
        )
        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


async def cmd_push(args: argparse.Namespace) -> int:
    """Apply changes to Google Docs using v2 push engine."""
    folder = Path(args.folder)

    if not folder.exists():
        print(f"Error: Folder not found: {folder}", file=sys.stderr)
        return 1

    print("Authenticating...")
    try:
        manager = CredentialsManager()
        token_obj = manager.get_token()
    except Exception as e:
        print(f"Authentication failed: {e}", file=sys.stderr)
        return 1

    transport = GoogleDocsTransport(access_token=token_obj.access_token)

    try:
        push_client = PushClient()
        result = await push_client.push(folder, transport, force=args.force)

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
    # Fast path to avoid subparser clashes when invoking `python -m extradoc test <folder>`
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        if len(sys.argv) < 3:
            print("Usage: python -m extradoc test <folder>", file=sys.stderr)
            return 1
        return run_test_workflow(Path(sys.argv[2]))

    parser = argparse.ArgumentParser(
        prog="extradoc",
        description="Transform Google Docs to LLM-friendly XML format",
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
        help="Path to document folder (containing document.xml)",
    )
    diff_parser.set_defaults(func=cmd_diff)

    # push subcommand
    push_parser = subparsers.add_parser(
        "push",
        help="Apply changes to Google Docs",
    )
    push_parser.add_argument(
        "folder",
        help="Path to document folder (containing document.xml)",
    )
    push_parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Force push despite warnings (blocks still prevent push)",
    )
    push_parser.set_defaults(func=cmd_push)

    # Note: test command handled via fast path above to avoid duplicate subparser registration

    args = parser.parse_args()
    result: int = asyncio.run(args.func(args))
    return result


if __name__ == "__main__":
    sys.exit(main())
