"""Diff engine for ExtraDoc XML.

Compares pristine and edited documents to generate minimal Google Docs
batchUpdate requests using a true diff algorithm.

The strategy is:
1. Parse both documents into desugared form
2. For each section, use sequence diffing to find changes
3. For modified elements, generate minimal update operations
4. Sort operations in descending index order for safe application
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .desugar import (
    Paragraph,
    Section,
    SpecialElement,
    Table,
    TableCell,
    desugar_document,
)
from .indexer import utf16_len
from .sequence_diff import (
    elements_match,
    sections_are_identical,
    sequence_diff,
)

# --- Helpers for style mapping ---


def _hex_to_rgb(color: str) -> dict[str, float]:
    """Convert #RRGGBB to Docs rgbColor dict."""
    color = color.lstrip("#")
    if len(color) != 6:
        return {}
    r = int(color[0:2], 16) / 255.0
    g = int(color[2:4], 16) / 255.0
    b = int(color[4:6], 16) / 255.0
    return {"red": r, "green": g, "blue": b}


def _styles_to_text_style(styles: dict[str, str]) -> tuple[dict[str, Any], str] | None:
    """Convert run styles to Google Docs textStyle + fields."""
    text_style: dict[str, Any] = {}
    fields: list[str] = []

    def add(field: str, value: Any) -> None:
        fields.append(field)
        text_style[field.split(".")[-1]] = value

    if styles.get("bold") == "1":
        add("bold", True)
    if styles.get("italic") == "1":
        add("italic", True)
    if styles.get("underline") == "1":
        add("underline", True)
    if styles.get("strikethrough") == "1":
        add("strikethrough", True)
    if styles.get("superscript") == "1":
        add("baselineOffset", "SUPERSCRIPT")
    if styles.get("subscript") == "1":
        add("baselineOffset", "SUBSCRIPT")
    if "link" in styles:
        text_style["link"] = {"url": styles["link"]}
        fields.append("link")
    if "color" in styles:
        rgb = _hex_to_rgb(styles["color"])
        if rgb:
            text_style["foregroundColor"] = {"color": {"rgbColor": rgb}}
            fields.append("foregroundColor")
    if "bg" in styles:
        rgb = _hex_to_rgb(styles["bg"])
        if rgb:
            text_style["backgroundColor"] = {"color": {"rgbColor": rgb}}
            fields.append("backgroundColor")
    if "font" in styles:
        text_style["weightedFontFamily"] = {"fontFamily": styles["font"]}
        fields.append("weightedFontFamily")
    if "size" in styles:
        # size like "11pt"
        try:
            size_pt = float(styles["size"].rstrip("pt"))
            text_style["fontSize"] = {"magnitude": size_pt, "unit": "PT"}
            fields.append("fontSize")
        except ValueError:
            pass

    if text_style:
        return text_style, ",".join(fields)
    return None


def _full_run_text_style(styles: dict[str, str]) -> tuple[dict[str, Any], str]:
    """Return a complete textStyle for a run, resetting unspecified props."""
    ts: dict[str, Any] = {}
    fields: list[str] = []

    def add(name: str, value: Any) -> None:
        ts[name] = value
        fields.append(name)

    add("bold", styles.get("bold") == "1")
    add("italic", styles.get("italic") == "1")
    add("underline", styles.get("underline") == "1")
    add("strikethrough", styles.get("strikethrough") == "1")

    if styles.get("superscript") == "1":
        add("baselineOffset", "SUPERSCRIPT")
    elif styles.get("subscript") == "1":
        add("baselineOffset", "SUBSCRIPT")
    else:
        add("baselineOffset", "NONE")

    link = styles.get("link")
    if link:
        add("link", {"url": link})
    else:
        add("link", None)

    return ts, ",".join(fields)


@dataclass
class DiffOperation:
    """A single diff operation."""

    op_type: str  # "insert", "delete", "replace", "update_style"
    index: int  # Primary index for sorting (descending)
    end_index: int = 0  # For delete/replace operations
    content: str = ""  # For insert operations
    text_style: dict[str, Any] | None = None  # For style updates
    paragraph_style: dict[str, Any] | None = None  # For paragraph style updates
    segment_id: str | None = None  # For headers/footers/footnotes
    tab_id: str | None = None  # For multi-tab documents
    bullet_preset: str | None = None  # For list operations
    fields: str = ""  # Field mask for style updates
    sequence: int = 0  # Generation sequence for stable sorting of same-index ops
    change_group: int = 0  # Which change block this operation belongs to
    is_post_insert: bool = False  # True for style ops that must run AFTER their insert


# Global sequence counter for stable sorting
_sequence_counter = 0


def _next_sequence() -> int:
    """Get next sequence number for operation ordering."""
    global _sequence_counter
    _sequence_counter += 1
    return _sequence_counter


def diff_documents(
    pristine_xml: str,
    current_xml: str,
    pristine_styles: str | None = None,
    current_styles: str | None = None,
) -> list[dict[str, Any]]:
    """Generate minimal batchUpdate requests via true diff.

    Compares pristine and current documents section by section,
    generating only the operations needed to transform pristine into current.

    Args:
        pristine_xml: The original document XML
        current_xml: The modified document XML
        pristine_styles: Optional styles.xml for pristine
        current_styles: Optional styles.xml for current

    Returns:
        List of batchUpdate request dictionaries
    """
    global _sequence_counter
    _sequence_counter = 0

    pristine = desugar_document(pristine_xml, pristine_styles)
    current = desugar_document(current_xml, current_styles)

    # Index sections by (type, id) for quick lookup
    def _key(section: Section) -> tuple[str, str]:
        return (section.section_type, section.section_id or "")

    pristine_map = {_key(s): s for s in pristine.sections}
    current_map = {_key(s): s for s in current.sections}

    operations: list[DiffOperation] = []

    # Process sections that exist in current
    for section in current.sections:
        key = _key(section)
        pristine_section = pristine_map.get(key)
        section_ops = _diff_section(pristine_section, section)
        operations.extend(section_ops)

    # Handle deleted sections (headers/footers that no longer exist)
    for key, pristine_section in pristine_map.items():
        if key not in current_map:
            # Section was deleted
            if pristine_section.section_type == "header":
                operations.append(
                    DiffOperation(
                        op_type="delete_header",
                        index=0,
                        segment_id=pristine_section.section_id,
                        sequence=_next_sequence(),
                    )
                )
            elif pristine_section.section_type == "footer":
                operations.append(
                    DiffOperation(
                        op_type="delete_footer",
                        index=0,
                        segment_id=pristine_section.section_id,
                        sequence=_next_sequence(),
                    )
                )

    # Hybrid sorting for correct operation ordering:
    #
    # 1. Element-level changes use bottom-up processing (handled by generation order)
    # 2. Within each element (change_group), operations must be ordered:
    #    a) Paragraph style updates for EXISTING paragraphs FIRST (use pristine range)
    #    b) Deletes second (descending index for bottom-up within element)
    #    c) Inserts third (ascending index)
    #    d) Post-insert style updates LAST (for newly created content)
    #
    # The is_post_insert flag distinguishes:
    # - Modifications: update_paragraph_style on existing paragraph (run BEFORE delete)
    # - Insertions: update_paragraph_style on new paragraph (run AFTER insert)
    #
    # The change_group field groups operations by their source change block.
    # During bottom-up processing, change_group 1 = bottom of doc (highest index),
    # change_group N = top of doc (lowest index).
    # We want bottom operations (low change_group) applied first.
    #
    # Sort key: (change_group ASC, op_priority, index for ordering, sequence)
    def sort_key(op: DiffOperation) -> tuple[int, int, int, int]:
        # Lower change_group = bottom of document = apply first
        group_key = op.change_group

        if op.op_type == "update_paragraph_style" and not op.is_post_insert:
            # Paragraph style updates for EXISTING paragraphs FIRST
            # They use pristine range which becomes invalid after delete shrinks it
            return (group_key, 0, op.index, op.sequence)
        elif op.op_type == "delete":
            # Deletes second: sort by descending index (higher indexes first)
            return (group_key, 1, -op.index, op.sequence)
        elif op.op_type == "insert":
            # Inserts third (ascending index)
            return (group_key, 2, op.index, op.sequence)
        else:
            # Everything else (text style updates, post-insert paragraph styles) last
            return (group_key, 3, op.index, op.sequence)

    operations.sort(key=sort_key)

    return [_operation_to_request(op) for op in operations if op.op_type]


