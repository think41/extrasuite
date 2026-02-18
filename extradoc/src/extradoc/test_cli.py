"""Developer-facing test CLI for extradoc.

Entry point: extradoc-test

Commands:
    pull --mock <golden.json> <output-dir>   Mock pull using golden JSON
    pull <document-id-or-url> <output-dir>   Real pull (requires credentials)
    diff <folder>                             Show what diff would produce
    push --mock <folder>                      Mock push: apply to in-memory mock
    push <folder>                             Real push + auto re-pull + verify
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import tempfile
from pathlib import Path

import extradoc.serde as serde
from extradoc.api_types._generated import Document
from extradoc.client import (
    DocsClient,
    _create_pristine_zip,
    _extract_pristine_zip,
    _read_document_id,
)
from extradoc.comments._from_raw import from_raw as comments_from_raw
from extradoc.comments._types import DocumentWithComments
from extradoc.mock.api import MockGoogleDocsAPI
from extradoc.reconcile import reconcile, reindex_document, resolve_deferred_ids, verify
from extradoc.transport import GoogleDocsTransport, LocalFileTransport


def _extract_doc_id(id_or_url: str) -> str:
    """Extract document ID from a URL or return as-is."""
    match = re.search(r"/d/([a-zA-Z0-9_-]+)", id_or_url)
    if match:
        return match.group(1)
    return id_or_url


# ---------------------------------------------------------------------------
# pull command
# ---------------------------------------------------------------------------


async def _cmd_pull_mock(golden_json: Path, output_dir: Path) -> None:
    """Mock pull: read golden JSON, serialize to folder (no auth)."""
    raw = json.loads(golden_json.read_text(encoding="utf-8"))
    doc_id = raw.get("documentId", golden_json.stem)
    doc = Document.model_validate(raw)

    # Look for a companion comments file
    comments_path = golden_json.parent / (golden_json.stem + "_comments.json")

    raw_comments: list[dict] = []  # type: ignore[type-arg]
    if comments_path.exists():
        data = json.loads(comments_path.read_text(encoding="utf-8"))
        raw_comments = data.get("comments", [])
        print(f"Loaded {len(raw_comments)} comment(s) from {comments_path.name}")

    file_comments = comments_from_raw(doc_id, raw_comments)
    bundle = DocumentWithComments(document=doc, comments=file_comments)

    document_dir = output_dir / doc_id
    written = serde.serialize(bundle, document_dir)
    pristine = _create_pristine_zip(document_dir)
    written.append(pristine)

    print(f"Pulled (mock) → {document_dir}")
    for p in written:
        print(f"  {p.relative_to(output_dir)}")


async def _cmd_pull_real(doc_id_or_url: str, output_dir: Path) -> None:
    """Real pull using credentials from env/config."""
    token = os.environ.get("EXTRADOC_ACCESS_TOKEN") or os.environ.get(
        "GOOGLE_ACCESS_TOKEN"
    )
    if not token:
        print(
            "ERROR: Set EXTRADOC_ACCESS_TOKEN or GOOGLE_ACCESS_TOKEN env var",
            file=sys.stderr,
        )
        sys.exit(1)

    doc_id = _extract_doc_id(doc_id_or_url)
    transport = GoogleDocsTransport(access_token=token)
    try:
        client = DocsClient(transport)
        written = await client.pull(doc_id, output_dir)
        print(f"Pulled → {output_dir / doc_id}")
        for p in written:
            print(f"  {p.relative_to(output_dir)}")
    finally:
        await transport.close()


# ---------------------------------------------------------------------------
# diff command
# ---------------------------------------------------------------------------


def _cmd_diff(folder: Path) -> None:
    """Show what diff would produce."""
    # Use a dummy LocalFileTransport (diff() doesn't call transport)
    transport = LocalFileTransport(folder)
    client = DocsClient(transport)

    result = client.diff(folder)

    print(f"Document ID: {result.document_id}")
    print()

    if result.batches:
        total_requests = sum(len(b.requests or []) for b in result.batches)
        print(
            f"Document batches: {len(result.batches)} batch(es),"
            f" {total_requests} request(s)"
        )
        for i, batch in enumerate(result.batches):
            reqs = batch.requests or []
            print(f"  Batch {i + 1}: {len(reqs)} request(s)")
            for req in reqs:
                d = req.model_dump(by_alias=True, exclude_none=True)
                req_type = next(iter(d), "unknown")
                print(f"    - {req_type}")
    else:
        print("Document batches: none")

    print()
    ops = result.comment_ops
    if ops.has_operations:
        print("Comment operations:")
        if ops.new_replies:
            print(f"  New replies: {len(ops.new_replies)}")
        if ops.resolves:
            print(f"  Resolves: {len(ops.resolves)}")
        if ops.edits:
            print(f"  Comment edits: {len(ops.edits)}")
        if ops.reply_edits:
            print(f"  Reply edits: {len(ops.reply_edits)}")
        if ops.deletes:
            print(f"  Comment deletes: {len(ops.deletes)}")
    else:
        print("Comment operations: none")


# ---------------------------------------------------------------------------
# push --mock command
# ---------------------------------------------------------------------------


async def _cmd_push_mock(folder: Path) -> None:
    """Mock push: apply reconcile to in-memory mock, verify result."""
    document_id = _read_document_id(folder)
    print(f"Document ID: {document_id}")

    # Load base (pristine) and desired bundles
    with tempfile.TemporaryDirectory() as tmp:
        _extract_pristine_zip(folder, Path(tmp))
        base_bundle = serde.deserialize(Path(tmp))

    desired_bundle = serde.deserialize(folder)

    base = reindex_document(base_bundle.document)
    desired = reindex_document(desired_bundle.document)
    batches = reconcile(base, desired)

    if not batches:
        print("No document changes — nothing to push.")
        return

    print(f"Applying {len(batches)} batch(es) to mock...")

    mock = MockGoogleDocsAPI(base)

    responses: list[dict] = []  # type: ignore[type-arg]
    for i, batch in enumerate(batches):
        if i > 0:
            batch = resolve_deferred_ids(responses, batch)
        resp = mock._batch_update_raw(
            [
                r.model_dump(by_alias=True, exclude_none=True)
                for r in (batch.requests or [])
            ]
        )
        responses.append(resp)

    match, diffs = verify(base, batches, desired)

    if match:
        print("PASS — mock document matches desired after push")
    else:
        print("FAIL — mock document differs from desired:")
        for diff in diffs:
            print(f"  {diff}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# push real command
# ---------------------------------------------------------------------------


async def _cmd_push_real(folder: Path) -> None:
    """Real push: apply to live doc, then auto re-pull, verify."""
    token = os.environ.get("EXTRADOC_ACCESS_TOKEN") or os.environ.get(
        "GOOGLE_ACCESS_TOKEN"
    )
    if not token:
        print(
            "ERROR: Set EXTRADOC_ACCESS_TOKEN or GOOGLE_ACCESS_TOKEN env var",
            file=sys.stderr,
        )
        sys.exit(1)

    transport = GoogleDocsTransport(access_token=token)
    try:
        client = DocsClient(transport)
        result = await client.push(folder)
        print(f"Push result: {result.message}")
        print(f"  Changes applied: {result.changes_applied}")
        print(f"  Replies created: {result.replies_created}")
        print(f"  Comments resolved: {result.comments_resolved}")

        # Auto re-pull
        print("\nRe-pulling to verify...")
        with tempfile.TemporaryDirectory() as tmp:
            repulled = await client.pull(result.document_id, Path(tmp))
            print(f"Re-pulled {len(repulled)} files")
    finally:
        await transport.close()


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="extradoc-test",
        description="Developer test CLI for extradoc pull/diff/push workflow",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # pull
    pull_p = subparsers.add_parser("pull", help="Pull a document")
    pull_p.add_argument(
        "--mock",
        metavar="GOLDEN_JSON",
        type=Path,
        help="Use a golden JSON file instead of the live API",
    )
    pull_p.add_argument(
        "source",
        help="Document ID, URL, or (with --mock) ignored (use --mock path)",
    )
    pull_p.add_argument("output_dir", type=Path, help="Output directory")

    # diff
    diff_p = subparsers.add_parser("diff", help="Show diff between edited and pristine")
    diff_p.add_argument("folder", type=Path, help="Document folder")

    # push
    push_p = subparsers.add_parser("push", help="Push changes to document")
    push_p.add_argument(
        "--mock",
        action="store_true",
        help="Apply to in-memory mock instead of live API",
    )
    push_p.add_argument("folder", type=Path, help="Document folder")

    args = parser.parse_args()

    if args.command == "pull":
        if args.mock:
            asyncio.run(_cmd_pull_mock(args.mock, args.output_dir))
        else:
            asyncio.run(_cmd_pull_real(args.source, args.output_dir))
    elif args.command == "diff":
        _cmd_diff(args.folder)
    elif args.command == "push":
        if args.mock:
            asyncio.run(_cmd_push_mock(args.folder))
        else:
            asyncio.run(_cmd_push_real(args.folder))


if __name__ == "__main__":
    main()
