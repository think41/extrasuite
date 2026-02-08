"""Table request generation for Google Docs batchUpdate.

Generates requests for table operations including:
- Table structure (insert/delete rows and columns)
"""

from __future__ import annotations

from typing import Any


def generate_insert_table_row_request(
    table_start_index: int,
    row_index: int,
    segment_id: str | None = None,
    insert_below: bool = True,
    tab_id: str | None = None,
) -> dict[str, Any]:
    """Generate an insertTableRow request.

    Args:
        table_start_index: Start index of the table
        row_index: Reference row index
        segment_id: Optional segment ID
        insert_below: If True, insert below the reference row; if False, above
        tab_id: Optional tab ID

    Returns:
        An insertTableRow request dict
    """
    table_start_loc: dict[str, Any] = {"index": table_start_index}
    if segment_id:
        table_start_loc["segmentId"] = segment_id
    if tab_id:
        table_start_loc["tabId"] = tab_id

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
    tab_id: str | None = None,
) -> dict[str, Any]:
    """Generate a deleteTableRow request.

    Args:
        table_start_index: Start index of the table
        row_index: Row index to delete
        segment_id: Optional segment ID
        tab_id: Optional tab ID

    Returns:
        A deleteTableRow request dict
    """
    table_start_loc: dict[str, Any] = {"index": table_start_index}
    if segment_id:
        table_start_loc["segmentId"] = segment_id
    if tab_id:
        table_start_loc["tabId"] = tab_id

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
    tab_id: str | None = None,
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
        tab_id: Optional tab ID

    Returns:
        An insertTableColumn request dict
    """
    table_start_loc: dict[str, Any] = {"index": table_start_index}
    if segment_id:
        table_start_loc["segmentId"] = segment_id
    if tab_id:
        table_start_loc["tabId"] = tab_id

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
    tab_id: str | None = None,
) -> dict[str, Any]:
    """Generate a deleteTableColumn request.

    Args:
        table_start_index: Start index of the table
        row_index: Row index for cell location
        col_index: Column index to delete
        segment_id: Optional segment ID
        tab_id: Optional tab ID

    Returns:
        A deleteTableColumn request dict
    """
    table_start_loc: dict[str, Any] = {"index": table_start_index}
    if segment_id:
        table_start_loc["segmentId"] = segment_id
    if tab_id:
        table_start_loc["tabId"] = tab_id

    return {
        "deleteTableColumn": {
            "tableCellLocation": {
                "tableStartLocation": table_start_loc,
                "rowIndex": row_index,
                "columnIndex": col_index,
            },
        }
    }