def _diff_section(pristine: Section | None, current: Section) -> list[DiffOperation]:
    """Diff a single section using bottom-up processing to avoid index drift.

    The key insight: process changes from bottom of document upward. Changes
    at higher indexes don't affect lower indexes. After processing each change,
    we update a working copy of elements to track the evolving document state.
    """
    segment_id = None if current.section_type == "body" else current.section_id
    start_idx = 1 if current.section_type == "body" else 0
    section_type = current.section_type

    # New section: create it and emit all content
    if pristine is None:
        ops: list[DiffOperation] = []
        if current.section_type == "header":
            ops.append(
                DiffOperation(
                    op_type="create_header",
                    index=0,
                    sequence=_next_sequence(),
                )
            )
        elif current.section_type == "footer":
            ops.append(
                DiffOperation(
                    op_type="create_footer",
                    index=0,
                    sequence=_next_sequence(),
                )
            )

        # Emit content for new section
        cursor = start_idx
        for elem in current.content:
            if isinstance(elem, SpecialElement) and elem.element_type == "hr":
                cursor += elem.utf16_length()
                continue
            elem_ops, added = _emit_element(elem, cursor, segment_id)
            ops.extend(elem_ops)
            cursor += added

        return ops

    # Fast path: sections are identical
    if sections_are_identical(pristine.content, current.content):
        return []

    # Flatten both sections to sequences with index ranges
    p_elements = _flatten_elements(pristine.content, section_type)
    c_elements = _flatten_elements(current.content, section_type)

    # Run sequence diff to find adds/deletes/modifications
    diff_result = sequence_diff(p_elements, c_elements)

    # === BOTTOM-UP PROCESSING ===
    # Process change blocks from bottom to top. This ensures that when we
    # generate operations for a change block, all indexes below it are
    # still at their pristine positions.

    operations: list[DiffOperation] = []

    # Working elements: a mutable copy that tracks document state as we process
    # Each entry is [elem, start, end] - using lists for mutability
    working: list[list[Any]] = [[elem, start, end] for elem, start, end in p_elements]

    # Track change group for proper ordering
    # Higher change_group = processed earlier (bottom-up) = should be applied first
    current_change_group = 0

    # Process changes in reverse order (bottom-up by pristine position)
    for change in reversed(diff_result):
        current_change_group += 1

        if change.type == "equal":
            # Check for style-only differences within "equal" blocks
            # Each element with changes gets its own change_group
            for i, p_elem in enumerate(change.pristine_elements):
                if i < len(change.current_elements):
                    c_elem = change.current_elements[i]
                    if not elements_match(p_elem, c_elem):
                        # Find PRISTINE indexes for this element
                        for pe, ps, pe_end in p_elements:
                            if pe is p_elem:
                                elem_ops_start = len(operations)
                                ops = _diff_element(
                                    (p_elem, ps, pe_end),
                                    (c_elem, ps, pe_end),
                                    segment_id,
                                )
                                operations.extend(ops)
                                # Each element gets its own change_group
                                for op in operations[elem_ops_start:]:
                                    op.change_group = current_change_group
                                current_change_group += 1
                                break

        elif change.type == "delete":
            # Delete elements using PRISTINE indexes
            # Bottom-up processing ensures higher-index changes don't affect lower indexes
            # Each delete gets its own change_group for correct ordering
            for p_elem in reversed(change.pristine_elements):
                # Skip HR (read-only)
                if isinstance(p_elem, SpecialElement) and p_elem.element_type == "hr":
                    continue

                # Find PRISTINE index for this element
                for pe, ps, pe_end in p_elements:
                    if pe is p_elem:
                        operations.append(
                            DiffOperation(
                                op_type="delete",
                                index=ps,
                                end_index=pe_end,
                                segment_id=segment_id,
                                sequence=_next_sequence(),
                                change_group=current_change_group,
                            )
                        )
                        current_change_group += 1
                        break

        elif change.type == "insert":
            # Use PRISTINE insert index from the change
            insert_idx = change.pristine_start

            # Detect end-of-segment insertion
            is_end_insert = False
            if working:
                last_elem_end = working[-1][2]
                if insert_idx >= last_elem_end:
                    is_end_insert = True
                    insert_idx = last_elem_end - 1  # Before structural newline

            # Insert elements in REVERSE order at the same position
            # Each insert pushes previous inserts to the right
            # First, calculate the final position for each element's styles
            elem_lengths = []
            for c_elem in change.current_elements:
                if isinstance(c_elem, SpecialElement) and c_elem.element_type == "hr":
                    elem_lengths.append(0)
                else:
                    elem_lengths.append(_element_length(c_elem))

            # Insert in reverse order, but track style positions
            # All elements in this insert block share the SAME change_group
            # so all inserts happen before any styles
            block_ops_start = len(operations)
            for i, c_elem in enumerate(reversed(change.current_elements)):
                if isinstance(c_elem, SpecialElement) and c_elem.element_type == "hr":
                    continue

                # Reverse index
                rev_idx = len(change.current_elements) - 1 - i
                # Calculate where this element's styles should be applied
                # Elements before this one (in forward order) take up space
                style_offset = sum(elem_lengths[:rev_idx])

                elem_ops, added = _emit_element_with_style_offset(
                    c_elem,
                    insert_idx,
                    style_offset,
                    segment_id,
                    prepend_newline=is_end_insert,
                )
                operations.extend(elem_ops)
                # Only first element needs prepend_newline for end-of-segment
                is_end_insert = False

            # All elements in this block share the same change_group
            for op in operations[block_ops_start:]:
                op.change_group = current_change_group
            current_change_group += 1
            # NOTE: Don't update working or recompute - pristine indexes are used

        elif change.type == "replace":
            # Try element-by-element diff if same count and compatible types
            if len(change.pristine_elements) == len(change.current_elements):
                can_diff = all(
                    isinstance(p, type(c))
                    for p, c in zip(
                        change.pristine_elements, change.current_elements, strict=False
                    )
                )
                if can_diff:
                    # Diff each pair using PRISTINE indexes from p_elements
                    # Process in REVERSE order (bottom-up) so higher-indexed elements
                    # get lower change_groups and are processed first.
                    paired = list(
                        zip(
                            change.pristine_elements,
                            change.current_elements,
                            strict=False,
                        )
                    )
                    for p_elem, c_elem in reversed(paired):
                        elem_ops_start = len(operations)
                        # Find pristine index for this element
                        for pe, ps, pe_end in p_elements:
                            if pe is p_elem:
                                ops = _diff_element(
                                    (p_elem, ps, pe_end),
                                    (c_elem, ps, pe_end),
                                    segment_id,
                                )
                                operations.extend(ops)
                                break
                        # Each element gets its own change_group
                        for op in operations[elem_ops_start:]:
                            op.change_group = current_change_group
                        current_change_group += 1
                    continue

            # Fallback: delete old elements, then insert new
            # Use PRISTINE indexes throughout
            # Each element gets its own change_group

            # Delete pristine elements (bottom-up)
            for p_elem in reversed(change.pristine_elements):
                if isinstance(p_elem, SpecialElement) and p_elem.element_type == "hr":
                    continue

                # Find pristine index for this element
                for pe, ps, pe_end in p_elements:
                    if pe is p_elem:
                        operations.append(
                            DiffOperation(
                                op_type="delete",
                                index=ps,
                                end_index=pe_end,
                                segment_id=segment_id,
                                sequence=_next_sequence(),
                                change_group=current_change_group,
                            )
                        )
                        current_change_group += 1
                        break

            # Insert at PRISTINE start index in reverse order with style offset
            insert_idx = change.pristine_start

            # Calculate element lengths for style offset
            elem_lengths = []
            for c_elem in change.current_elements:
                if isinstance(c_elem, SpecialElement) and c_elem.element_type == "hr":
                    elem_lengths.append(0)
                else:
                    elem_lengths.append(_element_length(c_elem))

            # Insert in reverse order with calculated style offsets
            # All elements share the same change_group for inserts
            insert_block_ops_start = len(operations)
            for i, c_elem in enumerate(reversed(change.current_elements)):
                if isinstance(c_elem, SpecialElement) and c_elem.element_type == "hr":
                    continue

                rev_idx = len(change.current_elements) - 1 - i
                style_offset = sum(elem_lengths[:rev_idx])

                elem_ops, added = _emit_element_with_style_offset(
                    c_elem, insert_idx, style_offset, segment_id, prepend_newline=False
                )
                operations.extend(elem_ops)

            # All insert operations share the same change_group
            for op in operations[insert_block_ops_start:]:
                op.change_group = current_change_group
            current_change_group += 1
            # NOTE: Don't update working or recompute - pristine indexes are used

    # Handle last paragraph rule - don't delete the final paragraph
    operations = _enforce_last_paragraph_rule(operations, pristine, current, segment_id)

    return operations


