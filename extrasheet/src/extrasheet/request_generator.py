"""Generate Google Sheets batchUpdate requests from DiffResult."""

from __future__ import annotations

from typing import Any

from extrasheet.diff import (
    BandedRangeChange,
    BasicFilterChange,
    CellChange,
    ChartChange,
    ConditionalFormatChange,
    DataValidationChange,
    DeletedSheetChange,
    DiffResult,
    DimensionChange,
    FilterViewChange,
    FormatRuleChange,
    FormulaChange,
    MergeChange,
    NewSheetChange,
    NoteChange,
    PivotTableChange,
    SheetDiff,
    SheetPropertyChange,
    SpreadsheetPropertyChange,
    TextFormatRunChange,
    range_to_indices,
)
from extrasheet.utils import a1_range_to_grid_range, a1_to_cell


def generate_requests(diff_result: DiffResult) -> list[dict[str, Any]]:
    """Generate batchUpdate requests from a DiffResult.

    Args:
        diff_result: DiffResult from diff()

    Returns:
        List of batchUpdate request objects

    Request ordering:
    1. Spreadsheet property changes
    2. New sheet additions
    3. Grid changes (insert/delete rows/columns) - BEFORE content changes
    4. Sheet property changes
    5. Sheet content changes
    6. Deleted sheets - LAST (after all content is handled)
    """
    requests: list[dict[str, Any]] = []

    # Spreadsheet property changes
    requests.extend(
        _generate_spreadsheet_property_requests(diff_result.spreadsheet_changes)
    )

    # New sheet additions (must come before content changes for those sheets)
    requests.extend(_generate_new_sheet_requests(diff_result.new_sheet_changes))

    # Grid changes (insert/delete rows/columns) - must come before content changes
    # because content positions depend on the grid structure
    for sheet_diff in diff_result.sheet_diffs:
        requests.extend(_generate_grid_change_requests(sheet_diff))

    # Sheet property changes
    requests.extend(
        _generate_sheet_property_requests(diff_result.sheet_property_changes)
    )

    # Sheet content changes
    for sheet_diff in diff_result.sheet_diffs:
        requests.extend(_generate_sheet_requests(sheet_diff))

    # Deleted sheets (must come last after all content is handled)
    requests.extend(_generate_deleted_sheet_requests(diff_result.deleted_sheet_changes))

    return requests


def _generate_new_sheet_requests(
    changes: list[NewSheetChange],
) -> list[dict[str, Any]]:
    """Generate addSheet requests for new sheets."""
    requests: list[dict[str, Any]] = []

    for change in changes:
        requests.append({"addSheet": {"properties": change.properties}})

    return requests


def _generate_deleted_sheet_requests(
    changes: list[DeletedSheetChange],
) -> list[dict[str, Any]]:
    """Generate deleteSheet requests for deleted sheets."""
    requests: list[dict[str, Any]] = []

    for change in changes:
        requests.append({"deleteSheet": {"sheetId": change.sheet_id}})

    return requests


def _generate_grid_change_requests(sheet_diff: SheetDiff) -> list[dict[str, Any]]:
    """Generate insertDimension/deleteDimension requests for grid changes."""
    requests: list[dict[str, Any]] = []

    for change in sheet_diff.grid_changes:
        if change.change_type == "insert_rows":
            requests.append(
                {
                    "insertDimension": {
                        "range": {
                            "sheetId": sheet_diff.sheet_id,
                            "dimension": "ROWS",
                            "startIndex": change.start_index,
                            "endIndex": change.end_index,
                        },
                        "inheritFromBefore": change.start_index > 0,
                    }
                }
            )
        elif change.change_type == "delete_rows":
            requests.append(
                {
                    "deleteDimension": {
                        "range": {
                            "sheetId": sheet_diff.sheet_id,
                            "dimension": "ROWS",
                            "startIndex": change.start_index,
                            "endIndex": change.end_index,
                        }
                    }
                }
            )
        elif change.change_type == "insert_columns":
            requests.append(
                {
                    "insertDimension": {
                        "range": {
                            "sheetId": sheet_diff.sheet_id,
                            "dimension": "COLUMNS",
                            "startIndex": change.start_index,
                            "endIndex": change.end_index,
                        },
                        "inheritFromBefore": change.start_index > 0,
                    }
                }
            )
        elif change.change_type == "delete_columns":
            requests.append(
                {
                    "deleteDimension": {
                        "range": {
                            "sheetId": sheet_diff.sheet_id,
                            "dimension": "COLUMNS",
                            "startIndex": change.start_index,
                            "endIndex": change.end_index,
                        }
                    }
                }
            )

    return requests


def _generate_spreadsheet_property_requests(
    changes: list[SpreadsheetPropertyChange],
) -> list[dict[str, Any]]:
    """Generate updateSpreadsheetProperties requests."""
    if not changes:
        return []

    properties: dict[str, Any] = {}
    fields: list[str] = []

    for change in changes:
        if change.property_name == "title":
            properties["title"] = change.new_value
            fields.append("title")

    if not properties:
        return []

    return [
        {
            "updateSpreadsheetProperties": {
                "properties": properties,
                "fields": ",".join(fields),
            }
        }
    ]


