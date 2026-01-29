"""Tests for the diff engine."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path  # noqa: TC003 - used at runtime

import pytest

from extrasheet.diff import (
    diff,
    parse_range,
    range_to_indices,
)
from extrasheet.exceptions import MissingPristineError


def create_pristine_zip(folder: Path, pristine_files: dict[str, str]) -> None:
    """Create a .pristine/spreadsheet.zip from file dict."""
    pristine_dir = folder / ".pristine"
    pristine_dir.mkdir(parents=True, exist_ok=True)
    zip_path = pristine_dir / "spreadsheet.zip"

    with zipfile.ZipFile(zip_path, "w") as zf:
        for name, content in pristine_files.items():
            zf.writestr(name, content)


def write_current_files(folder: Path, files: dict[str, str]) -> None:
    """Write files to the folder."""
    for name, content in files.items():
        file_path = folder / name
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)


class TestDiffBasic:
    """Basic diff functionality tests."""

    def test_no_changes(self, tmp_path: Path) -> None:
        """Test diff when no changes exist."""
        spreadsheet_json = json.dumps(
            {
                "spreadsheetId": "test123",
                "title": "Test",
                "sheets": [{"sheetId": 0, "title": "Sheet1", "folder": "Sheet1"}],
            }
        )
        data_tsv = "A\tB\n1\t2\n"

        pristine_files = {
            "spreadsheet.json": spreadsheet_json,
            "Sheet1/data.tsv": data_tsv,
        }

        create_pristine_zip(tmp_path, pristine_files)
        write_current_files(tmp_path, pristine_files)

        result = diff(tmp_path)

        assert result.spreadsheet_id == "test123"
        assert not result.has_changes()

    def test_cell_value_modified(self, tmp_path: Path) -> None:
        """Test diff detects modified cell values."""
        spreadsheet_json = json.dumps(
            {
                "spreadsheetId": "test123",
                "title": "Test",
                "sheets": [{"sheetId": 0, "title": "Sheet1", "folder": "Sheet1"}],
            }
        )

        pristine_files = {
            "spreadsheet.json": spreadsheet_json,
            "Sheet1/data.tsv": "Name\tAge\nAlice\t30\n",
        }

        current_files = {
            "spreadsheet.json": spreadsheet_json,
            "Sheet1/data.tsv": "Name\tAge\nAlicia\t30\n",
        }

        create_pristine_zip(tmp_path, pristine_files)
        write_current_files(tmp_path, current_files)

        result = diff(tmp_path)

        assert result.has_changes()
        assert len(result.sheet_diffs) == 1

        sheet_diff = result.sheet_diffs[0]
        assert len(sheet_diff.cell_changes) == 1

        change = sheet_diff.cell_changes[0]
        assert change.cell_ref == "A2"
        assert change.change_type == "modified"
        assert change.old_value == "Alice"
        assert change.new_value == "Alicia"

    def test_cell_value_added(self, tmp_path: Path) -> None:
        """Test diff detects added cell values."""
        spreadsheet_json = json.dumps(
            {
                "spreadsheetId": "test123",
                "title": "Test",
                "sheets": [{"sheetId": 0, "title": "Sheet1", "folder": "Sheet1"}],
            }
        )

        pristine_files = {
            "spreadsheet.json": spreadsheet_json,
            "Sheet1/data.tsv": "A\tB\n1\t\n",
        }

        current_files = {
            "spreadsheet.json": spreadsheet_json,
            "Sheet1/data.tsv": "A\tB\n1\t2\n",
        }

        create_pristine_zip(tmp_path, pristine_files)
        write_current_files(tmp_path, current_files)

        result = diff(tmp_path)

        assert result.has_changes()
        change = result.sheet_diffs[0].cell_changes[0]
        assert change.cell_ref == "B2"
        assert change.change_type == "added"
        assert change.new_value == "2"

    def test_cell_value_deleted(self, tmp_path: Path) -> None:
        """Test diff detects deleted cell values."""
        spreadsheet_json = json.dumps(
            {
                "spreadsheetId": "test123",
                "title": "Test",
                "sheets": [{"sheetId": 0, "title": "Sheet1", "folder": "Sheet1"}],
            }
        )

        pristine_files = {
            "spreadsheet.json": spreadsheet_json,
            "Sheet1/data.tsv": "A\tB\n1\t2\n",
        }

        current_files = {
            "spreadsheet.json": spreadsheet_json,
            "Sheet1/data.tsv": "A\tB\n1\t\n",
        }

        create_pristine_zip(tmp_path, pristine_files)
        write_current_files(tmp_path, current_files)

        result = diff(tmp_path)

        assert result.has_changes()
        change = result.sheet_diffs[0].cell_changes[0]
        assert change.cell_ref == "B2"
        assert change.change_type == "deleted"
        assert change.old_value == "2"


class TestDiffFormulas:
    """Tests for formula diff handling."""

    def test_formula_added(self, tmp_path: Path) -> None:
        """Test diff detects new formulas."""
        spreadsheet_json = json.dumps(
            {
                "spreadsheetId": "test123",
                "title": "Test",
                "sheets": [{"sheetId": 0, "title": "Sheet1", "folder": "Sheet1"}],
            }
        )

        pristine_files = {
            "spreadsheet.json": spreadsheet_json,
            "Sheet1/data.tsv": "A\tB\n1\t2\n",
            "Sheet1/formula.json": "{}",
        }

        current_files = {
            "spreadsheet.json": spreadsheet_json,
            "Sheet1/data.tsv": "A\tB\n1\t2\n",
            "Sheet1/formula.json": json.dumps({"B1": "=SUM(A:A)"}),
        }

        create_pristine_zip(tmp_path, pristine_files)
        write_current_files(tmp_path, current_files)

        result = diff(tmp_path)

        assert result.has_changes()
        formula_changes = result.sheet_diffs[0].formula_changes
        assert len(formula_changes) == 1
        assert formula_changes[0].range_key == "B1"
        assert formula_changes[0].change_type == "added"
        assert formula_changes[0].new_formula == "=SUM(A:A)"

    def test_formula_range_added(self, tmp_path: Path) -> None:
        """Test diff detects new formula ranges."""
        spreadsheet_json = json.dumps(
            {
                "spreadsheetId": "test123",
                "title": "Test",
                "sheets": [{"sheetId": 0, "title": "Sheet1", "folder": "Sheet1"}],
            }
        )

        pristine_files = {
            "spreadsheet.json": spreadsheet_json,
            "Sheet1/data.tsv": "A\tB\tC\n1\t2\t3\n4\t5\t9\n",
            "Sheet1/formula.json": "{}",
        }

        current_files = {
            "spreadsheet.json": spreadsheet_json,
            "Sheet1/data.tsv": "A\tB\tC\n1\t2\t3\n4\t5\t9\n",
            "Sheet1/formula.json": json.dumps({"C1:C2": "=A1+B1"}),
        }

        create_pristine_zip(tmp_path, pristine_files)
        write_current_files(tmp_path, current_files)

        result = diff(tmp_path)

        assert result.has_changes()
        formula_changes = result.sheet_diffs[0].formula_changes
        assert len(formula_changes) == 1
        assert formula_changes[0].range_key == "C1:C2"
        assert formula_changes[0].is_range is True
        assert formula_changes[0].new_formula == "=A1+B1"


class TestDiffGridDimensions:
    """Tests for grid dimension change detection."""

    def test_row_count_increased_detected(self, tmp_path: Path) -> None:
        """Test that adding rows is detected as a grid change."""
        spreadsheet_json = json.dumps(
            {
                "spreadsheetId": "test123",
                "title": "Test",
                "sheets": [{"sheetId": 0, "title": "Sheet1", "folder": "Sheet1"}],
            }
        )

        pristine_files = {
            "spreadsheet.json": spreadsheet_json,
            "Sheet1/data.tsv": "A\tB\n1\t2\n",  # 2 rows
        }

        current_files = {
            "spreadsheet.json": spreadsheet_json,
            "Sheet1/data.tsv": "A\tB\n1\t2\n3\t4\n",  # 3 rows
        }

        create_pristine_zip(tmp_path, pristine_files)
        write_current_files(tmp_path, current_files)

        result = diff(tmp_path)

        assert len(result.sheet_diffs) == 1
        grid_changes = result.sheet_diffs[0].grid_changes
        assert len(grid_changes) == 1
        assert grid_changes[0].change_type == "insert_rows"
        assert grid_changes[0].count == 1

    def test_column_count_increased_detected(self, tmp_path: Path) -> None:
        """Test that adding columns is detected as a grid change."""
        spreadsheet_json = json.dumps(
            {
                "spreadsheetId": "test123",
                "title": "Test",
                "sheets": [{"sheetId": 0, "title": "Sheet1", "folder": "Sheet1"}],
            }
        )

        pristine_files = {
            "spreadsheet.json": spreadsheet_json,
            "Sheet1/data.tsv": "A\tB\n1\t2\n",  # 2 columns
        }

        current_files = {
            "spreadsheet.json": spreadsheet_json,
            "Sheet1/data.tsv": "A\tB\tC\n1\t2\t3\n",  # 3 columns
        }

        create_pristine_zip(tmp_path, pristine_files)
        write_current_files(tmp_path, current_files)

        result = diff(tmp_path)

        assert len(result.sheet_diffs) == 1
        grid_changes = result.sheet_diffs[0].grid_changes
        assert len(grid_changes) == 1
        assert grid_changes[0].change_type == "insert_columns"
        assert grid_changes[0].count == 1

    def test_row_count_decreased_detected(self, tmp_path: Path) -> None:
        """Test that deleting rows is detected as a grid change."""
        spreadsheet_json = json.dumps(
            {
                "spreadsheetId": "test123",
                "title": "Test",
                "sheets": [{"sheetId": 0, "title": "Sheet1", "folder": "Sheet1"}],
            }
        )

        pristine_files = {
            "spreadsheet.json": spreadsheet_json,
            "Sheet1/data.tsv": "A\tB\n1\t2\n3\t4\n",  # 3 rows
        }

        current_files = {
            "spreadsheet.json": spreadsheet_json,
            "Sheet1/data.tsv": "A\tB\n1\t2\n",  # 2 rows
        }

        create_pristine_zip(tmp_path, pristine_files)
        write_current_files(tmp_path, current_files)

        result = diff(tmp_path)

        assert len(result.sheet_diffs) == 1
        grid_changes = result.sheet_diffs[0].grid_changes
        assert len(grid_changes) == 1
        assert grid_changes[0].change_type == "delete_rows"
        assert grid_changes[0].count == 1


class TestMissingPristine:
    """Tests for missing pristine handling."""

    def test_missing_pristine_raises_error(self, tmp_path: Path) -> None:
        """Test that missing pristine raises MissingPristineError."""
        spreadsheet_json = json.dumps(
            {"spreadsheetId": "test123", "title": "Test", "sheets": []}
        )

        write_current_files(tmp_path, {"spreadsheet.json": spreadsheet_json})

        with pytest.raises(MissingPristineError):
            diff(tmp_path)


class TestRangeHelpers:
    """Tests for range helper functions."""

    def test_parse_range_single_cell(self) -> None:
        """Test parsing a single cell reference."""
        start, end = parse_range("A1")
        assert start == "A1"
        assert end == "A1"

    def test_parse_range_multi_cell(self) -> None:
        """Test parsing a multi-cell range."""
        start, end = parse_range("C2:C100")
        assert start == "C2"
        assert end == "C100"

    def test_range_to_indices(self) -> None:
        """Test converting range to row/col indices."""
        start_row, start_col, end_row, end_col = range_to_indices("C2:D5")
        assert start_row == 1  # 0-indexed
        assert start_col == 2  # C = 2
        assert end_row == 4  # row 5 = index 4
        assert end_col == 3  # D = 3


class TestDiffCharts:
    """Tests for chart diff functionality."""

    def test_chart_added(self, tmp_path: Path) -> None:
        """Test detecting added chart."""
        spreadsheet_json = json.dumps(
            {
                "spreadsheetId": "test123",
                "title": "Test",
                "sheets": [{"sheetId": 0, "title": "Sheet1", "folder": "Sheet1"}],
            }
        )
        data_tsv = "A\tB\n1\t2\n"
        feature_pristine = json.dumps({})
        feature_current = json.dumps(
            {
                "charts": [
                    {
                        "chartId": 123456,
                        "spec": {"title": "New Chart"},
                        "position": {},
                    }
                ]
            }
        )

        create_pristine_zip(
            tmp_path,
            {
                "spreadsheet.json": spreadsheet_json,
                "Sheet1/data.tsv": data_tsv,
                "Sheet1/feature.json": feature_pristine,
            },
        )
        write_current_files(
            tmp_path,
            {
                "spreadsheet.json": spreadsheet_json,
                "Sheet1/data.tsv": data_tsv,
                "Sheet1/feature.json": feature_current,
            },
        )

        result = diff(tmp_path)

        assert len(result.sheet_diffs) == 1
        sheet_diff = result.sheet_diffs[0]
        assert len(sheet_diff.chart_changes) == 1
        assert sheet_diff.chart_changes[0].change_type == "added"
        assert sheet_diff.chart_changes[0].chart_id == 123456
        assert sheet_diff.chart_changes[0].new_chart["spec"]["title"] == "New Chart"

    def test_chart_deleted(self, tmp_path: Path) -> None:
        """Test detecting deleted chart."""
        spreadsheet_json = json.dumps(
            {
                "spreadsheetId": "test123",
                "title": "Test",
                "sheets": [{"sheetId": 0, "title": "Sheet1", "folder": "Sheet1"}],
            }
        )
        data_tsv = "A\tB\n1\t2\n"
        feature_pristine = json.dumps(
            {
                "charts": [
                    {
                        "chartId": 789012,
                        "spec": {"title": "Old Chart"},
                        "position": {},
                    }
                ]
            }
        )
        feature_current = json.dumps({})

        create_pristine_zip(
            tmp_path,
            {
                "spreadsheet.json": spreadsheet_json,
                "Sheet1/data.tsv": data_tsv,
                "Sheet1/feature.json": feature_pristine,
            },
        )
        write_current_files(
            tmp_path,
            {
                "spreadsheet.json": spreadsheet_json,
                "Sheet1/data.tsv": data_tsv,
                "Sheet1/feature.json": feature_current,
            },
        )

        result = diff(tmp_path)

        assert len(result.sheet_diffs) == 1
        sheet_diff = result.sheet_diffs[0]
        assert len(sheet_diff.chart_changes) == 1
        assert sheet_diff.chart_changes[0].change_type == "deleted"
        assert sheet_diff.chart_changes[0].chart_id == 789012

    def test_chart_modified(self, tmp_path: Path) -> None:
        """Test detecting modified chart."""
        spreadsheet_json = json.dumps(
            {
                "spreadsheetId": "test123",
                "title": "Test",
                "sheets": [{"sheetId": 0, "title": "Sheet1", "folder": "Sheet1"}],
            }
        )
        data_tsv = "A\tB\n1\t2\n"
        feature_pristine = json.dumps(
            {
                "charts": [
                    {
                        "chartId": 555666,
                        "spec": {"title": "Old Title"},
                        "position": {},
                    }
                ]
            }
        )
        feature_current = json.dumps(
            {
                "charts": [
                    {
                        "chartId": 555666,
                        "spec": {"title": "New Title"},
                        "position": {},
                    }
                ]
            }
        )

        create_pristine_zip(
            tmp_path,
            {
                "spreadsheet.json": spreadsheet_json,
                "Sheet1/data.tsv": data_tsv,
                "Sheet1/feature.json": feature_pristine,
            },
        )
        write_current_files(
            tmp_path,
            {
                "spreadsheet.json": spreadsheet_json,
                "Sheet1/data.tsv": data_tsv,
                "Sheet1/feature.json": feature_current,
            },
        )

        result = diff(tmp_path)

        assert len(result.sheet_diffs) == 1
        sheet_diff = result.sheet_diffs[0]
        assert len(sheet_diff.chart_changes) == 1
        assert sheet_diff.chart_changes[0].change_type == "modified"
        assert sheet_diff.chart_changes[0].chart_id == 555666
        assert sheet_diff.chart_changes[0].new_chart["spec"]["title"] == "New Title"

    def test_chart_no_change(self, tmp_path: Path) -> None:
        """Test no chart change detected when charts are identical."""
        spreadsheet_json = json.dumps(
            {
                "spreadsheetId": "test123",
                "title": "Test",
                "sheets": [{"sheetId": 0, "title": "Sheet1", "folder": "Sheet1"}],
            }
        )
        data_tsv = "A\tB\n1\t2\n"
        feature_json = json.dumps(
            {
                "charts": [
                    {
                        "chartId": 111222,
                        "spec": {"title": "Same Chart"},
                        "position": {},
                    }
                ]
            }
        )

        create_pristine_zip(
            tmp_path,
            {
                "spreadsheet.json": spreadsheet_json,
                "Sheet1/data.tsv": data_tsv,
                "Sheet1/feature.json": feature_json,
            },
        )
        write_current_files(
            tmp_path,
            {
                "spreadsheet.json": spreadsheet_json,
                "Sheet1/data.tsv": data_tsv,
                "Sheet1/feature.json": feature_json,
            },
        )

        result = diff(tmp_path)

        assert len(result.sheet_diffs) == 1
        sheet_diff = result.sheet_diffs[0]
        assert len(sheet_diff.chart_changes) == 0
