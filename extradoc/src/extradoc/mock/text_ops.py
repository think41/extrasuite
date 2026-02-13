"""Text insertion and deletion operations for the mock Google Docs API.

These handlers modify content directly without managing indices.
The reindex pass fixes all indices after each operation.
"""

from __future__ import annotations

import copy
from typing import Any

from extradoc.mock.exceptions import ValidationError
from extradoc.mock.navigation import get_segment, get_tab
from extradoc.mock.utils import calculate_utf16_offset, strip_control_characters
from extradoc.mock.validation import (
    validate_no_surrogate_pair_split,
    validate_no_table_cell_final_newline_deletion,
)


def handle_insert_text(
    document: dict[str, Any],
    request: dict[str, Any],
    structure_tracker: Any,
) -> dict[str, Any]:
    """Handle InsertTextRequest."""
    text = request.get("text", "")
    location = request.get("location")
    end_of_segment = request.get("endOfSegmentLocation")

    has_location = location is not None
    has_end_of_segment = end_of_segment is not None

    if not has_location and not has_end_of_segment:
        raise ValidationError("Must specify either location or endOfSegmentLocation")
    if has_location and has_end_of_segment:
        raise ValidationError("Cannot specify both location and endOfSegmentLocation")

    text = strip_control_characters(text)

    if location:
        index = location["index"]
        tab_id = location.get("tabId")
        segment_id = location.get("segmentId")
        _insert_text_impl(document, text, index, tab_id, segment_id)
    else:
        if end_of_segment is None:
            raise ValidationError("endOfSegmentLocation is required")
        tab_id = end_of_segment.get("tabId")
        segment_id = end_of_segment.get("segmentId")
        tab = get_tab(document, tab_id)
        segment, _ = get_segment(tab, segment_id)

        content = segment.get("content", [])
        if content:
            last_elem = content[-1]
            end_index = last_elem.get("endIndex", 1)
            insert_index = max(1, end_index - 1)
            _insert_text_impl(document, text, insert_index, tab_id, segment_id)

    return {}


def handle_delete_content_range(
    document: dict[str, Any],
    request: dict[str, Any],
    structure_tracker: Any,
) -> dict[str, Any]:
    """Handle DeleteContentRangeRequest."""
    range_obj = request.get("range")
    if not range_obj:
        raise ValidationError("range is required")

    start_index = range_obj["startIndex"]
    end_index = range_obj["endIndex"]
    tab_id = range_obj.get("tabId")
    segment_id = range_obj.get("segmentId")

    _delete_content_range_impl(
        document, start_index, end_index, tab_id, segment_id, structure_tracker
    )
    return {}


def _insert_text_impl(
    document: dict[str, Any],
    text: str,
    index: int,
    tab_id: str | None,
    segment_id: str | None,
) -> None:
    """Insert text at a specific index."""
    tab = get_tab(document, tab_id)
    segment, segment_type = get_segment(tab, segment_id)

    min_index = 1 if segment_type == "body" else 0
    if index < min_index:
        raise ValidationError(f"Index must be at least {min_index}, got {index}")

    content = segment.get("content", [])
    if not content:
        raise ValidationError(f"Segment {segment_type} has no content")

    last_element = content[-1]
    max_index = last_element.get("endIndex", 1)

    if index >= max_index:
        raise ValidationError(f"Index {index} is beyond segment end {max_index - 1}")

    for element in content:
        if "table" in element:
            table_start = element.get("startIndex", 0)
            if index == table_start:
                raise ValidationError(
                    "Cannot insert text at table start index. "
                    "Insert in the preceding paragraph instead."
                )

    if "\n" in text:
        _insert_text_with_newlines(segment, index, text)
    else:
        _insert_text_simple(segment, index, text)


def _insert_text_simple(segment: dict[str, Any], index: int, text: str) -> None:
    """Insert text without creating new paragraphs.

    Only modifies content strings — indices are fixed by reindex.
    """
    content = segment.get("content", [])

    for element in content:
        elem_start = element.get("startIndex", 0)
        elem_end = element.get("endIndex", 0)

        if elem_start <= index < elem_end and "paragraph" in element:
            paragraph = element["paragraph"]
            para_elements = paragraph.get("elements", [])

            for para_elem in para_elements:
                run_start = para_elem.get("startIndex", 0)
                run_end = para_elem.get("endIndex", 0)

                if run_start <= index <= run_end and "textRun" in para_elem:
                    text_run = para_elem["textRun"]
                    content_str = text_run.get("content", "")

                    offset_in_run = calculate_utf16_offset(
                        content_str, index - run_start
                    )

                    new_content = (
                        content_str[:offset_in_run] + text + content_str[offset_in_run:]
                    )
                    text_run["content"] = new_content
                    # Don't update indices — reindex handles it
                    return

    raise ValidationError(f"Could not find paragraph to insert at index {index}")


