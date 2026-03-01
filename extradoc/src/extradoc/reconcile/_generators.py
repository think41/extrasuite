"""Generate batchUpdate request dicts from aligned StructuralElements.

Processes the alignment in a single right-to-left pass:
- MATCHED elements: generate in-place update requests (paragraph style,
  table structural diff with recursive cell descent)
- Consecutive DELETE/ADD slots: delete the old content, insert the new
  content at the right anchor's position

All operations are collected with their base-document positions, then
sorted right-to-left before flattening, so that later operations in the
request list always target lower indices and never invalidate earlier ones.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from extradoc.api_types import SegmentID, TabID

from extradoc.api_types._generated import (
    List,
    NestingLevelGlyphType,
    ParagraphStyle,
    StructuralElement,
    TextStyle,
)
from extradoc.indexer import utf16_len
from extradoc.reconcile._alignment import (
    AlignedElement,
    AlignmentOp,
    align_sequences,
    align_structural_elements,
)
from extradoc.reconcile._exceptions import ReconcileError
from extradoc.reconcile._extractors import (
    column_fingerprint,
    extract_plain_text_from_paragraph,
    row_fingerprint,
)

if TYPE_CHECKING:
    from extradoc.api_types._generated import (
        Paragraph,
        Table,
        TableCell,
        TableRow,
    )


# ---------------------------------------------------------------------------
# Bullet preset inference
# ---------------------------------------------------------------------------

# Maps level-0 glyphType to the createParagraphBullets preset string
_GLYPH_TYPE_TO_PRESET: dict[str, str] = {
    "DECIMAL": "NUMBERED_DECIMAL_NESTED",
    "UPPER_ALPHA": "NUMBERED_UPPERALPHA_ALPHA_ROMAN",
    "ALPHA": "NUMBERED_DECIMAL_ALPHA_ROMAN",
    "UPPER_ROMAN": "NUMBERED_UPPERROMAN_UPPERALPHA_DECIMAL",
    "ROMAN": "NUMBERED_UPPERROMAN_UPPERALPHA_DECIMAL",
    "ZERO_DECIMAL": "NUMBERED_ZERODECIMAL_ALPHA_ROMAN",
}

# Maps level-0 glyphSymbol to the createParagraphBullets preset string
_GLYPH_SYMBOL_TO_PRESET: dict[str, str] = {
    "●": "BULLET_DISC_CIRCLE_SQUARE",
    "❖": "BULLET_DIAMONDX_ARROW3D_SQUARE",
    "☐": "BULLET_CHECKBOX",
    "➔": "BULLET_ARROW_DIAMOND_DISC",
    "★": "BULLET_STAR_CIRCLE_SQUARE",
    "➢": "BULLET_ARROW3D_CIRCLE_SQUARE",
    "◀": "BULLET_LEFTTRIANGLE_DIAMOND_DISC",
}

_DEFAULT_BULLET_PRESET = "BULLET_DISC_CIRCLE_SQUARE"


def _infer_bullet_preset(
    list_id: str | None,
    lists: dict[str, List] | None,
) -> str:
    """Infer the createParagraphBullets preset from the desired document's list definition.

    Reads the first NestingLevel to detect whether the list is numbered
    (glyphType set to a real type), a checkbox (GLYPH_TYPE_UNSPECIFIED), or
    unordered (glyphSymbol set). Falls back to BULLET_DISC_CIRCLE_SQUARE for
    any missing or unrecognised data.
    """
    if not list_id or not lists or list_id not in lists:
        return _DEFAULT_BULLET_PRESET

    list_obj = lists[list_id]
    lp = list_obj.list_properties
    if not lp:
        return _DEFAULT_BULLET_PRESET
    nesting = lp.nesting_levels
    if not nesting:
        return _DEFAULT_BULLET_PRESET

    level_0 = nesting[0]
    glyph_type = level_0.glyph_type
    glyph_symbol = level_0.glyph_symbol

    # Numbered list: a real glyphType is set (not NONE / GLYPH_TYPE_UNSPECIFIED)
    if glyph_type and glyph_type not in (
        NestingLevelGlyphType.GLYPH_TYPE_UNSPECIFIED,
        NestingLevelGlyphType.NONE,
    ):
        return _GLYPH_TYPE_TO_PRESET.get(glyph_type.value, "NUMBERED_DECIMAL_NESTED")

    # Checkbox: GLYPH_TYPE_UNSPECIFIED with no glyph symbol
    if glyph_type == NestingLevelGlyphType.GLYPH_TYPE_UNSPECIFIED:
        return "BULLET_CHECKBOX"

    # Unordered: glyph symbol determines the preset
    if glyph_symbol:
        return _GLYPH_SYMBOL_TO_PRESET.get(glyph_symbol, _DEFAULT_BULLET_PRESET)

    return _DEFAULT_BULLET_PRESET


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


def _table_structural_size(table: Table) -> int:
    """Compute the index footprint (endIndex - startIndex) of a table element.

    = 2 (table start/end markers)
      + R (one row-start marker per row)
      + R*C (one cell-start marker per cell)
      + sum of cell content sizes (at least 1 per cell for the trailing \\n)
    """
    total = 2  # table start + end markers
    for row in table.table_rows or []:
        total += 1  # row marker
        for cell in row.table_cells or []:
            total += 1  # cell marker
            ct = _cell_text(cell)
            total += utf16_len(ct) if ct else 1
    return total


# ---------------------------------------------------------------------------
# Style comparison utilities
# ---------------------------------------------------------------------------

# ParagraphStyle fields that are server-managed and cannot be set via the API.
# Attempting to include them in updateParagraphStyle fields causes a 400 error.
_PARA_STYLE_READONLY_FIELDS: frozenset[str] = frozenset(
    {
        "headingId",  # assigned by server when namedStyleType=HEADING_*
    }
)


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

    # Skip read-only ParagraphStyle fields — they are server-managed and
    # the API returns 400 if they appear in the updateParagraphStyle field mask.
    if style_type is ParagraphStyle:
        all_api_names -= _PARA_STYLE_READONLY_FIELDS

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
    desired_lists: dict[str, List] | None = None,
) -> list[dict[str, Any]]:
    """Generate batchUpdate requests from an alignment.

    Processes the alignment in a single right-to-left pass:
    - MATCHED elements: generate in-place update requests (paragraph style,
      table structural diff with recursive cell descent)
    - Consecutive DELETE/ADD slots: delete the old content, insert the new
      content at the right anchor's position

    All operations are collected with their base-document positions, then
    sorted right-to-left before flattening, so that later operations in the
    request list always target lower indices and never invalidate earlier ones.
    """
    # Check for unsupported TOC changes upfront
    for aligned in alignment:
        el = aligned.desired_element or aligned.base_element
        if el and el.table_of_contents is not None:
            if aligned.op in (AlignmentOp.ADDED, AlignmentOp.DELETED):
                raise ReconcileError(
                    "tableOfContents is read-only and cannot be added or removed"
                )
            continue

    operations: list[tuple[int, list[dict[str, Any]]]] = []
    left_anchor: StructuralElement | None = None
    i = 0

    while i < len(alignment):
        ae = alignment[i]

        if ae.op == AlignmentOp.MATCHED:
            base_el = ae.base_element
            desired_el = ae.desired_element
            if base_el and desired_el:
                if _is_table(base_el) and _is_table(desired_el):
                    reqs = _generate_table_diff(
                        base_el, desired_el, segment_id, tab_id, desired_lists
                    )
                    if reqs:
                        operations.append((_el_end(base_el) - 1, reqs))
                elif _is_paragraph(base_el) and _is_paragraph(desired_el):
                    reqs = _generate_paragraph_style_diff(
                        base_el, desired_el, segment_id, tab_id, desired_lists
                    )
                    if reqs:
                        operations.append((_el_start(base_el), reqs))
            left_anchor = base_el
            i += 1

        else:
            # Collect the full slot: all consecutive DELETED/ADDED elements
            deletes: list[AlignedElement] = []
            adds: list[AlignedElement] = []
            while i < len(alignment) and alignment[i].op in (
                AlignmentOp.DELETED,
                AlignmentOp.ADDED,
            ):
                if alignment[i].op == AlignmentOp.DELETED:
                    deletes.append(alignment[i])
                else:
                    adds.append(alignment[i])
                i += 1

            # Right anchor = next MATCH element (None if trailing)
            right_anchor: StructuralElement | None = None
            if i < len(alignment) and alignment[i].op == AlignmentOp.MATCHED:
                right_anchor = alignment[i].base_element

            # Determine sort position for this slot.
            # Trailing slots (no right_anchor, no deletes) with a non-sectionbreak
            # left_anchor use _el_end(left_anchor) so they sort ABOVE any adjacent
            # inner slot at _el_start(right_anchor) = _el_end(left_anchor) - 1.
            # Right-to-left ordering then runs the trailing slot first, preventing
            # the inner slot from displacing the trailing slot's insert position.
            if deletes and deletes[0].base_element:
                pos = _el_start(deletes[0].base_element)
            elif right_anchor:
                pos = _el_start(right_anchor)
            elif left_anchor and not _is_section_break(left_anchor):
                pos = _el_end(left_anchor)
            else:
                pos = 1

            if right_anchor is not None:
                # Special case: single table DELETE + single table ADD in an inner slot.
                # Route to in-place table diff instead of insertTable, which would create
                # a spurious \n before the new table that cannot be deleted (API constraint).
                if (
                    len(deletes) == 1
                    and len(adds) == 1
                    and deletes[0].base_element is not None
                    and adds[0].desired_element is not None
                    and _is_table(deletes[0].base_element)
                    and _is_table(adds[0].desired_element)
                ):
                    reqs = _generate_table_diff(
                        deletes[0].base_element,
                        adds[0].desired_element,
                        segment_id,
                        tab_id,
                        desired_lists,
                    )
                    # Use the same pos convention as MATCH-table operations
                    pos = _el_end(deletes[0].base_element) - 1
                else:
                    reqs = _process_slot_inner(
                        left_anchor,
                        deletes,
                        adds,
                        right_anchor,
                        segment_id,
                        tab_id,
                        desired_lists,
                    )
            else:
                reqs = _process_slot_trailing(
                    left_anchor,
                    deletes,
                    adds,
                    segment_id,
                    tab_id,
                    desired_lists,
                )
            if reqs:
                operations.append((pos, reqs))

    # Sort right-to-left, then flatten
    operations.sort(key=lambda x: x[0], reverse=True)
    result: list[dict[str, Any]] = []
    for _, reqs in operations:
        result.extend(reqs)
    return result


# ---------------------------------------------------------------------------
# Slot processing — inner slot
# ---------------------------------------------------------------------------


def _process_slot_inner(
    left_anchor: StructuralElement | None,
    deletes: list[AlignedElement],
    adds: list[AlignedElement],
    right_anchor: StructuralElement,
    segment_id: SegmentID,
    tab_id: TabID,
    desired_lists: dict[str, List] | None = None,
) -> list[dict[str, Any]]:
    """Process a slot between two MATCH anchors (inner gap).

    DELETE: merge all deleted elements into a single deleteContentRange.
    INSERT: insert each add in reversed document order at right_anchor's start.

    Table handling — spurious \\n fix:
      insertTable(idx) always inserts \\n at idx, placing the table after it.
      When idx is a paragraph start the \\n lands BEFORE the table and cannot
      be deleted (API forbids deleting the \\n immediately before a table).
      Instead, the paragraph inserted BEFORE the table in document order
      (processed AFTER the table in the reversed loop) omits its trailing \\n;
      the spurious \\n from insertTable becomes that paragraph's trailing \\n.

      spurious_pending tracks whether a table was the last element processed
      in the reversed loop.  When True, the next paragraph strips its \\n.
    """
    # --- Validate ---
    for ae in deletes:
        el = ae.base_element
        if el and _is_section_break(el):
            raise ReconcileError("Section break deletion is not supported")
    for ae in adds:
        el = ae.desired_element
        if el and _is_section_break(el):
            raise ReconcileError(
                "Section break insertion is not supported by reconcile()"
            )
        if el and _is_paragraph(el) and _has_non_text_elements(el):
            raise ReconcileError(
                "Cannot insert paragraph containing non-text elements "
                "(pageBreak, horizontalRule, inlineObject, footnoteReference). "
                "Use the appropriate API requests directly."
            )

    # --- INSERT must come before DELETE ---
    # delete_end == _el_start(right_anchor) == insert_idx (they are adjacent in
    # the base document), so the ranges do not overlap.  Inserting first at
    # insert_idx leaves the delete range [del_start, insert_idx) intact; then
    # deleting that range does not affect the already-inserted content (which
    # sits at or after insert_idx in the modified document).
    insert_reqs: list[dict[str, Any]] = []

    # --- INSERT ---
    filtered = _filter_trailing_empty_paras(adds) if adds else []
    if filtered:
        # Insertion point: right anchor's start (or its end for sectionbreaks,
        # since index 0 is invalid — insertText requires index >= 1).
        if _is_section_break(right_anchor):
            insert_idx = _el_end(right_anchor)  # = 1
        else:
            insert_idx = _el_start(right_anchor)

        # Special case: first doc-order add is a table, and left_anchor is a
        # real paragraph (not a sectionbreak).
        #
        # insertTable(insert_idx) places a spurious \n at insert_idx BEFORE the
        # table, and the API forbids deleting \n immediately before a table.
        # Fix: insert at _el_end(left_anchor) - 1 (left_anchor's own trailing \n)
        # so that the displaced \n ends up AFTER the table — that IS the required
        # post-table <p/>, so we no longer need to delete it.
        first_add_is_table = (
            _is_table(filtered[0].desired_element)
            if filtered[0].desired_element
            else False
        )
        if (
            first_add_is_table
            and left_anchor is not None
            and not _is_section_break(left_anchor)
        ):
            first_table_el = filtered[0].desired_element
            assert first_table_el is not None and first_table_el.table is not None
            remaining_adds = filtered[1:]

            # Insert the first table at left_anchor's \n position.
            table_insert_idx = _el_end(left_anchor) - 1

            # Process remaining elements (doc order [1:]) in reversed order.
            # Pure-table sequences: all remaining tables go at table_insert_idx
            # (left_anchor's \n), just like the first table.  This ensures
            # consecutive tables produce exactly one empty paragraph between
            # them (instead of two).
            # Mixed sequences (tables + paragraphs): tables fall back to
            # insert_idx so that paragraphs can be inserted at insert_idx
            # without hitting a table's start index.
            remaining_only_tables = all(
                _is_table(ae.desired_element)
                for ae in remaining_adds
                if ae.desired_element is not None
            )
            spurious_pending = False
            for ae in reversed(remaining_adds):
                el = ae.desired_element
                assert el is not None
                if _is_table(el):
                    assert el.table is not None
                    table_pos = (
                        table_insert_idx if remaining_only_tables else insert_idx
                    )
                    insert_reqs.extend(
                        _generate_insert_table_with_content(
                            el.table, table_pos, segment_id, tab_id, desired_lists
                        )
                    )
                    spurious_pending = True
                elif _is_paragraph(el):
                    text = _para_text(el)
                    if not text:
                        continue
                    if spurious_pending:
                        text = text.rstrip("\n")
                        spurious_pending = False
                    if text:
                        insert_reqs.append(
                            _make_insert_text(text, insert_idx, segment_id, tab_id)
                        )
            insert_reqs.extend(
                _generate_insert_table_with_content(
                    first_table_el.table,
                    table_insert_idx,
                    segment_id,
                    tab_id,
                    desired_lists,
                )
            )

            # The displaced \n is the required post-table <p/> — do NOT delete it.
            # table_size_extra=1: the displaced \n occupies 1 char that must be
            # accounted for in style request position arithmetic.
            insert_reqs.extend(
                _style_reqs_for_added_paras(
                    filtered,
                    table_insert_idx + 1,
                    segment_id,
                    tab_id,
                    desired_lists,
                    table_size_extra=1,
                )
            )

            # When there are deletes, they must run BEFORE insertTable.
            # insertTable targets table_insert_idx (< delete range), so if insert
            # ran first the delete would target table cells instead of old content.
            delete_reqs_inner: list[dict[str, Any]] = []
            if deletes:
                first_del_el = deletes[0].base_element
                last_del_el = deletes[-1].base_element
                assert first_del_el is not None and last_del_el is not None
                delete_start = _el_start(first_del_el)
                delete_end = _el_end(last_del_el)
                if _is_table(right_anchor):
                    delete_end -= 1
                if delete_start < delete_end:
                    delete_reqs_inner.append(
                        _make_delete_range(delete_start, delete_end, segment_id, tab_id)
                    )
            return delete_reqs_inner + insert_reqs
        else:
            # Sub-case: right_anchor is a table and there are deletes.
            # insertText at _el_start(right_anchor) is invalid (table start is not
            # inside any paragraph). Fix: delete first (protecting the \n immediately
            # before the table), then insert at the protected \n's new position.
            if _is_table(right_anchor) and deletes:
                first_del_el = deletes[0].base_element
                last_del_el = deletes[-1].base_element
                assert first_del_el is not None and last_del_el is not None
                del_start = _el_start(first_del_el)
                del_end = (
                    _el_end(last_del_el) - 1
                )  # protect \n immediately before table
                del_reqs_inner: list[dict[str, Any]] = []
                if del_start < del_end:
                    del_reqs_inner.append(
                        _make_delete_range(del_start, del_end, segment_id, tab_id)
                    )
                # After delete, protected \n is at del_start (the new insert point).
                tbl_insert_idx = del_start
                spurious_pending = False
                first_in_reversed = True
                for ae in reversed(filtered):
                    el = ae.desired_element
                    assert el is not None
                    if _is_table(el):
                        assert el.table is not None
                        insert_reqs.extend(
                            _generate_insert_table_with_content(
                                el.table,
                                tbl_insert_idx,
                                segment_id,
                                tab_id,
                                desired_lists,
                            )
                        )
                        spurious_pending = True
                        first_in_reversed = False
                    elif _is_paragraph(el):
                        text = _para_text(el)
                        if not text:
                            continue
                        if spurious_pending:
                            text = text.rstrip("\n")
                            spurious_pending = False
                        elif first_in_reversed:
                            # Last para in doc order: the protected \n acts as its
                            # trailing \n, so strip the explicit trailing \n.
                            text = text.rstrip("\n")
                            first_in_reversed = False
                        if text:
                            insert_reqs.append(
                                _make_insert_text(
                                    text, tbl_insert_idx, segment_id, tab_id
                                )
                            )
                insert_reqs.extend(
                    _style_reqs_for_added_paras(
                        filtered,
                        tbl_insert_idx,
                        segment_id,
                        tab_id,
                        desired_lists,
                        table_size_extra=1,
                    )
                )
                return del_reqs_inner + insert_reqs

            # Normal case: reversed insertion with spurious_pending for tables.
            spurious_pending = False
            for ae in reversed(filtered):
                el = ae.desired_element
                assert el is not None
                if _is_table(el):
                    assert el.table is not None
                    insert_reqs.extend(
                        _generate_insert_table_with_content(
                            el.table, insert_idx, segment_id, tab_id, desired_lists
                        )
                    )
                    spurious_pending = True
                elif _is_paragraph(el):
                    text = _para_text(el)
                    if not text:
                        continue
                    if spurious_pending:
                        # The spurious \n from the preceding insertTable call becomes
                        # this paragraph's trailing \n — strip it from the insert text.
                        text = text.rstrip("\n")
                        spurious_pending = False
                    if text:
                        insert_reqs.append(
                            _make_insert_text(text, insert_idx, segment_id, tab_id)
                        )

            # Style requests for added paragraphs.
            # table_size_extra=0: the spurious \n is absorbed by the preceding
            # paragraph, so the table's position immediately follows that paragraph.
            insert_reqs.extend(
                _style_reqs_for_added_paras(
                    filtered,
                    insert_idx,
                    segment_id,
                    tab_id,
                    desired_lists,
                    table_size_extra=0,
                )
            )

    # --- DELETE ---
    delete_reqs: list[dict[str, Any]] = []
    if deletes:
        first_del_el = deletes[0].base_element
        last_del_el = deletes[-1].base_element
        assert first_del_el is not None and last_del_el is not None
        delete_start = _el_start(first_del_el)
        delete_end = _el_end(last_del_el)
        # Cannot delete the \n immediately before a table (API constraint)
        if _is_table(right_anchor):
            delete_end -= 1
        if delete_start < delete_end:
            delete_reqs.append(
                _make_delete_range(delete_start, delete_end, segment_id, tab_id)
            )

    return insert_reqs + delete_reqs


# ---------------------------------------------------------------------------
# Slot processing — trailing slot
# ---------------------------------------------------------------------------


def _process_slot_trailing(
    left_anchor: StructuralElement | None,
    deletes: list[AlignedElement],
    adds: list[AlignedElement],
    segment_id: SegmentID,
    tab_id: TabID,
    desired_lists: dict[str, List] | None = None,
) -> list[dict[str, Any]]:
    """Process a trailing slot (no right anchor). Must protect segment-final \\n."""
    requests: list[dict[str, Any]] = []
    real_deletes = deletes
    real_adds = adds

    # Validate: no section break deletes or adds
    for ae in real_deletes:
        if ae.base_element and _is_section_break(ae.base_element):
            raise ReconcileError(
                "Section break deletion is not supported by reconcile()"
            )
    for ae in real_adds:
        if ae.desired_element and _is_section_break(ae.desired_element):
            raise ReconcileError(
                "Section break insertion is not supported by reconcile()"
            )

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

        if left_anchor and not _is_section_break(left_anchor):
            left_end = _el_end(left_anchor)
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
                    left_anchor,
                    real_deletes,
                    real_adds,
                    segment_id,
                    tab_id,
                    desired_lists,
                )
            )
            # Compute insert_idx (mirrors _process_trailing_adds_with_tables logic)
            first_del_el = real_deletes[0].base_element if real_deletes else None
            if real_deletes:
                if left_anchor and not _is_section_break(left_anchor):
                    _insert_idx = _el_end(left_anchor) - 1
                else:
                    assert first_del_el is not None
                    _insert_idx = _el_start(first_del_el)
            else:
                if left_anchor and not _is_section_break(left_anchor):
                    _insert_idx = _el_end(left_anchor) - 1
                else:
                    _insert_idx = _el_end(left_anchor) if left_anchor else 1
            # If left_anchor is a non-sectionbreak paragraph, paragraphs are inserted
            # with a leading \n, so the first para's actual start is insert_idx + 1
            if left_anchor and not _is_section_break(left_anchor):
                _first_para_start = _insert_idx + 1
            else:
                _first_para_start = _insert_idx
            requests.extend(
                _style_reqs_for_added_paras(
                    real_adds,
                    _first_para_start,
                    segment_id,
                    tab_id,
                    desired_lists,
                    table_size_extra=0,
                )
            )
        else:
            # Pure paragraph adds (original Phase 1 logic)
            requests.extend(
                _process_trailing_paragraph_adds(
                    left_anchor,
                    real_deletes,
                    real_adds,
                    segment_id,
                    tab_id,
                    desired_lists,
                )
            )

    return requests


def _style_reqs_for_added_paras(
    real_adds: list[AlignedElement],
    first_para_actual_start: int,
    segment_id: SegmentID,
    tab_id: TabID,
    desired_lists: dict[str, List] | None,
    table_size_extra: int = 1,
) -> list[dict[str, Any]]:
    """Generate style requests for ADDED paragraphs using actual positions.

    first_para_actual_start is the actual position of the first added paragraph
    in the modified base doc after the gap's insertText has been applied.
    Subsequent paragraph positions are computed by accumulating UTF-16 lengths.

    Consecutive list items with the same list_id (and no intervening non-paragraph
    elements) are batched into a single createParagraphBullets call covering their
    full range.  This ensures they form one list with sequential numbering (1, 2,
    3 …) rather than separate 1-item lists all showing "1.".

    Results are sorted right-to-left so they are safe to interleave with gap ops.
    """
    # --- Phase 1: compute actual positions and record inter-element gaps ---
    # Each entry: (actual_start, actual_end, element, gap_before)
    # gap_before=True means a non-paragraph element (table, etc.) appeared
    # between this paragraph and the previous one in real_adds.
    para_records: list[tuple[int, int, StructuralElement, bool]] = []
    offset = first_para_actual_start
    had_non_para = False
    for add in real_adds:
        el = add.desired_element
        if not el or not _is_paragraph(el):
            if el and _is_table(el) and el.table:
                # Advance offset by table footprint + extra (auto-trailing paragraph).
                # Inner gap (_insert_adds_individually): table_size_extra=1 because
                # insertTable's separator \n stays as a separate character.
                # Trailing gap (_process_trailing_adds_with_tables): table_size_extra=0
                # because the separator \n is absorbed into the preceding run's text.
                offset += _table_structural_size(el.table) + table_size_extra
            had_non_para = True
            continue
        para_text = _para_text(el)
        para_len = utf16_len(para_text)
        actual_start = offset
        actual_end = offset + para_len
        offset = actual_end
        para_records.append((actual_start, actual_end, el, had_non_para))
        had_non_para = False

    # --- Phase 2: group bullet items, emit batched + individual style requests ---
    style_ops: list[tuple[int, list[dict[str, Any]]]] = []
    i = 0
    while i < len(para_records):
        actual_start, actual_end, el, _gap = para_records[i]
        assert el.paragraph is not None
        bullet = el.paragraph.bullet

        if bullet is not None:
            # Collect a run of consecutive list items sharing the same list_id.
            list_id = bullet.list_id
            preset = _infer_bullet_preset(list_id, desired_lists)
            group: list[tuple[int, int, StructuralElement]] = [
                (actual_start, actual_end, el)
            ]
            j = i + 1
            while j < len(para_records):
                n_start, n_end, n_el, n_gap = para_records[j]
                assert n_el.paragraph is not None
                n_bullet = n_el.paragraph.bullet
                if n_bullet is not None and n_bullet.list_id == list_id and not n_gap:
                    group.append((n_start, n_end, n_el))
                    j += 1
                else:
                    break

            # One createParagraphBullets spanning the whole group, followed by
            # per-item updateParagraphStyle / updateTextStyle (right-to-left within
            # the group so that index stability is preserved).
            # All of this is bundled into a SINGLE style_ops entry at g_start so
            # that createParagraphBullets is guaranteed to come before any of the
            # per-item style overrides — even after the outer right-to-left sort.
            g_start = group[0][0]
            g_end = group[-1][1]

            # Collect non-bullet reqs per item, then sort them right-to-left.
            group_item_ops: list[tuple[int, list[dict[str, Any]]]] = []
            for g_start_i, g_end_i, g_el in group:
                reqs = _generate_style_for_added_paragraph(
                    g_el, g_start_i, g_end_i, segment_id, tab_id, desired_lists
                )
                non_bullet = [r for r in reqs if "createParagraphBullets" not in r]
                if non_bullet:
                    group_item_ops.append((g_start_i, non_bullet))
            group_item_ops.sort(key=lambda x: x[0], reverse=True)

            group_reqs: list[dict[str, Any]] = [
                _make_create_paragraph_bullets(
                    g_start, g_end, preset, segment_id, tab_id
                )
            ]
            for _, item_reqs in group_item_ops:
                group_reqs.extend(item_reqs)

            style_ops.append((g_start, group_reqs))

            i = j
        else:
            # Non-list paragraph: generate all style reqs normally
            reqs = _generate_style_for_added_paragraph(
                el, actual_start, actual_end, segment_id, tab_id, desired_lists
            )
            if reqs:
                style_ops.append((actual_start, reqs))
            i += 1

    style_ops.sort(key=lambda x: x[0], reverse=True)
    result: list[dict[str, Any]] = []
    for _, reqs in style_ops:
        result.extend(reqs)
    return result


def _process_trailing_paragraph_adds(
    left_anchor: StructuralElement | None,
    real_deletes: list[AlignedElement],
    real_adds: list[AlignedElement],
    segment_id: SegmentID,
    tab_id: TabID,
    desired_lists: dict[str, List] | None = None,
) -> list[dict[str, Any]]:
    """Handle pure paragraph adds in a trailing gap (Phase 1 logic)."""
    first_del_el = real_deletes[0].base_element if real_deletes else None

    combined_text = _collect_add_text(real_adds)
    if not combined_text:
        return []

    if real_deletes:
        if left_anchor and not _is_section_break(left_anchor):
            insert_idx = _el_end(left_anchor) - 1
        else:
            assert first_del_el is not None
            insert_idx = _el_start(first_del_el)
    else:
        if left_anchor and not _is_section_break(left_anchor):
            insert_idx = _el_end(left_anchor) - 1
        else:
            insert_idx = _el_end(left_anchor) if left_anchor else 1

    if left_anchor and not _is_section_break(left_anchor):
        text_stripped = combined_text.rstrip("\n")
        insert_text = "\n" + text_stripped
    else:
        insert_text = combined_text.rstrip("\n")

    if not insert_text:
        return []

    requests: list[dict[str, Any]] = [
        _make_insert_text(insert_text, insert_idx, segment_id, tab_id)
    ]
    # The first added paragraph starts at insert_idx, unless insert_text begins
    # with a "\n" (which is the left anchor's moved \n, not part of the first para).
    has_leading_newline = insert_text.startswith("\n")
    first_para_start = insert_idx + (1 if has_leading_newline else 0)
    requests.extend(
        _style_reqs_for_added_paras(
            real_adds, first_para_start, segment_id, tab_id, desired_lists
        )
    )
    return requests


def _process_trailing_adds_with_tables(
    left_anchor: StructuralElement | None,
    real_deletes: list[AlignedElement],
    real_adds: list[AlignedElement],
    segment_id: SegmentID,
    tab_id: TabID,
    desired_lists: dict[str, List] | None = None,
) -> list[dict[str, Any]]:
    """Handle adds containing tables in a trailing gap.

    Tables in trailing position need special handling because
    insertTable automatically creates a trailing paragraph.

    Consecutive paragraphs (including empty ones) are collected into runs and
    inserted as a single combined insertText — identical to how
    _process_trailing_paragraph_adds works.  This ensures:
    - \\n separators between consecutive paragraphs are preserved
    - empty paragraphs are NOT silently dropped
    - _style_reqs_for_added_paras position tracking remains consistent

    For a sectionbreak left_anchor:
      - the first run in document order (last processed in reversed order)
        is inserted WITHOUT a leading \\n (it lands directly at insert_idx)
      - every subsequent run (after a table) is inserted WITH a leading \\n so
        that the table's auto-\\n separator is correctly consumed by the run

    For a non-sectionbreak left_anchor:
      - every run is inserted WITH a leading \\n (same as before)
    """
    first_del_el = real_deletes[0].base_element if real_deletes else None

    # Determine insert position
    if real_deletes:
        if left_anchor and not _is_section_break(left_anchor):
            insert_idx = _el_end(left_anchor) - 1
        else:
            assert first_del_el is not None
            insert_idx = _el_start(first_del_el)
    else:
        if left_anchor and not _is_section_break(left_anchor):
            insert_idx = _el_end(left_anchor) - 1
        else:
            insert_idx = _el_end(left_anchor) if left_anchor else 1

    # Filter out empty paragraphs that insertTable creates implicitly
    filtered_adds = _filter_trailing_empty_paras(real_adds)

    # Group filtered_adds into alternating paragraph-runs and tables.
    # A "run" is a maximal contiguous sequence of non-table elements.
    groups: list[tuple[str, list[AlignedElement] | AlignedElement]] = []
    current_run: list[AlignedElement] = []
    for add in filtered_adds:
        el = add.desired_element
        if el and _is_table(el):
            if current_run:
                groups.append(("paras", current_run))
                current_run = []
            groups.append(("table", add))
        else:
            current_run.append(add)
    if current_run:
        groups.append(("paras", current_run))

    non_sectionbreak = left_anchor and not _is_section_break(left_anchor)

    # Process groups in REVERSE document order (all inserts land at insert_idx).
    requests: list[dict[str, Any]] = []
    groups_reversed = list(reversed(groups))
    for idx, (group_type, group) in enumerate(groups_reversed):
        # idx==0 is the LAST group in document order (we iterate reversed).
        # is_first_in_document_order is True for the group that appears FIRST
        # in the document — the LAST item when iterating groups_reversed.
        is_first_in_document_order = idx == len(groups_reversed) - 1

        if group_type == "table":
            assert isinstance(group, AlignedElement)
            el = group.desired_element
            assert el is not None and el.table is not None
            table_reqs = _generate_insert_table_with_content(
                el.table, insert_idx, segment_id, tab_id, desired_lists
            )
            requests.extend(table_reqs)
            # The \n created by insertTable becomes an empty paragraph between
            # this table and the next element in document order.  We do NOT
            # delete it: the API forbids removing the \n immediately before a
            # table, and consistent with the inner-slot behaviour we accept one
            # empty paragraph between consecutive tables.
        else:
            assert isinstance(group, list)
            combined = _collect_add_text(group)
            if not combined:
                continue
            if non_sectionbreak:
                # Always prepend \n to separate from the left anchor (or from
                # the table that precedes this run in document order).
                insert_text = "\n" + combined.rstrip("\n")
            else:
                # Sectionbreak: the first run in document order needs NO leading
                # \n — it inserts directly at insert_idx into the existing
                # trailing paragraph.  Every other run (after a table) needs a
                # leading \n so the table's auto-\n is used as its terminator.
                if is_first_in_document_order:
                    insert_text = combined.rstrip("\n")
                else:
                    insert_text = "\n" + combined.rstrip("\n")
            if insert_text:
                requests.append(
                    _make_insert_text(insert_text, insert_idx, segment_id, tab_id)
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
# Table insertion with cell content
# ---------------------------------------------------------------------------


def _generate_insert_table_with_content(
    table: Table,
    insert_idx: int,
    segment_id: SegmentID,
    tab_id: TabID,
    desired_lists: dict[str, List] | None = None,
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

    # 2. Populate cells in reverse order via recursive cell reconciliation
    table_rows = table.table_rows or []
    for r in range(len(table_rows) - 1, -1, -1):
        row = table_rows[r]
        cells = row.table_cells or []
        for c in range(len(cells) - 1, -1, -1):
            cell = cells[c]
            # Cell content start: I + 4 + r*(1 + 2C) + 2c
            cell_content_idx = insert_idx + 4 + r * (1 + 2 * cols) + 2 * c
            pop_reqs = _populate_cell_at(
                cell, cell_content_idx, segment_id, tab_id, desired_lists
            )
            requests.extend(pop_reqs)

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
    desired_lists: dict[str, List] | None = None,
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
            base_se.table, desired_se.table, segment_id, tab_id, desired_lists
        )

    # Same shape (rows x cols) but different cell text — positional cell diff.
    # Avoids DELETE+ADD rows that would leave the table momentarily empty.
    base_rows_n = base_se.table.rows or 0
    base_cols_n = base_se.table.columns or 0
    desired_rows_n = desired_se.table.rows or 0
    desired_cols_n = desired_se.table.columns or 0
    if base_rows_n == desired_rows_n and base_cols_n == desired_cols_n:
        return _diff_table_same_shape(
            base_se, desired_se, segment_id, tab_id, desired_lists
        )

    return _diff_table_structural(
        base_se, desired_se, segment_id, tab_id, desired_lists
    )


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
    desired_lists: dict[str, List] | None = None,
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
                    base_se, desired_se, segment_id, tab_id, desired_lists
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


def _make_create_header(header_type: str) -> dict[str, Any]:
    """Create a header request.

    Args:
        header_type: "DEFAULT" or other header type

    Note:
        sectionBreakLocation is intentionally omitted. Specifying it (even with
        a valid index) causes a Google Docs API 500 error. Omitting it creates
        the default header, which is correct for "_base" segments.
    """
    return {"createHeader": {"type": header_type}}


def _make_delete_header(header_id: str, tab_id: TabID) -> dict[str, Any]:
    """Delete a header request."""
    req: dict[str, Any] = {"deleteHeader": {"headerId": header_id}}
    if tab_id:
        req["deleteHeader"]["tabId"] = tab_id
    return req


def _make_create_footer(footer_type: str) -> dict[str, Any]:
    """Create a footer request.

    Args:
        footer_type: "DEFAULT" or other footer type

    Note:
        sectionBreakLocation is intentionally omitted. Specifying it (even with
        a valid index) causes a Google Docs API 500 error. Omitting it creates
        the default footer, which is correct for "_base" segments.
    """
    return {"createFooter": {"type": footer_type}}


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


def _diff_table_same_shape(
    base_se: StructuralElement,
    desired_se: StructuralElement,
    segment_id: SegmentID,
    tab_id: TabID,
    desired_lists: dict[str, List] | None = None,
) -> list[dict[str, Any]]:
    """Diff tables with identical dimensions by positional cell matching.

    Called when base and desired have the same rows x cols but different text.
    Matches rows and columns positionally and calls _diff_row_cells for each row,
    which in turn calls _diff_single_cell_at → _reconcile_cell_content for each cell.
    This handles text and style changes in place without any row/column structural ops.

    Processes rows bottom-to-top for right-to-left index stability.
    """
    table_start = _el_start(base_se)
    base_table = base_se.table
    desired_table = desired_se.table
    assert base_table is not None
    assert desired_table is not None

    base_rows = base_table.table_rows or []
    desired_rows = desired_table.table_rows or []
    col_count = base_table.columns or 0

    # All columns match positionally (no inserts/deletes needed)
    col_alignment: list[tuple[AlignmentOp, int | None, int | None]] = [
        (AlignmentOp.MATCHED, c, c) for c in range(col_count)
    ]

    # Build row table for position tracking
    row_entries: list[_RowEntry] = []
    for r_idx, row in enumerate(base_rows):
        adj_len = _compute_adjusted_row_length(row, col_alignment)
        row_entries.append(_RowEntry(id=f"base_{r_idx}", length=adj_len))
    row_table = _RowTable(row_entries, table_start)

    requests: list[dict[str, Any]] = []

    # Process rows bottom-to-top so that earlier index positions are not
    # invalidated by operations on rows with higher indices.
    for r in range(len(base_rows) - 1, -1, -1):
        if r >= len(desired_rows):
            continue
        entry_idx = row_table.find(f"base_{r}")
        rs = row_table.row_start(entry_idx)
        cell_reqs, new_length = _diff_row_cells(
            base_rows[r],
            desired_rows[r],
            rs,
            col_alignment,
            segment_id,
            tab_id,
            desired_lists,
        )
        requests.extend(cell_reqs)
        row_table.entries[entry_idx].length = new_length

    return requests


def _diff_table_structural(
    base_se: StructuralElement,
    desired_se: StructuralElement,
    segment_id: SegmentID,
    tab_id: TabID,
    desired_lists: dict[str, List] | None = None,
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
                desired_lists,
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
                desired_lists,
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
    desired_lists: dict[str, List] | None = None,
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
                    base_cell,
                    desired_cell,
                    cell_start,
                    segment_id,
                    tab_id,
                    desired_lists,
                )
                requests.extend(cell_reqs)
        elif col_op == AlignmentOp.ADDED:
            assert desired_col_idx is not None
            if desired_col_idx < len(desired_cells):
                desired_cell = desired_cells[desired_col_idx]
                pop_reqs = _populate_cell_at(
                    desired_cell, cell_start, segment_id, tab_id, desired_lists
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
    desired_lists: dict[str, List] | None = None,
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
                desired_cells[c], cell_start, segment_id, tab_id, desired_lists
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


def _fake_empty_para(cell_start: int) -> StructuralElement:
    """Create a fake StructuralElement for an empty cell (just \\n at cell_start).

    Used as the base when a cell is newly inserted (no prior API content).
    The trailing \\n is the cell-boundary marker that generate_requests must preserve.
    """
    return StructuralElement.model_validate(
        {
            "paragraph": {"elements": [{"textRun": {"content": "\n"}}]},
            "startIndex": cell_start,
            "endIndex": cell_start + 1,
        }
    )


def _reconcile_cell_content(
    base_elements: list[StructuralElement],
    desired_elements: list[StructuralElement],
    segment_id: SegmentID,
    tab_id: TabID,
    desired_lists: dict[str, List] | None = None,
) -> list[dict[str, Any]]:
    """Reconcile table cell content via full recursion through generate_requests.

    Cell paragraphs share the body index space (real startIndex/endIndex from
    the API).  Calling generate_requests on the aligned cell content is identical
    to reconciling any other segment — gaps, style diffs, and the protection of
    the cell-final \\n all work through the same mechanism.
    """
    alignment = align_structural_elements(base_elements, desired_elements)
    return generate_requests(alignment, segment_id, tab_id, desired_lists)


def _diff_single_cell_at(
    base_cell: TableCell,
    desired_cell: TableCell,
    cell_start: int,  # noqa: ARG001 — kept for call-site symmetry with _populate_cell_at
    segment_id: SegmentID,
    tab_id: TabID,
    desired_lists: dict[str, List] | None = None,
) -> list[dict[str, Any]]:
    """Diff a single MATCHED cell using recursive cell reconciliation.

    The base cell's paragraphs carry real API startIndex/endIndex values, so
    cell_start is not used for index computation here — it is kept for
    call-site symmetry with _populate_cell_at.
    """
    return _reconcile_cell_content(
        base_cell.content or [],
        desired_cell.content or [],
        segment_id,
        tab_id,
        desired_lists,
    )


def _populate_cell_at(
    desired_cell: TableCell,
    cell_start: int,
    segment_id: SegmentID,
    tab_id: TabID,
    desired_lists: dict[str, List] | None = None,
) -> list[dict[str, Any]]:
    """Populate a newly-inserted empty cell (just \\n at cell_start) with desired content."""
    return _reconcile_cell_content(
        [_fake_empty_para(cell_start)],
        desired_cell.content or [],
        segment_id,
        tab_id,
        desired_lists,
    )


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


def _generate_style_for_added_paragraph(
    desired_se: StructuralElement,
    para_start: int,
    para_end: int,
    segment_id: SegmentID,
    tab_id: TabID,
    desired_lists: dict[str, List] | None = None,
) -> list[dict[str, Any]]:
    """Generate style requests for a freshly-inserted (ADDED) paragraph.

    Treats the base as having no styles (NORMAL_TEXT, no text formatting).
    para_start and para_end are the ACTUAL positions in the modified base doc
    (after the gap's insertText has been applied), computed by the caller using
    insert_idx + cumulative UTF-16 offsets.

    Returns requests in order:
    1. createParagraphBullets (if paragraph has a bullet)
    2. updateParagraphStyle (if style differs from defaults)
    3. updateTextStyle ranges (right-to-left)
    """
    assert desired_se.paragraph is not None
    desired_para = desired_se.paragraph

    requests: list[dict[str, Any]] = []
    desired_bullet = desired_para.bullet

    # 1. Bullet first (so updateParagraphStyle can override indentation)
    if desired_bullet is not None:
        preset = _infer_bullet_preset(desired_bullet.list_id, desired_lists)
        requests.append(
            _make_create_paragraph_bullets(
                para_start, para_end, preset, segment_id, tab_id
            )
        )

    # 2. Paragraph style (diff against None — emits all non-default fields)
    if desired_para.paragraph_style is not None:
        style_dict, fields = _compute_style_diff(
            None, desired_para.paragraph_style, ParagraphStyle
        )
        if fields:
            requests.append(
                _make_update_paragraph_style(
                    para_start, para_end, style_dict, fields, segment_id, tab_id
                )
            )

    # 3. Text run styles — compute run positions from para_start using UTF-16 lengths
    #    (cannot use desired element indices, which are in a different index space)
    desired_runs = [el for el in (desired_para.elements or []) if el.text_run]
    ranges: list[tuple[int, int, dict[str, Any], list[str]]] = []
    current_range: tuple[int, int, dict[str, Any], list[str]] | None = None
    run_offset = para_start

    for el in desired_runs:
        run = el.text_run
        assert run is not None
        run_len = utf16_len(run.content or "")
        run_start = run_offset
        run_end = run_offset + run_len
        run_offset = run_end

        style_dict, fields = _compute_style_diff(None, run.text_style, TextStyle)

        if not fields:
            if current_range:
                ranges.append(current_range)
                current_range = None
            continue

        if (
            current_range is not None
            and current_range[1] == run_start
            and current_range[2] == style_dict
            and current_range[3] == fields
        ):
            current_range = (current_range[0], run_end, style_dict, fields)
        else:
            if current_range:
                ranges.append(current_range)
            current_range = (run_start, run_end, style_dict, fields)

    if current_range:
        ranges.append(current_range)

    for start, end, style_dict, fields in reversed(ranges):
        requests.append(
            _make_update_text_style(start, end, style_dict, fields, segment_id, tab_id)
        )

    return requests


def _generate_paragraph_style_diff(
    base_se: StructuralElement,
    desired_se: StructuralElement,
    segment_id: SegmentID,
    tab_id: TabID,
    desired_lists: dict[str, List] | None = None,
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
        preset = _infer_bullet_preset(desired_bullet.list_id, desired_lists)
        requests.append(
            _make_create_paragraph_bullets(
                para_start, para_end, preset, segment_id, tab_id
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

    For each desired run, walks all overlapping base intervals and compares
    each sub-range independently against the desired style. This correctly
    handles cases like removing bold from a run that spans multiple base
    intervals (e.g., base has [bold][plain], desired has one plain run).

    Merges contiguous sub-ranges with identical changes into single
    updateTextStyle requests (right-to-left).
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

    def _get_base_intervals_for_range(
        run_start: int, run_end: int
    ) -> list[tuple[int, int, TextStyle | None]]:
        """Return sub-intervals of base that overlap [run_start, run_end)."""
        result = []
        for bstart, bend, bstyle in base_intervals:
            if bstart < run_end and bend > run_start:
                result.append((max(run_start, bstart), min(run_end, bend), bstyle))
        if not result:
            result.append((run_start, run_end, None))
        return result

    # Process desired runs: for each, walk all overlapping base sub-intervals
    ranges: list[tuple[int, int, dict[str, Any], list[str]]] = []
    current_range: tuple[int, int, dict[str, Any], list[str]] | None = None

    offset = para_start
    for el in desired_elems:
        if el.text_run is None:
            continue
        run = el.text_run
        run_len = utf16_len(run.content or "")
        run_end = offset + run_len
        desired_style = run.text_style

        for sub_start, sub_end, base_style in _get_base_intervals_for_range(
            offset, run_end
        ):
            style_dict, fields = _compute_style_diff(
                base_style, desired_style, TextStyle
            )

            if not fields:
                if current_range:
                    ranges.append(current_range)
                    current_range = None
            elif (
                current_range is not None
                and current_range[1] == sub_start
                and current_range[2] == style_dict
                and current_range[3] == fields
            ):
                current_range = (current_range[0], sub_end, style_dict, fields)
            else:
                if current_range:
                    ranges.append(current_range)
                current_range = (sub_start, sub_end, style_dict, fields)

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
