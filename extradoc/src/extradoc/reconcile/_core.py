"""Core reconcile, verify, and reindex_document functions."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from extradoc.api_types import DeferredID, Request, TabID
from extradoc.api_types._generated import (
    BatchUpdateDocumentRequest,
    Body,
    Document,
    Footer,
    Header,
    StructuralElement,
    Tab,
)
from extradoc.mock.api import MockGoogleDocsAPI
from extradoc.mock.reindex import reindex_and_normalize_all_tabs
from extradoc.reconcile._alignment import (
    align_structural_elements,
    align_tabs,
)
from extradoc.reconcile._comparators import documents_match
from extradoc.reconcile._exceptions import ReconcileError
from extradoc.reconcile._extractors import Segment, extract_segments
from extradoc.reconcile._generators import (
    _make_add_document_tab,
    _make_create_footer,
    _make_create_header,
    _make_delete_footer,
    _make_delete_header,
    _make_delete_tab,
    _make_update_document_tab_properties,
    generate_requests,
)


def reindex_document(doc: Document) -> Document:
    """Reindex a Document using mock/reindex.py logic.

    Converts to dict, runs reindex_and_normalize_all_tabs(), converts back.
    Allows tests to create Documents without worrying about indices.
    """
    doc_dict = doc.model_dump(by_alias=True, exclude_none=True)
    reindex_and_normalize_all_tabs(doc_dict)
    return Document.model_validate(doc_dict)


def resolve_deferred_ids(
    prior_responses: list[dict[str, Any]],
    batch: BatchUpdateDocumentRequest,
) -> BatchUpdateDocumentRequest:
    """Resolve DeferredID placeholders using prior batch responses.

    Walks the batch recursively, replacing DeferredID objects with real ID
    strings extracted from prior batch responses.

    Args:
        prior_responses: List of batch response dicts from API/mock
        batch: The batch with possible DeferredID objects

    Returns:
        New BatchUpdateDocumentRequest with all IDs resolved

    Raises:
        ReconcileError: If a DeferredID cannot be resolved

    Example:
        # Execute batch 0
        response_0 = api.batch_update(doc_id, batches[0])

        # Resolve and execute batch 1
        batch_1_resolved = resolve_deferred_ids([response_0], batches[1])
        response_1 = api.batch_update(doc_id, batch_1_resolved)
    """
    id_cache: dict[str, str] = {}

    def _extract_path(data: Any, path: str) -> str:
        """Extract value from nested dict using dot notation."""
        keys = path.split(".")
        current = data
        for key in keys:
            if not isinstance(current, dict) or key not in current:
                raise ReconcileError(
                    f"Cannot resolve path '{path}': key '{key}' not found in {current}"
                )
            current = current[key]
        if not isinstance(current, str):
            raise ReconcileError(
                f"Path '{path}' did not resolve to a string: {current}"
            )
        return current

    def _is_deferred_id_dict(val: Any) -> bool:
        """Check if a value is a dict representation of DeferredID."""
        return (
            isinstance(val, dict)
            and "placeholder" in val
            and "batch_index" in val
            and "request_index" in val
            and "response_path" in val
        )

    def _resolve_value(val: Any) -> Any:
        """Recursively resolve DeferredID objects."""
        if isinstance(val, DeferredID):
            # Direct DeferredID object (shouldn't happen after dump, but handle it)
            deferred = val
        elif _is_deferred_id_dict(val):
            # Dict representation of DeferredID (from model_dump)
            deferred = DeferredID(
                placeholder=val["placeholder"],
                batch_index=val["batch_index"],
                request_index=val["request_index"],
                response_path=val["response_path"],
            )
        else:
            # Not a DeferredID - recurse into structure
            if isinstance(val, dict):
                return {k: _resolve_value(v) for k, v in val.items()}
            if isinstance(val, list):
                return [_resolve_value(item) for item in val]
            return val

        # Resolve the DeferredID
        # Check cache first
        if deferred.placeholder in id_cache:
            return id_cache[deferred.placeholder]

        # Validate batch index
        if deferred.batch_index >= len(prior_responses):
            raise ReconcileError(
                f"DeferredID {deferred.placeholder} references batch {deferred.batch_index}, "
                f"but only {len(prior_responses)} prior responses available"
            )

        # Extract from response
        batch_resp = prior_responses[deferred.batch_index]
        replies = batch_resp.get("replies", [])

        if deferred.request_index >= len(replies):
            raise ReconcileError(
                f"DeferredID {deferred.placeholder} references request {deferred.request_index}, "
                f"but batch {deferred.batch_index} only has {len(replies)} replies"
            )

        reply = replies[deferred.request_index]
        real_id = _extract_path(reply, deferred.response_path)

        id_cache[deferred.placeholder] = real_id
        return real_id

    # Convert to dict, resolve, convert back
    batch_dict = batch.model_dump(by_alias=True, exclude_none=True)
    resolved_dict = _resolve_value(batch_dict)
    return BatchUpdateDocumentRequest.model_validate(resolved_dict)


def reconcile(base: Document, desired: Document) -> list[BatchUpdateDocumentRequest]:
    """Diff two Documents and produce a list of BatchUpdateDocumentRequests.

    Returns multiple batches that must be executed sequentially with ID resolution
    between batches. Uses DFS traversal to handle arbitrary nesting depth.

    Both documents must have valid indices. Use reindex_document() if needed.

    Args:
        base: The current document state
        desired: The target document state

    Returns:
        List of BatchUpdateDocumentRequest objects, ordered by dependency.
        Execute batch 0, resolve IDs, execute batch 1, resolve IDs, etc.

    Example:
        batches = reconcile(base, desired)
        response_0 = api.batch_update(doc_id, batches[0])
        batch_1 = resolve_deferred_ids([response_0], batches[1])
        response_1 = api.batch_update(doc_id, batch_1)
    """
    return _Reconciler().run(base, desired)


class _Reconciler:
    """Accumulates batchUpdate requests during a single reconcile traversal.

    Holds the two pieces of mutable state that the DFS needs:
      - batches:    dict[batch_index → list[request_dict]]
      - id_counter: monotonically-increasing counters for placeholder names

    A fresh instance is created for every public reconcile() call so there is
    no shared/global state and the class is trivially reentrant.
    """

    def __init__(self) -> None:
        # Maps batch_index → ordered list of request dicts
        self._batches: dict[int, list[dict[str, Any]]] = defaultdict(list)
        # Counters for generating unique placeholder IDs ("header_1", "tab_2", …)
        self._id_counter: dict[str, int] = {}

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(
        self, base: Document, desired: Document
    ) -> list[BatchUpdateDocumentRequest]:
        """Execute the reconcile traversal and return ordered batches."""
        base_tabs = base.tabs or []
        desired_tabs = desired.tabs or []

        tab_align = align_tabs(base_tabs, desired_tabs)

        # Process deleted tabs (batch 0 - no dependencies)
        for tab in tab_align.deleted:
            tab_id = tab.tab_properties.tab_id if tab.tab_properties else None
            if tab_id:
                self._batches[0].append(_make_delete_tab(tab_id))

        # Process matched tabs (check property changes + content)
        for base_tab, desired_tab in tab_align.matched:
            tab_id = base_tab.tab_properties.tab_id if base_tab.tab_properties else None

            # Property updates (batch 0)
            prop_req = _get_tab_property_update(base_tab, desired_tab)
            if prop_req:
                self._batches[0].append(prop_req)

            # Reconcile tab content (starting at batch 0)
            self._reconcile_tab(base_tab, desired_tab, current_batch=0, tab_id=tab_id)

        # Process added tabs (DFS: create tab, then populate)
        for tab in tab_align.added:
            self._reconcile_new_tab(tab, current_batch=0)

        # Convert to BatchUpdateDocumentRequest objects
        result: list[BatchUpdateDocumentRequest] = []
        for i in sorted(self._batches.keys()):
            request_models = [Request.model_validate(r) for r in self._batches[i]]
            result.append(
                BatchUpdateDocumentRequest(
                    requests=request_models or None, writeControl=None
                )
            )
        return result

    # ------------------------------------------------------------------
    # DFS helpers
    # ------------------------------------------------------------------

    def _reconcile_tab(
        self,
        base_tab: Tab,
        desired_tab: Tab,
        current_batch: int,
        tab_id: TabID,
    ) -> None:
        base_segments = extract_segments(base_tab)
        desired_segments = extract_segments(desired_tab)

        # Extract desired lists for bullet preset inference
        desired_lists = (
            desired_tab.document_tab.lists if desired_tab.document_tab else None
        )

        all_segment_ids = sorted(
            set(base_segments.keys()) | set(desired_segments.keys())
        )

        for seg_id in all_segment_ids:
            base_seg = base_segments.get(seg_id)
            desired_seg = desired_segments.get(seg_id)

            if base_seg and desired_seg:
                # Matched segment: diff content (stay in current batch)
                self._reconcile_segment(
                    base_seg,
                    desired_seg,
                    current_batch,
                    base_seg.segment_id,
                    tab_id,
                    desired_lists,
                )
            elif desired_seg and not base_seg:
                # Added segment: create it (current batch), populate (next batch)
                # Reject new header/footer creation for multi-section tabs:
                # createHeader/createFooter always omits sectionBreakLocation, so the
                # header/footer would be applied to the document style (all sections).
                # In a multi-section document this is almost certainly wrong.
                source = desired_seg.source
                if isinstance(source, Header | Footer) and _tab_has_multiple_sections(
                    base_tab
                ):
                    raise ReconcileError(
                        "Cannot create a new header or footer in a multi-section tab. "
                        "The createHeader/createFooter API always omits "
                        "sectionBreakLocation, which applies the header/footer to all "
                        "sections. Use the Google Docs API directly to create "
                        "section-specific headers or footers."
                    )
                self._reconcile_new_segment(
                    desired_seg, current_batch, tab_id, desired_lists
                )
            elif base_seg and not desired_seg:
                # Deleted segment: delete it (current batch)
                delete_req = _delete_segment_request(base_seg, tab_id)
                if delete_req:
                    self._batches[current_batch].append(delete_req)

    def _reconcile_segment(
        self,
        base_seg: Segment,
        desired_seg: Segment,
        current_batch: int,
        segment_id: str | DeferredID | None,
        tab_id: TabID,
        desired_lists: dict[str, Any] | None = None,
    ) -> None:
        alignment = align_structural_elements(base_seg.content, desired_seg.content)
        actual_segment_id = (
            segment_id if segment_id is not None else base_seg.segment_id
        )
        requests = generate_requests(
            alignment, actual_segment_id, tab_id, desired_lists
        )
        self._batches[current_batch].extend(requests)

    def _reconcile_new_segment(
        self,
        desired_seg: Segment,
        current_batch: int,
        tab_id: TabID,
        desired_lists: dict[str, Any] | None = None,
    ) -> None:
        """Create a new segment and populate its content using DFS.

        Creates the segment in current_batch, then populates content in next batch.
        Uses DeferredID to handle the ID assignment problem.
        """
        source = desired_seg.source

        create_req: dict[str, Any] | None = None
        response_path: str | None = None
        placeholder_prefix: str | None = None
        segment_type: type[Header] | type[Footer] | None = None

        if isinstance(source, Header):
            create_req = _make_create_header("DEFAULT", tab_id)
            response_path = "createHeader.headerId"
            placeholder_prefix = "header"
            segment_type = Header
        elif isinstance(source, Footer):
            create_req = _make_create_footer("DEFAULT", tab_id)
            response_path = "createFooter.footerId"
            placeholder_prefix = "footer"
            segment_type = Footer

        if (
            not create_req
            or not response_path
            or not placeholder_prefix
            or not segment_type
        ):
            # Body/footnote - can't create, skip
            return

        # request_index is the position within this batch's reply list
        request_index = len(self._batches[current_batch])
        self._batches[current_batch].append(create_req)

        self._id_counter[placeholder_prefix] = (
            self._id_counter.get(placeholder_prefix, 0) + 1
        )
        placeholder = f"{placeholder_prefix}_{self._id_counter[placeholder_prefix]}"

        segment_id = DeferredID(
            placeholder=placeholder,
            batch_index=current_batch,
            request_index=request_index,
            response_path=response_path,
        )

        # Populate content in NEXT batch (new header/footer starts with just "\n")
        base_seg = _create_initial_segment(segment_type)
        self._reconcile_segment(
            base_seg, desired_seg, current_batch + 1, segment_id, tab_id, desired_lists
        )

    def _reconcile_new_tab(self, tab: Tab, current_batch: int) -> None:
        """Create a new tab and populate its content using DFS.

        Creates the tab in current_batch, then populates content in next batch.
        Uses DeferredID to handle the ID assignment problem.
        """
        if not tab.tab_properties:
            return

        title = tab.tab_properties.title or "Untitled Tab"
        index = tab.tab_properties.index

        create_req = _make_add_document_tab(title=title, index=index)

        # request_index is the position within this batch's reply list
        request_index = len(self._batches[current_batch])
        self._batches[current_batch].append(create_req)

        self._id_counter["tab"] = self._id_counter.get("tab", 0) + 1
        placeholder = f"tab_{self._id_counter['tab']}"

        tab_id = DeferredID(
            placeholder=placeholder,
            batch_index=current_batch,
            request_index=request_index,
            response_path="addDocumentTab.tabProperties.tabId",
        )

        # Populate tab content in NEXT batch
        desired_lists = tab.document_tab.lists if tab.document_tab else None
        for _seg_id, desired_seg in extract_segments(tab).items():
            if isinstance(desired_seg.source, Body):
                # Body always exists after tab creation; diff against initial state
                base_seg = _create_initial_body_segment()
                self._reconcile_segment(
                    base_seg,
                    desired_seg,
                    current_batch + 1,
                    None,
                    tab_id,
                    desired_lists,
                )
            else:
                self._reconcile_new_segment(
                    desired_seg, current_batch + 1, tab_id, desired_lists
                )


# ------------------------------------------------------------------
# Stateless helpers (no accumulator needed)
# ------------------------------------------------------------------


def _get_tab_property_update(base_tab: Tab, desired_tab: Tab) -> dict[str, Any] | None:
    """Check if tab properties changed and return update request if needed."""
    base_props = base_tab.tab_properties
    desired_props = desired_tab.tab_properties

    if not base_props or not desired_props:
        return None

    tab_id = base_props.tab_id
    if not tab_id:
        return None

    title_changed = base_props.title != desired_props.title
    index_changed = base_props.index != desired_props.index

    if not (title_changed or index_changed):
        return None

    return _make_update_document_tab_properties(
        tab_id=tab_id,
        title=desired_props.title if title_changed else None,
        index=desired_props.index if index_changed else None,
    )


def _delete_segment_request(segment: Segment, tab_id: TabID) -> dict[str, Any] | None:
    """Generate a delete request for a segment, or None if it can't be deleted."""
    source = segment.source
    seg_id = segment.segment_id

    if isinstance(source, Header) and seg_id:
        return _make_delete_header(seg_id, tab_id)
    if isinstance(source, Footer) and seg_id:
        return _make_delete_footer(seg_id, tab_id)

    # Body always exists (can't be deleted)
    # Footnotes are deleted by removing footnoteReference (element-level, Phase 4+)
    return None


