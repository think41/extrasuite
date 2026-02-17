"""Centralized reindex and normalize passes for document segments.

After each request handler modifies document content, these functions
are called to fix all indices and normalize text runs. This replaces
the error-prone incremental index shifting that was spread across
~15 locations in the old code.
"""

from __future__ import annotations

import copy
from typing import Any

from extradoc.indexer import utf16_len


def reindex_segment(segment: dict[str, Any], *, is_body: bool = True) -> None:
    """Walk all content in a segment and assign correct indices.

    For body segments:
    - If the first element is a sectionBreak, it starts at index 0
    - If there's no sectionBreak, paragraphs start at index 1
      (the implicit sectionBreak occupies index 0)

    For non-body segments (headers/footers/footnotes):
    - Content starts at index 0

    Args:
        segment: A segment dict with a "content" key.
        is_body: True for body segments, False for headers/footers/footnotes.
    """
    content = segment.get("content", [])
    if not content:
        return

    # Determine starting index.
    # Body with sectionBreak starts at 0; otherwise body content starts at 1.
    # Non-body segments (headers/footers/footnotes) start at 0.
    current_idx = (0 if "sectionBreak" in content[0] else 1) if is_body else 0

    is_first_element = True
    for element in content:
        if "sectionBreak" in element:
            # Real API omits startIndex on sectionBreak (always first element)
            element.pop("startIndex", None)
            element["endIndex"] = current_idx + 1
            current_idx += 1
            is_first_element = False
        elif "paragraph" in element:
            # Non-body segments: omit startIndex on first element
            if not is_body and is_first_element and current_idx == 0:
                element.pop("startIndex", None)
            else:
                element["startIndex"] = current_idx

            # Walk paragraph elements (text runs, inline objects)
            paragraph = element["paragraph"]
            para_elements = paragraph.get("elements", [])
            is_first_pe = is_first_element
            for pe in para_elements:
                if "textRun" in pe:
                    size = utf16_len(pe["textRun"].get("content", ""))
                elif (
                    "inlineObjectElement" in pe
                    or "autoText" in pe
                    or "pageBreak" in pe
                    or "footnoteReference" in pe
                    or "horizontalRule" in pe
                    or "columnBreak" in pe
                ):
                    size = 1
                elif "equation" in pe:
                    size = pe.get("endIndex", 0) - pe.get("startIndex", 0)
                    if size <= 0:
                        size = 1
                else:
                    size = pe.get("endIndex", 0) - pe.get("startIndex", 0)
                    if size <= 0:
                        size = 1

                # Non-body segments: omit startIndex on first para element
                if not is_body and is_first_pe and current_idx == 0:
                    pe.pop("startIndex", None)
                else:
                    pe["startIndex"] = current_idx
                is_first_pe = False
                pe["endIndex"] = current_idx + size
                current_idx += size

            element["endIndex"] = current_idx
            is_first_element = False
        elif "table" in element:
            element["startIndex"] = current_idx
            current_idx = _reindex_table(element["table"], current_idx)
            current_idx += 1  # table end marker
            element["endIndex"] = current_idx
            is_first_element = False
        elif "tableOfContents" in element:
            element["startIndex"] = current_idx
            # Preserve existing size for TOC
            size = element.get("endIndex", 0) - element.get("startIndex", 0)
            if size <= 0:
                size = 1
            element["endIndex"] = current_idx + size
            current_idx = element["endIndex"]
        else:
            size = element.get("endIndex", 0) - element.get("startIndex", 0)
            if size <= 0:
                size = 1
            element["startIndex"] = current_idx
            element["endIndex"] = current_idx + size
            current_idx += size


