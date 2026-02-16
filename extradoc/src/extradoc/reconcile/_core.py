"""Core reconcile, verify, and reindex_document functions."""

from __future__ import annotations

from typing import Any

from extradoc.api_types._generated import (
    BatchUpdateDocumentRequest,
    Document,
    Request,
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
from extradoc.reconcile._extractors import extract_segments
from extradoc.reconcile._generators import generate_requests


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
            # Matched segment - diff content
            segment_id = base_seg["segment_id"]
            seg_requests = _reconcile_segment(
                base_seg["content"],
                desired_seg["content"],
                segment_id,
                tab_id,
            )
            requests.extend(seg_requests)
        # Phase 3 will handle added/deleted segments (headers, footers, footnotes)

    return requests


def _reconcile_segment(
    base_content: list[Any],
    desired_content: list[Any],
    segment_id: str | None,
    tab_id: str | None,
) -> list[dict[str, Any]]:
    """Reconcile content within a single segment."""
    # Ensure we have StructuralElement objects
    base_elements: list[StructuralElement] = []
    for item in base_content:
        if isinstance(item, StructuralElement):
            base_elements.append(item)
        else:
            base_elements.append(StructuralElement.model_validate(item))

    desired_elements: list[StructuralElement] = []
    for item in desired_content:
        if isinstance(item, StructuralElement):
            desired_elements.append(item)
        else:
            desired_elements.append(StructuralElement.model_validate(item))

    alignment = align_structural_elements(base_elements, desired_elements)

    return generate_requests(alignment, segment_id, tab_id)


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
