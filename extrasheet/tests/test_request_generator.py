"""Tests for the request generator."""

from __future__ import annotations

from extrasheet.diff import (
    BandedRangeChange,
    BasicFilterChange,
    CellChange,
    ChartChange,
    ConditionalFormatChange,
    DataSourceTableChange,
    DataValidationChange,
    DiffResult,
    DimensionChange,
    FilterViewChange,
    FormatRuleChange,
    FormulaChange,
    MergeChange,
    NamedRangeChange,
    NoteChange,
    PivotTableChange,
    SheetDiff,
    SheetPropertyChange,
    SlicerChange,
    SpreadsheetPropertyChange,
    TableChange,
    TextFormatRunChange,
)
from extrasheet.request_generator import (
    _infer_value_type,
    generate_requests,
)


class TestInferValueType:
    """Tests for value type inference."""

    def test_empty_value(self) -> None:
        """Test empty value returns empty dict."""
        assert _infer_value_type("") == {}
        assert _infer_value_type(None) == {}

    def test_boolean_true(self) -> None:
        """Test TRUE is recognized as boolean."""
        assert _infer_value_type("TRUE") == {"boolValue": True}
        assert _infer_value_type("true") == {"boolValue": True}
        assert _infer_value_type("True") == {"boolValue": True}

    def test_boolean_false(self) -> None:
        """Test FALSE is recognized as boolean."""
        assert _infer_value_type("FALSE") == {"boolValue": False}
        assert _infer_value_type("false") == {"boolValue": False}

    def test_integer(self) -> None:
        """Test integer values."""
        assert _infer_value_type("42") == {"numberValue": 42}
        assert _infer_value_type("0") == {"numberValue": 0}
        assert _infer_value_type("-10") == {"numberValue": -10}

    def test_float(self) -> None:
        """Test float values."""
        assert _infer_value_type("3.14") == {"numberValue": 3.14}
        assert _infer_value_type("-0.5") == {"numberValue": -0.5}

    def test_number_with_commas(self) -> None:
        """Test numbers with commas are parsed correctly."""
        assert _infer_value_type("1,234") == {"numberValue": 1234}
        assert _infer_value_type("1,234.56") == {"numberValue": 1234.56}

    def test_string(self) -> None:
        """Test string values."""
        assert _infer_value_type("Hello") == {"stringValue": "Hello"}
        assert _infer_value_type("Alice") == {"stringValue": "Alice"}


class TestGenerateCellRequests:
    """Tests for cell value request generation."""

    def test_single_cell_change(self) -> None:
        """Test generating request for a single cell change."""
        diff_result = DiffResult(
            spreadsheet_id="test123",
            sheet_diffs=[
                SheetDiff(
                    sheet_id=0,
                    sheet_name="Sheet1",
                    folder_name="Sheet1",
                    cell_changes=[
                        CellChange(
                            row=1,
                            col=0,
                            cell_ref="A2",
                            change_type="modified",
                            old_value="Alice",
                            new_value="Alicia",
                        )
                    ],
                )
            ],
        )

        requests = generate_requests(diff_result)

        assert len(requests) == 1
        req = requests[0]
        assert "updateCells" in req
        assert req["updateCells"]["start"]["rowIndex"] == 1
        assert req["updateCells"]["start"]["columnIndex"] == 0
        assert req["updateCells"]["rows"][0]["values"][0] == {
            "userEnteredValue": {"stringValue": "Alicia"}
        }

    def test_multiple_cell_changes_same_row_contiguous(self) -> None:
        """Test generating request for contiguous cells in same row."""
        diff_result = DiffResult(
            spreadsheet_id="test123",
            sheet_diffs=[
                SheetDiff(
                    sheet_id=0,
                    sheet_name="Sheet1",
                    folder_name="Sheet1",
                    cell_changes=[
                        CellChange(
                            row=0,
                            col=0,
                            cell_ref="A1",
                            change_type="modified",
                            old_value="1",
                            new_value="10",
                        ),
                        CellChange(
                            row=0,
                            col=1,
                            cell_ref="B1",
                            change_type="modified",
                            old_value="2",
                            new_value="20",
                        ),
                    ],
                )
            ],
        )

        requests = generate_requests(diff_result)

        # Contiguous changes should be batched into one request
        assert len(requests) == 1
        req = requests[0]["updateCells"]
        assert req["start"]["columnIndex"] == 0
        assert len(req["rows"][0]["values"]) == 2

    def test_non_contiguous_cell_changes_same_row(self) -> None:
        """Test that non-contiguous changes generate separate requests."""
        diff_result = DiffResult(
            spreadsheet_id="test123",
            sheet_diffs=[
                SheetDiff(
                    sheet_id=0,
                    sheet_name="Sheet1",
                    folder_name="Sheet1",
                    cell_changes=[
                        CellChange(
                            row=0,
                            col=0,
                            cell_ref="A1",
                            change_type="modified",
                            old_value="1",
                            new_value="10",
                        ),
                        CellChange(
                            row=0,
                            col=3,  # Gap - skip B1 and C1
                            cell_ref="D1",
                            change_type="modified",
                            old_value="4",
                            new_value="40",
                        ),
                    ],
                )
            ],
        )

        requests = generate_requests(diff_result)

        # Non-contiguous changes should generate separate requests
        assert len(requests) == 2
        # First request for A1
        req1 = requests[0]["updateCells"]
        assert req1["start"]["columnIndex"] == 0
        assert len(req1["rows"][0]["values"]) == 1
        # Second request for D1
        req2 = requests[1]["updateCells"]
        assert req2["start"]["columnIndex"] == 3
        assert len(req2["rows"][0]["values"]) == 1


class TestGenerateFormulaRequests:
    """Tests for formula request generation."""

    def test_single_cell_formula(self) -> None:
        """Test generating request for a single cell formula."""
        diff_result = DiffResult(
            spreadsheet_id="test123",
            sheet_diffs=[
                SheetDiff(
                    sheet_id=0,
                    sheet_name="Sheet1",
                    folder_name="Sheet1",
                    formula_changes=[
                        FormulaChange(
                            range_key="C1",
                            change_type="added",
                            old_formula=None,
                            new_formula="=SUM(A1:B1)",
                            is_range=False,
                        )
                    ],
                )
            ],
        )

        requests = generate_requests(diff_result)

        assert len(requests) == 1
        req = requests[0]
        assert "updateCells" in req
        assert req["updateCells"]["rows"][0]["values"][0] == {
            "userEnteredValue": {"formulaValue": "=SUM(A1:B1)"}
        }

    def test_formula_range_generates_autofill(self) -> None:
        """Test formula range generates updateCells + autoFill."""
        diff_result = DiffResult(
            spreadsheet_id="test123",
            sheet_diffs=[
                SheetDiff(
                    sheet_id=0,
                    sheet_name="Sheet1",
                    folder_name="Sheet1",
                    formula_changes=[
                        FormulaChange(
                            range_key="C1:C5",
                            change_type="added",
                            old_formula=None,
                            new_formula="=A1+B1",
                            is_range=True,
                        )
                    ],
                )
            ],
        )

        requests = generate_requests(diff_result)

        # Should have updateCells + autoFill
        assert len(requests) == 2
        assert "updateCells" in requests[0]
        assert "autoFill" in requests[1]

        # Check updateCells
        update = requests[0]["updateCells"]
        assert update["start"]["rowIndex"] == 0
        assert update["start"]["columnIndex"] == 2

        # Check autoFill
        autofill = requests[1]["autoFill"]
        source_dest = autofill["sourceAndDestination"]
        source = source_dest["source"]

        assert source["startRowIndex"] == 0
        assert source["endRowIndex"] == 1  # Just first row
        assert source["startColumnIndex"] == 2
        assert source["endColumnIndex"] == 3  # Just first column

        # Check dimension and fillLength (correct API format)
        assert source_dest["dimension"] == "ROWS"
        assert source_dest["fillLength"] == 4  # C1 to C5 = 4 additional rows


