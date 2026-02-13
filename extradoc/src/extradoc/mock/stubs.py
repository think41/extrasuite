"""Stub handlers for unimplemented or minimal Google Docs API operations."""

from __future__ import annotations

import uuid
from typing import Any

from extradoc.mock.exceptions import ValidationError
from extradoc.mock.navigation import get_segment, get_tab, validate_range


def handle_replace_all_text(
    document: dict[str, Any],
    request: dict[str, Any],
    structure_tracker: Any,
) -> dict[str, Any]:
    """Handle ReplaceAllTextRequest."""
    contains_text = request.get("containsText")
    if not contains_text:
        raise ValidationError("containsText is required")
    return {"replaceAllText": {"occurrencesChanged": 0}}


def handle_delete_positioned_object(
    document: dict[str, Any],
    request: dict[str, Any],
    structure_tracker: Any,
) -> dict[str, Any]:
    """Handle DeletePositionedObjectRequest."""
    object_id = request.get("objectId")
    if not object_id:
        raise ValidationError("objectId is required")
    tab_id = request.get("tabId")
    get_tab(document, tab_id)
    return {}


def handle_update_table_column_properties(
    document: dict[str, Any],
    request: dict[str, Any],
    structure_tracker: Any,
) -> dict[str, Any]:
    """Handle UpdateTableColumnPropertiesRequest."""
    table_start_location = request.get("tableStartLocation")
    table_column_properties = request.get("tableColumnProperties")
    fields = request.get("fields")

    if not table_start_location:
        raise ValidationError("tableStartLocation is required")
    if table_column_properties is None:
        raise ValidationError("tableColumnProperties is required")
    if not fields:
        raise ValidationError("fields is required")

    tab_id = table_start_location.get("tabId")
    get_tab(document, tab_id)

    if "width" in fields or "*" in fields:
        width = table_column_properties.get("width", {})
        if width:
            magnitude = width.get("magnitude", 0)
            unit = width.get("unit", "PT")
            if unit == "PT" and magnitude < 5:
                raise ValidationError("Column width must be at least 5 points")

    return {}


def handle_update_table_cell_style(
    document: dict[str, Any],
    request: dict[str, Any],
    structure_tracker: Any,
) -> dict[str, Any]:
    """Handle UpdateTableCellStyleRequest."""
    table_cell_style = request.get("tableCellStyle")
    fields = request.get("fields")

    if table_cell_style is None:
        raise ValidationError("tableCellStyle is required")
    if not fields:
        raise ValidationError("fields is required")

    table_range = request.get("tableRange")
    table_start_location = request.get("tableStartLocation")

    if not table_range and not table_start_location:
        raise ValidationError("Must specify either tableRange or tableStartLocation")

    if table_range:
        tab_id = table_range.get("tabId")
    else:
        tab_id = table_start_location.get("tabId") if table_start_location else None

    get_tab(document, tab_id)
    return {}


def handle_update_table_row_style(
    document: dict[str, Any],
    request: dict[str, Any],
    structure_tracker: Any,
) -> dict[str, Any]:
    """Handle UpdateTableRowStyleRequest."""
    table_start_location = request.get("tableStartLocation")
    table_row_style = request.get("tableRowStyle")
    fields = request.get("fields")

    if not table_start_location:
        raise ValidationError("tableStartLocation is required")
    if table_row_style is None:
        raise ValidationError("tableRowStyle is required")
    if not fields:
        raise ValidationError("fields is required")

    tab_id = table_start_location.get("tabId")
    get_tab(document, tab_id)
    return {}


def handle_update_document_style(
    document: dict[str, Any],
    request: dict[str, Any],
    structure_tracker: Any,
) -> dict[str, Any]:
    """Handle UpdateDocumentStyleRequest."""
    document_style = request.get("documentStyle")
    fields = request.get("fields")

    if document_style is None:
        raise ValidationError("documentStyle is required")
    if not fields:
        raise ValidationError("fields is required")

    tab_id = request.get("tabId")
    get_tab(document, tab_id)
    return {}