def _enforce_last_paragraph_rule(
    operations: list[DiffOperation],
    pristine: Section,
    current: Section,
    segment_id: str | None,
) -> list[DiffOperation]:
    """Enforce Google Docs rule about structural newlines.

    Google Docs has two related constraints:
    1. Every segment must have at least one paragraph (can't delete all content)
    2. The newline at the very end of a segment is "structural" and cannot be
       deleted by any operation

    This function handles both by:
    - Truncating deletes that would extend to the segment end (preserve structural newline)
    - Skipping deletes of the last element when current has no content (preserve paragraph)
    - Resetting the last paragraph's style to NORMAL_TEXT if it had a different style
      and new content is being inserted (prevents style inheritance)
    """
    if not pristine.content:
        return operations

    # Find the segment end (last element's end index)
    p_flat = _flatten_elements(pristine.content, current.section_type)
    if not p_flat:
        return operations

    last_elem, last_start, segment_end = p_flat[-1]
    # The structural newline is at segment_end - 1
    structural_newline_idx = segment_end - 1

    # Check if the last pristine paragraph has a non-NORMAL_TEXT style
    # If so, and we're inserting content, we need to reset its style first
    # This prevents inserted text from inheriting the old paragraph's style
    last_para_style_reset_needed = False
    if isinstance(last_elem, Paragraph) and last_elem.named_style != "NORMAL_TEXT":
        # Check if there are any insert operations (meaning content is being added)
        has_inserts = any(op.op_type == "insert" for op in operations)
        if has_inserts:
            last_para_style_reset_needed = True

    filtered = []

    # If we need to reset the last paragraph's style, add that operation FIRST
    # (before any deletes or inserts) so it runs in the correct order
    if last_para_style_reset_needed:
        # Reset the trailing paragraph to NORMAL_TEXT
        # This must happen BEFORE inserts so that inserted text doesn't inherit
        # the old heading style
        filtered.append(
            DiffOperation(
                op_type="update_paragraph_style",
                index=last_start,
                end_index=segment_end,
                paragraph_style={"namedStyleType": "NORMAL_TEXT"},
                fields="namedStyleType",
                segment_id=segment_id,
                sequence=_next_sequence(),
                change_group=-1,  # Very low change_group to run first
                is_post_insert=False,  # Run before inserts
            )
        )

    for op in operations:
        if op.op_type == "delete":
            # Rule 1: Never delete the structural newline at segment end
            if op.end_index > structural_newline_idx:
                # Truncate delete to preserve the structural newline
                if op.index >= structural_newline_idx:
                    # This delete is entirely within the structural newline - skip it
                    continue
                op = DiffOperation(
                    op_type=op.op_type,
                    index=op.index,
                    end_index=structural_newline_idx,
                    segment_id=op.segment_id,
                    sequence=op.sequence,
                )

            # Rule 2: If current has no content, don't delete the last paragraph
            if (
                not current.content
                and op.index == last_start
                and op.end_index >= structural_newline_idx
            ):
                continue

        filtered.append(op)

    return filtered


