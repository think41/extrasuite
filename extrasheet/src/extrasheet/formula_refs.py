"""Formula reference parser for extrasheet.

Extracts cell and range references from formula strings for validation
of structural changes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class CellReference:
    """A reference to a single cell or range in a formula."""

    sheet_name: str | None  # None means same sheet
    start_row: int  # 0-based, -1 for full column (A:A)
    start_col: int  # 0-based, -1 for full row (1:1)
    end_row: int  # 0-based, -1 for full column, same as start for single cell
    end_col: int  # 0-based, -1 for full row, same as start for single cell
    is_row_absolute_start: bool = False  # $A1 vs A1
    is_col_absolute_start: bool = False  # A$1 vs A1
    is_row_absolute_end: bool = False
    is_col_absolute_end: bool = False
    original_text: str = ""  # Original text from formula

    def is_single_cell(self) -> bool:
        """Check if this is a single cell reference (not a range)."""
        return self.start_row == self.end_row and self.start_col == self.end_col

    def is_full_column(self) -> bool:
        """Check if this is a full column reference like A:A."""
        return self.start_row == -1 and self.end_row == -1

    def is_full_row(self) -> bool:
        """Check if this is a full row reference like 1:1."""
        return self.start_col == -1 and self.end_col == -1

    def contains_row(self, row: int) -> bool:
        """Check if this reference contains the given row (0-based)."""
        if self.is_full_column():
            return True  # Full column contains all rows
        if self.is_full_row():
            return self.start_row <= row <= self.end_row
        return self.start_row <= row <= self.end_row

    def contains_column(self, col: int) -> bool:
        """Check if this reference contains the given column (0-based)."""
        if self.is_full_row():
            return True  # Full row contains all columns
        if self.is_full_column():
            return self.start_col <= col <= self.end_col
        return self.start_col <= col <= self.end_col

    def contains_cell(self, row: int, col: int) -> bool:
        """Check if this reference contains the given cell (0-based)."""
        return self.contains_row(row) and self.contains_column(col)


@dataclass
class FormulaParseResult:
    """Result of parsing a formula for references."""

    references: list[CellReference] = field(default_factory=list)
    has_indirect: bool = False  # Contains INDIRECT() - can't statically analyze
    has_offset: bool = False  # Contains OFFSET() - can't statically analyze
    has_index: bool = False  # Contains INDEX() - can't statically analyze
    parse_errors: list[str] = field(default_factory=list)

    def has_dynamic_references(self) -> bool:
        """Check if formula has references we can't statically analyze."""
        return self.has_indirect or self.has_offset or self.has_index

    def references_row(self, row: int, sheet_name: str | None = None) -> bool:
        """Check if any reference in this formula references the given row."""
        for ref in self.references:
            # Check sheet match (None means same sheet)
            if sheet_name is not None and ref.sheet_name is not None:
                if ref.sheet_name != sheet_name:
                    continue
            elif sheet_name is not None and ref.sheet_name is None:
                # ref is on same sheet, but we're checking a specific sheet
                continue
            elif sheet_name is None and ref.sheet_name is not None:
                # ref is on different sheet, we're checking same sheet
                continue

            if ref.contains_row(row):
                return True
        return False

    def references_column(self, col: int, sheet_name: str | None = None) -> bool:
        """Check if any reference in this formula references the given column."""
        for ref in self.references:
            # Check sheet match
            if sheet_name is not None and ref.sheet_name is not None:
                if ref.sheet_name != sheet_name:
                    continue
            elif (sheet_name is not None and ref.sheet_name is None) or (
                sheet_name is None and ref.sheet_name is not None
            ):
                continue

            if ref.contains_column(col):
                return True
        return False

    def references_sheet(self, sheet_name: str) -> bool:
        """Check if any reference in this formula references the given sheet."""
        return any(ref.sheet_name == sheet_name for ref in self.references)


# Regex patterns for parsing

# Column letter pattern (A-Z, AA-ZZ, etc.)
_COL_PATTERN = r"[A-Za-z]+"
# Row number pattern
_ROW_PATTERN = r"[0-9]+"

# Single cell reference: A1, $A1, A$1, $A$1
_CELL_PATTERN = rf"(\$?)({_COL_PATTERN})(\$?)({_ROW_PATTERN})"

