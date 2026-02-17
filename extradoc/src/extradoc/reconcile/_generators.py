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

if TYPE_CHECKING:
    from extradoc.api_types import SegmentID, TabID

from extradoc.api_types._generated import ParagraphStyle, TextStyle
from extradoc.indexer import utf16_len
from extradoc.reconcile._alignment import AlignedElement, AlignmentOp, align_sequences
from extradoc.reconcile._exceptions import ReconcileError
from extradoc.reconcile._extractors import (
    column_fingerprint,
    extract_plain_text_from_paragraph,
    row_fingerprint,
)

if TYPE_CHECKING:
    from extradoc.api_types._generated import (
        Paragraph,
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
    index: int,
    segment_id: SegmentID,
    tab_id: TabID,
) -> dict[str, Any]:
    """Create a Location dict. IDs may be DeferredID objects."""
    loc: dict[str, Any] = {"index": index}
    if segment_id:
        loc["segmentId"] = segment_id
    if tab_id:
        loc["tabId"] = tab_id
    return loc


def _make_range(
    start: int,
    end: int,
    segment_id: SegmentID,
    tab_id: TabID,
) -> dict[str, Any]:
    """Create a Range dict. IDs may be DeferredID objects."""
    r: dict[str, Any] = {"startIndex": start, "endIndex": end}
    if segment_id:
        r["segmentId"] = segment_id
    if tab_id:
        r["tabId"] = tab_id
    return r


def _make_delete_range(
    start: int,
    end: int,
    segment_id: SegmentID,
    tab_id: TabID,
) -> dict[str, Any]:
    return {
        "deleteContentRange": {"range": _make_range(start, end, segment_id, tab_id)}
    }


def _make_insert_text(
    text: str,
    index: int,
    segment_id: SegmentID,
    tab_id: TabID,
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
    segment_id: SegmentID,
    tab_id: TabID,
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
    segment_id: SegmentID,
    tab_id: TabID,
) -> dict[str, Any]:
    """Create a TableCellLocation dict. IDs may be DeferredID objects."""
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


def _has_non_text_elements(se: StructuralElement) -> bool:
    """Check if a paragraph contains non-text elements (pageBreak, horizontalRule, etc.)."""
    if not se.paragraph:
        return False
    for elem in se.paragraph.elements or []:
        if (
            elem.page_break is not None
            or elem.horizontal_rule is not None
            or elem.inline_object_element is not None
            or elem.footnote_reference is not None
        ):
            return True
    return False


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
# Style comparison utilities
# ---------------------------------------------------------------------------


def _compute_style_diff(
    base_style: TextStyle | ParagraphStyle | None,
    desired_style: TextStyle | ParagraphStyle | None,
    style_type: type[TextStyle] | type[ParagraphStyle],
) -> tuple[dict[str, Any], list[str]]:
    """Compare two style objects and compute diff + field mask.

    Returns (style_dict, fields_list) where:
    - style_dict contains only changed fields with new values
    - fields_list contains all changed field names (for API mask)
    - Fields in mask but not in dict will be cleared by API
    """
    base_dict = (
        base_style.model_dump(by_alias=True, exclude_none=True) if base_style else {}
    )
    desired_dict = (
        desired_style.model_dump(by_alias=True, exclude_none=True)
        if desired_style
        else {}
    )

    all_api_names: set[str] = set()
    for field_name, field_info in style_type.model_fields.items():
        api_name = field_info.alias or field_name
        all_api_names.add(api_name)

    changed_fields: list[str] = []
    result_style: dict[str, Any] = {}

    for api_name in sorted(all_api_names):
        base_val = base_dict.get(api_name)
        desired_val = desired_dict.get(api_name)

        if base_val != desired_val:
            changed_fields.append(api_name)
            if desired_val is not None:
                result_style[api_name] = desired_val

    return result_style, changed_fields


