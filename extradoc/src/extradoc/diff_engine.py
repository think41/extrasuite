"""Diff engine for ExtraDoc XML.

Compares pristine and edited documents to generate Google Docs batchUpdate requests.
Uses block-level diff detection for structural changes.
"""

from __future__ import annotations

import json
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
    Paragraph,
    Section,
    SpecialElement,
    Table,
    TableCell,
    desugar_document,
)
from .indexer import calculate_table_indexes, utf16_len

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


def diff_documents(
    pristine_xml: str,
    current_xml: str,
    pristine_styles: str | None = None,
    current_styles: str | None = None,
) -> list[dict[str, Any]]:
    """Compare two XML documents and generate batchUpdate requests.

    Uses block-level diff detection to identify changes, then generates
    appropriate Google Docs API requests for each change.

    Strategy:
    1. Parse both documents into block trees
    2. Detect block-level changes (add, delete, modify)
    3. For each change, generate appropriate requests
    4. Process changes bottom-up (descending index) to maintain index stability
    """
    # Get block-level changes
    block_changes = diff_documents_block_level(
        pristine_xml, current_xml, pristine_styles, current_styles
    )

    # If no changes, return empty list
    if not block_changes:
        return []

    # Parse documents for index calculation
    pristine_doc = desugar_document(pristine_xml, pristine_styles)
    current_doc = desugar_document(current_xml, current_styles)

    # Calculate table indexes from pristine document
    table_indexes = calculate_table_indexes(pristine_doc.sections)

    # Generate requests from block changes
    requests: list[dict[str, Any]] = []

    for change in block_changes:
        change_requests = _generate_requests_for_change(
            change, pristine_doc, current_doc, table_indexes
        )
        requests.extend(change_requests)

    return requests


def _generate_requests_for_change(
    change: BlockChange,
    pristine_doc: Any,
    current_doc: Any,
    table_indexes: dict[str, int],
) -> list[dict[str, Any]]:
    """Generate batchUpdate requests for a single block change.

    Args:
        change: The BlockChange describing what changed
        pristine_doc: Desugared pristine document
        current_doc: Desugared current document
        table_indexes: Map of table positions to start indexes

    Returns:
        List of batchUpdate request dicts
    """
    # Extract segment_id from container path
    segment_id = _extract_segment_id(change.container_path)

    # Find the matching section for index calculation
    section_type = _get_section_type_from_path(change.container_path)
    pristine_section = _find_section(pristine_doc, section_type, segment_id)
    current_section = _find_section(current_doc, section_type, segment_id)

    requests: list[dict[str, Any]] = []

    if change.block_type == BlockType.CONTENT_BLOCK:
        requests.extend(
            _handle_content_block_change(
                change, pristine_section, current_section, segment_id
            )
        )
    elif change.block_type == BlockType.TABLE:
        requests.extend(
            _handle_table_change(
                change, pristine_section, current_section, segment_id, table_indexes
            )
        )
    elif change.block_type in (BlockType.HEADER, BlockType.FOOTER):
        requests.extend(_handle_header_footer_change(change))
    elif change.block_type == BlockType.FOOTNOTE:
        requests.extend(_handle_footnote_change(change))
    elif change.block_type == BlockType.TAB:
        requests.extend(_handle_tab_change(change))

    # Recursively handle child changes
    for child_change in change.child_changes:
        child_requests = _generate_requests_for_change(
            child_change, pristine_doc, current_doc, table_indexes
        )
        requests.extend(child_requests)

    return requests


def _extract_segment_id(container_path: list[str]) -> str | None:
    """Extract segment ID from container path.

    Returns None for body, or the segment ID for headers/footers/footnotes.
    """
    for part in container_path:
        if ":" in part:
            type_part, id_part = part.split(":", 1)
            if type_part in ("header", "footer", "footnote") and id_part:
                return id_part
    return None


def _get_section_type_from_path(container_path: list[str]) -> str:
    """Get section type from container path."""
    for part in container_path:
        if ":" in part:
            type_part = part.split(":")[0]
            if type_part in ("body", "header", "footer", "footnote"):
                return type_part
    return "body"


def _find_section(
    doc: Any, section_type: str, segment_id: str | None
) -> Section | None:
    """Find a section in the document by type and ID."""
    for section in doc.sections:
        sec: Section = section
        if sec.section_type == section_type and (
            segment_id is None or sec.section_id == segment_id
        ):
            return sec
    return None


