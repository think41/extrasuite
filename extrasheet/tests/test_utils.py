"""Tests for extrasheet.utils module."""

import pytest

from extrasheet.utils import (
    a1_range_to_grid_range,
    a1_to_cell,
    cell_to_a1,
    column_index_to_letter,
    escape_tsv_value,
    get_effective_value_string,
    grid_range_to_a1,
    is_default_cell_format,
    is_default_dimension,
    letter_to_column_index,
    parse_a1_with_sheet_prefix,
    range_to_a1,
    sanitize_filename,
    unescape_tsv_value,
)


class TestColumnConversion:
    """Tests for column index to letter conversion."""

    def test_single_letters(self) -> None:
        assert column_index_to_letter(0) == "A"
        assert column_index_to_letter(1) == "B"
        assert column_index_to_letter(25) == "Z"

    def test_double_letters(self) -> None:
        assert column_index_to_letter(26) == "AA"
        assert column_index_to_letter(27) == "AB"
        assert column_index_to_letter(51) == "AZ"
        assert column_index_to_letter(52) == "BA"
        assert column_index_to_letter(701) == "ZZ"

    def test_triple_letters(self) -> None:
        assert column_index_to_letter(702) == "AAA"

    def test_letter_to_index(self) -> None:
        assert letter_to_column_index("A") == 0
        assert letter_to_column_index("B") == 1
        assert letter_to_column_index("Z") == 25
        assert letter_to_column_index("AA") == 26
        assert letter_to_column_index("AB") == 27
        assert letter_to_column_index("ZZ") == 701
        assert letter_to_column_index("AAA") == 702

    def test_roundtrip(self) -> None:
        for i in range(1000):
            letter = column_index_to_letter(i)
            assert letter_to_column_index(letter) == i


class TestCellConversion:
    """Tests for cell coordinate conversion."""

    def test_cell_to_a1(self) -> None:
        assert cell_to_a1(0, 0) == "A1"
        assert cell_to_a1(0, 1) == "B1"
        assert cell_to_a1(9, 2) == "C10"
        assert cell_to_a1(0, 26) == "AA1"

    def test_a1_to_cell(self) -> None:
        assert a1_to_cell("A1") == (0, 0)
        assert a1_to_cell("B1") == (0, 1)
        assert a1_to_cell("C10") == (9, 2)
        assert a1_to_cell("AA1") == (0, 26)

    def test_a1_to_cell_invalid(self) -> None:
        with pytest.raises(ValueError):
            a1_to_cell("invalid")
        with pytest.raises(ValueError):
            a1_to_cell("123")
        with pytest.raises(ValueError):
            a1_to_cell("")


class TestRangeConversion:
    """Tests for range to A1 notation conversion."""

    def test_single_cell(self) -> None:
        assert range_to_a1(0, 1, 0, 1) == "A1"
        assert range_to_a1(9, 10, 2, 3) == "C10"

    def test_range(self) -> None:
        assert range_to_a1(0, 10, 0, 5) == "A1:E10"
        assert range_to_a1(0, 100, 0, 26) == "A1:Z100"

    def test_full_column(self) -> None:
        assert range_to_a1(None, None, 0, 1) == "A:A"
        assert range_to_a1(None, None, 0, 3) == "A:C"

    def test_full_row(self) -> None:
        assert range_to_a1(0, 1, None, None) == "1:1"
        assert range_to_a1(0, 5, None, None) == "1:5"

    def test_grid_range_to_a1(self) -> None:
        grid_range = {
            "sheetId": 0,
            "startRowIndex": 0,
            "endRowIndex": 10,
            "startColumnIndex": 0,
            "endColumnIndex": 5,
        }
        assert grid_range_to_a1(grid_range) == "A1:E10"


