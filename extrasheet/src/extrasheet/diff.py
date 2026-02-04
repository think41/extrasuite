"""Core diff engine for extrasheet.

Compares current files against pristine copy and generates DiffResult.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path  # noqa: TC003 - used at runtime
from typing import Any, Literal

from extrasheet.exceptions import (
    InvalidFileError,
    MissingSpreadsheetIdError,
)
from extrasheet.file_reader import parse_tsv, read_current_files
from extrasheet.formula_compression import expand_formulas
from extrasheet.pristine import extract_pristine, get_pristine_file
from extrasheet.utils import (
    a1_range_to_grid_range,
    a1_to_cell,
    cell_to_a1,
    letter_to_column_index,
)


@dataclass
class CellChange:
    """Represents a change to a single cell's value."""

    row: int  # 0-based row index
    col: int  # 0-based column index
    cell_ref: str  # A1 notation
    change_type: Literal["added", "deleted", "modified"]
    old_value: str | None
    new_value: str | None


@dataclass
class FormulaChange:
    """Represents a change to a formula."""

    range_key: str  # A1 notation: "A1" or "C2:C100"
    change_type: Literal["added", "deleted", "modified"]
    old_formula: str | None
    new_formula: str | None
    is_range: bool  # True if this is a range formula


@dataclass
class FormatRuleChange:
    """Represents a change to a format rule."""

    range_key: str  # A1 notation range
    change_type: Literal["added", "deleted", "modified"]
    old_format: dict[str, Any] | None
    new_format: dict[str, Any] | None


@dataclass
class DataValidationChange:
    """Represents a change to data validation rules."""

    range_key: str  # Human-readable range description like "H2... (49 cells)"
    cells: list[str]  # List of cell references like ["H2", "H3", ...]
    change_type: Literal["added", "deleted", "modified"]
    old_rule: dict[str, Any] | None
    new_rule: dict[str, Any] | None


@dataclass
class DimensionChange:
    """Represents a change to row/column dimensions."""

    dimension_type: Literal["COLUMNS", "ROWS"]
    index: int
    change_type: Literal["added", "deleted", "modified"]
    old_size: int | None
    new_size: int | None


@dataclass
class TextFormatRunChange:
    """Represents a change to rich text formatting within a cell."""

    cell_ref: str  # A1 notation
    change_type: Literal["added", "deleted", "modified"]
    old_runs: list[dict[str, Any]] | None
    new_runs: list[dict[str, Any]] | None


@dataclass
class NoteChange:
    """Represents a change to a cell note."""

    cell_ref: str  # A1 notation
    change_type: Literal["added", "deleted", "modified"]
    old_note: str | None
    new_note: str | None


@dataclass
class MergeChange:
    """Represents a change to merged cells."""

    range_key: str  # A1 notation range like "A1:B2"
    change_type: Literal["added", "deleted"]
    start_row: int
    end_row: int
    start_col: int
    end_col: int


@dataclass
class ConditionalFormatChange:
    """Represents a change to a conditional format rule."""

    rule_index: int | None  # Index for existing rules, None for new
    change_type: Literal["added", "deleted", "modified"]
    old_rule: dict[str, Any] | None
    new_rule: dict[str, Any] | None


@dataclass
class BasicFilterChange:
    """Represents a change to the basic filter on a sheet."""

    change_type: Literal["added", "deleted", "modified"]
    old_filter: dict[str, Any] | None
    new_filter: dict[str, Any] | None


@dataclass
class BandedRangeChange:
    """Represents a change to a banded range (alternating row/column colors)."""

    banded_range_id: int | None  # ID for existing ranges, None for new
    change_type: Literal["added", "deleted", "modified"]
    old_range: dict[str, Any] | None
    new_range: dict[str, Any] | None


@dataclass
class FilterViewChange:
    """Represents a change to a filter view."""

    filter_view_id: int | None  # ID for existing views, None for new
    change_type: Literal["added", "deleted", "modified"]
    old_view: dict[str, Any] | None
    new_view: dict[str, Any] | None


@dataclass
class ChartChange:
    """Represents a change to an embedded chart."""

    chart_id: int | None  # ID for existing charts, None for new
    change_type: Literal["added", "deleted", "modified"]
    old_chart: dict[str, Any] | None
    new_chart: dict[str, Any] | None


@dataclass
class PivotTableChange:
    """Represents a change to a pivot table."""

    anchor_cell: str  # A1 notation for the anchor cell
    change_type: Literal["added", "deleted", "modified"]
    old_pivot: dict[str, Any] | None
    new_pivot: dict[str, Any] | None


@dataclass
class TableChange:
    """Represents a change to a structured table."""

    table_id: str | None  # ID for existing tables, None for new
    table_name: str
    change_type: Literal["added", "deleted", "modified"]
    old_table: dict[str, Any] | None
    new_table: dict[str, Any] | None


@dataclass
class NamedRangeChange:
    """Represents a change to a named range."""

    named_range_id: str | None  # ID for existing ranges, None for new
    name: str
    change_type: Literal["added", "deleted", "modified"]
    old_range: dict[str, Any] | None
    new_range: dict[str, Any] | None


@dataclass
class SlicerChange:
    """Represents a change to a slicer."""

    slicer_id: int | None  # ID for existing slicers, None for new
    change_type: Literal["added", "deleted", "modified"]
    old_slicer: dict[str, Any] | None
    new_slicer: dict[str, Any] | None


@dataclass
class DataSourceTableChange:
    """Represents a change to a data source table."""

    # Data source tables are anchored at a cell position
    anchor_cell: str  # A1 notation of anchor cell
    change_type: Literal["added", "deleted", "modified"]
    old_table: dict[str, Any] | None
    new_table: dict[str, Any] | None


@dataclass
class GridChange:
    """Represents a change to the grid dimensions (row/column count)."""

    change_type: Literal[
        "insert_rows", "delete_rows", "insert_columns", "delete_columns"
    ]
    sheet_name: str
    start_index: int  # 0-based, where change starts
    end_index: int  # 0-based, exclusive
    count: int  # Number of rows/columns affected


@dataclass
class DeletedSheetChange:
    """Represents a sheet that was deleted."""

    sheet_name: str
    folder_name: str
    sheet_id: int


@dataclass
class NewSheetChange:
    """Represents a new sheet that needs to be added."""

    sheet_name: str
    folder_name: str
    properties: dict[
        str, Any
    ]  # Sheet properties like gridProperties, frozen rows, etc.


@dataclass
class SheetDiff:
    """Diff results for a single sheet."""

    sheet_id: int
    sheet_name: str
    folder_name: str
    cell_changes: list[CellChange] = field(default_factory=list)
    formula_changes: list[FormulaChange] = field(default_factory=list)
    format_rule_changes: list[FormatRuleChange] = field(default_factory=list)
    data_validation_changes: list[DataValidationChange] = field(default_factory=list)
    dimension_changes: list[DimensionChange] = field(default_factory=list)
    text_format_run_changes: list[TextFormatRunChange] = field(default_factory=list)
    note_changes: list[NoteChange] = field(default_factory=list)
    merge_changes: list[MergeChange] = field(default_factory=list)
    conditional_format_changes: list[ConditionalFormatChange] = field(
        default_factory=list
    )
    basic_filter_change: BasicFilterChange | None = None
    banded_range_changes: list[BandedRangeChange] = field(default_factory=list)
    filter_view_changes: list[FilterViewChange] = field(default_factory=list)
    chart_changes: list[ChartChange] = field(default_factory=list)
    pivot_table_changes: list[PivotTableChange] = field(default_factory=list)
    table_changes: list[TableChange] = field(default_factory=list)
    slicer_changes: list[SlicerChange] = field(default_factory=list)
    data_source_table_changes: list[DataSourceTableChange] = field(default_factory=list)
    grid_changes: list[GridChange] = field(default_factory=list)


@dataclass
class SpreadsheetPropertyChange:
    """Change to spreadsheet-level property."""

    property_name: str
    old_value: str | None
    new_value: str | None


@dataclass
class SheetPropertyChange:
    """Change to sheet-level property."""

    sheet_id: int
    sheet_name: str
    property_name: str
    old_value: str | int | bool | None
    new_value: str | int | bool | None


@dataclass
class DiffResult:
    """Complete diff result for a spreadsheet."""

    spreadsheet_id: str
    sheet_diffs: list[SheetDiff] = field(default_factory=list)
    spreadsheet_changes: list[SpreadsheetPropertyChange] = field(default_factory=list)
    sheet_property_changes: list[SheetPropertyChange] = field(default_factory=list)
    new_sheet_changes: list[NewSheetChange] = field(default_factory=list)
    deleted_sheet_changes: list[DeletedSheetChange] = field(default_factory=list)
    named_range_changes: list[NamedRangeChange] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def has_changes(self) -> bool:
        """Check if there are any changes to apply."""
        if (
            self.spreadsheet_changes
            or self.sheet_property_changes
            or self.new_sheet_changes
            or self.deleted_sheet_changes
            or self.named_range_changes
        ):
            return True
        for sheet_diff in self.sheet_diffs:
            if (
                sheet_diff.cell_changes
                or sheet_diff.formula_changes
                or sheet_diff.format_rule_changes
                or sheet_diff.data_validation_changes
                or sheet_diff.dimension_changes
                or sheet_diff.text_format_run_changes
                or sheet_diff.note_changes
                or sheet_diff.merge_changes
                or sheet_diff.conditional_format_changes
                or sheet_diff.basic_filter_change
                or sheet_diff.banded_range_changes
                or sheet_diff.filter_view_changes
                or sheet_diff.chart_changes
                or sheet_diff.pivot_table_changes
                or sheet_diff.table_changes
                or sheet_diff.slicer_changes
                or sheet_diff.data_source_table_changes
                or sheet_diff.grid_changes
            ):
                return True
        return False