def _handle_content_block_change(
    change: BlockChange,
    pristine_section: Section | None,
    current_section: Section | None,
    segment_id: str | None,
) -> list[dict[str, Any]]:
    """Handle ContentBlock add/delete/modify changes.

    For MODIFIED content blocks, we use a simple delete + insert strategy.
    """
    requests: list[dict[str, Any]] = []

    if change.change_type == ChangeType.ADDED:
        # Insert new content at the appropriate position
        if current_section and change.after_xml:
            # Parse the after_xml to get content
            # For now, use a simple rebuild approach
            requests.extend(
                _generate_content_insert_requests(change.after_xml, segment_id)
            )

    elif change.change_type == ChangeType.DELETED:
        # Delete the content range
        if pristine_section and change.before_xml:
            requests.extend(
                _generate_content_delete_requests(
                    change.before_xml, pristine_section, segment_id
                )
            )

    elif change.change_type == ChangeType.MODIFIED:
        # For modified blocks, delete old content and insert new
        # This is the simple strategy; can be optimized later
        if pristine_section and change.before_xml:
            requests.extend(
                _generate_content_delete_requests(
                    change.before_xml, pristine_section, segment_id
                )
            )
        if current_section and change.after_xml:
            requests.extend(
                _generate_content_insert_requests(change.after_xml, segment_id)
            )

    return requests


def _handle_table_change(
    change: BlockChange,
    pristine_section: Section | None,  # noqa: ARG001 - Reserved for Phase 3
    current_section: Section | None,  # noqa: ARG001 - Reserved for Phase 3
    segment_id: str | None,
    table_indexes: dict[str, int],
) -> list[dict[str, Any]]:
    """Handle Table add/delete/modify changes.

    For MODIFIED tables, we process child_changes which contain row/cell changes.
    Row/column operations use the table's startIndex calculated from document structure.
    """
    requests: list[dict[str, Any]] = []

    if change.change_type == ChangeType.ADDED:
        # Table insertion: need to parse dimensions and insertion point
        if change.after_xml:
            requests.extend(_generate_table_add_requests(change.after_xml, segment_id))

    elif change.change_type == ChangeType.DELETED:
        # Table deletion: need to calculate the range from before_xml
        if change.before_xml:
            requests.extend(
                _generate_table_delete_requests(change.before_xml, segment_id)
            )

    elif change.change_type == ChangeType.MODIFIED:
        # Table modified - process row/cell changes from child_changes
        # The child_changes contain TABLE_ROW and TABLE_CELL changes
        requests.extend(
            _generate_table_modify_requests(change, segment_id, table_indexes)
        )

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


def _handle_footnote_change(change: BlockChange) -> list[dict[str, Any]]:
    """Handle footnote add/delete changes."""
    requests: list[dict[str, Any]] = []

    if change.change_type == ChangeType.ADDED:
        # Footnotes are created via createFootnote request from body
        pass

    elif change.change_type == ChangeType.DELETED:
        # Footnotes are deleted by removing the reference in the body
        pass

    return requests


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
            import xml.etree.ElementTree as ET

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


def _generate_content_insert_requests(
    xml_content: str,  # noqa: ARG001 - Will be used in Phase 3
    segment_id: str | None,  # noqa: ARG001 - Will be used in Phase 3
) -> list[dict[str, Any]]:
    """Generate insert requests for content XML.

    This is a placeholder - full implementation needs to parse the XML
    and generate appropriate insertText/updateTextStyle requests.
    """
    # For now, return empty - will be implemented in Phase 3
    return []


def _generate_content_delete_requests(
    xml_content: str,  # noqa: ARG001 - Will be used in Phase 3
    section: Section,  # noqa: ARG001 - Will be used in Phase 3
    segment_id: str | None,  # noqa: ARG001 - Will be used in Phase 3
) -> list[dict[str, Any]]:
    """Generate delete requests for content XML.

    This is a placeholder - full implementation needs to calculate
    the index range of the content to delete.
    """
    # For now, return empty - will be implemented in Phase 3
    return []


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


def _generate_table_add_requests(
    after_xml: str,
    segment_id: str | None,
) -> list[dict[str, Any]]:
    """Generate requests to add a new table.

    For new tables, we need to:
    1. Insert the table structure with insertTable
    2. Populate cell content (handled by child_changes)
    """
    requests: list[dict[str, Any]] = []
    table_info = _parse_table_xml(after_xml)

    # Note: For ADDED tables, we don't have a startIndex from the pristine doc
    # The insertion point needs to be calculated based on surrounding content
    # For now, we return a placeholder request
    # Full implementation needs integration with index calculation

    location: dict[str, Any] = {}
    if segment_id:
        location["segmentId"] = segment_id

    # InsertTable requires either location.index or endOfSegmentLocation
    # For now, we use endOfSegmentLocation as a fallback
    requests.append(
        {
            "insertTable": {
                "rows": table_info["rows"],
                "columns": table_info["cols"],
                "endOfSegmentLocation": location if location else {"segmentId": ""},
            }
        }
    )

    return requests