class TestFilenameSanitization:
    """Tests for filename sanitization."""

    def test_valid_name(self) -> None:
        assert sanitize_filename("Sheet1") == "Sheet1"
        assert sanitize_filename("My Sheet") == "My Sheet"

    def test_invalid_characters(self) -> None:
        assert sanitize_filename("Sheet/Name") == "Sheet_Name"
        assert sanitize_filename("Sheet:Name") == "Sheet_Name"
        assert sanitize_filename('Sheet"Name') == "Sheet_Name"
        assert sanitize_filename("Sheet<Name>") == "Sheet_Name_"

    def test_leading_trailing(self) -> None:
        assert sanitize_filename("  Sheet1  ") == "Sheet1"
        assert sanitize_filename("...Sheet1...") == "Sheet1"

    def test_empty(self) -> None:
        assert sanitize_filename("") == "unnamed"
        assert sanitize_filename("   ") == "unnamed"

    def test_collapse_underscores(self) -> None:
        assert sanitize_filename("A///B") == "A_B"


class TestTsvEscaping:
    """Tests for TSV value escaping."""

    def test_no_escape_needed(self) -> None:
        assert escape_tsv_value("Hello") == "Hello"
        assert escape_tsv_value("123") == "123"

    def test_escape_tab(self) -> None:
        assert escape_tsv_value("Hello\tWorld") == "Hello\\tWorld"

    def test_escape_newline(self) -> None:
        assert escape_tsv_value("Hello\nWorld") == "Hello\\nWorld"
        assert escape_tsv_value("Hello\r\nWorld") == "Hello\\r\\nWorld"

    def test_escape_backslash(self) -> None:
        assert escape_tsv_value("Hello\\World") == "Hello\\\\World"

    def test_unescape_roundtrip(self) -> None:
        test_cases = [
            "Hello",
            "Tab\there",
            "New\nline",
            "Back\\slash",
            "All\t\n\\chars",
        ]
        for original in test_cases:
            escaped = escape_tsv_value(original)
            unescaped = unescape_tsv_value(escaped)
            assert unescaped == original


class TestEffectiveValueString:
    """Tests for extracting effective value strings from cell data."""

    def test_string_value(self) -> None:
        cell = {"effectiveValue": {"stringValue": "Test"}}
        assert get_effective_value_string(cell) == "Test"

    def test_number_value(self) -> None:
        cell = {"effectiveValue": {"numberValue": 42.5}}
        assert get_effective_value_string(cell) == "42.5"

    def test_integer_value(self) -> None:
        cell = {"effectiveValue": {"numberValue": 42.0}}
        assert get_effective_value_string(cell) == "42"

    def test_bool_value(self) -> None:
        cell = {"effectiveValue": {"boolValue": True}}
        assert get_effective_value_string(cell) == "TRUE"
        cell = {"effectiveValue": {"boolValue": False}}
        assert get_effective_value_string(cell) == "FALSE"

    def test_error_value(self) -> None:
        cell = {"effectiveValue": {"errorValue": {"message": "#REF!"}}}
        assert get_effective_value_string(cell) == "#REF!"

    def test_empty_cell(self) -> None:
        assert get_effective_value_string({}) == ""
        assert get_effective_value_string({"effectiveValue": {}}) == ""

    def test_uses_effective_value_not_formatted(self) -> None:
        """Verify effectiveValue is used for round-trip safety, not formattedValue."""
        cell = {
            "formattedValue": "$1,234.56",
            "effectiveValue": {"numberValue": 1234.56},
        }
        assert get_effective_value_string(cell) == "1234.56"


class TestDefaultChecks:
    """Tests for default value checking."""

    def test_default_cell_format(self) -> None:
        assert is_default_cell_format({}) is True
        assert is_default_cell_format(None) is True
        assert is_default_cell_format({"textFormat": {"bold": True}}) is False

    def test_default_dimension(self) -> None:
        assert is_default_dimension({}, is_row=True) is True
        assert is_default_dimension({"pixelSize": 21}, is_row=True) is True
        assert is_default_dimension({"pixelSize": 50}, is_row=True) is False
        assert is_default_dimension({"pixelSize": 100}, is_row=False) is True
        assert is_default_dimension({"pixelSize": 200}, is_row=False) is False
        assert is_default_dimension({"hidden": True}, is_row=True) is False