def diff(folder: Path) -> DiffResult:
    """Compare current files against pristine copy.

    Args:
        folder: Path to the spreadsheet folder

    Returns:
        DiffResult containing all detected changes

    Raises:
        MissingPristineError: If .pristine/spreadsheet.zip doesn't exist
        InvalidFileError: If files are corrupted
    """
    # Extract pristine files
    pristine_files = extract_pristine(folder)

    # Read current files
    current_files = read_current_files(folder)

    # Parse spreadsheet.json for metadata
    pristine_meta_str = get_pristine_file(pristine_files, "spreadsheet.json")
    current_meta_str = current_files.get("spreadsheet.json")

    if not pristine_meta_str:
        raise InvalidFileError("spreadsheet.json", "Missing from pristine copy")
    if not current_meta_str:
        raise InvalidFileError("spreadsheet.json", "Missing from current folder")

    pristine_meta = json.loads(pristine_meta_str)
    current_meta = json.loads(current_meta_str)

    # Get spreadsheet ID
    spreadsheet_id = current_meta.get("spreadsheetId")
    if not spreadsheet_id:
        raise MissingSpreadsheetIdError(str(folder))

    result = DiffResult(spreadsheet_id=spreadsheet_id)

    # Diff spreadsheet-level properties
    result.spreadsheet_changes = _diff_spreadsheet_properties(
        pristine_meta, current_meta
    )

    # Diff sheet-level properties
    result.sheet_property_changes = _diff_sheet_properties(pristine_meta, current_meta)

    # Build sheet mapping from current and pristine metadata
    current_sheets = {s["folder"]: s for s in current_meta.get("sheets", [])}
    pristine_sheets = {s["folder"]: s for s in pristine_meta.get("sheets", [])}

    # Detect new sheets (in current but not in pristine)
    # We use a counter to assign temporary sheetIds to new sheets
    # These IDs are specified in the addSheet request
    # Start from max existing sheetId + 1 to avoid conflicts
    all_sheet_ids = [
        s.get("sheetId", 0)
        for s in list(pristine_sheets.values()) + list(current_sheets.values())
    ]
    max_existing_id = max(all_sheet_ids) if all_sheet_ids else 0
    next_new_sheet_id = max_existing_id + 1

    for folder_name, current_sheet in current_sheets.items():
        is_new_sheet = folder_name not in pristine_sheets

        if is_new_sheet:
            # Assign a temporary sheetId for the new sheet
            sheet_id = next_new_sheet_id
            next_new_sheet_id += 1
            sheet_name = current_sheet.get("title", folder_name)

            # Create NewSheetChange with properties from current_sheet
            properties: dict[str, Any] = {
                "sheetId": sheet_id,
                "title": sheet_name,
            }
            # Copy grid properties if present
            if "gridProperties" in current_sheet:
                properties["gridProperties"] = current_sheet["gridProperties"]

            result.new_sheet_changes.append(
                NewSheetChange(
                    sheet_name=sheet_name,
                    folder_name=folder_name,
                    properties=properties,
                )
            )
        else:
            sheet_id = current_sheet.get("sheetId", 0)
            sheet_name = current_sheet.get("title", folder_name)

        # Diff sheet content (works for both existing and new sheets)
        # For new sheets, pristine files will be empty, so all content is "added"
        sheet_diff = _diff_sheet(
            pristine_files,
            current_files,
            folder_name,
            sheet_id,
            sheet_name,
        )
        result.sheet_diffs.append(sheet_diff)

    # Detect deleted sheets (in pristine but not in current)
    for folder_name, pristine_sheet in pristine_sheets.items():
        if folder_name not in current_sheets:
            result.deleted_sheet_changes.append(
                DeletedSheetChange(
                    sheet_name=pristine_sheet.get("title", folder_name),
                    folder_name=folder_name,
                    sheet_id=pristine_sheet.get("sheetId", 0),
                )
            )

    # Diff named ranges (spreadsheet-level feature)
    result.named_range_changes = _diff_named_ranges(pristine_files, current_files)

    return result


def _diff_spreadsheet_properties(
    pristine_meta: dict[str, Any], current_meta: dict[str, Any]
) -> list[SpreadsheetPropertyChange]:
    """Diff spreadsheet-level properties like title."""
    changes: list[SpreadsheetPropertyChange] = []

    # Get properties dict (title is nested under properties)
    pristine_props = pristine_meta.get("properties", {})
    current_props = current_meta.get("properties", {})

    # Check title
    pristine_title = pristine_props.get("title")
    current_title = current_props.get("title")
    if pristine_title != current_title:
        changes.append(
            SpreadsheetPropertyChange("title", pristine_title, current_title)
        )

    return changes


def _diff_sheet_properties(
    pristine_meta: dict[str, Any], current_meta: dict[str, Any]
) -> list[SheetPropertyChange]:
    """Diff sheet-level properties."""
    changes: list[SheetPropertyChange] = []

    pristine_sheets = {s["folder"]: s for s in pristine_meta.get("sheets", [])}
    current_sheets = {s["folder"]: s for s in current_meta.get("sheets", [])}

    for folder_name, current_sheet in current_sheets.items():
        pristine_sheet = pristine_sheets.get(folder_name)
        if not pristine_sheet:
            continue

        sheet_id = current_sheet.get("sheetId", 0)
        sheet_name = current_sheet.get("title", folder_name)

        # Check properties that can be changed
        for prop in ["title", "hidden"]:
            pristine_val = pristine_sheet.get(prop)
            current_val = current_sheet.get(prop)
            if pristine_val != current_val:
                changes.append(
                    SheetPropertyChange(
                        sheet_id, sheet_name, prop, pristine_val, current_val
                    )
                )

        # Check gridProperties
        pristine_grid = pristine_sheet.get("gridProperties", {})
        current_grid = current_sheet.get("gridProperties", {})
        for prop in ["frozenRowCount", "frozenColumnCount"]:
            pristine_val = pristine_grid.get(prop)
            current_val = current_grid.get(prop)
            if pristine_val != current_val:
                changes.append(
                    SheetPropertyChange(
                        sheet_id, sheet_name, prop, pristine_val, current_val
                    )
                )

    return changes


def _diff_sheet(
    pristine_files: dict[str, str | bytes],
    current_files: dict[str, str],
    folder_name: str,
    sheet_id: int,
    sheet_name: str,
) -> SheetDiff:
    """Diff a single sheet's contents."""
    sheet_diff = SheetDiff(
        sheet_id=sheet_id,
        sheet_name=sheet_name,
        folder_name=folder_name,
    )

    # Get data.tsv files
    data_path = f"{folder_name}/data.tsv"
    pristine_tsv = get_pristine_file(pristine_files, data_path)
    current_tsv = current_files.get(data_path)

    # If no current data, nothing to diff
    if current_tsv is None:
        return sheet_diff

    # Parse TSV into grids (pristine may be empty for new/empty sheets)
    pristine_grid = parse_tsv(pristine_tsv) if pristine_tsv else []
    current_grid = parse_tsv(current_tsv)

    # Detect grid dimension changes (previously this raised an error)
    if pristine_grid:
        sheet_diff.grid_changes = _detect_grid_changes(
            pristine_grid, current_grid, sheet_name
        )

    # Get formula files
    formula_path = f"{folder_name}/formula.json"
    pristine_formula_str = get_pristine_file(pristine_files, formula_path)
    current_formula_str = current_files.get(formula_path)

    pristine_formulas = json.loads(pristine_formula_str) if pristine_formula_str else {}
    current_formulas = json.loads(current_formula_str) if current_formula_str else {}

    # Expand formulas for cell-level comparison
    pristine_expanded = expand_formulas(pristine_formulas)
    current_expanded = expand_formulas(current_formulas)

    # Diff cells (values)
    # Pass grid_changes so we can account for row/column shifts
    sheet_diff.cell_changes = _diff_cells(
        pristine_grid,
        current_grid,
        pristine_expanded,
        current_expanded,
        sheet_diff.grid_changes,
    )

    # Diff formulas (as ranges)
    # Pass grid_changes so we can map pristine positions to post-change positions
    sheet_diff.formula_changes = _diff_formulas(
        pristine_formulas, current_formulas, sheet_diff.grid_changes
    )

    # Diff format rules
    format_path = f"{folder_name}/format.json"
    pristine_format_str = get_pristine_file(pristine_files, format_path)
    current_format_str = current_files.get(format_path)
    pristine_format = json.loads(pristine_format_str) if pristine_format_str else {}
    current_format = json.loads(current_format_str) if current_format_str else {}
    sheet_diff.format_rule_changes = _diff_format_rules(pristine_format, current_format)

    # Read feature data (supports both legacy feature.json and new split format)
    pristine_feature, current_feature = _read_feature_data(
        pristine_files, current_files, folder_name
    )

    # Diff data validation
    sheet_diff.data_validation_changes = _diff_data_validation(
        pristine_feature, current_feature
    )

    # Diff dimensions
    dimension_path = f"{folder_name}/dimension.json"
    pristine_dimension_str = get_pristine_file(pristine_files, dimension_path)
    current_dimension_str = current_files.get(dimension_path)
    pristine_dimension = (
        json.loads(pristine_dimension_str) if pristine_dimension_str else {}
    )
    current_dimension = (
        json.loads(current_dimension_str) if current_dimension_str else {}
    )
    sheet_diff.dimension_changes = _diff_dimensions(
        pristine_dimension, current_dimension
    )

    # Diff text format runs (rich text) - from format.json
    sheet_diff.text_format_run_changes = _diff_text_format_runs(
        pristine_format, current_format
    )

    # Diff notes - from format.json
    sheet_diff.note_changes = _diff_notes(pristine_format, current_format)

    # Diff merges - from format.json
    sheet_diff.merge_changes = _diff_merges(pristine_format, current_format)

    # Diff conditional formats - from format.json
    sheet_diff.conditional_format_changes = _diff_conditional_formats(
        pristine_format, current_format
    )

    # Diff basic filter - from feature.json
    sheet_diff.basic_filter_change = _diff_basic_filter(
        pristine_feature, current_feature
    )

    # Diff banded ranges - from feature.json
    sheet_diff.banded_range_changes = _diff_banded_ranges(
        pristine_feature, current_feature
    )

    # Diff filter views - from feature.json
    sheet_diff.filter_view_changes = _diff_filter_views(
        pristine_feature, current_feature
    )

    # Diff charts - from feature data
    sheet_diff.chart_changes = _diff_charts(pristine_feature, current_feature)

    # Diff pivot tables - from feature data
    sheet_diff.pivot_table_changes = _diff_pivot_tables(
        pristine_feature, current_feature
    )

    # Diff tables - from feature data
    sheet_diff.table_changes = _diff_tables(pristine_feature, current_feature)

    # Diff slicers - from feature data
    sheet_diff.slicer_changes = _diff_slicers(pristine_feature, current_feature)

    # Diff data source tables - from feature data
    sheet_diff.data_source_table_changes = _diff_data_source_tables(
        pristine_feature, current_feature
    )

    return sheet_diff


