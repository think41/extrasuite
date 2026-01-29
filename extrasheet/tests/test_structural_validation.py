"""Tests for structural change validation."""

import json
import zipfile
from pathlib import Path
from typing import Any

from extrasheet.structural_validation import (
    StructuralChangeType,
    ValidationResult,
    validate_structural_changes,
)


def create_test_folder(
    tmp_path: Path,
    pristine_sheets: list[dict[str, Any]],
    current_sheets: list[dict[str, Any]],
    pristine_data: dict[str, str],
    current_data: dict[str, str],
    pristine_formulas: dict[str, dict[str, str]] | None = None,
    current_formulas: dict[str, dict[str, str]] | None = None,
) -> Path:
    """Create a test folder with pristine and current files.

    Args:
        tmp_path: pytest tmp_path fixture
        pristine_sheets: List of sheet metadata for pristine state
        current_sheets: List of sheet metadata for current state
        pristine_data: Dict of folder_name -> TSV content for pristine
        current_data: Dict of folder_name -> TSV content for current
        pristine_formulas: Dict of folder_name -> {cell: formula} for pristine
        current_formulas: Dict of folder_name -> {cell: formula} for current
    """
    folder = tmp_path / "test_spreadsheet"
    folder.mkdir()

    # Create pristine spreadsheet.json
    pristine_meta = {
        "spreadsheetId": "test_id",
        "title": "Test Spreadsheet",
        "sheets": pristine_sheets,
    }

    # Create current spreadsheet.json
    current_meta = {
        "spreadsheetId": "test_id",
        "title": "Test Spreadsheet",
        "sheets": current_sheets,
    }

    # Write current spreadsheet.json
    (folder / "spreadsheet.json").write_text(json.dumps(current_meta))

    # Create current sheet folders and files
    for sheet in current_sheets:
        sheet_folder = folder / sheet["folder"]
        sheet_folder.mkdir(exist_ok=True)

        # Write data.tsv
        if sheet["folder"] in current_data:
            (sheet_folder / "data.tsv").write_text(current_data[sheet["folder"]])

        # Write formula.json
        if current_formulas and sheet["folder"] in current_formulas:
            (sheet_folder / "formula.json").write_text(
                json.dumps(current_formulas[sheet["folder"]])
            )
        else:
            (sheet_folder / "formula.json").write_text("{}")

    # Create .pristine/spreadsheet.zip
    pristine_dir = folder / ".pristine"
    pristine_dir.mkdir()

    with zipfile.ZipFile(pristine_dir / "spreadsheet.zip", "w") as zf:
        # Add spreadsheet.json
        zf.writestr("spreadsheet.json", json.dumps(pristine_meta))

        # Add sheet files
        for sheet in pristine_sheets:
            if sheet["folder"] in pristine_data:
                zf.writestr(
                    f"{sheet['folder']}/data.tsv", pristine_data[sheet["folder"]]
                )
            if pristine_formulas and sheet["folder"] in pristine_formulas:
                zf.writestr(
                    f"{sheet['folder']}/formula.json",
                    json.dumps(pristine_formulas[sheet["folder"]]),
                )
            else:
                zf.writestr(f"{sheet['folder']}/formula.json", "{}")

    return folder


class TestAppendRows:
    """Tests for appending rows at the end (always safe)."""

    def test_append_rows_detected(self, tmp_path: Path) -> None:
        """Appending rows should be detected as APPEND_ROWS."""
        pristine_sheets = [{"folder": "Sheet1", "title": "Sheet1", "sheetId": 0}]
        current_sheets = [{"folder": "Sheet1", "title": "Sheet1", "sheetId": 0}]

        # 3 rows -> 5 rows (2 appended)
        pristine_data = {"Sheet1": "A\tB\n1\t2\n3\t4"}
        current_data = {"Sheet1": "A\tB\n1\t2\n3\t4\n5\t6\n7\t8"}

        folder = create_test_folder(
            tmp_path, pristine_sheets, current_sheets, pristine_data, current_data
        )

        result = validate_structural_changes(folder)

        assert len(result.structural_changes) == 1
        change = result.structural_changes[0]
        assert change.change_type == StructuralChangeType.APPEND_ROWS
        assert change.count == 2
        assert change.start_index == 3  # Rows appended starting at index 3

    def test_append_rows_no_blocks_or_warnings(self, tmp_path: Path) -> None:
        """Appending rows should not produce blocks or warnings."""
        pristine_sheets = [{"folder": "Sheet1", "title": "Sheet1", "sheetId": 0}]
        current_sheets = [{"folder": "Sheet1", "title": "Sheet1", "sheetId": 0}]

        pristine_data = {"Sheet1": "A\tB\n1\t2\n3\t4"}
        current_data = {"Sheet1": "A\tB\n1\t2\n3\t4\n5\t6"}

        # Even with formula changes, appending rows is safe
        pristine_formulas = {"Sheet1": {"C1": "=SUM(A:A)"}}
        current_formulas = {"Sheet1": {"C1": "=SUM(A:A)", "C5": "=A5+B5"}}

        folder = create_test_folder(
            tmp_path,
            pristine_sheets,
            current_sheets,
            pristine_data,
            current_data,
            pristine_formulas,
            current_formulas,
        )

        result = validate_structural_changes(folder)

        assert result.can_push
        assert not result.has_warnings


