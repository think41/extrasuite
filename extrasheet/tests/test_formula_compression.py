"""Tests for formula compression."""

from extrasheet.formula_compression import (
    _denormalize_formula,
    _normalize_formula,
    compress_formulas,
    expand_formulas,
)


class TestNormalizeFormula:
    """Tests for formula normalization."""

    def test_simple_relative_ref(self):
        """Test normalizing a simple relative reference."""
        # Formula in B2 referencing A1
        result = _normalize_formula("=A1", 1, 1)
        assert result == "={c-1}{r-1}"

    def test_same_row_reference(self):
        """Test reference in same row."""
        # Formula in C2 referencing A2
        result = _normalize_formula("=A2", 1, 2)
        assert result == "={c-2}{r}"

    def test_same_col_reference(self):
        """Test reference in same column."""
        # Formula in A5 referencing A2
        result = _normalize_formula("=A2", 4, 0)
        assert result == "={c}{r-3}"

    def test_absolute_reference(self):
        """Test absolute references are preserved."""
        result = _normalize_formula("=$A$1", 5, 5)
        assert result == "=$A$1"

    def test_mixed_reference_col_absolute(self):
        """Test mixed reference with absolute column."""
        result = _normalize_formula("=$A1", 1, 2)
        assert result == "=$A{r-1}"

    def test_mixed_reference_row_absolute(self):
        """Test mixed reference with absolute row."""
        result = _normalize_formula("=A$1", 1, 2)
        assert result == "={c-2}$1"

    def test_complex_formula(self):
        """Test formula with multiple references."""
        # Formula in C2: =A2+B2
        result = _normalize_formula("=A2+B2", 1, 2)
        assert result == "={c-2}{r}+{c-1}{r}"

    def test_range_reference(self):
        """Test formula with range reference."""
        # Formula in D2: =SUM(A2:C2)
        result = _normalize_formula("=SUM(A2:C2)", 1, 3)
        assert result == "=SUM({c-3}{r}:{c-1}{r})"

    def test_structured_table_reference_not_matched(self):
        """Test that structured table references like Table1_2[#ALL] are not matched.

        This ensures names like 'Table1' are not mistakenly parsed as cell references.
        """
        # Formula in F2: =vlookup(E2,Table1_2[#ALL],3,0)
        result = _normalize_formula("=vlookup(E2,Table1_2[#ALL],3,0)", 1, 5)
        # Only E2 should be normalized (col offset -1, same row)
        # Table1_2[#ALL] should be unchanged
        assert result == "=vlookup({c-1}{r},Table1_2[#ALL],3,0)"


class TestDenormalizeFormula:
    """Tests for formula denormalization."""

    def test_simple_pattern(self):
        """Test denormalizing a simple pattern."""
        pattern = "={c-1}{r-1}"
        # For cell B2 (row=1, col=1)
        result = _denormalize_formula(pattern, 1, 1)
        assert result == "=A1"

    def test_same_row_pattern(self):
        """Test same row pattern."""
        pattern = "={c-2}{r}"
        # For cell C5 (row=4, col=2)
        result = _denormalize_formula(pattern, 4, 2)
        assert result == "=A5"

    def test_complex_pattern(self):
        """Test complex pattern with multiple refs."""
        pattern = "={c-2}{r}+{c-1}{r}"
        # For cell D3 (row=2, col=3)
        result = _denormalize_formula(pattern, 2, 3)
        assert result == "=B3+C3"