def _tab_has_multiple_sections(tab: Tab) -> bool:
    """Return True if the tab's body contains more than one section break.

    A document with a single section has exactly one sectionBreak (at the very
    beginning of the body). Each additional section adds another sectionBreak.
    """
    doc_tab = tab.document_tab
    if not doc_tab or not doc_tab.body:
        return False
    count = sum(
        1 for se in (doc_tab.body.content or []) if se.section_break is not None
    )
    return count > 1


def _create_initial_body_segment() -> Segment:
    """Return a Segment with the initial content a newly-created tab body has.

    A new tab starts with a sectionBreak (index 0-1) followed by a single
    paragraph with \\n (index 1-2).  Indices must be set so that downstream
    request generators insert content at index 1 (body min index) rather
    than 0.
    """
    initial_content = [
        StructuralElement.model_validate(
            {"sectionBreak": {}, "startIndex": 0, "endIndex": 1}
        ),
        StructuralElement.model_validate(
            {
                "paragraph": {"elements": [{"textRun": {"content": "\n"}}]},
                "startIndex": 1,
                "endIndex": 2,
            }
        ),
    ]
    source = Body.model_validate({"content": initial_content})
    return Segment(source=source)


def _create_initial_segment(segment_type: type[Header] | type[Footer]) -> Segment:
    """Return a Segment with the initial content a newly-created header/footer has (just \\n)."""
    initial_content = [
        StructuralElement.model_validate(
            {"paragraph": {"elements": [{"textRun": {"content": "\n"}}]}}
        )
    ]
    source: Header | Footer
    if segment_type is Header:
        source = Header.model_validate({"content": initial_content})
    else:
        source = Footer.model_validate({"content": initial_content})
    return Segment(source=source)


def verify(
    base: Document,
    batches: list[BatchUpdateDocumentRequest],
    desired: Document,
) -> tuple[bool, list[str]]:
    """Execute batches sequentially with ID resolution and compare with desired.

    Args:
        base: The original document
        batches: List of batch update requests to apply sequentially
        desired: The expected result

    Returns:
        (match, list_of_differences)
    """
    mock = MockGoogleDocsAPI(base)
    responses: list[dict[str, Any]] = []

    for i, batch in enumerate(batches):
        if i > 0:
            batch = resolve_deferred_ids(responses, batch)

        if batch.requests:
            response = mock.batch_update(batch)
            responses.append(response.model_dump(by_alias=True, exclude_none=True))

    actual_dict = mock.get().model_dump(by_alias=True, exclude_none=True)
    desired_dict = desired.model_dump(by_alias=True, exclude_none=True)

    return documents_match(actual_dict, desired_dict)