class TestGeneratePropertyRequests:
    """Tests for property change request generation."""

    def test_spreadsheet_title_change(self) -> None:
        """Test generating request for spreadsheet title change."""
        diff_result = DiffResult(
            spreadsheet_id="test123",
            spreadsheet_changes=[
                SpreadsheetPropertyChange(
                    property_name="title",
                    old_value="Old Title",
                    new_value="New Title",
                )
            ],
        )

        requests = generate_requests(diff_result)

        assert len(requests) == 1
        req = requests[0]
        assert "updateSpreadsheetProperties" in req
        assert req["updateSpreadsheetProperties"]["properties"]["title"] == "New Title"

    def test_sheet_property_change(self) -> None:
        """Test generating request for sheet property change."""
        diff_result = DiffResult(
            spreadsheet_id="test123",
            sheet_property_changes=[
                SheetPropertyChange(
                    sheet_id=0,
                    sheet_name="Sheet1",
                    property_name="title",
                    old_value="Sheet1",
                    new_value="Data",
                )
            ],
        )

        requests = generate_requests(diff_result)

        assert len(requests) == 1
        req = requests[0]
        assert "updateSheetProperties" in req
        props = req["updateSheetProperties"]["properties"]
        assert props["sheetId"] == 0
        assert props["title"] == "Data"


class TestNoChanges:
    """Tests for handling no changes."""

    def test_empty_diff_generates_no_requests(self) -> None:
        """Test that empty diff generates no requests."""
        diff_result = DiffResult(spreadsheet_id="test123")

        requests = generate_requests(diff_result)

        assert requests == []

    def test_deleted_formula_generates_clear_request(self) -> None:
        """Test that deleted formulas generate clear (empty) requests."""
        diff_result = DiffResult(
            spreadsheet_id="test123",
            sheet_diffs=[
                SheetDiff(
                    sheet_id=0,
                    sheet_name="Sheet1",
                    folder_name="Sheet1",
                    formula_changes=[
                        FormulaChange(
                            range_key="C1",
                            change_type="deleted",
                            old_formula="=SUM(A1:B1)",
                            new_formula=None,
                            is_range=False,
                        )
                    ],
                )
            ],
        )

        requests = generate_requests(diff_result)

        # Deleted formulas generate updateCells to clear the cell
        assert len(requests) == 1
        assert "updateCells" in requests[0]
        update = requests[0]["updateCells"]
        assert update["start"]["rowIndex"] == 0
        assert update["start"]["columnIndex"] == 2
        assert update["rows"][0]["values"][0]["userEnteredValue"] == {}

    def test_deleted_formula_range_generates_clear_request(self) -> None:
        """Test that deleted formula ranges generate clear requests for all cells."""
        diff_result = DiffResult(
            spreadsheet_id="test123",
            sheet_diffs=[
                SheetDiff(
                    sheet_id=0,
                    sheet_name="Sheet1",
                    folder_name="Sheet1",
                    formula_changes=[
                        FormulaChange(
                            range_key="C1:C3",
                            change_type="deleted",
                            old_formula="=A1+B1",
                            new_formula=None,
                            is_range=True,
                        )
                    ],
                )
            ],
        )

        requests = generate_requests(diff_result)

        # Should have one updateCells request clearing all 3 cells
        assert len(requests) == 1
        assert "updateCells" in requests[0]
        update = requests[0]["updateCells"]
        assert update["start"]["rowIndex"] == 0
        assert update["start"]["columnIndex"] == 2
        # 3 rows, each with empty value
        assert len(update["rows"]) == 3
        for row in update["rows"]:
            assert row["values"][0]["userEnteredValue"] == {}


class TestGenerateFormatRuleRequests:
    """Tests for format rule request generation."""

    def test_format_rule_added_with_background_color(self) -> None:
        """Test generating repeatCell for background color format."""

        diff_result = DiffResult(
            spreadsheet_id="test123",
            sheet_diffs=[
                SheetDiff(
                    sheet_id=0,
                    sheet_name="Sheet1",
                    folder_name="Sheet1",
                    format_rule_changes=[
                        FormatRuleChange(
                            range_key="A1:B5",
                            change_type="added",
                            old_format=None,
                            new_format={"backgroundColor": "#FF0000"},
                        )
                    ],
                )
            ],
        )

        requests = generate_requests(diff_result)

        assert len(requests) == 1
        req = requests[0]
        assert "repeatCell" in req

        repeat = req["repeatCell"]
        assert repeat["range"]["startRowIndex"] == 0
        assert repeat["range"]["endRowIndex"] == 5
        assert repeat["range"]["startColumnIndex"] == 0
        assert repeat["range"]["endColumnIndex"] == 2

        # Check RGB conversion
        bg = repeat["cell"]["userEnteredFormat"]["backgroundColor"]
        assert bg["red"] == 1.0
        assert bg["green"] == 0.0
        assert bg["blue"] == 0.0

    def test_format_rule_modified(self) -> None:
        """Test generating repeatCell for modified format."""

        diff_result = DiffResult(
            spreadsheet_id="test123",
            sheet_diffs=[
                SheetDiff(
                    sheet_id=0,
                    sheet_name="Sheet1",
                    folder_name="Sheet1",
                    format_rule_changes=[
                        FormatRuleChange(
                            range_key="C1",
                            change_type="modified",
                            old_format={"backgroundColor": "#FF0000"},
                            new_format={"backgroundColor": "#00FF00"},
                        )
                    ],
                )
            ],
        )

        requests = generate_requests(diff_result)

        assert len(requests) == 1
        bg = requests[0]["repeatCell"]["cell"]["userEnteredFormat"]["backgroundColor"]
        assert bg["green"] == 1.0


class TestGenerateDimensionRequests:
    """Tests for dimension change request generation."""

    def test_column_width_changed(self) -> None:
        """Test generating updateDimensionProperties for column width."""

        diff_result = DiffResult(
            spreadsheet_id="test123",
            sheet_diffs=[
                SheetDiff(
                    sheet_id=0,
                    sheet_name="Sheet1",
                    folder_name="Sheet1",
                    dimension_changes=[
                        DimensionChange(
                            dimension_type="COLUMNS",
                            index=2,
                            change_type="modified",
                            old_size=100,
                            new_size=200,
                        )
                    ],
                )
            ],
        )

        requests = generate_requests(diff_result)

        assert len(requests) == 1
        req = requests[0]
        assert "updateDimensionProperties" in req

        props = req["updateDimensionProperties"]
        assert props["range"]["dimension"] == "COLUMNS"
        assert props["range"]["startIndex"] == 2
        assert props["range"]["endIndex"] == 3
        assert props["properties"]["pixelSize"] == 200

    def test_row_height_added(self) -> None:
        """Test generating updateDimensionProperties for new row height."""

        diff_result = DiffResult(
            spreadsheet_id="test123",
            sheet_diffs=[
                SheetDiff(
                    sheet_id=0,
                    sheet_name="Sheet1",
                    folder_name="Sheet1",
                    dimension_changes=[
                        DimensionChange(
                            dimension_type="ROWS",
                            index=5,
                            change_type="added",
                            old_size=None,
                            new_size=50,
                        )
                    ],
                )
            ],
        )

        requests = generate_requests(diff_result)

        assert len(requests) == 1
        props = requests[0]["updateDimensionProperties"]
        assert props["range"]["dimension"] == "ROWS"
        assert props["range"]["startIndex"] == 5
        assert props["properties"]["pixelSize"] == 50