def _diff_element(
    pristine: tuple[Paragraph | Table | SpecialElement, int, int],
    current: tuple[Paragraph | Table | SpecialElement, int, int],
    segment_id: str | None,
) -> list[DiffOperation]:
    """Diff a single element that exists in both versions."""
    p_elem, p_start, p_end = pristine
    c_elem, _c_start, _c_end = current

    if isinstance(p_elem, Paragraph) and isinstance(c_elem, Paragraph):
        return _diff_paragraph(p_elem, c_elem, p_start, p_end, segment_id)

    if isinstance(p_elem, Table) and isinstance(c_elem, Table):
        return _diff_table(p_elem, c_elem, p_start, segment_id)

    # For other types or mismatched types, delete and reinsert
    ops: list[DiffOperation] = []
    ops.append(
        DiffOperation(
            op_type="delete",
            index=p_start,
            end_index=p_end,
            segment_id=segment_id,
            sequence=_next_sequence(),
        )
    )
    elem_ops, _ = _emit_element(c_elem, p_start, segment_id)
    ops.extend(elem_ops)
    return ops


def _diff_paragraph(
    pristine: Paragraph,
    current: Paragraph,
    p_start: int,
    p_end: int,
    segment_id: str | None,
) -> list[DiffOperation]:
    """Diff paragraph content and styles."""
    ops: list[DiffOperation] = []

    # 1. Check named style (heading level)
    if pristine.named_style != current.named_style:
        ops.append(
            DiffOperation(
                op_type="update_paragraph_style",
                index=p_start,
                end_index=p_end,
                paragraph_style={"namedStyleType": current.named_style},
                fields="namedStyleType",
                segment_id=segment_id,
                sequence=_next_sequence(),
            )
        )

    # 2. Check bullet changes
    if pristine.bullet_type != current.bullet_type:
        if current.bullet_type:
            preset = _bullet_type_to_preset(current.bullet_type)
            ops.append(
                DiffOperation(
                    op_type="create_bullets",
                    index=p_start,
                    end_index=p_end,
                    bullet_preset=preset,
                    segment_id=segment_id,
                    sequence=_next_sequence(),
                )
            )
            # Handle nested levels
            if current.bullet_level > 0:
                indent_pt = 36 * current.bullet_level
                ops.append(
                    DiffOperation(
                        op_type="update_paragraph_style",
                        index=p_start,
                        end_index=p_end,
                        paragraph_style={
                            "indentStart": {"magnitude": indent_pt, "unit": "PT"},
                            "indentFirstLine": {"magnitude": 0, "unit": "PT"},
                        },
                        fields="indentStart,indentFirstLine",
                        segment_id=segment_id,
                        sequence=_next_sequence(),
                    )
                )
        else:
            ops.append(
                DiffOperation(
                    op_type="delete_bullets",
                    index=p_start,
                    end_index=p_end,
                    segment_id=segment_id,
                    sequence=_next_sequence(),
                )
            )

    # 3. Diff text content
    p_text = pristine.text_content()
    c_text = current.text_content()

    if p_text != c_text:
        # Simple approach: delete old text, insert new text
        # This avoids index drift issues from fine-grained character-level diffing.
        # The delete removes the text content (not the newline), then insert adds new text.
        p_text_len = utf16_len(p_text)
        if p_text_len > 0:
            ops.append(
                DiffOperation(
                    op_type="delete",
                    index=p_start,
                    end_index=p_start + p_text_len,
                    segment_id=segment_id,
                    sequence=_next_sequence(),
                )
            )

        if c_text:
            ops.append(
                DiffOperation(
                    op_type="insert",
                    index=p_start,
                    content=c_text,
                    segment_id=segment_id,
                    sequence=_next_sequence(),
                )
            )

        # Apply styles for all runs in current paragraph
        cursor = p_start
        for run in current.runs:
            if "_special" in run.styles:
                continue
            if run.text:
                run_len = utf16_len(run.text)
                style_info = _full_run_text_style(run.styles)
                if style_info:
                    text_style, fields = style_info
                    ops.append(
                        DiffOperation(
                            op_type="update_text_style",
                            index=cursor,
                            end_index=cursor + run_len,
                            text_style=text_style,
                            fields=fields,
                            segment_id=segment_id,
                            sequence=_next_sequence(),
                        )
                    )
                cursor += run_len

    elif _runs_have_style_changes(pristine.runs, current.runs):
        # Same text, different styling
        style_ops = _diff_run_styles(pristine, current, p_start, segment_id)
        ops.extend(style_ops)

    return ops


def _apply_styles_to_inserted_text(
    paragraph: Paragraph,
    insert_idx: int,
    text: str,
    segment_id: str | None,
) -> list[DiffOperation]:
    """Apply appropriate styles to inserted text based on context."""
    ops: list[DiffOperation] = []
    text_len = utf16_len(text)

    # For now, apply styles from the first non-special run
    for run in paragraph.runs:
        if "_special" not in run.styles:
            style_info = _full_run_text_style(run.styles)
            if style_info:
                text_style, fields = style_info
                ops.append(
                    DiffOperation(
                        op_type="update_text_style",
                        index=insert_idx,
                        end_index=insert_idx + text_len,
                        text_style=text_style,
                        fields=fields,
                        segment_id=segment_id,
                        sequence=_next_sequence(),
                    )
                )
            break

    return ops


def _runs_have_style_changes(pristine_runs: list[Any], current_runs: list[Any]) -> bool:
    """Check if runs have style differences with same text."""
    if len(pristine_runs) != len(current_runs):
        return True

    for p_run, c_run in zip(pristine_runs, current_runs, strict=False):
        if p_run.text != c_run.text:
            return True
        # Compare styles excluding transient keys
        p_styles = {k: v for k, v in p_run.styles.items() if not k.startswith("_")}
        c_styles = {k: v for k, v in c_run.styles.items() if not k.startswith("_")}
        if p_styles != c_styles:
            return True

    return False


def _diff_run_styles(
    pristine: Paragraph,
    current: Paragraph,
    p_start: int,
    segment_id: str | None,
) -> list[DiffOperation]:
    """Generate style update operations for run-level changes.

    This function handles the case where the text content is the same but the
    run structure may differ (e.g., "Hello World" vs "Hello " + "World" with bold).
    It flattens both paragraphs to character-level styles and compares them.
    """
    ops: list[DiffOperation] = []

    # Flatten both paragraphs to character-level styles
    p_chars = _flatten_to_char_styles(pristine)
    c_chars = _flatten_to_char_styles(current)

    # If different lengths, something is wrong (text should be same)
    if len(p_chars) != len(c_chars):
        return ops

    # Find ranges where styles differ
    i = 0
    while i < len(p_chars):
        p_style, _ = p_chars[i]
        c_style, _ = c_chars[i]

        if p_style != c_style:
            # Find the end of this style difference range
            start_i = i
            while i < len(c_chars):
                ps, _ = p_chars[i]
                cs, _ = c_chars[i]
                # Continue while styles differ AND current style is consistent
                if ps != cs and cs == c_style:
                    i += 1
                else:
                    break

            # Calculate UTF-16 indexes
            start_offset = sum(utf16_len(c) for _, c in p_chars[:start_i])
            end_offset = sum(utf16_len(c) for _, c in p_chars[:i])

            style_diff = _compute_style_diff(p_style, c_style)
            if style_diff:
                text_style, fields = style_diff
                ops.append(
                    DiffOperation(
                        op_type="update_text_style",
                        index=p_start + start_offset,
                        end_index=p_start + end_offset,
                        text_style=text_style,
                        fields=fields,
                        segment_id=segment_id,
                        sequence=_next_sequence(),
                    )
                )
        else:
            i += 1

    return ops