def _reindex_table(table: dict[str, Any], table_start: int) -> int:
    """Reindex a table's internal structure.

    Uses the original index structure to determine overhead (markers)
    per row and cell, then recalculates based on actual content sizes.

    Args:
        table: The table dict (not the structural element wrapper).
        table_start: The start index of the table element.

    Returns:
        The current index after the last row (before table end marker).
    """
    rows = table.get("tableRows", [])
    if not rows:
        return table_start + 1

    # Detect the overhead structure by examining the first row/cell
    first_row = rows[0]
    first_cells = first_row.get("tableCells", [])
    has_cell_start = bool(first_cells and "startIndex" in first_cells[0])

    if has_cell_start:
        # Full structure with explicit markers on rows and cells
        current_idx = table_start + 1  # table start marker

        for row in rows:
            row["startIndex"] = current_idx
            current_idx += 1  # row marker

            for cell in row.get("tableCells", []):
                cell["startIndex"] = current_idx
                current_idx += 1  # cell marker

                current_idx = _reindex_cell_content(cell, current_idx)
                cell["endIndex"] = current_idx

            row["endIndex"] = current_idx
    else:
        # Cells don't have explicit startIndex. Detect the overhead
        # structure from the first cell's content position.
        first_content = first_cells[0].get("content", [{}])[0] if first_cells else {}
        first_content_start = first_content.get("startIndex", table_start + 1)
        # Total overhead from table start to first cell content
        total_initial_overhead = first_content_start - table_start

        # Detect inter-cell overhead from gap between end of cell 1 content
        # and start of cell 2 content
        cell_gap = 1  # default
        if len(first_cells) >= 2:
            c1_content = first_cells[0].get("content", [])
            c2_content = first_cells[1].get("content", [])
            if c1_content and c2_content:
                c1_end = c1_content[-1].get("endIndex", 0)
                c2_start = c2_content[0].get("startIndex", 0)
                if c2_start > c1_end:
                    cell_gap = c2_start - c1_end

        # Now reindex: start from table_start + total_initial_overhead
        current_idx = table_start + total_initial_overhead

        is_first_cell = True
        for row in rows:
            for cell in row.get("tableCells", []):
                if is_first_cell:
                    is_first_cell = False
                else:
                    current_idx += cell_gap  # inter-cell gap
                current_idx = _reindex_cell_content(cell, current_idx)

    return current_idx


def _reindex_cell_content(cell: dict[str, Any], current_idx: int) -> int:
    """Reindex the content elements within a table cell.

    Args:
        cell: Table cell dict.
        current_idx: Starting index for the content.

    Returns:
        Index after all cell content.
    """
    for content_elem in cell.get("content", []):
        if "paragraph" in content_elem:
            content_elem["startIndex"] = current_idx
            paragraph = content_elem["paragraph"]
            for pe in paragraph.get("elements", []):
                if "textRun" in pe:
                    size = utf16_len(pe["textRun"].get("content", ""))
                elif "inlineObjectElement" in pe:
                    size = 1
                else:
                    size = pe.get("endIndex", 0) - pe.get("startIndex", 0)
                    if size <= 0:
                        size = 1
                pe["startIndex"] = current_idx
                pe["endIndex"] = current_idx + size
                current_idx += size
            content_elem["endIndex"] = current_idx
        elif "table" in content_elem:
            content_elem["startIndex"] = current_idx
            current_idx = _reindex_table(content_elem["table"], current_idx)
            current_idx += 1  # nested table end marker
            content_elem["endIndex"] = current_idx
        else:
            size = content_elem.get("endIndex", 0) - content_elem.get("startIndex", 0)
            if size <= 0:
                size = 1
            content_elem["startIndex"] = current_idx
            content_elem["endIndex"] = current_idx + size
            current_idx += size
    return current_idx


def normalize_segment(segment: dict[str, Any]) -> None:
    """Normalize text runs in all paragraphs of a segment.

    For every paragraph (including inside table cells):
    1. Split runs that contain \\n followed by other text -> two runs
    2. Consolidate adjacent same-style textRuns (never merge \\n-only runs)
    3. Remove empty textRuns

    Args:
        segment: A segment dict with a "content" key.
    """
    for element in segment.get("content", []):
        if "paragraph" in element:
            _normalize_paragraph(element["paragraph"])
        elif "table" in element:
            _normalize_table(element["table"])
        elif "tableOfContents" in element:
            for toc_elem in element["tableOfContents"].get("content", []):
                if "paragraph" in toc_elem:
                    _normalize_paragraph(toc_elem["paragraph"])


def _normalize_table(table: dict[str, Any]) -> None:
    """Normalize all paragraphs inside a table."""
    for row in table.get("tableRows", []):
        for cell in row.get("tableCells", []):
            for content_elem in cell.get("content", []):
                if "paragraph" in content_elem:
                    _normalize_paragraph(content_elem["paragraph"])
                elif "table" in content_elem:
                    _normalize_table(content_elem["table"])


