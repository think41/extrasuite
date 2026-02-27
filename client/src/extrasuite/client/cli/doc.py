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
    _get_token,
    _parse_document_id,
)


def cmd_doc_pull(args: Any) -> None:
    """Pull a Google Doc."""
    from extradoc import DocsClient, GoogleDocsTransport

    document_id = _parse_document_id(args.url)
    output_dir = Path(args.output_dir) if args.output_dir else Path()
    access_token = _get_token(args, reason="Pulling Google Doc", scope="doc.pull")

    async def _run() -> None:
        transport = GoogleDocsTransport(access_token)
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

    access_token = _get_token(
        args, reason="Pushing changes to Google Doc", scope="doc.push"
    )

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


def cmd_doc_create(args: Any) -> None:
    """Create a new Google Doc."""
    _cmd_create("doc", args)


def cmd_doc_share(args: Any) -> None:
    """Share a Google Doc with trusted contacts."""
    _cmd_share("doc", args)