def _styles_equal(
    style1: TextStyle | ParagraphStyle | None,
    style2: TextStyle | ParagraphStyle | None,
) -> bool:
    """Check if two styles are equal (None-safe)."""
    if style1 is None and style2 is None:
        return True
    if style1 is None or style2 is None:
        return False
    dict1 = style1.model_dump(by_alias=True, exclude_none=True)
    dict2 = style2.model_dump(by_alias=True, exclude_none=True)
    return dict1 == dict2


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def generate_requests(
    alignment: list[AlignedElement],
    segment_id: SegmentID,
    tab_id: TabID,
) -> list[dict[str, Any]]:
    """Generate batchUpdate requests from an alignment.

    Args:
        alignment: List of aligned StructuralElements
        segment_id: Segment ID context (may be DeferredID for new segments)
        tab_id: Tab ID context (may be DeferredID for new tabs)

    Returns:
        List of request dicts (may contain DeferredID objects in location fields)

    Handles both gap-based operations (add/delete structural elements)
    and matched table diffs (cell content changes).
    All operations are processed right-to-left by base index position.
    """
    # Check for unsupported TOC changes upfront
    for aligned in alignment:
        el = aligned.desired_element or aligned.base_element
        if el and el.table_of_contents is not None:
            if aligned.op in (AlignmentOp.ADDED, AlignmentOp.DELETED):
                raise ReconcileError(
                    "tableOfContents is read-only and cannot be added or removed"
                )
            # MATCHED TOC: skip (no changes possible)
            continue

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

    # Collect matched paragraph style diff operations
    for aligned in alignment:
        if aligned.op != AlignmentOp.MATCHED:
            continue
        base_el = aligned.base_element
        desired_el = aligned.desired_element
        if not base_el or not desired_el:
            continue
        if not _is_paragraph(base_el) or not _is_paragraph(desired_el):
            continue

        reqs = _generate_paragraph_style_diff(base_el, desired_el, segment_id, tab_id)
        if reqs:
            operations.append((_el_start(base_el), reqs))

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


def _validate_no_section_breaks(gap: _Gap) -> None:
    """Raise ReconcileError if the gap contains any section break deletes or adds."""
    for a in gap.deletes:
        if a.base_element and _is_section_break(a.base_element):
            raise ReconcileError(
                "Section break deletion is not supported by reconcile()"
            )
    for a in gap.adds:
        if a.desired_element and _is_section_break(a.desired_element):
            raise ReconcileError(
                "Section break insertion is not supported by reconcile()"
            )


# ---------------------------------------------------------------------------
# Gap processing — inner gap
# ---------------------------------------------------------------------------


