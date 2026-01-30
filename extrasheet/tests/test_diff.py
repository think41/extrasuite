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


class TestDiffNewSheets:
    """Tests for new sheet detection."""

    def test_new_sheet_gets_unique_sheetid(self, tmp_path: Path) -> None:
        """Test that new sheets get sheetIds that don't conflict with existing sheets.

        Regression test for bug where new sheets were assigned sheetId starting at
        1000000, which could conflict with existing sheets.
        """
        # Pristine has one sheet with sheetId 1000000
        pristine_spreadsheet_json = json.dumps(
            {
                "spreadsheetId": "test123",
                "title": "Test",
                "sheets": [{"sheetId": 1000000, "title": "Fruits", "folder": "Fruits"}],
            }
        )

        # Current adds a new sheet
        current_spreadsheet_json = json.dumps(
            {
                "spreadsheetId": "test123",
                "title": "Test",
                "sheets": [
                    {"sheetId": 1000000, "title": "Fruits", "folder": "Fruits"},
                    {"sheetId": 999999, "title": "NewSheet", "folder": "NewSheet"},
                ],
            }
        )

        data_tsv = "A\tB\n1\t2\n"

        create_pristine_zip(
            tmp_path,
            {
                "spreadsheet.json": pristine_spreadsheet_json,
                "Fruits/data.tsv": data_tsv,
            },
        )
        write_current_files(
            tmp_path,
            {
                "spreadsheet.json": current_spreadsheet_json,
                "Fruits/data.tsv": data_tsv,
                "NewSheet/data.tsv": data_tsv,
            },
        )

        result = diff(tmp_path)

        # Should have one new sheet change
        assert len(result.new_sheet_changes) == 1
        new_sheet = result.new_sheet_changes[0]
        assert new_sheet.sheet_name == "NewSheet"

        # The assigned sheetId should NOT be 1000000 (which is used by Fruits)
        assigned_id = new_sheet.properties["sheetId"]
        assert assigned_id != 1000000, (
            f"New sheet got sheetId {assigned_id} which conflicts with existing sheet"
        )
        # Should be max(existing) + 1 = 1000001
        assert assigned_id == 1000001

    def test_new_sheet_sheetid_increments_for_multiple_new_sheets(
        self, tmp_path: Path
    ) -> None:
        """Test that multiple new sheets get incrementing unique sheetIds."""
        pristine_spreadsheet_json = json.dumps(
            {
                "spreadsheetId": "test123",
                "title": "Test",
                "sheets": [{"sheetId": 500, "title": "Sheet1", "folder": "Sheet1"}],
            }
        )

        current_spreadsheet_json = json.dumps(
            {
                "spreadsheetId": "test123",
                "title": "Test",
                "sheets": [
                    {"sheetId": 500, "title": "Sheet1", "folder": "Sheet1"},
                    {"sheetId": 0, "title": "NewA", "folder": "NewA"},
                    {"sheetId": 0, "title": "NewB", "folder": "NewB"},
                ],
            }
        )

        data_tsv = "A\tB\n1\t2\n"

        create_pristine_zip(
            tmp_path,
            {
                "spreadsheet.json": pristine_spreadsheet_json,
                "Sheet1/data.tsv": data_tsv,
            },
        )
        write_current_files(
            tmp_path,
            {
                "spreadsheet.json": current_spreadsheet_json,
                "Sheet1/data.tsv": data_tsv,
                "NewA/data.tsv": data_tsv,
                "NewB/data.tsv": data_tsv,
            },
        )

        result = diff(tmp_path)

        # Should have two new sheet changes
        assert len(result.new_sheet_changes) == 2

        # Extract assigned IDs
        assigned_ids = [
            change.properties["sheetId"] for change in result.new_sheet_changes
        ]

        # Both IDs should be > 500 (max existing)
        assert all(id > 500 for id in assigned_ids)
        # IDs should be unique
        assert len(set(assigned_ids)) == 2
        # Should be 501 and 502
        assert sorted(assigned_ids) == [501, 502]