# Full column reference: A:A, A:B, $A:$B
_FULL_COL_PATTERN = rf"(\$?)({_COL_PATTERN}):(\$?)({_COL_PATTERN})"

# Full row reference: 1:1, 1:10, $1:$10
_FULL_ROW_PATTERN = rf"(\$?)({_ROW_PATTERN}):(\$?)({_ROW_PATTERN})"

# Range reference: A1:B10, $A$1:$B$10
_RANGE_PATTERN = rf"{_CELL_PATTERN}:{_CELL_PATTERN}"

# Sheet name patterns
# Unquoted: Sheet1!A1
_UNQUOTED_SHEET = r"([A-Za-z_][A-Za-z0-9_]*)"
# Quoted: 'Sheet Name'!A1 or 'Sheet''s Name'!A1 (escaped quotes)
_QUOTED_SHEET = r"'((?:[^']|'')*)'"

# Combined sheet prefix
_SHEET_PREFIX = rf"(?:{_QUOTED_SHEET}|{_UNQUOTED_SHEET})!"

# Dynamic function patterns (case insensitive)
_INDIRECT_PATTERN = re.compile(r"\bINDIRECT\s*\(", re.IGNORECASE)
_OFFSET_PATTERN = re.compile(r"\bOFFSET\s*\(", re.IGNORECASE)
_INDEX_PATTERN = re.compile(r"\bINDEX\s*\(", re.IGNORECASE)


def _letter_to_col_index(letter: str) -> int:
    """Convert column letter(s) to 0-based index."""
    result = 0
    for char in letter.upper():
        result = result * 26 + (ord(char) - ord("A") + 1)
    return result - 1


def _parse_cell_ref(
    col_abs: str, col: str, row_abs: str, row: str
) -> tuple[int, int, bool, bool]:
    """Parse a single cell reference into (row, col, row_absolute, col_absolute)."""
    col_idx = _letter_to_col_index(col)
    row_idx = int(row) - 1  # Convert to 0-based
    return row_idx, col_idx, bool(row_abs), bool(col_abs)


