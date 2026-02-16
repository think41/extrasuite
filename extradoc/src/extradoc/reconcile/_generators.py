"""Generate batchUpdate request dicts from aligned StructuralElements.

Uses a gap-based approach:
1. Identify MATCHED elements as anchors
2. Group consecutive non-MATCHED elements into "gaps"
3. Process each gap: delete old content, insert new content
4. Process gaps right-to-left so indices remain valid

Additionally, MATCHED table pairs are diffed at the cell level
and interleaved with gap operations by position (right-to-left).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from extradoc.indexer import utf16_len
from extradoc.reconcile._alignment import AlignedElement, AlignmentOp, align_sequences
from extradoc.reconcile._extractors import (
    column_fingerprint,
    extract_plain_text_from_paragraph,
    extract_plain_text_from_table,
    row_fingerprint,
)

if TYPE_CHECKING:
    from extradoc.api_types._generated import (
        StructuralElement,
        Table,
        TableCell,
        TableRow,
    )


@dataclass
class _Gap:
    """A gap between MATCHED elements containing DELETEs and ADDs."""

    deletes: list[AlignedElement] = field(default_factory=list)
    adds: list[AlignedElement] = field(default_factory=list)
    left_anchor: StructuralElement | None = None  # MATCHED element to the left
    right_anchor: StructuralElement | None = None  # MATCHED element to the right
    is_trailing: bool = False  # True if this is the last gap (no right anchor)


# ---------------------------------------------------------------------------
# Request dict helpers
# ---------------------------------------------------------------------------


def _make_location(
    index: int, segment_id: str | None, tab_id: str | None
) -> dict[str, Any]:
    loc: dict[str, Any] = {"index": index}
    if segment_id:
        loc["segmentId"] = segment_id
    if tab_id:
        loc["tabId"] = tab_id
    return loc


def _make_range(
    start: int, end: int, segment_id: str | None, tab_id: str | None
) -> dict[str, Any]:
    r: dict[str, Any] = {"startIndex": start, "endIndex": end}
    if segment_id:
        r["segmentId"] = segment_id
    if tab_id:
        r["tabId"] = tab_id
    return r


def _make_delete_range(
    start: int, end: int, segment_id: str | None, tab_id: str | None
) -> dict[str, Any]:
    return {
        "deleteContentRange": {"range": _make_range(start, end, segment_id, tab_id)}
    }


def _make_insert_text(
    text: str, index: int, segment_id: str | None, tab_id: str | None
) -> dict[str, Any]:
    return {
        "insertText": {
            "text": text,
            "location": _make_location(index, segment_id, tab_id),
        }
    }


def _make_insert_table(
    rows: int,
    columns: int,
    index: int,
    segment_id: str | None,
    tab_id: str | None,
) -> dict[str, Any]:
    return {
        "insertTable": {
            "rows": rows,
            "columns": columns,
            "location": _make_location(index, segment_id, tab_id),
        }
    }


def _make_table_cell_location(
    table_start: int,
    row_index: int,
    col_index: int,
    segment_id: str | None,
    tab_id: str | None,
) -> dict[str, Any]:
    loc: dict[str, Any] = {"index": table_start}
    if segment_id:
        loc["segmentId"] = segment_id
    if tab_id:
        loc["tabId"] = tab_id
    return {
        "tableStartLocation": loc,
        "rowIndex": row_index,
        "columnIndex": col_index,
    }


# ---------------------------------------------------------------------------
# Element helpers
# ---------------------------------------------------------------------------


def _is_section_break(se: StructuralElement) -> bool:
    return se.section_break is not None


def _is_table(se: StructuralElement) -> bool:
    return se.table is not None


def _is_paragraph(se: StructuralElement) -> bool:
    return se.paragraph is not None


def _el_start(se: StructuralElement) -> int:
    return se.start_index if se.start_index is not None else 0


def _el_end(se: StructuralElement) -> int:
    return se.end_index if se.end_index is not None else 0


def _para_text(se: StructuralElement) -> str:
    """Get plain text from a paragraph StructuralElement."""
    if se.paragraph:
        return extract_plain_text_from_paragraph(se.paragraph)
    return ""


def _cell_text(cell: TableCell) -> str:
    """Get plain text from a table cell."""
    parts: list[str] = []
    for se in cell.content or []:
        if se.paragraph:
            parts.append(extract_plain_text_from_paragraph(se.paragraph))
    return "".join(parts)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def generate_requests(
    alignment: list[AlignedElement],
    segment_id: str | None,
    tab_id: str | None,
) -> list[dict[str, Any]]:
    """Generate batchUpdate requests from an alignment.

    Handles both gap-based operations (add/delete structural elements)
    and matched table diffs (cell content changes).
    All operations are processed right-to-left by base index position.
    """
    # Collect gap operations with their positions
    operations: list[tuple[int, list[dict[str, Any]]]] = []

    gaps = _identify_gaps(alignment)
    for gap in gaps:
        pos = _gap_position(gap)
        if gap.is_trailing:
            reqs = _process_trailing_gap(gap, segment_id, tab_id)
        else:
            reqs = _process_inner_gap(gap, segment_id, tab_id)
        if reqs:
            operations.append((pos, reqs))

    # Collect matched table diff operations
    for aligned in alignment:
        if aligned.op != AlignmentOp.MATCHED:
            continue
        base_el = aligned.base_element
        desired_el = aligned.desired_element
        if not base_el or not desired_el:
            continue
        if not _is_table(base_el) or not _is_table(desired_el):
            continue
        assert base_el.table is not None
        assert desired_el.table is not None

        reqs = _generate_table_diff(base_el, desired_el, segment_id, tab_id)
        if reqs:
            operations.append((_el_end(base_el) - 1, reqs))

    # Sort by position descending (right-to-left processing)
    operations.sort(key=lambda x: x[0], reverse=True)

    # Flatten
    result: list[dict[str, Any]] = []
    for _, reqs in operations:
        result.extend(reqs)
    return result


# ---------------------------------------------------------------------------
# Gap identification
# ---------------------------------------------------------------------------


def _gap_position(gap: _Gap) -> int:
    """Return the base index position of a gap for sorting."""
    if gap.right_anchor:
        return _el_start(gap.right_anchor)
    # Trailing gap: use first deleted element or left anchor
    if gap.deletes and gap.deletes[0].base_element:
        return _el_start(gap.deletes[0].base_element)
    if gap.left_anchor:
        return _el_end(gap.left_anchor)
    return 0


def _identify_gaps(alignment: list[AlignedElement]) -> list[_Gap]:
    """Split alignment into gaps between MATCHED elements."""
    gaps: list[_Gap] = []
    current_gap = _Gap()
    last_matched: StructuralElement | None = None

    for aligned in alignment:
        if aligned.op == AlignmentOp.MATCHED:
            # Close current gap if it has content
            if current_gap.deletes or current_gap.adds:
                current_gap.left_anchor = last_matched
                current_gap.right_anchor = aligned.base_element
                gaps.append(current_gap)
                current_gap = _Gap()
            last_matched = aligned.base_element
        elif aligned.op == AlignmentOp.DELETED:
            current_gap.deletes.append(aligned)
        elif aligned.op == AlignmentOp.ADDED:
            current_gap.adds.append(aligned)

    # Trailing gap
    if current_gap.deletes or current_gap.adds:
        current_gap.left_anchor = last_matched
        current_gap.right_anchor = None
        current_gap.is_trailing = True
        gaps.append(current_gap)

    return gaps


def _filter_section_breaks(
    gap: _Gap,
) -> tuple[list[AlignedElement], list[AlignedElement]]:
    """Filter section breaks from deletes and adds, returning (real_deletes, real_adds)."""
    real_deletes = [
        a
        for a in gap.deletes
        if a.base_element and not _is_section_break(a.base_element)
    ]
    real_adds = [
        a
        for a in gap.adds
        if a.desired_element and not _is_section_break(a.desired_element)
    ]
    return real_deletes, real_adds


# ---------------------------------------------------------------------------
# Gap processing — inner gap
# ---------------------------------------------------------------------------


def _process_inner_gap(
    gap: _Gap, segment_id: str | None, tab_id: str | None
) -> list[dict[str, Any]]:
    """Process a non-trailing gap (has a right anchor)."""
    requests: list[dict[str, Any]] = []
    real_deletes, real_adds = _filter_section_breaks(gap)

    if not real_deletes and not real_adds:
        return []

    first_del_el = real_deletes[0].base_element if real_deletes else None
    last_del_el = real_deletes[-1].base_element if real_deletes else None

    # When the right anchor is a table, we cannot delete up to the table
    # start (the API forbids deleting the \n before a table without also
    # deleting the table).  Trim the delete to preserve the \n.
    right_is_table = gap.right_anchor is not None and _is_table(gap.right_anchor)

    # --- DELETE phase ---
    if real_deletes:
        assert first_del_el is not None
        assert last_del_el is not None
        delete_start = _el_start(first_del_el)
        delete_end = _el_end(last_del_el)
        if right_is_table:
            delete_end = delete_end - 1  # protect \n before table
        if delete_start < delete_end:
            requests.append(
                _make_delete_range(delete_start, delete_end, segment_id, tab_id)
            )

    # --- INSERT phase ---
    if real_adds:
        has_tables = any(
            a.desired_element and _is_table(a.desired_element) for a in real_adds
        )

        if real_deletes:
            assert first_del_el is not None
            insert_idx = _el_start(first_del_el)
        elif has_tables and gap.left_anchor and not _is_section_break(gap.left_anchor):
            # For table inserts, use left anchor's \n to avoid creating
            # an extra empty paragraph (insertTable splits at the index)
            insert_idx = _el_end(gap.left_anchor) - 1
        elif gap.right_anchor:
            insert_idx = _el_start(gap.right_anchor)
        else:
            insert_idx = 1

        if has_tables:
            # Process each add individually in reverse order at insert_idx
            requests.extend(
                _insert_adds_individually(real_adds, insert_idx, segment_id, tab_id)
            )
        else:
            # Pure paragraph adds — concatenate text (original Phase 1 logic)
            combined_text = _collect_add_text(real_adds)
            if right_is_table:
                # The \n before the table is preserved, so strip trailing \n
                combined_text = combined_text.rstrip("\n")
            if combined_text:
                requests.append(
                    _make_insert_text(combined_text, insert_idx, segment_id, tab_id)
                )

    return requests


# ---------------------------------------------------------------------------
# Gap processing — trailing gap
# ---------------------------------------------------------------------------


def _process_trailing_gap(
    gap: _Gap, segment_id: str | None, tab_id: str | None
) -> list[dict[str, Any]]:
    """Process a trailing gap (no right anchor). Must protect segment-final \\n."""
    requests: list[dict[str, Any]] = []
    real_deletes, real_adds = _filter_section_breaks(gap)

    if not real_deletes and not real_adds:
        return []

    first_del_el = real_deletes[0].base_element if real_deletes else None
    last_del_el = real_deletes[-1].base_element if real_deletes else None

    # --- DELETE phase ---
    if real_deletes:
        assert first_del_el is not None
        assert last_del_el is not None
        delete_start = _el_start(first_del_el)
        delete_end = _el_end(last_del_el)

        if gap.left_anchor and not _is_section_break(gap.left_anchor):
            left_end = _el_end(gap.left_anchor)
            del_start = left_end - 1  # eat into preceding \n
            del_end = delete_end - 1  # protect segment-final \n
            if del_start < del_end:
                requests.append(
                    _make_delete_range(del_start, del_end, segment_id, tab_id)
                )
        else:
            del_end = delete_end - 1
            if delete_start < del_end:
                requests.append(
                    _make_delete_range(delete_start, del_end, segment_id, tab_id)
                )

    # --- INSERT phase ---
    if real_adds:
        has_tables = any(
            a.desired_element and _is_table(a.desired_element) for a in real_adds
        )

        if has_tables:
            requests.extend(
                _process_trailing_adds_with_tables(
                    gap, real_deletes, real_adds, segment_id, tab_id
                )
            )
        else:
            # Pure paragraph adds (original Phase 1 logic)
            requests.extend(
                _process_trailing_paragraph_adds(
                    gap, real_deletes, real_adds, segment_id, tab_id
                )
            )

    return requests


def _process_trailing_paragraph_adds(
    gap: _Gap,
    real_deletes: list[AlignedElement],
    real_adds: list[AlignedElement],
    segment_id: str | None,
    tab_id: str | None,
) -> list[dict[str, Any]]:
    """Handle pure paragraph adds in a trailing gap (Phase 1 logic)."""
    first_del_el = real_deletes[0].base_element if real_deletes else None

    combined_text = _collect_add_text(real_adds)
    if not combined_text:
        return []

    if real_deletes:
        if gap.left_anchor and not _is_section_break(gap.left_anchor):
            insert_idx = _el_end(gap.left_anchor) - 1
        else:
            assert first_del_el is not None
            insert_idx = _el_start(first_del_el)
    else:
        if gap.left_anchor and not _is_section_break(gap.left_anchor):
            insert_idx = _el_end(gap.left_anchor) - 1
        else:
            insert_idx = _el_end(gap.left_anchor) if gap.left_anchor else 1

    if gap.left_anchor and not _is_section_break(gap.left_anchor):
        text_stripped = combined_text.rstrip("\n")
        insert_text = "\n" + text_stripped
    else:
        insert_text = combined_text.rstrip("\n")

    if insert_text:
        return [_make_insert_text(insert_text, insert_idx, segment_id, tab_id)]
    return []


def _process_trailing_adds_with_tables(
    gap: _Gap,
    real_deletes: list[AlignedElement],
    real_adds: list[AlignedElement],
    segment_id: str | None,
    tab_id: str | None,
) -> list[dict[str, Any]]:
    """Handle adds containing tables in a trailing gap.

    Tables in trailing position need special handling because
    insertTable automatically creates a trailing paragraph.
    """
    first_del_el = real_deletes[0].base_element if real_deletes else None

    # Determine insert position
    if real_deletes:
        if gap.left_anchor and not _is_section_break(gap.left_anchor):
            insert_idx = _el_end(gap.left_anchor) - 1
        else:
            assert first_del_el is not None
            insert_idx = _el_start(first_del_el)
    else:
        if gap.left_anchor and not _is_section_break(gap.left_anchor):
            insert_idx = _el_end(gap.left_anchor) - 1
        else:
            insert_idx = _el_end(gap.left_anchor) if gap.left_anchor else 1

    # Filter out trailing empty paragraphs that insertTable creates implicitly
    filtered_adds = _filter_trailing_empty_paras(real_adds)

    # Process each add in reverse at insert_idx
    requests: list[dict[str, Any]] = []
    for add in reversed(filtered_adds):
        el = add.desired_element
        assert el is not None
        if _is_table(el):
            assert el.table is not None
            table_reqs = _generate_insert_table_with_content(
                el.table, insert_idx, segment_id, tab_id
            )
            requests.extend(table_reqs)
        elif _is_paragraph(el):
            text = _para_text(el)
            if text and text != "\n":
                # For trailing gap with left anchor paragraph, prepend \n
                if gap.left_anchor and not _is_section_break(gap.left_anchor):
                    text_stripped = text.rstrip("\n")
                    if text_stripped:
                        requests.append(
                            _make_insert_text(
                                "\n" + text_stripped, insert_idx, segment_id, tab_id
                            )
                        )
                else:
                    text_stripped = text.rstrip("\n")
                    if text_stripped:
                        requests.append(
                            _make_insert_text(
                                text_stripped, insert_idx, segment_id, tab_id
                            )
                        )

    return requests


def _filter_trailing_empty_paras(
    adds: list[AlignedElement],
) -> list[AlignedElement]:
    """Remove trailing empty paragraphs that follow a table add.

    When a table is added, insertTable automatically creates a trailing
    paragraph. We skip empty paragraph adds that immediately follow a table.
    """
    result: list[AlignedElement] = []
    for i, add in enumerate(adds):
        el = add.desired_element
        if not el:
            continue
        # Skip empty paragraph that follows a table
        if i > 0 and _is_paragraph(el):
            prev_el = adds[i - 1].desired_element
            if prev_el and _is_table(prev_el):
                text = _para_text(el)
                if text == "\n":
                    continue
        result.append(add)
    return result


# ---------------------------------------------------------------------------
# Individual add processing (for gaps containing tables)
# ---------------------------------------------------------------------------


def _insert_adds_individually(
    real_adds: list[AlignedElement],
    insert_idx: int,
    segment_id: str | None,
    tab_id: str | None,
) -> list[dict[str, Any]]:
    """Process adds individually in reverse order at insert_idx.

    Used when the gap contains tables mixed with paragraphs.
    Each insert happens at the same position; reverse order ensures
    correct final ordering (first inserted item ends up last).
    """
    requests: list[dict[str, Any]] = []

    # Filter trailing empty paras that follow tables
    filtered_adds = _filter_trailing_empty_paras(real_adds)

    for add in reversed(filtered_adds):
        el = add.desired_element
        assert el is not None
        if _is_table(el):
            assert el.table is not None
            table_reqs = _generate_insert_table_with_content(
                el.table, insert_idx, segment_id, tab_id
            )
            requests.extend(table_reqs)
        elif _is_paragraph(el):
            text = _para_text(el)
            if text:
                requests.append(_make_insert_text(text, insert_idx, segment_id, tab_id))

    return requests


# ---------------------------------------------------------------------------
# Table insertion with cell content
# ---------------------------------------------------------------------------


def _generate_insert_table_with_content(
    table: Table,
    insert_idx: int,
    segment_id: str | None,
    tab_id: str | None,
) -> list[dict[str, Any]]:
    """Generate insertTable + cell population requests.

    After insertTable at index I, the table starts at I+1.
    Cell [r][c] content starts at: I + 4 + r*(1 + 2*C) + 2*c
    where C is the column count. Cells are populated in reverse
    order so indices remain valid.
    """
    rows = table.rows or 0
    cols = table.columns or 0
    if rows == 0 or cols == 0:
        return []

    requests: list[dict[str, Any]] = []

    # 1. Insert the table
    requests.append(_make_insert_table(rows, cols, insert_idx, segment_id, tab_id))

    # 2. Populate cells in reverse order
    table_rows = table.table_rows or []
    for r in range(len(table_rows) - 1, -1, -1):
        row = table_rows[r]
        cells = row.table_cells or []
        for c in range(len(cells) - 1, -1, -1):
            cell = cells[c]
            text = _cell_text(cell)
            # Skip empty cells (just \n — the default after insertTable)
            text_stripped = text.rstrip("\n")
            if not text_stripped:
                continue
            # Cell content start: I + 4 + r*(1 + 2C) + 2c
            cell_content_idx = insert_idx + 4 + r * (1 + 2 * cols) + 2 * c
            requests.append(
                _make_insert_text(text_stripped, cell_content_idx, segment_id, tab_id)
            )

    return requests


# ---------------------------------------------------------------------------
# Matched table diffing
# ---------------------------------------------------------------------------


def _generate_table_diff(
    base_se: StructuralElement,
    desired_se: StructuralElement,
    segment_id: str | None,
    tab_id: str | None,
) -> list[dict[str, Any]]:
    """Generate requests to transform base table into desired table.

    Uses structural diff with proper row/column insert/delete operations.
    """
    assert base_se.table is not None
    assert desired_se.table is not None

    # Quick check: if text content is identical, no changes needed
    if extract_plain_text_from_table(base_se.table) == extract_plain_text_from_table(
        desired_se.table
    ):
        return []

    return _diff_table_structural(base_se, desired_se, segment_id, tab_id)


# ---------------------------------------------------------------------------
# Structural table diff — request helpers
# ---------------------------------------------------------------------------


def _make_insert_table_row(
    table_start: int,
    row_index: int,
    insert_below: bool,
    segment_id: str | None,
    tab_id: str | None,
) -> dict[str, Any]:
    return {
        "insertTableRow": {
            "tableCellLocation": _make_table_cell_location(
                table_start, row_index, 0, segment_id, tab_id
            ),
            "insertBelow": insert_below,
        }
    }


def _make_delete_table_row(
    table_start: int,
    row_index: int,
    segment_id: str | None,
    tab_id: str | None,
) -> dict[str, Any]:
    return {
        "deleteTableRow": {
            "tableCellLocation": _make_table_cell_location(
                table_start, row_index, 0, segment_id, tab_id
            ),
        }
    }


def _make_insert_table_column(
    table_start: int,
    col_index: int,
    insert_right: bool,
    segment_id: str | None,
    tab_id: str | None,
) -> dict[str, Any]:
    return {
        "insertTableColumn": {
            "tableCellLocation": _make_table_cell_location(
                table_start, 0, col_index, segment_id, tab_id
            ),
            "insertRight": insert_right,
        }
    }


def _make_delete_table_column(
    table_start: int,
    col_index: int,
    segment_id: str | None,
    tab_id: str | None,
) -> dict[str, Any]:
    return {
        "deleteTableColumn": {
            "tableCellLocation": _make_table_cell_location(
                table_start, 0, col_index, segment_id, tab_id
            ),
        }
    }


def _make_create_header(header_type: str, tab_id: str | None) -> dict[str, Any]:
    """Create a header request.

    Args:
        header_type: "DEFAULT" or other header type
        tab_id: Tab ID if creating in a specific tab
    """
    req: dict[str, Any] = {"createHeader": {"type": header_type}}
    # Note: sectionBreakLocation is None, so header applies to DocumentStyle
    if tab_id:
        req["createHeader"]["tabId"] = tab_id
    return req


def _make_delete_header(header_id: str, tab_id: str | None) -> dict[str, Any]:
    """Delete a header request."""
    req: dict[str, Any] = {"deleteHeader": {"headerId": header_id}}
    if tab_id:
        req["deleteHeader"]["tabId"] = tab_id
    return req


def _make_create_footer(footer_type: str, tab_id: str | None) -> dict[str, Any]:
    """Create a footer request.

    Args:
        footer_type: "DEFAULT" or other footer type
        tab_id: Tab ID if creating in a specific tab
    """
    req: dict[str, Any] = {"createFooter": {"type": footer_type}}
    # Note: sectionBreakLocation is None, so footer applies to DocumentStyle
    if tab_id:
        req["createFooter"]["tabId"] = tab_id
    return req


def _make_delete_footer(footer_id: str, tab_id: str | None) -> dict[str, Any]:
    """Delete a footer request."""
    req: dict[str, Any] = {"deleteFooter": {"footerId": footer_id}}
    if tab_id:
        req["deleteFooter"]["tabId"] = tab_id
    return req


# ---------------------------------------------------------------------------
# RowTable tracker for character index computation
# ---------------------------------------------------------------------------


@dataclass
class _RowEntry:
    id: str  # "base_0", "new_1", etc.
    length: int  # current row length in UTF-16 units


class _RowTable:
    """Tracks current table row state for index computation."""

    def __init__(self, entries: list[_RowEntry], table_start: int) -> None:
        self.entries = entries
        self.table_start = table_start

    def row_start(self, entry_index: int) -> int:
        """Character index where this row starts."""
        return self.table_start + 1 + sum(e.length for e in self.entries[:entry_index])

    def find(self, row_id: str) -> int:
        """Find entry index by id. Returns -1 if not found."""
        for i, e in enumerate(self.entries):
            if e.id == row_id:
                return i
        return -1

    def remove(self, entry_index: int) -> None:
        del self.entries[entry_index]

    def insert_after(self, entry_index: int, new_entry: _RowEntry) -> None:
        self.entries.insert(entry_index + 1, new_entry)

    def insert_before(self, entry_index: int, new_entry: _RowEntry) -> None:
        self.entries.insert(entry_index, new_entry)


# ---------------------------------------------------------------------------
# Structural table diff — main function
# ---------------------------------------------------------------------------


def _compute_row_length(row: TableRow, col_count: int) -> int:
    """Compute row length: 1 (row marker) + sum(1 (cell marker) + content_utf16_len)."""
    length = 1  # row marker
    cells = row.table_cells or []
    for c in range(col_count):
        if c < len(cells):
            text = _cell_text(cells[c])
            length += 1 + utf16_len(text)  # cell marker + content
        else:
            length += 1 + 1  # cell marker + \n
    return length


def _compute_adjusted_row_length(
    row: TableRow,
    col_alignment: list[tuple[AlignmentOp, int | None, int | None]],
) -> int:
    """Compute row length after column ops.

    MATCHED columns keep base cell content length.
    ADDED columns get 1 (empty \\n cell).
    DELETED columns are gone.
    """
    length = 1  # row marker
    cells = row.table_cells or []
    for op, base_col_idx, _desired_col_idx in col_alignment:
        if op == AlignmentOp.DELETED:
            continue
        if op == AlignmentOp.MATCHED:
            assert base_col_idx is not None
            if base_col_idx < len(cells):
                text = _cell_text(cells[base_col_idx])
                length += 1 + utf16_len(text)
            else:
                length += 1 + 1
        elif op == AlignmentOp.ADDED:
            length += 1 + 1  # cell marker + \n (empty cell)
    return length


def _diff_table_structural(
    base_se: StructuralElement,
    desired_se: StructuralElement,
    segment_id: str | None,
    tab_id: str | None,
) -> list[dict[str, Any]]:
    """Structural table diff with proper row/column operations."""
    table_start = _el_start(base_se)
    base_table = base_se.table
    desired_table = desired_se.table
    assert base_table is not None
    assert desired_table is not None

    base_rows = base_table.table_rows or []
    desired_rows = desired_table.table_rows or []
    base_col_count = base_table.columns or 0
    desired_col_count = desired_table.columns or 0

    # 1. Align rows and columns
    base_row_fps = [row_fingerprint(r) for r in base_rows]
    desired_row_fps = [row_fingerprint(r) for r in desired_rows]
    row_alignment = align_sequences(base_row_fps, desired_row_fps)

    base_col_fps = [column_fingerprint(base_rows, c) for c in range(base_col_count)]
    desired_col_fps = [
        column_fingerprint(desired_rows, c) for c in range(desired_col_count)
    ]
    col_alignment = align_sequences(base_col_fps, desired_col_fps)

    requests: list[dict[str, Any]] = []

    # 2. Column deletes (right to left, pristine indices)
    deleted_cols = sorted(
        [
            e.base_idx
            for e in col_alignment
            if e.op == AlignmentOp.DELETED and e.base_idx is not None
        ],
        reverse=True,
    )
    for col_idx in deleted_cols:
        requests.append(
            _make_delete_table_column(table_start, col_idx, segment_id, tab_id)
        )

    # 3. Column inserts (right to left, post-delete indices)
    # Build the list of columns after deletes, tracking base indices
    # For ADDED columns, find the nearest MATCHED column to the left as reference
    added_cols_with_refs: list[
        tuple[int, int, bool]
    ] = []  # (desired_col_idx, ref_current_idx, insert_right)

    # Build post-delete column mapping: for each MATCHED column,
    # compute its current index after deletes
    deleted_set = set(deleted_cols)
    for entry in col_alignment:
        if entry.op == AlignmentOp.ADDED:
            assert entry.desired_idx is not None
            # Find nearest MATCHED column to the left in desired order
            ref_base_idx: int | None = None
            for prev in col_alignment:
                if (
                    prev.op == AlignmentOp.MATCHED
                    and prev.desired_idx is not None
                    and prev.desired_idx < entry.desired_idx
                ):
                    ref_base_idx = prev.base_idx
            if ref_base_idx is not None:
                # Compute current index: base_idx minus count of deleted cols below it
                ref_current = ref_base_idx - sum(
                    1 for d in deleted_set if d < ref_base_idx
                )
                added_cols_with_refs.append((entry.desired_idx, ref_current, True))
            else:
                # No matched column to the left — find first MATCHED column
                for nxt in col_alignment:
                    if nxt.op == AlignmentOp.MATCHED and nxt.base_idx is not None:
                        ref_current = nxt.base_idx - sum(
                            1 for d in deleted_set if d < nxt.base_idx
                        )
                        added_cols_with_refs.append(
                            (entry.desired_idx, ref_current, False)
                        )
                        break

    # Sort by desired_col_idx descending (right to left)
    added_cols_with_refs.sort(key=lambda x: x[0], reverse=True)
    for _desired_col_idx, ref_current_idx, insert_right in added_cols_with_refs:
        requests.append(
            _make_insert_table_column(
                table_start, ref_current_idx, insert_right, segment_id, tab_id
            )
        )

    # 4. Initialize RowTable with post-column-ops base row lengths
    col_alignment_list = [(e.op, e.base_idx, e.desired_idx) for e in col_alignment]
    row_entries: list[_RowEntry] = []
    for r_idx, row in enumerate(base_rows):
        adj_len = _compute_adjusted_row_length(row, col_alignment_list)
        row_entries.append(_RowEntry(id=f"base_{r_idx}", length=adj_len))

    row_table = _RowTable(row_entries, table_start)

    # 5. Build sorted operation list for the row pass
    ops: list[tuple[int, AlignmentOp, int | None, int | None]] = []
    for entry in row_alignment:
        if entry.op == AlignmentOp.DELETED:
            position = entry.base_idx if entry.base_idx is not None else 0
        else:
            position = entry.desired_idx if entry.desired_idx is not None else 0
        ops.append((position, entry.op, entry.base_idx, entry.desired_idx))

    # Sort descending by position; at same position, DELETED before ADDED/MATCHED
    ops.sort(
        key=lambda x: (x[0], 0 if x[1] == AlignmentOp.DELETED else 1), reverse=True
    )

    # Number of columns in desired table (post-ops column count)
    desired_cols_count = desired_col_count

    # 6. Process bottom-to-top
    for _position, op, base_idx, desired_idx in ops:
        if op == AlignmentOp.DELETED:
            assert base_idx is not None
            entry_idx = row_table.find(f"base_{base_idx}")
            requests.append(
                _make_delete_table_row(table_start, entry_idx, segment_id, tab_id)
            )
            row_table.remove(entry_idx)

        elif op == AlignmentOp.MATCHED:
            assert base_idx is not None
            assert desired_idx is not None
            entry_idx = row_table.find(f"base_{base_idx}")
            rs = row_table.row_start(entry_idx)
            cell_reqs, new_length = _diff_row_cells(
                base_rows[base_idx],
                desired_rows[desired_idx],
                rs,
                col_alignment_list,
                segment_id,
                tab_id,
            )
            requests.extend(cell_reqs)
            row_table.entries[entry_idx].length = new_length

        elif op == AlignmentOp.ADDED:
            assert desired_idx is not None
            # Find reference: nearest MATCHED row above in desired table
            ref_entry_idx: int | None = None
            for prev in row_alignment:
                if (
                    prev.op == AlignmentOp.MATCHED
                    and prev.desired_idx is not None
                    and prev.desired_idx < desired_idx
                ):
                    assert prev.base_idx is not None
                    found = row_table.find(f"base_{prev.base_idx}")
                    if found >= 0:
                        ref_entry_idx = found

            if ref_entry_idx is not None:
                requests.append(
                    _make_insert_table_row(
                        table_start, ref_entry_idx, True, segment_id, tab_id
                    )
                )
                # Empty row length: 1 (row marker) + desired_cols * (1 cell marker + 1 \n)
                new_row_len = 1 + desired_cols_count * 2
                new_entry = _RowEntry(f"new_{desired_idx}", new_row_len)
                row_table.insert_after(ref_entry_idx, new_entry)
                new_entry_idx = ref_entry_idx + 1
            else:
                # No matched row above — insert before first row
                requests.append(
                    _make_insert_table_row(table_start, 0, False, segment_id, tab_id)
                )
                new_row_len = 1 + desired_cols_count * 2
                new_entry = _RowEntry(f"new_{desired_idx}", new_row_len)
                row_table.insert_before(0, new_entry)
                new_entry_idx = 0

            # Populate cells right-to-left
            rs = row_table.row_start(new_entry_idx)
            pop_reqs, new_length = _populate_new_row(
                desired_rows[desired_idx],
                rs,
                desired_cols_count,
                segment_id,
                tab_id,
            )
            requests.extend(pop_reqs)
            row_table.entries[new_entry_idx].length = new_length

    return requests


# ---------------------------------------------------------------------------
# Cell diffing within a row
# ---------------------------------------------------------------------------


def _diff_row_cells(
    base_row: TableRow,
    desired_row: TableRow,
    row_start: int,
    col_alignment: list[tuple[AlignmentOp, int | None, int | None]],
    segment_id: str | None,
    tab_id: str | None,
) -> tuple[list[dict[str, Any]], int]:
    """Diff cells right-to-left for a MATCHED row.

    Returns (requests, new_row_length).
    """
    base_cells = base_row.table_cells or []
    desired_cells = desired_row.table_cells or []

    # Build desired column layout: columns that survive (MATCHED or ADDED)
    desired_cols: list[tuple[AlignmentOp, int | None, int | None]] = [
        (op, b_idx, d_idx)
        for op, b_idx, d_idx in col_alignment
        if op != AlignmentOp.DELETED
    ]

    # Compute content lengths for each column (used for index computation)
    # For LEFT-side columns not yet processed: use current (base or empty) lengths
    content_lens: list[int] = []
    for op, base_col_idx, _desired_col_idx in desired_cols:
        if op == AlignmentOp.MATCHED:
            assert base_col_idx is not None
            if base_col_idx < len(base_cells):
                text = _cell_text(base_cells[base_col_idx])
                content_lens.append(utf16_len(text))
            else:
                content_lens.append(1)
        elif op == AlignmentOp.ADDED:
            content_lens.append(1)  # \n (empty cell)
        else:
            content_lens.append(1)

    requests: list[dict[str, Any]] = []
    new_row_length = 1  # row marker

    # Process right-to-left
    for c in range(len(desired_cols) - 1, -1, -1):
        col_op, base_col_idx, desired_col_idx = desired_cols[c]
        # cell_start = row_start + 1 (row marker) + 1 (first cell marker)
        # + c (cell markers for cols 0..c-1) + sum(content_len[0..c-1])
        cell_start = row_start + 2 + c + sum(content_lens[:c])

        if col_op == AlignmentOp.MATCHED:
            assert base_col_idx is not None
            assert desired_col_idx is not None
            base_cell = (
                base_cells[base_col_idx] if base_col_idx < len(base_cells) else None
            )
            desired_cell = (
                desired_cells[desired_col_idx]
                if desired_col_idx < len(desired_cells)
                else None
            )
            if base_cell and desired_cell:
                cell_reqs = _diff_single_cell_at(
                    base_cell, desired_cell, cell_start, segment_id, tab_id
                )
                requests.extend(cell_reqs)
        elif col_op == AlignmentOp.ADDED:
            assert desired_col_idx is not None
            if desired_col_idx < len(desired_cells):
                desired_cell = desired_cells[desired_col_idx]
                pop_reqs = _populate_cell_at(
                    desired_cell, cell_start, segment_id, tab_id
                )
                requests.extend(pop_reqs)

    # Compute new row length from desired cells
    for c in range(len(desired_cols)):
        _col_op, _b_idx, d_idx = desired_cols[c]
        if d_idx is not None and d_idx < len(desired_cells):
            text = _cell_text(desired_cells[d_idx])
            new_row_length += 1 + utf16_len(text)
        else:
            new_row_length += 2  # cell marker + \n

    return requests, new_row_length


def _populate_new_row(
    desired_row: TableRow,
    row_start: int,
    desired_cols_count: int,
    segment_id: str | None,
    tab_id: str | None,
) -> tuple[list[dict[str, Any]], int]:
    """Populate cells of a newly inserted row, right-to-left.

    Returns (requests, new_row_length).
    """
    desired_cells = desired_row.table_cells or []
    requests: list[dict[str, Any]] = []
    new_row_length = 1  # row marker

    # All cells start as empty (\n), so content_lens are all 1
    content_lens = [1] * desired_cols_count

    for c in range(desired_cols_count - 1, -1, -1):
        cell_start = row_start + 2 + c + sum(content_lens[:c])
        if c < len(desired_cells):
            pop_reqs = _populate_cell_at(
                desired_cells[c], cell_start, segment_id, tab_id
            )
            requests.extend(pop_reqs)

    # Compute actual row length
    for c in range(desired_cols_count):
        if c < len(desired_cells):
            text = _cell_text(desired_cells[c])
            new_row_length += 1 + utf16_len(text)
        else:
            new_row_length += 2

    return requests, new_row_length


def _diff_single_cell_at(
    base_cell: TableCell,
    desired_cell: TableCell,
    cell_start: int,
    segment_id: str | None,
    tab_id: str | None,
) -> list[dict[str, Any]]:
    """Diff a single cell using a computed cell_start index."""
    base_text = _cell_text(base_cell)
    desired_text = _cell_text(desired_cell)

    if base_text == desired_text:
        return []

    requests: list[dict[str, Any]] = []

    # Delete old content (protect cell-ending \n)
    old_text_stripped = base_text.rstrip("\n")
    if old_text_stripped:
        del_end = cell_start + utf16_len(old_text_stripped)
        if cell_start < del_end:
            requests.append(_make_delete_range(cell_start, del_end, segment_id, tab_id))

    # Insert new content
    new_text_stripped = desired_text.rstrip("\n")
    if new_text_stripped:
        requests.append(
            _make_insert_text(new_text_stripped, cell_start, segment_id, tab_id)
        )

    return requests


def _populate_cell_at(
    desired_cell: TableCell,
    cell_start: int,
    segment_id: str | None,
    tab_id: str | None,
) -> list[dict[str, Any]]:
    """Populate an empty cell (just \\n) with desired content."""
    desired_text = _cell_text(desired_cell)
    text_stripped = desired_text.rstrip("\n")
    if not text_stripped:
        return []
    return [_make_insert_text(text_stripped, cell_start, segment_id, tab_id)]


def _diff_single_cell(
    base_cell: TableCell,
    desired_cell: TableCell,
    segment_id: str | None,
    tab_id: str | None,
) -> list[dict[str, Any]]:
    """Diff a single cell's content. Uses deleteContentRange + insertText."""
    base_text = _cell_text(base_cell)
    desired_text = _cell_text(desired_cell)

    if base_text == desired_text:
        return []

    # Get the cell's content range from base indices
    base_content = base_cell.content or []
    if not base_content:
        return []

    # Find the text range within the cell (first element start to last element end)
    cell_start = base_content[0].start_index
    cell_end = base_content[-1].end_index
    if cell_start is None or cell_end is None:
        return []

    requests: list[dict[str, Any]] = []

    # Delete old content (protect cell-ending \n)
    old_text_stripped = base_text.rstrip("\n")
    if old_text_stripped:
        # Delete from cell start to cell_end - 1 (protect final \n)
        del_end = cell_end - 1
        if cell_start < del_end:
            requests.append(_make_delete_range(cell_start, del_end, segment_id, tab_id))

    # Insert new content
    new_text_stripped = desired_text.rstrip("\n")
    if new_text_stripped:
        requests.append(
            _make_insert_text(new_text_stripped, cell_start, segment_id, tab_id)
        )

    return requests


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _collect_add_text(real_adds: list[AlignedElement]) -> str:
    """Concatenate text from all ADDED paragraph elements."""
    parts: list[str] = []
    for a in real_adds:
        el = a.desired_element
        if el and el.paragraph:
            text = extract_plain_text_from_paragraph(el.paragraph)
            if text:
                parts.append(text)
    return "".join(parts)