class TestGenerateDataValidationRequests:
    """Tests for data validation request generation."""

    def test_data_validation_added(self) -> None:
        """Test generating setDataValidation for new validation rule."""
        diff_result = DiffResult(
            spreadsheet_id="test123",
            sheet_diffs=[
                SheetDiff(
                    sheet_id=0,
                    sheet_name="Sheet1",
                    folder_name="Sheet1",
                    data_validation_changes=[
                        DataValidationChange(
                            range_key="H2... (3 cells)",
                            cells=["H2", "H3", "H4"],
                            change_type="added",
                            old_rule=None,
                            new_rule={
                                "condition": {
                                    "type": "ONE_OF_LIST",
                                    "values": [
                                        {"userEnteredValue": "Yes"},
                                        {"userEnteredValue": "No"},
                                    ],
                                },
                                "showCustomUi": True,
                            },
                        )
                    ],
                )
            ],
        )

        requests = generate_requests(diff_result)

        # Should have 1 request (cells are contiguous)
        assert len(requests) == 1
        req = requests[0]
        assert "setDataValidation" in req

        validation = req["setDataValidation"]
        assert validation["range"]["startRowIndex"] == 1  # H2 is row 1
        assert validation["range"]["endRowIndex"] == 4  # H4 + 1
        assert validation["range"]["startColumnIndex"] == 7  # H is column 7
        assert validation["rule"]["condition"]["type"] == "ONE_OF_LIST"

    def test_data_validation_deleted(self) -> None:
        """Test generating setDataValidation to clear validation."""
        diff_result = DiffResult(
            spreadsheet_id="test123",
            sheet_diffs=[
                SheetDiff(
                    sheet_id=0,
                    sheet_name="Sheet1",
                    folder_name="Sheet1",
                    data_validation_changes=[
                        DataValidationChange(
                            range_key="A1... (2 cells)",
                            cells=["A1", "A2"],
                            change_type="deleted",
                            old_rule={"condition": {"type": "ONE_OF_LIST"}},
                            new_rule=None,
                        )
                    ],
                )
            ],
        )

        requests = generate_requests(diff_result)

        assert len(requests) == 1
        req = requests[0]
        assert "setDataValidation" in req
        # Deleted validation should not have a 'rule' key
        assert "rule" not in req["setDataValidation"]

    def test_data_validation_groups_contiguous_cells(self) -> None:
        """Test that non-contiguous cells create multiple requests."""
        diff_result = DiffResult(
            spreadsheet_id="test123",
            sheet_diffs=[
                SheetDiff(
                    sheet_id=0,
                    sheet_name="Sheet1",
                    folder_name="Sheet1",
                    data_validation_changes=[
                        DataValidationChange(
                            range_key="test",
                            cells=["A1", "A2", "A5", "A6"],  # Gap at A3, A4
                            change_type="added",
                            old_rule=None,
                            new_rule={"condition": {"type": "BOOLEAN"}},
                        )
                    ],
                )
            ],
        )

        requests = generate_requests(diff_result)

        # Should have 2 requests: A1:A2 and A5:A6
        assert len(requests) == 2
        ranges = [r["setDataValidation"]["range"] for r in requests]

        # First range: A1:A2
        assert ranges[0]["startRowIndex"] == 0
        assert ranges[0]["endRowIndex"] == 2

        # Second range: A5:A6
        assert ranges[1]["startRowIndex"] == 4
        assert ranges[1]["endRowIndex"] == 6


class TestGenerateTextFormatRunRequests:
    """Tests for text format run (rich text) request generation."""

    def test_text_format_run_added(self) -> None:
        """Test generating updateCells for added text format runs."""
        diff_result = DiffResult(
            spreadsheet_id="test123",
            sheet_diffs=[
                SheetDiff(
                    sheet_id=0,
                    sheet_name="Sheet1",
                    folder_name="Sheet1",
                    text_format_run_changes=[
                        TextFormatRunChange(
                            cell_ref="E5",
                            change_type="added",
                            old_runs=None,
                            new_runs=[
                                {"format": {}},
                                {
                                    "startIndex": 5,
                                    "format": {
                                        "bold": True,
                                        "foregroundColor": {
                                            "red": 1,
                                            "green": 0,
                                            "blue": 0,
                                        },
                                    },
                                },
                            ],
                        )
                    ],
                )
            ],
        )

        requests = generate_requests(diff_result)

        assert len(requests) == 1
        req = requests[0]
        assert "updateCells" in req

        update = req["updateCells"]
        assert update["fields"] == "textFormatRuns"
        assert update["start"]["rowIndex"] == 4  # E5 is row 4
        assert update["start"]["columnIndex"] == 4  # E is column 4
        assert len(update["rows"][0]["values"][0]["textFormatRuns"]) == 2

    def test_text_format_run_deleted(self) -> None:
        """Test generating updateCells to clear text format runs."""
        diff_result = DiffResult(
            spreadsheet_id="test123",
            sheet_diffs=[
                SheetDiff(
                    sheet_id=0,
                    sheet_name="Sheet1",
                    folder_name="Sheet1",
                    text_format_run_changes=[
                        TextFormatRunChange(
                            cell_ref="A1",
                            change_type="deleted",
                            old_runs=[
                                {"format": {}},
                                {"startIndex": 3, "format": {"bold": True}},
                            ],
                            new_runs=None,
                        )
                    ],
                )
            ],
        )

        requests = generate_requests(diff_result)

        assert len(requests) == 1
        req = requests[0]
        assert "updateCells" in req

        update = req["updateCells"]
        assert update["fields"] == "textFormatRuns"
        # Deleted should have empty textFormatRuns array
        assert update["rows"][0]["values"][0]["textFormatRuns"] == []

    def test_text_format_run_modified(self) -> None:
        """Test generating updateCells for modified text format runs."""
        diff_result = DiffResult(
            spreadsheet_id="test123",
            sheet_diffs=[
                SheetDiff(
                    sheet_id=0,
                    sheet_name="Sheet1",
                    folder_name="Sheet1",
                    text_format_run_changes=[
                        TextFormatRunChange(
                            cell_ref="B2",
                            change_type="modified",
                            old_runs=[
                                {"format": {}},
                                {"startIndex": 5, "format": {"italic": True}},
                            ],
                            new_runs=[
                                {"format": {}},
                                {
                                    "startIndex": 5,
                                    "format": {"bold": True, "underline": True},
                                },
                            ],
                        )
                    ],
                )
            ],
        )

        requests = generate_requests(diff_result)

        assert len(requests) == 1
        req = requests[0]
        assert "updateCells" in req

        update = req["updateCells"]
        assert update["start"]["rowIndex"] == 1  # B2 is row 1
        assert update["start"]["columnIndex"] == 1  # B is column 1
        # Should have the new format
        runs = update["rows"][0]["values"][0]["textFormatRuns"]
        assert runs[1]["format"]["bold"] is True
        assert runs[1]["format"]["underline"] is True


