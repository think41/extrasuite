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


# Request types that specifically create new elements with IDs we need to track
CREATION_REQUEST_TYPES: frozenset[str] = frozenset(
    {
        "createHeader",
        "createFooter",
        "addDocumentTab",
        "createFootnote",
    }
)


def separate_structural_requests(
    requests: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Separate structural creation requests from content requests.

    Structural requests need to be executed first so we can capture their
    returned IDs and use them in subsequent content requests.

    Args:
        requests: List of batchUpdate request dicts

    Returns:
        Tuple of (structural_requests, content_requests) where:
        - structural_requests should be executed first to get IDs
        - content_requests should be executed after ID substitution

    Example:
        >>> reqs = [
        ...     {"createHeader": {"type": "DEFAULT"}},
        ...     {"insertText": {"location": {"index": 1}, "text": "Hello"}},
        ... ]
        >>> structural, content = separate_structural_requests(reqs)
        >>> structural
        [{"createHeader": {"type": "DEFAULT"}}]
        >>> content
        [{"insertText": {"location": {"index": 1}, "text": "Hello"}}]
    """
    structural: list[dict[str, Any]] = []
    content: list[dict[str, Any]] = []

    for req in requests:
        req_type = next(iter(req.keys()))
        if req_type in CREATION_REQUEST_TYPES:
            structural.append(req)
        else:
            content.append(req)

    return structural, content


def extract_created_ids(
    response: dict[str, Any],
    placeholder_prefix: str = "_placeholder_",
) -> dict[str, str]:
    """Extract placeholder-to-real ID mappings from batchUpdate response.

    When we create structural elements (headers, footers, footnotes, tabs),
    we use placeholder IDs in pending requests. This function extracts the
    real IDs from the API response so we can substitute them.

    Args:
        response: The batchUpdate API response dict
        placeholder_prefix: Prefix used for placeholder IDs

    Returns:
        Dict mapping placeholder IDs to real IDs

    Example:
        >>> response = {
        ...     "replies": [
        ...         {"createHeader": {"headerId": "kix.abc123"}},
        ...         {"createFooter": {"footerId": "kix.def456"}},
        ...     ]
        ... }
        >>> extract_created_ids(response)
        {
            "_placeholder_header_0": "kix.abc123",
            "_placeholder_footer_0": "kix.def456"
        }
    """
    id_map: dict[str, str] = {}
    counters: dict[str, int] = {
        "header": 0,
        "footer": 0,
        "footnote": 0,
        "tab": 0,
    }

    # Mapping from API reply key to (element type, ID field)
    reply_mappings: dict[str, tuple[str, str]] = {
        "createHeader": ("header", "headerId"),
        "createFooter": ("footer", "footerId"),
        "createFootnote": ("footnote", "footnoteId"),
        "addDocumentTab": ("tab", "tabId"),
    }

    for reply in response.get("replies", []):
        for reply_key, (elem_type, id_field) in reply_mappings.items():
            if reply_key in reply:
                real_id = reply[reply_key].get(id_field)
                if real_id:
                    placeholder = (
                        f"{placeholder_prefix}{elem_type}_{counters[elem_type]}"
                    )
                    id_map[placeholder] = real_id
                    counters[elem_type] += 1
                break  # Only one reply type per reply object

    return id_map


def substitute_placeholder_ids(
    requests: list[dict[str, Any]],
    id_map: dict[str, str],
) -> list[dict[str, Any]]:
    """Replace placeholder IDs with real IDs in requests.

    Recursively traverses requests and substitutes any placeholder IDs
    found in id_map with their corresponding real IDs.

    Args:
        requests: List of request dicts (not modified in place)
        id_map: Dict mapping placeholder IDs to real IDs

    Returns:
        New list of requests with substituted IDs

    Example:
        >>> requests = [
        ...     {"insertText": {"location": {"segmentId": "_placeholder_header_0", "index": 0}}}
        ... ]
        >>> id_map = {"_placeholder_header_0": "kix.abc123"}
        >>> substitute_placeholder_ids(requests, id_map)
        [{"insertText": {"location": {"segmentId": "kix.abc123", "index": 0}}}]
    """
    if not id_map:
        return requests

    return [_substitute_in_value(req, id_map) for req in requests]


def _substitute_in_value(obj: Any, id_map: dict[str, str]) -> Any:
    """Recursively substitute placeholders in a value.

    Args:
        obj: The value to process (dict, list, or primitive)
        id_map: Dict mapping placeholder IDs to real IDs

    Returns:
        New value with substitutions applied
    """
    if isinstance(obj, dict):
        return {k: _substitute_in_value(v, id_map) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_substitute_in_value(item, id_map) for item in obj]
    elif isinstance(obj, str):
        return id_map.get(obj, obj)
    else:
        return obj


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