def _generate_table_delete_requests(
    before_xml: str,
    segment_id: str | None,
) -> list[dict[str, Any]]:
    """Generate requests to delete a table.

    Uses deleteContentRange with the table's index range.
    The table's startIndex and size determine the range.
    """
    requests: list[dict[str, Any]] = []
    table_info = _parse_table_xml(before_xml)

    start_index = table_info["startIndex"]
    if start_index == 0:
        # No startIndex stored - can't generate delete request
        return []

    # Calculate table end index by parsing the table content
    # For a simple approximation, use structural calculation:
    # table_start + 1 (table marker) + rows * (1 (row) + cols * (1 (cell) + 1 (newline))) + 1 (table end)
    # This is approximate - proper calculation needs full content parsing
    rows = table_info["rows"]
    cols = table_info["cols"]
    # Minimum table size: table markers + row/cell markers + minimum cell content
    table_size = 1 + rows * (1 + cols * 2) + 1

    range_obj: dict[str, Any] = {
        "startIndex": start_index,
        "endIndex": start_index + table_size,
    }
    if segment_id:
        range_obj["segmentId"] = segment_id

    requests.append({"deleteContentRange": {"range": range_obj}})

    return requests


def _generate_table_modify_requests(
    change: BlockChange,
    segment_id: str | None,
    table_indexes: dict[str, int],
) -> list[dict[str, Any]]:
    """Generate requests for table modifications (row/column/cell changes).

    Processes child_changes which contain TABLE_ROW changes.
    Row changes may contain TABLE_CELL changes.

    Note: Column operations affect entire columns, so we deduplicate them
    (only generate one insertTableColumn per unique column index).
    """
    requests: list[dict[str, Any]] = []

    # Get table startIndex from the calculated indexes
    # The table position is in the container_path
    table_start_index = _get_table_start_index(change.container_path, table_indexes)

    if table_start_index == 0:
        # No startIndex found - can't generate structural requests
        return []

    # Track column operations to deduplicate
    # When a column is added/deleted, every row has the cell change,
    # but we only need ONE insertTableColumn/deleteTableColumn request
    columns_added: set[int] = set()
    columns_deleted: set[int] = set()

    # Process child changes (TABLE_ROW changes)
    # Sort by row index descending for bottom-up processing
    row_changes = [
        c for c in change.child_changes if c.block_type == BlockType.TABLE_ROW
    ]
    row_changes.sort(key=lambda c: _get_row_index_from_change(c), reverse=True)

    for row_change in row_changes:
        row_index = _get_row_index_from_change(row_change)

        if row_change.change_type == ChangeType.ADDED:
            # Insert new row - insert below row_index - 1 (the previous row)
            # If row_index is 0, insert above row 0 (insertBelow=False)
            if row_index == 0:
                requests.append(
                    _generate_insert_table_row_request(
                        table_start_index, 0, segment_id, insert_below=False
                    )
                )
            else:
                requests.append(
                    _generate_insert_table_row_request(
                        table_start_index, row_index - 1, segment_id, insert_below=True
                    )
                )

        elif row_change.change_type == ChangeType.DELETED:
            # Delete row
            requests.append(
                _generate_delete_table_row_request(
                    table_start_index, row_index, segment_id
                )
            )

        elif row_change.change_type == ChangeType.MODIFIED:
            # Row modified - check for cell changes
            cell_changes = [
                c
                for c in row_change.child_changes
                if c.block_type == BlockType.TABLE_CELL
            ]

            for cell_change in cell_changes:
                col_index = _get_col_index_from_change(cell_change)

                if cell_change.change_type == ChangeType.ADDED:
                    # Cell added = column added (deduplicate)
                    if col_index not in columns_added:
                        columns_added.add(col_index)
                        requests.append(
                            _generate_insert_table_column_request(
                                table_start_index, row_index, col_index, segment_id
                            )
                        )

                elif cell_change.change_type == ChangeType.DELETED:
                    # Cell deleted = column deleted (deduplicate)
                    if col_index not in columns_deleted:
                        columns_deleted.add(col_index)
                        requests.append(
                            _generate_delete_table_column_request(
                                table_start_index, row_index, col_index, segment_id
                            )
                        )

                elif cell_change.change_type == ChangeType.MODIFIED:
                    # Cell content modified - this is Phase 3 (ContentBlock)
                    # The cell's child_changes contain the content changes
                    pass

    return requests