class TestGenerateNoteRequests:
    """Tests for cell note request generation."""

    def test_note_added(self) -> None:
        """Test generating updateCells for added note."""
        diff_result = DiffResult(
            spreadsheet_id="test123",
            sheet_diffs=[
                SheetDiff(
                    sheet_id=0,
                    sheet_name="Sheet1",
                    folder_name="Sheet1",
                    note_changes=[
                        NoteChange(
                            cell_ref="A1",
                            change_type="added",
                            old_note=None,
                            new_note="This is a test note",
                        )
                    ],
                )
            ],
        )

        requests = generate_requests(diff_result)

        assert len(requests) == 1
        req = requests[0]
        assert "updateCells" in req

        update = req["updateCells"]
        assert update["fields"] == "note"
        assert update["start"]["rowIndex"] == 0
        assert update["start"]["columnIndex"] == 0
        assert update["rows"][0]["values"][0]["note"] == "This is a test note"

    def test_note_deleted(self) -> None:
        """Test generating updateCells to clear note."""
        diff_result = DiffResult(
            spreadsheet_id="test123",
            sheet_diffs=[
                SheetDiff(
                    sheet_id=0,
                    sheet_name="Sheet1",
                    folder_name="Sheet1",
                    note_changes=[
                        NoteChange(
                            cell_ref="B3",
                            change_type="deleted",
                            old_note="Old note content",
                            new_note=None,
                        )
                    ],
                )
            ],
        )

        requests = generate_requests(diff_result)

        assert len(requests) == 1
        req = requests[0]
        assert "updateCells" in req

        update = req["updateCells"]
        assert update["fields"] == "note"
        assert update["start"]["rowIndex"] == 2  # B3 is row 2
        assert update["start"]["columnIndex"] == 1  # B is column 1
        # Deleted note should be empty string
        assert update["rows"][0]["values"][0]["note"] == ""

    def test_note_modified(self) -> None:
        """Test generating updateCells for modified note."""
        diff_result = DiffResult(
            spreadsheet_id="test123",
            sheet_diffs=[
                SheetDiff(
                    sheet_id=0,
                    sheet_name="Sheet1",
                    folder_name="Sheet1",
                    note_changes=[
                        NoteChange(
                            cell_ref="C5",
                            change_type="modified",
                            old_note="Old note",
                            new_note="Updated note content",
                        )
                    ],
                )
            ],
        )

        requests = generate_requests(diff_result)

        assert len(requests) == 1
        req = requests[0]
        assert "updateCells" in req

        update = req["updateCells"]
        assert update["start"]["rowIndex"] == 4  # C5 is row 4
        assert update["start"]["columnIndex"] == 2  # C is column 2
        assert update["rows"][0]["values"][0]["note"] == "Updated note content"


class TestGenerateMergeRequests:
    """Tests for merge cell request generation."""

    def test_merge_added(self) -> None:
        """Test generating mergeCells for new merge."""
        diff_result = DiffResult(
            spreadsheet_id="test123",
            sheet_diffs=[
                SheetDiff(
                    sheet_id=0,
                    sheet_name="Sheet1",
                    folder_name="Sheet1",
                    merge_changes=[
                        MergeChange(
                            range_key="A1:B2",
                            change_type="added",
                            start_row=0,
                            end_row=2,
                            start_col=0,
                            end_col=2,
                        )
                    ],
                )
            ],
        )

        requests = generate_requests(diff_result)

        assert len(requests) == 1
        req = requests[0]
        assert "mergeCells" in req

        merge = req["mergeCells"]
        assert merge["mergeType"] == "MERGE_ALL"
        assert merge["range"]["startRowIndex"] == 0
        assert merge["range"]["endRowIndex"] == 2
        assert merge["range"]["startColumnIndex"] == 0
        assert merge["range"]["endColumnIndex"] == 2

    def test_merge_deleted(self) -> None:
        """Test generating unmergeCells for deleted merge."""
        diff_result = DiffResult(
            spreadsheet_id="test123",
            sheet_diffs=[
                SheetDiff(
                    sheet_id=0,
                    sheet_name="Sheet1",
                    folder_name="Sheet1",
                    merge_changes=[
                        MergeChange(
                            range_key="C3:D4",
                            change_type="deleted",
                            start_row=2,
                            end_row=4,
                            start_col=2,
                            end_col=4,
                        )
                    ],
                )
            ],
        )

        requests = generate_requests(diff_result)

        assert len(requests) == 1
        req = requests[0]
        assert "unmergeCells" in req

        unmerge = req["unmergeCells"]
        assert unmerge["range"]["startRowIndex"] == 2
        assert unmerge["range"]["endRowIndex"] == 4
        assert unmerge["range"]["startColumnIndex"] == 2
        assert unmerge["range"]["endColumnIndex"] == 4


class TestGenerateConditionalFormatRequests:
    """Tests for conditional format request generation."""

    def test_conditional_format_added(self) -> None:
        """Test generating addConditionalFormatRule."""
        diff_result = DiffResult(
            spreadsheet_id="test123",
            sheet_diffs=[
                SheetDiff(
                    sheet_id=0,
                    sheet_name="Sheet1",
                    folder_name="Sheet1",
                    conditional_format_changes=[
                        ConditionalFormatChange(
                            rule_index=0,
                            change_type="added",
                            old_rule=None,
                            new_rule={
                                "ranges": ["A1:B10"],
                                "booleanRule": {
                                    "condition": {"type": "NOT_BLANK"},
                                    "format": {"backgroundColor": {"red": 1}},
                                },
                            },
                        )
                    ],
                )
            ],
        )

        requests = generate_requests(diff_result)

        assert len(requests) == 1
        req = requests[0]
        assert "addConditionalFormatRule" in req

        add_rule = req["addConditionalFormatRule"]
        assert add_rule["index"] == 0
        assert "ranges" in add_rule["rule"]
        assert add_rule["rule"]["ranges"][0]["startRowIndex"] == 0
        assert add_rule["rule"]["ranges"][0]["endRowIndex"] == 10

    def test_conditional_format_deleted(self) -> None:
        """Test generating deleteConditionalFormatRule."""
        diff_result = DiffResult(
            spreadsheet_id="test123",
            sheet_diffs=[
                SheetDiff(
                    sheet_id=0,
                    sheet_name="Sheet1",
                    folder_name="Sheet1",
                    conditional_format_changes=[
                        ConditionalFormatChange(
                            rule_index=2,
                            change_type="deleted",
                            old_rule={"ranges": ["A1:A10"]},
                            new_rule=None,
                        )
                    ],
                )
            ],
        )

        requests = generate_requests(diff_result)

        assert len(requests) == 1
        req = requests[0]
        assert "deleteConditionalFormatRule" in req
        assert req["deleteConditionalFormatRule"]["index"] == 2

    def test_conditional_format_modified(self) -> None:
        """Test generating updateConditionalFormatRule."""
        diff_result = DiffResult(
            spreadsheet_id="test123",
            sheet_diffs=[
                SheetDiff(
                    sheet_id=0,
                    sheet_name="Sheet1",
                    folder_name="Sheet1",
                    conditional_format_changes=[
                        ConditionalFormatChange(
                            rule_index=1,
                            change_type="modified",
                            old_rule={"ranges": ["A1:A5"]},
                            new_rule={
                                "ranges": ["A1:A10"],
                                "booleanRule": {
                                    "condition": {"type": "BLANK"},
                                    "format": {"backgroundColor": {"blue": 1}},
                                },
                            },
                        )
                    ],
                )
            ],
        )

        requests = generate_requests(diff_result)

        assert len(requests) == 1
        req = requests[0]
        assert "updateConditionalFormatRule" in req
        assert req["updateConditionalFormatRule"]["index"] == 1