def _process_inner_gap(
    gap: _Gap, segment_id: SegmentID, tab_id: TabID
) -> list[dict[str, Any]]:
    """Process a non-trailing gap (has a right anchor)."""
    requests: list[dict[str, Any]] = []
    _validate_no_section_breaks(gap)
    real_deletes = gap.deletes
    real_adds = gap.adds

    for a in real_adds:
        if a.desired_element and _has_non_text_elements(a.desired_element):
            raise ReconcileError(
                "Cannot insert paragraph containing non-text elements "
                "(pageBreak, horizontalRule, inlineObject, footnoteReference). "
                "Use the appropriate API requests directly."
            )

    if not real_deletes and not real_adds:
        return []

    first_del_el = real_deletes[0].base_element if real_deletes else None
    last_del_el = real_deletes[-1].base_element if real_deletes else None

    # When the right anchor is a table, we cannot delete up to the table
    # start (the API forbids deleting the \n before a table without also
    # deleting the table).  Trim the delete to preserve the \n.
    right_is_table = gap.right_anchor is not None and _is_table(gap.right_anchor)

    # Special case: exactly one table is being replaced with another table,
    # possibly alongside paragraph changes.
    # insertTable always creates a trailing paragraph by splitting at the
    # insertion index.  When a trailing P("\n") already exists (as the right
    # anchor or the body's final element), this creates an unwanted extra
    # paragraph.  Instead, diff the tables IN PLACE using _generate_table_diff,
    # which only emits row/column/cell operations without any insertTable call.
    # We also handle any surrounding paragraph deletes/inserts in the same gap.
    table_del_list = [
        (i, a)
        for i, a in enumerate(real_deletes)
        if a.base_element and _is_table(a.base_element)
    ]
    table_add_list = [
        (i, a)
        for i, a in enumerate(real_adds)
        if a.desired_element and _is_table(a.desired_element)
    ]
    if len(table_del_list) == 1 and len(table_add_list) == 1:
        table_del_pos, table_del_aligned = table_del_list[0]
        table_add_pos, table_add_aligned = table_add_list[0]
        base_table_el = table_del_aligned.base_element
        desired_table_el = table_add_aligned.desired_element
        assert base_table_el is not None
        assert desired_table_el is not None

        # Split non-table elements by position relative to the table
        # (using index within real_deletes/real_adds to preserve order)
        before_dels = real_deletes[:table_del_pos]
        after_dels = real_deletes[table_del_pos + 1 :]
        before_adds = real_adds[:table_add_pos]
        after_adds = real_adds[table_add_pos + 1 :]

        # Modify table in-place (avoids insertTable trailing-para issue)
        table_reqs = _generate_table_diff(
            base_table_el, desired_table_el, segment_id, tab_id
        )

        combined: list[dict[str, Any]] = []

        # "After table" changes first (right-to-left, higher index)
        if after_dels or after_adds:
            if after_dels:
                first_after_el = after_dels[0].base_element
                last_after_el = after_dels[-1].base_element
                assert first_after_el is not None
                assert last_after_el is not None
                a_del_start = _el_start(first_after_el)
                a_del_end = _el_end(last_after_el)
                if right_is_table:
                    a_del_end = a_del_end - 1
                if a_del_start < a_del_end:
                    combined.append(
                        _make_delete_range(a_del_start, a_del_end, segment_id, tab_id)
                    )
                after_text = _collect_add_text(after_adds)
                if after_text:
                    if right_is_table:
                        after_text = after_text.rstrip("\n")
                    if after_text:
                        combined.append(
                            _make_insert_text(
                                after_text, a_del_start, segment_id, tab_id
                            )
                        )
            else:
                # Only after-adds, no after-deletes: insert after the table
                after_text = _collect_add_text(after_adds)
                if after_text:
                    if right_is_table:
                        after_text = after_text.rstrip("\n")
                    if after_text:
                        combined.append(
                            _make_insert_text(
                                after_text, _el_end(base_table_el), segment_id, tab_id
                            )
                        )

        # Table operations (in-place, using original base indices)
        combined.extend(table_reqs)

        # "Before table" changes last (right-to-left, lower index)
        if before_dels or before_adds:
            if before_dels:
                first_before_el = before_dels[0].base_element
                last_before_el = before_dels[-1].base_element
                assert first_before_el is not None
                assert last_before_el is not None
                b_del_start = _el_start(first_before_el)
                b_del_end = _el_end(last_before_el)
                # The API forbids deleting the \n immediately before a table.
                # When the last paragraph ends exactly at the table's start,
                # protect its trailing \n by shrinking the delete range by 1.
                protect_newline = _el_end(last_before_el) == _el_start(base_table_el)
                if protect_newline:
                    b_del_end -= 1
                if b_del_start < b_del_end:
                    combined.append(
                        _make_delete_range(b_del_start, b_del_end, segment_id, tab_id)
                    )
                before_text = _collect_add_text(before_adds)
                if before_text:
                    # The protected \n remains in the doc, so strip the trailing \n
                    # from the inserted text to avoid creating an extra empty paragraph.
                    if protect_newline:
                        before_text = before_text.rstrip("\n")
                    if before_text:
                        combined.append(
                            _make_insert_text(
                                before_text, b_del_start, segment_id, tab_id
                            )
                        )
            else:
                # Only before-adds, no before-deletes: insert before the table
                before_text = _collect_add_text(before_adds)
                if before_text:
                    combined.append(
                        _make_insert_text(
                            before_text, _el_start(base_table_el), segment_id, tab_id
                        )
                    )

        return combined

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
    gap: _Gap, segment_id: SegmentID, tab_id: TabID
) -> list[dict[str, Any]]:
    """Process a trailing gap (no right anchor). Must protect segment-final \\n."""
    requests: list[dict[str, Any]] = []
    _validate_no_section_breaks(gap)
    real_deletes = gap.deletes
    real_adds = gap.adds

    for a in real_adds:
        if a.desired_element and _has_non_text_elements(a.desired_element):
            raise ReconcileError(
                "Cannot insert paragraph containing non-text elements "
                "(pageBreak, horizontalRule, inlineObject, footnoteReference). "
                "Use the appropriate API requests directly."
            )

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
    segment_id: SegmentID,
    tab_id: TabID,
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
    segment_id: SegmentID,
    tab_id: TabID,
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
    segment_id: SegmentID,
    tab_id: TabID,
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
    segment_id: SegmentID,
    tab_id: TabID,
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