def _generate_sheet_property_requests(
    changes: list[SheetPropertyChange],
) -> list[dict[str, Any]]:
    """Generate updateSheetProperties requests."""
    requests: list[dict[str, Any]] = []

    # Group changes by sheet_id
    changes_by_sheet: dict[int, list[SheetPropertyChange]] = {}
    for change in changes:
        if change.sheet_id not in changes_by_sheet:
            changes_by_sheet[change.sheet_id] = []
        changes_by_sheet[change.sheet_id].append(change)

    for sheet_id, sheet_changes in changes_by_sheet.items():
        properties: dict[str, Any] = {"sheetId": sheet_id}
        fields: list[str] = []
        grid_properties: dict[str, Any] = {}
        grid_fields: list[str] = []

        for change in sheet_changes:
            if change.property_name == "title":
                properties["title"] = change.new_value
                fields.append("title")
            elif change.property_name == "hidden":
                properties["hidden"] = change.new_value
                fields.append("hidden")
            elif change.property_name == "frozenRowCount":
                grid_properties["frozenRowCount"] = change.new_value or 0
                grid_fields.append("frozenRowCount")
            elif change.property_name == "frozenColumnCount":
                grid_properties["frozenColumnCount"] = change.new_value or 0
                grid_fields.append("frozenColumnCount")

        if grid_properties:
            properties["gridProperties"] = grid_properties
            fields.extend([f"gridProperties.{f}" for f in grid_fields])

        if fields:
            requests.append(
                {
                    "updateSheetProperties": {
                        "properties": properties,
                        "fields": ",".join(fields),
                    }
                }
            )

    return requests


def _generate_sheet_requests(sheet_diff: SheetDiff) -> list[dict[str, Any]]:
    """Generate all requests for a single sheet."""
    requests: list[dict[str, Any]] = []

    # Cell value changes
    requests.extend(
        _generate_cell_requests(sheet_diff.cell_changes, sheet_diff.sheet_id)
    )

    # Formula changes
    requests.extend(
        _generate_formula_requests(sheet_diff.formula_changes, sheet_diff.sheet_id)
    )

    # Format rule changes
    requests.extend(
        _generate_format_rule_requests(
            sheet_diff.format_rule_changes, sheet_diff.sheet_id
        )
    )

    # Data validation changes
    requests.extend(
        _generate_data_validation_requests(
            sheet_diff.data_validation_changes, sheet_diff.sheet_id
        )
    )

    # Dimension changes
    requests.extend(
        _generate_dimension_requests(sheet_diff.dimension_changes, sheet_diff.sheet_id)
    )

    # Text format run changes (rich text)
    requests.extend(
        _generate_text_format_run_requests(
            sheet_diff.text_format_run_changes, sheet_diff.sheet_id
        )
    )

    # Note changes
    requests.extend(
        _generate_note_requests(sheet_diff.note_changes, sheet_diff.sheet_id)
    )

    # Merge changes
    requests.extend(
        _generate_merge_requests(sheet_diff.merge_changes, sheet_diff.sheet_id)
    )

    # Conditional format changes
    requests.extend(
        _generate_conditional_format_requests(
            sheet_diff.conditional_format_changes, sheet_diff.sheet_id
        )
    )

    # Basic filter change
    if sheet_diff.basic_filter_change:
        requests.extend(
            _generate_basic_filter_requests(
                sheet_diff.basic_filter_change, sheet_diff.sheet_id
            )
        )

    # Banded range changes
    requests.extend(
        _generate_banded_range_requests(
            sheet_diff.banded_range_changes, sheet_diff.sheet_id
        )
    )

    # Filter view changes
    requests.extend(
        _generate_filter_view_requests(
            sheet_diff.filter_view_changes, sheet_diff.sheet_id
        )
    )

    # Chart changes
    requests.extend(
        _generate_chart_requests(sheet_diff.chart_changes, sheet_diff.sheet_id)
    )

    # Pivot table changes
    requests.extend(
        _generate_pivot_table_requests(
            sheet_diff.pivot_table_changes, sheet_diff.sheet_id
        )
    )

    return requests


def _generate_cell_requests(
    changes: list[CellChange], sheet_id: int
) -> list[dict[str, Any]]:
    """Generate updateCells requests for cell value changes.

    Groups contiguous changes by row for efficiency. Non-contiguous changes
    in the same row are split into separate requests to avoid clearing
    cells in between.
    """
    if not changes:
        return []

    requests: list[dict[str, Any]] = []

    # Group changes by row
    changes_by_row: dict[int, list[CellChange]] = {}
    for change in changes:
        if change.row not in changes_by_row:
            changes_by_row[change.row] = []
        changes_by_row[change.row].append(change)

    for row_idx, row_changes in changes_by_row.items():
        # Sort by column
        row_changes.sort(key=lambda c: c.col)

        # Split into contiguous groups to avoid clearing cells in gaps
        contiguous_groups = _split_into_contiguous_groups(row_changes)

        for group in contiguous_groups:
            start_col = group[0].col
            values: list[dict[str, Any]] = []
            for change in group:
                values.append({"userEnteredValue": _infer_value_type(change.new_value)})

            requests.append(
                {
                    "updateCells": {
                        "rows": [{"values": values}],
                        "fields": "userEnteredValue",
                        "start": {
                            "sheetId": sheet_id,
                            "rowIndex": row_idx,
                            "columnIndex": start_col,
                        },
                    }
                }
            )

    return requests


