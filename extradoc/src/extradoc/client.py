"""DocsClient - main interface for extradoc pull/diff/push operations.

Orchestrates pull/diff/push using serde + reconcile + comments packages.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from extradoc.api_types._generated import (
    BatchUpdateDocumentRequest,
    Document,
)
from extradoc.comments._diff import diff_comments
from extradoc.comments._from_raw import from_raw as comments_from_raw
from extradoc.comments._types import (
    CommentOperations,
    DocumentWithComments,
)
from extradoc.mock.reindex import reindex_and_normalize_all_tabs
from extradoc.reconcile_v3.api import reconcile_batches as reconcile_v3_batches
from extradoc.reconcile_v3.executor import execute_request_batches
from extradoc.serde._models import IndexXml
from extradoc.serde.markdown import MarkdownSerde
from extradoc.serde.xml import XmlSerde

if TYPE_CHECKING:
    from extradoc.serde import Serde
    from extradoc.transport import Transport

logger = logging.getLogger(__name__)

RAW_DIR = ".raw"


@dataclass
class PushResult:
    """Result of a push operation."""

    success: bool
    document_id: str
    changes_applied: int
    message: str = ""
    replies_created: int = 0
    comments_resolved: int = 0


@dataclass
class DiffResult:
    """Internal result of diff() — input for push()."""

    document_id: str
    batches: list[BatchUpdateDocumentRequest]
    comment_ops: CommentOperations
    base_revision_id: str | None = None


class DocsClient:
    """Main client for Google Docs pull/diff/push operations."""

    _xml_serde: Serde = XmlSerde()
    _md_serde: Serde = MarkdownSerde()

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    def _get_serde(self, format: str) -> Serde:
        """Return the appropriate serde for the given format."""
        return self._md_serde if format == "markdown" else self._xml_serde

    async def pull(
        self,
        document_id: str,
        output_path: str | Path,
        *,
        save_raw: bool = True,
        format: str = "xml",
    ) -> None:
        """Pull a document from Google Docs to local files.

        Args:
            document_id: The document identifier
            output_path: Parent directory for the output folder
            save_raw: Whether to save optional raw sidecars such as comments.json
            format: Output format — "xml" (default) or "markdown"
        """
        output_path = Path(output_path)

        # Fetch document and comments
        document_data = await self._transport.get_document(document_id)
        raw_comments = await self._transport.list_comments(document_id)

        # Parse into typed models
        doc = Document.model_validate(document_data.raw)
        file_comments = comments_from_raw(document_id, raw_comments)
        bundle = DocumentWithComments(document=doc, comments=file_comments)

        document_dir = output_path / document_id
        serde_impl = self._get_serde(format)
        serde_impl.serialize(bundle, document_dir)

        # Optional: save raw comments JSON for debugging
        if save_raw and raw_comments:
            raw_dir = document_dir / RAW_DIR
            raw_dir.mkdir(parents=True, exist_ok=True)
            raw_comments_path = raw_dir / "comments.json"
            raw_comments_path.write_text(
                json.dumps({"comments": raw_comments}, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

    def diff(self, folder: str | Path) -> DiffResult:
        """Compare current files against pristine and generate batch requests.

        This is local-only and does not make any API calls.

        Args:
            folder: Path to document folder (containing index.xml)

        Returns:
            DiffResult with document_id, batches, and comment_ops
        """
        folder = Path(folder)
        document_id = _read_document_id(folder)

        index_path = folder / "index.xml"
        index = IndexXml.from_xml_string(index_path.read_text(encoding="utf-8"))
        serde_impl = self._get_serde(index.format or "xml")

        result = serde_impl.deserialize(folder)

        base = result.base
        desired_dict = result.desired.document.model_dump(
            by_alias=True, exclude_none=True
        )
        reindex_and_normalize_all_tabs(desired_dict)
        desired_doc = Document.model_validate(desired_dict)
        batches = _reconcile_documents(base.document, desired_doc)
        comment_ops = diff_comments(base.comments, result.desired.comments)

        return DiffResult(
            document_id=document_id,
            batches=batches,
            comment_ops=comment_ops,
            base_revision_id=base.document.revision_id,
        )

    async def push(self, folder: str | Path, *, force: bool = False) -> PushResult:
        """Push local changes to Google Docs.

        Comment operations execute before document changes so that anchor
        positions (relative to the current live document) are not shifted
        by document mutations.

        Args:
            folder: Path to document folder
            force: Reserved for future use

        Returns:
            PushResult with success status and details
        """
        _ = force
        folder = Path(folder)
        result = self.diff(folder)

        if not result.batches and not result.comment_ops.has_operations:
            return PushResult(
                success=True,
                document_id=result.document_id,
                changes_applied=0,
                message="No changes to apply",
            )

        # --- 1. Comment operations (Drive API — before document changes) ---
        replies_created = 0
        comments_resolved = 0
        edits_applied = 0
        ops = result.comment_ops

        for r in ops.new_replies:
            await self._transport.create_reply(
                result.document_id, r.comment_id, r.content
            )
            replies_created += 1

        for s in ops.resolves:
            await self._transport.create_reply(
                result.document_id, s.comment_id, "", action="resolve"
            )
            comments_resolved += 1

        for e in ops.edits:
            await self._transport.edit_comment(
                result.document_id, e.comment_id, e.content
            )
            edits_applied += 1

        for d in ops.deletes:
            await self._transport.delete_comment(result.document_id, d.comment_id)

        for re_ in ops.reply_edits:
            await self._transport.edit_reply(
                result.document_id, re_.comment_id, re_.reply_id, re_.content
            )
            edits_applied += 1

        # --- 2. Document batches (Docs API — reconcile output) ---
        changes_applied = await _execute_document_batches(
            self._transport,
            result,
        )

        # Build result message
        parts: list[str] = []
        if changes_applied:
            parts.append(f"{changes_applied} document changes")
        if replies_created:
            parts.append(f"{replies_created} replies added")
        if comments_resolved:
            parts.append(f"{comments_resolved} comments resolved")
        if edits_applied:
            parts.append(f"{edits_applied} comment edits")

        message = "Applied " + ", ".join(parts) if parts else "No changes to apply"

        return PushResult(
            success=True,
            document_id=result.document_id,
            changes_applied=changes_applied,
            message=message,
            replies_created=replies_created,
            comments_resolved=comments_resolved,
        )


def _reconcile_documents(
    base: Document,
    desired: Document,
) -> list[BatchUpdateDocumentRequest]:
    return reconcile_v3_batches(base, desired)


async def _execute_document_batches(
    transport: Transport,
    result: DiffResult,
) -> int:
    await execute_request_batches(
        transport,
        document_id=result.document_id,
        request_batches=result.batches,
        initial_revision_id=result.base_revision_id,
    )
    return sum(len(batch.requests or []) for batch in result.batches)


def _read_document_id(folder: Path) -> str:
    """Read the document ID from index.xml."""
    index_path = folder / "index.xml"
    if not index_path.exists():
        return folder.name
    index = IndexXml.from_xml_string(index_path.read_text(encoding="utf-8"))
    return index.id or folder.name