class TestGenerateBasicFilterRequests:
    """Tests for basic filter request generation."""

    def test_basic_filter_added(self) -> None:
        """Test generating setBasicFilter."""
        diff_result = DiffResult(
            spreadsheet_id="test123",
            sheet_diffs=[
                SheetDiff(
                    sheet_id=0,
                    sheet_name="Sheet1",
                    folder_name="Sheet1",
                    basic_filter_change=BasicFilterChange(
                        change_type="added",
                        old_filter=None,
                        new_filter={
                            "range": {
                                "startRowIndex": 0,
                                "endRowIndex": 100,
                                "startColumnIndex": 0,
                                "endColumnIndex": 10,
                            }
                        },
                    ),
                )
            ],
        )

        requests = generate_requests(diff_result)

        assert len(requests) == 1
        req = requests[0]
        assert "setBasicFilter" in req
        # sheetId should be in range, not at filter level
        assert req["setBasicFilter"]["filter"]["range"]["sheetId"] == 0

    def test_basic_filter_deleted(self) -> None:
        """Test generating clearBasicFilter."""
        diff_result = DiffResult(
            spreadsheet_id="test123",
            sheet_diffs=[
                SheetDiff(
                    sheet_id=0,
                    sheet_name="Sheet1",
                    folder_name="Sheet1",
                    basic_filter_change=BasicFilterChange(
                        change_type="deleted",
                        old_filter={"range": {}},
                        new_filter=None,
                    ),
                )
            ],
        )

        requests = generate_requests(diff_result)

        assert len(requests) == 1
        req = requests[0]
        assert "clearBasicFilter" in req
        assert req["clearBasicFilter"]["sheetId"] == 0


class TestGenerateBandedRangeRequests:
    """Tests for banded range request generation."""

    def test_banded_range_added(self) -> None:
        """Test generating addBanding."""
        diff_result = DiffResult(
            spreadsheet_id="test123",
            sheet_diffs=[
                SheetDiff(
                    sheet_id=0,
                    sheet_name="Sheet1",
                    folder_name="Sheet1",
                    banded_range_changes=[
                        BandedRangeChange(
                            banded_range_id=None,
                            change_type="added",
                            old_range=None,
                            new_range={
                                "range": {
                                    "startRowIndex": 0,
                                    "endRowIndex": 10,
                                    "startColumnIndex": 0,
                                    "endColumnIndex": 5,
                                },
                                "rowProperties": {
                                    "headerColor": {
                                        "red": 0.2,
                                        "green": 0.4,
                                        "blue": 0.3,
                                    },
                                    "firstBandColor": {"red": 1, "green": 1, "blue": 1},
                                    "secondBandColor": {
                                        "red": 0.9,
                                        "green": 0.9,
                                        "blue": 0.9,
                                    },
                                },
                            },
                        )
                    ],
                )
            ],
        )

        requests = generate_requests(diff_result)

        assert len(requests) == 1
        req = requests[0]
        assert "addBanding" in req

        banded = req["addBanding"]["bandedRange"]
        assert banded["range"]["sheetId"] == 0
        assert banded["range"]["startRowIndex"] == 0
        assert banded["range"]["endRowIndex"] == 10
        assert "rowProperties" in banded
        assert banded["rowProperties"]["headerColor"]["red"] == 0.2

    def test_banded_range_deleted(self) -> None:
        """Test generating deleteBanding."""
        diff_result = DiffResult(
            spreadsheet_id="test123",
            sheet_diffs=[
                SheetDiff(
                    sheet_id=0,
                    sheet_name="Sheet1",
                    folder_name="Sheet1",
                    banded_range_changes=[
                        BandedRangeChange(
                            banded_range_id=12345,
                            change_type="deleted",
                            old_range={
                                "bandedRangeId": 12345,
                                "range": {},
                                "rowProperties": {},
                            },
                            new_range=None,
                        )
                    ],
                )
            ],
        )

        requests = generate_requests(diff_result)

        assert len(requests) == 1
        req = requests[0]
        assert "deleteBanding" in req
        assert req["deleteBanding"]["bandedRangeId"] == 12345

    def test_banded_range_modified(self) -> None:
        """Test generating updateBanding."""
        diff_result = DiffResult(
            spreadsheet_id="test123",
            sheet_diffs=[
                SheetDiff(
                    sheet_id=0,
                    sheet_name="Sheet1",
                    folder_name="Sheet1",
                    banded_range_changes=[
                        BandedRangeChange(
                            banded_range_id=67890,
                            change_type="modified",
                            old_range={
                                "bandedRangeId": 67890,
                                "range": {},
                                "rowProperties": {
                                    "firstBandColor": {"red": 1, "green": 1, "blue": 1}
                                },
                            },
                            new_range={
                                "bandedRangeId": 67890,
                                "range": {
                                    "startRowIndex": 0,
                                    "endRowIndex": 20,
                                    "startColumnIndex": 0,
                                    "endColumnIndex": 5,
                                },
                                "rowProperties": {
                                    "firstBandColor": {
                                        "red": 0.8,
                                        "green": 0.8,
                                        "blue": 1,
                                    }
                                },
                            },
                        )
                    ],
                )
            ],
        )

        requests = generate_requests(diff_result)

        assert len(requests) == 1
        req = requests[0]
        assert "updateBanding" in req

        update = req["updateBanding"]
        assert update["bandedRange"]["bandedRangeId"] == 67890
        assert "range,rowProperties" in update["fields"] or update["fields"] in [
            "range,rowProperties",
            "rowProperties,range",
        ]


class TestGenerateFilterViewRequests:
    """Tests for filter view request generation."""

    def test_filter_view_added(self) -> None:
        """Test generating addFilterView."""
        diff_result = DiffResult(
            spreadsheet_id="test123",
            sheet_diffs=[
                SheetDiff(
                    sheet_id=0,
                    sheet_name="Sheet1",
                    folder_name="Sheet1",
                    filter_view_changes=[
                        FilterViewChange(
                            filter_view_id=None,
                            change_type="added",
                            old_view=None,
                            new_view={
                                "title": "My Filter View",
                                "range": {
                                    "startRowIndex": 0,
                                    "endRowIndex": 100,
                                    "startColumnIndex": 0,
                                    "endColumnIndex": 10,
                                },
                                "sortSpecs": [
                                    {"dimensionIndex": 0, "sortOrder": "ASCENDING"}
                                ],
                            },
                        )
                    ],
                )
            ],
        )

        requests = generate_requests(diff_result)

        assert len(requests) == 1
        req = requests[0]
        assert "addFilterView" in req

        fv = req["addFilterView"]["filter"]
        assert fv["title"] == "My Filter View"
        assert fv["range"]["sheetId"] == 0
        assert fv["range"]["startRowIndex"] == 0
        assert fv["range"]["endRowIndex"] == 100
        assert len(fv["sortSpecs"]) == 1

    def test_filter_view_deleted(self) -> None:
        """Test generating deleteFilterView."""
        diff_result = DiffResult(
            spreadsheet_id="test123",
            sheet_diffs=[
                SheetDiff(
                    sheet_id=0,
                    sheet_name="Sheet1",
                    folder_name="Sheet1",
                    filter_view_changes=[
                        FilterViewChange(
                            filter_view_id=12345,
                            change_type="deleted",
                            old_view={
                                "filterViewId": 12345,
                                "title": "Old Filter View",
                                "range": {},
                            },
                            new_view=None,
                        )
                    ],
                )
            ],
        )

        requests = generate_requests(diff_result)

        assert len(requests) == 1
        req = requests[0]
        assert "deleteFilterView" in req
        assert req["deleteFilterView"]["filterId"] == 12345

    def test_filter_view_modified(self) -> None:
        """Test generating updateFilterView."""
        diff_result = DiffResult(
            spreadsheet_id="test123",
            sheet_diffs=[
                SheetDiff(
                    sheet_id=0,
                    sheet_name="Sheet1",
                    folder_name="Sheet1",
                    filter_view_changes=[
                        FilterViewChange(
                            filter_view_id=67890,
                            change_type="modified",
                            old_view={
                                "filterViewId": 67890,
                                "title": "Old Title",
                                "range": {},
                            },
                            new_view={
                                "filterViewId": 67890,
                                "title": "New Title",
                                "range": {
                                    "startRowIndex": 0,
                                    "endRowIndex": 50,
                                    "startColumnIndex": 0,
                                    "endColumnIndex": 5,
                                },
                            },
                        )
                    ],
                )
            ],
        )

        requests = generate_requests(diff_result)

        assert len(requests) == 1
        req = requests[0]
        assert "updateFilterView" in req

        update = req["updateFilterView"]
        assert update["filter"]["filterViewId"] == 67890
        assert update["filter"]["title"] == "New Title"
        assert "title" in update["fields"]
        assert "range" in update["fields"]