def _detect_grid_changes(
    pristine_grid: list[list[str]],
    current_grid: list[list[str]],
    sheet_name: str,
) -> list[GridChange]:
    """Detect changes to grid dimensions between pristine and current.

    Returns a list of GridChange objects describing row/column insertions or deletions.
    """
    changes: list[GridChange] = []

    pristine_rows = len(pristine_grid)
    current_rows = len(current_grid)
    pristine_cols = max((len(row) for row in pristine_grid), default=0)
    current_cols = max((len(row) for row in current_grid), default=0)

    # Detect row changes
    if current_rows != pristine_rows:
        if current_rows > pristine_rows:
            # Rows added - determine if append or insert
            added_count = current_rows - pristine_rows
            # Check if existing rows match (append at end)
            is_append = all(
                pristine_grid[i] == current_grid[i]
                for i in range(pristine_rows)
                if i < len(current_grid)
            )
            if is_append:
                changes.append(
                    GridChange(
                        change_type="insert_rows",
                        sheet_name=sheet_name,
                        start_index=pristine_rows,
                        end_index=current_rows,
                        count=added_count,
                    )
                )
            else:
                # Find insertion point
                insert_at = 0
                for i in range(min(pristine_rows, current_rows)):
                    if i >= len(current_grid) or pristine_grid[i] != current_grid[i]:
                        insert_at = i
                        break
                changes.append(
                    GridChange(
                        change_type="insert_rows",
                        sheet_name=sheet_name,
                        start_index=insert_at,
                        end_index=insert_at + added_count,
                        count=added_count,
                    )
                )
        else:
            # Rows deleted
            deleted_count = pristine_rows - current_rows
            # Find deletion point
            delete_start = pristine_rows
            for i in range(min(pristine_rows, current_rows)):
                if i >= len(current_grid) or pristine_grid[i] != current_grid[i]:
                    delete_start = i
                    break
            changes.append(
                GridChange(
                    change_type="delete_rows",
                    sheet_name=sheet_name,
                    start_index=delete_start,
                    end_index=delete_start + deleted_count,
                    count=deleted_count,
                )
            )

    # Detect column changes
    if current_cols != pristine_cols:
        if current_cols > pristine_cols:
            # Columns added
            added_count = current_cols - pristine_cols
            # Check if append at end
            is_append = True
            for row_idx in range(min(len(pristine_grid), len(current_grid))):
                p_row = pristine_grid[row_idx] if row_idx < len(pristine_grid) else []
                c_row = current_grid[row_idx] if row_idx < len(current_grid) else []
                for col_idx in range(min(len(p_row), pristine_cols)):
                    p_val = p_row[col_idx] if col_idx < len(p_row) else ""
                    c_val = c_row[col_idx] if col_idx < len(c_row) else ""
                    if p_val != c_val:
                        is_append = False
                        break
                if not is_append:
                    break

            if is_append:
                changes.append(
                    GridChange(
                        change_type="insert_columns",
                        sheet_name=sheet_name,
                        start_index=pristine_cols,
                        end_index=current_cols,
                        count=added_count,
                    )
                )
            else:
                # Find insertion point
                insert_at = pristine_cols
                for row_idx in range(min(len(pristine_grid), len(current_grid))):
                    p_row = (
                        pristine_grid[row_idx] if row_idx < len(pristine_grid) else []
                    )
                    c_row = current_grid[row_idx] if row_idx < len(current_grid) else []
                    for col_idx in range(min(len(p_row), len(c_row))):
                        if p_row[col_idx] != c_row[col_idx]:
                            insert_at = min(insert_at, col_idx)
                            break
                changes.append(
                    GridChange(
                        change_type="insert_columns",
                        sheet_name=sheet_name,
                        start_index=insert_at,
                        end_index=insert_at + added_count,
                        count=added_count,
                    )
                )
        else:
            # Columns deleted
            deleted_count = pristine_cols - current_cols
            # Find deletion point
            delete_start = pristine_cols
            for row_idx in range(min(len(pristine_grid), len(current_grid))):
                p_row = pristine_grid[row_idx] if row_idx < len(pristine_grid) else []
                c_row = current_grid[row_idx] if row_idx < len(current_grid) else []
                for col_idx in range(min(len(p_row), current_cols)):
                    p_val = p_row[col_idx] if col_idx < len(p_row) else ""
                    c_val = c_row[col_idx] if col_idx < len(c_row) else ""
                    if p_val != c_val:
                        delete_start = min(delete_start, col_idx)
                        break
            changes.append(
                GridChange(
                    change_type="delete_columns",
                    sheet_name=sheet_name,
                    start_index=delete_start,
                    end_index=delete_start + deleted_count,
                    count=deleted_count,
                )
            )

    return changes