class TestCompressFormulas:
    """Tests for the main compress_formulas function."""

    def test_empty_input(self):
        """Test with no formulas."""
        result = compress_formulas({})
        assert result == {}

    def test_single_formula(self):
        """Test single formula stays as single cell."""
        formulas = {"A1": "=B1+C1"}
        result = compress_formulas(formulas)
        assert result == {"A1": "=B1+C1"}

    def test_2_cells_compressed(self):
        """Test that 2 contiguous cells are compressed into a range."""
        formulas = {
            "K4": '=I4&" - "&J4',
            "K5": '=I5&" - "&J5',
        }
        result = compress_formulas(formulas)

        # Should be compressed into a range
        assert "K4:K5" in result
        assert result["K4:K5"] == '=I4&" - "&J4'

    def test_3_cells_compressed(self):
        """Test that 3 contiguous cells are compressed into a range."""
        formulas = {
            "K4": '=I4&" - "&J4',
            "K5": '=I5&" - "&J5',
            "K6": '=I6&" - "&J6',
        }
        result = compress_formulas(formulas)

        # Should be compressed into a range
        assert "K4:K6" in result
        assert result["K4:K6"] == '=I4&" - "&J4'

    def test_4_cells_compressed(self):
        """Test that 4+ cells with same pattern in a column are compressed."""
        formulas = {
            "K4": '=I4&" - "&J4',
            "K5": '=I5&" - "&J5',
            "K6": '=I6&" - "&J6',
            "K7": '=I7&" - "&J7',
        }
        result = compress_formulas(formulas)

        assert "K4:K7" in result
        # Formula should be the actual formula from first cell (not pattern)
        assert result["K4:K7"] == '=I4&" - "&J4'
        # Should only have one entry
        assert len(result) == 1

    def test_4_cells_in_row_compressed(self):
        """Test formulas with same pattern in a row are compressed."""
        formulas = {
            "B1": "=B2+B3",
            "C1": "=C2+C3",
            "D1": "=D2+D3",
            "E1": "=E2+E3",
        }
        result = compress_formulas(formulas)

        assert "B1:E1" in result
        assert result["B1:E1"] == "=B2+B3"

    def test_mixed_formulas(self):
        """Test mix of compressible and non-compressible formulas."""
        formulas = {
            "A1": "=SUM(B:B)",  # Unique formula
            "C2": "=A2+B2",
            "C3": "=A3+B3",
            "C4": "=A4+B4",
            "C5": "=A5+B5",
        }
        result = compress_formulas(formulas)

        # C2:C5 should be compressed
        assert "C2:C5" in result

        # A1 should remain as individual formula
        assert result["A1"] == "=SUM(B:B)"

    def test_non_contiguous_split_into_ranges(self):
        """Test non-contiguous cells are split into maximal contiguous ranges."""
        formulas = {
            "A1": "=B1+C1",
            "C1": "=D1+E1",  # Skip B1
            "D1": "=E1+F1",
            "E1": "=F1+G1",
        }
        result = compress_formulas(formulas)

        # Should have A1 as single cell and C1:E1 as range
        assert "A1" in result
        assert result["A1"] == "=B1+C1"
        assert "C1:E1" in result
        assert result["C1:E1"] == "=D1+E1"

    def test_non_contiguous_all_single_cells(self):
        """Test non-contiguous cells with gaps become individual cells."""
        formulas = {
            "A1": "=B1+C1",
            "A3": "=B3+C3",  # Skip A2
            "A5": "=B5+C5",  # Skip A4
        }
        result = compress_formulas(formulas)

        # Non-contiguous cells should be stored individually
        assert result["A1"] == "=B1+C1"
        assert result["A3"] == "=B3+C3"
        assert result["A5"] == "=B5+C5"

    def test_structured_table_reference_compressed(self):
        """Test formulas with structured table references are properly compressed.

        Regression test: 'Table1' in 'Table1_2[#ALL]' was incorrectly matched as
        a cell reference, causing each formula to normalize differently and
        preventing compression.
        """
        formulas = {
            "F2": "=vlookup(E2,Table1_2[#ALL],3,0)",
            "F3": "=vlookup(E3,Table1_2[#ALL],3,0)",
            "F4": "=vlookup(E4,Table1_2[#ALL],3,0)",
            "F5": "=vlookup(E5,Table1_2[#ALL],3,0)",
        }
        result = compress_formulas(formulas)

        # Should be compressed into a single range
        assert "F2:F5" in result
        assert result["F2:F5"] == "=vlookup(E2,Table1_2[#ALL],3,0)"
        assert len(result) == 1

    def test_quoted_sheet_name_with_number_compressed(self):
        """Test formulas with quoted sheet names containing numbers are compressed.

        Regression test: 'R41' in "'R41 Shortlisted'!A:A" was incorrectly matched as
        a cell reference, causing each formula to normalize differently and
        preventing compression.
        """
        formulas = {
            "J2": "=xlookup(A2,'R41 Shortlisted'!A:A,'R41 Shortlisted'!B:B,\"No\")",
            "J3": "=xlookup(A3,'R41 Shortlisted'!A:A,'R41 Shortlisted'!B:B,\"No\")",
            "J4": "=xlookup(A4,'R41 Shortlisted'!A:A,'R41 Shortlisted'!B:B,\"No\")",
            "J5": "=xlookup(A5,'R41 Shortlisted'!A:A,'R41 Shortlisted'!B:B,\"No\")",
        }
        result = compress_formulas(formulas)

        # Should be compressed into a single range
        assert "J2:J5" in result
        assert len(result) == 1


class TestExpandFormulas:
    """Tests for expanding compressed formulas."""

    def test_expand_formula_range(self):
        """Test expanding a formula range."""
        compressed = {"C2:C5": "=A2+B2"}
        result = expand_formulas(compressed)

        assert result["C2"] == "=A2+B2"
        assert result["C3"] == "=A3+B3"
        assert result["C4"] == "=A4+B4"
        assert result["C5"] == "=A5+B5"

    def test_expand_formula_range_horizontal(self):
        """Test expanding a horizontal formula range."""
        compressed = {"B1:E1": "=B2+B3"}
        result = expand_formulas(compressed)

        assert result["B1"] == "=B2+B3"
        assert result["C1"] == "=C2+C3"
        assert result["D1"] == "=D2+D3"
        assert result["E1"] == "=E2+E3"

    def test_expand_with_regular_formulas(self):
        """Test expanding when there are both ranges and regular formulas."""
        compressed = {
            "B2:B5": "=A2",
            "A1": "=SUM(C:C)",
        }
        result = expand_formulas(compressed)

        assert result["B2"] == "=A2"
        assert result["B3"] == "=A3"
        assert result["B4"] == "=A4"
        assert result["B5"] == "=A5"
        assert result["A1"] == "=SUM(C:C)"

    def test_roundtrip_4_cells(self):
        """Test that compress -> expand produces equivalent formulas (4+ cells)."""
        original = {
            "K4": '=I4&" - "&J4',
            "K5": '=I5&" - "&J5',
            "K6": '=I6&" - "&J6',
            "K7": '=I7&" - "&J7',
            "A1": "=NOW()",
        }

        compressed = compress_formulas(original)
        expanded = expand_formulas(compressed)

        assert expanded == original

    def test_roundtrip_2_cells(self):
        """Test that compress -> expand works for 2 contiguous cells."""
        original = {
            "K4": '=I4&" - "&J4',
            "K5": '=I5&" - "&J5',
            "A1": "=NOW()",
        }

        compressed = compress_formulas(original)
        # Should have K4:K5 as a range
        assert "K4:K5" in compressed
        expanded = expand_formulas(compressed)

        assert expanded == original

    def test_roundtrip_non_contiguous(self):
        """Test that compress -> expand works for non-contiguous cells."""
        original = {
            "K4": '=I4&" - "&J4',
            "K6": '=I6&" - "&J6',
            "A1": "=NOW()",
        }

        compressed = compress_formulas(original)
        expanded = expand_formulas(compressed)

        assert expanded == original
