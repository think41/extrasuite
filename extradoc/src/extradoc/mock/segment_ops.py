"""Segment-level operations: headers, footers, footnotes, tabs."""

from __future__ import annotations

import copy
import uuid
from typing import Any

from extradoc.mock.exceptions import ValidationError
from extradoc.mock.navigation import get_tab


def handle_create_header(
    document: dict[str, Any],
    request: dict[str, Any],
    structure_tracker: Any,
    header_types: set[str],
) -> dict[str, Any]:
    """Handle CreateHeaderRequest."""
    header_type = request.get("type")
    if not header_type:
        raise ValidationError("type is required")

    if header_type in header_types:
        raise ValidationError(
            f"A header of type {header_type} already exists. "
            "Only one header of each type (DEFAULT, FIRST_PAGE, EVEN_PAGE) is allowed."
        )

    section_break_location = request.get("sectionBreakLocation")
    tab_id = None
    if section_break_location:
        tab_id = section_break_location.get("tabId")

    tab = get_tab(document, tab_id)
    header_id = f"header_{uuid.uuid4().hex[:16]}"
    header_types.add(header_type)

    document_tab = tab.get("documentTab", {})
    if "headers" not in document_tab:
        document_tab["headers"] = {}

    document_tab["headers"][header_id] = {
        "content": [
            {
                "endIndex": 2,
                "paragraph": {
                    "elements": [
                        {
                            "endIndex": 2,
                            "textRun": {"content": "\n", "textStyle": {}},
                        }
                    ],
                    "paragraphStyle": {},
                },
            }
        ]
    }

    return {"createHeader": {"headerId": header_id}}


def handle_create_footer(
    document: dict[str, Any],
    request: dict[str, Any],
    structure_tracker: Any,
    footer_types: set[str],
) -> dict[str, Any]:
    """Handle CreateFooterRequest."""
    footer_type = request.get("type")
    if not footer_type:
        raise ValidationError("type is required")

    if footer_type in footer_types:
        raise ValidationError(
            f"A footer of type {footer_type} already exists. "
            "Only one footer of each type (DEFAULT, FIRST_PAGE, EVEN_PAGE) is allowed."
        )

    section_break_location = request.get("sectionBreakLocation")
    tab_id = None
    if section_break_location:
        tab_id = section_break_location.get("tabId")

    tab = get_tab(document, tab_id)
    footer_id = f"footer_{uuid.uuid4().hex[:16]}"
    footer_types.add(footer_type)

    document_tab = tab.get("documentTab", {})
    if "footers" not in document_tab:
        document_tab["footers"] = {}

    document_tab["footers"][footer_id] = {
        "content": [
            {
                "endIndex": 2,
                "paragraph": {
                    "elements": [
                        {
                            "endIndex": 2,
                            "textRun": {"content": "\n", "textStyle": {}},
                        }
                    ],
                    "paragraphStyle": {},
                },
            }
        ]
    }

    return {"createFooter": {"footerId": footer_id}}


def handle_create_footnote(
    document: dict[str, Any],
    request: dict[str, Any],
    structure_tracker: Any,
) -> dict[str, Any]:
    """Handle CreateFootnoteRequest."""
    location = request.get("location")
    end_of_segment = request.get("endOfSegmentLocation")

    if not location and not end_of_segment:
        raise ValidationError("Must specify either location or endOfSegmentLocation")
    if location and end_of_segment:
        raise ValidationError("Cannot specify both location and endOfSegmentLocation")

    if location:
        index = location["index"]
        tab_id = location.get("tabId")
        segment_id = location.get("segmentId")

        if segment_id:
            raise ValidationError(
                "Cannot create footnote in header, footer, or another footnote"
            )

        tab = get_tab(document, tab_id)
        if index < 1:
            raise ValidationError(f"Index must be at least 1, got {index}")

    footnote_id = f"footnote_{uuid.uuid4().hex[:16]}"

    if location:
        tab_id = location.get("tabId")
    else:
        tab_id = end_of_segment.get("tabId") if end_of_segment else None

    tab = get_tab(document, tab_id)
    document_tab = tab.get("documentTab", {})
    if "footnotes" not in document_tab:
        document_tab["footnotes"] = {}

    document_tab["footnotes"][footnote_id] = {
        "content": [
            {
                "endIndex": 3,
                "paragraph": {
                    "elements": [
                        {
                            "endIndex": 3,
                            "textRun": {"content": " \n", "textStyle": {}},
                        }
                    ],
                    "paragraphStyle": {},
                },
            }
        ]
    }

    return {"createFootnote": {"footnoteId": footnote_id}}


