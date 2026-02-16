"""Text insertion and deletion operations for the mock Google Docs API.

These handlers modify content directly without managing indices.
The reindex pass fixes all indices after each operation.
"""

from __future__ import annotations

import copy
from typing import Any

from extradoc.mock.exceptions import ValidationError
from extradoc.mock.navigation import get_segment, get_tab
from extradoc.mock.utils import (
    calculate_utf16_offset,
    merge_explicit_keys,
    strip_control_characters,
    styles_equal_ignoring_explicit,
)
from extradoc.mock.validation import (
    validate_no_surrogate_pair_split,
    validate_no_table_cell_final_newline_deletion,
)


def _strip_link_style(run_style: dict[str, Any]) -> dict[str, Any]:
    """Build inherited style for text inserted into a link run.

    The real API strips link, foregroundColor from the inserted text.
    Only properties that were explicitly set via updateTextStyle (tracked
    in __explicit__) are kept. If there are no explicit non-link styles,
    the result is {}.

    Note: styles from the original document that weren't set via
    updateTextStyle in this mock session will not have __explicit__
    tracking, so they'll be treated as inherited and stripped. This
    matches the real API's behavior for most cases but may differ when
    original-doc styles should be preserved (see S44 in known failures).
    """
    explicit = set(run_style.get("__explicit__", []))
    link_auto_keys = {"link", "foregroundColor", "underline"}
    explicit_non_link = explicit - link_auto_keys
    if not explicit_non_link:
        return {}
    result: dict[str, Any] = {}
    for k, v in run_style.items():
        if k == "__explicit__":
            continue
        if k in ("link", "foregroundColor"):
            continue
        if k == "underline" and "underline" not in explicit:
            continue
        result[k] = copy.deepcopy(v)
    new_explicit = sorted(explicit_non_link & set(result.keys()))
    if new_explicit:
        result["__explicit__"] = new_explicit
    return result


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
    Recurses into table cells when the index falls within a table.
    """
    content = segment.get("content", [])

    for element in content:
        elem_start = element.get("startIndex", 0)
        elem_end = element.get("endIndex", 0)

        if elem_start <= index < elem_end and "paragraph" in element:
            _insert_into_paragraph(element["paragraph"], index, text)
            return

        if elem_start <= index < elem_end and "table" in element:
            # Recurse into table cells
            for row in element["table"].get("tableRows", []):
                for cell in row.get("tableCells", []):
                    for cell_elem in cell.get("content", []):
                        ce_start = cell_elem.get("startIndex", 0)
                        ce_end = cell_elem.get("endIndex", 0)
                        if ce_start <= index < ce_end and "paragraph" in cell_elem:
                            _insert_into_paragraph(cell_elem["paragraph"], index, text)
                            return

    raise ValidationError(f"Could not find paragraph to insert at index {index}")


def _insert_into_paragraph(paragraph: dict[str, Any], index: int, text: str) -> None:
    """Insert simple text (no newlines) into a paragraph at the given index."""
    para_elements = paragraph.get("elements", [])

    for pe_idx, para_elem in enumerate(para_elements):
        run_start = para_elem.get("startIndex", 0)
        run_end = para_elem.get("endIndex", 0)

        if run_start <= index <= run_end and "textRun" in para_elem:
            text_run = para_elem["textRun"]
            content_str = text_run.get("content", "")
            run_style = text_run.get("textStyle", {})

            offset_in_run = calculate_utf16_offset(content_str, index - run_start)

            if "link" in run_style:
                inherited_style = _strip_link_style(run_style)
                before = content_str[:offset_in_run]
                after = content_str[offset_in_run:]
                new_elements: list[dict[str, Any]] = []
                if before:
                    new_elements.append(
                        {
                            "startIndex": 0,
                            "endIndex": 0,
                            "textRun": {
                                "content": before,
                                "textStyle": copy.deepcopy(run_style),
                            },
                        }
                    )
                new_elements.append(
                    {
                        "startIndex": 0,
                        "endIndex": 0,
                        "textRun": {
                            "content": text,
                            "textStyle": inherited_style,
                        },
                    }
                )
                if after:
                    new_elements.append(
                        {
                            "startIndex": 0,
                            "endIndex": 0,
                            "textRun": {
                                "content": after,
                                "textStyle": copy.deepcopy(run_style),
                            },
                        }
                    )
                para_elements[pe_idx : pe_idx + 1] = new_elements
            else:
                new_content = (
                    content_str[:offset_in_run] + text + content_str[offset_in_run:]
                )
                text_run["content"] = new_content
            return

    raise ValidationError(f"Could not find text run to insert at index {index}")


def _insert_text_with_newlines(segment: dict[str, Any], index: int, text: str) -> None:
    """Insert text that contains newlines, creating new paragraphs.

    Modifies content structure — indices are fixed by reindex.
    Recurses into table cells when the index falls within a table.
    """
    content = segment.get("content", [])

    # Check if index falls within a table cell
    for element in content:
        elem_start = element.get("startIndex", 0)
        elem_end = element.get("endIndex", 0)
        if elem_start <= index < elem_end and "table" in element:
            for row in element["table"].get("tableRows", []):
                for cell in row.get("tableCells", []):
                    cell_content = cell.get("content", [])
                    for cell_elem in cell_content:
                        ce_start = cell_elem.get("startIndex", 0)
                        ce_end = cell_elem.get("endIndex", 0)
                        if ce_start <= index < ce_end and "paragraph" in cell_elem:
                            # Delegate to cell-level insertion
                            _insert_text_with_newlines_in_cell(
                                cell, cell_content, cell_elem, index, text
                            )
                            return
            raise ValidationError(
                f"Could not find paragraph in table cell at index {index}"
            )

    for elem_idx, element in enumerate(content):
        elem_start = element.get("startIndex", 0)
        elem_end = element.get("endIndex", 0)

        if elem_start <= index < elem_end and "paragraph" in element:
            paragraph = element["paragraph"]
            para_elements = paragraph.get("elements", [])
            para_style = copy.deepcopy(paragraph.get("paragraphStyle", {}))

            # Step 1: Collect all runs, inserting text into the target run.
            # When inserting into a link-styled run, the inserted text gets
            # empty textStyle {} (the real API does not propagate link styles).
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
                    if "link" in run_style:
                        # Link runs: strip link+foregroundColor, keep explicit styles
                        inherited_style = _strip_link_style(run_style)
                        before = run_content[:offset]
                        after = run_content[offset:]
                        if before:
                            runs.append((before, copy.deepcopy(run_style)))
                        runs.append((text, inherited_style))
                        if after:
                            runs.append((after, copy.deepcopy(run_style)))
                    else:
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


def _insert_text_with_newlines_in_cell(
    cell: dict[str, Any],
    cell_content: list[dict[str, Any]],
    target_elem: dict[str, Any],
    index: int,
    text: str,
) -> None:
    """Insert text with newlines into a table cell paragraph.

    Creates new paragraphs within the cell's content list.
    """
    paragraph = target_elem["paragraph"]
    para_elements = paragraph.get("elements", [])
    para_style = copy.deepcopy(paragraph.get("paragraphStyle", {}))

    # Find the target element index in cell content
    elem_idx = cell_content.index(target_elem)

    # Collect all runs, inserting text into the target run
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

    # Split runs at \n boundaries to form paragraph groups
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

    # Build new structural elements
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
                    "textRun": {"content": text_content, "textStyle": style},
                }
            )
        new_elements.append(
            {
                "startIndex": 0,
                "endIndex": 0,
                "paragraph": {
                    "elements": elements,
                    "paragraphStyle": copy.deepcopy(para_style),
                },
            }
        )

    # Replace old element in cell content
    cell_content[elem_idx : elem_idx + 1] = new_elements


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


def _delete_content_from_table_cells(
    table: dict[str, Any], start_index: int, end_index: int
) -> None:
    """Delete content within table cells.

    Finds the cell(s) that overlap the delete range and delegates
    to the standard paragraph deletion logic within each cell.
    """
    for row in table.get("tableRows", []):
        for cell in row.get("tableCells", []):
            cell_content = cell.get("content", [])
            if not cell_content:
                continue
            cell_start = cell_content[0].get("startIndex", 0)
            cell_end = cell_content[-1].get("endIndex", 0)
            if cell_start < end_index and cell_end > start_index:
                # Range overlaps this cell — use cell as a mini-segment
                _delete_content_from_cell(cell, start_index, end_index)
                return


def _delete_content_from_cell(
    cell: dict[str, Any], start_index: int, end_index: int
) -> None:
    """Delete content from a table cell (analogous to segment-level delete).

    Only handles paragraph content within cells. Rebuilt elements omit
    startIndex/endIndex so the table reindex overhead detection works
    correctly (Minimal Structure tables read the first cell content's
    startIndex to compute overhead).
    """
    content = cell.get("content", [])

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

    # Re-split into paragraphs
    para_groups: list[tuple[list[tuple[str, dict[str, Any]]], dict[str, Any]]] = []
    current_group: list[tuple[str, dict[str, Any]]] = []
    first_props: dict[str, Any] | None = None

    for content_str, style, props, _modified in surviving_runs:
        if first_props is None:
            first_props = props
        while "\n" in content_str:
            nl_idx = content_str.index("\n")
            before = content_str[: nl_idx + 1]
            after = content_str[nl_idx + 1 :]
            if before:
                current_group.append((before, style))
            para_groups.append((current_group, copy.deepcopy(first_props or {})))
            current_group = []
            first_props = None
            content_str = after
            style = copy.deepcopy(style)
        if content_str:
            current_group.append((content_str, style))
            if first_props is None:
                first_props = props

    if current_group and first_props is not None:
        para_groups.append((current_group, copy.deepcopy(first_props)))

    # Build new structural elements — omit startIndex/endIndex so the
    # Minimal Structure table reindex overhead detection works correctly.
    # The reindex pass will assign correct indices.
    new_elements: list[dict[str, Any]] = []
    for group, props in para_groups:
        if not group:
            continue
        elements: list[dict[str, Any]] = []
        for text_content, style in group:
            elements.append({"textRun": {"content": text_content, "textStyle": style}})
        para_dict: dict[str, Any] = copy.deepcopy(props)
        para_dict["elements"] = elements
        new_elements.append({"paragraph": para_dict})

    first_idx = affected_indices[0]
    last_idx = affected_indices[-1]
    content[first_idx : last_idx + 1] = new_elements

    # Mark cell for Full Structure reindex. The Minimal Structure path
    # uses stale indices from unmodified cells to compute overhead, which
    # breaks when a cell's content changes size. Adding startIndex to the
    # cell dict triggers has_cell_start → Full Structure reindex.
    cell["startIndex"] = 0


def _delete_content_from_segment(
    segment: dict[str, Any], start_index: int, end_index: int
) -> None:
    """Delete content from a segment.

    Handles paragraphs, whole tables, and within-cell deletion.
    When deletion crosses paragraph boundaries (removing a \\n), the
    affected paragraphs are merged. The first paragraph's style is kept.
    Indices are set to 0 — reindex fixes them.
    """
    content = segment.get("content", [])

    # Check if range falls within a table cell — delegate to cell-level delete
    for element in content:
        if "table" not in element:
            continue
        table_start = element.get("startIndex", 0)
        table_end = element.get("endIndex", 0)
        if (
            table_start < end_index
            and table_end > start_index
            and not (start_index <= table_start and end_index >= table_end)
        ):
            # Range overlaps table but doesn't fully cover it → within-cell
            _delete_content_from_table_cells(element["table"], start_index, end_index)
            return

    # Find affected elements (paragraphs and fully-covered tables)
    affected_indices: list[int] = []
    for i, element in enumerate(content):
        elem_start = element.get("startIndex", 0)
        elem_end = element.get("endIndex", 0)
        if elem_start < end_index and elem_end > start_index:
            if "paragraph" in element:
                affected_indices.append(i)
            elif (
                "table" in element
                and start_index <= elem_start
                and end_index >= elem_end
            ):
                # Only include tables when fully covered by delete range
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

    # Collect surviving runs (skip table elements — they're just removed)
    surviving_runs: list[tuple[str, dict[str, Any], dict[str, Any], bool]] = []

    for idx in affected_indices:
        element = content[idx]
        if "table" in element:
            continue  # Whole table deletion, no surviving runs
        paragraph = element["paragraph"]
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
            and styles_equal_ignoring_explicit(consolidated[-1][1], run[1])
            and "\n" not in consolidated[-1][0]
            # Only consolidate across paragraph boundaries
            and consolidated[-1][2] is not run[2]
        ):
            prev = consolidated[-1]
            merged_style = copy.deepcopy(prev[1])
            merge_explicit_keys(merged_style, run[1])
            consolidated[-1] = (
                prev[0] + run[0],
                merged_style,
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