def _flatten_to_char_styles(para: Paragraph) -> list[tuple[dict[str, str], str]]:
    """Flatten a paragraph to a list of (style_dict, character) tuples.

    Special elements are skipped (they don't have character-level styles).
    """
    result: list[tuple[dict[str, str], str]] = []

    for run in para.runs:
        # Skip special elements
        if "_special" in run.styles:
            continue

        # Get clean styles (without _ prefixed keys)
        styles = {k: v for k, v in run.styles.items() if not k.startswith("_")}

        # Add each character with its style
        for char in run.text:
            result.append((styles, char))

    return result


def _compute_style_diff(
    pristine: dict[str, str], current: dict[str, str]
) -> tuple[dict[str, Any], str] | None:
    """Compute the style difference between two run styles."""
    changes: dict[str, Any] = {}
    fields: list[str] = []

    # Check each style key
    for key in ("bold", "italic", "underline", "strikethrough"):
        p_val = pristine.get(key, "")
        c_val = current.get(key, "")
        if p_val != c_val:
            changes[key] = c_val == "1"
            fields.append(key)

    # Handle link separately
    p_link = pristine.get("link", "")
    c_link = current.get("link", "")
    if p_link != c_link:
        changes["link"] = {"url": c_link} if c_link else None
        fields.append("link")

    # Handle superscript/subscript
    p_super = pristine.get("superscript") == "1"
    p_sub = pristine.get("subscript") == "1"
    c_super = current.get("superscript") == "1"
    c_sub = current.get("subscript") == "1"

    if p_super != c_super or p_sub != c_sub:
        if c_super:
            changes["baselineOffset"] = "SUPERSCRIPT"
        elif c_sub:
            changes["baselineOffset"] = "SUBSCRIPT"
        else:
            changes["baselineOffset"] = "NONE"
        fields.append("baselineOffset")

    if changes:
        return changes, ",".join(fields)
    return None


def _diff_table(
    pristine: Table,
    current: Table,
    p_start: int,
    segment_id: str | None,
) -> list[DiffOperation]:
    """Diff table structure and cell content."""
    ops: list[DiffOperation] = []

    # If structure changed, delete and reinsert the whole table
    if pristine.rows != current.rows or pristine.cols != current.cols:
        p_end = p_start + _table_length(pristine)
        ops.append(
            DiffOperation(
                op_type="delete",
                index=p_start,
                end_index=p_end,
                segment_id=segment_id,
                sequence=_next_sequence(),
            )
        )
        table_ops, _ = _emit_table(current, p_start, segment_id)
        ops.extend(table_ops)
        return ops

    # Same structure: diff cell by cell
    p_cells = {(c.row, c.col): c for c in pristine.cells}
    c_cells = {(c.row, c.col): c for c in current.cells}

    # Calculate cell start indexes
    cell_starts = _calculate_table_cell_indexes(pristine, p_start)

    for pos, c_cell in c_cells.items():
        p_cell = p_cells.get(pos)
        if p_cell and pos in cell_starts:
            cell_ops = _diff_cell_content(p_cell, c_cell, cell_starts[pos], segment_id)
            ops.extend(cell_ops)

    return ops


def _diff_cell_content(
    pristine: TableCell,
    current: TableCell,
    cell_start: int,
    segment_id: str | None,
) -> list[DiffOperation]:
    """Diff the content of a single table cell."""
    ops: list[DiffOperation] = []

    # Check colspan/rowspan changes (would need merge/unmerge operations)
    # For now, skip if merge attributes differ

    # Diff cell content element by element
    if len(pristine.content) == len(current.content):
        cursor = cell_start
        for p_elem, c_elem in zip(pristine.content, current.content, strict=False):
            if isinstance(p_elem, Paragraph) and isinstance(c_elem, Paragraph):
                p_len = p_elem.utf16_length()
                if not elements_match(p_elem, c_elem):
                    para_ops = _diff_paragraph(
                        p_elem, c_elem, cursor, cursor + p_len, segment_id
                    )
                    ops.extend(para_ops)
                cursor += p_len

    return ops


# --- Element flattening ---


def _flatten_elements(
    content: list[Paragraph | Table | SpecialElement],
    section_type: str,
) -> list[tuple[Paragraph | Table | SpecialElement, int, int]]:
    """Flatten elements with their index ranges."""
    result: list[tuple[Paragraph | Table | SpecialElement, int, int]] = []

    # Body starts at index 1, others at 0
    current_idx = 1 if section_type == "body" else 0

    for elem in content:
        start_idx = current_idx

        if isinstance(elem, Paragraph):
            end_idx = start_idx + elem.utf16_length()
            result.append((elem, start_idx, end_idx))
            current_idx = end_idx

        elif isinstance(elem, Table):
            end_idx = start_idx + _table_length(elem)
            result.append((elem, start_idx, end_idx))
            current_idx = end_idx

        elif isinstance(elem, SpecialElement):
            end_idx = start_idx + elem.utf16_length()
            result.append((elem, start_idx, end_idx))
            current_idx = end_idx

    return result


# --- Length calculations ---


def _element_length(elem: Paragraph | Table | SpecialElement) -> int:
    """Compute utf16 length of an element including structural markers."""
    if isinstance(elem, Paragraph):
        return elem.utf16_length()
    if isinstance(elem, SpecialElement):
        return elem.utf16_length()
    if isinstance(elem, Table):
        return _table_length(elem)
    return 0


def _table_length(table: Table) -> int:
    """Compute the utf16 length of a table including its contents."""
    length = 1  # table start marker
    # Build a lookup for cells
    cell_map = {(cell.row, cell.col): cell for cell in table.cells}
    for row in range(table.rows):
        length += 1  # row marker
        for col in range(table.cols):
            length += 1  # cell marker
            cell = cell_map.get((row, col))
            if cell and cell.content:
                for item in cell.content:
                    length += _element_length(item)
            else:
                # Default empty paragraph
                length += 1
    length += 1  # table end marker
    return length