def handle_update_section_style(
    document: dict[str, Any],
    request: dict[str, Any],
    structure_tracker: Any,
) -> dict[str, Any]:
    """Handle UpdateSectionStyleRequest."""
    range_obj = request.get("range")
    section_style = request.get("sectionStyle")
    fields = request.get("fields")

    if not range_obj:
        raise ValidationError("range is required")
    if section_style is None:
        raise ValidationError("sectionStyle is required")
    if not fields:
        raise ValidationError("fields is required")

    segment_id = range_obj.get("segmentId")
    if segment_id:
        raise ValidationError(
            "Section styles can only be applied to body, not headers/footers/footnotes"
        )

    start_index = range_obj["startIndex"]
    end_index = range_obj["endIndex"]
    tab_id = range_obj.get("tabId")

    tab = get_tab(document, tab_id)
    validate_range(tab, start_index, end_index)
    return {}


def handle_update_document_tab_properties(
    document: dict[str, Any],
    request: dict[str, Any],
    structure_tracker: Any,
) -> dict[str, Any]:
    """Handle UpdateDocumentTabPropertiesRequest."""
    tab_properties = request.get("tabProperties")
    fields = request.get("fields")

    if not tab_properties:
        raise ValidationError("tabProperties is required")
    if not fields:
        raise ValidationError("fields is required")

    tab_id = tab_properties.get("tabId")
    if not tab_id:
        raise ValidationError("tabProperties.tabId is required")

    get_tab(document, tab_id)
    return {}


def handle_merge_table_cells(
    document: dict[str, Any],
    request: dict[str, Any],
    structure_tracker: Any,
) -> dict[str, Any]:
    """Handle MergeTableCellsRequest."""
    table_range = request.get("tableRange")
    if not table_range:
        raise ValidationError("tableRange is required")
    tab_id = table_range.get("tabId")
    get_tab(document, tab_id)
    return {}


def handle_unmerge_table_cells(
    document: dict[str, Any],
    request: dict[str, Any],
    structure_tracker: Any,
) -> dict[str, Any]:
    """Handle UnmergeTableCellsRequest."""
    table_range = request.get("tableRange")
    if not table_range:
        raise ValidationError("tableRange is required")
    tab_id = table_range.get("tabId")
    get_tab(document, tab_id)
    return {}


def handle_pin_table_header_rows(
    document: dict[str, Any],
    request: dict[str, Any],
    structure_tracker: Any,
) -> dict[str, Any]:
    """Handle PinTableHeaderRowsRequest."""
    table_start_location = request.get("tableStartLocation")
    pinned_header_rows_count = request.get("pinnedHeaderRowsCount")

    if not table_start_location:
        raise ValidationError("tableStartLocation is required")
    if pinned_header_rows_count is None:
        raise ValidationError("pinnedHeaderRowsCount is required")

    tab_id = table_start_location.get("tabId")
    get_tab(document, tab_id)
    return {}


def handle_insert_inline_image(
    document: dict[str, Any],
    request: dict[str, Any],
    structure_tracker: Any,
) -> dict[str, Any]:
    """Handle InsertInlineImageRequest."""
    uri = request.get("uri")
    location = request.get("location")
    end_of_segment = request.get("endOfSegmentLocation")

    if not uri:
        raise ValidationError("uri is required")
    if not location and not end_of_segment:
        raise ValidationError("Must specify either location or endOfSegmentLocation")
    if location and end_of_segment:
        raise ValidationError("Cannot specify both location and endOfSegmentLocation")
    if len(uri) > 2048:
        raise ValidationError("URI must be less than 2 KB")

    if location:
        index = location["index"]
        tab_id = location.get("tabId")
        segment_id = location.get("segmentId")

        if segment_id:
            tab = get_tab(document, tab_id)
            _segment, segment_type = get_segment(tab, segment_id)
            if segment_type == "footnote":
                raise ValidationError("Cannot insert image in footnote")

        if index < 1:
            raise ValidationError(f"Index must be at least 1, got {index}")

    object_id = f"inlineImage_{uuid.uuid4().hex[:16]}"
    return {"insertInlineImage": {"objectId": object_id}}


