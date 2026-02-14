"""Table operations for the mock Google Docs API.

These handlers modify table structure. All index fixing is done by the
centralized reindex pass after each request.
"""

from __future__ import annotations

from typing import Any

from extradoc.mock.exceptions import ValidationError
from extradoc.mock.navigation import find_table_at_index, get_segment, get_tab
from extradoc.mock.reindex import reindex_segment
from extradoc.mock.text_ops import _insert_text_impl
from extradoc.mock.utils import make_empty_cell, table_cell_paragraph_style


def handle_insert_table(
    document: dict[str, Any],
    request: dict[str, Any],
    structure_tracker: Any,
) -> dict[str, Any]:
    """Handle InsertTableRequest."""
    rows = request.get("rows")
    columns = request.get("columns")
    location = request.get("location")
    end_of_segment = request.get("endOfSegmentLocation")

    if not rows or rows < 1:
        raise ValidationError("rows must be at least 1")
    if not columns or columns < 1:
        raise ValidationError("columns must be at least 1")

    if not location and not end_of_segment:
        raise ValidationError("Must specify either location or endOfSegmentLocation")
    if location and end_of_segment:
        raise ValidationError("Cannot specify both location and endOfSegmentLocation")

    if location:
        index = location["index"]
        tab_id = location.get("tabId")
        segment_id = location.get("segmentId")
    else:
        tab_id = end_of_segment.get("tabId") if end_of_segment else None
        segment_id = end_of_segment.get("segmentId") if end_of_segment else None
        tab = get_tab(document, tab_id)
        segment, _ = get_segment(tab, segment_id)
        seg_content = segment.get("content", [])
        index = seg_content[-1].get("endIndex", 1) - 1 if seg_content else 1

    # Validation
    if segment_id:
        tab = get_tab(document, tab_id)
        document_tab = tab.get("documentTab", {})
        footnotes = document_tab.get("footnotes", {})
        if segment_id in footnotes:
            raise ValidationError(
                "Cannot insert table in footnote. "
                "Tables can be inserted in body, headers, and footers, "
                "but not footnotes."
            )

    tab = get_tab(document, tab_id)
    if index < 1:
        raise ValidationError("index must be at least 1")

    segment, _ = get_segment(tab, segment_id)

    # Step 1: Insert \n to split the paragraph at the insertion point
    _insert_text_impl(document, "\n", index, tab_id, segment_id)

    # Run reindex so we can find the split point by index
    tab = get_tab(document, tab_id)
    segment, _ = get_segment(tab, segment_id)
    is_body = segment_id is None
    reindex_segment(segment, is_body=is_body)

    # Step 2: Find the content array position right after the split
    content = segment.get("content", [])
    inject_idx = None
    for i, element in enumerate(content):
        if element.get("startIndex", 0) == index + 1:
            inject_idx = i
            break

    if inject_idx is None:
        raise ValidationError(
            f"Could not find insertion point for table at index {index}"
        )

    # Step 3: Resolve inherited textStyle from the preceding paragraph's named style.
    # The real API propagates textStyle properties (e.g. fontSize) from the preceding
    # paragraph's named style into newly created table cells.
    inherited_text_style = _resolve_preceding_text_style(tab, inject_idx, content)

    # Step 4: Build table element (indices will be fixed by reindex)
    table_elem = _build_table_element(rows, columns, inherited_text_style)

    # Step 5: Insert table into content array
    content.insert(inject_idx, table_elem)

    # No index shifting — reindex handles it
    return {}


def _resolve_preceding_text_style(
    tab: dict[str, Any],
    inject_idx: int,
    content: list[dict[str, Any]],
) -> dict[str, Any]:
    """Resolve inherited textStyle from the preceding paragraph's named style.

    When the real API inserts a table after an empty heading paragraph (one
    whose only content is the trailing newline), cells inherit textStyle
    properties (like fontSize) from the heading's named style definition.
    Non-empty paragraphs do not trigger this inheritance.
    """
    # Find the paragraph just before the insertion point
    if inject_idx <= 0:
        return {}

    prev_element = content[inject_idx - 1]
    paragraph = prev_element.get("paragraph")
    if not paragraph:
        return {}

    # Only inherit from empty paragraphs (just the trailing "\n")
    elements = paragraph.get("elements", [])
    text = "".join(el.get("textRun", {}).get("content", "") for el in elements)
    if text != "\n":
        return {}

    ps = paragraph.get("paragraphStyle", {})
    named_style_type = ps.get("namedStyleType", "NORMAL_TEXT")
    if named_style_type == "NORMAL_TEXT":
        return {}

    # Look up the named style's textStyle in the document
    document_tab = tab.get("documentTab", {})
    named_styles = document_tab.get("namedStyles", {}).get("styles", [])
    for style_def in named_styles:
        if style_def.get("namedStyleType") == named_style_type:
            return dict(style_def.get("textStyle", {}))

    return {}


