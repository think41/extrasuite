#!/usr/bin/env python3
"""Recording mode script for testing mock API against real Google Docs API.

This script executes a pull-edit-push workflow while using a composite transport
that compares the real Google Docs API with the mock API. Any mismatches are
logged for analysis.

Usage:
    python record_scenario.py <doc_url> <instructions> [--output-dir DIR] [--mismatch-dir DIR]

Example:
    python record_scenario.py https://docs.google.com/document/d/abc123/edit \
        "Add a new paragraph with the text 'Hello World'" \
        --output-dir ./scenario_output \
        --mismatch-dir ./mismatch_logs
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import subprocess
import sys
from pathlib import Path

# Add parent directory to path to import extradoc modules
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from extradoc.client import DocsClient
from extradoc.composite_transport import CompositeTransport, MismatchLogger
from extradoc.transport import GoogleDocsTransport

# Add client package to path for CredentialsManager
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "client" / "src"))
from extrasuite.client import CredentialsManager


def extract_document_id(url: str) -> str:
    """Extract document ID from Google Docs URL.

    Args:
        url: Google Docs URL

    Returns:
        Document ID

    Raises:
        ValueError: If URL format is invalid
    """
    match = re.search(r"/document/d/([a-zA-Z0-9-_]+)", url)
    if not match:
        raise ValueError(f"Invalid Google Docs URL: {url}")
    return match.group(1)


def get_access_token() -> str:
    """Get access token from extrasuite CredentialsManager.

    Uses the standard CredentialsManager which supports gateway.json,
    service account files, and environment variables.

    Returns:
        Access token

    Raises:
        RuntimeError: If unable to get token
    """
    try:
        manager = CredentialsManager()
        token = manager.get_token()
        return token.access_token
    except Exception as e:
        raise RuntimeError(f"Failed to get access token: {e}") from e


def edit_xml_with_claude(folder: Path, instructions: str) -> None:
    """Use Claude Code print mode to edit XMLs per instructions.

    Args:
        folder: Folder containing document.xml and styles.xml
        instructions: Edit instructions for Claude

    Raises:
        RuntimeError: If Claude Code execution fails
    """
    document_xml = folder / "document.xml"
    if not document_xml.exists():
        raise RuntimeError(f"document.xml not found in {folder}")

    print(f"\n🤖 Invoking Claude Code to edit {document_xml}...")
    print(f"   Instructions: {instructions}")

    # Construct the prompt for Claude Code
    prompt = f"""Edit the document.xml file according to these instructions:
{instructions}

IMPORTANT: Only modify the document.xml file. Do not modify styles.xml.
Make minimal changes - only what's necessary to fulfill the instructions.
"""

    try:
        # Run Claude Code in print mode (-p)
        # Unset CLAUDECODE env var to avoid nested session check
        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
        result = subprocess.run(
            [
                "claude",
                "-p",
                "--dangerously-skip-permissions",
                prompt,
            ],
            cwd=folder,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
            env=env,
        )

        if result.returncode != 0:
            print(f"⚠️  Claude Code exited with code {result.returncode}")
            print(f"STDOUT:\n{result.stdout}")
            print(f"STDERR:\n{result.stderr}")
            raise RuntimeError(f"Claude Code failed: {result.stderr}")

        print("✅ Claude Code completed successfully")
        print(f"   Output:\n{result.stdout}")

    except subprocess.TimeoutExpired as e:
        raise RuntimeError("Claude Code execution timed out after 5 minutes") from e
    except FileNotFoundError as e:
        raise RuntimeError(
            "claude command not found. Please install Claude Code CLI."
        ) from e


async def run_scenario(
    doc_url: str,
    instructions: str,
    output_dir: Path,
    mismatch_dir: Path,
) -> None:
    """Run a complete pull-edit-push scenario with recording.

    Args:
        doc_url: Google Docs URL
        instructions: Edit instructions
        output_dir: Directory for pulled documents
        mismatch_dir: Directory for mismatch logs
    """
    print("=" * 80)
    print("RECORDING MODE: Pull-Edit-Push Scenario")
    print("=" * 80)

    # Extract document ID
    document_id = extract_document_id(doc_url)
    print(f"\n📄 Document ID: {document_id}")
    print(f"🔗 URL: {doc_url}")

    # Get access token
    print("\n🔑 Getting access token...")
    access_token = get_access_token()
    print("✅ Access token obtained")

    # Set up transports
    print("\n🚀 Setting up composite transport...")
    real_transport = GoogleDocsTransport(access_token)
    mismatch_logger = MismatchLogger(mismatch_dir)
    composite_transport = CompositeTransport(real_transport, mismatch_logger)
    client = DocsClient(composite_transport)

    try:
        # PULL
        print("\n📥 PULLING document...")
        output_dir.mkdir(parents=True, exist_ok=True)
        written_files = await client.pull(document_id, output_dir, save_raw=True)
        print(f"✅ Pulled {len(written_files)} files:")
        for file in written_files:
            print(f"   - {file}")

        doc_folder = output_dir / document_id

        # EDIT
        print("\n✏️  EDITING document with Claude Code...")
        edit_xml_with_claude(doc_folder, instructions)
        print("✅ Edits applied")

        # PUSH
        print("\n📤 PUSHING changes...")
        print("   (This will call both real and mock APIs and compare)")
        push_result = await client.push(doc_folder)

        if push_result.success:
            print("✅ Push successful!")
            print(f"   Changes applied: {push_result.changes_applied}")
            if push_result.replies_created:
                print(f"   Replies created: {push_result.replies_created}")
            if push_result.comments_resolved:
                print(f"   Comments resolved: {push_result.comments_resolved}")
        else:
            print(f"❌ Push failed: {push_result.message}")

        # SUMMARY
        print("\n" + "=" * 80)
        print("RECORDING SUMMARY")
        print("=" * 80)
        print(mismatch_logger.get_summary())

        if mismatch_logger.mismatch_count > 0:
            print(f"\n⚠️  Review mismatches in: {mismatch_dir}")
            sys.exit(1)
        else:
            print("\n✅ All tests passed - mock matches real API!")
            sys.exit(0)

    finally:
        await composite_transport.close()


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Record a pull-edit-push scenario to test mock API"
    )
    parser.add_argument(
        "doc_url",
        help="Google Docs URL (e.g., https://docs.google.com/document/d/abc123/edit)",
    )
    parser.add_argument(
        "instructions",
        help="Edit instructions for Claude Code (e.g., 'Add a paragraph with text Hello')",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("scenario_output"),
        help="Directory for pulled documents (default: scenario_output)",
    )
    parser.add_argument(
        "--mismatch-dir",
        type=Path,
        default=Path("mismatch_logs"),
        help="Directory for mismatch logs (default: mismatch_logs)",
    )

    args = parser.parse_args()

    try:
        asyncio.run(
            run_scenario(
                args.doc_url,
                args.instructions,
                args.output_dir,
                args.mismatch_dir,
            )
        )
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