def _calculate_table_cell_indexes(
    table: Table, table_start: int
) -> dict[tuple[int, int], int]:
    """Calculate the start index of text content in each table cell."""
    cell_indexes: dict[tuple[int, int], int] = {}
    cell_map = {(cell.row, cell.col): cell for cell in table.cells}

    current_idx = table_start + 1  # Skip table start marker

    for row in range(table.rows):
        current_idx += 1  # Row marker
        for col in range(table.cols):
            current_idx += 1  # Cell marker
            cell_indexes[(row, col)] = current_idx

            cell = cell_map.get((row, col))
            if cell and cell.content:
                for elem in cell.content:
                    current_idx += _element_length(elem)
            else:
                current_idx += 1  # Default empty paragraph

    return cell_indexes


def _table_cell_starts(
    table: Table, base_index: int, default_cell_len: int = 1
) -> tuple[dict[tuple[int, int], int], int]:
    """Return cell start indexes (first content char) and base length."""
    starts: dict[tuple[int, int], int] = {}
    idx = base_index
    idx += 1  # table start
    for row in range(table.rows):
        idx += 1  # row marker
        for col in range(table.cols):
            idx += 1  # cell marker
            starts[(row, col)] = idx
            idx += default_cell_len
    idx += 1  # table end
    return starts, idx - base_index


# --- Element emission ---


def _emit_element(
    elem: Paragraph | Table | SpecialElement,
    insert_idx: int,
    segment_id: str | None,
    prepend_newline: bool = False,
) -> tuple[list[DiffOperation], int]:
    """Emit operations for an element at a given index and return (ops, length).

    Args:
        elem: The element to emit
        insert_idx: The index at which to insert
        segment_id: Optional segment ID for headers/footers
        prepend_newline: If True, emit "\\n{content}" instead of "{content}\\n".
                        Used when appending at end of segment.
    """
    if isinstance(elem, Paragraph):
        return _emit_paragraph(elem, insert_idx, segment_id, prepend_newline)
    elif isinstance(elem, SpecialElement):
        return _emit_special(elem, insert_idx, segment_id)
    elif isinstance(elem, Table):
        return _emit_table(elem, insert_idx, segment_id)
    return [], 0


def _emit_element_with_style_offset(
    elem: Paragraph | Table | SpecialElement,
    insert_idx: int,
    style_offset: int,
    segment_id: str | None,
    prepend_newline: bool = False,
) -> tuple[list[DiffOperation], int]:
    """Emit element with style operations offset from insert position.

    When inserting multiple elements in reverse order at the same position,
    each element's style operations need to be at a different offset because
    the final positions differ from the insert position.

    Args:
        elem: The element to emit
        insert_idx: The index at which to insert (always the same for reverse inserts)
        style_offset: Offset to add to style operation indexes
        segment_id: Optional segment ID for headers/footers
        prepend_newline: If True, emit "\\n{content}" instead of "{content}\\n"
    """
    if isinstance(elem, Paragraph):
        return _emit_paragraph_with_style_offset(
            elem, insert_idx, style_offset, segment_id, prepend_newline
        )
    elif isinstance(elem, SpecialElement):
        # Special elements don't have styles
        return _emit_special(elem, insert_idx, segment_id)
    elif isinstance(elem, Table):
        # Tables are complex - for now, don't offset (may need fixing later)
        return _emit_table(elem, insert_idx, segment_id)
    return [], 0


def _emit_paragraph_with_style_offset(
    para: Paragraph,
    insert_idx: int,
    style_offset: int,
    segment_id: str | None,
    prepend_newline: bool = False,
) -> tuple[list[DiffOperation], int]:
    """Insert paragraph with style operations at offset position."""
    ops: list[DiffOperation] = []
    cursor = insert_idx
    style_cursor = insert_idx + style_offset  # Where styles actually apply
    add_trailing_newline = not prepend_newline

    has_specials = any("_special" in run.styles for run in para.runs)

    if not has_specials and para.runs:
        all_text = "".join(run.text for run in para.runs)
        if prepend_newline:
            all_text = "\n" + all_text
        elif add_trailing_newline:
            all_text += "\n"

        ops.append(
            DiffOperation(
                op_type="insert",
                index=cursor,  # Insert at original position
                content=all_text,
                segment_id=segment_id,
                sequence=_next_sequence(),
            )
        )

        # Apply styles at OFFSET position
        run_style_cursor = style_cursor + (1 if prepend_newline else 0)
        for run in para.runs:
            if run.text:
                run_len = utf16_len(run.text)
                style_info = _full_run_text_style(run.styles)
                if style_info:
                    text_style, fields = style_info
                    ops.append(
                        DiffOperation(
                            op_type="update_text_style",
                            index=run_style_cursor,
                            end_index=run_style_cursor + run_len,
                            text_style=text_style,
                            fields=fields,
                            segment_id=segment_id,
                            sequence=_next_sequence(),
                        )
                    )
                run_style_cursor += run_len

        cursor = (
            style_cursor
            + utf16_len(all_text.rstrip("\n"))
            + (1 if add_trailing_newline else 0)
        )
        if prepend_newline:
            cursor = run_style_cursor

    # Paragraph style at OFFSET position - ALWAYS emit to prevent style inheritance
    # When inserting paragraphs near headings, text can inherit the heading style
    # unless we explicitly set the paragraph style (even for NORMAL_TEXT)
    para_end = style_cursor + para.utf16_length()
    ops.append(
        DiffOperation(
            op_type="update_paragraph_style",
            index=style_cursor,
            end_index=para_end,
            paragraph_style={"namedStyleType": para.named_style},
            fields="namedStyleType",
            segment_id=segment_id,
            sequence=_next_sequence(),
            is_post_insert=True,
        )
    )

    # Bullets at OFFSET position
    if para.bullet_type:
        preset = _bullet_type_to_preset(para.bullet_type)
        ops.append(
            DiffOperation(
                op_type="create_bullets",
                index=style_cursor,
                end_index=para_end,
                bullet_preset=preset,
                segment_id=segment_id,
                sequence=_next_sequence(),
            )
        )
        if para.bullet_level > 0:
            indent_pt = 36 * para.bullet_level
            ops.append(
                DiffOperation(
                    op_type="update_paragraph_style",
                    index=style_cursor,
                    end_index=para_end,
                    paragraph_style={
                        "indentStart": {"magnitude": indent_pt, "unit": "PT"},
                        "indentFirstLine": {"magnitude": 0, "unit": "PT"},
                    },
                    fields="indentStart,indentFirstLine",
                    segment_id=segment_id,
                    sequence=_next_sequence(),
                    is_post_insert=True,
                )
            )

    return ops, para.utf16_length()