def _get_table_start_index(
    container_path: list[str],
    table_indexes: dict[str, int],
) -> int:
    """Get the table's start index from the calculated index map.

    The container_path contains the section type and table position.
    Example path: ["body:body", "table:abc123", "row_idx:2"]

    Args:
        container_path: The path to the changed element
        table_indexes: Map of "section:position" -> startIndex

    Returns:
        The table's start index, or 0 if not found
    """
    # Extract section type from path
    section_type = "body"
    for part in container_path:
        if ":" in part:
            prefix = part.split(":")[0]
            if prefix in ("body", "header", "footer", "footnote"):
                section_type = prefix
                break

    # Find table position - count tables in the section
    # For now, we assume single table per section (position 0)
    # TODO: Track table position in block_diff for multi-table sections
    table_key = f"{section_type}:0"

    return table_indexes.get(table_key, 0)


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


def _generate_insert_table_row_request(
    table_start_index: int,
    row_index: int,
    segment_id: str | None,
    insert_below: bool = True,
) -> dict[str, Any]:
    """Generate insertTableRow request."""
    cell_location: dict[str, Any] = {
        "tableStartLocation": {"index": table_start_index},
        "rowIndex": row_index,
        "columnIndex": 0,  # Any valid column works
    }
    if segment_id:
        cell_location["tableStartLocation"]["segmentId"] = segment_id

    return {
        "insertTableRow": {
            "tableCellLocation": cell_location,
            "insertBelow": insert_below,
        }
    }


def _generate_delete_table_row_request(
    table_start_index: int,
    row_index: int,
    segment_id: str | None,
) -> dict[str, Any]:
    """Generate deleteTableRow request."""
    cell_location: dict[str, Any] = {
        "tableStartLocation": {"index": table_start_index},
        "rowIndex": row_index,
        "columnIndex": 0,
    }
    if segment_id:
        cell_location["tableStartLocation"]["segmentId"] = segment_id

    return {
        "deleteTableRow": {
            "tableCellLocation": cell_location,
        }
    }


def _generate_insert_table_column_request(
    table_start_index: int,
    row_index: int,
    col_index: int,
    segment_id: str | None,
) -> dict[str, Any]:
    """Generate insertTableColumn request.

    The col_index is the NEW column's desired position. We need to convert this
    to a valid existing column reference:
    - For col_index > 0: insert to the right of column col_index - 1
    - For col_index == 0: insert to the left of column 0
    """
    if col_index == 0:
        # Insert as first column - insert to left of column 0
        cell_location: dict[str, Any] = {
            "tableStartLocation": {"index": table_start_index},
            "rowIndex": row_index,
            "columnIndex": 0,
        }
        if segment_id:
            cell_location["tableStartLocation"]["segmentId"] = segment_id

        return {
            "insertTableColumn": {
                "tableCellLocation": cell_location,
                "insertRight": False,
            }
        }
    else:
        # Insert to the right of the previous column
        cell_location = {
            "tableStartLocation": {"index": table_start_index},
            "rowIndex": row_index,
            "columnIndex": col_index - 1,
        }
        if segment_id:
            cell_location["tableStartLocation"]["segmentId"] = segment_id

        return {
            "insertTableColumn": {
                "tableCellLocation": cell_location,
                "insertRight": True,
            }
        }


def _generate_delete_table_column_request(
    table_start_index: int,
    row_index: int,
    col_index: int,
    segment_id: str | None,
) -> dict[str, Any]:
    """Generate deleteTableColumn request."""
    cell_location: dict[str, Any] = {
        "tableStartLocation": {"index": table_start_index},
        "rowIndex": row_index,
        "columnIndex": col_index,
    }
    if segment_id:
        cell_location["tableStartLocation"]["segmentId"] = segment_id

    return {
        "deleteTableColumn": {
            "tableCellLocation": cell_location,
        }
    }


# --- Request generation helpers (kept from original) ---


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

    # Fallback - should not happen
    return {}


