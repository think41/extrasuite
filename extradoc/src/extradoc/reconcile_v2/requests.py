"""Typed request-construction helpers for ``reconcile_v2`` lowering."""

from __future__ import annotations

from typing import Any

HEADER_SLOT_FIELDS = {
    "DEFAULT": "defaultHeaderId",
    "FIRST_PAGE": "firstPageHeaderId",
    "EVEN_PAGE": "evenPageHeaderId",
}

FOOTER_SLOT_FIELDS = {
    "DEFAULT": "defaultFooterId",
    "FIRST_PAGE": "firstPageFooterId",
    "EVEN_PAGE": "evenPageFooterId",
}


def make_add_document_tab(
    *,
    title: str,
    parent_tab_id: Any | None = None,
    index: int | None = None,
    icon_emoji: str | None = None,
) -> dict[str, Any]:
    tab_properties: dict[str, Any] = {"title": title}
    if parent_tab_id is not None:
        tab_properties["parentTabId"] = parent_tab_id
    if index is not None:
        tab_properties["index"] = index
    if icon_emoji is not None:
        tab_properties["iconEmoji"] = icon_emoji
    return {"addDocumentTab": {"tabProperties": tab_properties}}


def make_create_header(
    *,
    header_type: str,
    tab_id: str | None = None,
    section_break_index: int | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"type": header_type}
    if section_break_index is not None:
        location: dict[str, Any] = {"index": section_break_index}
        if tab_id is not None:
            location["tabId"] = tab_id
        payload["sectionBreakLocation"] = location
    return {"createHeader": payload}


def make_create_footer(
    *,
    footer_type: str,
    tab_id: str | None = None,
    section_break_index: int | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"type": footer_type}
    if section_break_index is not None:
        location: dict[str, Any] = {"index": section_break_index}
        if tab_id is not None:
            location["tabId"] = tab_id
        payload["sectionBreakLocation"] = location
    return {"createFooter": payload}


def make_create_footnote(*, index: int, tab_id: str) -> dict[str, Any]:
    return {
        "createFootnote": {
            "location": {
                "index": index,
                "tabId": tab_id,
            }
        }
    }


def make_delete_header(*, header_id: str, tab_id: str) -> dict[str, Any]:
    return {"deleteHeader": {"headerId": header_id, "tabId": tab_id}}


def make_delete_footer(*, footer_id: str, tab_id: str) -> dict[str, Any]:
    return {"deleteFooter": {"footerId": footer_id, "tabId": tab_id}}


def make_update_paragraph_role(
    *,
    start_index: int,
    end_index: int,
    tab_id: str,
    role: str,
) -> dict[str, Any]:
    return {
        "updateParagraphStyle": {
            "range": {
                "startIndex": start_index,
                "endIndex": end_index,
                "tabId": tab_id,
            },
            "paragraphStyle": {
                "namedStyleType": role,
            },
            "fields": "namedStyleType",
        }
    }


def make_update_text_style(
    *,
    start_index: int,
    end_index: int,
    tab_id: Any,
    text_style: dict[str, Any],
    fields: tuple[str, ...] | list[str],
    segment_id: str | None = None,
) -> dict[str, Any]:
    range_: dict[str, Any] = {
        "startIndex": start_index,
        "endIndex": end_index,
        "tabId": tab_id,
    }
    if segment_id:
        range_["segmentId"] = segment_id
    return {
        "updateTextStyle": {
            "range": range_,
            "textStyle": text_style,
            "fields": ",".join(fields),
        }
    }


def make_update_section_attachment(
    *,
    start_index: int,
    end_index: int,
    tab_id: str,
    attachment_kind: str,
    slot: str,
    attachment_id: Any,
) -> dict[str, Any]:
    if attachment_kind == "headers":
        field_name = HEADER_SLOT_FIELDS[slot]
    elif attachment_kind == "footers":
        field_name = FOOTER_SLOT_FIELDS[slot]
    else:
        raise ValueError(f"Unsupported attachment kind: {attachment_kind}")
    return {
        "updateSectionStyle": {
            "range": {
                "startIndex": start_index,
                "endIndex": end_index,
                "tabId": tab_id,
            },
            "sectionStyle": {
                field_name: attachment_id,
            },
            "fields": field_name,
        }
    }