class TestGenerateChartRequests:
    """Tests for chart request generation."""

    def test_chart_added(self) -> None:
        """Test generating addChart."""
        diff_result = DiffResult(
            spreadsheet_id="test123",
            sheet_diffs=[
                SheetDiff(
                    sheet_id=0,
                    sheet_name="Sheet1",
                    folder_name="Sheet1",
                    chart_changes=[
                        ChartChange(
                            chart_id=None,
                            change_type="added",
                            old_chart=None,
                            new_chart={
                                "position": {
                                    "overlayPosition": {
                                        "anchorCell": {"rowIndex": 0, "columnIndex": 5},
                                        "widthPixels": 400,
                                        "heightPixels": 300,
                                    }
                                },
                                "spec": {
                                    "title": "Sales by Region",
                                    "basicChart": {
                                        "chartType": "COLUMN",
                                        "legendPosition": "BOTTOM_LEGEND",
                                    },
                                },
                            },
                        )
                    ],
                )
            ],
        )

        requests = generate_requests(diff_result)

        assert len(requests) == 1
        req = requests[0]
        assert "addChart" in req

        chart = req["addChart"]["chart"]
        assert chart["spec"]["title"] == "Sales by Region"
        assert chart["spec"]["basicChart"]["chartType"] == "COLUMN"
        assert chart["position"]["overlayPosition"]["anchorCell"]["sheetId"] == 0
        assert chart["position"]["overlayPosition"]["widthPixels"] == 400

    def test_chart_deleted(self) -> None:
        """Test generating deleteEmbeddedObject."""
        diff_result = DiffResult(
            spreadsheet_id="test123",
            sheet_diffs=[
                SheetDiff(
                    sheet_id=0,
                    sheet_name="Sheet1",
                    folder_name="Sheet1",
                    chart_changes=[
                        ChartChange(
                            chart_id=123456,
                            change_type="deleted",
                            old_chart={
                                "chartId": 123456,
                                "spec": {"title": "Old Chart"},
                                "position": {},
                            },
                            new_chart=None,
                        )
                    ],
                )
            ],
        )

        requests = generate_requests(diff_result)

        assert len(requests) == 1
        req = requests[0]
        assert "deleteEmbeddedObject" in req
        assert req["deleteEmbeddedObject"]["objectId"] == 123456

    def test_chart_modified_spec(self) -> None:
        """Test generating updateChartSpec for spec changes."""
        diff_result = DiffResult(
            spreadsheet_id="test123",
            sheet_diffs=[
                SheetDiff(
                    sheet_id=0,
                    sheet_name="Sheet1",
                    folder_name="Sheet1",
                    chart_changes=[
                        ChartChange(
                            chart_id=789012,
                            change_type="modified",
                            old_chart={
                                "chartId": 789012,
                                "spec": {
                                    "title": "Old Title",
                                    "basicChart": {"chartType": "BAR"},
                                },
                                "position": {
                                    "overlayPosition": {
                                        "anchorCell": {"rowIndex": 0, "columnIndex": 5}
                                    }
                                },
                            },
                            new_chart={
                                "chartId": 789012,
                                "spec": {
                                    "title": "New Title",
                                    "basicChart": {"chartType": "COLUMN"},
                                },
                                "position": {
                                    "overlayPosition": {
                                        "anchorCell": {"rowIndex": 0, "columnIndex": 5}
                                    }
                                },
                            },
                        )
                    ],
                )
            ],
        )

        requests = generate_requests(diff_result)

        assert len(requests) == 1
        req = requests[0]
        assert "updateChartSpec" in req
        assert req["updateChartSpec"]["chartId"] == 789012
        assert req["updateChartSpec"]["spec"]["title"] == "New Title"
        assert req["updateChartSpec"]["spec"]["basicChart"]["chartType"] == "COLUMN"

    def test_chart_modified_position(self) -> None:
        """Test generating updateEmbeddedObjectPosition for position changes."""
        diff_result = DiffResult(
            spreadsheet_id="test123",
            sheet_diffs=[
                SheetDiff(
                    sheet_id=0,
                    sheet_name="Sheet1",
                    folder_name="Sheet1",
                    chart_changes=[
                        ChartChange(
                            chart_id=789012,
                            change_type="modified",
                            old_chart={
                                "chartId": 789012,
                                "spec": {"title": "Chart"},
                                "position": {
                                    "overlayPosition": {
                                        "anchorCell": {"rowIndex": 0, "columnIndex": 5},
                                        "widthPixels": 400,
                                        "heightPixels": 300,
                                    }
                                },
                            },
                            new_chart={
                                "chartId": 789012,
                                "spec": {"title": "Chart"},
                                "position": {
                                    "overlayPosition": {
                                        "anchorCell": {
                                            "rowIndex": 10,
                                            "columnIndex": 8,
                                        },
                                        "widthPixels": 600,
                                        "heightPixels": 400,
                                    }
                                },
                            },
                        )
                    ],
                )
            ],
        )

        requests = generate_requests(diff_result)

        assert len(requests) == 1
        req = requests[0]
        assert "updateEmbeddedObjectPosition" in req
        assert req["updateEmbeddedObjectPosition"]["objectId"] == 789012
        position = req["updateEmbeddedObjectPosition"]["newPosition"]
        assert position["overlayPosition"]["anchorCell"]["rowIndex"] == 10
        assert position["overlayPosition"]["anchorCell"]["sheetId"] == 0
        assert position["overlayPosition"]["widthPixels"] == 600

    def test_chart_modified_both(self) -> None:
        """Test generating both updateChartSpec and updateEmbeddedObjectPosition."""
        diff_result = DiffResult(
            spreadsheet_id="test123",
            sheet_diffs=[
                SheetDiff(
                    sheet_id=0,
                    sheet_name="Sheet1",
                    folder_name="Sheet1",
                    chart_changes=[
                        ChartChange(
                            chart_id=999888,
                            change_type="modified",
                            old_chart={
                                "chartId": 999888,
                                "spec": {"title": "Old Title"},
                                "position": {
                                    "overlayPosition": {
                                        "anchorCell": {"rowIndex": 0, "columnIndex": 0}
                                    }
                                },
                            },
                            new_chart={
                                "chartId": 999888,
                                "spec": {"title": "New Title"},
                                "position": {
                                    "overlayPosition": {
                                        "anchorCell": {"rowIndex": 5, "columnIndex": 5}
                                    }
                                },
                            },
                        )
                    ],
                )
            ],
        )

        requests = generate_requests(diff_result)

        # Should have 2 requests: updateChartSpec and updateEmbeddedObjectPosition
        assert len(requests) == 2

        request_types = [next(iter(r.keys())) for r in requests]
        assert "updateChartSpec" in request_types
        assert "updateEmbeddedObjectPosition" in request_types


