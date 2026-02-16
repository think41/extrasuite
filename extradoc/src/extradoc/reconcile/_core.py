"""Core reconcile, verify, and reindex_document functions."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from extradoc.api_types import DeferredID, Request, TabID
from extradoc.api_types._generated import (
    BatchUpdateDocumentRequest,
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

# Module-level list to collect requests during DFS traversal
# Each entry is (batch_index, request_dict)
_requests: list[tuple[int, dict[str, Any]]] = []

# Counter for generating unique placeholder IDs
_id_counter: dict[str, int] = {}


# Import ReconcileError here to avoid circular import
class ReconcileError(Exception):
    """Raised when reconciliation encounters an unsupported or invalid change."""


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
    global _requests, _id_counter
    _requests = []
    _id_counter = {}

    base_tabs = base.tabs or []
    desired_tabs = desired.tabs or []

    tab_align = align_tabs(base_tabs, desired_tabs)

    # Process deleted tabs (batch 0 - no dependencies)
    for tab in tab_align.deleted:
        tab_id = tab.tab_properties.tab_id if tab.tab_properties else None
        if tab_id:
            _requests.append((0, _make_delete_tab(tab_id)))

    # Process matched tabs (check property changes + content)
    for base_tab, desired_tab in tab_align.matched:
        tab_id = base_tab.tab_properties.tab_id if base_tab.tab_properties else None

        # Property updates (batch 0)
        prop_req = _get_tab_property_update(base_tab, desired_tab)
        if prop_req:
            _requests.append((0, prop_req))

        # Reconcile tab content (starting at batch 0)
        _reconcile_tab(base_tab, desired_tab, current_batch=0, tab_id=tab_id)

    # Process added tabs (DFS: create tab, then populate)
    for tab in tab_align.added:
        _reconcile_new_tab(tab, current_batch=0)

    # Group requests by batch index
    batches_dict: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for batch_idx, req in _requests:
        batches_dict[batch_idx].append(req)

    # Convert to BatchUpdateDocumentRequest objects
    result: list[BatchUpdateDocumentRequest] = []
    for i in sorted(batches_dict.keys()):
        request_models = [Request.model_validate(r) for r in batches_dict[i]]
        result.append(
            BatchUpdateDocumentRequest(
                requests=request_models or None, writeControl=None
            )
        )
    return result


def _reconcile_tab(
    base_tab: Tab,
    desired_tab: Tab,
    current_batch: int,
    tab_id: TabID,
) -> None:
    """Reconcile a single tab pair using DFS.

    Args:
        base_tab: Current tab state
        desired_tab: Desired tab state
        current_batch: Which batch are WE in?
        tab_id: Current tab context (may be DeferredID for new tabs)
    """
    base_segments = extract_segments(base_tab)
    desired_segments = extract_segments(desired_tab)

    # Match segments by ID
    all_segment_ids = set(base_segments.keys()) | set(desired_segments.keys())

    for seg_id in all_segment_ids:
        base_seg = base_segments.get(seg_id)
        desired_seg = desired_segments.get(seg_id)

        if base_seg and desired_seg:
            # Matched segment: diff content (stay in current batch)
            # Use base_seg.segment_id (which is None for body, real ID for headers/footers)
            _reconcile_segment(
                base_seg, desired_seg, current_batch, base_seg.segment_id, tab_id
            )

        elif desired_seg and not base_seg:
            # Added segment: create it (current batch), populate (next batch)
            _reconcile_new_segment(desired_seg, current_batch, tab_id)

        elif base_seg and not desired_seg:
            # Deleted segment: delete it (current batch)
            delete_req = _delete_segment_request(base_seg, tab_id)
            if delete_req:
                _requests.append((current_batch, delete_req))


def _reconcile_segment(
    base_seg: Segment,
    desired_seg: Segment,
    current_batch: int,
    segment_id: str | DeferredID | None,
    tab_id: TabID,
) -> None:
    """Reconcile content within a single segment using DFS.

    Args:
        base_seg: Current segment state
        desired_seg: Desired segment state
        current_batch: Which batch are WE in?
        segment_id: Segment ID to use in requests (overrides base_seg.segment_id if provided)
        tab_id: Current tab context (may be DeferredID)
    """
    alignment = align_structural_elements(base_seg.content, desired_seg.content)
    # Use provided segment_id if given, otherwise use base_seg.segment_id
    actual_segment_id = segment_id if segment_id is not None else base_seg.segment_id
    requests = generate_requests(alignment, actual_segment_id, tab_id)
    for req in requests:
        _requests.append((current_batch, req))


def _create_segment_request(
    segment: Segment, tab_id: str | None
) -> dict[str, Any] | None:
    """Generate a create request for a segment.

    Args:
        segment: The segment to create
        tab_id: Tab ID

    Returns:
        Create request dict, or None if segment can't be created (e.g., body, footnote)
    """
    source = segment.source

    if isinstance(source, Header):
        # Create header with DEFAULT type
        return _make_create_header("DEFAULT", tab_id)
    if isinstance(source, Footer):
        # Create footer with DEFAULT type
        return _make_create_footer("DEFAULT", tab_id)

    # Body always exists (can't be created)
    # Footnotes are created via createFootnote, which is element-level (Phase 4+)
    return None


def _delete_segment_request(segment: Segment, tab_id: TabID) -> dict[str, Any] | None:
    """Generate a delete request for a segment.

    Args:
        segment: The segment to delete
        tab_id: Tab ID

    Returns:
        Delete request dict, or None if segment can't be deleted (e.g., body)
    """
    source = segment.source
    seg_id = segment.segment_id

    if isinstance(source, Header) and seg_id:
        return _make_delete_header(seg_id, tab_id)
    if isinstance(source, Footer) and seg_id:
        return _make_delete_footer(seg_id, tab_id)

    # Body always exists (can't be deleted)
    # Footnotes are deleted by removing footnoteReference (element-level, Phase 4+)
    return None


def _create_initial_segment(segment_type: type[Header] | type[Footer]) -> Segment:
    """Create a segment with initial empty content (just \\n).

    When the API creates a new header/footer, it initializes it with a single
    paragraph containing just a newline character. This function recreates that
    initial state for diffing purposes.

    Args:
        segment_type: Header or Footer class

    Returns:
        Segment with initial content (ID is None, as it's passed separately to reconcile_segment)
    """
    # Create initial content: single paragraph with "\n"
    # Use dict construction to avoid mypy issues with optional fields
    initial_content_dict = [
        {"paragraph": {"elements": [{"textRun": {"content": "\n"}}]}}
    ]

    initial_content = [
        StructuralElement.model_validate(se) for se in initial_content_dict
    ]

    # Create the segment source without setting the ID
    # The ID is passed separately to _reconcile_segment as segment_id parameter
    source: Header | Footer
    if segment_type is Header:
        source = Header.model_validate({"content": initial_content})
    else:  # Footer
        source = Footer.model_validate({"content": initial_content})

    return Segment(source=source)


def _reconcile_new_segment(
    desired_seg: Segment,
    current_batch: int,
    tab_id: TabID,
) -> None:
    """Create a new segment and populate its content using DFS.

    Creates the segment in current_batch, then populates content in next batch.
    Uses DeferredID to handle the ID assignment problem.

    Args:
        desired_seg: The segment to create
        current_batch: Which batch creates the segment
        tab_id: Current tab context (may be DeferredID)
    """
    source = desired_seg.source

    # Generate creation request
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

    # Add creation request to current batch
    request_index = len(_requests)
    _requests.append((current_batch, create_req))

    # Generate unique placeholder ID
    _id_counter[placeholder_prefix] = _id_counter.get(placeholder_prefix, 0) + 1
    placeholder = f"{placeholder_prefix}_{_id_counter[placeholder_prefix]}"

    # Create DeferredID for this segment
    segment_id = DeferredID(
        placeholder=placeholder,
        batch_index=current_batch,
        request_index=request_index,
        response_path=response_path,
    )

    # Populate content in NEXT batch
    # New headers/footers are created with initial "\n" content
    # Diff desired content against that initial state
    base_seg = _create_initial_segment(segment_type)
    # Use segment_id (DeferredID) for location context in generated requests
    _reconcile_segment(base_seg, desired_seg, current_batch + 1, segment_id, tab_id)


def _reconcile_new_tab(tab: Tab, current_batch: int) -> None:
    """Create a new tab and populate its content using DFS.

    Creates the tab in current_batch, then populates content in next batch.
    Uses DeferredID to handle the ID assignment problem.

    Args:
        tab: The tab to create
        current_batch: Which batch creates the tab
    """
    if not tab.tab_properties:
        return

    title = tab.tab_properties.title or "Untitled Tab"
    index = tab.tab_properties.index

    # Generate creation request
    create_req = _make_add_document_tab(title=title, index=index)

    # Add creation request to current batch
    request_index = len(_requests)
    _requests.append((current_batch, create_req))

    # Generate unique placeholder ID
    _id_counter["tab"] = _id_counter.get("tab", 0) + 1
    placeholder = f"tab_{_id_counter['tab']}"

    # Create DeferredID for this tab
    tab_id = DeferredID(
        placeholder=placeholder,
        batch_index=current_batch,
        request_index=request_index,
        response_path="addDocumentTab.tabProperties.tabId",
    )

    # Populate tab content in NEXT batch
    # Use empty base tab (new tab has no content yet)
    desired_segments = extract_segments(tab)

    # Process all segments in the new tab
    for _seg_id, desired_seg in desired_segments.items():
        # All segments are "new" (no base)
        _reconcile_new_segment(desired_seg, current_batch + 1, tab_id)


def _get_tab_property_update(base_tab: Tab, desired_tab: Tab) -> dict[str, Any] | None:
    """Check if tab properties changed and return update request if needed.

    Args:
        base_tab: Current tab
        desired_tab: Desired tab

    Returns:
        updateDocumentTabProperties request dict, or None if no changes
    """
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
    base_dict = base.model_dump(by_alias=True, exclude_none=True)
    mock = MockGoogleDocsAPI(base_dict)
    responses: list[dict[str, Any]] = []

    # Execute batches sequentially
    for i, batch in enumerate(batches):
        # Resolve DeferredIDs if this is not the first batch
        if i > 0:
            batch = resolve_deferred_ids(responses, batch)

        # Convert Request models to dicts
        request_dicts: list[dict[str, Any]] = []
        for req in batch.requests or []:
            req_dict = req.model_dump(by_alias=True, exclude_none=True)
            request_dicts.append(req_dict)

        if request_dicts:
            response = mock.batch_update(request_dicts)
            responses.append(response)

    actual_dict = mock.get()
    desired_dict = desired.model_dump(by_alias=True, exclude_none=True)

    return documents_match(actual_dict, desired_dict)