def _build_table_element(
    rows: int, columns: int, cell_text_style: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Build a complete table element. Indices set to 0 — reindex fixes them."""
    text_style = dict(cell_text_style) if cell_text_style else {}
    table_rows: list[dict[str, Any]] = []

    for _r in range(rows):
        cells: list[dict[str, Any]] = []
        for _c in range(columns):
            cells.append(
                {
                    "startIndex": 0,
                    "endIndex": 0,
                    "content": [
                        {
                            "startIndex": 0,
                            "endIndex": 0,
                            "paragraph": {
                                "elements": [
                                    {
                                        "startIndex": 0,
                                        "endIndex": 0,
                                        "textRun": {
                                            "content": "\n",
                                            "textStyle": dict(text_style),
                                        },
                                    }
                                ],
                                "paragraphStyle": table_cell_paragraph_style(),
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
            )

        table_rows.append(
            {
                "startIndex": 0,
                "endIndex": 0,
                "tableCells": cells,
                "tableRowStyle": {"minRowHeight": {"unit": "PT"}},
            }
        )

    return {
        "startIndex": 0,
        "endIndex": 0,
        "table": {
            "rows": rows,
            "columns": columns,
            "tableRows": table_rows,
            "tableStyle": {
                "tableColumnProperties": [
                    {"widthType": "EVENLY_DISTRIBUTED"} for _ in range(columns)
                ],
            },
        },
    }


def handle_insert_table_row(
    document: dict[str, Any],
    request: dict[str, Any],
    structure_tracker: Any,
) -> dict[str, Any]:
    """Handle InsertTableRowRequest."""
    table_cell_location = request.get("tableCellLocation")
    if not table_cell_location:
        raise ValidationError("tableCellLocation is required")

    insert_below = request.get("insertBelow", False)

    table_start_location = table_cell_location.get("tableStartLocation", {})
    row_index = table_cell_location.get("rowIndex", 0)
    tab_id = table_start_location.get("tabId")
    segment_id = table_start_location.get("segmentId")
    table_start_idx = table_start_location.get("index")

    tab = get_tab(document, tab_id)
    segment, _ = get_segment(tab, segment_id)
    table_element, _elem_idx = find_table_at_index(segment, table_start_idx)
    table = table_element["table"]
    table_rows = table.get("tableRows", [])
    num_cols = table.get("columns", 0)

    if row_index < 0 or row_index >= len(table_rows):
        raise ValidationError(
            f"rowIndex {row_index} out of range (0-{len(table_rows) - 1})"
        )

    target_row_idx = row_index + 1 if insert_below else row_index

    # Build new row with empty cells
    new_cells: list[dict[str, Any]] = []
    for _c in range(num_cols):
        new_cells.append(
            {
                "startIndex": 0,
                "endIndex": 0,
                "content": [
                    {
                        "startIndex": 0,
                        "endIndex": 0,
                        "paragraph": {
                            "elements": [
                                {
                                    "startIndex": 0,
                                    "endIndex": 0,
                                    "textRun": {
                                        "content": "\n",
                                        "textStyle": {},
                                    },
                                }
                            ],
                            "paragraphStyle": table_cell_paragraph_style(),
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
        )

    new_row = {
        "startIndex": 0,
        "endIndex": 0,
        "tableCells": new_cells,
        "tableRowStyle": {"minRowHeight": {"unit": "PT"}},
    }

    table_rows.insert(target_row_idx, new_row)
    table["rows"] = len(table_rows)

    # No index shifting — reindex handles it
    return {}


def handle_insert_table_column(
    document: dict[str, Any],
    request: dict[str, Any],
    structure_tracker: Any,
) -> dict[str, Any]:
    """Handle InsertTableColumnRequest."""
    table_cell_location = request.get("tableCellLocation")
    if not table_cell_location:
        raise ValidationError("tableCellLocation is required")

    insert_right = request.get("insertRight", False)

    table_start_location = table_cell_location.get("tableStartLocation", {})
    col_index = table_cell_location.get("columnIndex", 0)
    tab_id = table_start_location.get("tabId")
    segment_id = table_start_location.get("segmentId")
    table_start_idx = table_start_location.get("index")

    tab = get_tab(document, tab_id)
    segment, _ = get_segment(tab, segment_id)
    table_element, _elem_idx = find_table_at_index(segment, table_start_idx)
    table = table_element["table"]
    table_rows = table.get("tableRows", [])
    num_cols = table.get("columns", 0)

    if col_index < 0 or col_index >= num_cols:
        raise ValidationError(
            f"columnIndex {col_index} out of range (0-{num_cols - 1})"
        )

    target_col_idx = col_index + 1 if insert_right else col_index

    for row in table_rows:
        cells = row.get("tableCells", [])
        new_cell = make_empty_cell(0)
        cells.insert(target_col_idx, new_cell)

    table["columns"] = num_cols + 1

    # Update tableColumnProperties
    table_style = table.setdefault("tableStyle", {})
    col_props = table_style.get("tableColumnProperties", [])
    if col_props:
        col_props.insert(target_col_idx, {"widthType": "EVENLY_DISTRIBUTED"})
        table_style["tableColumnProperties"] = col_props

    # No index recalculation or shifting — reindex handles it
    return {}


def handle_delete_table_row(
    document: dict[str, Any],
    request: dict[str, Any],
    structure_tracker: Any,
) -> dict[str, Any]:
    """Handle DeleteTableRowRequest."""
    table_cell_location = request.get("tableCellLocation")
    if not table_cell_location:
        raise ValidationError("tableCellLocation is required")

    table_start_location = table_cell_location.get("tableStartLocation", {})
    row_index = table_cell_location.get("rowIndex", 0)
    tab_id = table_start_location.get("tabId")
    segment_id = table_start_location.get("segmentId")
    table_start_idx = table_start_location.get("index")

    tab = get_tab(document, tab_id)
    segment, _ = get_segment(tab, segment_id)
    table_element, elem_idx = find_table_at_index(segment, table_start_idx)
    table = table_element["table"]
    table_rows = table.get("tableRows", [])

    if row_index < 0 or row_index >= len(table_rows):
        raise ValidationError(
            f"rowIndex {row_index} out of range (0-{len(table_rows) - 1})"
        )

    content = segment.get("content", [])

    if len(table_rows) <= 1:
        # Delete entire table
        content.pop(elem_idx)
    else:
        table_rows.pop(row_index)
        table["rows"] = len(table_rows)

    # No index shifting — reindex handles it
    return {}


def handle_delete_table_column(
    document: dict[str, Any],
    request: dict[str, Any],
    structure_tracker: Any,
) -> dict[str, Any]:
    """Handle DeleteTableColumnRequest."""
    table_cell_location = request.get("tableCellLocation")
    if not table_cell_location:
        raise ValidationError("tableCellLocation is required")

    table_start_location = table_cell_location.get("tableStartLocation", {})
    col_index = table_cell_location.get("columnIndex", 0)
    tab_id = table_start_location.get("tabId")
    segment_id = table_start_location.get("segmentId")
    table_start_idx = table_start_location.get("index")

    tab = get_tab(document, tab_id)
    segment, _ = get_segment(tab, segment_id)
    table_element, elem_idx = find_table_at_index(segment, table_start_idx)
    table = table_element["table"]
    table_rows = table.get("tableRows", [])
    num_cols = table.get("columns", 0)

    if col_index < 0 or col_index >= num_cols:
        raise ValidationError(
            f"columnIndex {col_index} out of range (0-{num_cols - 1})"
        )

    content = segment.get("content", [])

    if num_cols <= 1:
        # Delete entire table
        content.pop(elem_idx)
    else:
        for row in table_rows:
            cells = row.get("tableCells", [])
            if col_index < len(cells):
                cells.pop(col_index)
        table["columns"] = num_cols - 1

        # Update tableColumnProperties
        table_style = table.get("tableStyle", {})
        col_props = table_style.get("tableColumnProperties", [])
        if col_props and col_index < len(col_props):
            col_props.pop(col_index)

    # No index shifting or recalculation — reindex handles it
    return {}
