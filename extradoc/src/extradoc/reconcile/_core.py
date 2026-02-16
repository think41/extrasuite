"""Core reconcile, verify, and reindex_document functions."""

from __future__ import annotations

from typing import Any

from extradoc.api_types._generated import (
    BatchUpdateDocumentRequest,
    Document,
    Footer,
    Header,
    Request,
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
    _make_create_footer,
    _make_create_header,
    _make_delete_footer,
    _make_delete_header,
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


def reconcile(base: Document, desired: Document) -> BatchUpdateDocumentRequest:
    """Diff two Documents and produce a BatchUpdateDocumentRequest.

    Both documents must have valid indices. Use reindex_document() if needed.

    Args:
        base: The current document state
        desired: The target document state

    Returns:
        BatchUpdateDocumentRequest that transforms base into desired
    """
    all_requests: list[dict[str, Any]] = []

    base_tabs = base.tabs or []
    desired_tabs = desired.tabs or []

    tab_align = align_tabs(base_tabs, desired_tabs)

    # Phase 4 will handle added/deleted tabs
    # For now, process matched tabs only

    for base_tab, desired_tab in tab_align.matched:
        tab_id = base_tab.tab_properties.tab_id if base_tab.tab_properties else None
        tab_requests = _reconcile_tab(base_tab, desired_tab, tab_id)
        all_requests.extend(tab_requests)

    # Convert request dicts to Request models
    requests = []
    for req_dict in all_requests:
        requests.append(Request.model_validate(req_dict))

    return BatchUpdateDocumentRequest(requests=requests or None, writeControl=None)


def _reconcile_tab(
    base_tab: Tab, desired_tab: Tab, tab_id: str | None
) -> list[dict[str, Any]]:
    """Reconcile a single tab pair."""
    requests: list[dict[str, Any]] = []

    base_segments = extract_segments(base_tab)
    desired_segments = extract_segments(desired_tab)

    # Match segments by ID
    all_segment_ids = set(base_segments.keys()) | set(desired_segments.keys())

    for seg_id in all_segment_ids:
        base_seg = base_segments.get(seg_id)
        desired_seg = desired_segments.get(seg_id)

        if base_seg and desired_seg:
            # Matched segment: diff content
            seg_requests = _reconcile_segment(base_seg, desired_seg, tab_id)
            requests.extend(seg_requests)
        elif desired_seg and not base_seg:
            # Added segment: create it, then populate content
            create_req = _create_segment_request(desired_seg, tab_id)
            if create_req:
                requests.append(create_req)
            # After creation, populate content
            # Note: Headers/footers are created with initial "\n" content
            # We need to diff against that initial state
            seg_requests = _reconcile_new_segment(desired_seg, tab_id)
            requests.extend(seg_requests)
        elif base_seg and not desired_seg:
            # Deleted segment: delete it
            delete_req = _delete_segment_request(base_seg, tab_id)
            if delete_req:
                requests.append(delete_req)

    return requests


def _reconcile_segment(
    base_seg: Segment,
    desired_seg: Segment,
    tab_id: str | None,
) -> list[dict[str, Any]]:
    """Reconcile content within a single segment."""
    alignment = align_structural_elements(base_seg.content, desired_seg.content)
    return generate_requests(alignment, base_seg.segment_id, tab_id)


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


def _delete_segment_request(
    segment: Segment, tab_id: str | None
) -> dict[str, Any] | None:
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


def _reconcile_new_segment(
    _desired_seg: Segment, _tab_id: str | None
) -> list[dict[str, Any]]:
    """Populate content in a newly created segment.

    When a header/footer is created, it contains initial content (just "\n").
    This function diffs the desired content against that initial state.

    NOTE: This is a stub for Phase 3. Full implementation requires handling
    the ID assignment problem: the API returns a new ID when creating a segment,
    and content requests must reference that new ID (not the desired doc's ID).
    This will be addressed in Phase 4+ with placeholder ID rewriting.
    """
    # For now, return empty list - segment is created but not populated
    # Phase 4 will implement proper content population
    return []


def verify(
    base: Document,
    requests: BatchUpdateDocumentRequest,
    desired: Document,
) -> tuple[bool, list[str]]:
    """Apply requests to base via MockGoogleDocsAPI and compare with desired.

    Args:
        base: The original document
        requests: The batch update requests to apply
        desired: The expected result

    Returns:
        (match, list_of_differences)
    """
    base_dict = base.model_dump(by_alias=True, exclude_none=True)
    mock = MockGoogleDocsAPI(base_dict)

    # Convert Request models to dicts
    request_dicts: list[dict[str, Any]] = []
    for req in requests.requests or []:
        req_dict = req.model_dump(by_alias=True, exclude_none=True)
        request_dicts.append(req_dict)

    if request_dicts:
        mock.batch_update(request_dicts)

    actual_dict = mock.get()
    desired_dict = desired.model_dump(by_alias=True, exclude_none=True)

    return documents_match(actual_dict, desired_dict)