class TestGeneratePivotTableRequests:
    """Tests for pivot table request generation."""

    def test_pivot_table_added(self) -> None:
        """Test generating updateCells for added pivot table."""
        diff_result = DiffResult(
            spreadsheet_id="test123",
            sheet_diffs=[
                SheetDiff(
                    sheet_id=0,
                    sheet_name="Sheet1",
                    folder_name="Sheet1",
                    pivot_table_changes=[
                        PivotTableChange(
                            anchor_cell="G1",
                            change_type="added",
                            old_pivot=None,
                            new_pivot={
                                "anchorCell": "G1",
                                "source": {
                                    "startRowIndex": 0,
                                    "endRowIndex": 100,
                                    "startColumnIndex": 0,
                                    "endColumnIndex": 5,
                                },
                                "rows": [{"sourceColumnOffset": 0}],
                                "values": [
                                    {
                                        "summarizeFunction": "SUM",
                                        "sourceColumnOffset": 1,
                                    }
                                ],
                            },
                        )
                    ],
                )
            ],
        )

        requests = generate_requests(diff_result)

        assert len(requests) == 1
        req = requests[0]
        assert "updateCells" in req

        update = req["updateCells"]
        assert update["fields"] == "pivotTable"
        assert update["start"]["sheetId"] == 0
        assert update["start"]["rowIndex"] == 0  # G1 is row 0
        assert update["start"]["columnIndex"] == 6  # G is column 6

        pivot = update["rows"][0]["values"][0]["pivotTable"]
        assert pivot["source"]["sheetId"] == 0
        assert pivot["rows"][0]["sourceColumnOffset"] == 0
        assert "anchorCell" not in pivot  # Should be stripped

    def test_pivot_table_deleted(self) -> None:
        """Test generating updateCells to clear pivot table."""
        diff_result = DiffResult(
            spreadsheet_id="test123",
            sheet_diffs=[
                SheetDiff(
                    sheet_id=0,
                    sheet_name="Sheet1",
                    folder_name="Sheet1",
                    pivot_table_changes=[
                        PivotTableChange(
                            anchor_cell="H5",
                            change_type="deleted",
                            old_pivot={
                                "anchorCell": "H5",
                                "source": {"startRowIndex": 0, "endRowIndex": 50},
                            },
                            new_pivot=None,
                        )
                    ],
                )
            ],
        )

        requests = generate_requests(diff_result)

        assert len(requests) == 1
        req = requests[0]
        assert "updateCells" in req

        update = req["updateCells"]
        assert update["fields"] == "pivotTable"
        assert update["start"]["rowIndex"] == 4  # H5 is row 4
        assert update["start"]["columnIndex"] == 7  # H is column 7
        assert update["rows"][0]["values"][0]["pivotTable"] is None

    def test_pivot_table_modified(self) -> None:
        """Test generating updateCells for modified pivot table."""
        diff_result = DiffResult(
            spreadsheet_id="test123",
            sheet_diffs=[
                SheetDiff(
                    sheet_id=0,
                    sheet_name="Sheet1",
                    folder_name="Sheet1",
                    pivot_table_changes=[
                        PivotTableChange(
                            anchor_cell="G1",
                            change_type="modified",
                            old_pivot={
                                "anchorCell": "G1",
                                "source": {"startRowIndex": 0, "endRowIndex": 50},
                                "rows": [{"sourceColumnOffset": 0}],
                            },
                            new_pivot={
                                "anchorCell": "G1",
                                "source": {"startRowIndex": 0, "endRowIndex": 100},
                                "rows": [{"sourceColumnOffset": 0}],
                                "columns": [{"sourceColumnOffset": 1}],
                            },
                        )
                    ],
                )
            ],
        )

        requests = generate_requests(diff_result)

        assert len(requests) == 1
        req = requests[0]
        assert "updateCells" in req

        update = req["updateCells"]
        assert update["fields"] == "pivotTable"
        pivot = update["rows"][0]["values"][0]["pivotTable"]
        assert pivot["source"]["endRowIndex"] == 100
        assert "columns" in pivot


class TestGenerateTableRequests:
    """Tests for table request generation."""

    def test_table_added(self) -> None:
        """Test generating addTable."""
        diff_result = DiffResult(
            spreadsheet_id="test123",
            sheet_diffs=[
                SheetDiff(
                    sheet_id=0,
                    sheet_name="Sheet1",
                    folder_name="Sheet1",
                    table_changes=[
                        TableChange(
                            table_id=None,
                            table_name="TestTable",
                            change_type="added",
                            old_table=None,
                            new_table={
                                "name": "TestTable",
                                "range": {
                                    "startRowIndex": 0,
                                    "endRowIndex": 10,
                                    "startColumnIndex": 0,
                                    "endColumnIndex": 5,
                                },
                            },
                        )
                    ],
                )
            ],
        )

        requests = generate_requests(diff_result)

        assert len(requests) == 1
        req = requests[0]
        assert "addTable" in req

        table = req["addTable"]["table"]
        assert table["name"] == "TestTable"
        assert table["range"]["sheetId"] == 0
        assert table["range"]["startRowIndex"] == 0
        assert table["range"]["endRowIndex"] == 10

    def test_table_deleted(self) -> None:
        """Test generating deleteTable."""
        diff_result = DiffResult(
            spreadsheet_id="test123",
            sheet_diffs=[
                SheetDiff(
                    sheet_id=0,
                    sheet_name="Sheet1",
                    folder_name="Sheet1",
                    table_changes=[
                        TableChange(
                            table_id="table123",
                            table_name="TestTable",
                            change_type="deleted",
                            old_table={
                                "tableId": "table123",
                                "name": "TestTable",
                                "range": {},
                            },
                            new_table=None,
                        )
                    ],
                )
            ],
        )

        requests = generate_requests(diff_result)

        assert len(requests) == 1
        req = requests[0]
        assert "deleteTable" in req
        assert req["deleteTable"]["tableId"] == "table123"

    def test_table_modified(self) -> None:
        """Test generating updateTable."""
        diff_result = DiffResult(
            spreadsheet_id="test123",
            sheet_diffs=[
                SheetDiff(
                    sheet_id=0,
                    sheet_name="Sheet1",
                    folder_name="Sheet1",
                    table_changes=[
                        TableChange(
                            table_id="table456",
                            table_name="NewName",
                            change_type="modified",
                            old_table={
                                "tableId": "table456",
                                "name": "OldName",
                                "range": {},
                            },
                            new_table={
                                "tableId": "table456",
                                "name": "NewName",
                                "range": {
                                    "startRowIndex": 0,
                                    "endRowIndex": 20,
                                    "startColumnIndex": 0,
                                    "endColumnIndex": 5,
                                },
                            },
                        )
                    ],
                )
            ],
        )

        requests = generate_requests(diff_result)

        assert len(requests) == 1
        req = requests[0]
        assert "updateTable" in req

        update = req["updateTable"]
        assert update["table"]["tableId"] == "table456"
        assert update["table"]["name"] == "NewName"
        assert update["fields"] == "*"