def _emit_paragraph(
    para: Paragraph,
    insert_idx: int,
    segment_id: str | None,
    prepend_newline: bool = False,
) -> tuple[list[DiffOperation], int]:
    """Insert a paragraph with styles and bullets. Returns (ops, length).

    Args:
        para: The paragraph to emit
        insert_idx: The index at which to insert
        segment_id: Optional segment ID for headers/footers
        prepend_newline: If True, emit "\\n{content}" instead of "{content}\\n".
                        Used when appending at end of segment.
    """
    ops: list[DiffOperation] = []
    cursor = insert_idx
    add_trailing_newline = not prepend_newline  # Don't add trailing if prepending

    # Check if we can do a simple single-insert (no special elements, uniform style)
    has_specials = any("_special" in run.styles for run in para.runs)

    if not has_specials and para.runs:
        # Collect all text and insert at once (including newline)
        all_text = "".join(run.text for run in para.runs)
        if prepend_newline:
            all_text = "\n" + all_text
        elif add_trailing_newline:
            all_text += "\n"

        ops.append(
            DiffOperation(
                op_type="insert",
                index=cursor,
                content=all_text,
                segment_id=segment_id,
                sequence=_next_sequence(),
            )
        )

        # Apply styles to each run's range
        # If prepending newline, text starts after the newline
        run_cursor = cursor + (1 if prepend_newline else 0)
        for run in para.runs:
            if run.text:
                run_len = utf16_len(run.text)
                style_info = _full_run_text_style(run.styles)
                if style_info:
                    text_style, fields = style_info
                    ops.append(
                        DiffOperation(
                            op_type="update_text_style",
                            index=run_cursor,
                            end_index=run_cursor + run_len,
                            text_style=text_style,
                            fields=fields,
                            segment_id=segment_id,
                            sequence=_next_sequence(),
                        )
                    )
                run_cursor += run_len

        # Calculate final cursor position
        cursor = run_cursor + (1 if add_trailing_newline else 0)
        if prepend_newline:
            cursor = run_cursor  # Already accounted for newline at start
    else:
        # Complex case: handle special elements individually
        # If prepending newline, insert it first
        if prepend_newline:
            ops.append(
                DiffOperation(
                    op_type="insert",
                    index=cursor,
                    content="\n",
                    segment_id=segment_id,
                    sequence=_next_sequence(),
                )
            )
            cursor += 1

        for idx, run in enumerate(para.runs):
            if "_special" in run.styles:
                special_ops, special_len = _emit_special(
                    SpecialElement(run.styles["_special"], dict(run.styles)),
                    cursor,
                    segment_id,
                )
                ops.extend(special_ops)
                cursor += special_len
                # If a column break is the last thing, skip trailing newline
                if (
                    run.styles.get("_special") == "columnbreak"
                    and idx == len(para.runs) - 1
                ):
                    add_trailing_newline = False
                continue

            if run.text:
                ops.append(
                    DiffOperation(
                        op_type="insert",
                        index=cursor,
                        content=run.text,
                        segment_id=segment_id,
                        sequence=_next_sequence(),
                    )
                )
                run_len = utf16_len(run.text)

                style_info = _full_run_text_style(run.styles)
                if style_info:
                    text_style, fields = style_info
                    ops.append(
                        DiffOperation(
                            op_type="update_text_style",
                            index=cursor,
                            end_index=cursor + run_len,
                            text_style=text_style,
                            fields=fields,
                            segment_id=segment_id,
                            sequence=_next_sequence(),
                        )
                    )

                cursor += run_len

        # Append newline to terminate paragraph
        if add_trailing_newline:
            ops.append(
                DiffOperation(
                    op_type="insert",
                    index=cursor,
                    content="\n",
                    segment_id=segment_id,
                    sequence=_next_sequence(),
                )
            )
            cursor += 1

    # Paragraph style - must run AFTER insert creates the paragraph
    # ALWAYS emit to prevent style inheritance from surrounding headings
    ops.append(
        DiffOperation(
            op_type="update_paragraph_style",
            index=insert_idx,
            end_index=cursor,
            paragraph_style={"namedStyleType": para.named_style},
            fields="namedStyleType",
            segment_id=segment_id,
            sequence=_next_sequence(),
            is_post_insert=True,  # Must run after insert
        )
    )

    # Bullets
    if para.bullet_type:
        preset = _bullet_type_to_preset(para.bullet_type)
        ops.append(
            DiffOperation(
                op_type="create_bullets",
                index=insert_idx,
                end_index=cursor,
                bullet_preset=preset,
                segment_id=segment_id,
                sequence=_next_sequence(),
            )
        )
        # Indent nested levels - must run AFTER insert creates the paragraph
        if para.bullet_level > 0:
            indent_pt = 36 * para.bullet_level
            ops.append(
                DiffOperation(
                    op_type="update_paragraph_style",
                    index=insert_idx,
                    end_index=cursor,
                    paragraph_style={
                        "indentStart": {"magnitude": indent_pt, "unit": "PT"},
                        "indentFirstLine": {"magnitude": 0, "unit": "PT"},
                    },
                    fields="indentStart,indentFirstLine",
                    segment_id=segment_id,
                    is_post_insert=True,  # Must run after insert
                    sequence=_next_sequence(),
                )
            )

    return ops, cursor - insert_idx


def _emit_special(
    elem: SpecialElement,
    insert_idx: int,
    segment_id: str | None,
) -> tuple[list[DiffOperation], int]:
    """Insert special elements (pagebreak, columnbreak, hr placeholder, person)."""
    etype = elem.element_type
    ops: list[DiffOperation] = []
    added = 1

    if etype == "pagebreak":
        ops.append(
            DiffOperation(
                op_type="insert_page_break",
                index=insert_idx,
                segment_id=segment_id,
                sequence=_next_sequence(),
            )
        )
        added = 1
    elif etype == "columnbreak":
        ops.append(
            DiffOperation(
                op_type="insert_section_break",
                index=insert_idx,
                segment_id=segment_id,
                fields="CONTINUOUS",
                sequence=_next_sequence(),
            )
        )
        added = 2
    elif etype == "hr":
        ops.append(
            DiffOperation(
                op_type="insert",
                index=insert_idx,
                content="\n",
                segment_id=segment_id,
                sequence=_next_sequence(),
            )
        )
        ops.append(
            DiffOperation(
                op_type="update_paragraph_style",
                index=insert_idx,
                end_index=insert_idx + 1,
                paragraph_style={
                    "borderBottom": {
                        "width": {"magnitude": 1, "unit": "PT"},
                        "dashStyle": "SOLID",
                        "color": {
                            "color": {"rgbColor": {"red": 0, "green": 0, "blue": 0}}
                        },
                    }
                },
                fields="borderBottom",
                segment_id=segment_id,
                sequence=_next_sequence(),
            )
        )
        added = 1
    elif etype == "footnoteref":
        placeholder = elem.attributes.get("id", "")
        ops.append(
            DiffOperation(
                op_type="create_footnote",
                index=insert_idx,
                content=placeholder,
                sequence=_next_sequence(),
            )
        )
        added = 1
    elif etype == "person":
        email = elem.attributes.get("email", "")
        name = elem.attributes.get("name", email)
        content = name or email
        ops.append(
            DiffOperation(
                op_type="insert",
                index=insert_idx,
                content=content,
                segment_id=segment_id,
                sequence=_next_sequence(),
            )
        )
        added = utf16_len(content)
    else:
        added = 0

    return ops, added