def _diff_cells(
    pristine_grid: list[list[str]],
    current_grid: list[list[str]],
    pristine_formulas: dict[str, str],
    current_formulas: dict[str, str],
    grid_changes: list[GridChange] | None = None,
) -> list[CellChange]:
    """Diff cell values between pristine and current.

    Cells with formulas are skipped - formula changes are tracked separately.

    When there are grid changes (row/column insertions or deletions), we need to
    account for the shift in row/column indices. For example, if row 3 is deleted,
    pristine row 4 corresponds to current row 3, not current row 4.
    """
    changes: list[CellChange] = []
    grid_changes = grid_changes or []

    # Calculate row and column offsets based on grid changes
    # A deletion at index N means: for rows >= N, pristine[i] maps to current[i - count]
    # An insertion at index N means: for rows >= N, pristine[i] maps to current[i + count]
    row_deletions: list[tuple[int, int]] = []  # (start_index, count)
    row_insertions: list[tuple[int, int]] = []  # (start_index, count)
    col_deletions: list[tuple[int, int]] = []
    col_insertions: list[tuple[int, int]] = []

    for change in grid_changes:
        if change.change_type == "delete_rows":
            row_deletions.append((change.start_index, change.count))
        elif change.change_type == "insert_rows":
            row_insertions.append((change.start_index, change.count))
        elif change.change_type == "delete_columns":
            col_deletions.append((change.start_index, change.count))
        elif change.change_type == "insert_columns":
            col_insertions.append((change.start_index, change.count))

    def pristine_to_current_row(pristine_row: int) -> int | None:
        """Map a pristine row index to the corresponding current row index.

        Returns None if the row was deleted.
        """
        # Check if this row was deleted
        for start, count in row_deletions:
            if start <= pristine_row < start + count:
                return None  # Row was deleted

        # Calculate offset from deletions (rows before this one that were deleted)
        offset = 0
        for start, count in row_deletions:
            if pristine_row >= start + count:
                offset -= count

        # Calculate offset from insertions (rows before this one that were inserted)
        for start, count in row_insertions:
            if pristine_row >= start:
                offset += count

        return pristine_row + offset

    def pristine_to_current_col(pristine_col: int) -> int | None:
        """Map a pristine column index to the corresponding current column index.

        Returns None if the column was deleted.
        """
        # Check if this column was deleted
        for start, count in col_deletions:
            if start <= pristine_col < start + count:
                return None  # Column was deleted

        # Calculate offset
        offset = 0
        for start, count in col_deletions:
            if pristine_col >= start + count:
                offset -= count
        for start, count in col_insertions:
            if pristine_col >= start:
                offset += count

        return pristine_col + offset

    # If there are grid changes, we need to be careful about how we compare
    if row_deletions or row_insertions or col_deletions or col_insertions:
        # Compare existing pristine cells to their corresponding current positions
        pristine_rows = len(pristine_grid)
        pristine_cols = max((len(row) for row in pristine_grid), default=0)

        for pristine_row in range(pristine_rows):
            current_row = pristine_to_current_row(pristine_row)
            if current_row is None:
                continue  # Row was deleted, skip

            for pristine_col in range(pristine_cols):
                current_col = pristine_to_current_col(pristine_col)
                if current_col is None:
                    continue  # Column was deleted, skip

                # Use current coordinates for cell reference (that's what we're writing to)
                cell_ref = cell_to_a1(current_row, current_col)

                # Skip cells with formulas in the CURRENT position
                if cell_ref in current_formulas:
                    continue

                pristine_val = _get_cell(pristine_grid, pristine_row, pristine_col)
                current_val = _get_cell(current_grid, current_row, current_col)

                if pristine_val != current_val:
                    if pristine_val == "" and current_val != "":
                        change_type: Literal["added", "deleted", "modified"] = "added"
                    elif pristine_val != "" and current_val == "":
                        change_type = "deleted"
                    else:
                        change_type = "modified"

                    changes.append(
                        CellChange(
                            row=current_row,
                            col=current_col,
                            cell_ref=cell_ref,
                            change_type=change_type,
                            old_value=pristine_val if pristine_val else None,
                            new_value=current_val if current_val else None,
                        )
                    )

        # Also check for new content in inserted rows/columns
        current_rows = len(current_grid)
        current_cols_max = max((len(row) for row in current_grid), default=0)

        for start, count in row_insertions:
            for current_row in range(start, min(start + count, current_rows)):
                for current_col in range(current_cols_max):
                    cell_ref = cell_to_a1(current_row, current_col)
                    if cell_ref in current_formulas:
                        continue

                    current_val = _get_cell(current_grid, current_row, current_col)
                    if current_val:
                        changes.append(
                            CellChange(
                                row=current_row,
                                col=current_col,
                                cell_ref=cell_ref,
                                change_type="added",
                                old_value=None,
                                new_value=current_val,
                            )
                        )

        for start, count in col_insertions:
            for current_row in range(current_rows):
                for current_col in range(start, min(start + count, current_cols_max)):
                    cell_ref = cell_to_a1(current_row, current_col)
                    if cell_ref in current_formulas:
                        continue

                    current_val = _get_cell(current_grid, current_row, current_col)
                    if current_val:
                        changes.append(
                            CellChange(
                                row=current_row,
                                col=current_col,
                                cell_ref=cell_ref,
                                change_type="added",
                                old_value=None,
                                new_value=current_val,
                            )
                        )

        return changes

    # No grid changes - simple comparison
    num_rows = max(len(pristine_grid), len(current_grid))
    pristine_cols = max((len(row) for row in pristine_grid), default=0)
    current_cols = max((len(row) for row in current_grid), default=0)
    num_cols = max(pristine_cols, current_cols)

    for row in range(num_rows):
        for col in range(num_cols):
            cell_ref = cell_to_a1(row, col)

            # Skip cells with formulas (formula changes handled separately)
            if cell_ref in pristine_formulas or cell_ref in current_formulas:
                continue

            pristine_val = _get_cell(pristine_grid, row, col)
            current_val = _get_cell(current_grid, row, col)

            if pristine_val != current_val:
                if pristine_val == "" and current_val != "":
                    change_type = "added"
                elif pristine_val != "" and current_val == "":
                    change_type = "deleted"
                else:
                    change_type = "modified"

                changes.append(
                    CellChange(
                        row=row,
                        col=col,
                        cell_ref=cell_ref,
                        change_type=change_type,
                        old_value=pristine_val if pristine_val else None,
                        new_value=current_val if current_val else None,
                    )
                )

    return changes


def _diff_formulas(
    pristine_formulas: dict[str, str],
    current_formulas: dict[str, str],
    grid_changes: list[GridChange] | None = None,
) -> list[FormulaChange]:
    """Diff formulas between pristine and current.

    Works with compressed formula format (ranges like "C2:C100").

    When there are grid changes, pristine formula positions must be mapped to
    post-change coordinates for comparison. For example, if row 5 is inserted,
    pristine D14 maps to current D15.
    """
    changes: list[FormulaChange] = []
    grid_changes = grid_changes or []

    # Build mapping functions based on grid changes
    row_deletions: list[tuple[int, int]] = []
    row_insertions: list[tuple[int, int]] = []
    col_deletions: list[tuple[int, int]] = []
    col_insertions: list[tuple[int, int]] = []

    for change in grid_changes:
        if change.change_type == "delete_rows":
            row_deletions.append((change.start_index, change.count))
        elif change.change_type == "insert_rows":
            row_insertions.append((change.start_index, change.count))
        elif change.change_type == "delete_columns":
            col_deletions.append((change.start_index, change.count))
        elif change.change_type == "insert_columns":
            col_insertions.append((change.start_index, change.count))

    def pristine_to_current_row(pristine_row: int) -> int | None:
        """Map a pristine row to current row, or None if deleted."""
        for start, count in row_deletions:
            if start <= pristine_row < start + count:
                return None
        offset = 0
        for start, count in row_deletions:
            if pristine_row >= start + count:
                offset -= count
        for start, count in row_insertions:
            if pristine_row >= start:
                offset += count
        return pristine_row + offset

    def pristine_to_current_col(pristine_col: int) -> int | None:
        """Map a pristine column to current column, or None if deleted."""
        for start, count in col_deletions:
            if start <= pristine_col < start + count:
                return None
        offset = 0
        for start, count in col_deletions:
            if pristine_col >= start + count:
                offset -= count
        for start, count in col_insertions:
            if pristine_col >= start:
                offset += count
        return pristine_col + offset

    def map_formula_key(key: str) -> str | None:
        """Map a pristine formula key to its current position.

        Returns None if any part of the range was deleted.
        """
        if ":" in key:
            # Range formula
            start_cell, end_cell = key.split(":")
            start_row, start_col = a1_to_cell(start_cell)
            end_row, end_col = a1_to_cell(end_cell)

            new_start_row = pristine_to_current_row(start_row)
            new_start_col = pristine_to_current_col(start_col)
            new_end_row = pristine_to_current_row(end_row)
            new_end_col = pristine_to_current_col(end_col)

            if (
                new_start_row is None
                or new_start_col is None
                or new_end_row is None
                or new_end_col is None
            ):
                return None

            new_start = cell_to_a1(new_start_row, new_start_col)
            new_end = cell_to_a1(new_end_row, new_end_col)
            return f"{new_start}:{new_end}"
        else:
            # Single cell formula
            row, col = a1_to_cell(key)
            new_row = pristine_to_current_row(row)
            new_col = pristine_to_current_col(col)

            if new_row is None or new_col is None:
                return None

            return cell_to_a1(new_row, new_col)

    # If there are grid changes, map pristine keys to current positions
    if row_deletions or row_insertions or col_deletions or col_insertions:
        # Map pristine formulas to their new positions
        mapped_pristine: dict[str, str] = {}
        deleted_formulas: dict[str, str] = {}  # Formulas at deleted positions

        for key, formula in pristine_formulas.items():
            new_key = map_formula_key(key)
            if new_key is None:
                # Formula position was deleted
                deleted_formulas[key] = formula
            else:
                mapped_pristine[new_key] = formula

        # Now compare mapped pristine against current
        all_keys = set(mapped_pristine.keys()) | set(current_formulas.keys())

        for key in all_keys:
            pristine_formula = mapped_pristine.get(key)
            current_formula = current_formulas.get(key)
            is_range = ":" in key

            if pristine_formula is None and current_formula is not None:
                # New formula
                changes.append(
                    FormulaChange(
                        range_key=key,
                        change_type="added",
                        old_formula=None,
                        new_formula=current_formula,
                        is_range=is_range,
                    )
                )
            elif pristine_formula is not None and current_formula is None:
                # Formula deleted (position still exists but formula removed)
                changes.append(
                    FormulaChange(
                        range_key=key,
                        change_type="deleted",
                        old_formula=pristine_formula,
                        new_formula=None,
                        is_range=is_range,
                    )
                )
            elif pristine_formula != current_formula:
                # Modified formula
                changes.append(
                    FormulaChange(
                        range_key=key,
                        change_type="modified",
                        old_formula=pristine_formula,
                        new_formula=current_formula,
                        is_range=is_range,
                    )
                )

        # Note: We don't generate delete changes for formulas at deleted positions
        # because the deleteDimension request handles that automatically

        return changes

    # No grid changes - simple comparison
    all_keys = set(pristine_formulas.keys()) | set(current_formulas.keys())

    for key in all_keys:
        pristine_formula = pristine_formulas.get(key)
        current_formula = current_formulas.get(key)
        is_range = ":" in key

        if pristine_formula is None and current_formula is not None:
            # New formula
            changes.append(
                FormulaChange(
                    range_key=key,
                    change_type="added",
                    old_formula=None,
                    new_formula=current_formula,
                    is_range=is_range,
                )
            )
        elif pristine_formula is not None and current_formula is None:
            # Deleted formula
            changes.append(
                FormulaChange(
                    range_key=key,
                    change_type="deleted",
                    old_formula=pristine_formula,
                    new_formula=None,
                    is_range=is_range,
                )
            )
        elif pristine_formula != current_formula:
            # Modified formula
            changes.append(
                FormulaChange(
                    range_key=key,
                    change_type="modified",
                    old_formula=pristine_formula,
                    new_formula=current_formula,
                    is_range=is_range,
                )
            )

    return changes


