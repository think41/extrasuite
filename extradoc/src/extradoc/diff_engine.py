"""Diff engine for ExtraDoc XML.

Compares pristine and edited documents to generate Google Docs batchUpdate requests.
Uses block-level diff detection for structural changes.

This module orchestrates the diff/request generation process, delegating to
specialized modules for style conversion and request generation:
- style_converter: Declarative style mappings and conversion
- request_generators/: Structural, table, and content request generation
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any

from .block_diff import (
    BlockChange,
    BlockType,
    ChangeType,
    diff_documents_block_level,
)
from .desugar import (
    desugar_document,
)
from .indexer import calculate_table_indexes, utf16_len
from .request_generators.table import (
    generate_delete_table_column_request,
    generate_delete_table_row_request,
    generate_insert_table_column_request,
    generate_insert_table_row_request,
)
from .style_converter import (
    PARAGRAPH_STYLE_PROPS,
    TABLE_CELL_STYLE_PROPS,
    TEXT_STYLE_PROPS,
    build_table_cell_style_request,
    convert_styles,
)

# --- Helpers for style mapping ---


def parse_cell_styles(styles_xml: str | None) -> dict[str, dict[str, str]]:
    """Parse cell styles from styles.xml content.

    Args:
        styles_xml: The styles.xml content, or None

    Returns:
        Dict mapping style ID (e.g., "cell-abc123") to style properties
    """
    if not styles_xml:
        return {}

    try:
        root = ET.fromstring(styles_xml)
    except ET.ParseError:
        return {}

    cell_styles: dict[str, dict[str, str]] = {}
    for style_elem in root.findall("style"):
        style_id = style_elem.get("id", "")
        if style_id.startswith("cell-"):
            # Extract all attributes except 'id' as style properties
            props = {k: v for k, v in style_elem.attrib.items() if k != "id"}
            cell_styles[style_id] = props

    return cell_styles


def parse_text_styles(styles_xml: str | None) -> dict[str, dict[str, str]]:
    """Parse text styles from styles.xml content.

    Text styles are any styles that are NOT cell styles (i.e., don't start with "cell-").
    These are used for inline text styling via <span class="..."> elements.

    Args:
        styles_xml: The styles.xml content, or None

    Returns:
        Dict mapping style ID to style properties (e.g., {"highlight-yellow": {"bg": "#FFFF00"}})
    """
    if not styles_xml:
        return {}

    try:
        root = ET.fromstring(styles_xml)
    except ET.ParseError:
        return {}

    text_styles: dict[str, dict[str, str]] = {}
    for style_elem in root.findall("style"):
        style_id = style_elem.get("id", "")
        # Skip cell styles - they're handled separately
        if style_id.startswith("cell-"):
            continue
        # Extract all attributes except 'id' as style properties
        props = {k: v for k, v in style_elem.attrib.items() if k != "id"}
        if props:  # Only add if there are actual properties
            text_styles[style_id] = props

    return text_styles


def _extract_column_widths(table_xml: str | None) -> dict[int, str]:
    """Extract column widths from table XML.

    Parses <col index="N" width="Xpt"/> elements from table XML.

    Args:
        table_xml: The table XML string, or None

    Returns:
        Dict mapping column index to width string (e.g., {0: "100pt", 1: "200pt"})
    """
    if not table_xml:
        return {}

    try:
        root = ET.fromstring(table_xml)
    except ET.ParseError:
        return {}

    import contextlib

    widths: dict[int, str] = {}
    for col_elem in root.findall("col"):
        index_str = col_elem.get("index", "")
        width = col_elem.get("width", "")
        if index_str and width:
            with contextlib.suppress(ValueError):
                widths[int(index_str)] = width

    return widths


def _generate_column_width_requests(
    table_start_index: int,
    before_widths: dict[int, str],
    after_widths: dict[int, str],
    segment_id: str | None,
) -> list[dict[str, Any]]:
    """Generate UpdateTableColumnPropertiesRequest for column width changes.

    Args:
        table_start_index: The table's start index
        before_widths: Column widths from pristine table
        after_widths: Column widths from current table
        segment_id: The segment ID (for headers/footers/footnotes)

    Returns:
        List of updateTableColumnProperties requests
    """
    requests: list[dict[str, Any]] = []

    # Find all columns that have changed
    all_columns = set(before_widths.keys()) | set(after_widths.keys())

    for col_index in sorted(all_columns):
        before_width = before_widths.get(col_index)
        after_width = after_widths.get(col_index)

        if before_width == after_width:
            continue

        # Column width changed
        request: dict[str, Any] = {
            "updateTableColumnProperties": {
                "tableStartLocation": {"index": table_start_index},
                "columnIndices": [col_index],
                "tableColumnProperties": {},
                "fields": "",
            }
        }

        if segment_id:
            request["updateTableColumnProperties"]["tableStartLocation"][
                "segmentId"
            ] = segment_id

        col_props = request["updateTableColumnProperties"]["tableColumnProperties"]
        fields: list[str] = []

        if after_width:
            # Set to fixed width
            # Parse width value (e.g., "100pt" -> magnitude=100, unit=PT)
            match = re.match(r"([\d.]+)(pt|in|mm)?", after_width, re.IGNORECASE)
            if match:
                magnitude = float(match.group(1))
                unit = (match.group(2) or "pt").upper()
                col_props["widthType"] = "FIXED_WIDTH"
                col_props["width"] = {"magnitude": magnitude, "unit": unit}
                fields.extend(["widthType", "width"])
        else:
            # Changed back to evenly distributed
            col_props["widthType"] = "EVENLY_DISTRIBUTED"
            fields.append("widthType")

        request["updateTableColumnProperties"]["fields"] = ",".join(fields)
        requests.append(request)

    return requests


def diff_documents(
    pristine_xml: str,
    current_xml: str,
    pristine_styles: str | None = None,
    current_styles: str | None = None,
    raw_table_indexes: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    """Compare two XML documents and generate batchUpdate requests.

    Uses block-level diff detection to identify changes, then generates
    requests using a backwards walk algorithm. Each segment (body, header,
    footer, footnote) is processed independently. Within each segment,
    changes are walked from highest pristine index to lowest, emitting
    requests in execution order. This guarantees that when processing
    element at pristine position P, everything at positions < P is still
    at pristine state.

    Args:
        pristine_xml: The pristine document XML
        current_xml: The current document XML
        pristine_styles: The pristine styles.xml content
        current_styles: The current styles.xml content
        raw_table_indexes: Optional dict of table indexes from raw API response
            (used for property-only changes like column widths)
    """
    # Get block-level changes
    block_changes = diff_documents_block_level(
        pristine_xml, current_xml, pristine_styles, current_styles
    )

    # If no changes, return empty list
    if not block_changes:
        return []

    # Calculate table indexes for current document
    # Used for property changes (column widths) where we need the live table position
    # Pristine indexes are no longer needed — the backwards walk uses
    # change.pristine_start_index directly from the block diff
    if raw_table_indexes is not None:
        current_table_indexes = raw_table_indexes
    else:
        current_doc = desugar_document(current_xml, current_styles)
        current_table_indexes = calculate_table_indexes(current_doc.sections)

    # Parse cell styles from styles.xml for class attribute resolution
    cell_styles = parse_cell_styles(current_styles)

    # Parse text styles from styles.xml for span class resolution
    text_styles = parse_text_styles(current_styles)

    # Group changes by segment and walk each backwards
    segments = _group_changes_by_segment(block_changes)
    all_requests: list[dict[str, Any]] = []
    for segment_key, segment_changes in segments.items():
        all_requests.extend(
            _walk_segment_backwards(
                segment_changes,
                segment_key,
                current_table_indexes,
                cell_styles,
                text_styles,
            )
        )

    return all_requests


def _group_changes_by_segment(
    changes: list[BlockChange],
) -> dict[str, list[BlockChange]]:
    """Group block changes by segment.

    Each segment (body, header, footer, footnote) has its own index space
    and is processed independently.

    Returns:
        Dict mapping segment key to list of changes, sorted ascending
        by pristine_start_index within each segment.
    """
    segments: dict[str, list[BlockChange]] = {}

    for change in changes:
        key = _segment_key_from_change(change)
        if key not in segments:
            segments[key] = []
        segments[key].append(change)

    # Sort each segment's changes ascending by pristine_start_index
    for key in segments:
        segments[key].sort(key=lambda c: c.pristine_start_index)

    return segments


def _segment_key_from_change(change: BlockChange) -> str:
    """Derive a segment key from a BlockChange.

    For changes with a container_path, the key comes from the first path element
    (e.g., "body:body" -> "body", "header:kix.abc" -> "header:kix.abc").

    For top-level structural changes (HEADER/FOOTER/TAB/FOOTNOTE block types)
    with empty container_path, derive the key from block_type and block_id.
    """
    if change.container_path:
        first = change.container_path[0]
        if first.startswith("body:"):
            return "body"
        return first

    # Top-level structural changes without container_path
    if change.block_type == BlockType.HEADER:
        return f"header:{change.block_id}" if change.block_id else "header"
    if change.block_type == BlockType.FOOTER:
        return f"footer:{change.block_id}" if change.block_id else "footer"
    if change.block_type == BlockType.FOOTNOTE:
        return f"footnote:{change.block_id}" if change.block_id else "footnote"
    if change.block_type == BlockType.TAB:
        return f"tab:{change.block_id}" if change.block_id else "tab"

    return "body"


def _walk_segment_backwards(
    changes: list[BlockChange],
    segment_key: str,
    current_table_indexes: dict[str, int],
    cell_styles: dict[str, dict[str, str]] | None,
    text_styles: dict[str, dict[str, str]] | None,
) -> list[dict[str, Any]]:
    """Walk changes in a segment from highest to lowest pristine index.

    Core invariant: when processing element at pristine position P,
    everything at positions < P is still at pristine state.
    """
    requests: list[dict[str, Any]] = []
    segment_id = _segment_id_from_key(segment_key)

    for change in reversed(changes):
        if change.block_type == BlockType.CONTENT_BLOCK:
            requests.extend(_emit_content_block(change, segment_id, text_styles))
        elif change.block_type == BlockType.TABLE:
            requests.extend(
                _emit_table(
                    change,
                    segment_id,
                    current_table_indexes,
                    cell_styles,
                    text_styles,
                )
            )
        elif change.block_type in (BlockType.HEADER, BlockType.FOOTER):
            requests.extend(_handle_header_footer_change(change))
        elif change.block_type == BlockType.FOOTNOTE:
            requests.extend(_handle_footnote_change(change))
        elif change.block_type == BlockType.TAB:
            requests.extend(_handle_tab_change(change))

    return requests


def _segment_id_from_key(segment_key: str) -> str | None:
    """Extract segment ID from segment key.

    Returns None for body, or the segment ID for headers/footers/footnotes.
    """
    if segment_key == "body":
        return None
    if ":" in segment_key:
        prefix, sid = segment_key.split(":", 1)
        if prefix in ("header", "footer", "footnote"):
            return sid
    return None


def _emit_content_block(
    change: BlockChange,
    segment_id: str | None,
    text_styles: dict[str, dict[str, str]] | None,
) -> list[dict[str, Any]]:
    """Emit requests for a ContentBlock change."""
    requests: list[dict[str, Any]] = []

    # Handle footnote child_changes first
    base_index = (
        change.pristine_start_index
        if change.pristine_start_index > 0
        else (1 if segment_id is None else 0)
    )

    for child_change in change.child_changes:
        if child_change.block_type == BlockType.FOOTNOTE:
            content_xml = (
                change.after_xml
                if child_change.change_type == ChangeType.ADDED
                else change.before_xml
            )
            requests.extend(
                _handle_footnote_change(child_change, content_xml, base_index)
            )

    segment_start = 1 if segment_id is None else 0
    segment_end = change.segment_end_index if change.segment_end_index > 0 else None

    requests.extend(
        _emit_content_ops(
            change,
            segment_id,
            segment_start,
            segment_end,
            text_styles,
        )
    )

    return requests


def _emit_table(
    change: BlockChange,
    segment_id: str | None,
    current_table_indexes: dict[str, int],
    cell_styles: dict[str, dict[str, str]] | None,
    text_styles: dict[str, dict[str, str]] | None,
) -> list[dict[str, Any]]:
    """Emit requests for a TABLE change."""
    # Column add/delete changes are represented as child_changes of TABLE when present
    column_changes = [
        c for c in change.child_changes if c.block_type == BlockType.TABLE_COLUMN
    ]

    if change.change_type == ChangeType.ADDED:
        if change.after_xml:
            insert_index = (
                change.pristine_start_index if change.pristine_start_index > 0 else 0
            )
            return _generate_table_add_requests(
                change.after_xml, segment_id, insert_index, text_styles
            )

    elif change.change_type == ChangeType.DELETED:
        if change.before_xml and change.pristine_start_index > 0:
            return _generate_table_delete_requests(
                change.before_xml, segment_id, change.pristine_start_index
            )

    elif change.change_type == ChangeType.MODIFIED:
        return _emit_table_modify(
            change,
            segment_id,
            current_table_indexes,
            cell_styles,
            text_styles,
            column_changes=column_changes,
        )

    return []


def _emit_table_modify(
    change: BlockChange,
    segment_id: str | None,
    current_table_indexes: dict[str, int],
    cell_styles: dict[str, dict[str, str]] | None,
    text_styles: dict[str, dict[str, str]] | None = None,
    column_changes: list[BlockChange] | None = None,
) -> list[dict[str, Any]]:
    """Emit requests for a modified table using backwards cell walk.

    Walks rows backwards, and within each row walks cells backwards,
    maintaining the invariant that operations on later cells don't shift
    indexes of earlier cells.
    """
    requests: list[dict[str, Any]] = []
    table_start = change.pristine_start_index

    # Column width changes (uses current table index)
    before_widths = _extract_column_widths(change.before_xml)
    after_widths = _extract_column_widths(change.after_xml)
    if before_widths != after_widths:
        current_table_start = _get_table_start_index(
            change.container_path, current_table_indexes
        )
        if current_table_start > 0:
            requests.extend(
                _generate_column_width_requests(
                    current_table_start, before_widths, after_widths, segment_id
                )
            )

    if table_start == 0:
        return requests

    # Track column operations to deduplicate
    columns_deleted: set[int] = set()
    columns_added: set[int] = set()
    deferred_col_adds: list[tuple[int, dict[str, Any]]] = []

    # Apply column add/delete first based on column_changes
    if column_changes:
        for col_change in column_changes:
            col_idx = _get_col_index_from_change(col_change)
            if (
                col_change.change_type == ChangeType.ADDED
                and col_idx not in columns_added
            ):
                columns_added.add(col_idx)
                deferred_col_adds.append(
                    (
                        col_idx,
                        generate_insert_table_column_request(
                            table_start, 0, col_idx, segment_id
                        ),
                    )
                )
            elif (
                col_change.change_type == ChangeType.DELETED
                and col_idx not in columns_deleted
            ):
                columns_deleted.add(col_idx)
                requests.append(
                    generate_delete_table_column_request(
                        table_start, 0, col_idx, segment_id
                    )
                )

    # Walk rows backwards
    row_changes = [
        c for c in change.child_changes if c.block_type == BlockType.TABLE_ROW
    ]
    row_changes.sort(key=lambda c: _get_row_index_from_change(c), reverse=True)
    # (row_index, insert_request, after_xml_for_cell_content)
    deferred_row_adds: list[tuple[int, dict[str, Any], str | None]] = []

    # Determine pristine row count from before_xml (if any)
    pristine_row_count = 0
    try:
        if change.before_xml:
            pristine_row_count = len(ET.fromstring(change.before_xml).findall("tr"))
    except ET.ParseError:
        pristine_row_count = 0
    last_pristine_row = max(pristine_row_count - 1, 0)

    for row_change in row_changes:
        row_index = _get_row_index_from_change(row_change)

        if row_change.change_type == ChangeType.ADDED:
            if row_index == 0 or pristine_row_count == 0:
                anchor = 0
                deferred_row_adds.append(
                    (
                        row_index,
                        generate_insert_table_row_request(
                            table_start, anchor, segment_id, insert_below=False
                        ),
                        row_change.after_xml,
                    )
                )
            else:
                anchor = min(row_index - 1, last_pristine_row)
                deferred_row_adds.append(
                    (
                        row_index,
                        generate_insert_table_row_request(
                            table_start, anchor, segment_id, insert_below=True
                        ),
                        row_change.after_xml,
                    )
                )

        elif row_change.change_type == ChangeType.DELETED:
            requests.append(
                generate_delete_table_row_request(table_start, row_index, segment_id)
            )

        elif row_change.change_type == ChangeType.MODIFIED:
            # Walk cells backwards within this row
            cell_changes = sorted(
                [
                    c
                    for c in row_change.child_changes
                    if c.block_type == BlockType.TABLE_CELL
                ],
                key=lambda c: _get_col_index_from_change(c),
                reverse=True,
            )

            for cell_change in cell_changes:
                col_index = _get_col_index_from_change(cell_change)

                # If column handled structurally, allow only content ADD for added cols; skip others
                if col_index in columns_added:
                    if (
                        cell_change.change_type
                        in (ChangeType.ADDED, ChangeType.MODIFIED)
                        and cell_change.after_xml
                    ):
                        cell_content_index = cell_change.pristine_start_index
                        cell_end = (
                            cell_change.segment_end_index
                            if cell_change.segment_end_index > 0
                            else cell_content_index
                        )
                        if cell_content_index > 0:
                            after_inner = _extract_cell_inner_content(
                                cell_change.after_xml or ""
                            )
                            content_change = BlockChange(
                                change_type=ChangeType.ADDED,
                                block_type=BlockType.CONTENT_BLOCK,
                                before_xml=None,
                                after_xml=after_inner,
                                pristine_start_index=cell_content_index,
                                pristine_end_index=cell_end,
                                segment_end_index=cell_end,
                            )
                            requests.extend(
                                _emit_content_ops(
                                    content_change,
                                    segment_id,
                                    cell_content_index,
                                    cell_end,
                                    text_styles,
                                )
                            )
                    continue

                if col_index in columns_deleted:
                    # Content is removed by deleteTableColumn; skip
                    continue

                if cell_change.change_type == ChangeType.MODIFIED and change.before_xml:
                    cell_content_index = cell_change.pristine_start_index
                    cell_end = (
                        cell_change.segment_end_index
                        if cell_change.segment_end_index > 0
                        else cell_content_index
                    )
                    if cell_content_index > 0 and cell_end >= cell_content_index:
                        before_inner = _extract_cell_inner_content(
                            cell_change.before_xml or ""
                        )
                        after_inner = _extract_cell_inner_content(
                            cell_change.after_xml or ""
                        )
                        content_change = BlockChange(
                            change_type=ChangeType.MODIFIED,
                            block_type=BlockType.CONTENT_BLOCK,
                            before_xml=before_inner,
                            after_xml=after_inner,
                            pristine_start_index=cell_content_index,
                            pristine_end_index=max(cell_end - 1, cell_content_index),
                            segment_end_index=cell_end,
                        )
                        requests.extend(
                            _emit_content_ops(
                                content_change,
                                segment_id,
                                cell_content_index,
                                cell_end,
                                text_styles,
                            )
                        )

                        # Cell styling
                        cell_style_req = _generate_cell_style_request(
                            cell_change.after_xml or "",
                            table_start,
                            row_index,
                            col_index,
                            segment_id,
                            cell_styles,
                        )
                        if cell_style_req:
                            requests.append(cell_style_req)

    # Apply deferred inserts last to avoid index shifts
    for _, req in sorted(deferred_col_adds, key=lambda item: item[0], reverse=True):
        requests.append(req)

    # Insert content for newly added columns (non-empty cells only).
    # After insertTableColumn, new cells are empty (just '\n' = 1 unit).
    # Each row gets a new cell marker (1 unit) + newline (1 unit) = 2 units.
    # Calculate new cell position using PRISTINE table, then adjust for
    # the 2-unit-per-row shift from new empty cells in earlier rows.
    if columns_added and change.after_xml and change.before_xml:
        try:
            after_root = ET.fromstring(change.after_xml)
        except ET.ParseError:
            after_root = None
        if after_root is not None:
            rows_after = after_root.findall("tr")
            for col_idx in sorted(columns_added, reverse=True):
                for row_idx in reversed(range(len(rows_after))):
                    td_xml = _get_cell_xml_from_table(
                        change.after_xml, row_idx, col_idx
                    )
                    if not td_xml:
                        continue
                    inner = _extract_cell_inner_content(td_xml)
                    if not inner.strip():
                        continue
                    if col_idx == 0:
                        # Inserted left of pristine column 0
                        base = _calculate_cell_content_index(
                            table_start, row_idx, 0, change.before_xml
                        )
                        cell_start = base + 2 * row_idx
                    else:
                        # Inserted right of pristine column (col_idx - 1)
                        pristine_col = col_idx - 1
                        base = _calculate_cell_content_index(
                            table_start, row_idx, pristine_col, change.before_xml
                        )
                        pristine_len = _get_pristine_cell_length(
                            change.before_xml, row_idx, pristine_col
                        )
                        cell_start = base + pristine_len + 2 * row_idx + 1
                    if cell_start <= 0:
                        continue
                    content_reqs = _generate_content_insert_requests(
                        inner,
                        segment_id,
                        insert_index=cell_start,
                        strip_trailing_newline=True,
                        text_styles=text_styles,
                    )
                    requests.extend(content_reqs)

    # Emit deferred row inserts (highest row index first), then populate cells.
    # After insertTableRow, each new cell contains just '\n' (1 index unit).
    # We use the after_xml (current table) to calculate cell positions,
    # then insert content into each non-empty cell.
    for _, req, _row_after_xml in sorted(
        deferred_row_adds, key=lambda item: item[0], reverse=True
    ):
        requests.append(req)

    # Insert cell content for added rows.
    # After insertTableRow, each cell is empty ('\n' = 1 index unit).
    # Cell N content starts at: cell_0_start + 2*N
    # (each empty cell = 1 cell marker + 1 newline = 2 units).
    # We get cell_0_start from _calculate_cell_content_index for col 0
    # (which only walks PRIOR rows, not the new row's cells).
    # Walk cells right-to-left so earlier cell positions stay stable.
    if deferred_row_adds and change.after_xml:
        for row_index, _, row_after_xml in sorted(
            deferred_row_adds, key=lambda item: item[0]
        ):
            if not row_after_xml:
                continue
            try:
                row_root = ET.fromstring(row_after_xml)
            except ET.ParseError:
                continue
            cells = list(row_root.findall("td"))
            if not cells:
                continue
            # Cell 0 position is correct from _calculate_cell_content_index
            # because it stops as soon as it reaches (row, col=0).
            cell_0_start = _calculate_cell_content_index(
                table_start, row_index, 0, change.after_xml
            )
            if cell_0_start <= 0:
                continue
            # Walk cells right-to-left
            for col_idx in reversed(range(len(cells))):
                td = cells[col_idx]
                inner = _extract_cell_inner_content(ET.tostring(td, encoding="unicode"))
                if not inner.strip():
                    continue
                # Each empty cell = 2 index units (marker + newline)
                cell_start = cell_0_start + 2 * col_idx
                cell_end = cell_start + 1  # empty cell has just '\n'
                content_reqs = _generate_content_insert_requests(
                    inner,
                    segment_id,
                    insert_index=cell_start,
                    strip_trailing_newline=True,
                    text_styles=text_styles,
                )
                requests.extend(content_reqs)

    return requests


def _handle_header_footer_change(change: BlockChange) -> list[dict[str, Any]]:
    """Handle header/footer add/delete changes.

    Supported operations:
    - ADDED: createHeader/createFooter with type DEFAULT
    - DELETED: deleteHeader/deleteFooter with the segment ID
    - MODIFIED: Handled via child ContentBlock changes (Phase 3)
    """
    requests: list[dict[str, Any]] = []

    if change.change_type == ChangeType.ADDED:
        if change.block_type == BlockType.HEADER:
            requests.append({"createHeader": {"type": "DEFAULT"}})
        elif change.block_type == BlockType.FOOTER:
            requests.append({"createFooter": {"type": "DEFAULT"}})

    elif change.change_type == ChangeType.DELETED:
        # Extract the header/footer ID from the block_id
        segment_id = change.block_id
        if change.block_type == BlockType.HEADER and segment_id:
            requests.append({"deleteHeader": {"headerId": segment_id}})
        elif change.block_type == BlockType.FOOTER and segment_id:
            requests.append({"deleteFooter": {"footerId": segment_id}})

    return requests


def _handle_footnote_change(
    change: BlockChange,
    content_block_xml: str | None = None,
    base_index: int = 1,
) -> list[dict[str, Any]]:
    """Handle footnote add/delete changes.

    Args:
        change: The footnote change (ADDED/DELETED/MODIFIED)
        content_block_xml: The containing ContentBlock's XML for index calculation
        base_index: The starting index for the content block in the body

    For ADDED: Creates footnote at the calculated position
    For DELETED: Deletes the 1-character footnote reference
    For MODIFIED: Content changes handled via child_changes (Phase 3)
    """
    requests: list[dict[str, Any]] = []

    if change.change_type == ChangeType.ADDED:
        # For adding footnotes, we have two options:
        # 1. If we can calculate a precise index from content, use location
        # 2. Otherwise, use endOfSegmentLocation (adds at end)
        #
        # Note: Precise positioning requires Phase 3 (content handling) to ensure
        # the text exists before the footnote. For now, we use endOfSegmentLocation.
        #
        # TODO: Once Phase 3 is implemented, calculate precise index and use location
        requests.append(
            {
                "createFootnote": {
                    "endOfSegmentLocation": {}  # Adds footnote at end of body
                }
            }
        )

    elif change.change_type == ChangeType.DELETED:
        # Delete the 1-character footnote reference
        # Need to find the index in the pristine content
        index = _calculate_footnote_index(
            content_block_xml, change.block_id, base_index
        )
        if index > 0:
            requests.append(
                {
                    "deleteContentRange": {
                        "range": {
                            "startIndex": index,
                            "endIndex": index + 1,  # Footnote ref is 1 character
                        }
                    }
                }
            )

    return requests


def _calculate_footnote_index(
    content_xml: str | None,
    footnote_id: str,
    base_index: int,
) -> int:
    """Calculate the index where a footnote reference should be/is located.

    Parses the XML to find text content before the footnote tag.
    Returns the index in the body where the footnote reference is.
    """
    if not content_xml:
        return 0

    # Find the position of the footnote in the XML
    # The index is based on text content before the footnote
    pattern = rf'<footnote[^>]*id="{re.escape(footnote_id)}"'
    match = re.search(pattern, content_xml)
    if not match:
        return 0

    # Get content before the footnote
    before_footnote = content_xml[: match.start()]

    # Extract text content (strip tags)
    # Simple approach: count characters that aren't part of tags
    text_length = 0
    in_tag = False
    for char in before_footnote:
        if char == "<":
            in_tag = True
        elif char == ">":
            in_tag = False
        elif not in_tag:
            text_length += 1

    # Add newlines for paragraph breaks (each </p> or </h1> etc. adds a newline)
    newline_count = len(
        re.findall(r"</(?:p|h[1-6]|li|title|subtitle)>", before_footnote)
    )
    text_length += newline_count

    return base_index + text_length


def _handle_tab_change(change: BlockChange) -> list[dict[str, Any]]:
    """Handle document tab add/delete changes.

    Supported operations:
    - ADDED: addDocumentTab to create a new tab
    - DELETED: deleteTab to remove a tab (and its child tabs)
    - MODIFIED: Handled via child ContentBlock changes (Phase 3)
    """
    requests: list[dict[str, Any]] = []

    if change.change_type == ChangeType.ADDED:
        # Create a new tab - tabProperties are optional
        # Extract title from the change's XML if available
        tab_properties: dict[str, Any] = {}
        if change.after_xml:
            try:
                root = ET.fromstring(change.after_xml)
                title = root.get("title")
                if title:
                    tab_properties["title"] = title
            except ET.ParseError:
                pass
        requests.append({"addDocumentTab": {"tabProperties": tab_properties}})

    elif change.change_type == ChangeType.DELETED:
        # Delete the tab by ID
        tab_id = change.block_id
        if tab_id:
            requests.append({"deleteTab": {"tabId": tab_id}})

    return requests


@dataclass
class ParsedContent:
    """Parsed content block ready for request generation.

    Attributes:
        plain_text: Text content with newlines between paragraphs (no special elements)
        special_elements: List of (offset, element_type, attributes) for special elements
        paragraph_styles: List of (start_offset, end_offset, named_style) for headings
        paragraph_props: List of (start_offset, end_offset, props_dict) for paragraph style attrs
            (align, spaceAbove, spaceBelow, borderTop, borderBottom, etc.)
        bullets: List of (start_offset, end_offset, bullet_type, level) for list items
        text_styles: List of (start_offset, end_offset, styles_dict) for inline formatting
    """

    plain_text: str
    special_elements: list[tuple[int, str, dict[str, str]]]
    paragraph_styles: list[tuple[int, int, str]]
    paragraph_props: list[tuple[int, int, dict[str, str]]]
    bullets: list[tuple[int, int, str, int]]
    text_styles: list[tuple[int, int, dict[str, str]]]


def _parse_content_block_xml(
    xml_content: str,
    style_defs: dict[str, dict[str, str]] | None = None,
) -> ParsedContent:
    """Parse ContentBlock XML into structured data for request generation.

    The XML content is a sequence of paragraph elements (p, h1, li, etc.).
    This function extracts:
    - Plain text with newlines between paragraphs
    - Special element positions (pagebreak, hr, etc.)
    - Paragraph styles (headings)
    - Bullet list info
    - Text run styles (bold, italic, links)

    Args:
        xml_content: The ContentBlock XML (sequence of paragraph elements)
        style_defs: Map of style class ID to properties (from styles.xml)
            Used to resolve <span class="..."> to actual style properties.
    """
    # Wrap in a root element for parsing
    wrapped = f"<root>{xml_content}</root>"
    root = ET.fromstring(wrapped)

    # Paragraph style attributes we support (from PARAGRAPH_STYLE_PROPS)
    para_style_attrs = {
        "align",
        "lineSpacing",
        "spaceAbove",
        "spaceBelow",
        "indentLeft",
        "indentRight",
        "indentFirst",
        "keepTogether",
        "keepNext",
        "avoidWidow",
        "direction",
        "bgColor",
        "borderTop",
        "borderBottom",
        "borderLeft",
        "borderRight",
    }

    plain_text_parts: list[str] = []
    special_elements: list[tuple[int, str, dict[str, str]]] = []
    paragraph_styles: list[tuple[int, int, str]] = []
    paragraph_props: list[tuple[int, int, dict[str, str]]] = []
    bullets: list[tuple[int, int, str, int]] = []
    text_styles: list[tuple[int, int, dict[str, str]]] = []

    current_offset = 0  # UTF-16 offset tracking

    for para_elem in root:
        tag = para_elem.tag
        para_start = current_offset

        # Determine paragraph type
        named_style = "NORMAL_TEXT"
        bullet_type = None
        bullet_level = 0

        if tag in HEADING_STYLES:
            named_style = HEADING_STYLES[tag]
        elif tag == "li":
            bullet_type = para_elem.get("type", "bullet")
            bullet_level = int(para_elem.get("level", "0"))

        # Extract text runs from this paragraph
        para_text, para_specials, para_text_styles = _extract_paragraph_content(
            para_elem, current_offset, style_defs
        )

        # For nested bullets, prepend leading tabs (Google Docs uses tabs for nesting)
        if bullet_level > 0:
            tabs = "\t" * bullet_level
            # Adjust text style offsets to account for prepended tabs
            tab_len = utf16_len(tabs)
            para_text = tabs + para_text
            para_specials = [
                (offset + tab_len, elem_type, attrs)
                for offset, elem_type, attrs in para_specials
            ]
            para_text_styles = [
                (start + tab_len, end + tab_len, styles)
                for start, end, styles in para_text_styles
            ]

        plain_text_parts.append(para_text)
        special_elements.extend(para_specials)
        text_styles.extend(para_text_styles)

        # Calculate paragraph end (after newline)
        para_end = current_offset + utf16_len(para_text) + 1  # +1 for newline

        # Track paragraph style if not normal
        if named_style != "NORMAL_TEXT":
            paragraph_styles.append((para_start, para_end, named_style))

        # Extract paragraph style attributes (align, spaceAbove, borderTop, etc.)
        para_props_dict = {
            k: v for k, v in para_elem.attrib.items() if k in para_style_attrs
        }

        # Resolve class attribute to style properties from styles.xml
        class_name = para_elem.get("class")
        if class_name and style_defs and class_name in style_defs:
            class_props = style_defs[class_name]

            # Map style.xml property names to para_style_attrs names
            style_to_para_mapping = {
                "alignment": "align",
            }

            # Text-level properties that can apply to the whole paragraph
            text_style_props = {
                "bg",
                "color",
                "font",
                "size",
                "bold",
                "italic",
                "underline",
                "strikethrough",
            }

            para_class_styles: dict[str, str] = {}
            text_class_styles: dict[str, str] = {}

            for prop, value in class_props.items():
                # Map property name if needed
                mapped_prop = style_to_para_mapping.get(prop, prop)

                if mapped_prop in para_style_attrs:
                    # Paragraph-level property
                    if mapped_prop not in para_props_dict:  # Don't override explicit
                        para_class_styles[mapped_prop] = value
                elif prop in text_style_props:
                    # Text-level property - will be applied as text style
                    text_class_styles[prop] = value

            # Merge paragraph styles from class
            para_props_dict.update(para_class_styles)

            # Add text style covering the whole paragraph content
            if text_class_styles and para_text:
                # Calculate actual text range (excluding tabs for nested bullets)
                text_start = para_start
                if bullet_level > 0:
                    text_start += bullet_level  # Skip tab characters
                text_end = para_start + utf16_len(para_text)
                if text_start < text_end:
                    text_styles.append((text_start, text_end, text_class_styles))

        if para_props_dict:
            paragraph_props.append((para_start, para_end, para_props_dict))

        # Track bullets
        if bullet_type:
            bullets.append((para_start, para_end, bullet_type, bullet_level))

        # Update offset (text + newline)
        current_offset = para_end

    # Join paragraphs with newlines
    plain_text = "\n".join(plain_text_parts)
    if plain_text_parts:
        plain_text += "\n"  # Trailing newline for last paragraph

    return ParsedContent(
        plain_text=plain_text,
        special_elements=special_elements,
        paragraph_styles=paragraph_styles,
        paragraph_props=paragraph_props,
        bullets=bullets,
        text_styles=text_styles,
    )


# Heading tag to named style mapping (duplicated from desugar for independence)
HEADING_STYLES = {
    "title": "TITLE",
    "subtitle": "SUBTITLE",
    "h1": "HEADING_1",
    "h2": "HEADING_2",
    "h3": "HEADING_3",
    "h4": "HEADING_4",
    "h5": "HEADING_5",
    "h6": "HEADING_6",
}

# Inline formatting tags
INLINE_STYLE_TAGS = {
    "b": "bold",
    "i": "italic",
    "u": "underline",
    "s": "strikethrough",
    "sup": "superscript",
    "sub": "subscript",
}

# Special elements that consume 1 index
SPECIAL_ELEMENT_TAGS = {"hr", "pagebreak", "columnbreak", "image", "footnote"}


def _extract_paragraph_content(
    para_elem: ET.Element,
    base_offset: int,
    style_defs: dict[str, dict[str, str]] | None = None,
) -> tuple[
    str, list[tuple[int, str, dict[str, str]]], list[tuple[int, int, dict[str, str]]]
]:
    """Extract text, special elements, and text styles from a paragraph element.

    Args:
        para_elem: The paragraph XML element
        base_offset: The starting offset for this paragraph
        style_defs: Map of style class ID to properties (from styles.xml)
            Used to resolve <span class="..."> to actual style properties.

    Returns:
        - plain_text: Text content (no special elements)
        - special_elements: List of (offset, element_type, attributes)
        - text_styles: List of (start_offset, end_offset, styles_dict)
    """
    plain_text_parts: list[str] = []
    special_elements: list[tuple[int, str, dict[str, str]]] = []
    text_styles: list[tuple[int, int, dict[str, str]]] = []

    current_offset = base_offset

    def process_node(node: ET.Element, inherited_styles: dict[str, str]) -> None:
        nonlocal current_offset

        tag = node.tag
        node_styles = inherited_styles.copy()

        # Update styles based on tag
        if tag in INLINE_STYLE_TAGS:
            node_styles[INLINE_STYLE_TAGS[tag]] = "1"
        elif tag == "a":
            href = node.get("href", "")
            if href:
                node_styles["link"] = href
        elif tag == "span":
            # Span with class - resolve to actual style properties from styles.xml
            class_name = node.get("class")
            if class_name and style_defs and class_name in style_defs:
                # Merge in the resolved style properties
                node_styles.update(style_defs[class_name])
            # Also copy any inline attributes (except class)
            for attr, value in node.attrib.items():
                if attr != "class":
                    node_styles[attr] = value

        # Handle text content
        if node.text:
            text = node.text
            text_len = utf16_len(text)
            plain_text_parts.append(text)

            # Track styles if any non-trivial styles
            style_dict = {k: v for k, v in node_styles.items() if v}
            if style_dict:
                text_styles.append(
                    (current_offset, current_offset + text_len, style_dict)
                )

            current_offset += text_len

        # Process children
        for child in node:
            child_tag = child.tag

            # Special elements
            if child_tag in SPECIAL_ELEMENT_TAGS:
                # Track position and attributes
                attrs = dict(child.attrib)
                special_elements.append((current_offset, child_tag, attrs))
                # Don't add to plain_text - will be inserted separately
            else:
                # Recurse for inline formatting
                process_node(child, node_styles)

            # Handle tail text
            if child.tail:
                tail = child.tail
                tail_len = utf16_len(tail)
                plain_text_parts.append(tail)

                # Tail inherits parent styles (not child's)
                style_dict = {k: v for k, v in node_styles.items() if v}
                if style_dict:
                    text_styles.append(
                        (current_offset, current_offset + tail_len, style_dict)
                    )

                current_offset += tail_len

    # Start processing from para element children
    # Handle para element's direct text
    if para_elem.text:
        text = para_elem.text
        text_len = utf16_len(text)
        plain_text_parts.append(text)
        current_offset += text_len

    # Process children
    for child in para_elem:
        child_tag = child.tag

        if child_tag in SPECIAL_ELEMENT_TAGS:
            attrs = dict(child.attrib)
            special_elements.append((current_offset, child_tag, attrs))
        else:
            process_node(child, {})

        if child.tail:
            tail = child.tail
            tail_len = utf16_len(tail)
            plain_text_parts.append(tail)
            current_offset += tail_len

    return "".join(plain_text_parts), special_elements, text_styles


def _generate_content_insert_requests(
    xml_content: str,
    segment_id: str | None,
    insert_index: int = 1,
    strip_trailing_newline: bool = False,
    text_styles: dict[str, dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """Generate insert requests for content XML.

    Strategy:
    1. Parse XML to extract plain text (with newlines), special elements, and styles
    2. Insert plain text - newlines automatically create paragraphs
    3. Insert special elements from highest offset to lowest
    4. Apply paragraph styles (headings)
    5. Apply bullets
    6. Apply text styles (bold, italic, links)

    Args:
        xml_content: The ContentBlock XML (sequence of paragraph elements)
        segment_id: The segment ID (header/footer/footnote ID, or None for body)
        insert_index: The index at which to insert (default 1 for body start)
        strip_trailing_newline: If True, strip the trailing newline from the text.
            Used when modifying content at segment end where we preserve the
            existing final newline rather than inserting a new one.
        text_styles: Map of text style class ID to properties (from styles.xml)

    Returns:
        List of batchUpdate requests
    """
    if not xml_content or not xml_content.strip():
        return []

    requests: list[dict[str, Any]] = []

    # Parse the content
    parsed = _parse_content_block_xml(xml_content, text_styles)

    # Strip trailing newline if at segment end
    if strip_trailing_newline and parsed.plain_text.endswith("\n"):
        parsed = ParsedContent(
            plain_text=parsed.plain_text[:-1],
            special_elements=parsed.special_elements,
            paragraph_styles=parsed.paragraph_styles,
            paragraph_props=parsed.paragraph_props,
            bullets=parsed.bullets,
            text_styles=parsed.text_styles,
        )

    if not parsed.plain_text:
        return []

    # Build location for requests
    def make_location(index: int) -> dict[str, Any]:
        loc: dict[str, Any] = {"index": insert_index + index}
        if segment_id:
            loc["segmentId"] = segment_id
        return loc

    def make_range(start: int, end: int) -> dict[str, Any]:
        rng: dict[str, Any] = {
            "startIndex": insert_index + start,
            "endIndex": insert_index + end,
        }
        if segment_id:
            rng["segmentId"] = segment_id
        return rng

    # 1. Insert plain text
    requests.append(
        {
            "insertText": {
                "location": make_location(0),
                "text": parsed.plain_text,
            },
        }
    )

    # 1.5. Clear all formatting from inserted text
    # This prevents inheritance of styles from the insertion point
    # We reset bold, italic, underline, strikethrough, and baselineOffset
    text_len = utf16_len(parsed.plain_text)
    requests.append(
        {
            "updateTextStyle": {
                "range": make_range(0, text_len),
                "textStyle": {
                    "bold": False,
                    "italic": False,
                    "underline": False,
                    "strikethrough": False,
                    "baselineOffset": "NONE",
                },
                "fields": "bold,italic,underline,strikethrough,baselineOffset",
            },
        }
    )

    # 2. Insert special elements (highest offset first)
    for offset, elem_type, _attrs in sorted(
        parsed.special_elements, key=lambda x: x[0], reverse=True
    ):
        if elem_type == "pagebreak":
            requests.append(
                {
                    "insertPageBreak": {
                        "location": make_location(offset),
                    },
                }
            )
        elif elem_type == "columnbreak":
            # Column break is inserted via insertSectionBreak with CONTINUOUS type
            requests.append(
                {
                    "insertSectionBreak": {
                        "location": make_location(offset),
                        "sectionType": "CONTINUOUS",
                    },
                }
            )
        # Note: hr, image, footnote require different handling
        # hr: Can't be inserted directly, handled via paragraph border
        # image: Requires separate upload flow (attrs contains src, width, height)
        # footnote: Already handled in _handle_footnote_change

    # 3. Apply paragraph styles (headings)
    for start, end, named_style in parsed.paragraph_styles:
        requests.append(
            {
                "updateParagraphStyle": {
                    "range": make_range(start, end),
                    "paragraphStyle": {
                        "namedStyleType": named_style,
                    },
                    "fields": "namedStyleType",
                }
            }
        )

    # 3.5 Apply paragraph properties (align, spaceAbove, borderTop, etc.)
    for start, end, props in parsed.paragraph_props:
        para_style, para_fields = convert_styles(props, PARAGRAPH_STYLE_PROPS)
        if para_style and para_fields:
            requests.append(
                {
                    "updateParagraphStyle": {
                        "range": make_range(start, end),
                        "paragraphStyle": para_style,
                        "fields": ",".join(para_fields),
                    }
                }
            )

    # 4. Apply bullets - consolidate consecutive bullets of same type into single request
    # This is required because createParagraphBullets removes leading tabs, shifting indices
    if parsed.bullets:
        # Group consecutive bullets by type (must be adjacent - no gaps)
        bullet_groups: list[tuple[int, int, str]] = []  # (start, end, preset)
        for start, end, bullet_type, _level in parsed.bullets:
            preset = _bullet_type_to_preset(bullet_type)
            # Only extend if bullets are adjacent (prev_end == current_start) and same type
            if (
                bullet_groups
                and bullet_groups[-1][2] == preset
                and bullet_groups[-1][1] == start
            ):
                # Extend the previous group
                bullet_groups[-1] = (bullet_groups[-1][0], end, preset)
            else:
                # Start a new group
                bullet_groups.append((start, end, preset))

        # Create one request per group
        for group_start, group_end, preset in bullet_groups:
            requests.append(
                {
                    "createParagraphBullets": {
                        "range": make_range(group_start, group_end),
                        "bulletPreset": preset,
                    }
                }
            )
        # Note: Nesting level is determined by leading tabs in the inserted text
        # (handled in _parse_content_xml). Tabs are removed by createParagraphBullets.

    # 5. Apply text styles (bold, italic, links)
    for start, end, styles in parsed.text_styles:
        text_style, fields = _styles_to_text_style_request(styles)
        if text_style and fields:
            requests.append(
                {
                    "updateTextStyle": {
                        "range": make_range(start, end),
                        "textStyle": text_style,
                        "fields": fields,
                    }
                }
            )

    return requests


def _emit_content_ops(
    change: BlockChange,
    segment_id: str | None,
    segment_start: int,
    segment_end: int | None,
    text_styles: dict[str, dict[str, str]] | None,
) -> list[dict[str, Any]]:
    """Central handler for content add/delete/modify within a segment.

    segment_end is the exclusive end (position of the sentinel newline).
    """
    requests: list[dict[str, Any]] = []
    sentinel = (segment_end - 1) if segment_end and segment_end > 0 else None

    def clamp_range(start: int, end: int) -> tuple[int, int]:
        if sentinel is None:
            return start, end
        end = min(end, sentinel)
        return start, end

    def at_segment_end(idx: int) -> bool:
        return sentinel is not None and idx >= sentinel

    if change.change_type == ChangeType.DELETED:
        if (
            change.before_xml
            and change.pristine_end_index > change.pristine_start_index
        ):
            d_start, d_end = clamp_range(
                change.pristine_start_index, change.pristine_end_index
            )
            if d_start < d_end:
                requests.extend(
                    _generate_content_delete_requests_by_index(
                        d_start,
                        d_end,
                        segment_id,
                        segment_end or 0,
                    )
                )

    elif change.change_type == ChangeType.ADDED:
        if change.after_xml:
            insert_idx = change.pristine_start_index
            if insert_idx <= 0:
                insert_idx = segment_start
            if segment_end is not None:
                insert_idx = (
                    min(insert_idx, segment_end - 1)
                    if insert_idx > segment_end - 1
                    else insert_idx
                )
            strip_nl = at_segment_end(insert_idx)
            requests.extend(
                _generate_content_insert_requests(
                    change.after_xml,
                    segment_id,
                    insert_idx,
                    strip_trailing_newline=strip_nl,
                    text_styles=text_styles,
                )
            )

    elif change.change_type == ChangeType.MODIFIED:
        if (
            change.before_xml
            and change.pristine_end_index > change.pristine_start_index
        ):
            d_start, d_end = clamp_range(
                change.pristine_start_index, change.pristine_end_index
            )
            if d_start < d_end:
                requests.extend(
                    _generate_content_delete_requests_by_index(
                        d_start,
                        d_end,
                        segment_id,
                        segment_end or 0,
                    )
                )
        if change.after_xml:
            insert_idx = change.pristine_start_index
            if insert_idx <= 0:
                insert_idx = segment_start
            if segment_end is not None:
                insert_idx = (
                    min(insert_idx, segment_end - 1)
                    if insert_idx > segment_end - 1
                    else insert_idx
                )
            strip_nl = at_segment_end(change.pristine_end_index)
            requests.extend(
                _generate_content_insert_requests(
                    change.after_xml,
                    segment_id,
                    insert_idx,
                    strip_trailing_newline=strip_nl,
                    text_styles=text_styles,
                )
            )

    return requests


def _bullet_type_to_preset(bullet_type: str) -> str:
    """Convert bullet type to Google Docs bullet preset.

    Valid presets from Google Docs API:
    - BULLET_DISC_CIRCLE_SQUARE, BULLET_CHECKBOX, BULLET_ARROW_DIAMOND_DISC, etc.
    - NUMBERED_DECIMAL_NESTED, NUMBERED_DECIMAL_ALPHA_ROMAN
    - NUMBERED_UPPERALPHA_ALPHA_ROMAN (starts with A, B, C)
    - NUMBERED_UPPERROMAN_UPPERALPHA_DECIMAL (starts with I, II, III)
    """
    presets = {
        "bullet": "BULLET_DISC_CIRCLE_SQUARE",
        "decimal": "NUMBERED_DECIMAL_NESTED",
        "alpha": "NUMBERED_UPPERALPHA_ALPHA_ROMAN",
        "roman": "NUMBERED_UPPERROMAN_UPPERALPHA_DECIMAL",
        "checkbox": "BULLET_CHECKBOX",
    }
    return presets.get(bullet_type, "BULLET_DISC_CIRCLE_SQUARE")


def _styles_to_text_style_request(styles: dict[str, str]) -> tuple[dict[str, Any], str]:
    """Convert style dict to Google Docs textStyle and fields string.

    Uses convert_styles from style_converter to handle all text style properties
    including bold, italic, underline, strikethrough, font, size, bg (background color),
    link, superscript, subscript, etc.
    """
    # Use the declarative style converter for comprehensive style support
    text_style, fields = convert_styles(styles, TEXT_STYLE_PROPS)
    return text_style, ",".join(fields)


def _generate_content_delete_requests_by_index(
    start_index: int,
    end_index: int,
    segment_id: str | None,
    segment_end_index: int = 0,
) -> list[dict[str, Any]]:
    """Generate delete request using pre-calculated indexes.

    Args:
        start_index: Start index in the document
        end_index: End index in the document
        segment_id: The segment ID (header/footer/footnote ID, or None for body)
        segment_end_index: End index of the containing segment (for boundary detection)

    Returns:
        List containing a single deleteContentRange request

    Note:
        Google Docs API does not allow deleting the final newline of a segment
        (body, header, footer, footnote, table cell). If end_index equals
        segment_end_index, we reduce it by 1 to preserve that final newline.
    """
    # Adjust end_index if it would delete the segment's final newline
    if segment_end_index > 0 and end_index >= segment_end_index:
        end_index = segment_end_index - 1

    if start_index >= end_index:
        return []

    range_spec: dict[str, Any] = {
        "startIndex": start_index,
        "endIndex": end_index,
    }
    if segment_id:
        range_spec["segmentId"] = segment_id

    return [
        {
            "deleteContentRange": {
                "range": range_spec,
            }
        }
    ]


# --- Table request generation (Phase 2) ---


def _parse_table_xml(xml_content: str) -> dict[str, Any]:
    """Parse table XML to extract attributes needed for requests.

    Returns dict with:
    - rows: int (derived from structure)
    - cols: int (derived from structure)
    - id: str
    """
    root = ET.fromstring(xml_content)

    # Derive dimensions from structure
    tr_elements = list(root.iter("tr"))
    num_rows = len(tr_elements)
    num_cols = 0
    if tr_elements:
        num_cols = len(list(tr_elements[0].iter("td")))

    return {
        "rows": num_rows,
        "cols": num_cols,
        "id": root.get("id", ""),
    }


def _calculate_cell_content_index(
    table_start_index: int,
    target_row: int,
    target_col: int,
    table_xml: str,
) -> int:
    """Calculate the content start index for a specific table cell.

    Cell content index = table_start + 1 (table marker) +
        sum of row/cell markers and content lengths up to target cell +
        1 (target cell marker)

    Args:
        table_start_index: The table's start index in the document
        target_row: Row index (0-based)
        target_col: Column index (0-based)
        table_xml: The pristine table XML for calculating content lengths

    Returns:
        The index where the cell's content starts (after the cell marker)
    """
    try:
        root = ET.fromstring(table_xml)
    except ET.ParseError:
        return 0

    current_index = table_start_index + 1  # Table start marker

    tr_elements = list(root.findall("tr"))

    for row_idx, tr in enumerate(tr_elements):
        current_index += 1  # Row marker

        td_elements = list(tr.findall("td"))
        for col_idx, td in enumerate(td_elements):
            current_index += 1  # Cell marker

            if row_idx == target_row and col_idx == target_col:
                # Found the target cell - return the content start index
                return current_index

            # Add cell content length
            cell_content_length = _calculate_cell_content_length(td)
            current_index += cell_content_length

        if row_idx == target_row:
            # Target row passed but column not found - shouldn't happen
            break

    return 0  # Cell not found


def _calculate_cell_content_length(td_elem: ET.Element) -> int:
    """Calculate the UTF-16 length of a table cell's content.

    Each paragraph in the cell contributes: text_length + special_elements + 1 (newline)
    Empty cells have a default paragraph with just a newline (length 1).
    """
    total_length = 0
    paragraph_tags = {
        "p",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "li",
        "title",
        "subtitle",
    }

    children = list(td_elem)
    if not children:
        # Empty cell has default paragraph with newline
        return 1

    for child in children:
        if child.tag in paragraph_tags:
            # Calculate paragraph length: text + specials + newline
            text_length = _get_element_text_length(child)
            special_count = sum(
                1 for elem in child.iter() if elem.tag in SPECIAL_ELEMENT_TAGS
            )
            total_length += text_length + special_count + 1  # +1 for newline
        elif child.tag == "table":
            # Nested table - calculate recursively
            total_length += _calculate_nested_table_length(child)

    # If no content was found, default to 1 (empty paragraph)
    return total_length if total_length > 0 else 1


def _get_element_text_length(elem: ET.Element) -> int:
    """Get the UTF-16 length of text content in an element."""
    length = 0
    if elem.text:
        length += utf16_len(elem.text)

    for child in elem:
        if child.tag not in SPECIAL_ELEMENT_TAGS:
            length += _get_element_text_length(child)
        if child.tail:
            length += utf16_len(child.tail)

    return length


def _calculate_nested_table_length(table_elem: ET.Element) -> int:
    """Calculate the UTF-16 length of a nested table."""
    length = 1  # Table start marker

    for tr in table_elem.findall("tr"):
        length += 1  # Row marker
        for td in tr.findall("td"):
            length += 1  # Cell marker
            length += _calculate_cell_content_length(td)

    length += 1  # Table end marker
    return length


def _get_cell_xml_from_table(table_xml: str, row: int, col: int) -> str | None:
    """Extract full td XML for a given row/col from table_xml."""
    try:
        root = ET.fromstring(table_xml)
    except ET.ParseError:
        return None
    trs = root.findall("tr")
    if row >= len(trs):
        return None
    tds = trs[row].findall("td")
    if col >= len(tds):
        return None
    return ET.tostring(tds[col], encoding="unicode")


def _get_pristine_cell_length(table_xml: str, row: int, col: int) -> int:
    """Get the content length of a specific cell in a table XML.

    Args:
        table_xml: The table XML
        row: Row index (0-based)
        col: Column index (0-based)

    Returns:
        The UTF-16 length of the cell's content
    """
    try:
        root = ET.fromstring(table_xml)
    except ET.ParseError:
        return 1  # Default: empty cell

    tr_elements = list(root.findall("tr"))
    if row >= len(tr_elements):
        return 1

    td_elements = list(tr_elements[row].findall("td"))
    if col >= len(td_elements):
        return 1

    return _calculate_cell_content_length(td_elements[col])


def _extract_cell_inner_content(cell_xml: str) -> str:
    """Extract the inner content (paragraphs) from a cell XML.

    The cell_xml is like: <td id="..."><p>content</p></td>
    We want just: <p>content</p>

    Args:
        cell_xml: The full cell XML including the td wrapper

    Returns:
        The inner content XML (paragraphs only)
    """
    try:
        root = ET.fromstring(cell_xml)
    except ET.ParseError:
        return ""

    # Get all child elements and serialize them
    inner_parts = []
    for child in root:
        inner_parts.append(ET.tostring(child, encoding="unicode"))

    return "\n".join(inner_parts)


def _generate_cell_style_request(
    cell_xml: str,
    table_start_index: int,
    row_index: int,
    col_index: int,
    segment_id: str | None,
    cell_styles: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any] | None:
    """Generate updateTableCellStyle request if cell has style attributes.

    Parses the cell XML to extract style attributes (bg, borders, padding, valign)
    and generates an updateTableCellStyle request if any are present.

    If the cell has a `class` attribute, looks up the style properties from
    the cell_styles map (parsed from styles.xml).

    Args:
        cell_xml: The full cell XML (e.g., <td class="cell-abc123">...</td>)
        table_start_index: Start index of the table
        row_index: Row index (0-based)
        col_index: Column index (0-based)
        segment_id: Optional segment ID
        cell_styles: Map of cell style class ID to properties (from styles.xml)

    Returns:
        An updateTableCellStyle request dict, or None if no styles to apply
    """
    try:
        root = ET.fromstring(cell_xml)
    except ET.ParseError:
        return None

    # Extract style attributes from the cell element
    attrs = dict(root.attrib)

    # If cell has a class attribute, look up the style properties
    styles: dict[str, str] = {}
    class_name = attrs.get("class")
    if class_name and cell_styles and class_name in cell_styles:
        # Use the style properties from styles.xml
        styles = cell_styles[class_name].copy()

    # Merge with any inline attributes (inline takes precedence)
    for key, value in attrs.items():
        if key not in ("id", "class", "colspan", "rowspan"):
            styles[key] = value

    # Check if there are any cell style properties
    _, fields = convert_styles(styles, TABLE_CELL_STYLE_PROPS)
    if not fields:
        return None

    return build_table_cell_style_request(
        styles,
        table_start_index,
        row_index,
        col_index,
        segment_id,
    )


def _generate_table_add_requests(
    after_xml: str,
    segment_id: str | None,
    insert_index: int = 0,
    text_styles: dict[str, dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """Generate requests to add a new table with cell content.

    Strategy:
    1. Insert the empty table structure with insertTable
    2. Calculate each cell's content start index
    3. For each cell with content, use _generate_content_insert_requests()
       (same as body/header/footer/footnote content handling)

    Args:
        after_xml: The table XML content
        segment_id: Segment ID (None for body, header/footer ID otherwise)
        insert_index: The index at which to insert the table (0 = end of segment)
        text_styles: Style definitions for text styling
    """
    requests: list[dict[str, Any]] = []
    table_info = _parse_table_xml(after_xml)
    rows = table_info["rows"]
    cols = table_info["cols"]

    # 1. Insert the empty table structure
    if insert_index > 0:
        location: dict[str, Any] = {"index": insert_index}
        if segment_id:
            location["segmentId"] = segment_id
        requests.append(
            {
                "insertTable": {
                    "rows": rows,
                    "columns": cols,
                    "location": location,
                },
            }
        )
    else:
        # Use endOfSegmentLocation when no specific index
        end_location: dict[str, Any] = {}
        if segment_id:
            end_location["segmentId"] = segment_id
        requests.append(
            {
                "insertTable": {
                    "rows": rows,
                    "columns": cols,
                    "endOfSegmentLocation": end_location
                    if end_location
                    else {"segmentId": ""},
                }
            }
        )
        # Without a specific insert index, we can't calculate cell positions
        # The table structure is created but content requires a second pass
        return requests

    # 2. Parse table to extract cell content XML
    try:
        root = ET.fromstring(after_xml)
    except ET.ParseError:
        return requests

    # 3. Calculate cell content indexes and insert content
    # Table structure: table_start + 1 (table marker) + row markers + cell markers
    # Each cell starts at: base + row_offset + cell_offset
    # Process cells in reverse order (high to low index) for index stability

    cell_contents: list[tuple[int, int, str]] = []  # (row, col, inner_xml)
    tr_elements = list(root.findall("tr"))
    for row_idx, tr in enumerate(tr_elements):
        td_elements = list(tr.findall("td"))
        for col_idx, td in enumerate(td_elements):
            # Extract inner XML of the cell (the ContentBlock)
            inner_parts = []
            for child in td:
                inner_parts.append(ET.tostring(child, encoding="unicode"))
            if inner_parts:
                cell_contents.append((row_idx, col_idx, "".join(inner_parts)))

    # Calculate base cell positions for the freshly inserted empty table
    # Each cell in a new table has 1 character (the default empty paragraph newline)
    cell_starts = _calculate_new_table_cell_starts(insert_index, rows, cols)

    # Process cells from highest index to lowest for index stability
    for row_idx, col_idx, inner_xml in sorted(
        cell_contents, key=lambda x: cell_starts.get((x[0], x[1]), 0), reverse=True
    ):
        cell_start = cell_starts.get((row_idx, col_idx))
        if cell_start is None:
            continue

        # The cell already has a default empty paragraph (1 newline)
        # We insert content at the start of the cell, and the content will
        # replace/precede the default newline
        cell_requests = _generate_content_insert_requests(
            inner_xml,
            segment_id,
            insert_index=cell_start,
            strip_trailing_newline=True,  # Don't add trailing newline, cell already has one
            text_styles=text_styles,
        )
        requests.extend(cell_requests)

    return requests


def _calculate_new_table_cell_starts(
    insert_location_index: int, rows: int, cols: int
) -> dict[tuple[int, int], int]:
    """Calculate cell content start indexes for a newly inserted empty table.

    IMPORTANT: When inserting a table via InsertTableRequest, a newline is
    inserted BEFORE the table. So if location.index = N, the table actually
    starts at N + 1.

    In a fresh table, each cell contains just one empty paragraph (1 newline char).

    Table structure indexes (after the auto-inserted newline):
    - table_start (at insert_location + 1): table marker (1 char)
    - For each row: row marker (1 char)
    - For each cell: cell marker (1 char) + content (1 char for empty para)

    Returns:
        Dict mapping (row, col) to the content start index for that cell
    """
    cell_starts: dict[tuple[int, int], int] = {}
    # Table starts at insert_location + 1 (due to auto-inserted newline)
    # Then skip the table start marker
    idx = insert_location_index + 1 + 1  # +1 for newline, +1 for table marker

    for row in range(rows):
        idx += 1  # Row marker
        for col in range(cols):
            idx += 1  # Cell marker
            cell_starts[(row, col)] = idx
            idx += 1  # Default empty paragraph (1 newline)

    return cell_starts


def _generate_table_delete_requests(
    before_xml: str,
    segment_id: str | None,
    table_start_index: int,
) -> list[dict[str, Any]]:
    """Generate requests to delete a table.

    Uses deleteContentRange with the table's index range.
    The table's startIndex and size determine the range.

    Args:
        before_xml: The table's XML content (for parsing structure)
        segment_id: The segment ID (body, header, footer, etc.)
        table_start_index: The table's start index from pristine_table_indexes
    """
    requests: list[dict[str, Any]] = []
    table_info = _parse_table_xml(before_xml)

    if table_start_index == 0:
        # No startIndex provided - can't generate delete request
        return []

    start_index = table_start_index

    # Calculate table size accurately by parsing the table XML content
    try:
        root = ET.fromstring(before_xml)
        table_size = _calculate_nested_table_length(root)
    except ET.ParseError:
        # Fallback to rough estimate if XML parsing fails
        rows = table_info["rows"]
        cols = table_info["cols"]
        table_size = 1 + rows * (1 + cols * 2) + 1

    range_obj: dict[str, Any] = {
        "startIndex": start_index,
        "endIndex": start_index + table_size,
    }
    if segment_id:
        range_obj["segmentId"] = segment_id

    requests.append({"deleteContentRange": {"range": range_obj}})

    return requests


def _get_table_start_index(
    container_path: list[str],
    table_indexes: dict[str, int],
    table_position: int | None = None,
) -> int:
    """Get the table's start index from the calculated index map.

    Prefers stable content-hash IDs from the container_path, falls back to
    positional lookup when needed.
    """
    section_type = "body"
    table_id: str | None = None

    for part in container_path:
        if ":" not in part:
            continue
        prefix, value = part.split(":", 1)
        if prefix in ("body", "header", "footer", "footnote"):
            section_type = prefix
        if prefix == "table":
            table_id = value

    if table_id:
        key = f"{section_type}:id:{table_id}"
        if key in table_indexes:
            return table_indexes[key]

    if table_position is not None:
        pos_key = f"{section_type}:pos:{table_position}"
        if pos_key in table_indexes:
            return table_indexes[pos_key]

    # Fallback to first table in section
    return table_indexes.get(f"{section_type}:pos:0", 0)


def _get_row_index_from_change(change: BlockChange) -> int:
    """Extract row index from a TABLE_ROW change.

    The row index is extracted from the container_path which includes "row_idx:N".
    """
    # Get from container path (e.g., ["body:body", "table:abc", "row_idx:2"])
    for part in change.container_path:
        if part.startswith("row_idx:"):
            try:
                return int(part.split(":")[1])
            except (ValueError, IndexError):
                pass

    # Fallback: try to extract from block_id if it's a position-based ID like "r0"
    if change.block_id.startswith("r") and change.block_id[1:].isdigit():
        return int(change.block_id[1:])

    # Default to 0
    return 0


def _get_col_index_from_change(change: BlockChange) -> int:
    """Extract column index from a TABLE_CELL change.

    The column index is extracted from the container_path which includes "col_idx:N".
    """
    # Get from container path (e.g., ["body:body", "table:abc", "row_idx:1", "col_idx:2"])
    for part in change.container_path:
        if part.startswith("col_idx:"):
            try:
                return int(part.split(":")[1])
            except (ValueError, IndexError):
                pass

    # Fallback: try to extract from block_id if it's position-based like "0,1"
    if "," in change.block_id:
        try:
            _, col = change.block_id.split(",", 1)
            return int(col)
        except ValueError:
            pass

    # Fallback: try XML attributes
    if change.before_xml or change.after_xml:
        xml = change.before_xml or change.after_xml
        assert xml is not None  # Guaranteed by if condition
        try:
            root = ET.fromstring(xml)
            if root.get("col"):
                return int(root.get("col", "0"))
        except ET.ParseError:
            pass

    return 0


# Table request generation functions are now delegated to request_generators/table.py
# The following are imported at the top of this file:
# - generate_insert_table_row_request
# - generate_delete_table_row_request
# - generate_insert_table_column_request
# - generate_delete_table_column_request