def _tables_have_identical_text_structure(
    base_table: Table, desired_table: Table
) -> bool:
    """Return True iff tables have the same dimensions and identical text in each cell.

    Compares row-by-row using row_fingerprint (which encodes per-cell text) so that
    row reordering or column reordering within a row is detected as a structural change.
    """
    base_rows = base_table.table_rows or []
    desired_rows = desired_table.table_rows or []
    if len(base_rows) != len(desired_rows):
        return False
    return all(
        row_fingerprint(br) == row_fingerprint(dr)
        for br, dr in zip(base_rows, desired_rows, strict=False)
    )


def _generate_table_diff(
    base_se: StructuralElement,
    desired_se: StructuralElement,
    segment_id: SegmentID,
    tab_id: TabID,
) -> list[dict[str, Any]]:
    """Generate requests to transform base table into desired table.

    When text content is identical, performs style-only diff on matched cells.
    When text differs, uses structural diff (row/column insert/delete/modify).
    """
    assert base_se.table is not None
    assert desired_se.table is not None

    if _tables_have_identical_text_structure(base_se.table, desired_se.table):
        # Same dimensions and same text in each cell position — style changes only
        return _diff_table_cell_styles_only(
            base_se.table, desired_se.table, segment_id, tab_id
        )

    return _diff_table_structural(base_se, desired_se, segment_id, tab_id)


def _table_cell_style_changed(base_cell: Any, desired_cell: Any) -> bool:
    """Return True if tableCellStyle differs between base and desired cells."""
    base_style = getattr(base_cell, "table_cell_style", None)
    desired_style = getattr(desired_cell, "table_cell_style", None)
    base_dict = (
        base_style.model_dump(by_alias=True, exclude_none=True) if base_style else {}
    )
    desired_dict = (
        desired_style.model_dump(by_alias=True, exclude_none=True)
        if desired_style
        else {}
    )
    return base_dict != desired_dict


def _diff_table_cell_styles_only(
    base_table: Table,
    desired_table: Table,
    segment_id: SegmentID,
    tab_id: TabID,
) -> list[dict[str, Any]]:
    """Diff paragraph/text styles within table cells when text is identical.

    Iterates matched row/cell pairs and applies _generate_paragraph_style_diff
    on each matched paragraph. Uses the base paragraph's actual start_index
    (valid since no structural changes are made).

    Returns requests sorted right-to-left by paragraph start index.

    Raises ReconcileError if tableCellStyle changes are detected (unsupported).
    """
    requests: list[dict[str, Any]] = []
    base_rows = base_table.table_rows or []
    desired_rows = desired_table.table_rows or []

    base_row_fps = [row_fingerprint(r) for r in base_rows]
    desired_row_fps = [row_fingerprint(r) for r in desired_rows]
    row_align = align_sequences(base_row_fps, desired_row_fps)

    for entry in row_align:
        if entry.op != AlignmentOp.MATCHED:
            continue
        assert entry.base_idx is not None
        assert entry.desired_idx is not None
        base_row = base_rows[entry.base_idx]
        desired_row = desired_rows[entry.desired_idx]

        base_cells = base_row.table_cells or []
        desired_cells = desired_row.table_cells or []

        for bc, dc in zip(base_cells, desired_cells, strict=False):
            if _table_cell_style_changed(bc, dc):
                raise ReconcileError(
                    "tableCellStyle changes are not supported by reconcile(). "
                    "The Google Docs API requires updateTableCellStyle which is "
                    "not yet implemented. Use the API directly to change cell styles."
                )
            # Each cell's content is a list of StructuralElements (paragraphs)
            base_paras = [se for se in (bc.content or []) if se.paragraph]
            desired_paras = [se for se in (dc.content or []) if se.paragraph]

            # Align cell paragraphs by plain text fingerprint
            bfps = [_para_text(se) for se in base_paras]
            dfps = [_para_text(se) for se in desired_paras]
            para_align = align_sequences(bfps, dfps)

            for pa in para_align:
                if pa.op != AlignmentOp.MATCHED:
                    continue
                assert pa.base_idx is not None
                assert pa.desired_idx is not None
                base_se = base_paras[pa.base_idx]
                desired_se = desired_paras[pa.desired_idx]
                reqs = _generate_paragraph_style_diff(
                    base_se, desired_se, segment_id, tab_id
                )
                requests.extend(reqs)

    # Sort right-to-left by paragraph start index
    def _sort_key(r: dict[str, Any]) -> int:
        inner: dict[str, Any] = next(iter(r.values()), {})
        rng: dict[str, Any] = inner.get("range", {})
        return int(rng.get("startIndex", 0))

    requests.sort(key=_sort_key, reverse=True)
    return requests


