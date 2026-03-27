"""Doc CLI commands: pull, diff, push, create."""

from __future__ import annotations

import asyncio
import json
import shutil
import sys
import tempfile
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
    output_dir_arg = args.output_dir

    reason = _get_reason(args, default="Pulling Google Doc")
    cred = _get_credential(
        args,
        command={"type": "doc.pull", "file_url": args.url, "file_name": ""},
        reason=reason,
    )

    tmp_parent = None
    if output_dir_arg:
        tmp_parent = Path(tempfile.mkdtemp())
        dest_dir = Path(output_dir_arg)
    else:
        dest_dir = Path() / document_id

    async def _run() -> None:
        transport = GoogleDocsTransport(cred.token)
        client = DocsClient(transport)
        pull_parent = tmp_parent if tmp_parent else Path()
        try:
            await client.pull(
                document_id,
                pull_parent,
                save_raw=not args.no_raw,
            )
            if tmp_parent is not None:
                dest_dir.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(tmp_parent / document_id), str(dest_dir))
        finally:
            await transport.close()

    try:
        asyncio.run(_run())
    finally:
        if tmp_parent is not None:
            shutil.rmtree(tmp_parent, ignore_errors=True)

    print(f"Pulled to {dest_dir}/")


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
    output_dir_arg = args.output_dir

    reason = _get_reason(args, default="Pulling Google Doc as markdown")
    cred = _get_credential(
        args,
        command={"type": "doc.pull", "file_url": args.url, "file_name": ""},
        reason=reason,
    )

    tmp_parent = None
    if output_dir_arg:
        tmp_parent = Path(tempfile.mkdtemp())
        dest_dir = Path(output_dir_arg)
    else:
        dest_dir = Path() / document_id

    async def _run() -> None:
        transport = GoogleDocsTransport(cred.token)
        client = DocsClient(transport)
        pull_parent = tmp_parent if tmp_parent else Path()
        try:
            await client.pull(
                document_id,
                pull_parent,
                save_raw=not args.no_raw,
                format="markdown",
            )
            if tmp_parent is not None:
                dest_dir.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(tmp_parent / document_id), str(dest_dir))
        finally:
            await transport.close()

    try:
        asyncio.run(_run())
    finally:
        if tmp_parent is not None:
            shutil.rmtree(tmp_parent, ignore_errors=True)

    print(f"Pulled to {dest_dir}/")


def cmd_doc_push_md(args: Any) -> None:
    """Push changes to a Google Doc (markdown format, auto-detected)."""
    # Format is auto-detected from index.xml; push logic is identical to XML.
    cmd_doc_push(args)


def cmd_doc_create(args: Any) -> None:
    """Create a new Google Doc and pull it locally."""
    from extradoc import DocsClient, GoogleDocsTransport

    file_id, url = _cmd_create("doc", args)

    output_dir_arg = getattr(args, "output_dir", None)
    tmp_parent = None
    if output_dir_arg:
        tmp_parent = Path(tempfile.mkdtemp())
        dest_dir = Path(output_dir_arg)
    else:
        dest_dir = Path() / file_id

    reason = _get_reason(args, default="Pulling newly created Google Doc")
    cred = _get_credential(
        args,
        command={"type": "doc.pull", "file_url": url, "file_name": args.title},
        reason=reason,
    )

    async def _run() -> None:
        transport = GoogleDocsTransport(cred.token)
        client = DocsClient(transport)
        pull_parent = tmp_parent if tmp_parent else Path()
        try:
            await client.pull(file_id, pull_parent, save_raw=True)
            if tmp_parent is not None:
                dest_dir.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(tmp_parent / file_id), str(dest_dir))
        finally:
            await transport.close()

    try:
        asyncio.run(_run())
    finally:
        if tmp_parent is not None:
            shutil.rmtree(tmp_parent, ignore_errors=True)

    print(f"Pulled to {dest_dir}/")


def cmd_doc_share(args: Any) -> None:
    """Share a Google Doc with trusted contacts."""
    _cmd_share("doc", args)
