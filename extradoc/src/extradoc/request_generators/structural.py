"""Structural request handling for Google Docs batchUpdate.

Handles structural creation requests that need to be executed in a separate batch
before content operations, enabling ID tracking for newly created elements.

Structural requests include:
- Header/footer creation and deletion
- Tab creation and deletion
- Footnote creation and deletion
- Table creation, row/column insertion and deletion
"""

from __future__ import annotations

from typing import Any

# Request types that create structural elements and need separate handling
STRUCTURAL_REQUEST_TYPES: frozenset[str] = frozenset(
    {
        # Header/footer
        "createHeader",
        "createFooter",
        "deleteHeader",
        "deleteFooter",
        # Tabs
        "addDocumentTab",
        "deleteTab",
        # Footnotes
        "createFootnote",
        "deleteFootnoteReference",
        # Tables
        "insertTable",
        "insertTableRow",
        "insertTableColumn",
        "deleteTableRow",
        "deleteTableColumn",
    }
)


def has_segment_id(obj: Any, target_ids: set[str]) -> bool:
    """Check if an object contains any of the target segment IDs.

    Used to identify requests that need to wait for segment creation.

    Args:
        obj: The object to check (dict, list, or primitive)
        target_ids: Set of segment IDs to look for

    Returns:
        True if any target ID is found in a segmentId field
    """
    if isinstance(obj, dict):
        if obj.get("segmentId") in target_ids:
            return True
        return any(has_segment_id(v, target_ids) for v in obj.values())
    elif isinstance(obj, list):
        return any(has_segment_id(item, target_ids) for item in obj)
    return False


def separate_by_segment_ids(
    requests: list[dict[str, Any]],
    segment_ids: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Separate requests by whether they reference specific segment IDs.

    Args:
        requests: List of request dicts
        segment_ids: Set of segment IDs to filter by

    Returns:
        Tuple of (main_requests, segment_requests) where:
        - main_requests don't reference any of the segment IDs
        - segment_requests reference at least one of the segment IDs
    """
    main: list[dict[str, Any]] = []
    segment: list[dict[str, Any]] = []

    for req in requests:
        if has_segment_id(req, segment_ids):
            segment.append(req)
        else:
            main.append(req)

    return main, segment


def extract_placeholder_footnote_ids(
    requests: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Extract and strip placeholder footnote IDs from createFootnote requests.

    Args:
        requests: List of request dicts

    Returns:
        Tuple of (cleaned_requests, placeholder_ids) where:
        - cleaned_requests have _placeholderFootnoteId removed
        - placeholder_ids are the extracted placeholder IDs in order
    """
    placeholders: list[str] = []
    cleaned: list[dict[str, Any]] = []

    for req in requests:
        if "createFootnote" in req:
            placeholder = req.get("_placeholderFootnoteId", "")
            if "_placeholderFootnoteId" in req:
                req = {k: v for k, v in req.items() if k != "_placeholderFootnoteId"}
            placeholders.append(placeholder)
        cleaned.append(req)

    return cleaned, placeholders