class TestParseA1WithSheetPrefix:
    """Tests for parsing A1 references with optional sheet name prefix."""

    def test_no_sheet_prefix(self) -> None:
        sheet_name, range_part = parse_a1_with_sheet_prefix("A1:B5")
        assert sheet_name is None
        assert range_part == "A1:B5"

    def test_simple_sheet_name(self) -> None:
        sheet_name, range_part = parse_a1_with_sheet_prefix("Sheet1!A1:B5")
        assert sheet_name == "Sheet1"
        assert range_part == "A1:B5"

    def test_quoted_sheet_name(self) -> None:
        sheet_name, range_part = parse_a1_with_sheet_prefix("'My Sheet'!A1:B5")
        assert sheet_name == "My Sheet"
        assert range_part == "A1:B5"

    def test_sheet_name_with_spaces(self) -> None:
        sheet_name, range_part = parse_a1_with_sheet_prefix("'Git Commits'!A1:I41")
        assert sheet_name == "Git Commits"
        assert range_part == "A1:I41"

    def test_single_cell_reference(self) -> None:
        sheet_name, range_part = parse_a1_with_sheet_prefix("Sheet2!C3")
        assert sheet_name == "Sheet2"
        assert range_part == "C3"


class TestA1RangeToGridRangeWithSheetPrefix:
    """Tests for a1_range_to_grid_range with cross-sheet references."""

    def test_simple_range_no_prefix(self) -> None:
        result = a1_range_to_grid_range("A1:B5", sheet_id=123)
        assert result == {
            "sheetId": 123,
            "startRowIndex": 0,
            "endRowIndex": 5,
            "startColumnIndex": 0,
            "endColumnIndex": 2,
        }

    def test_single_cell_no_prefix(self) -> None:
        result = a1_range_to_grid_range("C3", sheet_id=0)
        assert result == {
            "sheetId": 0,
            "startRowIndex": 2,
            "endRowIndex": 3,
            "startColumnIndex": 2,
            "endColumnIndex": 3,
        }

    def test_cross_sheet_reference(self) -> None:
        sheet_name_to_id = {"Sheet1": 100, "Sheet2": 200}
        result = a1_range_to_grid_range(
            "Sheet2!A1:B5", sheet_id=0, sheet_name_to_id=sheet_name_to_id
        )
        assert result["sheetId"] == 200
        assert result["startRowIndex"] == 0
        assert result["endRowIndex"] == 5

    def test_cross_sheet_reference_with_spaces(self) -> None:
        sheet_name_to_id = {"Git Commits": 6, "Analytics": 7}
        result = a1_range_to_grid_range(
            "'Git Commits'!A1:I41", sheet_id=0, sheet_name_to_id=sheet_name_to_id
        )
        assert result["sheetId"] == 6
        assert result["startRowIndex"] == 0
        assert result["endRowIndex"] == 41
        assert result["startColumnIndex"] == 0
        assert result["endColumnIndex"] == 9  # I is column 8 (0-indexed), +1 exclusive

    def test_cross_sheet_reference_missing_mapping(self) -> None:
        with pytest.raises(ValueError, match="requires sheet_name_to_id mapping"):
            a1_range_to_grid_range("Sheet2!A1:B5", sheet_id=0)

    def test_cross_sheet_reference_unknown_sheet(self) -> None:
        sheet_name_to_id = {"Sheet1": 100}
        with pytest.raises(ValueError, match="Unknown sheet"):
            a1_range_to_grid_range(
                "Sheet2!A1:B5", sheet_id=0, sheet_name_to_id=sheet_name_to_id
            )