class TestDiffPivotTables:
    """Tests for pivot table diff functionality."""

    def test_pivot_table_added(self, tmp_path: Path) -> None:
        """Test detecting added pivot table."""
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
                "pivotTables": [
                    {
                        "anchorCell": "G1",
                        "source": {
                            "startRowIndex": 0,
                            "endRowIndex": 100,
                            "startColumnIndex": 0,
                            "endColumnIndex": 5,
                        },
                        "rows": [{"sourceColumnOffset": 0}],
                        "values": [{"sourceColumnOffset": 1}],
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
        assert len(sheet_diff.pivot_table_changes) == 1
        assert sheet_diff.pivot_table_changes[0].change_type == "added"
        assert sheet_diff.pivot_table_changes[0].anchor_cell == "G1"
        assert sheet_diff.pivot_table_changes[0].new_pivot is not None
        assert "rows" in sheet_diff.pivot_table_changes[0].new_pivot

    def test_pivot_table_deleted(self, tmp_path: Path) -> None:
        """Test detecting deleted pivot table."""
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
                "pivotTables": [
                    {
                        "anchorCell": "H5",
                        "source": {"startRowIndex": 0, "endRowIndex": 50},
                        "rows": [{"sourceColumnOffset": 0}],
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
        assert len(sheet_diff.pivot_table_changes) == 1
        assert sheet_diff.pivot_table_changes[0].change_type == "deleted"
        assert sheet_diff.pivot_table_changes[0].anchor_cell == "H5"

    def test_pivot_table_modified(self, tmp_path: Path) -> None:
        """Test detecting modified pivot table."""
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
                "pivotTables": [
                    {
                        "anchorCell": "G1",
                        "source": {"startRowIndex": 0, "endRowIndex": 50},
                        "rows": [{"sourceColumnOffset": 0}],
                    }
                ]
            }
        )
        feature_current = json.dumps(
            {
                "pivotTables": [
                    {
                        "anchorCell": "G1",
                        "source": {"startRowIndex": 0, "endRowIndex": 100},
                        "rows": [{"sourceColumnOffset": 0}],
                        "columns": [{"sourceColumnOffset": 1}],
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
        assert len(sheet_diff.pivot_table_changes) == 1
        assert sheet_diff.pivot_table_changes[0].change_type == "modified"
        assert sheet_diff.pivot_table_changes[0].anchor_cell == "G1"
        # Verify the change
        assert (
            sheet_diff.pivot_table_changes[0].new_pivot["source"]["endRowIndex"] == 100
        )
        assert "columns" in sheet_diff.pivot_table_changes[0].new_pivot

    def test_pivot_table_no_change(self, tmp_path: Path) -> None:
        """Test no pivot table change detected when identical."""
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
                "pivotTables": [
                    {
                        "anchorCell": "G1",
                        "source": {"startRowIndex": 0, "endRowIndex": 50},
                        "rows": [{"sourceColumnOffset": 0}],
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
        assert len(sheet_diff.pivot_table_changes) == 0


class TestDiffSplitFeatureFiles:
    """Tests for reading from split feature files (new format)."""

    def test_reads_from_pivot_tables_json(self, tmp_path: Path) -> None:
        """Test that diff reads from pivot-tables.json."""
        spreadsheet_json = json.dumps(
            {
                "spreadsheetId": "test123",
                "title": "Test",
                "sheets": [{"sheetId": 0, "title": "Sheet1", "folder": "Sheet1"}],
            }
        )
        data_tsv = "A\tB\n1\t2\n"
        pivot_pristine = json.dumps({"pivotTables": []})
        pivot_current = json.dumps(
            {
                "pivotTables": [
                    {
                        "anchorCell": "G1",
                        "source": {"startRowIndex": 0, "endRowIndex": 50},
                    }
                ]
            }
        )

        create_pristine_zip(
            tmp_path,
            {
                "spreadsheet.json": spreadsheet_json,
                "Sheet1/data.tsv": data_tsv,
                "Sheet1/pivot-tables.json": pivot_pristine,
            },
        )
        write_current_files(
            tmp_path,
            {
                "spreadsheet.json": spreadsheet_json,
                "Sheet1/data.tsv": data_tsv,
                "Sheet1/pivot-tables.json": pivot_current,
            },
        )

        result = diff(tmp_path)

        assert len(result.sheet_diffs) == 1
        sheet_diff = result.sheet_diffs[0]
        assert len(sheet_diff.pivot_table_changes) == 1
        assert sheet_diff.pivot_table_changes[0].change_type == "added"

    def test_reads_from_charts_json(self, tmp_path: Path) -> None:
        """Test that diff reads from charts.json."""
        spreadsheet_json = json.dumps(
            {
                "spreadsheetId": "test123",
                "title": "Test",
                "sheets": [{"sheetId": 0, "title": "Sheet1", "folder": "Sheet1"}],
            }
        )
        data_tsv = "A\tB\n1\t2\n"
        charts_pristine = json.dumps({"charts": []})
        charts_current = json.dumps(
            {
                "charts": [
                    {
                        "chartId": 12345,
                        "spec": {"title": "Test Chart"},
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
                "Sheet1/charts.json": charts_pristine,
            },
        )
        write_current_files(
            tmp_path,
            {
                "spreadsheet.json": spreadsheet_json,
                "Sheet1/data.tsv": data_tsv,
                "Sheet1/charts.json": charts_current,
            },
        )

        result = diff(tmp_path)

        assert len(result.sheet_diffs) == 1
        sheet_diff = result.sheet_diffs[0]
        assert len(sheet_diff.chart_changes) == 1
        assert sheet_diff.chart_changes[0].change_type == "added"

    def test_reads_from_filters_json(self, tmp_path: Path) -> None:
        """Test that diff reads from filters.json."""
        spreadsheet_json = json.dumps(
            {
                "spreadsheetId": "test123",
                "title": "Test",
                "sheets": [{"sheetId": 0, "title": "Sheet1", "folder": "Sheet1"}],
            }
        )
        data_tsv = "A\tB\n1\t2\n"
        filters_pristine = json.dumps({})
        filters_current = json.dumps(
            {"basicFilter": {"range": {"startRowIndex": 0, "endRowIndex": 50}}}
        )

        create_pristine_zip(
            tmp_path,
            {
                "spreadsheet.json": spreadsheet_json,
                "Sheet1/data.tsv": data_tsv,
                "Sheet1/filters.json": filters_pristine,
            },
        )
        write_current_files(
            tmp_path,
            {
                "spreadsheet.json": spreadsheet_json,
                "Sheet1/data.tsv": data_tsv,
                "Sheet1/filters.json": filters_current,
            },
        )

        result = diff(tmp_path)

        assert len(result.sheet_diffs) == 1
        sheet_diff = result.sheet_diffs[0]
        assert sheet_diff.basic_filter_change is not None
        assert sheet_diff.basic_filter_change.change_type == "added"

    def test_split_files_override_legacy_feature_json(self, tmp_path: Path) -> None:
        """Test that split files take precedence over legacy feature.json."""
        spreadsheet_json = json.dumps(
            {
                "spreadsheetId": "test123",
                "title": "Test",
                "sheets": [{"sheetId": 0, "title": "Sheet1", "folder": "Sheet1"}],
            }
        )
        data_tsv = "A\tB\n1\t2\n"
        # Legacy feature.json has no charts
        feature_json = json.dumps({"charts": []})
        # But charts.json has a chart - this should take precedence
        charts_json = json.dumps(
            {
                "charts": [
                    {"chartId": 999, "spec": {"title": "Override"}, "position": {}}
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
                "Sheet1/charts.json": charts_json,
            },
        )

        result = diff(tmp_path)

        assert len(result.sheet_diffs) == 1
        sheet_diff = result.sheet_diffs[0]
        assert len(sheet_diff.chart_changes) == 1
        assert sheet_diff.chart_changes[0].change_type == "added"
        assert sheet_diff.chart_changes[0].chart_id == 999


class TestDiffTables:
    """Tests for table diffing functionality."""

    def test_table_added(self, tmp_path: Path) -> None:
        """Test diff detects added tables."""
        spreadsheet_json = json.dumps(
            {
                "spreadsheetId": "test123",
                "title": "Test",
                "sheets": [{"sheetId": 0, "title": "Sheet1", "folder": "Sheet1"}],
            }
        )
        data_tsv = "Name\tValue\n1\t2\n"
        tables_pristine = json.dumps({"tables": []})
        tables_current = json.dumps(
            {
                "tables": [
                    {
                        "tableId": "table123",
                        "name": "TestTable",
                        "range": {
                            "sheetId": 0,
                            "startRowIndex": 0,
                            "endRowIndex": 10,
                            "startColumnIndex": 0,
                            "endColumnIndex": 2,
                        },
                    }
                ]
            }
        )

        create_pristine_zip(
            tmp_path,
            {
                "spreadsheet.json": spreadsheet_json,
                "Sheet1/data.tsv": data_tsv,
                "Sheet1/tables.json": tables_pristine,
            },
        )
        write_current_files(
            tmp_path,
            {
                "spreadsheet.json": spreadsheet_json,
                "Sheet1/data.tsv": data_tsv,
                "Sheet1/tables.json": tables_current,
            },
        )

        result = diff(tmp_path)

        assert len(result.sheet_diffs) == 1
        sheet_diff = result.sheet_diffs[0]
        assert len(sheet_diff.table_changes) == 1
        assert sheet_diff.table_changes[0].change_type == "added"
        assert sheet_diff.table_changes[0].table_id == "table123"
        assert sheet_diff.table_changes[0].table_name == "TestTable"

    def test_table_deleted(self, tmp_path: Path) -> None:
        """Test diff detects deleted tables."""
        spreadsheet_json = json.dumps(
            {
                "spreadsheetId": "test123",
                "title": "Test",
                "sheets": [{"sheetId": 0, "title": "Sheet1", "folder": "Sheet1"}],
            }
        )
        data_tsv = "Name\tValue\n1\t2\n"
        tables_pristine = json.dumps(
            {
                "tables": [
                    {
                        "tableId": "table123",
                        "name": "TestTable",
                        "range": {"sheetId": 0},
                    }
                ]
            }
        )
        tables_current = json.dumps({"tables": []})

        create_pristine_zip(
            tmp_path,
            {
                "spreadsheet.json": spreadsheet_json,
                "Sheet1/data.tsv": data_tsv,
                "Sheet1/tables.json": tables_pristine,
            },
        )
        write_current_files(
            tmp_path,
            {
                "spreadsheet.json": spreadsheet_json,
                "Sheet1/data.tsv": data_tsv,
                "Sheet1/tables.json": tables_current,
            },
        )

        result = diff(tmp_path)

        assert len(result.sheet_diffs) == 1
        sheet_diff = result.sheet_diffs[0]
        assert len(sheet_diff.table_changes) == 1
        assert sheet_diff.table_changes[0].change_type == "deleted"
        assert sheet_diff.table_changes[0].table_id == "table123"

    def test_table_modified(self, tmp_path: Path) -> None:
        """Test diff detects modified tables."""
        spreadsheet_json = json.dumps(
            {
                "spreadsheetId": "test123",
                "title": "Test",
                "sheets": [{"sheetId": 0, "title": "Sheet1", "folder": "Sheet1"}],
            }
        )
        data_tsv = "Name\tValue\n1\t2\n"
        tables_pristine = json.dumps(
            {
                "tables": [
                    {
                        "tableId": "table123",
                        "name": "OldName",
                        "range": {"sheetId": 0},
                    }
                ]
            }
        )
        tables_current = json.dumps(
            {
                "tables": [
                    {
                        "tableId": "table123",
                        "name": "NewName",
                        "range": {"sheetId": 0},
                    }
                ]
            }
        )

        create_pristine_zip(
            tmp_path,
            {
                "spreadsheet.json": spreadsheet_json,
                "Sheet1/data.tsv": data_tsv,
                "Sheet1/tables.json": tables_pristine,
            },
        )
        write_current_files(
            tmp_path,
            {
                "spreadsheet.json": spreadsheet_json,
                "Sheet1/data.tsv": data_tsv,
                "Sheet1/tables.json": tables_current,
            },
        )

        result = diff(tmp_path)

        assert len(result.sheet_diffs) == 1
        sheet_diff = result.sheet_diffs[0]
        assert len(sheet_diff.table_changes) == 1
        assert sheet_diff.table_changes[0].change_type == "modified"
        assert sheet_diff.table_changes[0].table_name == "NewName"


class TestDiffNamedRanges:
    """Tests for named range diffing functionality."""

    def test_named_range_added(self, tmp_path: Path) -> None:
        """Test diff detects added named ranges."""
        spreadsheet_json = json.dumps(
            {
                "spreadsheetId": "test123",
                "title": "Test",
                "sheets": [{"sheetId": 0, "title": "Sheet1", "folder": "Sheet1"}],
            }
        )
        data_tsv = "Name\tValue\n1\t2\n"
        named_ranges_pristine = json.dumps({"namedRanges": []})
        named_ranges_current = json.dumps(
            {
                "namedRanges": [
                    {
                        "namedRangeId": "range123",
                        "name": "TestRange",
                        "range": {
                            "sheetId": 0,
                            "startRowIndex": 0,
                            "endRowIndex": 10,
                            "startColumnIndex": 0,
                            "endColumnIndex": 1,
                        },
                    }
                ]
            }
        )

        create_pristine_zip(
            tmp_path,
            {
                "spreadsheet.json": spreadsheet_json,
                "Sheet1/data.tsv": data_tsv,
                "named_ranges.json": named_ranges_pristine,
            },
        )
        write_current_files(
            tmp_path,
            {
                "spreadsheet.json": spreadsheet_json,
                "Sheet1/data.tsv": data_tsv,
                "named_ranges.json": named_ranges_current,
            },
        )

        result = diff(tmp_path)

        assert len(result.named_range_changes) == 1
        assert result.named_range_changes[0].change_type == "added"
        assert result.named_range_changes[0].named_range_id == "range123"
        assert result.named_range_changes[0].name == "TestRange"

    def test_named_range_deleted(self, tmp_path: Path) -> None:
        """Test diff detects deleted named ranges."""
        spreadsheet_json = json.dumps(
            {
                "spreadsheetId": "test123",
                "title": "Test",
                "sheets": [{"sheetId": 0, "title": "Sheet1", "folder": "Sheet1"}],
            }
        )
        data_tsv = "Name\tValue\n1\t2\n"
        named_ranges_pristine = json.dumps(
            {
                "namedRanges": [
                    {
                        "namedRangeId": "range123",
                        "name": "TestRange",
                        "range": {"sheetId": 0},
                    }
                ]
            }
        )
        named_ranges_current = json.dumps({"namedRanges": []})

        create_pristine_zip(
            tmp_path,
            {
                "spreadsheet.json": spreadsheet_json,
                "Sheet1/data.tsv": data_tsv,
                "named_ranges.json": named_ranges_pristine,
            },
        )
        write_current_files(
            tmp_path,
            {
                "spreadsheet.json": spreadsheet_json,
                "Sheet1/data.tsv": data_tsv,
                "named_ranges.json": named_ranges_current,
            },
        )

        result = diff(tmp_path)

        assert len(result.named_range_changes) == 1
        assert result.named_range_changes[0].change_type == "deleted"
        assert result.named_range_changes[0].named_range_id == "range123"

    def test_named_range_modified(self, tmp_path: Path) -> None:
        """Test diff detects modified named ranges."""
        spreadsheet_json = json.dumps(
            {
                "spreadsheetId": "test123",
                "title": "Test",
                "sheets": [{"sheetId": 0, "title": "Sheet1", "folder": "Sheet1"}],
            }
        )
        data_tsv = "Name\tValue\n1\t2\n"
        named_ranges_pristine = json.dumps(
            {
                "namedRanges": [
                    {
                        "namedRangeId": "range123",
                        "name": "OldName",
                        "range": {"sheetId": 0, "startRowIndex": 0, "endRowIndex": 5},
                    }
                ]
            }
        )
        named_ranges_current = json.dumps(
            {
                "namedRanges": [
                    {
                        "namedRangeId": "range123",
                        "name": "NewName",
                        "range": {"sheetId": 0, "startRowIndex": 0, "endRowIndex": 10},
                    }
                ]
            }
        )

        create_pristine_zip(
            tmp_path,
            {
                "spreadsheet.json": spreadsheet_json,
                "Sheet1/data.tsv": data_tsv,
                "named_ranges.json": named_ranges_pristine,
            },
        )
        write_current_files(
            tmp_path,
            {
                "spreadsheet.json": spreadsheet_json,
                "Sheet1/data.tsv": data_tsv,
                "named_ranges.json": named_ranges_current,
            },
        )

        result = diff(tmp_path)

        assert len(result.named_range_changes) == 1
        assert result.named_range_changes[0].change_type == "modified"
        assert result.named_range_changes[0].name == "NewName"

    def test_no_named_ranges_file(self, tmp_path: Path) -> None:
        """Test diff works when named_ranges.json doesn't exist."""
        spreadsheet_json = json.dumps(
            {
                "spreadsheetId": "test123",
                "title": "Test",
                "sheets": [{"sheetId": 0, "title": "Sheet1", "folder": "Sheet1"}],
            }
        )
        data_tsv = "Name\tValue\n1\t2\n"

        create_pristine_zip(
            tmp_path,
            {
                "spreadsheet.json": spreadsheet_json,
                "Sheet1/data.tsv": data_tsv,
            },
        )
        write_current_files(
            tmp_path,
            {
                "spreadsheet.json": spreadsheet_json,
                "Sheet1/data.tsv": data_tsv,
            },
        )

        result = diff(tmp_path)

        # No named ranges changes when file doesn't exist
        assert len(result.named_range_changes) == 0


class TestDiffSlicers:
    """Tests for slicer diffing."""

    def test_slicer_added(self, tmp_path: Path) -> None:
        """Test diff detects added slicers."""
        spreadsheet_json = json.dumps(
            {
                "spreadsheetId": "test123",
                "title": "Test",
                "sheets": [{"sheetId": 0, "title": "Sheet1", "folder": "Sheet1"}],
            }
        )
        data_tsv = "Name\tValue\n1\t2\n"
        slicers_pristine = json.dumps({"slicers": []})
        slicers_current = json.dumps(
            {
                "slicers": [
                    {
                        "slicerId": 123,
                        "spec": {"title": "TestSlicer"},
                        "position": {"overlayPosition": {"anchorCell": {"sheetId": 0}}},
                    }
                ]
            }
        )

        create_pristine_zip(
            tmp_path,
            {
                "spreadsheet.json": spreadsheet_json,
                "Sheet1/data.tsv": data_tsv,
                "Sheet1/slicers.json": slicers_pristine,
            },
        )
        write_current_files(
            tmp_path,
            {
                "spreadsheet.json": spreadsheet_json,
                "Sheet1/data.tsv": data_tsv,
                "Sheet1/slicers.json": slicers_current,
            },
        )

        result = diff(tmp_path)

        assert len(result.sheet_diffs) == 1
        sheet_diff = result.sheet_diffs[0]
        assert len(sheet_diff.slicer_changes) == 1
        assert sheet_diff.slicer_changes[0].change_type == "added"
        assert sheet_diff.slicer_changes[0].slicer_id == 123

    def test_slicer_deleted(self, tmp_path: Path) -> None:
        """Test diff detects deleted slicers."""
        spreadsheet_json = json.dumps(
            {
                "spreadsheetId": "test123",
                "title": "Test",
                "sheets": [{"sheetId": 0, "title": "Sheet1", "folder": "Sheet1"}],
            }
        )
        data_tsv = "Name\tValue\n1\t2\n"
        slicers_pristine = json.dumps(
            {
                "slicers": [
                    {
                        "slicerId": 123,
                        "spec": {"title": "TestSlicer"},
                    }
                ]
            }
        )
        slicers_current = json.dumps({"slicers": []})

        create_pristine_zip(
            tmp_path,
            {
                "spreadsheet.json": spreadsheet_json,
                "Sheet1/data.tsv": data_tsv,
                "Sheet1/slicers.json": slicers_pristine,
            },
        )
        write_current_files(
            tmp_path,
            {
                "spreadsheet.json": spreadsheet_json,
                "Sheet1/data.tsv": data_tsv,
                "Sheet1/slicers.json": slicers_current,
            },
        )

        result = diff(tmp_path)

        assert len(result.sheet_diffs) == 1
        sheet_diff = result.sheet_diffs[0]
        assert len(sheet_diff.slicer_changes) == 1
        assert sheet_diff.slicer_changes[0].change_type == "deleted"
        assert sheet_diff.slicer_changes[0].slicer_id == 123

    def test_slicer_modified(self, tmp_path: Path) -> None:
        """Test diff detects modified slicers."""
        spreadsheet_json = json.dumps(
            {
                "spreadsheetId": "test123",
                "title": "Test",
                "sheets": [{"sheetId": 0, "title": "Sheet1", "folder": "Sheet1"}],
            }
        )
        data_tsv = "Name\tValue\n1\t2\n"
        slicers_pristine = json.dumps(
            {
                "slicers": [
                    {
                        "slicerId": 123,
                        "spec": {"title": "OldTitle"},
                    }
                ]
            }
        )
        slicers_current = json.dumps(
            {
                "slicers": [
                    {
                        "slicerId": 123,
                        "spec": {"title": "NewTitle"},
                    }
                ]
            }
        )

        create_pristine_zip(
            tmp_path,
            {
                "spreadsheet.json": spreadsheet_json,
                "Sheet1/data.tsv": data_tsv,
                "Sheet1/slicers.json": slicers_pristine,
            },
        )
        write_current_files(
            tmp_path,
            {
                "spreadsheet.json": spreadsheet_json,
                "Sheet1/data.tsv": data_tsv,
                "Sheet1/slicers.json": slicers_current,
            },
        )

        result = diff(tmp_path)

        assert len(result.sheet_diffs) == 1
        sheet_diff = result.sheet_diffs[0]
        assert len(sheet_diff.slicer_changes) == 1
        assert sheet_diff.slicer_changes[0].change_type == "modified"
        assert sheet_diff.slicer_changes[0].slicer_id == 123


class TestDiffDataSourceTables:
    """Tests for data source table diffing."""

    def test_data_source_table_added(self, tmp_path: Path) -> None:
        """Test diff detects added data source tables."""
        spreadsheet_json = json.dumps(
            {
                "spreadsheetId": "test123",
                "title": "Test",
                "sheets": [{"sheetId": 0, "title": "Sheet1", "folder": "Sheet1"}],
            }
        )
        data_tsv = "Name\tValue\n1\t2\n"
        ds_tables_pristine = json.dumps({"dataSourceTables": []})
        ds_tables_current = json.dumps(
            {
                "dataSourceTables": [
                    {
                        "anchorCell": "A1",
                        "dataSourceId": "ds123",
                    }
                ]
            }
        )

        create_pristine_zip(
            tmp_path,
            {
                "spreadsheet.json": spreadsheet_json,
                "Sheet1/data.tsv": data_tsv,
                "Sheet1/data-source-tables.json": ds_tables_pristine,
            },
        )
        write_current_files(
            tmp_path,
            {
                "spreadsheet.json": spreadsheet_json,
                "Sheet1/data.tsv": data_tsv,
                "Sheet1/data-source-tables.json": ds_tables_current,
            },
        )

        result = diff(tmp_path)

        assert len(result.sheet_diffs) == 1
        sheet_diff = result.sheet_diffs[0]
        assert len(sheet_diff.data_source_table_changes) == 1
        assert sheet_diff.data_source_table_changes[0].change_type == "added"
        assert sheet_diff.data_source_table_changes[0].anchor_cell == "A1"

    def test_data_source_table_deleted(self, tmp_path: Path) -> None:
        """Test diff detects deleted data source tables."""
        spreadsheet_json = json.dumps(
            {
                "spreadsheetId": "test123",
                "title": "Test",
                "sheets": [{"sheetId": 0, "title": "Sheet1", "folder": "Sheet1"}],
            }
        )
        data_tsv = "Name\tValue\n1\t2\n"
        ds_tables_pristine = json.dumps(
            {
                "dataSourceTables": [
                    {
                        "anchorCell": "A1",
                        "dataSourceId": "ds123",
                    }
                ]
            }
        )
        ds_tables_current = json.dumps({"dataSourceTables": []})

        create_pristine_zip(
            tmp_path,
            {
                "spreadsheet.json": spreadsheet_json,
                "Sheet1/data.tsv": data_tsv,
                "Sheet1/data-source-tables.json": ds_tables_pristine,
            },
        )
        write_current_files(
            tmp_path,
            {
                "spreadsheet.json": spreadsheet_json,
                "Sheet1/data.tsv": data_tsv,
                "Sheet1/data-source-tables.json": ds_tables_current,
            },
        )

        result = diff(tmp_path)

        assert len(result.sheet_diffs) == 1
        sheet_diff = result.sheet_diffs[0]
        assert len(sheet_diff.data_source_table_changes) == 1
        assert sheet_diff.data_source_table_changes[0].change_type == "deleted"

    def test_data_source_table_modified(self, tmp_path: Path) -> None:
        """Test diff detects modified data source tables."""
        spreadsheet_json = json.dumps(
            {
                "spreadsheetId": "test123",
                "title": "Test",
                "sheets": [{"sheetId": 0, "title": "Sheet1", "folder": "Sheet1"}],
            }
        )
        data_tsv = "Name\tValue\n1\t2\n"
        ds_tables_pristine = json.dumps(
            {
                "dataSourceTables": [
                    {
                        "anchorCell": "A1",
                        "dataSourceId": "ds123",
                        "columns": ["col1"],
                    }
                ]
            }
        )
        ds_tables_current = json.dumps(
            {
                "dataSourceTables": [
                    {
                        "anchorCell": "A1",
                        "dataSourceId": "ds123",
                        "columns": ["col1", "col2"],
                    }
                ]
            }
        )

        create_pristine_zip(
            tmp_path,
            {
                "spreadsheet.json": spreadsheet_json,
                "Sheet1/data.tsv": data_tsv,
                "Sheet1/data-source-tables.json": ds_tables_pristine,
            },
        )
        write_current_files(
            tmp_path,
            {
                "spreadsheet.json": spreadsheet_json,
                "Sheet1/data.tsv": data_tsv,
                "Sheet1/data-source-tables.json": ds_tables_current,
            },
        )

        result = diff(tmp_path)

        assert len(result.sheet_diffs) == 1
        sheet_diff = result.sheet_diffs[0]
        assert len(sheet_diff.data_source_table_changes) == 1
        assert sheet_diff.data_source_table_changes[0].change_type == "modified"
