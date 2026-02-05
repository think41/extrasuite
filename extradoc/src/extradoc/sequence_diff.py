"""Sequence diffing for document elements using LCS algorithm.

This module provides the core diffing infrastructure for comparing
document sections element-by-element using Python's SequenceMatcher.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import TYPE_CHECKING, Any

from .desugar import Paragraph, SpecialElement, Table
from .indexer import utf16_len

if TYPE_CHECKING:
    from .desugar import TableCell

Element = Any  # Paragraph | Table | SpecialElement


@dataclass
class DiffChange:
    """Represents a single change in a sequence diff."""

    type: str  # "equal", "insert", "delete", "replace"
    pristine_elements: list[Element]  # Elements from pristine (for delete/replace)
    current_elements: list[Element]  # Elements from current (for insert/replace)
    pristine_start: int  # Start index in pristine document
    pristine_end: int  # End index in pristine document
    current_start: int  # Start index in current document
    current_end: int  # End index in current document


def element_signature(elem: Element) -> str:
    """Create a hashable signature for matching elements.

    Elements with the same signature are considered "equal" for the purposes
    of sequence alignment. The signature captures the semantic identity of
    an element but not necessarily all details.

    For paragraphs: includes style, bullet type, and text content
    For tables: includes dimensions
    For special elements: includes type
    """
    if isinstance(elem, Paragraph):
        # Include named style, bullet type, and text content
        return f"P:{elem.named_style}:{elem.bullet_type}:{elem.text_content()}"
    if isinstance(elem, Table):
        # Include dimensions - structure identity
        return f"T:{elem.rows}x{elem.cols}"
    if isinstance(elem, SpecialElement):
        # Include type and key attributes
        attrs = elem.attributes.copy()
        # Remove transient attributes
        for key in ["id", "num"]:
            attrs.pop(key, None)
        attr_str = ",".join(f"{k}={v}" for k, v in sorted(attrs.items()))
        return f"S:{elem.element_type}:{attr_str}"
    return f"U:{type(elem).__name__}"


def elements_match(p_elem: Element, c_elem: Element) -> bool:
    """Check if two elements are structurally equivalent (same content).

    This is a deeper comparison than element_signature - it checks if
    two elements are completely identical including all details.
    """
    # Different types never match
    if not isinstance(p_elem, type(c_elem)):
        return False

    if isinstance(p_elem, Paragraph) and isinstance(c_elem, Paragraph):
        return _paragraphs_match(p_elem, c_elem)

    if isinstance(p_elem, Table) and isinstance(c_elem, Table):
        return _tables_match(p_elem, c_elem)

    if isinstance(p_elem, SpecialElement) and isinstance(c_elem, SpecialElement):
        return _specials_match(p_elem, c_elem)

    return False


def _paragraphs_match(p: Paragraph, c: Paragraph) -> bool:
    """Check if two paragraphs are identical."""
    # Check high-level properties
    if p.named_style != c.named_style:
        return False
    if p.bullet_type != c.bullet_type:
        return False
    if p.bullet_level != c.bullet_level:
        return False

    # Check text content
    if p.text_content() != c.text_content():
        return False

    # Check runs (text styling)
    if len(p.runs) != len(c.runs):
        return False

    for p_run, c_run in zip(p.runs, c.runs, strict=False):
        if p_run.text != c_run.text:
            return False
        # Compare styles excluding transient keys
        p_styles = {k: v for k, v in p_run.styles.items() if not k.startswith("_")}
        c_styles = {k: v for k, v in c_run.styles.items() if not k.startswith("_")}
        if p_styles != c_styles:
            return False

    return True


def _tables_match(p: Table, c: Table) -> bool:
    """Check if two tables are identical."""
    if p.rows != c.rows or p.cols != c.cols:
        return False

    # Build cell maps
    p_cells = {(cell.row, cell.col): cell for cell in p.cells}
    c_cells = {(cell.row, cell.col): cell for cell in c.cells}

    if set(p_cells.keys()) != set(c_cells.keys()):
        return False

    return all(_cells_match(p_cells[pos], c_cells[pos]) for pos in p_cells)


def _cells_match(p: TableCell, c: TableCell) -> bool:
    """Check if two table cells are identical."""
    if p.colspan != c.colspan or p.rowspan != c.rowspan:
        return False

    if len(p.content) != len(c.content):
        return False

    for p_elem, c_elem in zip(p.content, c.content, strict=False):
        if not elements_match(p_elem, c_elem):
            return False

    return True


def _specials_match(p: SpecialElement, c: SpecialElement) -> bool:
    """Check if two special elements are identical."""
    if p.element_type != c.element_type:
        return False

    # Compare attributes, excluding transient ones
    p_attrs = {k: v for k, v in p.attributes.items() if k not in ("id", "num")}
    c_attrs = {k: v for k, v in c.attributes.items() if k not in ("id", "num")}

    return p_attrs == c_attrs


def sequence_diff(
    pristine: list[tuple[Element, int, int]],  # (element, start_idx, end_idx)
    current: list[tuple[Element, int, int]],
) -> list[DiffChange]:
    """Find changes between two element sequences.

    Uses Python's SequenceMatcher with element signatures to identify
    matching elements, then categorizes changes as equal, insert, delete,
    or replace.

    Args:
        pristine: List of (element, start_index, end_index) tuples from pristine
        current: List of (element, start_index, end_index) tuples from current

    Returns:
        List of DiffChange objects describing the changes
    """
    # Build signature sequences for matching
    p_sigs = [element_signature(elem) for elem, _, _ in pristine]
    c_sigs = [element_signature(elem) for elem, _, _ in current]

    matcher = SequenceMatcher(isjunk=None, a=p_sigs, b=c_sigs, autojunk=False)

    changes: list[DiffChange] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        # Calculate index ranges
        p_start = (
            pristine[i1][1]
            if i1 < len(pristine)
            else (pristine[-1][2] if pristine else 0)
        )
        p_end = pristine[i2 - 1][2] if i2 > 0 and i1 < len(pristine) else p_start
        c_start = (
            current[j1][1] if j1 < len(current) else (current[-1][2] if current else 0)
        )
        c_end = current[j2 - 1][2] if j2 > 0 and j1 < len(current) else c_start

        change = DiffChange(
            type=tag,
            pristine_elements=[pristine[i][0] for i in range(i1, i2)],
            current_elements=[current[j][0] for j in range(j1, j2)],
            pristine_start=p_start,
            pristine_end=p_end,
            current_start=c_start,
            current_end=c_end,
        )
        changes.append(change)

    return changes


def diff_text(pristine: str, current: str) -> list[tuple[str, int, int, str]]:
    """Diff two strings at character level.

    Returns a list of operations to transform pristine into current.
    Each operation is (type, start_idx, end_idx, text):
    - ("delete", start, end, "") - delete characters from start to end
    - ("insert", idx, idx, text) - insert text at idx
    - ("equal", start, end, text) - no change needed

    Operations are returned in document order (not reverse order).
    """
    matcher = SequenceMatcher(isjunk=None, a=pristine, b=current, autojunk=False)

    operations: list[tuple[str, int, int, str]] = []

    # Track position in pristine using UTF-16 code units
    p_utf16_pos = 0

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        # Calculate UTF-16 lengths for this segment
        p_segment = pristine[i1:i2]
        c_segment = current[j1:j2]
        p_len = utf16_len(p_segment)

        if tag == "equal":
            operations.append(("equal", p_utf16_pos, p_utf16_pos + p_len, p_segment))
        elif tag == "delete":
            operations.append(("delete", p_utf16_pos, p_utf16_pos + p_len, ""))
        elif tag == "insert":
            operations.append(("insert", p_utf16_pos, p_utf16_pos, c_segment))
        elif tag == "replace":
            # Replace = delete old + insert new
            operations.append(("delete", p_utf16_pos, p_utf16_pos + p_len, ""))
            operations.append(("insert", p_utf16_pos, p_utf16_pos, c_segment))

        # Advance pristine position only for segments that existed in pristine
        if tag in ("equal", "delete", "replace"):
            p_utf16_pos += p_len

    return operations


def sections_are_identical(
    pristine_content: list[Element],
    current_content: list[Element],
) -> bool:
    """Fast path: check if two sections have identical content.

    Returns True if all elements match exactly, False otherwise.
    """
    if len(pristine_content) != len(current_content):
        return False

    for p_elem, c_elem in zip(pristine_content, current_content, strict=False):
        if not elements_match(p_elem, c_elem):
            return False

    return True