def _normalize_paragraph(paragraph: dict[str, Any]) -> None:
    """Normalize text runs in a single paragraph.

    Steps:
    1. Split runs where \\n appears mid-run (not at end)
    2. Consolidate adjacent same-style runs (except \\n-only runs)
    3. Remove empty runs
    """
    elements = paragraph.get("elements", [])
    if not elements:
        return

    # Step 1: Split runs with \n in the middle
    split_elements: list[dict[str, Any]] = []
    for elem in elements:
        if "textRun" not in elem:
            split_elements.append(elem)
            continue

        content = elem["textRun"].get("content", "")
        style = elem["textRun"].get("textStyle", {})

        if not content:
            continue  # skip empty runs

        # Split at \n boundaries: each \n ends a run
        parts: list[str] = []
        current = ""
        for ch in content:
            current += ch
            if ch == "\n":
                parts.append(current)
                current = ""
        if current:
            parts.append(current)

        for part in parts:
            if "link" in style and part.endswith("\n") and len(part) > 1:
                # Split "text\n" into "text" (with link) and "\n" (without link)
                text_part = part[:-1]
                split_elements.append(
                    {
                        "startIndex": 0,
                        "endIndex": 0,
                        "textRun": {
                            "content": text_part,
                            "textStyle": copy.deepcopy(style),
                        },
                    }
                )
                nl_style = copy.deepcopy(style)
                nl_style.pop("link", None)
                nl_style.pop("foregroundColor", None)
                split_elements.append(
                    {
                        "startIndex": 0,
                        "endIndex": 0,
                        "textRun": {
                            "content": "\n",
                            "textStyle": nl_style,
                        },
                    }
                )
            else:
                part_style = copy.deepcopy(style)
                # The real API strips link from a standalone \n
                if part == "\n" and "link" in part_style:
                    part_style.pop("link", None)
                    part_style.pop("foregroundColor", None)
                split_elements.append(
                    {
                        "startIndex": 0,
                        "endIndex": 0,
                        "textRun": {
                            "content": part,
                            "textStyle": part_style,
                        },
                    }
                )

    # Step 2: No consolidation — the real API preserves run boundaries
    paragraph["elements"] = split_elements


def _update_para_nesting_level(
    paragraph: dict[str, Any], lists: dict[str, Any]
) -> None:
    """Update nestingLevel in a bulleted paragraph based on its indentStart.

    Looks up the paragraph's list definition and finds which nesting level
    has an indentStart matching the paragraph's current indentStart.
    """
    bullet = paragraph.get("bullet")
    if not bullet:
        return
    list_id = bullet.get("listId")
    if not list_id:
        return
    list_def = lists.get(list_id, {})
    nesting_levels_def = list_def.get("listProperties", {}).get("nestingLevels", [])
    if not nesting_levels_def:
        return

    ps = paragraph.get("paragraphStyle", {})
    indent_start = ps.get("indentStart")
    if not isinstance(indent_start, dict):
        return
    target_magnitude = indent_start.get("magnitude")
    target_unit = indent_start.get("unit", "PT")
    if target_magnitude is None:
        return

    for level_idx, level_def in enumerate(nesting_levels_def):
        level_indent = level_def.get("indentStart", {})
        if isinstance(level_indent, dict) and (
            level_indent.get("magnitude") == target_magnitude
            and level_indent.get("unit", "PT") == target_unit
        ):
            if level_idx == 0:
                bullet.pop("nestingLevel", None)
            else:
                bullet["nestingLevel"] = level_idx
            return


def _update_nesting_levels_in_table(
    table: dict[str, Any], lists: dict[str, Any]
) -> None:
    """Update nestingLevel in all bulleted paragraphs inside a table."""
    for row in table.get("tableRows", []):
        for cell in row.get("tableCells", []):
            for ce in cell.get("content", []):
                if "paragraph" in ce:
                    _update_para_nesting_level(ce["paragraph"], lists)
                elif "table" in ce:
                    _update_nesting_levels_in_table(ce["table"], lists)


def _update_nesting_levels_in_segment(
    segment: dict[str, Any], lists: dict[str, Any]
) -> None:
    """Update nestingLevel in all bulleted paragraphs in a segment."""
    for element in segment.get("content", []):
        if "paragraph" in element:
            _update_para_nesting_level(element["paragraph"], lists)
        elif "table" in element:
            _update_nesting_levels_in_table(element["table"], lists)


def reindex_and_normalize_all_tabs(document: dict[str, Any]) -> None:
    """Reindex and normalize all segments across all tabs.

    Called after each request in batch_update().

    Args:
        document: The full document dict.
    """
    for tab in document.get("tabs", []):
        doc_tab = tab.get("documentTab", {})
        lists = doc_tab.get("lists", {})

        # Body
        body = doc_tab.get("body")
        if body:
            normalize_segment(body)
            reindex_segment(body, is_body=True)
            _update_nesting_levels_in_segment(body, lists)

        # Headers
        for header in doc_tab.get("headers", {}).values():
            normalize_segment(header)
            reindex_segment(header, is_body=False)
            _update_nesting_levels_in_segment(header, lists)

        # Footers
        for footer in doc_tab.get("footers", {}).values():
            normalize_segment(footer)
            reindex_segment(footer, is_body=False)
            _update_nesting_levels_in_segment(footer, lists)

        # Footnotes
        for footnote in doc_tab.get("footnotes", {}).values():
            normalize_segment(footnote)
            reindex_segment(footnote, is_body=False)
            _update_nesting_levels_in_segment(footnote, lists)