def _insert_text_with_newlines(segment: dict[str, Any], index: int, text: str) -> None:
    """Insert text that contains newlines, creating new paragraphs.

    Modifies content structure — indices are fixed by reindex.
    """
    content = segment.get("content", [])

    for elem_idx, element in enumerate(content):
        elem_start = element.get("startIndex", 0)
        elem_end = element.get("endIndex", 0)

        if elem_start <= index < elem_end and "paragraph" in element:
            paragraph = element["paragraph"]
            para_elements = paragraph.get("elements", [])
            para_style = copy.deepcopy(paragraph.get("paragraphStyle", {}))

            # Step 1: Collect all runs, inserting text into the target run
            runs: list[tuple[str, dict[str, Any]]] = []
            inserted = False
            for pe in para_elements:
                if "textRun" not in pe:
                    continue
                run_start = pe.get("startIndex", 0)
                run_end = pe.get("endIndex", 0)
                run_content = pe["textRun"].get("content", "")
                run_style = pe["textRun"].get("textStyle", {})

                if not inserted and run_start <= index <= run_end:
                    offset = calculate_utf16_offset(run_content, index - run_start)
                    new_content = run_content[:offset] + text + run_content[offset:]
                    runs.append((new_content, copy.deepcopy(run_style)))
                    inserted = True
                else:
                    runs.append((run_content, copy.deepcopy(run_style)))

            # Step 2: Split runs at \n boundaries to form paragraph groups
            para_groups: list[list[tuple[str, dict[str, Any]]]] = []
            current_group: list[tuple[str, dict[str, Any]]] = []

            for content_str, style in runs:
                while "\n" in content_str:
                    nl_idx = content_str.index("\n")
                    before = content_str[: nl_idx + 1]
                    after = content_str[nl_idx + 1 :]

                    if before:
                        current_group.append((before, style))
                    para_groups.append(current_group)
                    current_group = []
                    content_str = after
                    style = copy.deepcopy(style)

                if content_str:
                    current_group.append((content_str, style))

            if current_group:
                para_groups.append(current_group)

            # Step 3: Build new structural elements (indices set to 0, reindex fixes them)
            new_elements: list[dict[str, Any]] = []

            for group in para_groups:
                if not group:
                    continue

                elements: list[dict[str, Any]] = []
                for text_content, style in group:
                    elements.append(
                        {
                            "startIndex": 0,
                            "endIndex": 0,
                            "textRun": {
                                "content": text_content,
                                "textStyle": style,
                            },
                        }
                    )

                para_dict: dict[str, Any] = {
                    "elements": elements,
                    "paragraphStyle": copy.deepcopy(para_style),
                }
                if "bullet" in paragraph:
                    para_dict["bullet"] = copy.deepcopy(paragraph["bullet"])
                new_elements.append(
                    {
                        "startIndex": 0,
                        "endIndex": 0,
                        "paragraph": para_dict,
                    }
                )

            # Step 4: Replace old element
            content[elem_idx : elem_idx + 1] = new_elements
            # No index shifting needed — reindex handles it
            return

    raise ValidationError(f"Could not find paragraph to insert at index {index}")


def _delete_content_range_impl(
    document: dict[str, Any],
    start_index: int,
    end_index: int,
    tab_id: str | None,
    segment_id: str | None,
    structure_tracker: Any,
) -> None:
    """Delete content range with full validation."""
    tab = get_tab(document, tab_id)
    segment, segment_type = get_segment(tab, segment_id)

    min_index = 1 if segment_type == "body" else 0
    if start_index < min_index:
        raise ValidationError(
            f"startIndex must be at least {min_index}, got {start_index}"
        )
    if end_index <= start_index:
        raise ValidationError(
            f"endIndex ({end_index}) must be greater than startIndex ({start_index})"
        )

    content = segment.get("content", [])
    if not content:
        raise ValidationError(f"Segment {segment_type} has no content")

    last_element = content[-1]
    max_index = last_element.get("endIndex", 1)

    validate_no_surrogate_pair_split(segment, start_index, end_index)

    if end_index >= max_index:
        raise ValidationError(
            f"Cannot delete the final newline of {segment_type}. "
            f"Deletion range {start_index}-{end_index} includes final newline at {max_index - 1}"
        )

    validate_no_table_cell_final_newline_deletion(
        tab, segment_id, start_index, end_index
    )

    structure_tracker.validate_delete_range(start_index, end_index)

    _delete_content_from_segment(segment, start_index, end_index)