def parse_formula(formula: str) -> FormulaParseResult:
    """Parse a formula string and extract all cell/range references.

    Args:
        formula: Formula string (with or without leading =)

    Returns:
        FormulaParseResult containing all extracted references and flags
        for dynamic references (INDIRECT, OFFSET, INDEX).
    """
    result = FormulaParseResult()

    # Check for dynamic reference functions
    result.has_indirect = bool(_INDIRECT_PATTERN.search(formula))
    result.has_offset = bool(_OFFSET_PATTERN.search(formula))
    result.has_index = bool(_INDEX_PATTERN.search(formula))

    # Remove string literals to avoid false matches
    # Replace "string" with placeholder of same length
    formula_clean = re.sub(r'"[^"]*"', lambda m: " " * len(m.group(0)), formula)

    # Track which character positions are already part of a matched reference
    # to avoid matching B10 separately when A1:B10 was already matched
    matched_chars: set[int] = set()

    def is_position_free(start: int, end: int) -> bool:
        """Check if all positions in range are not yet matched."""
        return not any(i in matched_chars for i in range(start, end))

    def mark_positions(start: int, end: int) -> None:
        """Mark positions as matched."""
        for i in range(start, end):
            matched_chars.add(i)

    # Pattern 1: Sheet!Range (e.g., Sheet1!A1:B10, 'Sheet Name'!A1)
    # Match sheet prefix followed by range, cell, full column, or full row
    sheet_range_pattern = rf"({_QUOTED_SHEET}|{_UNQUOTED_SHEET})!(\$?{_COL_PATTERN}\$?{_ROW_PATTERN}:\$?{_COL_PATTERN}\$?{_ROW_PATTERN}|\$?{_COL_PATTERN}\$?{_ROW_PATTERN}|\$?{_COL_PATTERN}:\$?{_COL_PATTERN}|\$?{_ROW_PATTERN}:\$?{_ROW_PATTERN})"

    for match in re.finditer(sheet_range_pattern, formula_clean):
        if not is_position_free(match.start(), match.end()):
            continue
        mark_positions(match.start(), match.end())

        # Extract sheet name (quoted or unquoted)
        sheet_part = match.group(1)
        if sheet_part.startswith("'"):
            # Quoted sheet name - remove quotes and unescape
            sheet_name = sheet_part[1:-1].replace("''", "'")
        else:
            sheet_name = sheet_part

        ref_text = match.group(3) if match.lastindex and match.lastindex >= 3 else ""
        # Actually, we need to find where the ref_text is
        full_match = match.group(0)
        excl_pos = full_match.find("!")
        if excl_pos >= 0:
            ref_text = full_match[excl_pos + 1 :]

        ref = _parse_reference(ref_text, sheet_name, full_match)
        if ref:
            result.references.append(ref)

    # Pattern 2: Range without sheet (A1:B10)
    # Must not be preceded by ! (which would indicate sheet prefix)
    range_only_pattern = rf"(?<![!])(\$?{_COL_PATTERN}\$?{_ROW_PATTERN}:\$?{_COL_PATTERN}\$?{_ROW_PATTERN})(?![A-Za-z0-9])"

    for match in re.finditer(range_only_pattern, formula_clean):
        if not is_position_free(match.start(), match.end()):
            continue
        mark_positions(match.start(), match.end())

        ref = _parse_reference(match.group(1), None, match.group(1))
        if ref:
            result.references.append(ref)

    # Pattern 3: Full column without sheet (A:A, A:B)
    full_col_only_pattern = (
        rf"(?<![A-Za-z0-9_!])(\$?{_COL_PATTERN}:\$?{_COL_PATTERN})(?![A-Za-z0-9])"
    )

    for match in re.finditer(full_col_only_pattern, formula_clean):
        if not is_position_free(match.start(), match.end()):
            continue
        mark_positions(match.start(), match.end())

        ref = _parse_full_column_ref(match.group(1), None, match.group(1))
        if ref:
            result.references.append(ref)

    # Pattern 4: Full row without sheet (1:1, 1:10)
    full_row_only_pattern = (
        rf"(?<![A-Za-z0-9_!])(\$?{_ROW_PATTERN}:\$?{_ROW_PATTERN})(?![A-Za-z0-9])"
    )

    for match in re.finditer(full_row_only_pattern, formula_clean):
        if not is_position_free(match.start(), match.end()):
            continue
        mark_positions(match.start(), match.end())

        ref = _parse_full_row_ref(match.group(1), None, match.group(1))
        if ref:
            result.references.append(ref)

    # Pattern 5: Single cell without sheet (A1, $A$1)
    # Must not be preceded by ! or followed by :
    cell_only_pattern = (
        rf"(?<![A-Za-z0-9_!])(\$?{_COL_PATTERN}\$?{_ROW_PATTERN})(?![A-Za-z0-9:])"
    )

    for match in re.finditer(cell_only_pattern, formula_clean):
        if not is_position_free(match.start(), match.end()):
            continue
        mark_positions(match.start(), match.end())

        ref = _parse_single_cell_ref(match.group(1), None, match.group(1))
        if ref:
            result.references.append(ref)

    return result


def _parse_reference(
    ref_text: str, sheet_name: str | None, original: str
) -> CellReference | None:
    """Parse a reference string (without sheet prefix) into a CellReference."""
    if ":" in ref_text:
        # Could be range (A1:B10), full column (A:B), or full row (1:10)
        parts = ref_text.split(":")
        if len(parts) != 2:
            return None

        left, right = parts

        # Check if it's a full column reference (A:B)
        if re.match(rf"^(\$?)({_COL_PATTERN})$", left) and re.match(
            rf"^(\$?)({_COL_PATTERN})$", right
        ):
            return _parse_full_column_ref(ref_text, sheet_name, original)

        # Check if it's a full row reference (1:10)
        if re.match(rf"^(\$?)({_ROW_PATTERN})$", left) and re.match(
            rf"^(\$?)({_ROW_PATTERN})$", right
        ):
            return _parse_full_row_ref(ref_text, sheet_name, original)

        # Otherwise it's a cell range (A1:B10)
        return _parse_cell_range_ref(ref_text, sheet_name, original)
    else:
        # Single cell
        return _parse_single_cell_ref(ref_text, sheet_name, original)