def _split_into_contiguous_groups(
    changes: list[CellChange],
) -> list[list[CellChange]]:
    """Split changes into contiguous groups.

    Changes are contiguous if their columns are adjacent (differ by 1).
    """
    if not changes:
        return []

    groups: list[list[CellChange]] = []
    current_group: list[CellChange] = [changes[0]]

    for i in range(1, len(changes)):
        prev_col = changes[i - 1].col
        curr_col = changes[i].col

        if curr_col == prev_col + 1:
            # Contiguous - add to current group
            current_group.append(changes[i])
        else:
            # Gap - start new group
            groups.append(current_group)
            current_group = [changes[i]]

    # Don't forget the last group
    groups.append(current_group)
    return groups


def _generate_formula_requests(
    changes: list[FormulaChange], sheet_id: int
) -> list[dict[str, Any]]:
    """Generate requests for formula changes.

    For single cells: updateCells
    For ranges: updateCells + autoFill
    For deleted formulas: updateCells to clear the cells
    """
    requests: list[dict[str, Any]] = []

    for change in changes:
        if change.change_type == "deleted":
            # Formula removed - clear the cells
            requests.extend(_generate_formula_delete_requests(change, sheet_id))
        elif change.is_range:
            # Range formula: updateCells for first cell + autoFill
            requests.extend(_generate_formula_range_requests(change, sheet_id))
        else:
            # Single cell formula: just updateCells
            requests.append(_generate_single_formula_request(change, sheet_id))

    return requests


def _generate_single_formula_request(
    change: FormulaChange, sheet_id: int
) -> dict[str, Any]:
    """Generate updateCells request for a single-cell formula."""
    row, col = a1_to_cell(change.range_key)

    return {
        "updateCells": {
            "rows": [
                {"values": [{"userEnteredValue": {"formulaValue": change.new_formula}}]}
            ],
            "fields": "userEnteredValue",
            "start": {
                "sheetId": sheet_id,
                "rowIndex": row,
                "columnIndex": col,
            },
        }
    }


def _generate_formula_range_requests(
    change: FormulaChange, sheet_id: int
) -> list[dict[str, Any]]:
    """Generate requests for a formula range change.

    Uses updateCells to set the formula in the first cell,
    then autoFill to copy it to the entire range.
    """
    start_row, start_col, end_row, end_col = range_to_indices(change.range_key)

    requests: list[dict[str, Any]] = []

    # 1. Set formula in the first cell
    requests.append(
        {
            "updateCells": {
                "rows": [
                    {
                        "values": [
                            {"userEnteredValue": {"formulaValue": change.new_formula}}
                        ]
                    }
                ],
                "fields": "userEnteredValue",
                "start": {
                    "sheetId": sheet_id,
                    "rowIndex": start_row,
                    "columnIndex": start_col,
                },
            }
        }
    )

    # 2. AutoFill to the rest of the range (only if range spans more than one cell)
    if end_row > start_row or end_col > start_col:
        # Determine dimension and fill length
        # If range spans multiple rows in same column, fill by ROWS
        # If range spans multiple columns in same row, fill by COLUMNS
        if end_row > start_row:
            dimension = "ROWS"
            fill_length = end_row - start_row
        else:
            dimension = "COLUMNS"
            fill_length = end_col - start_col

        requests.append(
            {
                "autoFill": {
                    "useAlternateSeries": False,
                    "sourceAndDestination": {
                        "source": {
                            "sheetId": sheet_id,
                            "startRowIndex": start_row,
                            "endRowIndex": start_row + 1,
                            "startColumnIndex": start_col,
                            "endColumnIndex": start_col + 1,
                        },
                        "dimension": dimension,
                        "fillLength": fill_length,
                    },
                }
            }
        )

    return requests


def _generate_formula_delete_requests(
    change: FormulaChange, sheet_id: int
) -> list[dict[str, Any]]:
    """Generate requests to clear cells where formulas were deleted.

    For single cells: one updateCells request
    For ranges: one updateCells request covering the entire range
    """
    start_row, start_col, end_row, end_col = range_to_indices(change.range_key)

    # Calculate number of rows and columns
    num_rows = end_row - start_row + 1
    num_cols = end_col - start_col + 1

    # Build rows with empty values
    rows: list[dict[str, Any]] = []
    for _ in range(num_rows):
        row_values: list[dict[str, Any]] = [
            {"userEnteredValue": {}} for _ in range(num_cols)
        ]
        rows.append({"values": row_values})

    return [
        {
            "updateCells": {
                "rows": rows,
                "fields": "userEnteredValue",
                "start": {
                    "sheetId": sheet_id,
                    "rowIndex": start_row,
                    "columnIndex": start_col,
                },
            }
        }
    ]


