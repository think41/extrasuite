"""DocsClient - main interface for extradoc pull/diff/push operations.

Orchestrates pull/diff/push using serde + reconcile + comments packages.
"""

from __future__ import annotations

import json
import logging
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import extradoc.serde as serde
from extradoc.api_types._generated import Document
from extradoc.comments._diff import diff_comments
from extradoc.comments._from_raw import from_raw as comments_from_raw
from extradoc.comments._types import (
    CommentOperations,
    DocumentWithComments,
)
from extradoc.reconcile import reconcile, reindex_document, resolve_deferred_ids
from extradoc.serde._models import IndexXml

if TYPE_CHECKING:
    from extradoc.api_types._generated import BatchUpdateDocumentRequest
    from extradoc.transport import Transport

logger = logging.getLogger(__name__)

# Directory / file constants
RAW_DIR = ".raw"
PRISTINE_DIR = ".pristine"
PRISTINE_ZIP = "document.zip"


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


class DocsClient:
    """Main client for Google Docs pull/diff/push operations."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def pull(
        self,
        document_id: str,
        output_path: str | Path,
        *,
        save_raw: bool = True,
    ) -> list[Path]:
        """Pull a document from Google Docs to local files.

        Args:
            document_id: The document identifier
            output_path: Parent directory for the output folder
            save_raw: Whether to save raw API responses to .raw/ folder

        Returns:
            List of file paths written
        """
        output_path = Path(output_path)

        # Fetch document and comments in parallel
        document_data = await self._transport.get_document(document_id)
        raw_comments = await self._transport.list_comments(document_id)

        # Parse into typed models
        doc = Document.model_validate(document_data.raw)
        file_comments = comments_from_raw(document_id, raw_comments)
        bundle = DocumentWithComments(document=doc, comments=file_comments)

        document_dir = output_path / document_id
        document_dir.mkdir(parents=True, exist_ok=True)

        # Serialize bundle to folder
        written_files = serde.serialize(bundle, document_dir)

        # Optionally save raw API responses
        if save_raw:
            raw_dir = document_dir / RAW_DIR
            raw_dir.mkdir(parents=True, exist_ok=True)

            raw_doc_path = raw_dir / "document.json"
            raw_doc_path.write_text(
                json.dumps(document_data.raw, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            written_files.append(raw_doc_path)

            if raw_comments:
                raw_comments_path = raw_dir / "comments.json"
                raw_comments_path.write_text(
                    json.dumps(
                        {"comments": raw_comments}, indent=2, ensure_ascii=False
                    ),
                    encoding="utf-8",
                )
                written_files.append(raw_comments_path)

        # Create pristine zip from the serde output
        pristine_path = _create_pristine_zip(document_dir)
        written_files.append(pristine_path)

        return written_files

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

        with tempfile.TemporaryDirectory() as tmp:
            _extract_pristine_zip(folder, Path(tmp))
            base_bundle = serde.deserialize(Path(tmp))

        desired_bundle = serde.deserialize(folder)

        base = reindex_document(base_bundle.document)
        desired = reindex_document(desired_bundle.document)
        batches = reconcile(base, desired)

        comment_ops = diff_comments(base_bundle.comments, desired_bundle.comments)

        return DiffResult(
            document_id=document_id,
            batches=batches,
            comment_ops=comment_ops,
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
        prior_responses: list[dict] = []  # type: ignore[type-arg]
        changes_applied = 0

        for i, batch in enumerate(result.batches):
            if i > 0:
                batch = resolve_deferred_ids(prior_responses, batch)
            resp = await self._transport.batch_update(
                result.document_id,
                [
                    r.model_dump(by_alias=True, exclude_none=True)
                    for r in (batch.requests or [])
                ],
            )
            prior_responses.append(resp)
            changes_applied += len(batch.requests or [])

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


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _create_pristine_zip(folder: Path) -> Path:
    """Zip the entire serde output (excluding .pristine/ and .raw/) into pristine zip.

    Args:
        folder: The document folder to zip

    Returns:
        Path to the created zip file
    """
    pristine_dir = folder / PRISTINE_DIR
    pristine_dir.mkdir(parents=True, exist_ok=True)
    zip_path = pristine_dir / PRISTINE_ZIP

    _skip_dirs = {PRISTINE_DIR, RAW_DIR}

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(folder.rglob("*")):
            if path.is_dir():
                continue
            # Skip anything inside .pristine/ or .raw/
            try:
                rel = path.relative_to(folder)
            except ValueError:
                continue
            if rel.parts[0] in _skip_dirs:
                continue
            zf.write(path, rel)

    return zip_path


def _extract_pristine_zip(folder: Path, dest: Path) -> None:
    """Extract the pristine zip into dest directory.

    Args:
        folder: The document folder containing .pristine/document.zip
        dest: Destination directory to extract into
    """
    zip_path = folder / PRISTINE_DIR / PRISTINE_ZIP
    if not zip_path.exists():
        raise FileNotFoundError(f"Pristine zip not found: {zip_path}")
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(dest)


def _read_document_id(folder: Path) -> str:
    """Read the document ID from index.xml.

    Args:
        folder: The document folder containing index.xml

    Returns:
        The document ID string
    """
    index_path = folder / "index.xml"
    if not index_path.exists():
        # Fall back to folder name
        return folder.name
    index = IndexXml.from_xml_string(index_path.read_text(encoding="utf-8"))
    return index.id or folder.name