def handle_add_document_tab(
    document: dict[str, Any],
    request: dict[str, Any],
    structure_tracker: Any,
) -> dict[str, Any]:
    """Handle AddDocumentTabRequest."""
    tab_properties = request.get("tabProperties", {})
    tab_id = f"t.{uuid.uuid4().hex[:16]}"

    # Real API returns 400 if a tab with the same title already exists
    requested_title = tab_properties.get("title", "Untitled Tab")
    existing_titles = {
        t.get("tabProperties", {}).get("title", "") for t in document.get("tabs", [])
    }
    if requested_title in existing_titles:
        raise ValidationError("Tab title must be unique")

    first_tab = document.get("tabs", [{}])[0]
    first_doc_tab = first_tab.get("documentTab", {})
    document_style = copy.deepcopy(first_doc_tab.get("documentStyle", {}))
    named_styles = copy.deepcopy(first_doc_tab.get("namedStyles", {}))

    new_tab = {
        "tabProperties": {
            "tabId": tab_id,
            "title": tab_properties.get("title", "Untitled Tab"),
            "index": tab_properties.get("index", len(document.get("tabs", []))),
        },
        "documentTab": {
            "body": {
                "content": [
                    {
                        "sectionBreak": {
                            "sectionStyle": {
                                "columnSeparatorStyle": "NONE",
                                "contentDirection": "LEFT_TO_RIGHT",
                                "sectionType": "CONTINUOUS",
                            },
                        },
                        "startIndex": 0,
                        "endIndex": 1,
                    },
                    {
                        "startIndex": 1,
                        "endIndex": 2,
                        "paragraph": {
                            "elements": [
                                {
                                    "startIndex": 1,
                                    "endIndex": 2,
                                    "textRun": {"content": "\n", "textStyle": {}},
                                }
                            ],
                            "paragraphStyle": {
                                "namedStyleType": "NORMAL_TEXT",
                                "direction": "LEFT_TO_RIGHT",
                            },
                        },
                    },
                ]
            },
            "documentStyle": document_style,
            "namedStyles": named_styles,
            "headers": {},
            "footers": {},
            "footnotes": {},
            "namedRanges": {},
        },
    }

    if "tabs" not in document:
        document["tabs"] = []
    tab_index = tab_properties.get("index", len(document["tabs"]))
    document["tabs"].insert(tab_index, new_tab)

    return {
        "addDocumentTab": {
            "tabProperties": new_tab["tabProperties"],
        }
    }


def handle_delete_header(
    document: dict[str, Any],
    request: dict[str, Any],
    structure_tracker: Any,
) -> dict[str, Any]:
    """Handle DeleteHeaderRequest."""
    header_id = request.get("headerId")
    if not header_id:
        raise ValidationError("headerId is required")

    tab_id = request.get("tabId")
    tab = get_tab(document, tab_id)

    document_tab = tab.get("documentTab", {})
    headers = document_tab.get("headers", {})
    if header_id not in headers:
        raise ValidationError(f"Header not found: {header_id}")

    return {}


def handle_delete_footer(
    document: dict[str, Any],
    request: dict[str, Any],
    structure_tracker: Any,
) -> dict[str, Any]:
    """Handle DeleteFooterRequest."""
    footer_id = request.get("footerId")
    if not footer_id:
        raise ValidationError("footerId is required")

    tab_id = request.get("tabId")
    tab = get_tab(document, tab_id)

    document_tab = tab.get("documentTab", {})
    footers = document_tab.get("footers", {})
    if footer_id not in footers:
        raise ValidationError(f"Footer not found: {footer_id}")

    return {}


def handle_delete_tab(
    document: dict[str, Any],
    request: dict[str, Any],
    structure_tracker: Any,
) -> dict[str, Any]:
    """Handle DeleteTabRequest."""
    tab_id = request.get("tabId")
    if not tab_id:
        raise ValidationError("tabId is required")

    get_tab(document, tab_id)

    tabs = document.get("tabs", [])
    if len(tabs) <= 1:
        raise ValidationError(
            "Cannot delete the last tab. Document must have at least one tab."
        )

    document["tabs"] = [
        t for t in tabs if t.get("tabProperties", {}).get("tabId") != tab_id
    ]

    return {}