def _infer_value_type(value: str | None) -> dict[str, Any]:
    """Infer the ExtendedValue type from a string value.

    Returns appropriate userEnteredValue structure for Google Sheets API.
    """
    if value is None or value == "":
        return {}  # Empty cell

    # Check for boolean
    if value.upper() == "TRUE":
        return {"boolValue": True}
    if value.upper() == "FALSE":
        return {"boolValue": False}

    # Try to parse as number
    try:
        # Handle numbers with commas (e.g., "1,234.56")
        clean_value = value.replace(",", "")
        num = float(clean_value)
        # Return as int if it's a whole number
        if num == int(num):
            return {"numberValue": int(num)}
        return {"numberValue": num}
    except ValueError:
        pass

    # Default to string
    return {"stringValue": value}


def _generate_format_rule_requests(
    changes: list[FormatRuleChange], sheet_id: int
) -> list[dict[str, Any]]:
    """Generate requests for format rule changes.

    Uses repeatCell to apply formatting to ranges.
    """
    requests: list[dict[str, Any]] = []

    for change in changes:
        grid_range = a1_range_to_grid_range(change.range_key, sheet_id)

        if change.change_type == "deleted":
            # To delete formatting, we'd need to clear the format
            # For now, we skip deleted format rules as clearing is complex
            continue

        if change.change_type in ("added", "modified"):
            # Convert simplified format to Google Sheets CellFormat
            cell_format = _convert_to_cell_format(change.new_format)
            fields = _get_format_fields(change.new_format)

            if cell_format and fields:
                requests.append(
                    {
                        "repeatCell": {
                            "range": grid_range,
                            "cell": {"userEnteredFormat": cell_format},
                            "fields": f"userEnteredFormat({fields})",
                        }
                    }
                )

    return requests


def _convert_to_cell_format(format_dict: dict[str, Any] | None) -> dict[str, Any]:
    """Convert simplified format dict to Google Sheets CellFormat."""
    if not format_dict:
        return {}

    cell_format: dict[str, Any] = {}

    # Number format
    if "numberFormat" in format_dict:
        cell_format["numberFormat"] = format_dict["numberFormat"]

    # Background color (convert hex to RGB)
    if "backgroundColor" in format_dict:
        cell_format["backgroundColor"] = _hex_to_rgb(format_dict["backgroundColor"])

    # Text format (convert colors from hex to RGB)
    if "textFormat" in format_dict:
        cell_format["textFormat"] = _convert_text_format(format_dict["textFormat"])

    # Alignment
    if "horizontalAlignment" in format_dict:
        cell_format["horizontalAlignment"] = format_dict["horizontalAlignment"]
    if "verticalAlignment" in format_dict:
        cell_format["verticalAlignment"] = format_dict["verticalAlignment"]

    # Other formats
    if "hyperlinkDisplayType" in format_dict:
        cell_format["hyperlinkDisplayType"] = format_dict["hyperlinkDisplayType"]

    return cell_format


def _get_format_fields(format_dict: dict[str, Any] | None) -> str:
    """Get the fields string for repeatCell based on what's in the format."""
    if not format_dict:
        return ""

    fields = []
    if "numberFormat" in format_dict:
        fields.append("numberFormat")
    if "backgroundColor" in format_dict:
        fields.append("backgroundColor")
    if "textFormat" in format_dict:
        fields.append("textFormat")
    if "horizontalAlignment" in format_dict:
        fields.append("horizontalAlignment")
    if "verticalAlignment" in format_dict:
        fields.append("verticalAlignment")
    if "hyperlinkDisplayType" in format_dict:
        fields.append("hyperlinkDisplayType")

    return ",".join(fields)


def _hex_to_rgb(hex_color: str) -> dict[str, float]:
    """Convert hex color string to RGB dict for Google Sheets API."""
    hex_color = hex_color.lstrip("#")
    r = int(hex_color[0:2], 16) / 255.0
    g = int(hex_color[2:4], 16) / 255.0
    b = int(hex_color[4:6], 16) / 255.0
    return {"red": r, "green": g, "blue": b}


def _convert_text_format(text_format: dict[str, Any]) -> dict[str, Any]:
    """Convert text format, ensuring colors are in RGB format."""
    result = dict(text_format)

    # Convert foregroundColor from hex to RGB if needed
    if "foregroundColor" in result:
        color = result["foregroundColor"]
        if isinstance(color, str) and color.startswith("#"):
            result["foregroundColor"] = _hex_to_rgb(color)

    return result