def handle_insert_page_break(
    document: dict[str, Any],
    request: dict[str, Any],
    structure_tracker: Any,
) -> dict[str, Any]:
    """Handle InsertPageBreakRequest."""
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
                "Cannot insert page break in header, footer, or footnote"
            )
        get_tab(document, tab_id)
        if index < 1:
            raise ValidationError(f"Index must be at least 1, got {index}")

    return {}


def handle_insert_section_break(
    document: dict[str, Any],
    request: dict[str, Any],
    structure_tracker: Any,
) -> dict[str, Any]:
    """Handle InsertSectionBreakRequest."""
    location = request.get("location")
    end_of_segment = request.get("endOfSegmentLocation")
    section_type = request.get("sectionType")

    if not location and not end_of_segment:
        raise ValidationError("Must specify either location or endOfSegmentLocation")
    if location and end_of_segment:
        raise ValidationError("Cannot specify both location and endOfSegmentLocation")
    if not section_type:
        raise ValidationError("sectionType is required")

    if location:
        index = location["index"]
        tab_id = location.get("tabId")
        segment_id = location.get("segmentId")

        if segment_id:
            raise ValidationError(
                "Cannot insert section break in header, footer, or footnote"
            )
        get_tab(document, tab_id)
        if index < 1:
            raise ValidationError(f"Index must be at least 1, got {index}")

    return {}


def handle_insert_person(
    document: dict[str, Any],
    request: dict[str, Any],
    structure_tracker: Any,
) -> dict[str, Any]:
    """Handle InsertPersonRequest."""
    location = request.get("location")
    end_of_segment = request.get("endOfSegmentLocation")
    person_properties = request.get("personProperties")

    if not location and not end_of_segment:
        raise ValidationError("Must specify either location or endOfSegmentLocation")
    if location and end_of_segment:
        raise ValidationError("Cannot specify both location and endOfSegmentLocation")
    if not person_properties:
        raise ValidationError("personProperties is required")

    if location:
        index = location["index"]
        tab_id = location.get("tabId")
        segment_id = location.get("segmentId")

        if segment_id:
            tab = get_tab(document, tab_id)
            get_segment(tab, segment_id)

        if index < 1:
            raise ValidationError(f"Index must be at least 1, got {index}")

    return {}


def handle_insert_date(
    document: dict[str, Any],
    request: dict[str, Any],
    structure_tracker: Any,
) -> dict[str, Any]:
    """Handle InsertDateRequest."""
    location = request.get("location")
    end_of_segment = request.get("endOfSegmentLocation")
    date_element_properties = request.get("dateElementProperties")

    if not location and not end_of_segment:
        raise ValidationError("Must specify either location or endOfSegmentLocation")
    if location and end_of_segment:
        raise ValidationError("Cannot specify both location and endOfSegmentLocation")
    if not date_element_properties:
        raise ValidationError("dateElementProperties is required")

    if location:
        index = location["index"]
        tab_id = location.get("tabId")

        if index < 1:
            raise ValidationError(f"Index must be at least 1, got {index}")
        get_tab(document, tab_id)

    return {}


def handle_replace_image(
    document: dict[str, Any],
    request: dict[str, Any],
    structure_tracker: Any,
) -> dict[str, Any]:
    """Handle ReplaceImageRequest."""
    image_object_id = request.get("imageObjectId")
    uri = request.get("uri")

    if not image_object_id:
        raise ValidationError("imageObjectId is required")
    if not uri:
        raise ValidationError("uri is required")
    if len(uri) > 2048:
        raise ValidationError("URI must be less than 2 KB")

    tab_id = request.get("tabId")
    get_tab(document, tab_id)
    return {}


def handle_replace_named_range_content(
    document: dict[str, Any],
    request: dict[str, Any],
    structure_tracker: Any,
) -> dict[str, Any]:
    """Handle ReplaceNamedRangeContentRequest."""
    text = request.get("text")
    named_range_id = request.get("namedRangeId")
    named_range_name = request.get("namedRangeName")

    if text is None:
        raise ValidationError("text is required")
    if not named_range_id and not named_range_name:
        raise ValidationError("Must specify either namedRangeId or namedRangeName")

    return {}
