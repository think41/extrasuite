"""Named range operations for the mock Google Docs API."""

from __future__ import annotations

import uuid
from typing import Any

from extradoc.indexer import utf16_len
from extradoc.mock.exceptions import ValidationError
from extradoc.mock.navigation import get_tab, validate_range


def handle_create_named_range(
    document: dict[str, Any],
    request: dict[str, Any],
    structure_tracker: Any,
    named_ranges: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Handle CreateNamedRangeRequest."""
    name = request.get("name")
    range_obj = request.get("range")

    if name is None:
        raise ValidationError("name is required")
    if not range_obj:
        raise ValidationError("range is required")

    name_length = utf16_len(name)
    if name_length < 1 or name_length > 256:
        raise ValidationError(
            f"name must be 1-256 UTF-16 code units, got {name_length}"
        )

    start_index = range_obj.get("startIndex")
    end_index = range_obj.get("endIndex")
    tab_id = range_obj.get("tabId")

    if start_index is None or end_index is None:
        raise ValidationError("range must have startIndex and endIndex")

    tab = get_tab(document, tab_id)
    validate_range(tab, start_index, end_index)

    named_range_id = f"namedRange_{uuid.uuid4().hex[:16]}"

    named_ranges[named_range_id] = {"name": name, "range": range_obj}

    document_tab = tab.get("documentTab", {})
    if "namedRanges" not in document_tab:
        document_tab["namedRanges"] = {}

    if name not in document_tab["namedRanges"]:
        document_tab["namedRanges"][name] = {"namedRanges": []}

    document_tab["namedRanges"][name]["namedRanges"].append(
        {"namedRangeId": named_range_id, "ranges": [range_obj]}
    )

    return {"createNamedRange": {"namedRangeId": named_range_id}}


def handle_delete_named_range(
    document: dict[str, Any],
    request: dict[str, Any],
    structure_tracker: Any,
    named_ranges: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Handle DeleteNamedRangeRequest."""
    named_range_id = request.get("namedRangeId")
    name = request.get("name")

    if not named_range_id and not name:
        raise ValidationError("Must specify either namedRangeId or name")
    if named_range_id and name:
        raise ValidationError("Cannot specify both namedRangeId and name")

    if named_range_id:
        if named_range_id not in named_ranges:
            raise ValidationError(f"Named range not found: {named_range_id}")
        range_name = named_ranges[named_range_id]["name"]
        del named_ranges[named_range_id]

        for tab in document.get("tabs", []):
            document_tab = tab.get("documentTab", {})
            named_ranges_obj = document_tab.get("namedRanges", {})
            if range_name in named_ranges_obj:
                ranges_list = named_ranges_obj[range_name].get("namedRanges", [])
                named_ranges_obj[range_name]["namedRanges"] = [
                    r for r in ranges_list if r.get("namedRangeId") != named_range_id
                ]
                if not named_ranges_obj[range_name]["namedRanges"]:
                    del named_ranges_obj[range_name]
    else:
        to_delete = [rid for rid, info in named_ranges.items() if info["name"] == name]
        for rid in to_delete:
            del named_ranges[rid]

        for tab in document.get("tabs", []):
            document_tab = tab.get("documentTab", {})
            named_ranges_obj = document_tab.get("namedRanges", {})
            if name in named_ranges_obj:
                del named_ranges_obj[name]

    return {}