def _generate_data_validation_requests(
    changes: list[DataValidationChange], sheet_id: int
) -> list[dict[str, Any]]:
    """Generate requests for data validation changes.

    Uses setDataValidation to apply validation rules.
    Groups contiguous cells in the same column into ranges for efficiency.
    """
    requests: list[dict[str, Any]] = []

    for change in changes:
        if change.change_type == "deleted":
            # Clear validation from all cells in the range
            for cell_range in _group_cells_into_ranges(change.cells, sheet_id):
                requests.append(
                    {
                        "setDataValidation": {
                            "range": cell_range,
                            # Omitting 'rule' clears the validation
                        }
                    }
                )

        elif change.change_type in ("added", "modified"):
            # Apply validation to all cells
            for cell_range in _group_cells_into_ranges(change.cells, sheet_id):
                requests.append(
                    {
                        "setDataValidation": {
                            "range": cell_range,
                            "rule": change.new_rule,
                        }
                    }
                )

    return requests


def _group_cells_into_ranges(cells: list[str], sheet_id: int) -> list[dict[str, int]]:
    """Group cell references into contiguous ranges.

    Groups cells that are in the same column and have contiguous rows.
    Returns a list of GridRange dicts.
    """
    if not cells:
        return []

    # Parse cells into (row, col) tuples
    parsed: list[tuple[int, int, str]] = []
    for cell in cells:
        row, col = a1_to_cell(cell)
        parsed.append((row, col, cell))

    # Sort by column, then row
    parsed.sort(key=lambda x: (x[1], x[0]))

    ranges: list[dict[str, int]] = []
    current_col = -1
    start_row = -1
    end_row = -1

    for row, col, _ in parsed:
        if col != current_col:
            # New column - emit previous range if exists
            if current_col >= 0:
                ranges.append(
                    {
                        "sheetId": sheet_id,
                        "startRowIndex": start_row,
                        "endRowIndex": end_row + 1,
                        "startColumnIndex": current_col,
                        "endColumnIndex": current_col + 1,
                    }
                )
            current_col = col
            start_row = row
            end_row = row
        elif row == end_row + 1:
            # Contiguous row in same column
            end_row = row
        else:
            # Gap in rows - emit previous range and start new one
            ranges.append(
                {
                    "sheetId": sheet_id,
                    "startRowIndex": start_row,
                    "endRowIndex": end_row + 1,
                    "startColumnIndex": current_col,
                    "endColumnIndex": current_col + 1,
                }
            )
            start_row = row
            end_row = row

    # Emit final range
    if current_col >= 0:
        ranges.append(
            {
                "sheetId": sheet_id,
                "startRowIndex": start_row,
                "endRowIndex": end_row + 1,
                "startColumnIndex": current_col,
                "endColumnIndex": current_col + 1,
            }
        )

    return ranges


def _generate_dimension_requests(
    changes: list[DimensionChange], sheet_id: int
) -> list[dict[str, Any]]:
    """Generate requests for dimension (row/column size) changes.

    Uses updateDimensionProperties to resize rows/columns.
    """
    requests: list[dict[str, Any]] = []

    for change in changes:
        if change.change_type == "deleted":
            # Deleted dimension means we want to reset to default
            # We can use updateDimensionProperties with pixelSize = default
            # For now, skip deletion
            continue

        if change.change_type in ("added", "modified"):
            if change.new_size is None:
                continue

            requests.append(
                {
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": sheet_id,
                            "dimension": change.dimension_type,
                            "startIndex": change.index,
                            "endIndex": change.index + 1,
                        },
                        "properties": {"pixelSize": change.new_size},
                        "fields": "pixelSize",
                    }
                }
            )

    return requests


def _generate_text_format_run_requests(
    changes: list[TextFormatRunChange], sheet_id: int
) -> list[dict[str, Any]]:
    """Generate requests for text format run (rich text) changes.

    Uses updateCells to apply textFormatRuns to specific cells.
    """
    requests: list[dict[str, Any]] = []

    for change in changes:
        row, col = a1_to_cell(change.cell_ref)

        if change.change_type == "deleted":
            # Clear text format runs by setting empty list
            requests.append(
                {
                    "updateCells": {
                        "rows": [{"values": [{"textFormatRuns": []}]}],
                        "fields": "textFormatRuns",
                        "start": {
                            "sheetId": sheet_id,
                            "rowIndex": row,
                            "columnIndex": col,
                        },
                    }
                }
            )
        elif (
            change.change_type in ("added", "modified") and change.new_runs is not None
        ):
            requests.append(
                {
                    "updateCells": {
                        "rows": [{"values": [{"textFormatRuns": change.new_runs}]}],
                        "fields": "textFormatRuns",
                        "start": {
                            "sheetId": sheet_id,
                            "rowIndex": row,
                            "columnIndex": col,
                        },
                    }
                }
            )

    return requests


def _generate_note_requests(
    changes: list[NoteChange], sheet_id: int
) -> list[dict[str, Any]]:
    """Generate requests for cell note changes.

    Uses updateCells to add/modify/delete notes on specific cells.
    """
    requests: list[dict[str, Any]] = []

    for change in changes:
        row, col = a1_to_cell(change.cell_ref)

        if change.change_type == "deleted":
            # Clear note by setting empty string
            requests.append(
                {
                    "updateCells": {
                        "rows": [{"values": [{"note": ""}]}],
                        "fields": "note",
                        "start": {
                            "sheetId": sheet_id,
                            "rowIndex": row,
                            "columnIndex": col,
                        },
                    }
                }
            )
        elif (
            change.change_type in ("added", "modified") and change.new_note is not None
        ):
            requests.append(
                {
                    "updateCells": {
                        "rows": [{"values": [{"note": change.new_note}]}],
                        "fields": "note",
                        "start": {
                            "sheetId": sheet_id,
                            "rowIndex": row,
                            "columnIndex": col,
                        },
                    }
                }
            )

    return requests