class TestDeleteRows:
    """Tests for deleting rows."""

    def test_delete_rows_with_formula_change_blocks(self, tmp_path: Path) -> None:
        """Deleting rows while editing formulas at/after that point should BLOCK."""
        pristine_sheets = [{"folder": "Sheet1", "title": "Sheet1", "sheetId": 0}]
        current_sheets = [{"folder": "Sheet1", "title": "Sheet1", "sheetId": 0}]

        # 5 rows -> 4 rows (row 2 deleted, indices 0-4 -> 0-3)
        # We'll simulate deleting row at index 1 (row 2)
        pristine_data = {"Sheet1": "A\tB\n1\t2\nDELETE\tME\n3\t4\n5\t6"}
        current_data = {"Sheet1": "A\tB\n1\t2\n3\t4\n5\t6"}

        # Formula at row 5 (index 4) in pristine, but after delete it's at index 3
        # If we edit this formula, we're targeting the wrong cell
        pristine_formulas = {"Sheet1": {"A5": "=1+1"}}
        current_formulas = {"Sheet1": {"A5": "=2+2"}}  # Changed formula

        folder = create_test_folder(
            tmp_path,
            pristine_sheets,
            current_sheets,
            pristine_data,
            current_data,
            pristine_formulas,
            current_formulas,
        )

        result = validate_structural_changes(folder)

        assert not result.can_push
        assert len(result.blocks) >= 1
        assert "A5" in result.blocks[0]  # Should mention the problematic cell

    def test_delete_referenced_row_warns(self, tmp_path: Path) -> None:
        """Deleting a row referenced by a formula should WARN."""
        pristine_sheets = [{"folder": "Sheet1", "title": "Sheet1", "sheetId": 0}]
        current_sheets = [{"folder": "Sheet1", "title": "Sheet1", "sheetId": 0}]

        # Delete row 3 (index 2) which contains "DELETE ME"
        # Pristine: Row0=header, Row1=1,2, Row2=DELETE,ME, Row3=3,4
        # Current:  Row0=header, Row1=1,2, Row2=3,4
        pristine_data = {"Sheet1": "A\tB\n1\t2\nDELETE\tME\n3\t4"}
        current_data = {"Sheet1": "A\tB\n1\t2\n3\t4"}

        # Formula references A3 (row index 2, the row being deleted)
        pristine_formulas = {"Sheet1": {"C1": "=A3*2"}}
        current_formulas = {"Sheet1": {"C1": "=A3*2"}}  # No change to formula

        folder = create_test_folder(
            tmp_path,
            pristine_sheets,
            current_sheets,
            pristine_data,
            current_data,
            pristine_formulas,
            current_formulas,
        )

        result = validate_structural_changes(folder)

        # Can still push (just a warning), but should warn
        assert result.can_push
        assert result.has_warnings
        assert "#REF!" in result.warnings[0]


class TestDeleteSheet:
    """Tests for deleting entire sheets."""

    def test_delete_referenced_sheet_warns(self, tmp_path: Path) -> None:
        """Deleting a sheet referenced by another sheet should WARN."""
        pristine_sheets = [
            {"folder": "Sheet1", "title": "Sheet1", "sheetId": 0},
            {"folder": "DataSheet", "title": "DataSheet", "sheetId": 1},
        ]
        # DataSheet is deleted
        current_sheets = [
            {"folder": "Sheet1", "title": "Sheet1", "sheetId": 0},
        ]

        pristine_data = {
            "Sheet1": "A\n=DataSheet!A1",
            "DataSheet": "Value\n100",
        }
        current_data = {"Sheet1": "A\n=DataSheet!A1"}

        # Sheet1 references DataSheet
        pristine_formulas = {"Sheet1": {"A2": "=DataSheet!A1"}, "DataSheet": {}}
        current_formulas = {"Sheet1": {"A2": "=DataSheet!A1"}}

        folder = create_test_folder(
            tmp_path,
            pristine_sheets,
            current_sheets,
            pristine_data,
            current_data,
            pristine_formulas,
            current_formulas,
        )

        result = validate_structural_changes(folder)

        assert result.can_push  # Just a warning
        assert result.has_warnings
        assert "DataSheet" in result.warnings[0]
        assert "Sheet1" in result.warnings[0]

    def test_delete_unreferenced_sheet_no_warning(self, tmp_path: Path) -> None:
        """Deleting a sheet not referenced anywhere should produce no warning."""
        pristine_sheets = [
            {"folder": "Sheet1", "title": "Sheet1", "sheetId": 0},
            {"folder": "UnusedSheet", "title": "UnusedSheet", "sheetId": 1},
        ]
        current_sheets = [
            {"folder": "Sheet1", "title": "Sheet1", "sheetId": 0},
        ]

        pristine_data = {
            "Sheet1": "A\n1",
            "UnusedSheet": "X\n2",
        }
        current_data = {"Sheet1": "A\n1"}

        folder = create_test_folder(
            tmp_path, pristine_sheets, current_sheets, pristine_data, current_data
        )

        result = validate_structural_changes(folder)

        assert result.can_push
        assert not result.has_warnings
        assert len(result.structural_changes) == 1
        assert (
            result.structural_changes[0].change_type
            == StructuralChangeType.DELETE_SHEET
        )


