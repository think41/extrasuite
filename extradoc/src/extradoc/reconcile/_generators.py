"""Generate batchUpdate request dicts from aligned StructuralElements.

Uses a gap-based approach:
1. Identify MATCHED elements as anchors
2. Group consecutive non-MATCHED elements into "gaps"
3. Process each gap: delete old content, insert new content
4. Process gaps right-to-left so indices remain valid
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from extradoc.reconcile._alignment import AlignedElement, AlignmentOp
from extradoc.reconcile._extractors import extract_plain_text_from_paragraph

if TYPE_CHECKING:
    from extradoc.api_types._generated import (
        Paragraph,
        StructuralElement,
    )


@dataclass
class _Gap:
    """A gap between MATCHED elements containing DELETEs and ADDs."""

    deletes: list[AlignedElement] = field(default_factory=list)
    adds: list[AlignedElement] = field(default_factory=list)
    left_anchor: StructuralElement | None = None  # MATCHED element to the left
    right_anchor: StructuralElement | None = None  # MATCHED element to the right
    is_trailing: bool = False  # True if this is the last gap (no right anchor)


def _paragraph_text(para: Paragraph) -> str:
    return extract_plain_text_from_paragraph(para)


def _make_delete_range(
    start: int, end: int, segment_id: str | None, tab_id: str | None
) -> dict[str, Any]:
    r: dict[str, Any] = {"startIndex": start, "endIndex": end}
    if segment_id:
        r["segmentId"] = segment_id
    if tab_id:
        r["tabId"] = tab_id
    return {"deleteContentRange": {"range": r}}


def _make_insert_text(
    text: str, index: int, segment_id: str | None, tab_id: str | None
) -> dict[str, Any]:
    loc: dict[str, Any] = {"index": index}
    if segment_id:
        loc["segmentId"] = segment_id
    if tab_id:
        loc["tabId"] = tab_id
    return {"insertText": {"text": text, "location": loc}}


def _make_insert_table(
    rows: int,
    columns: int,
    index: int,
    segment_id: str | None,
    tab_id: str | None,
) -> dict[str, Any]:
    loc: dict[str, Any] = {"index": index}
    if segment_id:
        loc["segmentId"] = segment_id
    if tab_id:
        loc["tabId"] = tab_id
    return {"insertTable": {"rows": rows, "columns": columns, "location": loc}}


def _is_section_break(se: StructuralElement) -> bool:
    return se.section_break is not None


def _el_start(se: StructuralElement) -> int:
    return se.start_index if se.start_index is not None else 0


def _el_end(se: StructuralElement) -> int:
    return se.end_index if se.end_index is not None else 0


def _desired_text(aligned: AlignedElement) -> str:
    """Get the text to insert for an ADDED element."""
    el = aligned.desired_element
    assert el is not None
    if el.paragraph:
        return _paragraph_text(el.paragraph)
    return ""


def generate_requests(
    alignment: list[AlignedElement],
    segment_id: str | None,
    tab_id: str | None,
) -> list[dict[str, Any]]:
    """Generate batchUpdate requests from an alignment.

    Groups operations into gaps between MATCHED elements, then processes
    each gap right-to-left. Within each gap:
    1. Delete the contiguous base range of DELETED elements
    2. Insert text for ADDED elements at the gap position
    """
    gaps = _identify_gaps(alignment)
    requests: list[dict[str, Any]] = []

    # Process gaps right to left
    for gap in reversed(gaps):
        reqs = _process_gap(gap, segment_id, tab_id)
        requests.extend(reqs)

    return requests


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


def _process_gap(
    gap: _Gap, segment_id: str | None, tab_id: str | None
) -> list[dict[str, Any]]:
    """Process a single gap: generate delete + insert requests."""
    requests: list[dict[str, Any]] = []

    # Filter out section breaks from deletes and adds
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

    if not real_deletes and not real_adds:
        return []

    # Pre-compute delete element references (guaranteed non-None by filter above)
    first_del_el = real_deletes[0].base_element if real_deletes else None
    last_del_el = real_deletes[-1].base_element if real_deletes else None

    # --- DELETE phase ---
    if real_deletes:
        assert first_del_el is not None
        assert last_del_el is not None
        delete_start = _el_start(first_del_el)
        delete_end = _el_end(last_del_el)

        if gap.is_trailing:
            # Trailing gap: protect segment-final \n
            if gap.left_anchor and not _is_section_break(gap.left_anchor):
                # Include the \n of the preceding matched paragraph
                # to merge the deletion cleanly
                left_end = _el_end(gap.left_anchor)
                del_start = left_end - 1  # eat into preceding \n
                del_end = delete_end - 1  # protect segment-final \n
                if del_start < del_end:
                    requests.append(
                        _make_delete_range(del_start, del_end, segment_id, tab_id)
                    )
            else:
                # No preceding paragraph (only SB before)
                # Just clear content, keep final \n
                del_end = delete_end - 1
                if delete_start < del_end:
                    requests.append(
                        _make_delete_range(delete_start, del_end, segment_id, tab_id)
                    )
        else:
            # Non-trailing gap: delete full range
            if delete_start < delete_end:
                requests.append(
                    _make_delete_range(delete_start, delete_end, segment_id, tab_id)
                )

    # --- INSERT phase ---
    if real_adds:
        # Concatenate all add texts
        add_texts: list[str] = []
        for a in real_adds:
            text = _desired_text(a)
            if text:
                add_texts.append(text)

        if not add_texts:
            return requests

        combined_text = "".join(add_texts)

        if gap.is_trailing:
            # Inserting at the end of the segment
            if real_deletes:
                # After the delete, figure out insert position
                if gap.left_anchor and not _is_section_break(gap.left_anchor):
                    # We deleted [left_end-1, delete_end-1), so position
                    # left_end-1 now has the segment-final \n
                    insert_idx = _el_end(gap.left_anchor) - 1
                else:
                    # We deleted [delete_start, delete_end-1)
                    # Position delete_start now has segment-final \n
                    assert first_del_el is not None
                    insert_idx = _el_start(first_del_el)
            else:
                # Pure add at end (no deletes)
                if gap.left_anchor and not _is_section_break(gap.left_anchor):
                    insert_idx = _el_end(gap.left_anchor) - 1
                else:
                    # After SB only
                    insert_idx = _el_end(gap.left_anchor) if gap.left_anchor else 1

            # Strip trailing \n from combined text and prepend \n
            # to create paragraph break (unless inserting right after SB)
            if gap.left_anchor and not _is_section_break(gap.left_anchor):
                text_stripped = combined_text.rstrip("\n")
                insert_text = "\n" + text_stripped
            else:
                # After SB: insert without trailing \n (segment already has one)
                insert_text = combined_text.rstrip("\n")

            if insert_text:
                requests.append(
                    _make_insert_text(insert_text, insert_idx, segment_id, tab_id)
                )
        else:
            # Non-trailing gap: insert at the gap start position
            if real_deletes:
                # After delete, position delete_start is where right_anchor starts
                assert first_del_el is not None
                insert_idx = _el_start(first_del_el)
            elif gap.right_anchor:
                # Pure add: right_anchor.start is the insert point
                insert_idx = _el_start(gap.right_anchor)
            else:
                insert_idx = 1

            requests.append(
                _make_insert_text(combined_text, insert_idx, segment_id, tab_id)
            )

    return requests
