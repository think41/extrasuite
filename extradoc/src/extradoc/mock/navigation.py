"""Navigation helpers for finding elements in a Google Docs document."""

from __future__ import annotations

from typing import Any

from extradoc.mock.exceptions import ValidationError


def get_tab(document: dict[str, Any], tab_id: str | None) -> dict[str, Any]:
    """Get tab by ID, or first tab if None.

    Args:
        document: The full document dict.
        tab_id: Tab ID or None for first tab.

    Returns:
        Tab object.

    Raises:
        ValidationError: If tab not found.
    """
    tabs = document.get("tabs", [])
    if not tabs:
        raise ValidationError("Document has no tabs")

    if tab_id is None:
        first_tab: dict[str, Any] = tabs[0]
        return first_tab

    for tab in tabs:
        if tab.get("tabProperties", {}).get("tabId") == tab_id:
            found_tab: dict[str, Any] = tab
            return found_tab

    raise ValidationError(f"Tab not found: {tab_id}")


def get_segment(
    tab: dict[str, Any], segment_id: str | None
) -> tuple[dict[str, Any], str]:
    """Get segment (body, header, footer, footnote) from tab.

    Args:
        tab: Tab object.
        segment_id: Segment ID or None for body.

    Returns:
        Tuple of (segment object, segment type).

    Raises:
        ValidationError: If segment not found.
    """
    document_tab = tab.get("documentTab", {})

    if segment_id is None:
        body = document_tab.get("body")
        if not body:
            raise ValidationError("Document has no body")
        return body, "body"

    headers = document_tab.get("headers", {})
    if segment_id in headers:
        return headers[segment_id], "header"

    footers = document_tab.get("footers", {})
    if segment_id in footers:
        return footers[segment_id], "footer"

    footnotes = document_tab.get("footnotes", {})
    if segment_id in footnotes:
        return footnotes[segment_id], "footnote"

    raise ValidationError(f"Segment not found: {segment_id}")


def validate_range(tab: dict[str, Any], start_index: int, end_index: int) -> None:
    """Validate that a range is within document bounds.

    Args:
        tab: Tab object.
        start_index: Start index.
        end_index: End index.

    Raises:
        ValidationError: If range is invalid.
    """
    if start_index < 1:
        raise ValidationError(f"startIndex must be at least 1, got {start_index}")
    if end_index <= start_index:
        raise ValidationError(
            f"endIndex ({end_index}) must be greater than startIndex ({start_index})"
        )

    document_tab = tab.get("documentTab", {})
    body = document_tab.get("body", {})
    content = body.get("content", [])

    if content:
        last_element = content[-1]
        max_index = last_element.get("endIndex", 1)
        if end_index > max_index:
            raise ValidationError(
                f"endIndex ({end_index}) exceeds document length ({max_index})"
            )


def _collect_paragraphs_in_range(
    content: list[dict[str, Any]],
    start_index: int,
    end_index: int,
    result: list[dict[str, Any]],
    *,
    inclusive: bool = False,
) -> None:
    """Recursively collect paragraphs in range from content list (including inside tables)."""
    for element in content:
        el_start = element.get("startIndex", 0)
        el_end = element.get("endIndex", 0)

        if "paragraph" in element:
            if inclusive:
                if el_end >= start_index and el_start < end_index:
                    result.append(element["paragraph"])
            else:
                if el_end > start_index and el_start < end_index:
                    result.append(element["paragraph"])
        elif "table" in element and el_end > start_index and el_start < end_index:
            for row in element["table"].get("tableRows", []):
                for cell in row.get("tableCells", []):
                    _collect_paragraphs_in_range(
                        cell.get("content", []),
                        start_index,
                        end_index,
                        result,
                        inclusive=inclusive,
                    )


def get_paragraphs_in_range(
    tab: dict[str, Any],
    start_index: int,
    end_index: int,
    segment_id: str | None = None,
    *,
    inclusive: bool = False,
) -> list[dict[str, Any]]:
    """Get all paragraphs whose range overlaps [start_index, end_index).

    Includes paragraphs inside table cells that overlap the range.

    Args:
        tab: Tab object.
        start_index: Range start index.
        end_index: Range end index.
        segment_id: Segment ID or None for body.
        inclusive: If True, use inclusive boundary check.

    Returns:
        List of paragraph dicts that overlap the range.
    """
    segment, _ = get_segment(tab, segment_id)
    content = segment.get("content", [])
    result: list[dict[str, Any]] = []
    _collect_paragraphs_in_range(
        content, start_index, end_index, result, inclusive=inclusive
    )
    return result


def find_table_at_index(
    segment: dict[str, Any], table_start_index: int
) -> tuple[dict[str, Any], int]:
    """Find a table element by its start index.

    Args:
        segment: Segment containing the table.
        table_start_index: Start index of the table.

    Returns:
        Tuple of (table structural element, index in content array).

    Raises:
        ValidationError: If table not found.
    """
    content = segment.get("content", [])
    for i, element in enumerate(content):
        if "table" in element and element.get("startIndex", 0) == table_start_index:
            return element, i
    raise ValidationError(f"Table not found at index {table_start_index}")
