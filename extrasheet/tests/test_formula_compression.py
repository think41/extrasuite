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
        """Test single formula is not compressed."""
        formulas = {"A1": "=B1+C1"}
        result = compress_formulas(formulas)
        assert result == {"formulas": {"A1": "=B1+C1"}}

    def test_identical_relative_formulas_in_column(self):
        """Test formulas with same pattern in a column are compressed."""
        # These formulas follow the pattern =I{row}&" - "&J{row}
        formulas = {
            "K4": '=I4&" - "&J4',
            "K5": '=I5&" - "&J5',
            "K6": '=I6&" - "&J6',
        }
        result = compress_formulas(formulas)

        assert "formulaPatterns" in result
        assert len(result["formulaPatterns"]) == 1

        pattern = result["formulaPatterns"][0]
        assert pattern["range"] == "K4:K6"
        assert pattern["anchor"] == "K4"
        # Pattern should use placeholders
        assert "{r}" in pattern["pattern"]

        # Should not have individual formulas
        assert "formulas" not in result

    def test_identical_relative_formulas_in_row(self):
        """Test formulas with same pattern in a row are compressed."""
        formulas = {
            "B1": "=B2+B3",
            "C1": "=C2+C3",
            "D1": "=D2+D3",
        }
        result = compress_formulas(formulas)

        assert "formulaPatterns" in result
        assert len(result["formulaPatterns"]) == 1

        pattern = result["formulaPatterns"][0]
        assert pattern["range"] == "B1:D1"

    def test_mixed_formulas(self):
        """Test mix of compressible and non-compressible formulas."""
        formulas = {
            "A1": "=SUM(B:B)",  # Unique formula
            "C2": "=A2+B2",
            "C3": "=A3+B3",
            "C4": "=A4+B4",
        }
        result = compress_formulas(formulas)

        assert "formulaPatterns" in result
        assert "formulas" in result

        # C2:C4 should be compressed
        patterns = result["formulaPatterns"]
        assert any(p.get("range") == "C2:C4" for p in patterns)

        # A1 should remain as individual formula
        assert result["formulas"]["A1"] == "=SUM(B:B)"

    def test_non_contiguous_same_pattern(self):
        """Test non-contiguous cells with same pattern."""
        formulas = {
            "A1": "=B1+C1",
            "A3": "=B3+C3",  # Skip A2
            "A5": "=B5+C5",  # Skip A4
        }
        result = compress_formulas(formulas)

        assert "formulaPatterns" in result
        pattern = result["formulaPatterns"][0]
        # Should list cells individually since not contiguous
        assert "cells" in pattern
        assert set(pattern["cells"]) == {"A1", "A3", "A5"}


class TestExpandFormulas:
    """Tests for expanding compressed formulas."""

    def test_expand_range_pattern(self):
        """Test expanding a range-based pattern."""
        compressed = {
            "formulaPatterns": [
                {
                    "pattern": "={c-2}{r}+{c-1}{r}",
                    "range": "C2:C4",
                    "anchor": "C2",
                }
            ]
        }
        result = expand_formulas(compressed)

        assert result["C2"] == "=A2+B2"
        assert result["C3"] == "=A3+B3"
        assert result["C4"] == "=A4+B4"

    def test_expand_cell_list_pattern(self):
        """Test expanding a cell-list pattern."""
        compressed = {
            "formulaPatterns": [
                {
                    "pattern": "={c-1}{r}*2",
                    "cells": ["B1", "B3", "B5"],
                    "anchor": "B1",
                }
            ]
        }
        result = expand_formulas(compressed)

        assert result["B1"] == "=A1*2"
        assert result["B3"] == "=A3*2"
        assert result["B5"] == "=A5*2"

    def test_expand_with_regular_formulas(self):
        """Test expanding when there are both patterns and regular formulas."""
        compressed = {
            "formulaPatterns": [
                {
                    "pattern": "={c-1}{r}",
                    "range": "B2:B3",
                    "anchor": "B2",
                }
            ],
            "formulas": {
                "A1": "=SUM(C:C)",
            }
        }
        result = expand_formulas(compressed)

        assert result["B2"] == "=A2"
        assert result["B3"] == "=A3"
        assert result["A1"] == "=SUM(C:C)"

    def test_roundtrip(self):
        """Test that compress -> expand produces equivalent formulas."""
        original = {
            "K4": '=I4&" - "&J4',
            "K5": '=I5&" - "&J5',
            "K6": '=I6&" - "&J6',
            "A1": "=NOW()",
        }

        compressed = compress_formulas(original)
        expanded = expand_formulas(compressed)

        assert expanded == original