def _get_cell(grid: list[list[str]], row: int, col: int) -> str:
    """Get a cell value from a grid, returning empty string for out-of-bounds."""
    if row >= len(grid):
        return ""
    if col >= len(grid[row]):
        return ""
    return grid[row][col]


def parse_range(range_key: str) -> tuple[str, str]:
    """Parse a range key into start and end cell references.

    Args:
        range_key: A1 notation range like "C2:C100"

    Returns:
        Tuple of (start_cell, end_cell) e.g. ("C2", "C100")
    """
    if ":" not in range_key:
        return range_key, range_key
    parts = range_key.split(":")
    return parts[0], parts[1]


def range_to_indices(range_key: str) -> tuple[int, int, int, int]:
    """Convert a range key to row/col indices.

    Args:
        range_key: A1 notation range like "C2:C100"

    Returns:
        Tuple of (start_row, start_col, end_row, end_col) - all 0-based
    """
    start_cell, end_cell = parse_range(range_key)
    start_row, start_col = a1_to_cell(start_cell)
    end_row, end_col = a1_to_cell(end_cell)
    return start_row, start_col, end_row, end_col


def _diff_format_rules(
    pristine_format: dict[str, Any], current_format: dict[str, Any]
) -> list[FormatRuleChange]:
    """Diff format rules between pristine and current.

    Format rules are keyed by their range in A1 notation.
    """
    changes: list[FormatRuleChange] = []

    pristine_rules = pristine_format.get("formatRules", [])
    current_rules = current_format.get("formatRules", [])

    # Build dicts keyed by range for comparison
    pristine_by_range = {rule["range"]: rule["format"] for rule in pristine_rules}
    current_by_range = {rule["range"]: rule["format"] for rule in current_rules}

    all_ranges = set(pristine_by_range.keys()) | set(current_by_range.keys())

    for range_key in all_ranges:
        pristine_fmt = pristine_by_range.get(range_key)
        current_fmt = current_by_range.get(range_key)

        if pristine_fmt is None and current_fmt is not None:
            changes.append(
                FormatRuleChange(
                    range_key=range_key,
                    change_type="added",
                    old_format=None,
                    new_format=current_fmt,
                )
            )
        elif pristine_fmt is not None and current_fmt is None:
            changes.append(
                FormatRuleChange(
                    range_key=range_key,
                    change_type="deleted",
                    old_format=pristine_fmt,
                    new_format=None,
                )
            )
        elif pristine_fmt != current_fmt:
            changes.append(
                FormatRuleChange(
                    range_key=range_key,
                    change_type="modified",
                    old_format=pristine_fmt,
                    new_format=current_fmt,
                )
            )

    return changes


def _diff_data_validation(
    pristine_feature: dict[str, Any], current_feature: dict[str, Any]
) -> list[DataValidationChange]:
    """Diff data validation rules between pristine and current.

    Data validation rules are keyed by their range description.
    Each rule has a 'cells' list with individual cell references.
    """
    changes: list[DataValidationChange] = []

    pristine_rules = pristine_feature.get("dataValidation", [])
    current_rules = current_feature.get("dataValidation", [])

    # Build dicts keyed by range, storing both rule and cells
    pristine_by_range: dict[str, dict[str, Any]] = {}
    for rule in pristine_rules:
        pristine_by_range[rule["range"]] = {
            "rule": rule["rule"],
            "cells": rule.get("cells", []),
        }

    current_by_range: dict[str, dict[str, Any]] = {}
    for rule in current_rules:
        current_by_range[rule["range"]] = {
            "rule": rule["rule"],
            "cells": rule.get("cells", []),
        }

    all_ranges = set(pristine_by_range.keys()) | set(current_by_range.keys())

    for range_key in all_ranges:
        pristine_data = pristine_by_range.get(range_key)
        current_data = current_by_range.get(range_key)

        pristine_rule = pristine_data["rule"] if pristine_data else None
        current_rule = current_data["rule"] if current_data else None
        current_cells = current_data["cells"] if current_data else []
        pristine_cells = pristine_data["cells"] if pristine_data else []

        if pristine_rule is None and current_rule is not None:
            changes.append(
                DataValidationChange(
                    range_key=range_key,
                    cells=current_cells,
                    change_type="added",
                    old_rule=None,
                    new_rule=current_rule,
                )
            )
        elif pristine_rule is not None and current_rule is None:
            changes.append(
                DataValidationChange(
                    range_key=range_key,
                    cells=pristine_cells,
                    change_type="deleted",
                    old_rule=pristine_rule,
                    new_rule=None,
                )
            )
        elif pristine_rule != current_rule:
            changes.append(
                DataValidationChange(
                    range_key=range_key,
                    cells=current_cells,
                    change_type="modified",
                    old_rule=pristine_rule,
                    new_rule=current_rule,
                )
            )

    return changes


def _diff_dimensions(
    pristine_dimension: dict[str, Any], current_dimension: dict[str, Any]
) -> list[DimensionChange]:
    """Diff row/column dimensions between pristine and current.

    Handles both old format (0-based index) and new A1 format:
    - Columns: use "column" (letter like "A") or "index" (0-based)
    - Rows: use "row" (1-based number) or "index" (0-based)
    """
    changes: list[DimensionChange] = []

    def get_col_index(col: dict[str, Any]) -> int:
        """Get 0-based column index from column letter or index."""
        if "column" in col:
            return letter_to_column_index(col["column"])
        return int(col.get("index", 0))

    def get_row_index(row: dict[str, Any]) -> int:
        """Get 0-based row index from 1-based row number or index."""
        if "row" in row:
            return int(row["row"]) - 1  # Convert 1-based to 0-based
        return int(row.get("index", 0))

    # Diff column dimensions
    pristine_cols = pristine_dimension.get("columnMetadata", [])
    current_cols = current_dimension.get("columnMetadata", [])

    pristine_cols_by_idx = {
        get_col_index(col): col.get("pixelSize") for col in pristine_cols
    }
    current_cols_by_idx = {
        get_col_index(col): col.get("pixelSize") for col in current_cols
    }

    all_col_indices = set(pristine_cols_by_idx.keys()) | set(current_cols_by_idx.keys())

    for idx in all_col_indices:
        pristine_size = pristine_cols_by_idx.get(idx)
        current_size = current_cols_by_idx.get(idx)

        if pristine_size is None and current_size is not None:
            changes.append(
                DimensionChange(
                    dimension_type="COLUMNS",
                    index=idx,
                    change_type="added",
                    old_size=None,
                    new_size=current_size,
                )
            )
        elif pristine_size is not None and current_size is None:
            changes.append(
                DimensionChange(
                    dimension_type="COLUMNS",
                    index=idx,
                    change_type="deleted",
                    old_size=pristine_size,
                    new_size=None,
                )
            )
        elif pristine_size != current_size:
            changes.append(
                DimensionChange(
                    dimension_type="COLUMNS",
                    index=idx,
                    change_type="modified",
                    old_size=pristine_size,
                    new_size=current_size,
                )
            )

    # Diff row dimensions
    pristine_rows = pristine_dimension.get("rowMetadata", [])
    current_rows = current_dimension.get("rowMetadata", [])

    pristine_rows_by_idx = {
        get_row_index(row): row.get("pixelSize") for row in pristine_rows
    }
    current_rows_by_idx = {
        get_row_index(row): row.get("pixelSize") for row in current_rows
    }

    all_row_indices = set(pristine_rows_by_idx.keys()) | set(current_rows_by_idx.keys())

    for idx in all_row_indices:
        pristine_size = pristine_rows_by_idx.get(idx)
        current_size = current_rows_by_idx.get(idx)

        if pristine_size is None and current_size is not None:
            changes.append(
                DimensionChange(
                    dimension_type="ROWS",
                    index=idx,
                    change_type="added",
                    old_size=None,
                    new_size=current_size,
                )
            )
        elif pristine_size is not None and current_size is None:
            changes.append(
                DimensionChange(
                    dimension_type="ROWS",
                    index=idx,
                    change_type="deleted",
                    old_size=pristine_size,
                    new_size=None,
                )
            )
        elif pristine_size != current_size:
            changes.append(
                DimensionChange(
                    dimension_type="ROWS",
                    index=idx,
                    change_type="modified",
                    old_size=pristine_size,
                    new_size=current_size,
                )
            )

    return changes