def _generate_merge_requests(
    changes: list[MergeChange], sheet_id: int
) -> list[dict[str, Any]]:
    """Generate requests for merge changes.

    Uses mergeCells to create merges, unmergeCells to remove them.
    """
    requests: list[dict[str, Any]] = []

    for change in changes:
        grid_range = {
            "sheetId": sheet_id,
            "startRowIndex": change.start_row,
            "endRowIndex": change.end_row,
            "startColumnIndex": change.start_col,
            "endColumnIndex": change.end_col,
        }

        if change.change_type == "deleted":
            requests.append({"unmergeCells": {"range": grid_range}})
        elif change.change_type == "added":
            requests.append(
                {"mergeCells": {"range": grid_range, "mergeType": "MERGE_ALL"}}
            )

    return requests


def _generate_conditional_format_requests(
    changes: list[ConditionalFormatChange], sheet_id: int
) -> list[dict[str, Any]]:
    """Generate requests for conditional format changes.

    Uses addConditionalFormatRule, updateConditionalFormatRule,
    and deleteConditionalFormatRule.
    """
    requests: list[dict[str, Any]] = []

    for change in changes:
        if change.change_type == "deleted" and change.rule_index is not None:
            requests.append(
                {
                    "deleteConditionalFormatRule": {
                        "sheetId": sheet_id,
                        "index": change.rule_index,
                    }
                }
            )
        elif change.change_type == "added" and change.new_rule is not None:
            # Build rule for API (convert A1 ranges back to GridRange)
            rule = _build_conditional_format_rule(change.new_rule, sheet_id)
            requests.append(
                {
                    "addConditionalFormatRule": {
                        "rule": rule,
                        "index": change.rule_index,
                    }
                }
            )
        elif (
            change.change_type == "modified"
            and change.new_rule is not None
            and change.rule_index is not None
        ):
            rule = _build_conditional_format_rule(change.new_rule, sheet_id)
            requests.append(
                {
                    "updateConditionalFormatRule": {
                        "rule": rule,
                        "index": change.rule_index,
                    }
                }
            )

    return requests


def _build_conditional_format_rule(
    rule_data: dict[str, Any], sheet_id: int
) -> dict[str, Any]:
    """Build a ConditionalFormatRule for the API.

    Converts A1 notation ranges to GridRange format.
    """
    rule: dict[str, Any] = {}

    # Convert ranges from A1 notation to GridRange
    if "ranges" in rule_data:
        rule["ranges"] = [
            a1_range_to_grid_range(r, sheet_id) for r in rule_data["ranges"]
        ]

    # Copy booleanRule or gradientRule
    if "booleanRule" in rule_data:
        rule["booleanRule"] = rule_data["booleanRule"]
    if "gradientRule" in rule_data:
        rule["gradientRule"] = rule_data["gradientRule"]

    return rule


def _generate_basic_filter_requests(
    change: BasicFilterChange, sheet_id: int
) -> list[dict[str, Any]]:
    """Generate requests for basic filter changes.

    Uses setBasicFilter and clearBasicFilter.
    """
    requests: list[dict[str, Any]] = []

    if change.change_type == "deleted":
        requests.append({"clearBasicFilter": {"sheetId": sheet_id}})
    elif change.change_type in ("added", "modified") and change.new_filter is not None:
        # Build the filter request (sheetId goes in range, not at filter level)
        filter_spec: dict[str, Any] = {}

        # Copy range if present (convert to GridRange if needed)
        if "range" in change.new_filter:
            range_data = change.new_filter["range"]
            if isinstance(range_data, str):
                # A1 notation - convert to GridRange
                filter_spec["range"] = a1_range_to_grid_range(range_data, sheet_id)
            else:
                # Already a GridRange - copy and add sheetId
                filter_spec["range"] = dict(range_data)
                filter_spec["range"]["sheetId"] = sheet_id

        # Copy filter criteria
        if "criteria" in change.new_filter:
            filter_spec["criteria"] = change.new_filter["criteria"]
        if "filterSpecs" in change.new_filter:
            filter_spec["filterSpecs"] = change.new_filter["filterSpecs"]
        if "sortSpecs" in change.new_filter:
            filter_spec["sortSpecs"] = change.new_filter["sortSpecs"]

        requests.append({"setBasicFilter": {"filter": filter_spec}})

    return requests