def make_insert_text(*, index: int, tab_id: Any, text: str) -> dict[str, Any]:
    return make_insert_text_in_story(
        index=index,
        tab_id=tab_id,
        segment_id=None,
        text=text,
    )


def make_create_paragraph_bullets(
    *,
    start_index: int,
    end_index: int,
    tab_id: str,
    bullet_preset: str,
) -> dict[str, Any]:
    return {
        "createParagraphBullets": {
            "range": {
                "startIndex": start_index,
                "endIndex": end_index,
                "tabId": tab_id,
            },
            "bulletPreset": bullet_preset,
        }
    }


def make_delete_paragraph_bullets(
    *,
    start_index: int,
    end_index: int,
    tab_id: str,
) -> dict[str, Any]:
    return {
        "deleteParagraphBullets": {
            "range": {
                "startIndex": start_index,
                "endIndex": end_index,
                "tabId": tab_id,
            }
        }
    }


def make_insert_section_break(
    *,
    index: int,
    tab_id: str,
    section_type: str = "NEXT_PAGE",
) -> dict[str, Any]:
    return {
        "insertSectionBreak": {
            "location": {
                "index": index,
                "tabId": tab_id,
            },
            "sectionType": section_type,
        }
    }


def make_delete_content_range(
    *,
    start_index: int,
    end_index: int,
    tab_id: Any,
    segment_id: str | None = None,
) -> dict[str, Any]:
    range_: dict[str, Any] = {
        "startIndex": start_index,
        "endIndex": end_index,
        "tabId": tab_id,
    }
    if segment_id:
        range_["segmentId"] = segment_id
    return {
        "deleteContentRange": {
            "range": range_,
        }
    }


def make_insert_text_in_story(
    *,
    index: int,
    tab_id: Any,
    segment_id: Any,
    text: str,
) -> dict[str, Any]:
    location: dict[str, Any] = {
        "index": index,
        "tabId": tab_id,
    }
    if segment_id:
        location["segmentId"] = segment_id
    return {
        "insertText": {
            "location": location,
            "text": text,
        }
    }


def make_delete_named_range(*, name: str) -> dict[str, Any]:
    return {"deleteNamedRange": {"name": name}}


def make_create_named_range(
    *,
    name: str,
    start_index: int,
    end_index: int,
    tab_id: Any,
    segment_id: str | None = None,
) -> dict[str, Any]:
    range_: dict[str, Any] = {
        "startIndex": start_index,
        "endIndex": end_index,
        "tabId": tab_id,
    }
    if segment_id:
        range_["segmentId"] = segment_id
    return {"createNamedRange": {"name": name, "range": range_}}


def make_insert_table(
    *,
    rows: int,
    columns: int,
    tab_id: Any,
    index: int | None = None,
    segment_id: str | None = None,
    end_of_segment: bool = False,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"rows": rows, "columns": columns}
    if end_of_segment:
        location: dict[str, Any] = {"tabId": tab_id}
        if segment_id:
            location["segmentId"] = segment_id
        payload["endOfSegmentLocation"] = location
    elif index is not None:
        location = {"index": index, "tabId": tab_id}
        if segment_id:
            location["segmentId"] = segment_id
        payload["location"] = location
    else:
        raise ValueError("insertTable requires either index or end_of_segment=True")
    return {"insertTable": payload}


def make_insert_table_row(
    *,
    table_start_index: int,
    row_index: int,
    insert_below: bool,
    tab_id: str,
) -> dict[str, Any]:
    return {
        "insertTableRow": {
            "tableCellLocation": {
                "tableStartLocation": {"index": table_start_index, "tabId": tab_id},
                "rowIndex": row_index,
                "columnIndex": 0,
            },
            "insertBelow": insert_below,
        }
    }


def make_delete_table_row(
    *,
    table_start_index: int,
    row_index: int,
    tab_id: str,
) -> dict[str, Any]:
    return {
        "deleteTableRow": {
            "tableCellLocation": {
                "tableStartLocation": {"index": table_start_index, "tabId": tab_id},
                "rowIndex": row_index,
                "columnIndex": 0,
            }
        }
    }