def _diff_text_format_runs(
    pristine_format: dict[str, Any], current_format: dict[str, Any]
) -> list[TextFormatRunChange]:
    """Diff text format runs (rich text) between pristine and current.

    Text format runs are stored in format.json under 'textFormatRuns',
    keyed by cell reference.
    """
    changes: list[TextFormatRunChange] = []

    pristine_runs = pristine_format.get("textFormatRuns", {})
    current_runs = current_format.get("textFormatRuns", {})

    all_cells = set(pristine_runs.keys()) | set(current_runs.keys())

    for cell_ref in all_cells:
        pristine_run = pristine_runs.get(cell_ref)
        current_run = current_runs.get(cell_ref)

        if pristine_run is None and current_run is not None:
            changes.append(
                TextFormatRunChange(
                    cell_ref=cell_ref,
                    change_type="added",
                    old_runs=None,
                    new_runs=current_run,
                )
            )
        elif pristine_run is not None and current_run is None:
            changes.append(
                TextFormatRunChange(
                    cell_ref=cell_ref,
                    change_type="deleted",
                    old_runs=pristine_run,
                    new_runs=None,
                )
            )
        elif pristine_run != current_run:
            changes.append(
                TextFormatRunChange(
                    cell_ref=cell_ref,
                    change_type="modified",
                    old_runs=pristine_run,
                    new_runs=current_run,
                )
            )

    return changes


def _diff_notes(
    pristine_format: dict[str, Any], current_format: dict[str, Any]
) -> list[NoteChange]:
    """Diff cell notes between pristine and current.

    Notes are stored in format.json under 'notes', keyed by cell reference.
    """
    changes: list[NoteChange] = []

    pristine_notes = pristine_format.get("notes", {})
    current_notes = current_format.get("notes", {})

    all_cells = set(pristine_notes.keys()) | set(current_notes.keys())

    for cell_ref in all_cells:
        pristine_note = pristine_notes.get(cell_ref)
        current_note = current_notes.get(cell_ref)

        if pristine_note is None and current_note is not None:
            changes.append(
                NoteChange(
                    cell_ref=cell_ref,
                    change_type="added",
                    old_note=None,
                    new_note=current_note,
                )
            )
        elif pristine_note is not None and current_note is None:
            changes.append(
                NoteChange(
                    cell_ref=cell_ref,
                    change_type="deleted",
                    old_note=pristine_note,
                    new_note=None,
                )
            )
        elif pristine_note != current_note:
            changes.append(
                NoteChange(
                    cell_ref=cell_ref,
                    change_type="modified",
                    old_note=pristine_note,
                    new_note=current_note,
                )
            )

    return changes


def _diff_merges(
    pristine_format: dict[str, Any], current_format: dict[str, Any]
) -> list[MergeChange]:
    """Diff merged cell ranges between pristine and current.

    Merges are stored in format.json under 'merges' with A1 notation range.
    We parse the A1 range to get 0-based indices for the API.
    """
    changes: list[MergeChange] = []

    pristine_merges = pristine_format.get("merges", [])
    current_merges = current_format.get("merges", [])

    # Build dicts keyed by range
    pristine_by_range = {m["range"]: m for m in pristine_merges}
    current_by_range = {m["range"]: m for m in current_merges}

    all_ranges = set(pristine_by_range.keys()) | set(current_by_range.keys())

    for range_key in all_ranges:
        pristine_merge = pristine_by_range.get(range_key)
        current_merge = current_by_range.get(range_key)

        if pristine_merge is None and current_merge is not None:
            # New merge - parse A1 range to get indices
            grid_range = a1_range_to_grid_range(range_key)
            changes.append(
                MergeChange(
                    range_key=range_key,
                    change_type="added",
                    start_row=grid_range["startRowIndex"],
                    end_row=grid_range["endRowIndex"],
                    start_col=grid_range["startColumnIndex"],
                    end_col=grid_range["endColumnIndex"],
                )
            )
        elif pristine_merge is not None and current_merge is None:
            # Deleted merge - parse A1 range to get indices
            grid_range = a1_range_to_grid_range(range_key)
            changes.append(
                MergeChange(
                    range_key=range_key,
                    change_type="deleted",
                    start_row=grid_range["startRowIndex"],
                    end_row=grid_range["endRowIndex"],
                    start_col=grid_range["startColumnIndex"],
                    end_col=grid_range["endColumnIndex"],
                )
            )
        # Note: merges don't have "modified" - same range means same merge

    return changes


