"""DocsClient - main interface for extradoc pull/diff/push operations.

Orchestrates pull/diff/push using serde + reconcile + comments packages.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
import zipfile
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import extradoc.serde as serde
from extradoc.api_types._generated import (
    BatchUpdateDocumentRequest,
    Document,
    Paragraph,
    ParagraphElement,
    ParagraphStyle,
    StructuralElement,
    TableCell,
    TextRun,
    TextStyle,
)
from extradoc.comments._diff import diff_comments
from extradoc.comments._from_raw import from_raw as comments_from_raw
from extradoc.comments._types import (
    CommentOperations,
    DocumentWithComments,
)
from extradoc.reconcile import (
    reconcile as reconcile_v1,
)
from extradoc.reconcile import (
    reindex_document,
    resolve_deferred_ids,
)
from extradoc.reconcile_v2.api import reconcile as reconcile_v2
from extradoc.reconcile_v2.executor import (
    execute_request_batches,
    resolve_deferred_placeholders,
)
from extradoc.reconcile_v3.api import reconcile_batches as reconcile_v3_batches
from extradoc.serde._models import IndexXml
from extradoc.serde._utils import hex_to_optional_color, optional_color_to_hex
from extradoc.transport import APIError, DocumentConflictError

if TYPE_CHECKING:
    from extradoc.api_types._generated import DocumentTab
    from extradoc.transport import Transport

logger = logging.getLogger(__name__)

RECONCILER_ENV_VAR = "EXTRADOC_RECONCILER"

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
    reconciler_version: str = "v3"
    base_revision_id: str | None = None
    desired_document: Document | None = None
    desired_format: str | None = None
    allow_live_refresh: bool = False


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
        format: str = "xml",
    ) -> list[Path]:
        """Pull a document from Google Docs to local files.

        Args:
            document_id: The document identifier
            output_path: Parent directory for the output folder
            save_raw: Whether to save optional raw sidecars such as comments.json.
                The raw document JSON is always written because diff/push now
                treat ``.raw/document.json`` as required transport state.
            format: Output format — "xml" (default) or "markdown"

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
        written_files = serde.serialize(bundle, document_dir, format=format)

        # Raw document JSON is always materialized because the reconciler uses
        # it as transport-accurate base state during diff/push.
        raw_dir = document_dir / RAW_DIR
        raw_dir.mkdir(parents=True, exist_ok=True)

        raw_doc_path = raw_dir / "document.json"
        raw_doc_path.write_text(
            json.dumps(document_data.raw, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        written_files.append(raw_doc_path)

        if save_raw and raw_comments:
            raw_comments_path = raw_dir / "comments.json"
            raw_comments_path.write_text(
                json.dumps({"comments": raw_comments}, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            written_files.append(raw_comments_path)

        # Create pristine zip from the serde output.
        # For markdown format, _serialize_markdown already wrote the pristine zip;
        # re-writing it here ensures .raw/ is excluded regardless of format.
        pristine_path = _create_pristine_zip(document_dir)
        written_files.append(pristine_path)

        return written_files

    def diff(self, folder: str | Path) -> DiffResult:
        """Compare current files against pristine and generate batch requests.

        This is local-only and does not make any API calls.

        When `.raw/document.json` exists, it is treated as the authoritative
        live transport base for reconciliation. XML/markdown semantic
        correctness is still validated at the serde boundary, but the
        reconciler itself runs against the pulled raw document so requests are
        anchored to real Docs indices/story state.

        Args:
            folder: Path to document folder (containing index.xml)

        Returns:
            DiffResult with document_id, batches, and comment_ops
        """
        folder = Path(folder)
        document_id = _read_document_id(folder)
        reconciler_version = _get_reconciler_version()

        index_path = folder / "index.xml"
        index = serde.IndexXml.from_xml_string(index_path.read_text(encoding="utf-8"))

        # Prefer the raw API JSON as transport base so generated requests carry
        # real Docs indices rather than reconstructed approximations.
        raw_doc_path = folder / RAW_DIR / "document.json"
        if raw_doc_path.exists():
            raw_data = json.loads(raw_doc_path.read_text(encoding="utf-8"))
            transport_base = Document.model_validate(raw_data)
            if index.format == "markdown":
                # 3-way merge: desired = apply_ops(transport_base, diff(ancestor_md, mine_md))
                # Fields the markdown SERDE doesn't model (lineSpacing, underline on links,
                # inter-table separators, TITLE/SUBTITLE etc.) produce zero ops and are
                # preserved unchanged from transport_base.  No normalisation needed.
                with tempfile.TemporaryDirectory() as tmp:
                    _extract_pristine_zip(folder, Path(tmp))
                    pristine_bundle = serde.deserialize(Path(tmp))
                transport_bundle = DocumentWithComments(
                    document=transport_base, comments=pristine_bundle.comments
                )
                desired_bundle = serde.deserialize(transport_bundle, folder)
                desired = reindex_document(desired_bundle.document)
                batches = _reconcile_documents(
                    transport_base,
                    desired,
                    reconciler_version=reconciler_version,
                    transport_base=transport_base,
                )
                comment_ops = diff_comments(
                    pristine_bundle.comments, desired_bundle.comments
                )
                return DiffResult(
                    document_id=document_id,
                    batches=batches,
                    comment_ops=comment_ops,
                    reconciler_version=reconciler_version,
                    base_revision_id=transport_base.revision_id,
                    desired_document=desired,
                    desired_format="markdown",
                    allow_live_refresh=_tab_ids_subset(transport_base, desired),
                )

            with tempfile.TemporaryDirectory() as tmp:
                _extract_pristine_zip(folder, Path(tmp))
                base_bundle = serde.deserialize(Path(tmp))
            desired_bundle = serde.deserialize(folder)
            base = transport_base
            desired = reindex_document(desired_bundle.document)
            batches = _reconcile_documents(
                base,
                desired,
                reconciler_version=reconciler_version,
                transport_base=transport_base,
            )
            comment_ops = diff_comments(base_bundle.comments, desired_bundle.comments)
            return DiffResult(
                document_id=document_id,
                batches=batches,
                comment_ops=comment_ops,
                reconciler_version=reconciler_version,
                base_revision_id=transport_base.revision_id,
                desired_document=desired,
                desired_format=index.format,
                allow_live_refresh=_tab_ids_subset(base, desired),
            )

        with tempfile.TemporaryDirectory() as tmp:
            _extract_pristine_zip(folder, Path(tmp))
            base_bundle = serde.deserialize(Path(tmp))
        desired_bundle = serde.deserialize(folder)
        base = reindex_document(base_bundle.document)
        desired = reindex_document(desired_bundle.document)
        batches = _reconcile_documents(
            base,
            desired,
            reconciler_version=reconciler_version,
        )

        comment_ops = diff_comments(base_bundle.comments, desired_bundle.comments)

        return DiffResult(
            document_id=document_id,
            batches=batches,
            comment_ops=comment_ops,
            reconciler_version=reconciler_version,
            base_revision_id=base.revision_id,
            desired_document=desired,
            desired_format="xml",
            allow_live_refresh=_tab_ids_subset(base, desired),
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


def _get_reconciler_version() -> str:
    raw = os.getenv(RECONCILER_ENV_VAR, "v3").strip().lower()
    if raw in {"", "v3"}:
        return "v3"
    if raw in {"v2", "semantic-ir", "semantic_ir"}:
        return "v2"
    if raw in {"v1", "legacy"}:
        return "v1"
    raise ValueError(
        f"Unsupported {RECONCILER_ENV_VAR} value {raw!r}; expected v1, v2, or v3"
    )


def _reconcile_documents(
    base: Document,
    desired: Document,
    *,
    reconciler_version: str,
    transport_base: Document | None = None,
) -> list[BatchUpdateDocumentRequest]:
    if reconciler_version == "v2":
        return reconcile_v2(base, desired, transport_base=transport_base)
    if reconciler_version == "v3":
        base_dict = base.model_dump(by_alias=True, exclude_none=True)
        desired_dict = desired.model_dump(by_alias=True, exclude_none=True)
        raw_batches = reconcile_v3_batches(base_dict, desired_dict)
        return [
            BatchUpdateDocumentRequest.model_validate({"requests": batch})
            for batch in raw_batches
        ]
    return reconcile_v1(base, desired)


async def _execute_document_batches(
    transport: Transport,
    result: DiffResult,
) -> int:
    if result.reconciler_version in {"v2", "v3"}:
        if (
            result.reconciler_version == "v2"
            and result.allow_live_refresh
            and result.desired_document is not None
            and result.desired_format is not None
        ):
            return await _execute_document_batches_v2_live_refresh(transport, result)
        request_batches = [
            [
                request.model_dump(by_alias=True, exclude_none=True)
                for request in (batch.requests or [])
            ]
            for batch in result.batches
        ]
        await execute_request_batches(
            transport,
            document_id=result.document_id,
            request_batches=request_batches,
            initial_revision_id=result.base_revision_id,
        )
        return sum(len(batch) for batch in request_batches)

    prior_responses: list[dict] = []  # type: ignore[type-arg]
    changes_applied = 0
    for i, batch in enumerate(result.batches):
        if i > 0:
            batch = resolve_deferred_ids(prior_responses, batch)
        resp = await transport.batch_update(
            result.document_id,
            [
                request.model_dump(by_alias=True, exclude_none=True)
                for request in (batch.requests or [])
            ],
        )
        prior_responses.append(resp)
        changes_applied += len(batch.requests or [])
    return changes_applied


async def _execute_document_batches_v2_live_refresh(
    transport: Transport,
    result: DiffResult,
) -> int:
    assert result.desired_document is not None
    assert result.desired_format is not None

    request_batches = [
        [
            request.model_dump(by_alias=True, exclude_none=True)
            for request in (batch.requests or [])
        ]
        for batch in result.batches
    ]
    revision_id = result.base_revision_id
    changes_applied = 0
    batch_index = 0
    prior_responses: list[dict] = []  # type: ignore[type-arg]

    while batch_index < len(request_batches):
        batch = request_batches[batch_index]
        resolved_batch = resolve_deferred_placeholders(prior_responses, list(batch))
        resolved_batch, refresh_reason = _truncate_batch_for_live_refresh(
            resolved_batch
        )
        write_control = None
        if revision_id is not None:
            write_control = {"requiredRevisionId": revision_id}
        try:
            response = await transport.batch_update(
                result.document_id,
                list(resolved_batch),
                write_control=write_control,
            )
        except APIError as exc:
            if not _is_revision_mismatch_error(exc):
                raise
            raise DocumentConflictError(
                "The document was modified by another party after you pulled it. "
                "Re-pull the document, merge your changes, and push again."
            ) from exc
        prior_responses.append(response)
        revision_id = _next_required_revision_id(response, revision_id)
        changes_applied += len(batch)
        batch_index += 1

        if refresh_reason is None:
            continue

        if refresh_reason == "structural":
            (
                refreshed_batches,
                revision_id,
            ) = await _refresh_v2_batches_after_structural_ops(
                transport=transport,
                document_id=result.document_id,
                _resolved_batch=resolved_batch,
                desired_document=result.desired_document,
                desired_format=result.desired_format,
                current_revision_id=revision_id,
            )
        else:
            (
                refreshed_batches,
                revision_id,
            ) = await _refresh_v2_batches_after_live_change(
                transport=transport,
                document_id=result.document_id,
                desired_document=result.desired_document,
                desired_format=result.desired_format,
                current_revision_id=revision_id,
            )
        request_batches = [
            [
                request.model_dump(by_alias=True, exclude_none=True)
                for request in (batch.requests or [])
            ]
            for batch in refreshed_batches
        ]
        batch_index = 0
        prior_responses = []

    return changes_applied


async def _refresh_v2_batches_after_structural_ops(
    *,
    transport: Transport,
    document_id: str,
    _resolved_batch: list[dict],
    desired_document: Document,
    desired_format: str,
    current_revision_id: str | None,
) -> tuple[list[BatchUpdateDocumentRequest], str | None]:
    max_attempts = 20
    next_revision_id = current_revision_id
    for attempt in range(max_attempts):
        document_data = await transport.get_document(document_id)
        transport_base = Document.model_validate(document_data.raw)
        base = Document.model_validate(document_data.raw)
        next_revision_id = transport_base.revision_id or current_revision_id
        if desired_format == "markdown":
            _normalize_raw_base_para_styles(base, desired_document)
        refreshed_batches = reconcile_v2(
            base,
            desired_document,
            transport_base=transport_base,
        )
        if not _refresh_still_contains_same_structural_shell(
            resolved_batch=_resolved_batch,
            refreshed_batches=refreshed_batches,
        ):
            return refreshed_batches, next_revision_id
        if attempt < max_attempts - 1:
            await asyncio.sleep(0.5)
    raise RuntimeError(
        "Live Docs did not expose the applied structural change after refresh retries"
    )


async def _refresh_v2_batches_after_live_change(
    *,
    transport: Transport,
    document_id: str,
    desired_document: Document,
    desired_format: str,
    current_revision_id: str | None,
) -> tuple[list[BatchUpdateDocumentRequest], str | None]:
    document_data = await transport.get_document(document_id)
    transport_base = Document.model_validate(document_data.raw)
    base = Document.model_validate(document_data.raw)
    next_revision_id = transport_base.revision_id or current_revision_id
    if desired_format == "markdown":
        _normalize_raw_base_para_styles(base, desired_document)
    refreshed_batches = reconcile_v2(
        base,
        desired_document,
        transport_base=transport_base,
    )
    return refreshed_batches, next_revision_id


def _should_refresh_v2_batches(batch: list[dict]) -> bool:
    return any(
        "insertTable" in request or "insertPageBreak" in request for request in batch
    )


def _truncate_batch_for_live_refresh(
    batch: list[dict],
) -> tuple[list[dict], str | None]:
    structural_trimmed = _truncate_batch_before_post_table_para_ops(batch)
    if structural_trimmed != batch:
        return structural_trimmed, "structural"
    # Batch has structural ops but nothing to truncate — still requires a refresh
    # so the reconciler can re-plan from the live post-structural state.
    if _should_refresh_v2_batches(batch):
        return batch, "structural"
    delete_trimmed = _truncate_batch_before_delete_sensitive_inserts(batch)
    if delete_trimmed != batch:
        return delete_trimmed, "delete-only"
    return batch, None


def _is_revision_mismatch_error(exc: APIError) -> bool:
    return exc.status_code == 400 and "required revision ID" in str(exc)


def _refresh_still_contains_same_structural_shell(
    *,
    resolved_batch: list[dict],
    refreshed_batches: list[BatchUpdateDocumentRequest],
) -> bool:
    wanted = {
        _structural_request_signature(request)
        for request in resolved_batch
        if _structural_request_signature(request) is not None
    }
    if not wanted:
        return False
    refreshed_raw = [
        request
        for batch in refreshed_batches
        for request in (
            batch.model_dump(by_alias=True, exclude_none=True, mode="json").get(
                "requests"
            )
            or []
        )
    ]
    seen = {
        _structural_request_signature(request)
        for request in refreshed_raw
        if _structural_request_signature(request) is not None
    }
    if wanted.isdisjoint(seen):
        return False
    if not refreshed_batches:
        return True
    first_refreshed_batch = (
        refreshed_batches[0]
        .model_dump(by_alias=True, exclude_none=True, mode="json")
        .get("requests")
        or []
    )
    truncated_first_refreshed_batch = _truncate_batch_before_post_table_para_ops(
        list(first_refreshed_batch)
    )
    return truncated_first_refreshed_batch == resolved_batch


def _structural_request_signature(
    request: dict,
) -> tuple[str, str | None, int | None] | None:
    if "insertTable" in request:
        payload = request["insertTable"]
        location = payload.get("location", {})
        return ("insertTable", location.get("tabId"), location.get("index"))
    if "insertPageBreak" in request:
        payload = request["insertPageBreak"]
        location = payload.get("location", {})
        return ("insertPageBreak", location.get("tabId"), location.get("index"))
    return None


def _truncate_batch_before_post_table_para_ops(batch: list[dict]) -> list[dict]:
    """Keep a structural shell plus safe surrounding content before refresh.

    Live Docs can lag behind the shadow shape around fresh ``insertTable``
    and ``insertPageBreak`` operations.  The lowered batch is in reverse
    document order (bottom-to-top insertion), so the first structural op in
    the batch corresponds to the *last* structural element in document order.

    **Single structural op per tab**: keep everything before and including the
    structural op in batch order (= the content that follows it in document
    order).  For ``insertTable``, also keep same-anchor ``insertText`` ops that
    appear after it in the batch (pre-table body paragraphs).  For
    ``insertPageBreak``, defer all following content.

    **Multiple structural ops per tab**: keep only the *last* structural op in
    batch order (= the *first* structural element in document order) together
    with the ``insertText`` ops that follow it in the batch (pre-structural
    body paragraphs in document order).  Content before the last structural op
    in batch order (= content after the first structural element in document
    order) is deferred entirely — it belongs to later refresh cycles.  This
    prevents the re-plan from seeing a document where end-of-document content
    has been inserted before beginning-of-document structural elements.

    Everything else on that tab after the selected structural op is deferred
    until the next live refresh.
    """
    structural_kinds = {"insertTable", "insertPageBreak"}
    if not any(k in request for k in structural_kinds for request in batch):
        return batch
    same_tab_followup_kinds = {
        "insertText",
        "createParagraphBullets",
        "updateParagraphStyle",
        "updateTextStyle",
        "insertTable",
        "insertPageBreak",
    }

    # Track both first and last structural op per tab to detect multi-structural batches.
    first_structural_index_by_tab: dict[str, int] = {}
    last_structural_index_by_tab: dict[str, int] = {}
    last_structural_kind_by_tab: dict[str, str] = {}
    last_structural_location_by_tab: dict[str, int | None] = {}
    for index, request in enumerate(batch):
        kind = next(iter(request))
        tab_id = _request_tab_id(request)
        if kind in structural_kinds and tab_id is not None:
            if tab_id not in first_structural_index_by_tab:
                first_structural_index_by_tab[tab_id] = index
            last_structural_index_by_tab[tab_id] = index
            last_structural_kind_by_tab[tab_id] = kind
            last_structural_location_by_tab[tab_id] = (
                request[kind].get("location", {}).get("index")
            )

    if not first_structural_index_by_tab:
        return batch

    # Tabs where multiple structural ops exist: use the last one (first in doc order).
    multi_structural_tabs = {
        tab_id
        for tab_id in first_structural_index_by_tab
        if first_structural_index_by_tab[tab_id] != last_structural_index_by_tab[tab_id]
    }

    trimmed: list[dict] = []
    for index, request in enumerate(batch):
        kind = next(iter(request))
        tab_id = _request_tab_id(request)
        if tab_id is None or tab_id not in first_structural_index_by_tab:
            trimmed.append(request)
            continue

        if tab_id in multi_structural_tabs:
            # Multi-structural: use last structural op (first in doc order).
            # Drop everything before it in batch order (later in doc order).
            structural_index = last_structural_index_by_tab[tab_id]
            structural_kind = last_structural_kind_by_tab[tab_id]
            structural_location = last_structural_location_by_tab[tab_id]
            if index < structural_index:
                # Earlier batch position = later doc position: defer entirely.
                continue
        else:
            # Single structural op: existing behaviour (keep everything up to it).
            structural_index = first_structural_index_by_tab[tab_id]
            structural_kind = last_structural_kind_by_tab[tab_id]
            structural_location = last_structural_location_by_tab[tab_id]
            if index <= structural_index:
                trimmed.append(request)
                continue

        # At or after the structural op in batch order.
        if index == structural_index:
            trimmed.append(request)
            continue
        # After the structural op: for insertTable, allow same-anchor insertText
        # (pre-table body paragraphs).  For insertPageBreak, defer all content.
        if (
            structural_kind == "insertTable"
            and kind == "insertText"
            and (
                structural_location is None
                or request[kind].get("location", {}).get("index") <= structural_location
            )
        ):
            trimmed.append(request)
            continue
        if kind in same_tab_followup_kinds:
            continue
        trimmed.append(request)
    return trimmed


def _truncate_batch_before_delete_sensitive_inserts(batch: list[dict]) -> list[dict]:
    """Split destructive same-tab rewrites into a delete-only live round.

    Some refreshed body-repair batches delete a large range and then reinsert
    content using indices from the pre-delete layout. Live Docs rightfully
    rejects those stale follow-up indices. For the live-refresh execution path,
    keep the delete requests only, then re-fetch and replan from the actual
    post-delete transport state.
    """
    delete_tabs = {
        request["deleteContentRange"]["range"].get("tabId")
        for request in batch
        if "deleteContentRange" in request
    }
    delete_tabs.discard(None)
    if not delete_tabs:
        return batch
    if not any(
        _request_tab_id(request) in delete_tabs
        and next(iter(request)) != "deleteContentRange"
        for request in batch
    ):
        return batch
    trimmed: list[dict] = []
    for request in batch:
        tab_id = _request_tab_id(request)
        if tab_id not in delete_tabs:
            trimmed.append(request)
            continue
        if "deleteContentRange" in request:
            trimmed.append(request)
    return trimmed


def _request_tab_id(request: dict) -> str | None:
    kind = next(iter(request))
    payload = request[kind]
    if kind in {"insertTable", "insertText", "insertPageBreak"}:
        return payload.get("location", {}).get("tabId")
    if kind in {
        "createParagraphBullets",
        "deleteContentRange",
        "updateParagraphStyle",
        "updateTextStyle",
    }:
        return payload.get("range", {}).get("tabId")
    return None


def _tab_ids_subset(base: Document, desired: Document) -> bool:
    base_tab_ids = {
        tab.tab_properties.tab_id
        for tab in base.tabs
        if tab.tab_properties and tab.tab_properties.tab_id
    }
    desired_tab_ids = {
        tab.tab_properties.tab_id
        for tab in desired.tabs
        if tab.tab_properties and tab.tab_properties.tab_id
    }
    return desired_tab_ids <= base_tab_ids


def _next_required_revision_id(
    response: dict,
    current_revision_id: str | None,
) -> str | None:
    write_control = response.get("writeControl")
    if not isinstance(write_control, dict):
        return current_revision_id
    next_revision_id = write_control.get("requiredRevisionId")
    if not isinstance(next_revision_id, str):
        return current_revision_id
    return next_revision_id


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

# Named styles that the markdown serializer renders as heading markers (# / ##)
# and that parse back as HEADING_1 / HEADING_2.  Normalise the raw-JSON base
# to use the same values so the reconciler doesn't generate spurious
# updateParagraphStyle requests when neither style was intentionally changed.
_MARKDOWN_STYLE_REMAP: dict[str, str] = {
    "TITLE": "HEADING_1",
    "SUBTITLE": "HEADING_2",
}


def _normalize_raw_base_para_styles(
    doc: Document,
    markdown_reference: Document | None = None,
) -> None:
    """Normalise the raw API JSON base document so it is consistent with the
    markdown-serde-derived desired document.

    Two classes of normalisation are applied:

    1. **Paragraph style reduction** — The markdown serde only ever sets
       ``namedStyleType`` on paragraph styles.  All other fields (lineSpacing,
       avoidWidowAndOrphan, spaceAbove, direction, alignment, …) come from the
       raw API as inherited or table-default values that markdown cannot express.
       Without stripping them, reconcile() generates hundreds of spurious
       updateParagraphStyle requests for every unchanged paragraph.

    2. **Inter-table separator paragraph removal** — The real Google Docs API
       automatically inserts an empty ``\\n`` paragraph between two adjacent
       tables (and after every table insertion).  The markdown serde does not
       produce these separator paragraphs, so the base would have them but the
       desired would not.  Leaving them in triggers spurious DELETE + INSERT
       sequences for unchanged callout/codeblock tables, causing insertTable
       requests to target invalid positions.

    3. **Bare empty-paragraph removal** — The markdown serializer skips any
       paragraph whose sole content is an unstyled ``\\n`` (they look identical
       to trailing paragraphs).  The raw API document may have many such empty
       paragraphs for spacing around TOC, HR, person chips, etc.  Since they
       do not appear in the desired document, the reconciler would generate
       spurious ``deleteContentRange`` requests for all of them.  Stripping
       them from the base prevents this without changing any document content
       (the real API document is unaffected — we only modify the in-memory
       base used for diffing).

    4. **TITLE / SUBTITLE → HEADING_1 / HEADING_2** — The markdown serializer
       renders TITLE as ``#`` and SUBTITLE as ``##``, which parse back as
       HEADING_1 and HEADING_2.  Normalising the base to use those same values
       prevents spurious ``updateParagraphStyle namedStyleType`` requests while
       preserving the original Google Docs style in the actual document.

    The structural content (tables, named ranges) and all index values are
    unchanged — the raw JSON is still used for accurate startIndex/endIndex
    values in deleteContentRange requests.
    """
    if not doc.tabs:
        return

    reference_tabs: dict[str, list[StructuralElement]] = {}
    if markdown_reference is not None:
        for ref_tab in markdown_reference.tabs:
            ref_tab_id = (
                ref_tab.tab_properties.tab_id if ref_tab.tab_properties else None
            )
            ref_dt = ref_tab.document_tab
            if ref_tab_id and ref_dt and ref_dt.body and ref_dt.body.content:
                reference_tabs[ref_tab_id] = ref_dt.body.content

    for tab in doc.tabs:
        dt = tab.document_tab
        if not dt:
            continue
        if dt.body and dt.body.content:
            tab_id = tab.tab_properties.tab_id if tab.tab_properties else None
            protected_empty_para_indices = _body_named_range_anchor_indices(dt, tab_id)
            preserve_after_table_starts = _preserved_separator_table_starts(
                dt.body.content,
                reference_tabs.get(tab_id, []),
            )
            # 1. Strip inter-table separator paragraphs
            dt.body.content = _strip_inter_table_separators(
                dt.body.content,
                preserve_after_table_starts,
                protected_empty_para_indices,
            )
            # 2. Strip bare empty paragraphs (invisible in markdown)
            dt.body.content = _strip_empty_body_paragraphs(
                dt.body.content,
                preserve_after_table_starts,
                protected_empty_para_indices,
            )
            # 3. Normalise paragraph styles (including TITLE/SUBTITLE mapping)
            for se in dt.body.content:
                _normalize_structural_element_para_styles(se)


def _table_text_fingerprint(se: StructuralElement) -> str | None:
    """Return a stable plain-text fingerprint for a table element."""
    if se.table is None:
        return None

    row_parts: list[str] = []
    for row in se.table.table_rows or []:
        cell_parts: list[str] = []
        for cell in row.table_cells or []:
            para_parts: list[str] = []
            for cell_se in cell.content or []:
                if cell_se.paragraph is None:
                    continue
                para_parts.append(
                    "".join(
                        pe.text_run.content or ""
                        for pe in (cell_se.paragraph.elements or [])
                        if pe.text_run
                    )
                )
            cell_parts.append("\u241e".join(para_parts))
        row_parts.append("\u241f".join(cell_parts))
    return "\u241d".join(row_parts)


def _preserved_separator_table_starts(
    raw_content: list[StructuralElement],
    reference_content: list[StructuralElement],
) -> set[int]:
    """Return raw table start indices whose following separator should remain.

    The pristine markdown document is the authoritative source for whether a
    blank paragraph after a given table is visible to users. We match raw tables
    to pristine-markdown tables by plain-text fingerprint and preserve only the
    separators that were present in that pristine markdown representation.
    """
    expected: dict[str, deque[bool]] = defaultdict(deque)
    n = len(reference_content)
    for i, se in enumerate(reference_content):
        fingerprint = _table_text_fingerprint(se)
        if fingerprint is None:
            continue
        keep_after = i + 1 < n and _is_bare_empty_paragraph(reference_content[i + 1])
        expected[fingerprint].append(keep_after)

    preserve: set[int] = set()
    for se in raw_content:
        fingerprint = _table_text_fingerprint(se)
        if fingerprint is None or se.start_index is None:
            continue
        queue = expected.get(fingerprint)
        if queue and queue.popleft():
            preserve.add(se.start_index)
    return preserve


def _strip_inter_table_separators(
    content: list[StructuralElement],
    preserve_after_table_starts: set[int],
    protected_empty_para_indices: set[int],
) -> list[StructuralElement]:
    """Remove empty paragraphs that sit between two tables in the body.

    The real Google Docs API always inserts a trailing paragraph after every
    table, so consecutive tables are separated by an empty '\\n' paragraph.
    Markdown does not preserve these separators uniformly: code-block tables
    omit them, while callout and blockquote tables keep a visible blank
    separator. To keep the raw base consistent with the markdown-deserialized
    desired document, drop only the separators that are invisible in markdown.
    """
    out: list[StructuralElement] = []
    n = len(content)
    for i, se in enumerate(content):
        if se.paragraph:
            # Check if this is a bare '\n' separator between two tables
            para = se.paragraph
            elements = para.elements or []
            text = "".join(
                e.text_run.content
                for e in elements
                if e.text_run and e.text_run.content
            )
            if text == "\n":
                if (
                    se.start_index in protected_empty_para_indices
                    or se.end_index in protected_empty_para_indices
                ):
                    out.append(se)
                    continue
                # Look for a table before and after this paragraph
                prev_is_table = any(out) and out[-1].table is not None
                next_is_table = i + 1 < n and content[i + 1].table is not None
                if prev_is_table and next_is_table:
                    prev_start = out[-1].start_index
                    if (
                        prev_start is not None
                        and prev_start in preserve_after_table_starts
                    ):
                        out.append(se)
                        continue
                    continue  # skip this inter-table separator
        out.append(se)
    return out


def _is_bare_empty_paragraph(se: StructuralElement) -> bool:
    """Return True if se is a bare unstyled '\\n'-only paragraph.

    These are invisible in the markdown representation — _to_markdown.py
    skips them as trailing paragraphs — so they must be stripped from the
    base to avoid spurious deleteContentRange requests.
    """
    if se.paragraph is None:
        return False
    elements = se.paragraph.elements or []
    if not elements:
        return True
    if len(elements) == 1:
        tr = elements[0].text_run
        if tr is not None and tr.content == "\n":
            ts = tr.text_style
            return ts is None or not any(
                getattr(ts, f, None)
                for f in (
                    "bold",
                    "italic",
                    "underline",
                    "strikethrough",
                    "link",
                    "weighted_font_family",
                    "foreground_color",
                    "background_color",
                    "font_size",
                )
            )
    return False


def _strip_empty_body_paragraphs(
    content: list[StructuralElement],
    preserve_after_table_starts: set[int],
    protected_empty_para_indices: set[int],
) -> list[StructuralElement]:
    """Remove bare empty paragraphs that immediately precede a table.

    The Google Docs API automatically inserts a bare-\\n paragraph before
    every insertTable call.  These pre-table paragraphs are invisible in the
    markdown representation and cannot be deleted via deleteContentRange.
    Stripping them from the base keeps it consistent with the desired
    document and avoids spurious deleteContentRange requests.

    Bare-\\n paragraphs that do NOT precede a table are left in place so that
    the reconciler can generate delete requests for them.

    The reconciler handles the trailing paragraph via explicit index arithmetic.
    """
    result: list[StructuralElement] = []
    n = len(content)
    for i, se in enumerate(content):
        if _is_bare_empty_paragraph(se):
            if (
                se.start_index in protected_empty_para_indices
                or se.end_index in protected_empty_para_indices
            ):
                result.append(se)
                continue
            next_is_table = i + 1 < n and content[i + 1].table is not None
            if next_is_table:
                prev_is_table = bool(result) and result[-1].table is not None
                prev_start = result[-1].start_index if prev_is_table else None
                if prev_start is not None and prev_start in preserve_after_table_starts:
                    result.append(se)
                    continue
                continue
        result.append(se)
    return result


def _body_named_range_anchor_indices(
    document_tab: DocumentTab,
    tab_id: str | None,
) -> set[int]:
    indices: set[int] = set()
    for grouped in (document_tab.named_ranges or {}).values():
        for named_range in grouped.named_ranges or []:
            for range_ in named_range.ranges or []:
                if range_.segment_id:
                    continue
                if (
                    tab_id is not None
                    and range_.tab_id
                    and str(range_.tab_id) != tab_id
                ):
                    continue
                if range_.start_index is not None:
                    indices.add(range_.start_index)
                if range_.end_index is not None:
                    indices.add(range_.end_index)
    return indices


def _normalize_structural_element_para_styles(se: StructuralElement) -> None:
    """Recursively strip non-markdown paragraph style fields from a StructuralElement."""
    if se.paragraph:
        _normalize_paragraph(se.paragraph)
    elif se.table:
        for row in se.table.table_rows or []:
            for cell in row.table_cells or []:
                _normalize_table_cell_style(cell)
                for cell_se in cell.content or []:
                    _normalize_structural_element_para_styles(cell_se)


def _normalize_table_cell_style(cell: TableCell) -> None:
    """Normalize table cell backgroundColor by round-tripping through hex.

    The Google Docs API returns truncated float values for RGB colors
    (e.g. 0.81960785) while our hex_to_rgb computes full Python float
    precision (0.8196078431372549).  Round-tripping through hex normalizes
    both representations to the same float values so the reconciler does
    not generate spurious updateTableCellStyle backgroundColor requests.
    """
    style = cell.table_cell_style
    if not style or not style.background_color:
        return
    hex_val = optional_color_to_hex(style.background_color)
    if hex_val:
        style.background_color = hex_to_optional_color(hex_val)


def _normalize_paragraph(para: Paragraph) -> None:
    """Reduce paragraph style and text run styles in-place for markdown consistency.

    Two normalisations:

    1. **Paragraph style reduction** — The markdown serde only sets
       ``namedStyleType`` on paragraph styles.  All other fields are stripped.

    2. **Text run normalisation** — Strip non-markdown text run style fields
       (fontSize, foregroundColor, backgroundColor, etc.) that the markdown
       serde cannot express.  Also replace U+000B (vertical tab / line break)
       in run content with a plain space to match what mistletoe produces when
       re-parsing the serialized markdown.
    """
    ps = para.paragraph_style
    if ps:
        raw = ps.named_style_type
        style_val = raw.value if hasattr(raw, "value") else (raw or "")
        # TITLE/SUBTITLE → HEADING_1/HEADING_2: markdown renders them as #/##
        # which parse back as HEADING_1/HEADING_2, so normalise the base too.
        remapped = _MARKDOWN_STYLE_REMAP.get(style_val, style_val) or style_val
        para.paragraph_style = ParagraphStyle(named_style_type=remapped)

    new_elements: list[ParagraphElement] = []
    for elem in para.elements or []:
        tr = elem.text_run
        if not tr:
            new_elements.append(elem)
            continue
        # Replace vertical tab with a space so the base fingerprint matches
        # what mistletoe produces when parsing the serialized markdown.
        if tr.content and "\u000b" in tr.content:
            tr.content = tr.content.replace("\u000b", " ")
        content = tr.content or ""
        # If a run embeds the paragraph-terminal '\n' in the middle of other
        # text (e.g. "Recruit41 Playbook\n" as one bold run), split it into a
        # styled text part and an unstyled '\n' part.  The markdown serde
        # always produces a separate bare '\n' run, so splitting here keeps
        # the run count equal and avoids falling into positional comparison.
        if content.endswith("\n") and len(content) > 1:
            text_part = content[:-1]
            si = elem.start_index
            ei = elem.end_index
            text_end = (si + len(text_part)) if si is not None else None
            text_elem = ParagraphElement(
                text_run=TextRun(content=text_part, text_style=tr.text_style),
                start_index=si,
                end_index=text_end,
            )
            nl_elem = ParagraphElement(
                text_run=TextRun(content="\n", text_style=None),
                start_index=text_end,
                end_index=ei,
            )
            new_elements.append(text_elem)
            new_elements.append(nl_elem)
            # Normalise the text part's style in-place below
            tr = text_elem.text_run
            assert tr is not None
        else:
            new_elements.append(elem)
        # The trailing '\n' run always has no style in the markdown-serde
        # desired document.  Strip all styles on '\n'-only runs.
        if content == "\n":
            tr.text_style = None
            continue
        # Strip non-markdown text run style fields from the base so that
        # matched paragraphs don't generate spurious updateTextStyle requests.
        if tr.text_style:
            ts = tr.text_style
            tr.text_style = TextStyle(
                bold=ts.bold,
                italic=ts.italic,
                strikethrough=ts.strikethrough,
                underline=ts.underline,
                link=ts.link,
                weighted_font_family=ts.weighted_font_family,
            )
    para.elements = new_elements


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