def make_insert_table_column(
    *,
    table_start_index: int,
    column_index: int,
    insert_right: bool,
    tab_id: str,
) -> dict[str, Any]:
    return {
        "insertTableColumn": {
            "tableCellLocation": {
                "tableStartLocation": {"index": table_start_index, "tabId": tab_id},
                "rowIndex": 0,
                "columnIndex": column_index,
            },
            "insertRight": insert_right,
        }
    }


def make_delete_table_column(
    *,
    table_start_index: int,
    column_index: int,
    tab_id: str,
) -> dict[str, Any]:
    return {
        "deleteTableColumn": {
            "tableCellLocation": {
                "tableStartLocation": {"index": table_start_index, "tabId": tab_id},
                "rowIndex": 0,
                "columnIndex": column_index,
            }
        }
    }


def make_merge_table_cells(
    *,
    table_start_index: int,
    row_index: int,
    column_index: int,
    row_span: int,
    column_span: int,
    tab_id: str,
) -> dict[str, Any]:
    return {
        "mergeTableCells": {
            "tableRange": {
                "tableCellLocation": {
                    "tableStartLocation": {"index": table_start_index, "tabId": tab_id},
                    "rowIndex": row_index,
                    "columnIndex": column_index,
                },
                "rowSpan": row_span,
                "columnSpan": column_span,
            }
        }
    }


def make_unmerge_table_cells(
    *,
    table_start_index: int,
    row_index: int,
    column_index: int,
    row_span: int,
    column_span: int,
    tab_id: str,
) -> dict[str, Any]:
    return {
        "unmergeTableCells": {
            "tableRange": {
                "tableCellLocation": {
                    "tableStartLocation": {"index": table_start_index, "tabId": tab_id},
                    "rowIndex": row_index,
                    "columnIndex": column_index,
                },
                "rowSpan": row_span,
                "columnSpan": column_span,
            }
        }
    }


def make_pin_table_header_rows(
    *,
    table_start_index: int,
    pinned_header_rows_count: int,
    tab_id: str,
) -> dict[str, Any]:
    return {
        "pinTableHeaderRows": {
            "tableStartLocation": {"index": table_start_index, "tabId": tab_id},
            "pinnedHeaderRowsCount": pinned_header_rows_count,
        }
    }


def make_update_table_row_style(
    *,
    table_start_index: int,
    row_index: int,
    style: dict[str, Any],
    fields: tuple[str, ...],
    tab_id: str,
) -> dict[str, Any]:
    return {
        "updateTableRowStyle": {
            "tableStartLocation": {"index": table_start_index, "tabId": tab_id},
            "rowIndices": [row_index],
            "tableRowStyle": style,
            "fields": ",".join(fields),
        }
    }


def make_update_table_column_properties(
    *,
    table_start_index: int,
    column_index: int,
    properties: dict[str, Any],
    fields: tuple[str, ...],
    tab_id: str,
) -> dict[str, Any]:
    return {
        "updateTableColumnProperties": {
            "tableStartLocation": {"index": table_start_index, "tabId": tab_id},
            "columnIndices": [column_index],
            "tableColumnProperties": properties,
            "fields": ",".join(fields),
        }
    }


def make_update_table_cell_style(
    *,
    table_start_index: int,
    row_index: int,
    column_index: int,
    style: dict[str, Any],
    fields: tuple[str, ...],
    tab_id: str,
) -> dict[str, Any]:
    return {
        "updateTableCellStyle": {
            "tableRange": {
                "tableCellLocation": {
                    "tableStartLocation": {"index": table_start_index, "tabId": tab_id},
                    "rowIndex": row_index,
                    "columnIndex": column_index,
                },
                "rowSpan": 1,
                "columnSpan": 1,
            },
            "tableCellStyle": style,
            "fields": ",".join(fields),
        }
    }


def bullet_preset_for_kind(kind: str) -> str:
    if kind == "NUMBERED":
        return "NUMBERED_DECIMAL_ALPHA_ROMAN"
    if kind == "CHECKBOX":
        return "BULLET_CHECKBOX"
    return "BULLET_DISC_CIRCLE_SQUARE"