def _delete_content_from_segment(
    segment: dict[str, Any], start_index: int, end_index: int
) -> None:
    """Delete content from a segment.

    When deletion crosses paragraph boundaries (removing a \\n), the
    affected paragraphs are merged. The first paragraph's style is kept.
    Indices are set to 0 — reindex fixes them.
    """
    content = segment.get("content", [])

    # Find affected paragraphs
    affected_indices: list[int] = []
    for i, element in enumerate(content):
        elem_start = element.get("startIndex", 0)
        elem_end = element.get("endIndex", 0)
        if elem_start < end_index and elem_end > start_index and "paragraph" in element:
            affected_indices.append(i)

    # If the last affected paragraph's \n is being deleted, include next paragraph
    if affected_indices:
        last_affected = affected_indices[-1]
        last_elem = content[last_affected]
        last_end = last_elem.get("endIndex", 0)
        if end_index >= last_end:
            for j in range(last_affected + 1, len(content)):
                if "paragraph" in content[j]:
                    affected_indices.append(j)
                    break

    if not affected_indices:
        return

    # Collect surviving runs
    surviving_runs: list[tuple[str, dict[str, Any], dict[str, Any], bool]] = []

    for idx in affected_indices:
        paragraph = content[idx]["paragraph"]
        para_props = {k: v for k, v in paragraph.items() if k != "elements"}

        for pe in paragraph.get("elements", []):
            if "textRun" not in pe:
                continue
            run_start = pe.get("startIndex", 0)
            run_end = pe.get("endIndex", 0)
            run_content = pe["textRun"].get("content", "")
            run_style = pe["textRun"].get("textStyle", {})

            if run_end <= start_index or run_start >= end_index:
                surviving_runs.append(
                    (run_content, copy.deepcopy(run_style), para_props, False)
                )
            elif run_start >= start_index and run_end <= end_index:
                continue
            else:
                del_from = max(0, start_index - run_start)
                del_to = min(run_end - run_start, end_index - run_start)
                str_from = calculate_utf16_offset(run_content, del_from)
                str_to = calculate_utf16_offset(run_content, del_to)
                remaining = run_content[:str_from] + run_content[str_to:]
                if remaining:
                    surviving_runs.append(
                        (remaining, copy.deepcopy(run_style), para_props, True)
                    )

    # Consolidate same-style runs only across paragraph boundaries (merge scenario).
    # When a \n is deleted, runs from different paragraphs get merged.
    # The real API consolidates those, but keeps within-paragraph runs separate.
    consolidated: list[tuple[str, dict[str, Any], dict[str, Any], bool]] = []
    for run in surviving_runs:
        if (
            consolidated
            and consolidated[-1][1] == run[1]
            and "\n" not in consolidated[-1][0]
            # Only consolidate across paragraph boundaries
            and consolidated[-1][2] is not run[2]
        ):
            prev = consolidated[-1]
            consolidated[-1] = (
                prev[0] + run[0],
                prev[1],
                prev[2],
                prev[3] or run[3],
            )
        else:
            consolidated.append(run)
    surviving_runs = consolidated

    # Re-split into paragraphs based on \n boundaries
    para_groups: list[tuple[list[tuple[str, dict[str, Any]]], dict[str, Any]]] = []
    current_group: list[tuple[str, dict[str, Any]]] = []
    first_props_in_group: dict[str, Any] | None = None

    for content_str, style, props, _modified in surviving_runs:
        if first_props_in_group is None:
            first_props_in_group = props
        while "\n" in content_str:
            nl_idx = content_str.index("\n")
            before = content_str[: nl_idx + 1]
            after = content_str[nl_idx + 1 :]
            if before:
                current_group.append((before, style))
            para_groups.append(
                (current_group, copy.deepcopy(first_props_in_group or {}))
            )
            current_group = []
            first_props_in_group = None
            content_str = after
            style = copy.deepcopy(style)
        if content_str:
            current_group.append((content_str, style))
            if first_props_in_group is None:
                first_props_in_group = props

    if current_group and first_props_in_group is not None:
        para_groups.append((current_group, copy.deepcopy(first_props_in_group)))

    # Build new structural elements (indices = 0, reindex fixes them)
    new_elements: list[dict[str, Any]] = []

    for group, props in para_groups:
        if not group:
            continue
        elements: list[dict[str, Any]] = []
        for text_content, style in group:
            elements.append(
                {
                    "startIndex": 0,
                    "endIndex": 0,
                    "textRun": {"content": text_content, "textStyle": style},
                }
            )
        para_dict: dict[str, Any] = copy.deepcopy(props)
        para_dict["elements"] = elements
        new_elements.append(
            {
                "startIndex": 0,
                "endIndex": 0,
                "paragraph": para_dict,
            }
        )

    # Replace affected elements
    first_idx = affected_indices[0]
    last_idx = affected_indices[-1]
    content[first_idx : last_idx + 1] = new_elements
    # No index shifting — reindex handles it
