"""Structural change validation for extrasheet.

Validates that structural changes (insert/delete rows/columns, delete sheets)
are safe to apply alongside other changes in the same diff.

Severity Levels:
- BLOCK: Silent bug - would cause data corruption without visible indication
- WARN: Will break something, but the break is visible (shows as #REF! etc.)
- SILENT: Ambiguous but valid - proceed without comment
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

from extrasheet.file_reader import parse_tsv, read_current_files
from extrasheet.formula_compression import expand_formulas
from extrasheet.formula_refs import FormulaParseResult, parse_formula
from extrasheet.pristine import extract_pristine, get_pristine_file
from extrasheet.utils import a1_to_cell, cell_to_a1, column_index_to_letter

if TYPE_CHECKING:
    from pathlib import Path


class StructuralChangeType(Enum):
    """Types of structural changes."""

    APPEND_ROWS = "append_rows"
    APPEND_COLUMNS = "append_columns"
    INSERT_ROWS = "insert_rows"
    INSERT_COLUMNS = "insert_columns"
    DELETE_ROWS = "delete_rows"
    DELETE_COLUMNS = "delete_columns"
    DELETE_SHEET = "delete_sheet"


@dataclass
class StructuralChange:
    """Represents a detected structural change."""

    change_type: StructuralChangeType
    sheet_name: str
    # For row/column changes
    start_index: int | None = None  # 0-based, where change starts
    end_index: int | None = None  # 0-based, where change ends (exclusive)
    count: int = 0  # Number of rows/columns affected


@dataclass
class ValidationResult:
    """Result of structural change validation."""

    blocks: list[str] = field(default_factory=list)  # Hard errors - cannot proceed
    warnings: list[str] = field(
        default_factory=list
    )  # Soft warnings - can proceed with --force
    structural_changes: list[StructuralChange] = field(default_factory=list)

    @property
    def can_push(self) -> bool:
        """Check if push can proceed (no blocks)."""
        return len(self.blocks) == 0

    @property
    def has_warnings(self) -> bool:
        """Check if there are warnings."""
        return len(self.warnings) > 0

    @property
    def has_structural_changes(self) -> bool:
        """Check if there are any structural changes."""
        return len(self.structural_changes) > 0


@dataclass
class SheetFormulas:
    """Collected formulas for a sheet."""

    # Formulas keyed by cell reference (expanded from ranges)
    pristine_formulas: dict[str, str]
    current_formulas: dict[str, str]
    # Parsed references from all formulas
    pristine_parsed: list[FormulaParseResult]
    current_parsed: list[FormulaParseResult]


def validate_structural_changes(folder: Path) -> ValidationResult:
    """Validate structural changes in a folder.

    This should be called before generating batchUpdate requests.
    It detects structural changes (row/column inserts/deletes, sheet deletes)
    and validates them against formula changes.

    Args:
        folder: Path to the spreadsheet folder

    Returns:
        ValidationResult with blocks, warnings, and detected structural changes
    """
    result = ValidationResult()

    # Extract pristine and current files
    pristine_files = extract_pristine(folder)
    current_files = read_current_files(folder)

    # Parse spreadsheet.json for metadata
    pristine_meta_str = get_pristine_file(pristine_files, "spreadsheet.json")
    current_meta_str = current_files.get("spreadsheet.json")

    if not pristine_meta_str or not current_meta_str:
        return result

    pristine_meta = json.loads(pristine_meta_str)
    current_meta = json.loads(current_meta_str)

    # Build sheet mappings
    pristine_sheets = {s["folder"]: s for s in pristine_meta.get("sheets", [])}
    current_sheets = {s["folder"]: s for s in current_meta.get("sheets", [])}

    # Collect all formulas from all sheets (for cross-sheet reference checking)
    all_formulas = _collect_all_formulas(pristine_files, current_files, pristine_sheets)

    # Detect deleted sheets
    for folder_name in pristine_sheets:
        if folder_name not in current_sheets:
            sheet_name = pristine_sheets[folder_name].get("title", folder_name)
            result.structural_changes.append(
                StructuralChange(
                    change_type=StructuralChangeType.DELETE_SHEET,
                    sheet_name=sheet_name,
                )
            )

    # Check each sheet for dimension changes
    for folder_name, current_sheet in current_sheets.items():
        pristine_sheet = pristine_sheets.get(folder_name)
        if not pristine_sheet:
            # New sheet - no structural validation needed
            continue

        sheet_name = current_sheet.get("title", folder_name)

        # Get data.tsv files
        data_path = f"{folder_name}/data.tsv"
        pristine_tsv = get_pristine_file(pristine_files, data_path)
        current_tsv = current_files.get(data_path)

        if not pristine_tsv or not current_tsv:
            continue

        # Parse TSV into grids
        pristine_grid = parse_tsv(pristine_tsv)
        current_grid = parse_tsv(current_tsv)

        pristine_rows = len(pristine_grid)
        current_rows = len(current_grid)
        pristine_cols = max((len(row) for row in pristine_grid), default=0)
        current_cols = max((len(row) for row in current_grid), default=0)

        # Detect row changes
        if current_rows != pristine_rows:
            if current_rows > pristine_rows:
                # Rows added - check if at end (append) or middle (insert)
                change = _detect_row_addition(pristine_grid, current_grid, sheet_name)
            else:
                # Rows deleted
                change = _detect_row_deletion(pristine_grid, current_grid, sheet_name)
            if change:
                result.structural_changes.append(change)

        # Detect column changes
        if current_cols != pristine_cols:
            if current_cols > pristine_cols:
                # Columns added
                change = _detect_column_addition(
                    pristine_grid, current_grid, sheet_name, pristine_cols, current_cols
                )
            else:
                # Columns deleted
                change = _detect_column_deletion(
                    pristine_grid, current_grid, sheet_name, pristine_cols, current_cols
                )
            if change:
                result.structural_changes.append(change)

    # Now validate each structural change
    for change in result.structural_changes:
        _validate_change(
            change,
            result,
            all_formulas,
        )

    return result


def _collect_all_formulas(
    pristine_files: dict[str, str | bytes],
    current_files: dict[str, str],
    pristine_sheets: dict[str, Any],
) -> dict[str, SheetFormulas]:
    """Collect all formulas from all sheets."""
    result: dict[str, SheetFormulas] = {}

    for folder_name, sheet_info in pristine_sheets.items():
        sheet_name = sheet_info.get("title", folder_name)
        formula_path = f"{folder_name}/formula.json"

        pristine_formula_str = get_pristine_file(pristine_files, formula_path)
        current_formula_str = current_files.get(formula_path)

        pristine_formulas = (
            json.loads(pristine_formula_str) if pristine_formula_str else {}
        )
        current_formulas = (
            json.loads(current_formula_str) if current_formula_str else {}
        )

        # Expand compressed formulas
        pristine_expanded = expand_formulas(pristine_formulas)
        current_expanded = expand_formulas(current_formulas)

        # Parse all formulas
        pristine_parsed = [parse_formula(f) for f in pristine_expanded.values()]
        current_parsed = [parse_formula(f) for f in current_expanded.values()]

        result[sheet_name] = SheetFormulas(
            pristine_formulas=pristine_expanded,
            current_formulas=current_expanded,
            pristine_parsed=pristine_parsed,
            current_parsed=current_parsed,
        )

    return result


def _detect_row_addition(
    pristine_grid: list[list[str]],
    current_grid: list[list[str]],
    sheet_name: str,
) -> StructuralChange | None:
    """Detect if rows were added at end (append) or middle (insert)."""
    pristine_rows = len(pristine_grid)
    current_rows = len(current_grid)
    added_count = current_rows - pristine_rows

    if added_count <= 0:
        return None

    # Check if all pristine rows match at the start of current
    # If yes, it's an append at the end
    is_append = True
    for i in range(pristine_rows):
        if i >= len(current_grid):
            is_append = False
            break
        if pristine_grid[i] != current_grid[i]:
            is_append = False
            break

    if is_append:
        return StructuralChange(
            change_type=StructuralChangeType.APPEND_ROWS,
            sheet_name=sheet_name,
            start_index=pristine_rows,
            end_index=current_rows,
            count=added_count,
        )
    else:
        # Find where the insertion happened by finding first difference
        insert_at = 0
        for i in range(min(pristine_rows, current_rows)):
            if pristine_grid[i] != current_grid[i]:
                insert_at = i
                break

        return StructuralChange(
            change_type=StructuralChangeType.INSERT_ROWS,
            sheet_name=sheet_name,
            start_index=insert_at,
            end_index=insert_at + added_count,
            count=added_count,
        )


def _detect_row_deletion(
    pristine_grid: list[list[str]],
    current_grid: list[list[str]],
    sheet_name: str,
) -> StructuralChange | None:
    """Detect which rows were deleted."""
    pristine_rows = len(pristine_grid)
    current_rows = len(current_grid)
    deleted_count = pristine_rows - current_rows

    if deleted_count <= 0:
        return None

    # Find where deletion happened by comparing rows
    # Simple approach: find first row that differs
    delete_start = pristine_rows  # Default to end
    for i in range(min(pristine_rows, current_rows)):
        if i >= len(current_grid) or pristine_grid[i] != current_grid[i]:
            delete_start = i
            break

    return StructuralChange(
        change_type=StructuralChangeType.DELETE_ROWS,
        sheet_name=sheet_name,
        start_index=delete_start,
        end_index=delete_start + deleted_count,
        count=deleted_count,
    )


def _detect_column_addition(
    pristine_grid: list[list[str]],
    current_grid: list[list[str]],
    sheet_name: str,
    pristine_cols: int,
    current_cols: int,
) -> StructuralChange | None:
    """Detect if columns were added at end (append) or middle (insert)."""
    added_count = current_cols - pristine_cols

    if added_count <= 0:
        return None

    # Check if all existing columns match (append at end)
    is_append = True
    for row_idx in range(min(len(pristine_grid), len(current_grid))):
        pristine_row = pristine_grid[row_idx] if row_idx < len(pristine_grid) else []
        current_row = current_grid[row_idx] if row_idx < len(current_grid) else []

        for col_idx in range(min(len(pristine_row), pristine_cols)):
            pristine_val = pristine_row[col_idx] if col_idx < len(pristine_row) else ""
            current_val = current_row[col_idx] if col_idx < len(current_row) else ""
            if pristine_val != current_val:
                is_append = False
                break
        if not is_append:
            break

    if is_append:
        return StructuralChange(
            change_type=StructuralChangeType.APPEND_COLUMNS,
            sheet_name=sheet_name,
            start_index=pristine_cols,
            end_index=current_cols,
            count=added_count,
        )
    else:
        # Find insertion point
        insert_at = pristine_cols
        for row_idx in range(min(len(pristine_grid), len(current_grid))):
            pristine_row = (
                pristine_grid[row_idx] if row_idx < len(pristine_grid) else []
            )
            current_row = current_grid[row_idx] if row_idx < len(current_grid) else []

            for col_idx in range(min(len(pristine_row), len(current_row))):
                if pristine_row[col_idx] != current_row[col_idx]:
                    insert_at = min(insert_at, col_idx)
                    break

        return StructuralChange(
            change_type=StructuralChangeType.INSERT_COLUMNS,
            sheet_name=sheet_name,
            start_index=insert_at,
            end_index=insert_at + added_count,
            count=added_count,
        )


def _detect_column_deletion(
    pristine_grid: list[list[str]],
    current_grid: list[list[str]],
    sheet_name: str,
    pristine_cols: int,
    current_cols: int,
) -> StructuralChange | None:
    """Detect which columns were deleted."""
    deleted_count = pristine_cols - current_cols

    if deleted_count <= 0:
        return None

    # Find deletion point
    delete_start = pristine_cols
    for row_idx in range(min(len(pristine_grid), len(current_grid))):
        pristine_row = pristine_grid[row_idx] if row_idx < len(pristine_grid) else []
        current_row = current_grid[row_idx] if row_idx < len(current_grid) else []

        for col_idx in range(min(len(pristine_row), current_cols)):
            pristine_val = pristine_row[col_idx] if col_idx < len(pristine_row) else ""
            current_val = current_row[col_idx] if col_idx < len(current_row) else ""
            if pristine_val != current_val:
                delete_start = min(delete_start, col_idx)
                break

    return StructuralChange(
        change_type=StructuralChangeType.DELETE_COLUMNS,
        sheet_name=sheet_name,
        start_index=delete_start,
        end_index=delete_start + deleted_count,
        count=deleted_count,
    )


def _validate_change(
    change: StructuralChange,
    result: ValidationResult,
    all_formulas: dict[str, SheetFormulas],
) -> None:
    """Validate a single structural change and add blocks/warnings to result."""
    sheet_formulas = all_formulas.get(change.sheet_name)

    if change.change_type == StructuralChangeType.APPEND_ROWS:
        # Appending rows at end is always safe - nothing shifts
        pass

    elif change.change_type == StructuralChangeType.APPEND_COLUMNS:
        # Appending columns at end is always safe - nothing shifts
        pass

    elif change.change_type == StructuralChangeType.INSERT_ROWS:
        # Check for formula changes at or after insertion point
        # This would cause coordinate staleness
        if sheet_formulas and change.start_index is not None:
            _check_formula_staleness_rows(change, sheet_formulas, result, "insert")

    elif change.change_type == StructuralChangeType.INSERT_COLUMNS:
        # Check for formula changes at or after insertion point
        if sheet_formulas and change.start_index is not None:
            _check_formula_staleness_columns(change, sheet_formulas, result, "insert")

    elif change.change_type == StructuralChangeType.DELETE_ROWS:
        if change.start_index is not None and change.end_index is not None:
            # Check 1: Are deleted rows referenced by any formula? (WARN)
            _check_deleted_rows_referenced(change, all_formulas, result)

            # Check 2: Are there formula changes at or after deletion? (BLOCK)
            if sheet_formulas:
                _check_formula_staleness_rows(change, sheet_formulas, result, "delete")

    elif change.change_type == StructuralChangeType.DELETE_COLUMNS:
        if change.start_index is not None and change.end_index is not None:
            # Check 1: Are deleted columns referenced by any formula? (WARN)
            _check_deleted_columns_referenced(change, all_formulas, result)

            # Check 2: Are there formula changes at or after deletion? (BLOCK)
            if sheet_formulas:
                _check_formula_staleness_columns(
                    change, sheet_formulas, result, "delete"
                )

    elif change.change_type == StructuralChangeType.DELETE_SHEET:
        # Check if any formula on other sheets references this sheet
        _check_deleted_sheet_referenced(change, all_formulas, result)


def _check_formula_staleness_rows(
    change: StructuralChange,
    sheet_formulas: SheetFormulas,
    result: ValidationResult,
    operation: str,  # "insert" or "delete"
) -> None:
    """Check for formula changes at or after row change point.

    For INSERT: Only MODIFIED formulas (same cell in both pristine and current with
    different values) are problematic. NEW formulas are always written with post-insert
    coordinates. DELETED formulas just move, we don't write to them.

    For DELETE: We need to map pristine positions to post-delete positions.
    A formula at pristine D14 maps to D13 after deleting row 8.
    Only formulas that are MODIFIED (position matches after mapping, but content differs)
    are problematic.
    """
    if change.start_index is None:
        return

    # Find cells with formula changes
    pristine_cells = set(sheet_formulas.pristine_formulas.keys())
    current_cells = set(sheet_formulas.current_formulas.keys())

    if operation == "insert":
        # For inserts: only check MODIFIED formulas (exist in both with different values)
        # at positions that would shift. New formulas use post-insert coordinates.
        # Deleted formulas just move, we don't write anything.
        changed_cells: set[str] = set()
        for cell in pristine_cells & current_cells:
            if (
                sheet_formulas.pristine_formulas[cell]
                != sheet_formulas.current_formulas[cell]
            ):
                changed_cells.add(cell)
    else:
        # For deletes: map pristine positions to post-delete positions
        # Then compare against current to find true modifications
        delete_start = change.start_index
        delete_count = change.count

        def map_pristine_row(row: int) -> int | None:
            """Map pristine row to post-delete position, or None if deleted."""
            if delete_start <= row < delete_start + delete_count:
                return None  # Row was deleted
            if row >= delete_start + delete_count:
                return row - delete_count  # Shift up
            return row  # Before delete point, unchanged

        def map_cell_ref(cell_ref: str) -> str | None:
            """Map a cell reference from pristine to post-delete position."""
            try:
                row, col = a1_to_cell(cell_ref)
                new_row = map_pristine_row(row)
                if new_row is None:
                    return None
                return cell_to_a1(new_row, col)
            except ValueError:
                return None

        # Map pristine cells to post-delete positions
        mapped_pristine: dict[str, str] = {}
        for cell_ref, formula in sheet_formulas.pristine_formulas.items():
            mapped_ref = map_cell_ref(cell_ref)
            if mapped_ref is not None:
                mapped_pristine[mapped_ref] = formula

        # Find truly changed cells (exist in both with different content)
        changed_cells = set()
        mapped_pristine_cells = set(mapped_pristine.keys())

        for cell in mapped_pristine_cells & current_cells:
            if mapped_pristine[cell] != sheet_formulas.current_formulas[cell]:
                changed_cells.add(cell)

        # Also check for new formulas at shifted positions (not in mapped pristine)
        # These are truly new formulas that might target wrong cells
        for cell in current_cells - mapped_pristine_cells:
            try:
                row, _col = a1_to_cell(cell)
                # Only problematic if at or after delete point (in post-delete coords)
                if row >= delete_start:
                    changed_cells.add(cell)
            except ValueError:
                continue

    # Check if any changed formula is at or after the structural change point
    for cell_ref in changed_cells:
        try:
            row, _col = a1_to_cell(cell_ref)
            if row >= change.start_index:
                result.blocks.append(
                    f"Cannot {operation} rows at row {change.start_index + 1} on sheet '{change.sheet_name}' "
                    f"while also modifying formula at {cell_ref}. "
                    f"After the {operation}, cell coordinates will shift, causing the formula edit to target the wrong cell. "
                    f"Push the structural change first, then pull and edit formulas."
                )
                return  # One block is enough
        except ValueError:
            continue


def _check_formula_staleness_columns(
    change: StructuralChange,
    sheet_formulas: SheetFormulas,
    result: ValidationResult,
    operation: str,  # "insert" or "delete"
) -> None:
    """Check for formula changes at or after column change point.

    For INSERT: Only MODIFIED formulas (same cell in both pristine and current with
    different values) are problematic. NEW formulas are always written with post-insert
    coordinates. DELETED formulas just move, we don't write to them.

    For DELETE: We need to map pristine positions to post-delete positions.
    A formula at pristine E14 maps to D14 after deleting column D.
    Only formulas that are MODIFIED (position matches after mapping, but content differs)
    are problematic.
    """
    if change.start_index is None:
        return

    pristine_cells = set(sheet_formulas.pristine_formulas.keys())
    current_cells = set(sheet_formulas.current_formulas.keys())

    if operation == "insert":
        # For inserts: only check MODIFIED formulas (exist in both with different values)
        # at positions that would shift. New formulas use post-insert coordinates.
        # Deleted formulas just move, we don't write anything.
        changed_cells: set[str] = set()
        for cell in pristine_cells & current_cells:
            if (
                sheet_formulas.pristine_formulas[cell]
                != sheet_formulas.current_formulas[cell]
            ):
                changed_cells.add(cell)
    else:
        # For deletes: map pristine positions to post-delete positions
        delete_start = change.start_index
        delete_count = change.count

        def map_pristine_col(col: int) -> int | None:
            """Map pristine column to post-delete position, or None if deleted."""
            if delete_start <= col < delete_start + delete_count:
                return None  # Column was deleted
            if col >= delete_start + delete_count:
                return col - delete_count  # Shift left
            return col  # Before delete point, unchanged

        def map_cell_ref(cell_ref: str) -> str | None:
            """Map a cell reference from pristine to post-delete position."""
            try:
                row, col = a1_to_cell(cell_ref)
                new_col = map_pristine_col(col)
                if new_col is None:
                    return None
                return cell_to_a1(row, new_col)
            except ValueError:
                return None

        # Map pristine cells to post-delete positions
        mapped_pristine: dict[str, str] = {}
        for cell_ref, formula in sheet_formulas.pristine_formulas.items():
            mapped_ref = map_cell_ref(cell_ref)
            if mapped_ref is not None:
                mapped_pristine[mapped_ref] = formula

        # Find truly changed cells (exist in both with different content)
        changed_cells = set()
        mapped_pristine_cells = set(mapped_pristine.keys())

        for cell in mapped_pristine_cells & current_cells:
            if mapped_pristine[cell] != sheet_formulas.current_formulas[cell]:
                changed_cells.add(cell)

        # Also check for new formulas at shifted positions (not in mapped pristine)
        for cell in current_cells - mapped_pristine_cells:
            try:
                _row, col = a1_to_cell(cell)
                if col >= delete_start:
                    changed_cells.add(cell)
            except ValueError:
                continue

    for cell_ref in changed_cells:
        try:
            _row, col = a1_to_cell(cell_ref)
            if col >= change.start_index:
                result.blocks.append(
                    f"Cannot {operation} columns at column {change.start_index + 1} on sheet '{change.sheet_name}' "
                    f"while also modifying formula at {cell_ref}. "
                    f"After the {operation}, cell coordinates will shift, causing the formula edit to target the wrong cell. "
                    f"Push the structural change first, then pull and edit formulas."
                )
                return
        except ValueError:
            continue


def _check_deleted_rows_referenced(
    change: StructuralChange,
    all_formulas: dict[str, SheetFormulas],
    result: ValidationResult,
) -> None:
    """Check if any deleted rows are referenced by formulas.

    This is a WARN because it will cause visible #REF! errors.
    """
    if change.start_index is None or change.end_index is None:
        return

    deleted_rows = set(range(change.start_index, change.end_index))

    for sheet_name, sheet_formulas in all_formulas.items():
        for parsed in sheet_formulas.pristine_parsed:
            for ref in parsed.references:
                # Check if this ref is on the same sheet or cross-sheet
                if ref.sheet_name is not None and ref.sheet_name != change.sheet_name:
                    continue
                if ref.sheet_name is None and sheet_name != change.sheet_name:
                    continue

                # Check if any deleted row is in this reference
                for row in deleted_rows:
                    if ref.contains_row(row):
                        result.warnings.append(
                            f"Deleting row {row + 1} on sheet '{change.sheet_name}' will break formula "
                            f"'{ref.original_text}' on sheet '{sheet_name}'. "
                            f"The affected cell will show #REF! error."
                        )
                        return  # One warning is enough per change


def _check_deleted_columns_referenced(
    change: StructuralChange,
    all_formulas: dict[str, SheetFormulas],
    result: ValidationResult,
) -> None:
    """Check if any deleted columns are referenced by formulas."""
    if change.start_index is None or change.end_index is None:
        return

    deleted_cols = set(range(change.start_index, change.end_index))

    for sheet_name, sheet_formulas in all_formulas.items():
        for parsed in sheet_formulas.pristine_parsed:
            for ref in parsed.references:
                if ref.sheet_name is not None and ref.sheet_name != change.sheet_name:
                    continue
                if ref.sheet_name is None and sheet_name != change.sheet_name:
                    continue

                for col in deleted_cols:
                    if ref.contains_column(col):
                        col_letter = column_index_to_letter(col)
                        result.warnings.append(
                            f"Deleting column {col_letter} on sheet '{change.sheet_name}' will break formula "
                            f"'{ref.original_text}' on sheet '{sheet_name}'. "
                            f"The affected cell will show #REF! error."
                        )
                        return


def _check_deleted_sheet_referenced(
    change: StructuralChange,
    all_formulas: dict[str, SheetFormulas],
    result: ValidationResult,
) -> None:
    """Check if the deleted sheet is referenced by any formula on other sheets."""
    deleted_sheet = change.sheet_name

    for sheet_name, sheet_formulas in all_formulas.items():
        if sheet_name == deleted_sheet:
            continue  # Skip formulas on the sheet being deleted

        for parsed in sheet_formulas.pristine_parsed:
            if parsed.references_sheet(deleted_sheet):
                result.warnings.append(
                    f"Deleting sheet '{deleted_sheet}' will break formulas on sheet '{sheet_name}' "
                    f"that reference it. The affected cells will show #REF! error."
                )
                return


def has_formula_changes(folder: Path, sheet_name: str) -> bool:
    """Check if a sheet has any formula changes between pristine and current.

    Useful for checking if it's safe to sort (no formula changes = safe).
    """
    pristine_files = extract_pristine(folder)
    current_files = read_current_files(folder)

    # Find folder name from sheet name
    pristine_meta_str = get_pristine_file(pristine_files, "spreadsheet.json")
    if not pristine_meta_str:
        return False

    pristine_meta = json.loads(pristine_meta_str)

    folder_name = None
    for sheet in pristine_meta.get("sheets", []):
        if sheet.get("title") == sheet_name:
            folder_name = sheet.get("folder")
            break

    if not folder_name:
        return False

    formula_path = f"{folder_name}/formula.json"
    pristine_formula_str = get_pristine_file(pristine_files, formula_path)
    current_formula_str = current_files.get(formula_path)

    pristine_formulas = json.loads(pristine_formula_str) if pristine_formula_str else {}
    current_formulas = json.loads(current_formula_str) if current_formula_str else {}

    return pristine_formulas != current_formulas