class TestInsertRows:
    """Tests for inserting rows in the middle."""

    def test_insert_rows_with_formula_change_blocks(self, tmp_path: Path) -> None:
        """Inserting rows while editing formulas at/after that point should BLOCK."""
        pristine_sheets = [{"folder": "Sheet1", "title": "Sheet1", "sheetId": 0}]
        current_sheets = [{"folder": "Sheet1", "title": "Sheet1", "sheetId": 0}]

        # Insert row in the middle (after row 1)
        pristine_data = {"Sheet1": "A\n1\n2"}
        current_data = {"Sheet1": "A\n1\nNEW\n2"}  # NEW inserted between 1 and 2

        # Formula at A3 changes - but is this the OLD A3 or NEW A3?
        pristine_formulas = {"Sheet1": {"A3": "=1+1"}}
        current_formulas = {"Sheet1": {"A3": "=2+2"}}

        folder = create_test_folder(
            tmp_path,
            pristine_sheets,
            current_sheets,
            pristine_data,
            current_data,
            pristine_formulas,
            current_formulas,
        )

        result = validate_structural_changes(folder)

        assert not result.can_push
        assert len(result.blocks) >= 1


class TestAppendColumns:
    """Tests for appending columns at the end."""

    def test_append_columns_no_blocks(self, tmp_path: Path) -> None:
        """Appending columns should not produce blocks."""
        pristine_sheets = [{"folder": "Sheet1", "title": "Sheet1", "sheetId": 0}]
        current_sheets = [{"folder": "Sheet1", "title": "Sheet1", "sheetId": 0}]

        # 2 columns -> 3 columns
        pristine_data = {"Sheet1": "A\tB\n1\t2"}
        current_data = {"Sheet1": "A\tB\tC\n1\t2\t3"}

        folder = create_test_folder(
            tmp_path, pristine_sheets, current_sheets, pristine_data, current_data
        )

        result = validate_structural_changes(folder)

        assert result.can_push
        assert not result.has_warnings
        assert len(result.structural_changes) == 1
        assert (
            result.structural_changes[0].change_type
            == StructuralChangeType.APPEND_COLUMNS
        )


class TestValidationResult:
    """Tests for ValidationResult properties."""

    def test_can_push_with_no_blocks(self) -> None:
        result = ValidationResult()
        assert result.can_push

        result.warnings.append("Some warning")
        assert result.can_push  # Warnings don't block

    def test_can_push_false_with_blocks(self) -> None:
        result = ValidationResult()
        result.blocks.append("Some error")
        assert not result.can_push

    def test_has_warnings(self) -> None:
        result = ValidationResult()
        assert not result.has_warnings

        result.warnings.append("Warning")
        assert result.has_warnings


class TestNoChanges:
    """Tests for when there are no structural changes."""

    def test_no_dimension_changes(self, tmp_path: Path) -> None:
        """No structural changes when dimensions are the same."""
        pristine_sheets = [{"folder": "Sheet1", "title": "Sheet1", "sheetId": 0}]
        current_sheets = [{"folder": "Sheet1", "title": "Sheet1", "sheetId": 0}]

        # Same dimensions, just value changes
        pristine_data = {"Sheet1": "A\tB\n1\t2\n3\t4"}
        current_data = {"Sheet1": "A\tB\n1\t2\n5\t6"}  # Changed values

        folder = create_test_folder(
            tmp_path, pristine_sheets, current_sheets, pristine_data, current_data
        )

        result = validate_structural_changes(folder)

        assert result.can_push
        assert not result.has_warnings
        assert not result.has_structural_changes