# ---------------------------------------------------------------------------
# Structural table diff — request helpers
# ---------------------------------------------------------------------------


def _make_insert_table_row(
    table_start: int,
    row_index: int,
    insert_below: bool,
    segment_id: SegmentID,
    tab_id: TabID,
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
    segment_id: SegmentID,
    tab_id: TabID,
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
    segment_id: SegmentID,
    tab_id: TabID,
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
    segment_id: SegmentID,
    tab_id: TabID,
) -> dict[str, Any]:
    return {
        "deleteTableColumn": {
            "tableCellLocation": _make_table_cell_location(
                table_start, 0, col_index, segment_id, tab_id
            ),
        }
    }


def _make_create_header(header_type: str, tab_id: TabID) -> dict[str, Any]:
    """Create a header request.

    Args:
        header_type: "DEFAULT" or other header type
        tab_id: Tab ID if creating in a specific tab (may be DeferredID)
    """
    req: dict[str, Any] = {"createHeader": {"type": header_type}}
    # Note: sectionBreakLocation is None, so header applies to DocumentStyle
    if tab_id:
        req["createHeader"]["tabId"] = tab_id
    return req


def _make_delete_header(header_id: str, tab_id: TabID) -> dict[str, Any]:
    """Delete a header request."""
    req: dict[str, Any] = {"deleteHeader": {"headerId": header_id}}
    if tab_id:
        req["deleteHeader"]["tabId"] = tab_id
    return req


def _make_create_footer(footer_type: str, tab_id: TabID) -> dict[str, Any]:
    """Create a footer request.

    Args:
        footer_type: "DEFAULT" or other footer type
        tab_id: Tab ID if creating in a specific tab (may be DeferredID)
    """
    req: dict[str, Any] = {"createFooter": {"type": footer_type}}
    # Note: sectionBreakLocation is None, so footer applies to DocumentStyle
    if tab_id:
        req["createFooter"]["tabId"] = tab_id
    return req


def _make_delete_footer(footer_id: str, tab_id: TabID) -> dict[str, Any]:
    """Delete a footer request."""
    req: dict[str, Any] = {"deleteFooter": {"footerId": footer_id}}
    if tab_id:
        req["deleteFooter"]["tabId"] = tab_id
    return req


def _make_add_document_tab(title: str, index: int | None = None) -> dict[str, Any]:
    """Create an addDocumentTab request.

    Args:
        title: Tab title
        index: Tab index (position in tab list). None means append to end.

    Returns:
        addDocumentTab request dict
    """
    tab_properties: dict[str, Any] = {"title": title}
    if index is not None:
        tab_properties["index"] = index
    return {"addDocumentTab": {"tabProperties": tab_properties}}


def _make_delete_tab(tab_id: str) -> dict[str, Any]:
    """Create a deleteTab request.

    Args:
        tab_id: ID of tab to delete

    Returns:
        deleteTab request dict
    """
    return {"deleteTab": {"tabId": tab_id}}