def _generate_banded_range_requests(
    changes: list[BandedRangeChange], sheet_id: int
) -> list[dict[str, Any]]:
    """Generate requests for banded range changes.

    Uses addBanding, updateBanding, and deleteBanding.
    """
    requests: list[dict[str, Any]] = []

    for change in changes:
        if change.change_type == "deleted" and change.banded_range_id is not None:
            requests.append(
                {
                    "deleteBanding": {
                        "bandedRangeId": change.banded_range_id,
                    }
                }
            )
        elif change.change_type == "added" and change.new_range is not None:
            # Build banded range for API
            banded_range = _build_banded_range(change.new_range, sheet_id)
            requests.append({"addBanding": {"bandedRange": banded_range}})
        elif (
            change.change_type == "modified"
            and change.new_range is not None
            and change.banded_range_id is not None
        ):
            banded_range = _build_banded_range(change.new_range, sheet_id)
            # Ensure bandedRangeId is set for update
            banded_range["bandedRangeId"] = change.banded_range_id
            # Build fields string for what's being updated
            fields = _get_banded_range_fields(change.new_range)
            requests.append(
                {
                    "updateBanding": {
                        "bandedRange": banded_range,
                        "fields": fields,
                    }
                }
            )

    return requests


def _build_banded_range(range_data: dict[str, Any], sheet_id: int) -> dict[str, Any]:
    """Build a BandedRange for the API.

    Ensures the range has the correct sheetId.
    """
    result: dict[str, Any] = {}

    # Copy bandedRangeId if present
    if "bandedRangeId" in range_data:
        result["bandedRangeId"] = range_data["bandedRangeId"]

    # Copy and fix range (add sheetId)
    if "range" in range_data:
        result["range"] = dict(range_data["range"])
        result["range"]["sheetId"] = sheet_id

    # Copy row properties
    if "rowProperties" in range_data:
        result["rowProperties"] = range_data["rowProperties"]

    # Copy column properties
    if "columnProperties" in range_data:
        result["columnProperties"] = range_data["columnProperties"]

    return result


def _get_banded_range_fields(range_data: dict[str, Any]) -> str:
    """Get the fields string for updateBanding based on what's in the range."""
    fields = []
    if "range" in range_data:
        fields.append("range")
    if "rowProperties" in range_data:
        fields.append("rowProperties")
    if "columnProperties" in range_data:
        fields.append("columnProperties")
    return ",".join(fields)


def _generate_filter_view_requests(
    changes: list[FilterViewChange], sheet_id: int
) -> list[dict[str, Any]]:
    """Generate requests for filter view changes.

    Uses addFilterView, updateFilterView, and deleteFilterView.
    """
    requests: list[dict[str, Any]] = []

    for change in changes:
        if change.change_type == "deleted" and change.filter_view_id is not None:
            requests.append(
                {
                    "deleteFilterView": {
                        "filterId": change.filter_view_id,
                    }
                }
            )
        elif change.change_type == "added" and change.new_view is not None:
            # Build filter view for API
            filter_view = _build_filter_view(change.new_view, sheet_id)
            requests.append({"addFilterView": {"filter": filter_view}})
        elif (
            change.change_type == "modified"
            and change.new_view is not None
            and change.filter_view_id is not None
        ):
            filter_view = _build_filter_view(change.new_view, sheet_id)
            # Ensure filterViewId is set for update
            filter_view["filterViewId"] = change.filter_view_id
            # Build fields string for what's being updated
            fields = _get_filter_view_fields(change.new_view)
            requests.append(
                {
                    "updateFilterView": {
                        "filter": filter_view,
                        "fields": fields,
                    }
                }
            )

    return requests


def _build_filter_view(view_data: dict[str, Any], sheet_id: int) -> dict[str, Any]:
    """Build a FilterView for the API.

    Ensures the range has the correct sheetId.
    """
    result: dict[str, Any] = {}

    # Copy filterViewId if present
    if "filterViewId" in view_data:
        result["filterViewId"] = view_data["filterViewId"]

    # Copy title
    if "title" in view_data:
        result["title"] = view_data["title"]

    # Copy and fix range (add sheetId)
    if "range" in view_data:
        result["range"] = dict(view_data["range"])
        result["range"]["sheetId"] = sheet_id

    # Copy sort specs
    if "sortSpecs" in view_data:
        result["sortSpecs"] = view_data["sortSpecs"]

    # Copy filter specs
    if "filterSpecs" in view_data:
        result["filterSpecs"] = view_data["filterSpecs"]

    # Copy criteria (legacy, but still supported)
    if "criteria" in view_data:
        result["criteria"] = view_data["criteria"]

    # Copy named range ID if present
    if "namedRangeId" in view_data:
        result["namedRangeId"] = view_data["namedRangeId"]

    return result


def _get_filter_view_fields(view_data: dict[str, Any]) -> str:
    """Get the fields string for updateFilterView based on what's in the view."""
    fields = []
    if "title" in view_data:
        fields.append("title")
    if "range" in view_data:
        fields.append("range")
    if "sortSpecs" in view_data:
        fields.append("sortSpecs")
    if "filterSpecs" in view_data:
        fields.append("filterSpecs")
    if "criteria" in view_data:
        fields.append("criteria")
    return ",".join(fields)


