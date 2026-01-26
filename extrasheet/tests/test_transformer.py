"""Tests for extrasheet.transformer module."""

from extrasheet.transformer import SpreadsheetTransformer


class TestSpreadsheetTransformer:
    """Tests for SpreadsheetTransformer class."""

    def test_empty_spreadsheet(self) -> None:
        """Test transforming an empty spreadsheet."""
        spreadsheet = {
            "spreadsheetId": "test123",
            "spreadsheetUrl": "https://docs.google.com/spreadsheets/d/test123",
            "properties": {"title": "Test Spreadsheet"},
            "sheets": [],
        }

        transformer = SpreadsheetTransformer(spreadsheet)
        result = transformer.transform()

        assert "test123/spreadsheet.json" in result
        meta = result["test123/spreadsheet.json"]
        assert meta["spreadsheetId"] == "test123"
        assert meta["sheets"] == []

    def test_single_sheet_with_data(self) -> None:
        """Test transforming a spreadsheet with one sheet containing data."""
        spreadsheet = {
            "spreadsheetId": "test123",
            "spreadsheetUrl": "https://docs.google.com/spreadsheets/d/test123",
            "properties": {"title": "Test Spreadsheet"},
            "sheets": [
                {
                    "properties": {
                        "sheetId": 0,
                        "title": "Sheet1",
                        "index": 0,
                        "sheetType": "GRID",
                        "gridProperties": {"rowCount": 10, "columnCount": 5},
                    },
                    "data": [
                        {
                            "startRow": 0,
                            "startColumn": 0,
                            "rowData": [
                                {
                                    "values": [
                                        {"formattedValue": "Name"},
                                        {"formattedValue": "Value"},
                                    ]
                                },
                                {
                                    "values": [
                                        {"formattedValue": "Alice"},
                                        {"formattedValue": "100"},
                                    ]
                                },
                            ],
                        }
                    ],
                }
            ],
        }

        transformer = SpreadsheetTransformer(spreadsheet)
        result = transformer.transform()

        # Check spreadsheet metadata
        assert "test123/spreadsheet.json" in result
        meta = result["test123/spreadsheet.json"]
        assert len(meta["sheets"]) == 1
        assert meta["sheets"][0]["title"] == "Sheet1"
        assert meta["sheets"][0]["folder"] == "Sheet1"

        # Check data.tsv
        assert "test123/Sheet1/data.tsv" in result
        tsv = result["test123/Sheet1/data.tsv"]
        lines = tsv.split("\n")
        assert lines[0] == "A\tB"  # Header
        assert lines[1] == "Name\tValue"
        assert lines[2] == "Alice\t100"

    def test_sheet_with_formulas(self) -> None:
        """Test extracting formulas from cells."""
        spreadsheet = {
            "spreadsheetId": "test123",
            "properties": {"title": "Test"},
            "sheets": [
                {
                    "properties": {
                        "sheetId": 0,
                        "title": "Sheet1",
                        "sheetType": "GRID",
                        "gridProperties": {"rowCount": 5, "columnCount": 3},
                    },
                    "data": [
                        {
                            "startRow": 0,
                            "startColumn": 0,
                            "rowData": [
                                {
                                    "values": [
                                        {"formattedValue": "A"},
                                        {"formattedValue": "B"},
                                        {"formattedValue": "Total"},
                                    ]
                                },
                                {
                                    "values": [
                                        {"formattedValue": "10"},
                                        {"formattedValue": "20"},
                                        {
                                            "formattedValue": "30",
                                            "userEnteredValue": {
                                                "formulaValue": "=A2+B2"
                                            },
                                        },
                                    ]
                                },
                            ],
                        }
                    ],
                }
            ],
        }

        transformer = SpreadsheetTransformer(spreadsheet)
        result = transformer.transform()

        # Check formula.json
        assert "test123/Sheet1/formula.json" in result
        formulas = result["test123/Sheet1/formula.json"]
        assert formulas["formulas"]["C2"] == "=A2+B2"

    def test_sheet_with_formatting(self) -> None:
        """Test extracting cell formatting."""
        spreadsheet = {
            "spreadsheetId": "test123",
            "properties": {"title": "Test"},
            "sheets": [
                {
                    "properties": {
                        "sheetId": 0,
                        "title": "Sheet1",
                        "sheetType": "GRID",
                        "gridProperties": {"rowCount": 5, "columnCount": 3},
                    },
                    "data": [
                        {
                            "startRow": 0,
                            "startColumn": 0,
                            "rowData": [
                                {
                                    "values": [
                                        {
                                            "formattedValue": "Header",
                                            "userEnteredFormat": {
                                                "textFormat": {"bold": True}
                                            },
                                        }
                                    ]
                                }
                            ],
                        }
                    ],
                }
            ],
        }

        transformer = SpreadsheetTransformer(spreadsheet)
        result = transformer.transform()

        # Check format.json
        assert "test123/Sheet1/format.json" in result
        formatting = result["test123/Sheet1/format.json"]
        assert "cellFormats" in formatting
        assert "A1" in formatting["cellFormats"]
        assert formatting["cellFormats"]["A1"]["textFormat"]["bold"] is True

    def test_sheet_with_notes(self) -> None:
        """Test extracting cell notes."""
        spreadsheet = {
            "spreadsheetId": "test123",
            "properties": {"title": "Test"},
            "sheets": [
                {
                    "properties": {
                        "sheetId": 0,
                        "title": "Sheet1",
                        "sheetType": "GRID",
                        "gridProperties": {"rowCount": 5, "columnCount": 3},
                    },
                    "data": [
                        {
                            "startRow": 0,
                            "startColumn": 0,
                            "rowData": [
                                {
                                    "values": [
                                        {
                                            "formattedValue": "Cell with note",
                                            "note": "This is a note",
                                        }
                                    ]
                                }
                            ],
                        }
                    ],
                }
            ],
        }

        transformer = SpreadsheetTransformer(spreadsheet)
        result = transformer.transform()

        # Check format.json has notes
        assert "test123/Sheet1/format.json" in result
        formatting = result["test123/Sheet1/format.json"]
        assert "notes" in formatting
        assert formatting["notes"]["A1"] == "This is a note"

    def test_named_ranges(self) -> None:
        """Test extracting named ranges."""
        spreadsheet = {
            "spreadsheetId": "test123",
            "properties": {"title": "Test"},
            "sheets": [],
            "namedRanges": [
                {
                    "namedRangeId": "range1",
                    "name": "SalesData",
                    "range": {
                        "sheetId": 0,
                        "startRowIndex": 0,
                        "endRowIndex": 100,
                        "startColumnIndex": 0,
                        "endColumnIndex": 5,
                    },
                }
            ],
        }

        transformer = SpreadsheetTransformer(spreadsheet)
        result = transformer.transform()

        # Check named_ranges.json
        assert "test123/named_ranges.json" in result
        named = result["test123/named_ranges.json"]
        assert len(named["namedRanges"]) == 1
        assert named["namedRanges"][0]["name"] == "SalesData"

    def test_conditional_formatting(self) -> None:
        """Test extracting conditional formatting rules."""
        spreadsheet = {
            "spreadsheetId": "test123",
            "properties": {"title": "Test"},
            "sheets": [
                {
                    "properties": {
                        "sheetId": 0,
                        "title": "Sheet1",
                        "sheetType": "GRID",
                        "gridProperties": {"rowCount": 10, "columnCount": 5},
                    },
                    "conditionalFormats": [
                        {
                            "ranges": [
                                {
                                    "sheetId": 0,
                                    "startRowIndex": 1,
                                    "endRowIndex": 10,
                                    "startColumnIndex": 1,
                                    "endColumnIndex": 2,
                                }
                            ],
                            "booleanRule": {
                                "condition": {
                                    "type": "NUMBER_GREATER",
                                    "values": [{"userEnteredValue": "100"}],
                                },
                                "format": {
                                    "backgroundColor": {
                                        "red": 0.8,
                                        "green": 1.0,
                                        "blue": 0.8,
                                    }
                                },
                            },
                        }
                    ],
                    "data": [{"rowData": []}],
                }
            ],
        }

        transformer = SpreadsheetTransformer(spreadsheet)
        result = transformer.transform()

        # Check format.json has conditional formats
        assert "test123/Sheet1/format.json" in result
        formatting = result["test123/Sheet1/format.json"]
        assert "conditionalFormats" in formatting
        assert len(formatting["conditionalFormats"]) == 1
        assert formatting["conditionalFormats"][0]["ruleIndex"] == 0
        assert "B2:B10" in formatting["conditionalFormats"][0]["ranges"]

    def test_duplicate_sheet_names(self) -> None:
        """Test handling duplicate sheet names."""
        spreadsheet = {
            "spreadsheetId": "test123",
            "properties": {"title": "Test"},
            "sheets": [
                {
                    "properties": {
                        "sheetId": 0,
                        "title": "Sheet1",
                        "sheetType": "GRID",
                        "gridProperties": {"rowCount": 5, "columnCount": 3},
                    },
                    "data": [],
                },
                {
                    "properties": {
                        "sheetId": 1,
                        "title": "Sheet1",  # Duplicate name
                        "sheetType": "GRID",
                        "gridProperties": {"rowCount": 5, "columnCount": 3},
                    },
                    "data": [],
                },
            ],
        }

        transformer = SpreadsheetTransformer(spreadsheet)
        result = transformer.transform()

        meta = result["test123/spreadsheet.json"]
        folders = [s["folder"] for s in meta["sheets"]]
        # Folders should be unique
        assert len(set(folders)) == len(folders)
        assert "Sheet1" in folders
        assert "Sheet1_1" in folders

    def test_charts(self) -> None:
        """Test extracting charts."""
        spreadsheet = {
            "spreadsheetId": "test123",
            "properties": {"title": "Test"},
            "sheets": [
                {
                    "properties": {
                        "sheetId": 0,
                        "title": "Sheet1",
                        "sheetType": "GRID",
                        "gridProperties": {"rowCount": 10, "columnCount": 5},
                    },
                    "charts": [
                        {
                            "chartId": 12345,
                            "position": {
                                "overlayPosition": {
                                    "anchorCell": {
                                        "sheetId": 0,
                                        "rowIndex": 0,
                                        "columnIndex": 5,
                                    }
                                }
                            },
                            "spec": {"title": "Sales Chart"},
                        }
                    ],
                    "data": [],
                }
            ],
        }

        transformer = SpreadsheetTransformer(spreadsheet)
        result = transformer.transform()

        # Check feature.json has charts
        assert "test123/Sheet1/feature.json" in result
        features = result["test123/Sheet1/feature.json"]
        assert "charts" in features
        assert len(features["charts"]) == 1
        assert features["charts"][0]["chartId"] == 12345

    def test_protected_ranges(self) -> None:
        """Test extracting protected ranges."""
        spreadsheet = {
            "spreadsheetId": "test123",
            "properties": {"title": "Test"},
            "sheets": [
                {
                    "properties": {
                        "sheetId": 0,
                        "title": "Sheet1",
                        "sheetType": "GRID",
                        "gridProperties": {"rowCount": 10, "columnCount": 5},
                    },
                    "protectedRanges": [
                        {
                            "protectedRangeId": 99999,
                            "range": {
                                "sheetId": 0,
                                "startRowIndex": 0,
                                "endRowIndex": 1,
                            },
                            "description": "Header row",
                        }
                    ],
                    "data": [],
                }
            ],
        }

        transformer = SpreadsheetTransformer(spreadsheet)
        result = transformer.transform()

        # Check protection.json
        assert "test123/Sheet1/protection.json" in result
        protection = result["test123/Sheet1/protection.json"]
        assert len(protection["protectedRanges"]) == 1
        assert protection["protectedRanges"][0]["protectedRangeId"] == 99999


class TestObjectSheets:
    """Tests for object sheets (non-grid sheets)."""

    def test_object_sheet(self) -> None:
        """Test handling object sheets (chart-only sheets)."""
        spreadsheet = {
            "spreadsheetId": "test123",
            "properties": {"title": "Test"},
            "sheets": [
                {
                    "properties": {
                        "sheetId": 0,
                        "title": "ChartSheet",
                        "sheetType": "OBJECT",
                    },
                    "charts": [
                        {
                            "chartId": 12345,
                            "spec": {"title": "Big Chart"},
                        }
                    ],
                }
            ],
        }

        transformer = SpreadsheetTransformer(spreadsheet)
        result = transformer.transform()

        # Should not have data.tsv for object sheets
        assert "test123/ChartSheet/data.tsv" not in result
        # Should have feature.json with chart
        assert "test123/ChartSheet/feature.json" in result