def _generate_paragraph_insert(
    para: Paragraph,
    insert_idx: int,
    segment_id: str | None,
    *,
    reuse_existing_newline: bool = False,
) -> tuple[list[DiffOperation], int]:
    """Insert a paragraph with styles and bullets. Returns (ops, length)."""
    ops: list[DiffOperation] = []
    cursor = insert_idx
    # When reusing the default empty paragraph inside a table cell, Google Docs
    # already provides a trailing newline. In that case, avoid adding another and
    # advance past the existing newline instead.
    add_trailing_newline = not reuse_existing_newline

    # Insert runs sequentially to keep order with specials
    for idx, run in enumerate(para.runs):
        if "_special" in run.styles:
            special_ops, special_len = _generate_special_insert(
                SpecialElement(run.styles["_special"], dict(run.styles)),
                cursor,
                segment_id,
            )
            ops.extend(special_ops)
            cursor += special_len
            # If a column break is the last thing in the paragraph, skip the trailing
            # newline. The section break itself ends the paragraph.
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
                    )
                )

            cursor += run_len

    # Append newline to terminate paragraph (unless suppressed for column break)
    if add_trailing_newline:
        ops.append(
            DiffOperation(
                op_type="insert",
                index=cursor,
                content="\n",
                segment_id=segment_id,
            )
        )
        cursor += 1

    # Paragraph style (headings)
    if para.named_style != "NORMAL_TEXT":
        ops.append(
            DiffOperation(
                op_type="update_paragraph_style",
                index=insert_idx,
                end_index=cursor,
                paragraph_style={"namedStyleType": para.named_style},
                fields="namedStyleType",
                segment_id=segment_id,
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
            )
        )
        # Indent nested levels
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
                )
            )

    # If we skipped adding our own newline because we are reusing the existing
    # default paragraph newline, advance past it so subsequent inserts land in
    # the next paragraph.
    if reuse_existing_newline and not add_trailing_newline:
        cursor += 1

    return ops, cursor - insert_idx


def _generate_special_insert(
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
            )
        )
        added = 1
    elif etype == "columnbreak":
        # Insert a continuous section break inline. Docs also inserts a newline
        # before the break, so account for two characters of length.
        ops.append(
            DiffOperation(
                op_type="insert_section_break",
                index=insert_idx,
                segment_id=segment_id,
                fields="CONTINUOUS",
            )
        )
        added = 2
    elif etype == "hr":
        # Insert an empty paragraph and apply a bottom border to render as a rule.
        ops.append(
            DiffOperation(
                op_type="insert",
                index=insert_idx,
                content="\n",
                segment_id=segment_id,
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
            )
        )
        added = utf16_len(content)
    else:
        added = 0

    return ops, added


def _generate_table_insert(
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
        cell_ops, _ = _emit_cell_content(cell, start + 1, segment_id)
        ops.extend(cell_ops)

    # Final length accounts for actual cell content
    length = _table_length(table)
    return ops, length


def _emit_cell_content(
    cell: TableCell, insert_idx: int, segment_id: str | None
) -> tuple[list[DiffOperation], int]:
    """Emit operations for the content of a single table cell."""
    ops: list[DiffOperation] = []
    cursor = insert_idx
    first_para_in_cell = True

    for elem in cell.content:
        if isinstance(elem, Paragraph):
            para_ops, para_len = _generate_paragraph_insert(
                elem,
                cursor,
                segment_id,
                reuse_existing_newline=first_para_in_cell,
            )
            ops.extend(para_ops)
            cursor += para_len
            first_para_in_cell = False
        elif isinstance(elem, SpecialElement):
            spec_ops, spec_len = _generate_special_insert(elem, cursor, segment_id)
            ops.extend(spec_ops)
            cursor += spec_len
        elif isinstance(elem, Table):
            table_ops, table_len = _generate_table_insert(elem, cursor, segment_id)
            ops.extend(table_ops)
            cursor += table_len

    return ops, cursor - insert_idx


def _table_cell_starts(
    table: Table, base_index: int, default_cell_len: int = 1
) -> tuple[dict[tuple[int, int], int], int]:
    """Return cell start indexes (first content char) and base length.

    Indexes are computed for the freshly inserted table with default
    empty-paragraph content (length = default_cell_len per cell).
    """
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


def _element_length(elem: Paragraph | Table | SpecialElement) -> int:
    """Compute utf16 length of an element including structural markers."""
    if isinstance(elem, Paragraph):
        return elem.utf16_length()
    if isinstance(elem, SpecialElement):
        return elem.utf16_length()
    if isinstance(elem, Table):
        return _table_length(elem)
    return 0
