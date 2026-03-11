"""Doc CLI commands: pull, diff, push, create."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from extrasuite.client.cli._common import (
    _cmd_create,
    _cmd_share,
    _get_credential,
    _get_reason,
    _parse_document_id,
)


def cmd_doc_pull(args: Any) -> None:
    """Pull a Google Doc."""
    from extradoc import DocsClient, GoogleDocsTransport

    document_id = _parse_document_id(args.url)
    output_dir = Path(args.output_dir) if args.output_dir else Path()
    reason = _get_reason(args, default="Pulling Google Doc")
    cred = _get_credential(
        args,
        command={"type": "doc.pull", "file_url": args.url, "file_name": ""},
        reason=reason,
    )

    async def _run() -> None:
        transport = GoogleDocsTransport(cred.token)
        client = DocsClient(transport)
        try:
            await client.pull(
                document_id,
                output_dir,
                save_raw=not args.no_raw,
            )
            print(f"Pulled document to {output_dir / document_id}/")
        finally:
            await transport.close()

    asyncio.run(_run())


def cmd_doc_diff(args: Any) -> None:
    """Preview changes to a Google Doc."""
    from extradoc import DocsClient

    client = DocsClient.__new__(DocsClient)
    result = client.diff(args.folder)
    has_changes = bool(result.batches) or result.comment_ops.has_operations
    if not has_changes:
        print("No changes detected.")
    else:
        if result.batches:
            batches_json = [
                b.model_dump(exclude_none=True, by_alias=True) for b in result.batches
            ]
            print(json.dumps(batches_json, indent=2))
        if result.comment_ops.has_operations:
            parts: list[str] = []
            if result.comment_ops.new_comments:
                parts.append(f"{len(result.comment_ops.new_comments)} new comment(s)")
            if result.comment_ops.new_replies:
                parts.append(f"{len(result.comment_ops.new_replies)} new reply/replies")
            if result.comment_ops.resolves:
                parts.append(
                    f"{len(result.comment_ops.resolves)} comment(s) to resolve"
                )
            print("Comment operations: " + ", ".join(parts))


def cmd_doc_push(args: Any) -> None:
    """Push changes to a Google Doc."""
    from extradoc import DocsClient, GoogleDocsTransport

    reason = _get_reason(args, default="Pushing changes to Google Doc")
    cred = _get_credential(
        args,
        command={"type": "doc.push", "file_url": "", "file_name": ""},
        reason=reason,
    )

    async def _run() -> None:
        transport = GoogleDocsTransport(cred.token)
        client = DocsClient(transport)
        try:
            result = await client.push(args.folder, force=args.force)
            print(result.message)
            if not result.success:
                sys.exit(1)
        finally:
            await transport.close()

    asyncio.run(_run())


def cmd_doc_pull_md(args: Any) -> None:
    """Pull a Google Doc in markdown format."""
    from extradoc import DocsClient, GoogleDocsTransport

    document_id = _parse_document_id(args.url)
    output_dir = Path(args.output_dir) if args.output_dir else Path()
    reason = _get_reason(args, default="Pulling Google Doc as markdown")
    cred = _get_credential(
        args,
        command={"type": "doc.pull", "file_url": args.url, "file_name": ""},
        reason=reason,
    )

    async def _run() -> None:
        transport = GoogleDocsTransport(cred.token)
        client = DocsClient(transport)
        try:
            await client.pull(
                document_id,
                output_dir,
                save_raw=not args.no_raw,
                format="markdown",
            )
            print(f"Pulled document to {output_dir / document_id}/")
        finally:
            await transport.close()

    asyncio.run(_run())


def cmd_doc_push_md(args: Any) -> None:
    """Push changes to a Google Doc (markdown format, auto-detected)."""
    # Format is auto-detected from index.xml; push logic is identical to XML.
    cmd_doc_push(args)


def cmd_doc_create(args: Any) -> None:
    """Create a new Google Doc."""
    _cmd_create("doc", args)


def cmd_doc_create_md(args: Any) -> None:
    """Create a new Google Doc and optionally initialize it from markdown files."""
    import xml.etree.ElementTree as ET
    from pathlib import Path

    from extradoc import DocsClient, GoogleDocsTransport

    from extrasuite.client import CredentialsManager
    from extrasuite.client.cli._common import _auth_kwargs, _get_reason
    from extrasuite.client.google_api import create_file_via_drive, share_file

    manager = CredentialsManager(**_auth_kwargs(args))
    reason = _get_reason(args, default="Create Google Doc with markdown content")
    output_dir = Path(args.output_dir) if args.output_dir else Path()

    # Step 1: Create doc and share with service account
    dwd_cred = manager.get_credential(
        command={"type": "drive.file.create", "file_name": args.title, "file_type": "doc"},
        reason=reason,
    )
    sa_email = dwd_cred.service_account_email
    if not sa_email:
        raise RuntimeError("Could not determine service account email. Cannot share file.")

    result = create_file_via_drive(
        dwd_cred.token, args.title, "application/vnd.google-apps.document"
    )
    file_id = result["id"]
    share_file(dwd_cred.token, file_id, sa_email)
    url = f"https://docs.google.com/document/d/{file_id}"
    doc_folder = output_dir / file_id

    # Step 2: Pull in markdown format to create the local folder structure
    sa_cred = manager.get_credential(
        command={"type": "doc.pull", "file_url": url, "file_name": args.title},
        reason=reason,
    )

    async def _pull(token: str) -> None:
        transport = GoogleDocsTransport(token)
        client = DocsClient(transport)
        try:
            await client.pull(file_id, output_dir, save_raw=True, format="markdown")
        finally:
            await transport.close()

    asyncio.run(_pull(sa_cred.token))

    # Step 3: Import user's markdown files if --from provided
    if args.from_folder:
        from_path = Path(args.from_folder)
        user_files = sorted(f for f in from_path.glob("*.md"))

        if user_files:
            # Map user files onto existing tabs; extras become new tabs
            index_path = doc_folder / "index.xml"
            root = ET.parse(index_path).getroot()
            existing_tab_folders = [t.get("folder", "") for t in root.findall(".//tab")]

            for i, user_file in enumerate(user_files):
                if i < len(existing_tab_folders):
                    target = doc_folder / f"{existing_tab_folders[i]}.md"
                else:
                    target = doc_folder / user_file.name
                target.write_text(user_file.read_text(encoding="utf-8"), encoding="utf-8")

            # Step 4: Push changes
            push_cred = manager.get_credential(
                command={"type": "doc.push", "file_url": url, "file_name": args.title},
                reason=reason,
            )

            async def _push() -> None:
                transport = GoogleDocsTransport(push_cred.token)
                client = DocsClient(transport)
                try:
                    push_result = await client.push(str(doc_folder), force=True)
                    if not push_result.success:
                        raise RuntimeError(f"Push failed: {push_result.message}")
                finally:
                    await transport.close()

            asyncio.run(_push())

            # Step 5: Re-pull to update pristine state with real tab IDs
            repull_cred = manager.get_credential(
                command={"type": "doc.pull", "file_url": url, "file_name": args.title},
                reason=reason,
            )
            asyncio.run(_pull(repull_cred.token))

    print(f"\nCreated document: {args.title}")
    print(f"URL: {url}")
    print(f"Local folder: {doc_folder}/")
    print(f"Shared with: {sa_email}")
    if args.from_folder:
        print(f"Content imported from: {args.from_folder}")


def cmd_doc_share(args: Any) -> None:
    """Share a Google Doc with trusted contacts."""
    _cmd_share("doc", args)
