"""Shared utility functions for the mock Google Docs API."""

from __future__ import annotations

import re
from typing import Any

from extradoc.indexer import utf16_len


def calculate_utf16_offset(text: str, utf16_units: int) -> int:
    """Calculate string offset for a given UTF-16 code unit offset.

    Args:
        text: The text string
        utf16_units: Number of UTF-16 code units from start

    Returns:
        String index (Python character position)
    """
    if utf16_units == 0:
        return 0

    units_counted = 0
    for i, char in enumerate(text):
        if units_counted >= utf16_units:
            return i
        if ord(char) >= 0x10000:
            units_counted += 2
        else:
            units_counted += 1

    return len(text)


def strip_control_characters(text: str) -> str:
    """Strip control characters from text as per API spec.

    Args:
        text: Input text.

    Returns:
        Text with control characters removed.
    """
    text = re.sub(r"[\x00-\x08\x0c-\x1f]", "", text)
    text = re.sub(r"[\ue000-\uf8ff]", "", text)
    return text


def table_cell_paragraph_style() -> dict[str, Any]:
    """Return the default paragraph style for a new table cell.

    Matches the full set of defaults the real Google Docs API returns.
    """
    _border_default = {
        "color": {},
        "width": {"unit": "PT"},
        "padding": {"unit": "PT"},
        "dashStyle": "SOLID",
    }
    return {
        "namedStyleType": "NORMAL_TEXT",
        "direction": "LEFT_TO_RIGHT",
        "alignment": "START",
        "lineSpacing": 100,
        "spacingMode": "COLLAPSE_LISTS",
        "spaceAbove": {"unit": "PT"},
        "spaceBelow": {"unit": "PT"},
        "borderTop": dict(_border_default),
        "borderBottom": dict(_border_default),
        "borderLeft": dict(_border_default),
        "borderRight": dict(_border_default),
        "borderBetween": dict(_border_default),
        "indentFirstLine": {"unit": "PT"},
        "indentStart": {"unit": "PT"},
        "indentEnd": {"unit": "PT"},
        "keepLinesTogether": False,
        "keepWithNext": False,
        "avoidWidowAndOrphan": False,
        "shading": {"backgroundColor": {}},
        "pageBreakBefore": False,
    }


def make_empty_cell(start_index: int) -> dict[str, Any]:
    """Create an empty table cell with default styling.

    Args:
        start_index: Starting index for the cell.

    Returns:
        Cell dict with one empty paragraph.
    """
    para_start = start_index + 1
    para_end = para_start + 1
    return {
        "startIndex": start_index,
        "endIndex": para_end,
        "content": [
            {
                "startIndex": para_start,
                "endIndex": para_end,
                "paragraph": {
                    "elements": [
                        {
                            "startIndex": para_start,
                            "endIndex": para_end,
                            "textRun": {
                                "content": "\n",
                                "textStyle": {},
                            },
                        }
                    ],
                    "paragraphStyle": {
                        "namedStyleType": "NORMAL_TEXT",
                        "direction": "LEFT_TO_RIGHT",
                    },
                },
            }
        ],
        "tableCellStyle": {
            "rowSpan": 1,
            "columnSpan": 1,
            "backgroundColor": {},
            "paddingLeft": {"magnitude": 5, "unit": "PT"},
            "paddingRight": {"magnitude": 5, "unit": "PT"},
            "paddingTop": {"magnitude": 5, "unit": "PT"},
            "paddingBottom": {"magnitude": 5, "unit": "PT"},
            "contentAlignment": "TOP",
        },
    }


def content_element_size(element: dict[str, Any]) -> int:
    """Calculate the index size of a content element.

    Args:
        element: A structural element (paragraph, table, etc.)

    Returns:
        Number of index units this element occupies.
    """
    if "paragraph" in element:
        total = 0
        for pe in element["paragraph"].get("elements", []):
            if "textRun" in pe:
                total += utf16_len(pe["textRun"].get("content", ""))
            else:
                total += pe.get("endIndex", 0) - pe.get("startIndex", 0)
        return total
    end: int = element.get("endIndex", 0)
    start: int = element.get("startIndex", 0)
    return end - start