def _parse_single_cell_ref(
    ref_text: str, sheet_name: str | None, original: str
) -> CellReference | None:
    """Parse a single cell reference like A1 or $A$1."""
    match = re.match(rf"^{_CELL_PATTERN}$", ref_text)
    if not match:
        return None

    col_abs, col, row_abs, row = match.groups()
    row_idx, col_idx, is_row_abs, is_col_abs = _parse_cell_ref(
        col_abs, col, row_abs, row
    )

    return CellReference(
        sheet_name=sheet_name,
        start_row=row_idx,
        start_col=col_idx,
        end_row=row_idx,
        end_col=col_idx,
        is_row_absolute_start=is_row_abs,
        is_col_absolute_start=is_col_abs,
        is_row_absolute_end=is_row_abs,
        is_col_absolute_end=is_col_abs,
        original_text=original,
    )


def _parse_cell_range_ref(
    ref_text: str, sheet_name: str | None, original: str
) -> CellReference | None:
    """Parse a cell range reference like A1:B10."""
    match = re.match(rf"^{_RANGE_PATTERN}$", ref_text)
    if not match:
        return None

    (
        col_abs1,
        col1,
        row_abs1,
        row1,
        col_abs2,
        col2,
        row_abs2,
        row2,
    ) = match.groups()

    row_idx1, col_idx1, is_row_abs1, is_col_abs1 = _parse_cell_ref(
        col_abs1, col1, row_abs1, row1
    )
    row_idx2, col_idx2, is_row_abs2, is_col_abs2 = _parse_cell_ref(
        col_abs2, col2, row_abs2, row2
    )

    return CellReference(
        sheet_name=sheet_name,
        start_row=min(row_idx1, row_idx2),
        start_col=min(col_idx1, col_idx2),
        end_row=max(row_idx1, row_idx2),
        end_col=max(col_idx1, col_idx2),
        is_row_absolute_start=is_row_abs1,
        is_col_absolute_start=is_col_abs1,
        is_row_absolute_end=is_row_abs2,
        is_col_absolute_end=is_col_abs2,
        original_text=original,
    )


def _parse_full_column_ref(
    ref_text: str, sheet_name: str | None, original: str
) -> CellReference | None:
    """Parse a full column reference like A:A or A:B."""
    match = re.match(rf"^{_FULL_COL_PATTERN}$", ref_text)
    if not match:
        return None

    col_abs1, col1, col_abs2, col2 = match.groups()
    col_idx1 = _letter_to_col_index(col1)
    col_idx2 = _letter_to_col_index(col2)

    return CellReference(
        sheet_name=sheet_name,
        start_row=-1,  # Full column
        start_col=min(col_idx1, col_idx2),
        end_row=-1,  # Full column
        end_col=max(col_idx1, col_idx2),
        is_row_absolute_start=False,
        is_col_absolute_start=bool(col_abs1),
        is_row_absolute_end=False,
        is_col_absolute_end=bool(col_abs2),
        original_text=original,
    )


def _parse_full_row_ref(
    ref_text: str, sheet_name: str | None, original: str
) -> CellReference | None:
    """Parse a full row reference like 1:1 or 1:10."""
    match = re.match(rf"^{_FULL_ROW_PATTERN}$", ref_text)
    if not match:
        return None

    row_abs1, row1, row_abs2, row2 = match.groups()
    row_idx1 = int(row1) - 1
    row_idx2 = int(row2) - 1

    return CellReference(
        sheet_name=sheet_name,
        start_row=min(row_idx1, row_idx2),
        start_col=-1,  # Full row
        end_row=max(row_idx1, row_idx2),
        end_col=-1,  # Full row
        is_row_absolute_start=bool(row_abs1),
        is_col_absolute_start=False,
        is_row_absolute_end=bool(row_abs2),
        is_col_absolute_end=False,
        original_text=original,
    )


def collect_all_references(
    formulas: dict[str, dict[str, str]],
) -> dict[str, list[FormulaParseResult]]:
    """Collect all formula references from all sheets.

    Args:
        formulas: Dict mapping sheet_name -> {cell_ref -> formula}

    Returns:
        Dict mapping sheet_name -> list of FormulaParseResult
    """
    result: dict[str, list[FormulaParseResult]] = {}

    for sheet_name, sheet_formulas in formulas.items():
        result[sheet_name] = []
        for _cell_ref, formula in sheet_formulas.items():
            parsed = parse_formula(formula)
            result[sheet_name].append(parsed)

    return result