def _make_update_document_tab_properties(
    tab_id: str, title: str | None = None, index: int | None = None
) -> dict[str, Any]:
    """Create an updateDocumentTabProperties request.

    Args:
        tab_id: ID of tab to update
        title: New title (if changing)
        index: New index (if changing)

    Returns:
        updateDocumentTabProperties request dict with appropriate field mask
    """
    tab_properties: dict[str, Any] = {"tabId": tab_id}
    fields: list[str] = []

    if title is not None:
        tab_properties["title"] = title
        fields.append("title")
    if index is not None:
        tab_properties["index"] = index
        fields.append("index")

    return {
        "updateDocumentTabProperties": {
            "tabProperties": tab_properties,
            "fields": ",".join(fields),
        }
    }


# ---------------------------------------------------------------------------
# Style request builders
# ---------------------------------------------------------------------------


def _make_update_text_style(
    start: int,
    end: int,
    text_style: dict[str, Any],
    fields: list[str],
    segment_id: SegmentID,
    tab_id: TabID,
) -> dict[str, Any]:
    """Create an updateTextStyle request."""
    return {
        "updateTextStyle": {
            "range": _make_range(start, end, segment_id, tab_id),
            "textStyle": text_style,
            "fields": ",".join(fields),
        }
    }


def _make_update_paragraph_style(
    start: int,
    end: int,
    paragraph_style: dict[str, Any],
    fields: list[str],
    segment_id: SegmentID,
    tab_id: TabID,
) -> dict[str, Any]:
    """Create an updateParagraphStyle request."""
    return {
        "updateParagraphStyle": {
            "range": _make_range(start, end, segment_id, tab_id),
            "paragraphStyle": paragraph_style,
            "fields": ",".join(fields),
        }
    }


def _make_create_paragraph_bullets(
    start: int,
    end: int,
    bullet_preset: str,
    segment_id: SegmentID,
    tab_id: TabID,
) -> dict[str, Any]:
    """Create a createParagraphBullets request."""
    return {
        "createParagraphBullets": {
            "range": _make_range(start, end, segment_id, tab_id),
            "bulletPreset": bullet_preset,
        }
    }


def _make_delete_paragraph_bullets(
    start: int,
    end: int,
    segment_id: SegmentID,
    tab_id: TabID,
) -> dict[str, Any]:
    """Create a deleteParagraphBullets request."""
    return {
        "deleteParagraphBullets": {
            "range": _make_range(start, end, segment_id, tab_id),
        }
    }


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
    segment_id: SegmentID,
    tab_id: TabID,
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
    segment_id: SegmentID,
    tab_id: TabID,
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
    segment_id: SegmentID,
    tab_id: TabID,
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


def _check_multi_para_cell_styles(cell: TableCell) -> None:
    """Raise ReconcileError if a cell has multiple paragraphs with non-default styles.

    When a desired cell has multiple paragraphs, we use insertText which correctly
    creates paragraph breaks via embedded \\n. However, per-paragraph styles (such as
    namedStyleType=HEADING_1) cannot be applied through insertText alone — they would
    be silently lost. Raise an error to surface this limitation.
    """
    paras = [se for se in (cell.content or []) if se.paragraph]
    if len(paras) <= 1:
        return
    for se in paras:
        ps = se.paragraph and se.paragraph.paragraph_style
        if ps is not None:
            style_dict = ps.model_dump(by_alias=True, exclude_none=True)
            if style_dict:
                raise ReconcileError(
                    "Multi-paragraph table cells with paragraph styles (e.g. "
                    "namedStyleType=HEADING_1) are not supported by reconcile(). "
                    "The per-paragraph styles would be silently lost. "
                    "Use the Google Docs API directly to create such cells."
                )