class TestGenerateNamedRangeRequests:
    """Tests for named range request generation."""

    def test_named_range_added(self) -> None:
        """Test generating addNamedRange."""
        diff_result = DiffResult(
            spreadsheet_id="test123",
            named_range_changes=[
                NamedRangeChange(
                    named_range_id=None,
                    name="TestRange",
                    change_type="added",
                    old_range=None,
                    new_range={
                        "name": "TestRange",
                        "range": {
                            "sheetId": 0,
                            "startRowIndex": 0,
                            "endRowIndex": 10,
                            "startColumnIndex": 0,
                            "endColumnIndex": 1,
                        },
                    },
                )
            ],
        )

        requests = generate_requests(diff_result)

        assert len(requests) == 1
        req = requests[0]
        assert "addNamedRange" in req

        named_range = req["addNamedRange"]["namedRange"]
        assert named_range["name"] == "TestRange"
        assert named_range["range"]["sheetId"] == 0

    def test_named_range_deleted(self) -> None:
        """Test generating deleteNamedRange."""
        diff_result = DiffResult(
            spreadsheet_id="test123",
            named_range_changes=[
                NamedRangeChange(
                    named_range_id="range123",
                    name="TestRange",
                    change_type="deleted",
                    old_range={
                        "namedRangeId": "range123",
                        "name": "TestRange",
                        "range": {},
                    },
                    new_range=None,
                )
            ],
        )

        requests = generate_requests(diff_result)

        assert len(requests) == 1
        req = requests[0]
        assert "deleteNamedRange" in req
        assert req["deleteNamedRange"]["namedRangeId"] == "range123"

    def test_named_range_modified(self) -> None:
        """Test generating updateNamedRange."""
        diff_result = DiffResult(
            spreadsheet_id="test123",
            named_range_changes=[
                NamedRangeChange(
                    named_range_id="range456",
                    name="NewName",
                    change_type="modified",
                    old_range={
                        "namedRangeId": "range456",
                        "name": "OldName",
                        "range": {"sheetId": 0, "startRowIndex": 0, "endRowIndex": 5},
                    },
                    new_range={
                        "namedRangeId": "range456",
                        "name": "NewName",
                        "range": {"sheetId": 0, "startRowIndex": 0, "endRowIndex": 10},
                    },
                )
            ],
        )

        requests = generate_requests(diff_result)

        assert len(requests) == 1
        req = requests[0]
        assert "updateNamedRange" in req

        update = req["updateNamedRange"]
        assert update["namedRange"]["namedRangeId"] == "range456"
        assert update["namedRange"]["name"] == "NewName"
        assert update["fields"] == "name,range"


class TestGenerateSlicerRequests:
    """Tests for slicer request generation."""

    def test_slicer_added(self) -> None:
        """Test generating addSlicer."""
        diff_result = DiffResult(
            spreadsheet_id="test123",
            sheet_diffs=[
                SheetDiff(
                    sheet_id=0,
                    sheet_name="Sheet1",
                    folder_name="Sheet1",
                    slicer_changes=[
                        SlicerChange(
                            slicer_id=None,
                            change_type="added",
                            old_slicer=None,
                            new_slicer={
                                "spec": {"title": "TestSlicer"},
                                "position": {
                                    "overlayPosition": {
                                        "anchorCell": {
                                            "sheetId": 0,
                                            "rowIndex": 0,
                                            "columnIndex": 0,
                                        }
                                    }
                                },
                            },
                        )
                    ],
                )
            ],
        )

        requests = generate_requests(diff_result)

        assert len(requests) == 1
        req = requests[0]
        assert "addSlicer" in req
        assert req["addSlicer"]["slicer"]["spec"]["title"] == "TestSlicer"

    def test_slicer_deleted(self) -> None:
        """Test generating deleteEmbeddedObject for slicer."""
        diff_result = DiffResult(
            spreadsheet_id="test123",
            sheet_diffs=[
                SheetDiff(
                    sheet_id=0,
                    sheet_name="Sheet1",
                    folder_name="Sheet1",
                    slicer_changes=[
                        SlicerChange(
                            slicer_id=123,
                            change_type="deleted",
                            old_slicer={
                                "slicerId": 123,
                                "spec": {"title": "TestSlicer"},
                            },
                            new_slicer=None,
                        )
                    ],
                )
            ],
        )

        requests = generate_requests(diff_result)

        assert len(requests) == 1
        req = requests[0]
        assert "deleteEmbeddedObject" in req
        assert req["deleteEmbeddedObject"]["objectId"] == 123

    def test_slicer_modified(self) -> None:
        """Test generating updateSlicerSpec."""
        diff_result = DiffResult(
            spreadsheet_id="test123",
            sheet_diffs=[
                SheetDiff(
                    sheet_id=0,
                    sheet_name="Sheet1",
                    folder_name="Sheet1",
                    slicer_changes=[
                        SlicerChange(
                            slicer_id=456,
                            change_type="modified",
                            old_slicer={
                                "slicerId": 456,
                                "spec": {"title": "OldTitle"},
                            },
                            new_slicer={
                                "slicerId": 456,
                                "spec": {"title": "NewTitle"},
                            },
                        )
                    ],
                )
            ],
        )

        requests = generate_requests(diff_result)

        assert len(requests) == 1
        req = requests[0]
        assert "updateSlicerSpec" in req
        assert req["updateSlicerSpec"]["slicerId"] == 456
        assert req["updateSlicerSpec"]["spec"]["title"] == "NewTitle"


class TestGenerateDataSourceTableRequests:
    """Tests for data source table request generation."""

    def test_data_source_table_modified(self) -> None:
        """Test generating refreshDataSource for modified data source table."""
        diff_result = DiffResult(
            spreadsheet_id="test123",
            sheet_diffs=[
                SheetDiff(
                    sheet_id=0,
                    sheet_name="Sheet1",
                    folder_name="Sheet1",
                    data_source_table_changes=[
                        DataSourceTableChange(
                            anchor_cell="A1",
                            change_type="modified",
                            old_table={
                                "anchorCell": "A1",
                                "dataSourceId": "ds123",
                                "columns": ["col1"],
                            },
                            new_table={
                                "anchorCell": "A1",
                                "dataSourceId": "ds123",
                                "columns": ["col1", "col2"],
                            },
                        )
                    ],
                )
            ],
        )

        requests = generate_requests(diff_result)

        assert len(requests) == 1
        req = requests[0]
        assert "refreshDataSource" in req
        assert req["refreshDataSource"]["dataSourceId"] == "ds123"

    def test_data_source_table_added_no_request(self) -> None:
        """Test that added data source tables don't generate requests (unsupported)."""
        diff_result = DiffResult(
            spreadsheet_id="test123",
            sheet_diffs=[
                SheetDiff(
                    sheet_id=0,
                    sheet_name="Sheet1",
                    folder_name="Sheet1",
                    data_source_table_changes=[
                        DataSourceTableChange(
                            anchor_cell="A1",
                            change_type="added",
                            old_table=None,
                            new_table={
                                "anchorCell": "A1",
                                "dataSourceId": "ds123",
                            },
                        )
                    ],
                )
            ],
        )

        requests = generate_requests(diff_result)

        # Adding data source tables is not supported via batchUpdate
        assert len(requests) == 0

    def test_data_source_table_deleted_no_request(self) -> None:
        """Test that deleted data source tables don't generate requests (unsupported)."""
        diff_result = DiffResult(
            spreadsheet_id="test123",
            sheet_diffs=[
                SheetDiff(
                    sheet_id=0,
                    sheet_name="Sheet1",
                    folder_name="Sheet1",
                    data_source_table_changes=[
                        DataSourceTableChange(
                            anchor_cell="A1",
                            change_type="deleted",
                            old_table={
                                "anchorCell": "A1",
                                "dataSourceId": "ds123",
                            },
                            new_table=None,
                        )
                    ],
                )
            ],
        )

        requests = generate_requests(diff_result)

        # Deleting data source tables is not supported via batchUpdate
        assert len(requests) == 0