def _auto_assign_rule_indices(
    current_rules: list[dict[str, Any]], pristine_rules: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Auto-assign ruleIndex to rules that don't have one.

    New rules without ruleIndex get assigned indices starting after the
    maximum existing index from both pristine and current rules.
    """
    # Find max existing ruleIndex
    all_indices: list[int] = []
    for r in pristine_rules + current_rules:
        idx = r.get("ruleIndex")
        if idx is not None:
            all_indices.append(int(idx))
    next_index = max(all_indices, default=-1) + 1

    # Process current rules, assigning indices where missing
    result = []
    for rule in current_rules:
        if rule.get("ruleIndex") is None:
            # Auto-assign index
            rule_copy = dict(rule)
            rule_copy["ruleIndex"] = next_index
            next_index += 1
            result.append(rule_copy)
        else:
            result.append(rule)

    return result


def _diff_conditional_formats(
    pristine_format: dict[str, Any], current_format: dict[str, Any]
) -> list[ConditionalFormatChange]:
    """Diff conditional format rules between pristine and current.

    Conditional formats are stored in format.json under 'conditionalFormats'.
    Each rule has a ruleIndex for identification. If ruleIndex is missing,
    it will be auto-assigned.
    """
    changes: list[ConditionalFormatChange] = []

    pristine_rules = pristine_format.get("conditionalFormats", [])
    current_rules = current_format.get("conditionalFormats", [])

    # Auto-assign ruleIndex to current rules that don't have one
    current_rules = _auto_assign_rule_indices(current_rules, pristine_rules)

    # Build dicts keyed by ruleIndex
    pristine_by_idx = {r.get("ruleIndex"): r for r in pristine_rules}
    current_by_idx = {r.get("ruleIndex"): r for r in current_rules}

    # Find deleted and modified rules
    for idx, pristine_rule in pristine_by_idx.items():
        current_rule = current_by_idx.get(idx)
        if current_rule is None:
            # Rule was deleted
            changes.append(
                ConditionalFormatChange(
                    rule_index=idx,
                    change_type="deleted",
                    old_rule=pristine_rule,
                    new_rule=None,
                )
            )
        elif _rules_differ(pristine_rule, current_rule):
            # Rule was modified
            changes.append(
                ConditionalFormatChange(
                    rule_index=idx,
                    change_type="modified",
                    old_rule=pristine_rule,
                    new_rule=current_rule,
                )
            )

    # Find added rules (rules in current but not in pristine)
    for idx, current_rule in current_by_idx.items():
        if idx not in pristine_by_idx:
            changes.append(
                ConditionalFormatChange(
                    rule_index=idx,
                    change_type="added",
                    old_rule=None,
                    new_rule=current_rule,
                )
            )

    return changes


def _rules_differ(rule1: dict[str, Any], rule2: dict[str, Any]) -> bool:
    """Check if two conditional format rules differ (ignoring ruleIndex)."""
    # Compare everything except ruleIndex
    r1 = {k: v for k, v in rule1.items() if k != "ruleIndex"}
    r2 = {k: v for k, v in rule2.items() if k != "ruleIndex"}
    return r1 != r2


def _diff_basic_filter(
    pristine_feature: dict[str, Any], current_feature: dict[str, Any]
) -> BasicFilterChange | None:
    """Diff basic filter between pristine and current.

    Basic filter is stored in feature.json under 'basicFilter'.
    """
    pristine_filter = pristine_feature.get("basicFilter")
    current_filter = current_feature.get("basicFilter")

    if pristine_filter is None and current_filter is not None:
        return BasicFilterChange(
            change_type="added",
            old_filter=None,
            new_filter=current_filter,
        )
    elif pristine_filter is not None and current_filter is None:
        return BasicFilterChange(
            change_type="deleted",
            old_filter=pristine_filter,
            new_filter=None,
        )
    elif pristine_filter != current_filter:
        return BasicFilterChange(
            change_type="modified",
            old_filter=pristine_filter,
            new_filter=current_filter,
        )

    return None


def _diff_banded_ranges(
    pristine_feature: dict[str, Any], current_feature: dict[str, Any]
) -> list[BandedRangeChange]:
    """Diff banded ranges between pristine and current.

    Banded ranges are stored in feature.json under 'bandedRanges'.
    Each range has a bandedRangeId for identification.
    """
    changes: list[BandedRangeChange] = []

    pristine_ranges = pristine_feature.get("bandedRanges", [])
    current_ranges = current_feature.get("bandedRanges", [])

    # Build dicts keyed by bandedRangeId
    pristine_by_id = {r.get("bandedRangeId"): r for r in pristine_ranges}
    current_by_id = {r.get("bandedRangeId"): r for r in current_ranges}

    # Find deleted and modified ranges
    for range_id, pristine_range in pristine_by_id.items():
        current_range = current_by_id.get(range_id)
        if current_range is None:
            # Range was deleted
            changes.append(
                BandedRangeChange(
                    banded_range_id=range_id,
                    change_type="deleted",
                    old_range=pristine_range,
                    new_range=None,
                )
            )
        elif _banded_ranges_differ(pristine_range, current_range):
            # Range was modified
            changes.append(
                BandedRangeChange(
                    banded_range_id=range_id,
                    change_type="modified",
                    old_range=pristine_range,
                    new_range=current_range,
                )
            )

    # Find added ranges (ranges in current but not in pristine)
    for range_id, current_range in current_by_id.items():
        if range_id not in pristine_by_id:
            changes.append(
                BandedRangeChange(
                    banded_range_id=range_id,
                    change_type="added",
                    old_range=None,
                    new_range=current_range,
                )
            )

    return changes


def _banded_ranges_differ(range1: dict[str, Any], range2: dict[str, Any]) -> bool:
    """Check if two banded ranges differ (ignoring bandedRangeId)."""
    # Compare everything except bandedRangeId
    r1 = {k: v for k, v in range1.items() if k != "bandedRangeId"}
    r2 = {k: v for k, v in range2.items() if k != "bandedRangeId"}
    return r1 != r2


def _diff_filter_views(
    pristine_feature: dict[str, Any], current_feature: dict[str, Any]
) -> list[FilterViewChange]:
    """Diff filter views between pristine and current.

    Filter views are stored in feature.json under 'filterViews'.
    Each view has a filterViewId for identification.
    """
    changes: list[FilterViewChange] = []

    pristine_views = pristine_feature.get("filterViews", [])
    current_views = current_feature.get("filterViews", [])

    # Build dicts keyed by filterViewId
    pristine_by_id = {v.get("filterViewId"): v for v in pristine_views}
    current_by_id = {v.get("filterViewId"): v for v in current_views}

    # Find deleted and modified views
    for view_id, pristine_view in pristine_by_id.items():
        current_view = current_by_id.get(view_id)
        if current_view is None:
            # View was deleted
            changes.append(
                FilterViewChange(
                    filter_view_id=view_id,
                    change_type="deleted",
                    old_view=pristine_view,
                    new_view=None,
                )
            )
        elif _filter_views_differ(pristine_view, current_view):
            # View was modified
            changes.append(
                FilterViewChange(
                    filter_view_id=view_id,
                    change_type="modified",
                    old_view=pristine_view,
                    new_view=current_view,
                )
            )

    # Find added views (views in current but not in pristine)
    for view_id, current_view in current_by_id.items():
        if view_id not in pristine_by_id:
            changes.append(
                FilterViewChange(
                    filter_view_id=view_id,
                    change_type="added",
                    old_view=None,
                    new_view=current_view,
                )
            )

    return changes


def _filter_views_differ(view1: dict[str, Any], view2: dict[str, Any]) -> bool:
    """Check if two filter views differ (ignoring filterViewId)."""
    # Compare everything except filterViewId
    v1 = {k: v for k, v in view1.items() if k != "filterViewId"}
    v2 = {k: v for k, v in view2.items() if k != "filterViewId"}
    return v1 != v2


def _diff_charts(
    pristine_feature: dict[str, Any], current_feature: dict[str, Any]
) -> list[ChartChange]:
    """Diff charts between pristine and current.

    Charts are stored in feature.json under 'charts'.
    Each chart has a chartId for identification.
    """
    changes: list[ChartChange] = []

    pristine_charts = pristine_feature.get("charts", [])
    current_charts = current_feature.get("charts", [])

    # Build dicts keyed by chartId
    pristine_by_id = {c.get("chartId"): c for c in pristine_charts}
    current_by_id = {c.get("chartId"): c for c in current_charts}

    # Find deleted and modified charts
    for chart_id, pristine_chart in pristine_by_id.items():
        current_chart = current_by_id.get(chart_id)
        if current_chart is None:
            # Chart was deleted
            changes.append(
                ChartChange(
                    chart_id=chart_id,
                    change_type="deleted",
                    old_chart=pristine_chart,
                    new_chart=None,
                )
            )
        elif _charts_differ(pristine_chart, current_chart):
            # Chart was modified
            changes.append(
                ChartChange(
                    chart_id=chart_id,
                    change_type="modified",
                    old_chart=pristine_chart,
                    new_chart=current_chart,
                )
            )

    # Find added charts (charts in current but not in pristine)
    for chart_id, current_chart in current_by_id.items():
        if chart_id not in pristine_by_id:
            changes.append(
                ChartChange(
                    chart_id=chart_id,
                    change_type="added",
                    old_chart=None,
                    new_chart=current_chart,
                )
            )

    return changes


def _charts_differ(chart1: dict[str, Any], chart2: dict[str, Any]) -> bool:
    """Check if two charts differ (ignoring chartId)."""
    # Compare everything except chartId
    c1 = {k: v for k, v in chart1.items() if k != "chartId"}
    c2 = {k: v for k, v in chart2.items() if k != "chartId"}
    return c1 != c2


def _diff_pivot_tables(
    pristine_feature: dict[str, Any], current_feature: dict[str, Any]
) -> list[PivotTableChange]:
    """Diff pivot tables between pristine and current.

    Pivot tables are keyed by their anchorCell (A1 notation).
    """
    changes: list[PivotTableChange] = []

    pristine_pivots = pristine_feature.get("pivotTables", [])
    current_pivots = current_feature.get("pivotTables", [])

    # Build dicts keyed by anchorCell
    pristine_by_anchor = {p.get("anchorCell"): p for p in pristine_pivots}
    current_by_anchor = {p.get("anchorCell"): p for p in current_pivots}

    # Find deleted and modified pivot tables
    for anchor_cell, pristine_pivot in pristine_by_anchor.items():
        current_pivot = current_by_anchor.get(anchor_cell)
        if current_pivot is None:
            # Pivot table was deleted
            changes.append(
                PivotTableChange(
                    anchor_cell=anchor_cell,
                    change_type="deleted",
                    old_pivot=pristine_pivot,
                    new_pivot=None,
                )
            )
        elif _pivot_tables_differ(pristine_pivot, current_pivot):
            # Pivot table was modified
            changes.append(
                PivotTableChange(
                    anchor_cell=anchor_cell,
                    change_type="modified",
                    old_pivot=pristine_pivot,
                    new_pivot=current_pivot,
                )
            )

    # Find added pivot tables (pivot tables in current but not in pristine)
    for anchor_cell, current_pivot in current_by_anchor.items():
        if anchor_cell not in pristine_by_anchor:
            changes.append(
                PivotTableChange(
                    anchor_cell=anchor_cell,
                    change_type="added",
                    old_pivot=None,
                    new_pivot=current_pivot,
                )
            )

    return changes


def _pivot_tables_differ(pivot1: dict[str, Any], pivot2: dict[str, Any]) -> bool:
    """Check if two pivot tables differ (ignoring anchorCell)."""
    # Compare everything except anchorCell
    p1 = {k: v for k, v in pivot1.items() if k != "anchorCell"}
    p2 = {k: v for k, v in pivot2.items() if k != "anchorCell"}
    return p1 != p2


def _read_feature_data(
    pristine_files: dict[str, str | bytes],
    current_files: dict[str, str],
    folder_name: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read feature data from separate files or legacy feature.json.

    Supports both the new split format (charts.json, pivot-tables.json, etc.)
    and the legacy feature.json format for backward compatibility.

    New format files take precedence over legacy feature.json.

    Args:
        pristine_files: Files from the pristine zip
        current_files: Files from the current folder
        folder_name: Name of the sheet folder

    Returns:
        Tuple of (pristine_feature_data, current_feature_data)
    """
    # File mapping: new file name -> feature key
    feature_files = {
        "charts.json": "charts",
        "pivot-tables.json": "pivotTables",
        "tables.json": "tables",
        "filters.json": None,  # Special handling for basicFilter + filterViews
        "banded-ranges.json": "bandedRanges",
        "data-validation.json": "dataValidation",
        "slicers.json": "slicers",
        "data-source-tables.json": "dataSourceTables",
    }

    def read_pristine_features(
        files: dict[str, str | bytes],
    ) -> dict[str, Any]:
        """Read feature data from pristine files."""
        result: dict[str, Any] = {}

        # First, try to read from legacy feature.json
        legacy_path = f"{folder_name}/feature.json"
        legacy_str = get_pristine_file(files, legacy_path)

        if legacy_str:
            result = json.loads(legacy_str)

        # Then, override with separate files if they exist
        for filename, feature_key in feature_files.items():
            file_path = f"{folder_name}/{filename}"
            content_str = get_pristine_file(files, file_path)

            if content_str:
                content = json.loads(content_str)
                if filename == "filters.json":
                    # Special handling: filters.json contains basicFilter + filterViews
                    if "basicFilter" in content:
                        result["basicFilter"] = content["basicFilter"]
                    if "filterViews" in content:
                        result["filterViews"] = content["filterViews"]
                elif feature_key and feature_key in content:
                    result[feature_key] = content[feature_key]

        return result

    def read_current_features(
        files: dict[str, str],
    ) -> dict[str, Any]:
        """Read feature data from current files."""
        result: dict[str, Any] = {}

        # First, try to read from legacy feature.json
        legacy_path = f"{folder_name}/feature.json"
        legacy_str = files.get(legacy_path)

        if legacy_str:
            result = json.loads(legacy_str)

        # Then, override with separate files if they exist
        for filename, feature_key in feature_files.items():
            file_path = f"{folder_name}/{filename}"
            content_str = files.get(file_path)

            if content_str:
                content = json.loads(content_str)
                if filename == "filters.json":
                    # Special handling: filters.json contains basicFilter + filterViews
                    if "basicFilter" in content:
                        result["basicFilter"] = content["basicFilter"]
                    if "filterViews" in content:
                        result["filterViews"] = content["filterViews"]
                elif feature_key and feature_key in content:
                    result[feature_key] = content[feature_key]

        return result

    pristine_feature = read_pristine_features(pristine_files)
    current_feature = read_current_features(current_files)

    return pristine_feature, current_feature


def _diff_tables(
    pristine_feature: dict[str, Any], current_feature: dict[str, Any]
) -> list[TableChange]:
    """Diff tables between pristine and current.

    Tables are keyed by their tableId.
    """
    changes: list[TableChange] = []

    pristine_tables = pristine_feature.get("tables", [])
    current_tables = current_feature.get("tables", [])

    # Build lookup by tableId
    pristine_by_id = {t.get("tableId"): t for t in pristine_tables if t.get("tableId")}
    current_by_id = {t.get("tableId"): t for t in current_tables if t.get("tableId")}

    # Find deleted and modified tables
    for table_id, pristine_table in pristine_by_id.items():
        current_table = current_by_id.get(table_id)
        if current_table is None:
            # Table was deleted
            changes.append(
                TableChange(
                    table_id=table_id,
                    table_name=pristine_table.get("name", ""),
                    change_type="deleted",
                    old_table=pristine_table,
                    new_table=None,
                )
            )
        elif _tables_differ(pristine_table, current_table):
            # Table was modified
            changes.append(
                TableChange(
                    table_id=table_id,
                    table_name=current_table.get("name", ""),
                    change_type="modified",
                    old_table=pristine_table,
                    new_table=current_table,
                )
            )

    # Find added tables (tables in current but not in pristine)
    for table_id, current_table in current_by_id.items():
        if table_id not in pristine_by_id:
            changes.append(
                TableChange(
                    table_id=table_id,
                    table_name=current_table.get("name", ""),
                    change_type="added",
                    old_table=None,
                    new_table=current_table,
                )
            )

    # Handle tables without tableId (new tables added by user)
    # These won't have a tableId yet
    current_without_id = [t for t in current_tables if not t.get("tableId")]
    for table in current_without_id:
        changes.append(
            TableChange(
                table_id=None,
                table_name=table.get("name", ""),
                change_type="added",
                old_table=None,
                new_table=table,
            )
        )

    return changes


def _tables_differ(table1: dict[str, Any], table2: dict[str, Any]) -> bool:
    """Check if two tables differ."""
    # Compare all fields
    return table1 != table2


def _diff_named_ranges(
    pristine_files: dict[str, str | bytes],
    current_files: dict[str, str],
) -> list[NamedRangeChange]:
    """Diff named ranges between pristine and current.

    Named ranges are stored at the spreadsheet level in named_ranges.json.
    """
    changes: list[NamedRangeChange] = []

    # Read named ranges from files
    pristine_str = get_pristine_file(pristine_files, "named_ranges.json")
    current_str = current_files.get("named_ranges.json")

    pristine_data = json.loads(pristine_str) if pristine_str else {}
    current_data = json.loads(current_str) if current_str else {}

    pristine_ranges = pristine_data.get("namedRanges", [])
    current_ranges = current_data.get("namedRanges", [])

    # Build lookup by namedRangeId
    pristine_by_id = {
        r.get("namedRangeId"): r for r in pristine_ranges if r.get("namedRangeId")
    }
    current_by_id = {
        r.get("namedRangeId"): r for r in current_ranges if r.get("namedRangeId")
    }

    # Find deleted and modified named ranges
    for range_id, pristine_range in pristine_by_id.items():
        current_range = current_by_id.get(range_id)
        if current_range is None:
            # Named range was deleted
            changes.append(
                NamedRangeChange(
                    named_range_id=range_id,
                    name=pristine_range.get("name", ""),
                    change_type="deleted",
                    old_range=pristine_range,
                    new_range=None,
                )
            )
        elif _named_ranges_differ(pristine_range, current_range):
            # Named range was modified
            changes.append(
                NamedRangeChange(
                    named_range_id=range_id,
                    name=current_range.get("name", ""),
                    change_type="modified",
                    old_range=pristine_range,
                    new_range=current_range,
                )
            )

    # Find added named ranges (in current but not in pristine)
    for range_id, current_range in current_by_id.items():
        if range_id not in pristine_by_id:
            changes.append(
                NamedRangeChange(
                    named_range_id=range_id,
                    name=current_range.get("name", ""),
                    change_type="added",
                    old_range=None,
                    new_range=current_range,
                )
            )

    # Handle named ranges without namedRangeId (new ranges added by user)
    current_without_id = [r for r in current_ranges if not r.get("namedRangeId")]
    for named_range in current_without_id:
        changes.append(
            NamedRangeChange(
                named_range_id=None,
                name=named_range.get("name", ""),
                change_type="added",
                old_range=None,
                new_range=named_range,
            )
        )

    return changes


def _named_ranges_differ(range1: dict[str, Any], range2: dict[str, Any]) -> bool:
    """Check if two named ranges differ."""
    # Compare all fields
    return range1 != range2


def _diff_slicers(
    pristine_feature: dict[str, Any], current_feature: dict[str, Any]
) -> list[SlicerChange]:
    """Diff slicers between pristine and current.

    Slicers are identified by their slicerId.
    """
    changes: list[SlicerChange] = []

    pristine_slicers = pristine_feature.get("slicers", [])
    current_slicers = current_feature.get("slicers", [])

    # Build dicts keyed by slicerId
    pristine_by_id = {s.get("slicerId"): s for s in pristine_slicers}
    current_by_id = {s.get("slicerId"): s for s in current_slicers}

    # Find deleted and modified slicers
    for slicer_id, pristine_slicer in pristine_by_id.items():
        current_slicer = current_by_id.get(slicer_id)
        if current_slicer is None:
            # Slicer was deleted
            changes.append(
                SlicerChange(
                    slicer_id=slicer_id,
                    change_type="deleted",
                    old_slicer=pristine_slicer,
                    new_slicer=None,
                )
            )
        elif _slicers_differ(pristine_slicer, current_slicer):
            # Slicer was modified
            changes.append(
                SlicerChange(
                    slicer_id=slicer_id,
                    change_type="modified",
                    old_slicer=pristine_slicer,
                    new_slicer=current_slicer,
                )
            )

    # Find added slicers (in current but not in pristine)
    for slicer_id, current_slicer in current_by_id.items():
        if slicer_id not in pristine_by_id:
            changes.append(
                SlicerChange(
                    slicer_id=slicer_id,
                    change_type="added",
                    old_slicer=None,
                    new_slicer=current_slicer,
                )
            )

    # Handle slicers without slicerId (new slicers added by user)
    current_without_id = [s for s in current_slicers if not s.get("slicerId")]
    for slicer in current_without_id:
        changes.append(
            SlicerChange(
                slicer_id=None,
                change_type="added",
                old_slicer=None,
                new_slicer=slicer,
            )
        )

    return changes


def _slicers_differ(slicer1: dict[str, Any], slicer2: dict[str, Any]) -> bool:
    """Check if two slicers differ (ignoring slicerId)."""
    s1 = {k: v for k, v in slicer1.items() if k != "slicerId"}
    s2 = {k: v for k, v in slicer2.items() if k != "slicerId"}
    return s1 != s2


def _diff_data_source_tables(
    pristine_feature: dict[str, Any], current_feature: dict[str, Any]
) -> list[DataSourceTableChange]:
    """Diff data source tables between pristine and current.

    Data source tables are anchored at a cell position.
    Each entry has an anchorCell key for identification.
    """
    changes: list[DataSourceTableChange] = []

    pristine_tables = pristine_feature.get("dataSourceTables", [])
    current_tables = current_feature.get("dataSourceTables", [])

    # Build dicts keyed by anchorCell
    pristine_by_anchor = {t.get("anchorCell"): t for t in pristine_tables}
    current_by_anchor = {t.get("anchorCell"): t for t in current_tables}

    # Find deleted and modified data source tables
    for anchor, pristine_table in pristine_by_anchor.items():
        current_table = current_by_anchor.get(anchor)
        if current_table is None:
            # Table was deleted
            changes.append(
                DataSourceTableChange(
                    anchor_cell=anchor or "",
                    change_type="deleted",
                    old_table=pristine_table,
                    new_table=None,
                )
            )
        elif _data_source_tables_differ(pristine_table, current_table):
            # Table was modified
            changes.append(
                DataSourceTableChange(
                    anchor_cell=anchor or "",
                    change_type="modified",
                    old_table=pristine_table,
                    new_table=current_table,
                )
            )

    # Find added data source tables (in current but not in pristine)
    for anchor, current_table in current_by_anchor.items():
        if anchor not in pristine_by_anchor:
            changes.append(
                DataSourceTableChange(
                    anchor_cell=anchor or "",
                    change_type="added",
                    old_table=None,
                    new_table=current_table,
                )
            )

    return changes


def _data_source_tables_differ(table1: dict[str, Any], table2: dict[str, Any]) -> bool:
    """Check if two data source tables differ."""
    return table1 != table2