def _diff_single_cell_at(
    base_cell: TableCell,
    desired_cell: TableCell,
    cell_start: int,
    segment_id: SegmentID,
    tab_id: TabID,
) -> list[dict[str, Any]]:
    """Diff a single cell using a computed cell_start index."""
    _check_multi_para_cell_styles(desired_cell)
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
    segment_id: SegmentID,
    tab_id: TabID,
) -> list[dict[str, Any]]:
    """Populate an empty cell (just \\n) with desired content."""
    _check_multi_para_cell_styles(desired_cell)
    desired_text = _cell_text(desired_cell)
    text_stripped = desired_text.rstrip("\n")
    if not text_stripped:
        return []
    return [_make_insert_text(text_stripped, cell_start, segment_id, tab_id)]


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


# ---------------------------------------------------------------------------
# Paragraph and text style diffing
# ---------------------------------------------------------------------------


def _generate_paragraph_style_diff(
    base_se: StructuralElement,
    desired_se: StructuralElement,
    segment_id: SegmentID,
    tab_id: TabID,
) -> list[dict[str, Any]]:
    """Generate style update requests for a MATCHED paragraph.

    Checks for paragraph-level style changes, bullet changes, and text run
    style changes. Only processes paragraphs with matching text content.

    Returns requests in order:
    1. createParagraphBullets (if adding bullet — must come before updateParagraphStyle
       so that the subsequent updateParagraphStyle can override the default indentation
       that createParagraphBullets sets, enabling nesting level > 0)
    2. updateParagraphStyle
    3. deleteParagraphBullets (if removing bullet)
    4. updateTextStyle ranges (right-to-left)
    """
    assert base_se.paragraph is not None
    assert desired_se.paragraph is not None

    base_para = base_se.paragraph
    desired_para = desired_se.paragraph

    # Quick check: text must match (text changes handled by gap processing)
    if _para_text(base_se) != _para_text(desired_se):
        return []

    requests: list[dict[str, Any]] = []
    para_start = _el_start(base_se)
    para_end = _el_end(base_se)

    base_bullet = base_para.bullet
    desired_bullet = desired_para.bullet

    # 1. Bullet creation FIRST — so that updateParagraphStyle below can override
    #    the default indentation (enabling nesting level > 0 for new bullets).
    if base_bullet is None and desired_bullet is not None:
        requests.append(
            _make_create_paragraph_bullets(
                para_start, para_end, "BULLET_DISC_CIRCLE_SQUARE", segment_id, tab_id
            )
        )

    # 2. Paragraph-level style changes
    if not _styles_equal(base_para.paragraph_style, desired_para.paragraph_style):
        style_dict, fields = _compute_style_diff(
            base_para.paragraph_style, desired_para.paragraph_style, ParagraphStyle
        )
        if fields:
            requests.append(
                _make_update_paragraph_style(
                    para_start, para_end, style_dict, fields, segment_id, tab_id
                )
            )

    # 3. Bullet removal AFTER paragraph style (clearing style before removing bullet)
    if base_bullet is not None and desired_bullet is None:
        requests.append(
            _make_delete_paragraph_bullets(para_start, para_end, segment_id, tab_id)
        )

    # 4. Text run style changes (processed right-to-left)
    text_style_reqs = _generate_text_style_updates(
        base_para, desired_para, para_start, segment_id, tab_id
    )
    requests.extend(text_style_reqs)

    return requests


