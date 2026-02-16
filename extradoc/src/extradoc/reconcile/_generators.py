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
        return extract_plain_text_from_paragraph(el.paragraph)
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
        if gap.is_trailing:
            reqs = _process_trailing_gap(gap, segment_id, tab_id)
        else:
            reqs = _process_inner_gap(gap, segment_id, tab_id)
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


def _collect_add_text(real_adds: list[AlignedElement]) -> str:
    """Concatenate text from all ADDED elements."""
    parts: list[str] = []
    for a in real_adds:
        text = _desired_text(a)
        if text:
            parts.append(text)
    return "".join(parts)


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

    # --- INSERT phase ---
    if real_adds:
        combined_text = _collect_add_text(real_adds)
        if not combined_text:
            return requests

        if real_deletes:
            if gap.left_anchor and not _is_section_break(gap.left_anchor):
                insert_idx = _el_end(gap.left_anchor) - 1
            else:
                assert first_del_el is not None
                insert_idx = _el_start(first_del_el)
        else:
            # Pure add at end (no deletes)
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
            requests.append(
                _make_insert_text(insert_text, insert_idx, segment_id, tab_id)
            )

    return requests


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

    # --- DELETE phase ---
    if real_deletes:
        assert first_del_el is not None
        assert last_del_el is not None
        delete_start = _el_start(first_del_el)
        delete_end = _el_end(last_del_el)
        if delete_start < delete_end:
            requests.append(
                _make_delete_range(delete_start, delete_end, segment_id, tab_id)
            )

    # --- INSERT phase ---
    if real_adds:
        combined_text = _collect_add_text(real_adds)
        if not combined_text:
            return requests

        if real_deletes:
            assert first_del_el is not None
            insert_idx = _el_start(first_del_el)
        elif gap.right_anchor:
            insert_idx = _el_start(gap.right_anchor)
        else:
            insert_idx = 1

        requests.append(
            _make_insert_text(combined_text, insert_idx, segment_id, tab_id)
        )

    return requests
