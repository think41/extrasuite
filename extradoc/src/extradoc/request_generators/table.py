"""Table request generation for Google Docs batchUpdate.

Generates requests for table operations including:
- Table cell styling (background color, alignment, padding)
- Table structure (insert/delete rows and columns)
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

from extradoc.style_converter import (
    TABLE_CELL_STYLE_PROPS,
    build_table_cell_style_request,
    convert_styles,
)


def generate_table_cell_style_requests(
    table_xml: str,
    table_start_index: int,
    segment_id: str | None = None,
) -> list[dict[str, Any]]:
    """Generate updateTableCellStyle requests for all styled cells in a table.

    Parses the table XML and generates style requests for any cells that have
    style attributes (bg, valign, padding, etc.).

    Args:
        table_xml: XML string of the table element
        table_start_index: The start index of the table in the document
        segment_id: Optional segment ID for headers/footers/footnotes

    Returns:
        List of updateTableCellStyle request dicts
    """
    try:
        root = ET.fromstring(table_xml)
    except ET.ParseError:
        return []

    requests: list[dict[str, Any]] = []

    for row_idx, tr in enumerate(root.findall("tr")):
        for col_idx, td in enumerate(tr.findall("td")):
            # Extract style attributes from the cell
            styles = dict(td.attrib)

            # Check if there are any style properties
            _, fields = convert_styles(styles, TABLE_CELL_STYLE_PROPS)
            if fields:
                req = build_table_cell_style_request(
                    styles,
                    table_start_index,
                    row_idx,
                    col_idx,
                    segment_id,
                )
                if req:
                    requests.append(req)

    return requests


def calculate_cell_positions(
    table_start: int,
    rows: int,
    cols: int,
) -> dict[tuple[int, int], int]:
    """Calculate the insertion index for each cell in a freshly inserted table.

    For a newly inserted table with empty cells, calculates the index where
    content should be inserted for each (row, col) position.

    Table structure in Google Docs:
    - table_start: table marker (1 index)
    - row_start: row marker (1 index per row)
    - cell_start: cell marker (1 index per cell)
    - cell_content: empty paragraph (1 index for newline)
    - table_end: end marker (1 index)

    Args:
        table_start: The start index of the table
        rows: Number of rows in the table
        cols: Number of columns in the table

    Returns:
        Dict mapping (row, col) tuples to cell content insertion indexes
    """
    positions: dict[tuple[int, int], int] = {}
    idx = table_start + 1  # After table start marker

    for row in range(rows):
        idx += 1  # Row marker
        for col in range(cols):
            idx += 1  # Cell marker
            positions[(row, col)] = idx
            idx += 1  # Default empty paragraph (1 character for newline)

    return positions


def calculate_table_length(rows: int, cols: int) -> int:
    """Calculate the minimum length of an empty table.

    Args:
        rows: Number of rows
        cols: Number of columns

    Returns:
        The total index length of the table structure
    """
    # 1 (table start) + rows * (1 row marker + cols * 2 (cell marker + newline)) + 1 (table end)
    return 1 + rows * (1 + cols * 2) + 1


def generate_insert_table_request(
    rows: int,
    cols: int,
    insert_index: int | None = None,
    segment_id: str | None = None,
) -> dict[str, Any]:
    """Generate an insertTable request.

    Args:
        rows: Number of rows
        cols: Number of columns
        insert_index: Index to insert at, or None for end of segment
        segment_id: Optional segment ID

    Returns:
        An insertTable request dict
    """
    req: dict[str, Any] = {
        "insertTable": {
            "rows": rows,
            "columns": cols,
        }
    }

    if insert_index is not None:
        location: dict[str, Any] = {"index": insert_index}
        if segment_id:
            location["segmentId"] = segment_id
        req["insertTable"]["location"] = location
    else:
        end_loc: dict[str, Any] = {}
        if segment_id:
            end_loc["segmentId"] = segment_id
        req["insertTable"]["endOfSegmentLocation"] = end_loc

    return req


def generate_insert_table_row_request(
    table_start_index: int,
    row_index: int,
    segment_id: str | None = None,
    insert_below: bool = True,
) -> dict[str, Any]:
    """Generate an insertTableRow request.

    Args:
        table_start_index: Start index of the table
        row_index: Reference row index
        segment_id: Optional segment ID
        insert_below: If True, insert below the reference row; if False, above

    Returns:
        An insertTableRow request dict
    """
    table_start_loc: dict[str, Any] = {"index": table_start_index}
    if segment_id:
        table_start_loc["segmentId"] = segment_id

    return {
        "insertTableRow": {
            "tableCellLocation": {
                "tableStartLocation": table_start_loc,
                "rowIndex": row_index,
                "columnIndex": 0,  # Any valid column works
            },
            "insertBelow": insert_below,
        }
    }


def generate_delete_table_row_request(
    table_start_index: int,
    row_index: int,
    segment_id: str | None = None,
) -> dict[str, Any]:
    """Generate a deleteTableRow request.

    Args:
        table_start_index: Start index of the table
        row_index: Row index to delete
        segment_id: Optional segment ID

    Returns:
        A deleteTableRow request dict
    """
    table_start_loc: dict[str, Any] = {"index": table_start_index}
    if segment_id:
        table_start_loc["segmentId"] = segment_id

    return {
        "deleteTableRow": {
            "tableCellLocation": {
                "tableStartLocation": table_start_loc,
                "rowIndex": row_index,
                "columnIndex": 0,
            },
        }
    }


def generate_insert_table_column_request(
    table_start_index: int,
    row_index: int,
    col_index: int,
    segment_id: str | None = None,
) -> dict[str, Any]:
    """Generate an insertTableColumn request.

    The col_index is the NEW column's desired position. We need to convert this
    to a valid existing column reference:
    - For col_index > 0: insert to the right of column col_index - 1
    - For col_index == 0: insert to the left of column 0

    Args:
        table_start_index: Start index of the table
        row_index: Row index for cell location
        col_index: Desired position of new column
        segment_id: Optional segment ID

    Returns:
        An insertTableColumn request dict
    """
    table_start_loc: dict[str, Any] = {"index": table_start_index}
    if segment_id:
        table_start_loc["segmentId"] = segment_id

    if col_index == 0:
        # Insert as first column - insert to left of column 0
        return {
            "insertTableColumn": {
                "tableCellLocation": {
                    "tableStartLocation": table_start_loc,
                    "rowIndex": row_index,
                    "columnIndex": 0,
                },
                "insertRight": False,
            }
        }
    else:
        # Insert to the right of the previous column
        return {
            "insertTableColumn": {
                "tableCellLocation": {
                    "tableStartLocation": table_start_loc,
                    "rowIndex": row_index,
                    "columnIndex": col_index - 1,
                },
                "insertRight": True,
            }
        }


def generate_delete_table_column_request(
    table_start_index: int,
    row_index: int,
    col_index: int,
    segment_id: str | None = None,
) -> dict[str, Any]:
    """Generate a deleteTableColumn request.

    Args:
        table_start_index: Start index of the table
        row_index: Row index for cell location
        col_index: Column index to delete
        segment_id: Optional segment ID

    Returns:
        A deleteTableColumn request dict
    """
    table_start_loc: dict[str, Any] = {"index": table_start_index}
    if segment_id:
        table_start_loc["segmentId"] = segment_id

    return {
        "deleteTableColumn": {
            "tableCellLocation": {
                "tableStartLocation": table_start_loc,
                "rowIndex": row_index,
                "columnIndex": col_index,
            },
        }
    }