def _generate_text_style_updates_positional(
    base_para: Paragraph,
    desired_para: Paragraph,
    para_start: int,
    segment_id: SegmentID,
    tab_id: TabID,
) -> list[dict[str, Any]]:
    """Position-based text style update when run counts differ.

    Used when base and desired have different numbers of text runs (e.g., due
    to link addition splitting the trailing \\n into a separate run). Aligns
    runs by character position rather than by index.

    For each desired run, finds the base style at that character offset and
    computes the style diff. Merges contiguous desired runs with identical
    changes into single updateTextStyle requests (right-to-left).
    """
    base_elems = base_para.elements or []
    desired_elems = desired_para.elements or []

    # Build [(start_offset, end_offset, style), ...] for base runs
    base_intervals: list[tuple[int, int, TextStyle | None]] = []
    offset = para_start
    for el in base_elems:
        if el.text_run is None:
            continue
        run_len = utf16_len(el.text_run.content or "")
        base_intervals.append((offset, offset + run_len, el.text_run.text_style))
        offset += run_len

    def _get_base_style_at(pos: int) -> TextStyle | None:
        for start, end, style in base_intervals:
            if start <= pos < end:
                return style
        return None

    # Process desired runs and find style diffs
    ranges: list[tuple[int, int, dict[str, Any], list[str]]] = []
    current_range: tuple[int, int, dict[str, Any], list[str]] | None = None

    offset = para_start
    for el in desired_elems:
        if el.text_run is None:
            continue
        run = el.text_run
        run_len = utf16_len(run.content or "")
        run_end = offset + run_len

        base_style = _get_base_style_at(offset)
        desired_style = run.text_style

        style_dict, fields = _compute_style_diff(base_style, desired_style, TextStyle)

        if not fields:
            if current_range:
                ranges.append(current_range)
                current_range = None
            offset = run_end
            continue

        if (
            current_range is not None
            and current_range[1] == offset
            and current_range[2] == style_dict
            and current_range[3] == fields
        ):
            current_range = (current_range[0], run_end, style_dict, fields)
        else:
            if current_range:
                ranges.append(current_range)
            current_range = (offset, run_end, style_dict, fields)

        offset = run_end

    if current_range:
        ranges.append(current_range)

    requests: list[dict[str, Any]] = []
    for start, end, style_dict, fields in reversed(ranges):
        requests.append(
            _make_update_text_style(start, end, style_dict, fields, segment_id, tab_id)
        )
    return requests


def _generate_text_style_updates(
    base_para: Paragraph,
    desired_para: Paragraph,
    para_start: int,
    segment_id: SegmentID,
    tab_id: TabID,
) -> list[dict[str, Any]]:
    """Generate text style update requests for text runs.

    Merges contiguous runs with identical style changes into single requests.
    Processes right-to-left (highest index first).

    When base and desired have different run counts (e.g., due to link addition
    splitting the trailing \\n), falls back to position-based alignment.
    """
    base_elems = base_para.elements or []
    desired_elems = desired_para.elements or []

    # Extract text runs only (filter to elements that have text_run)
    base_runs = [el for el in base_elems if el.text_run]
    desired_runs = [el for el in desired_elems if el.text_run]

    # Run count mismatch — fall back to position-based comparison
    if len(base_runs) != len(desired_runs):
        return _generate_text_style_updates_positional(
            base_para, desired_para, para_start, segment_id, tab_id
        )

    # Compute style update ranges (with merging)
    ranges: list[tuple[int, int, dict[str, Any], list[str]]] = []
    current_range: tuple[int, int, dict[str, Any], list[str]] | None = None

    offset = para_start
    for base_elem, desired_elem in zip(base_runs, desired_runs, strict=False):
        base_run = base_elem.text_run
        desired_run = desired_elem.text_run
        assert base_run is not None
        assert desired_run is not None

        # Verify text match
        if base_run.content != desired_run.content:
            raise ReconcileError(
                f"Text content mismatch in matched paragraph run: "
                f"{base_run.content!r} != {desired_run.content!r}. "
                f"This indicates a bug in the upstream text alignment."
            )

        # Compute style diff
        style_dict, fields = _compute_style_diff(
            base_run.text_style, desired_run.text_style, TextStyle
        )

        run_len = utf16_len(base_run.content or "")
        run_end = offset + run_len

        if not fields:
            # No style change for this run
            if current_range:
                ranges.append(current_range)
                current_range = None
            offset = run_end
            continue

        # Try to merge with current range
        if (
            current_range is not None
            and current_range[1] == offset  # contiguous
            and current_range[2] == style_dict  # same style changes
            and current_range[3] == fields  # same field mask
        ):
            # Extend range
            current_range = (current_range[0], run_end, style_dict, fields)
        else:
            # Start new range
            if current_range:
                ranges.append(current_range)
            current_range = (offset, run_end, style_dict, fields)

        offset = run_end

    if current_range:
        ranges.append(current_range)

    # Generate requests right-to-left
    requests: list[dict[str, Any]] = []
    for start, end, style_dict, fields in reversed(ranges):
        requests.append(
            _make_update_text_style(start, end, style_dict, fields, segment_id, tab_id)
        )

    return requests