def _emit_table(
    table: Table, insert_idx: int, segment_id: str | None
) -> tuple[list[DiffOperation], int]:
    """Insert a table and populate cell content. Returns (ops, length)."""
    ops: list[DiffOperation] = []
    ops.append(
        DiffOperation(
            op_type="insert_table",
            index=insert_idx,
            content=json.dumps({"rows": table.rows, "cols": table.cols}),
            segment_id=segment_id,
            sequence=_next_sequence(),
        )
    )

    # Compute base cell starts for the freshly inserted empty table
    cell_starts, _ = _table_cell_starts(table, insert_idx, default_cell_len=1)
    cell_map = {(cell.row, cell.col): cell for cell in table.cells}

    # Populate cells that have content, processing from later indexes first
    for (row, col), start in sorted(
        cell_starts.items(), key=lambda item: item[1], reverse=True
    ):
        cell = cell_map.get((row, col))
        if not cell or not cell.content:
            continue

        # Offset by 1 to land inside the default empty paragraph for the cell
        cell_ops = _emit_cell_content(cell, start + 1, segment_id)
        ops.extend(cell_ops)

    # Final length accounts for actual cell content
    length = _table_length(table)
    return ops, length


def _emit_cell_content(
    cell: TableCell, insert_idx: int, segment_id: str | None
) -> list[DiffOperation]:
    """Emit operations for the content of a single table cell."""
    ops: list[DiffOperation] = []
    cursor = insert_idx

    for elem in cell.content:
        if isinstance(elem, Paragraph):
            para_ops, para_len = _emit_paragraph(elem, cursor, segment_id)
            ops.extend(para_ops)
            cursor += para_len
        elif isinstance(elem, SpecialElement):
            spec_ops, spec_len = _emit_special(elem, cursor, segment_id)
            ops.extend(spec_ops)
            cursor += spec_len
        elif isinstance(elem, Table):
            table_ops, table_len = _emit_table(elem, cursor, segment_id)
            ops.extend(table_ops)
            cursor += table_len

    return ops


# --- Bullet preset mapping ---


def _bullet_type_to_preset(bullet_type: str) -> str:
    """Convert bullet type to Google Docs preset name."""
    presets = {
        "bullet": "BULLET_DISC_CIRCLE_SQUARE",
        "decimal": "NUMBERED_DECIMAL_NESTED",
        "alpha": "NUMBERED_DECIMAL_ALPHA_ROMAN",
        "roman": "NUMBERED_DECIMAL_ALPHA_ROMAN",
        "checkbox": "BULLET_CHECKBOX",
    }
    return presets.get(bullet_type, "BULLET_DISC_CIRCLE_SQUARE")


# --- Operation to request conversion ---


def _operation_to_request(op: DiffOperation) -> dict[str, Any]:
    """Convert a DiffOperation to a batchUpdate request."""
    if op.op_type == "delete":
        range_obj: dict[str, Any] = {
            "startIndex": op.index,
            "endIndex": op.end_index,
        }
        if op.segment_id:
            range_obj["segmentId"] = op.segment_id
        if op.tab_id:
            range_obj["tabId"] = op.tab_id

        return {"deleteContentRange": {"range": range_obj}}

    elif op.op_type == "insert":
        insert_location: dict[str, Any] = {"index": op.index}
        if op.segment_id:
            insert_location["segmentId"] = op.segment_id
        if op.tab_id:
            insert_location["tabId"] = op.tab_id

        return {"insertText": {"location": insert_location, "text": op.content}}

    elif op.op_type == "insert_table":
        data = json.loads(op.content) if op.content else {}
        table_location: dict[str, Any] = {"index": op.index}
        if op.segment_id:
            table_location["segmentId"] = op.segment_id
        return {
            "insertTable": {
                "rows": data.get("rows", 0),
                "columns": data.get("cols", 0),
                "location": table_location,
            }
        }

    elif op.op_type == "insert_page_break":
        page_location: dict[str, Any] = {"index": op.index}
        if op.segment_id:
            page_location["segmentId"] = op.segment_id
        return {"insertPageBreak": {"location": page_location}}

    elif op.op_type == "insert_section_break":
        section_location: dict[str, Any] = {"index": op.index}
        if op.segment_id:
            section_location["segmentId"] = op.segment_id
        return {
            "insertSectionBreak": {
                "sectionType": op.fields or "CONTINUOUS",
                "location": section_location,
            }
        }

    elif op.op_type == "update_text_style":
        range_obj = {
            "startIndex": op.index,
            "endIndex": op.end_index,
        }
        if op.segment_id:
            range_obj["segmentId"] = op.segment_id
        if op.tab_id:
            range_obj["tabId"] = op.tab_id

        return {
            "updateTextStyle": {
                "range": range_obj,
                "textStyle": op.text_style,
                "fields": op.fields,
            }
        }

    elif op.op_type == "update_paragraph_style":
        range_obj = {
            "startIndex": op.index,
            "endIndex": op.end_index,
        }
        if op.segment_id:
            range_obj["segmentId"] = op.segment_id
        if op.tab_id:
            range_obj["tabId"] = op.tab_id

        return {
            "updateParagraphStyle": {
                "range": range_obj,
                "paragraphStyle": op.paragraph_style,
                "fields": op.fields,
            }
        }

    elif op.op_type == "create_bullets":
        range_obj = {
            "startIndex": op.index,
            "endIndex": op.end_index,
        }
        if op.segment_id:
            range_obj["segmentId"] = op.segment_id
        if op.tab_id:
            range_obj["tabId"] = op.tab_id

        return {
            "createParagraphBullets": {
                "range": range_obj,
                "bulletPreset": op.bullet_preset,
            }
        }

    elif op.op_type == "delete_bullets":
        range_obj = {
            "startIndex": op.index,
            "endIndex": op.end_index,
        }
        if op.segment_id:
            range_obj["segmentId"] = op.segment_id
        if op.tab_id:
            range_obj["tabId"] = op.tab_id

        return {"deleteParagraphBullets": {"range": range_obj}}

    elif op.op_type == "create_footnote":
        req: dict[str, Any] = {
            "createFootnote": {
                "location": {
                    "index": op.index,
                }
            }
        }
        if op.content:
            req["_placeholderFootnoteId"] = op.content
        return req

    elif op.op_type == "create_header":
        return {"createHeader": {"type": "DEFAULT"}}

    elif op.op_type == "create_footer":
        return {"createFooter": {"type": "DEFAULT"}}

    elif op.op_type == "delete_header":
        return {"deleteHeader": {"headerId": op.segment_id}}

    elif op.op_type == "delete_footer":
        return {"deleteFooter": {"footerId": op.segment_id}}

    # Fallback - should not happen
    return {}
