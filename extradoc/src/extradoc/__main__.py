"""CLI entry point for extradoc.

Usage:
    python -m extradoc pull <document_id_or_url> [output_dir]
    python -m extradoc diff <folder>
    python -m extradoc push <folder> [--verify]
"""

from __future__ import annotations

import argparse
import asyncio
import difflib
import json
import re
import sys
import zipfile
from pathlib import Path

from extrasuite.client import CredentialsManager

from extradoc.push import PushClient
from extradoc.transport import GoogleDocsTransport
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
    """Show changes as batchUpdate JSON (dry run)."""
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
    """Apply changes to Google Docs."""
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
        else:
            print(f"Push failed: {result.message}", file=sys.stderr)
            return 1

        if args.verify and result.changes_applied > 0:
            return await _verify_push(folder, result.document_id, transport)

        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    finally:
        await transport.close()


_REVISION_RE = re.compile(r'\srevision="[^"]*"')


def _strip_revision(text: str) -> list[str]:
    """Strip revision attributes and normalize lines for comparison."""
    text = _REVISION_RE.sub("", text)
    return [ln.rstrip() for ln in text.splitlines()]


async def _verify_push(
    folder: Path, document_id: str, transport: GoogleDocsTransport
) -> int:
    """Re-pull the document and compare against the edited XML."""
    print("\nVerifying push...")
    after_dir = folder.parent / f"{folder.name}-verify"

    try:
        document_data = await transport.get_document(document_id)
        after_dir.mkdir(parents=True, exist_ok=True)
        document_xml, _ = convert_document_to_xml(document_data.raw)
        actual_path = after_dir / DOCUMENT_XML
        actual_path.write_text(document_xml, encoding="utf-8")
    except Exception as e:
        print(f"Verify failed (re-pull error): {e}", file=sys.stderr)
        return 1

    expected = (folder / DOCUMENT_XML).read_text(encoding="utf-8")
    actual = actual_path.read_text(encoding="utf-8")

    exp_lines = _strip_revision(expected)
    act_lines = _strip_revision(actual)

    if exp_lines == act_lines:
        print("Verify OK: repull matches edited document (ignoring revision).")
        return 0

    diff = "\n".join(
        difflib.unified_diff(
            exp_lines,
            act_lines,
            fromfile="edited",
            tofile="repulled",
            lineterm="",
        )
    )
    print("Verify MISMATCH: repull differs from edited version.", file=sys.stderr)
    print(diff, file=sys.stderr)
    return 1


def main() -> int:
    """Main entry point."""
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
    push_parser.add_argument(
        "--verify",
        action="store_true",
        help="After push, re-pull and compare to verify correctness",
    )
    push_parser.set_defaults(func=cmd_push)

    args = parser.parse_args()
    result: int = asyncio.run(args.func(args))
    return result


if __name__ == "__main__":
    sys.exit(main())