def _generate_chart_requests(
    changes: list[ChartChange], sheet_id: int
) -> list[dict[str, Any]]:
    """Generate requests for chart changes.

    Uses addChart, updateChartSpec, updateEmbeddedObjectPosition,
    and deleteEmbeddedObject.
    """
    requests: list[dict[str, Any]] = []

    for change in changes:
        if change.change_type == "deleted" and change.chart_id is not None:
            # Delete chart using deleteEmbeddedObject
            requests.append(
                {
                    "deleteEmbeddedObject": {
                        "objectId": change.chart_id,
                    }
                }
            )
        elif change.change_type == "added" and change.new_chart is not None:
            # Add new chart - don't include chartId, let Google assign it
            chart = _build_chart(change.new_chart, sheet_id, include_chart_id=False)
            requests.append({"addChart": {"chart": chart}})
        elif (
            change.change_type == "modified"
            and change.new_chart is not None
            and change.chart_id is not None
        ):
            # Modified chart - need to check what changed (spec vs position)
            old_chart = change.old_chart or {}
            new_chart = change.new_chart

            # Check if spec changed
            if old_chart.get("spec") != new_chart.get("spec"):
                requests.append(
                    {
                        "updateChartSpec": {
                            "chartId": change.chart_id,
                            "spec": new_chart.get("spec", {}),
                        }
                    }
                )

            # Check if position changed
            if old_chart.get("position") != new_chart.get("position"):
                position = _build_chart_position(
                    new_chart.get("position", {}), sheet_id
                )
                requests.append(
                    {
                        "updateEmbeddedObjectPosition": {
                            "objectId": change.chart_id,
                            "newPosition": position,
                            "fields": "*",
                        }
                    }
                )

    return requests


def _build_chart(
    chart_data: dict[str, Any], sheet_id: int, include_chart_id: bool = True
) -> dict[str, Any]:
    """Build a Chart for the API.

    Ensures position has the correct sheetId.

    Args:
        chart_data: Chart data from feature.json
        sheet_id: The sheet ID
        include_chart_id: Whether to include chartId (False for new charts)
    """
    result: dict[str, Any] = {}

    # Copy chartId only if requested (not for new charts - let Google assign it)
    if include_chart_id and "chartId" in chart_data:
        result["chartId"] = chart_data["chartId"]

    # Copy spec
    if "spec" in chart_data:
        result["spec"] = chart_data["spec"]

    # Copy and fix position (add sheetId to anchorCell if needed)
    if "position" in chart_data:
        result["position"] = _build_chart_position(chart_data["position"], sheet_id)

    return result


def _build_chart_position(
    position_data: dict[str, Any], sheet_id: int
) -> dict[str, Any]:
    """Build chart position with correct sheetId."""
    result: dict[str, Any] = {}

    # Handle overlayPosition (most common)
    if "overlayPosition" in position_data:
        overlay = dict(position_data["overlayPosition"])
        # Ensure anchorCell has sheetId
        if "anchorCell" in overlay:
            overlay["anchorCell"] = dict(overlay["anchorCell"])
            overlay["anchorCell"]["sheetId"] = sheet_id
        result["overlayPosition"] = overlay

    # Handle newSheet position (creates a new sheet for the chart)
    if "newSheet" in position_data:
        result["newSheet"] = position_data["newSheet"]

    return result


def _generate_pivot_table_requests(
    changes: list[PivotTableChange], sheet_id: int
) -> list[dict[str, Any]]:
    """Generate requests for pivot table changes.

    Uses updateCells with fields: "pivotTable" to add/modify pivot tables.
    For deletions, clears the pivot table field.
    """
    requests: list[dict[str, Any]] = []

    for change in changes:
        row, col = a1_to_cell(change.anchor_cell)

        if change.change_type == "deleted":
            # Delete pivot table by clearing the pivotTable field
            requests.append(
                {
                    "updateCells": {
                        "rows": [{"values": [{"pivotTable": None}]}],
                        "fields": "pivotTable",
                        "start": {
                            "sheetId": sheet_id,
                            "rowIndex": row,
                            "columnIndex": col,
                        },
                    }
                }
            )
        elif change.change_type in ("added", "modified") and change.new_pivot:
            # Add or modify pivot table
            pivot_table = _build_pivot_table(change.new_pivot, sheet_id)
            requests.append(
                {
                    "updateCells": {
                        "rows": [{"values": [{"pivotTable": pivot_table}]}],
                        "fields": "pivotTable",
                        "start": {
                            "sheetId": sheet_id,
                            "rowIndex": row,
                            "columnIndex": col,
                        },
                    }
                }
            )

    return requests


def _build_pivot_table(pivot_data: dict[str, Any], sheet_id: int) -> dict[str, Any]:
    """Build a pivot table for the API.

    Strips the anchorCell (since it's specified in updateCells start)
    and ensures the source range has the correct sheetId.
    """
    # Copy everything except anchorCell
    result: dict[str, Any] = {k: v for k, v in pivot_data.items() if k != "anchorCell"}

    # Ensure the source range has sheetId
    if "source" in result:
        result["source"] = dict(result["source"])
        result["source"]["sheetId"] = sheet_id

    return result
