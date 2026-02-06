"""Diff engine for ExtraDoc XML.

Compares pristine and edited documents to generate Google Docs batchUpdate requests.
Uses block-level diff detection for structural changes.

This module orchestrates the diff/request generation process, delegating to
specialized modules for style conversion and request generation:
- style_converter: Declarative style mappings and conversion
- request_generators/: Structural, table, and content request generation
"""

from __future__ import annotations

import json
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
    Paragraph,
    Section,
    SpecialElement,
    Table,
    TableCell,
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
    TABLE_CELL_STYLE_PROPS,
    TEXT_STYLE_PROPS,
    build_table_cell_style_request,
    convert_styles,
)

# --- Helpers for style mapping ---


def _styles_to_text_style(styles: dict[str, str]) -> tuple[dict[str, Any], str] | None:
    """Convert run styles to Google Docs textStyle + fields.

    Uses the declarative style converter for basic styles, with special
    handling for link URLs which need nested structure.
    """
    text_style, fields = convert_styles(styles, TEXT_STYLE_PROPS)

    if not fields:
        return None

    return text_style, ",".join(fields)


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

    # Separate body ContentBlock changes from structural changes
    # Body ContentBlock changes may need merged approach for index stability
    # Structural changes (table, footer, tab, header) are processed separately
    body_content_changes = [
        c
        for c in block_changes
        if "body" in str(c.container_path) and c.block_type == BlockType.CONTENT_BLOCK
    ]
    structural_changes = [
        c
        for c in block_changes
        if c.block_type
        in (BlockType.TABLE, BlockType.FOOTER, BlockType.TAB, BlockType.HEADER)
        or "body" not in str(c.container_path)
    ]

    has_body_deletes = any(
        c.change_type in (ChangeType.DELETED, ChangeType.MODIFIED)
        for c in body_content_changes
    )
    has_body_inserts = any(
        c.change_type in (ChangeType.ADDED, ChangeType.MODIFIED)
        for c in body_content_changes
    )

    all_requests: list[dict[str, Any]] = []

    # If we have both deletes and inserts/modifies in body ContentBlocks, use merged approach
    # This ensures index stability by doing a single delete + single insert
    if has_body_deletes and has_body_inserts and len(body_content_changes) > 1:
        # Merge all body content changes into a single insert
        merged_requests = _generate_merged_body_insert(
            block_changes, pristine_doc, current_doc, current_xml
        )
        if merged_requests:
            all_requests.extend(merged_requests)
        # Continue to process structural changes below

    # Process structural changes (footer, tab, header, table) normally
    for change in structural_changes:
        change_requests = _generate_requests_for_change(
            change, pristine_doc, current_doc, table_indexes
        )
        all_requests.extend(change_requests)

    # If merged approach was NOT used (no body content requests yet), process all changes normally
    if not all_requests:
        # Generate requests from all block changes
        # Sort by pristine_start_index descending (bottom-up) to maintain index stability
        sorted_changes = sorted(
            block_changes,
            key=lambda c: c.pristine_start_index,
            reverse=True,
        )

        for change in sorted_changes:
            change_requests = _generate_requests_for_change(
                change, pristine_doc, current_doc, table_indexes
            )
            all_requests.extend(change_requests)

    # Reorder requests: DELETEs first, then INSERTs, then UPDATEs
    # This ensures deletes don't affect inserted content
    # Exception: requests marked with _skipReorder should stay in their original position
    delete_requests: list[dict[str, Any]] = []
    insert_requests: list[dict[str, Any]] = []
    update_requests: list[dict[str, Any]] = []
    ordered_requests: list[dict[str, Any]] = []  # Requests that shouldn't be reordered

    for req in all_requests:
        # Check for skip reorder marker
        if req.pop("_skipReorder", False):
            ordered_requests.append(req)
            continue

        if (
            "deleteContentRange" in req
            or "deleteTableRow" in req
            or "deleteTableColumn" in req
        ):
            delete_requests.append(req)
        elif (
            "insertText" in req
            or "insertPageBreak" in req
            or "insertSectionBreak" in req
            or "insertTable" in req
            or "insertTableRow" in req
            or "insertTableColumn" in req
        ):
            insert_requests.append(req)
        else:
            update_requests.append(req)

    # Sort deletes by start index descending
    def get_delete_index(req: dict[str, Any]) -> int:
        if "deleteContentRange" in req:
            return int(req["deleteContentRange"]["range"].get("startIndex", 0))
        if "deleteTableRow" in req:
            return int(
                req["deleteTableRow"]
                .get("tableCellLocation", {})
                .get("tableStartLocation", {})
                .get("index", 0)
            )
        return 0

    delete_requests.sort(key=get_delete_index, reverse=True)

    # Sort inserts by index descending
    def get_insert_index(req: dict[str, Any]) -> int:
        if "insertText" in req:
            return int(req["insertText"]["location"].get("index", 0))
        if "insertPageBreak" in req:
            return int(req["insertPageBreak"]["location"].get("index", 0))
        if "insertSectionBreak" in req:
            return int(req["insertSectionBreak"]["location"].get("index", 0))
        if "insertTable" in req:
            table_req = req["insertTable"]
            if "location" in table_req:
                return int(table_req["location"].get("index", 0))
            # endOfSegmentLocation means insert at end - use 0 for sorting
            return 0
        return 0

    insert_requests.sort(key=get_insert_index, reverse=True)

    # Combine: deletes first, then ordered requests (e.g., table cell ops),
    # then regular inserts, then updates
    return delete_requests + ordered_requests + insert_requests + update_requests


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
    # Note: Some child changes are already handled by their parent handlers
    for child_change in change.child_changes:
        if (
            change.block_type == BlockType.CONTENT_BLOCK
            and child_change.block_type == BlockType.FOOTNOTE
        ):
            # Already handled in _handle_content_block_change
            continue
        if change.block_type == BlockType.TABLE:
            # Table child changes (rows, cells, cell content) are all handled
            # in _generate_table_modify_requests
            continue
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


def _generate_merged_body_insert(
    block_changes: list[BlockChange],
    pristine_doc: Any,
    current_doc: Any,  # noqa: ARG001 - Kept for API consistency
    current_xml: str,
) -> list[dict[str, Any]]:
    """Generate a single merged insert for body content when positions overlap.

    This is used when replacing document content, where the normal diff would
    produce multiple changes at different positions. Since deletes change the
    document size, insert indexes calculated from pristine become invalid.

    Strategy:
    1. Delete all existing body content (preserving final newline)
    2. Insert all new body content as a single operation
    3. Generate styling for the merged content

    Returns empty list if merge cannot be performed.
    """

    # Find body section in pristine
    pristine_body = None
    for sec in pristine_doc.sections:
        if sec.section_type == "body":
            pristine_body = sec
            break

    if pristine_body is None:
        return []

    # Parse current XML to extract body content
    try:
        root = ET.fromstring(current_xml)
        body_elem = root.find("body")
        if body_elem is None:
            return []
    except ET.ParseError:
        return []

    # Serialize all body children as the merged content
    body_content_parts: list[str] = []
    for child in body_elem:
        body_content_parts.append(ET.tostring(child, encoding="unicode"))

    if not body_content_parts:
        return []

    merged_xml = "\n".join(body_content_parts)

    requests: list[dict[str, Any]] = []

    # 1. Calculate pristine body end index from the actual pristine body content
    # Body starts at index 1
    pristine_end = 1
    for elem in pristine_body.content:
        if isinstance(elem, Paragraph):
            pristine_end += elem.utf16_length()
        elif isinstance(elem, Table):
            pristine_end += _table_length(elem)
        elif isinstance(elem, SpecialElement):
            pristine_end += elem.utf16_length()

    # Also check block changes for segment_end_index (more reliable for segment boundary)
    for change in block_changes:
        if "body" in str(change.container_path) and change.segment_end_index > 0:
            pristine_end = max(pristine_end, change.segment_end_index)
            break

    # Delete from 1 to pristine_end - 1 (preserve final newline)
    if pristine_end > 2:
        requests.append(
            {
                "deleteContentRange": {
                    "range": {
                        "startIndex": 1,
                        "endIndex": pristine_end - 1,
                    }
                }
            }
        )

    # 2. Insert all new body content at index 1
    requests.extend(
        _generate_content_insert_requests(
            merged_xml,
            segment_id=None,  # Body has no segment ID
            insert_index=1,
            strip_trailing_newline=False,
        )
    )

    return requests


def _handle_content_block_change(
    change: BlockChange,
    pristine_section: Section | None,  # noqa: ARG001 - Kept for API consistency
    current_section: Section | None,  # noqa: ARG001 - Kept for API consistency
    segment_id: str | None,
) -> list[dict[str, Any]]:
    """Handle ContentBlock add/delete/modify changes.

    For MODIFIED content blocks, we use a simple delete + insert strategy.
    Also handles footnote child_changes which require special index calculation.

    Uses pristine_start_index/pristine_end_index from the BlockChange for positioning.
    """
    requests: list[dict[str, Any]] = []

    # Handle footnote child_changes first (they need the ContentBlock context)
    base_index = (
        change.pristine_start_index
        if change.pristine_start_index > 0
        else (1 if segment_id is None else 0)
    )

    for child_change in change.child_changes:
        if child_change.block_type == BlockType.FOOTNOTE:
            # For added footnotes, use after_xml; for deleted, use before_xml
            content_xml = (
                change.after_xml
                if child_change.change_type == ChangeType.ADDED
                else change.before_xml
            )
            requests.extend(
                _handle_footnote_change(child_change, content_xml, base_index)
            )

    if change.change_type == ChangeType.ADDED:
        # Insert new content - for additions, insert at pristine_start_index
        # (where the preceding element ends, or at the base index)
        if change.after_xml:
            insert_index = (
                change.pristine_start_index
                if change.pristine_start_index > 0
                else (1 if segment_id is None else 0)
            )
            # Adjust if at segment end - can't insert at the final newline position
            if (
                change.segment_end_index > 0
                and insert_index >= change.segment_end_index
            ):
                insert_index = change.segment_end_index - 1
            requests.extend(
                _generate_content_insert_requests(
                    change.after_xml, segment_id, insert_index
                )
            )

    elif change.change_type == ChangeType.DELETED:
        # Delete content using pristine indexes from BlockChange
        # Note: Body starts at index 1, but headers/footers/footnotes start at 0
        # Check for valid content range rather than just start > 0
        if (
            change.before_xml
            and change.pristine_end_index > change.pristine_start_index
        ):
            requests.extend(
                _generate_content_delete_requests_by_index(
                    change.pristine_start_index,
                    change.pristine_end_index,
                    segment_id,
                    change.segment_end_index,
                )
            )

    elif change.change_type == ChangeType.MODIFIED:
        # For modified blocks, delete old content and insert new at same position
        # Note: Don't strip trailing newline for MODIFIED blocks since other content
        # (ADDED blocks) may follow. The paragraph structure should be preserved.
        # Note: Body starts at index 1, but headers/footers/footnotes start at 0
        if (
            change.before_xml
            and change.pristine_end_index > change.pristine_start_index
        ):
            requests.extend(
                _generate_content_delete_requests_by_index(
                    change.pristine_start_index,
                    change.pristine_end_index,
                    segment_id,
                    change.segment_end_index,
                )
            )
        if change.after_xml:
            # Insert at the same position where we deleted
            requests.extend(
                _generate_content_insert_requests(
                    change.after_xml,
                    segment_id,
                    change.pristine_start_index,
                    strip_trailing_newline=False,  # Always include paragraph newline
                )
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
        bullets: List of (start_offset, end_offset, bullet_type, level) for list items
        text_styles: List of (start_offset, end_offset, styles_dict) for inline formatting
    """

    plain_text: str
    special_elements: list[tuple[int, str, dict[str, str]]]
    paragraph_styles: list[tuple[int, int, str]]
    bullets: list[tuple[int, int, str, int]]
    text_styles: list[tuple[int, int, dict[str, str]]]


def _parse_content_block_xml(xml_content: str) -> ParsedContent:
    """Parse ContentBlock XML into structured data for request generation.

    The XML content is a sequence of paragraph elements (p, h1, li, etc.).
    This function extracts:
    - Plain text with newlines between paragraphs
    - Special element positions (pagebreak, hr, etc.)
    - Paragraph styles (headings)
    - Bullet list info
    - Text run styles (bold, italic, links)
    """
    # Wrap in a root element for parsing
    wrapped = f"<root>{xml_content}</root>"
    root = ET.fromstring(wrapped)

    plain_text_parts: list[str] = []
    special_elements: list[tuple[int, str, dict[str, str]]] = []
    paragraph_styles: list[tuple[int, int, str]] = []
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
            para_elem, current_offset
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
    para_elem: ET.Element, base_offset: int
) -> tuple[
    str, list[tuple[int, str, dict[str, str]]], list[tuple[int, int, dict[str, str]]]
]:
    """Extract text, special elements, and text styles from a paragraph element.

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
            # Span with class - would need style resolution
            # For now, just track the class
            class_name = node.get("class")
            if class_name:
                node_styles["class"] = class_name

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

    Returns:
        List of batchUpdate requests
    """
    if not xml_content or not xml_content.strip():
        return []

    requests: list[dict[str, Any]] = []

    # Parse the content
    parsed = _parse_content_block_xml(xml_content)

    # Strip trailing newline if at segment end
    if strip_trailing_newline and parsed.plain_text.endswith("\n"):
        parsed = ParsedContent(
            plain_text=parsed.plain_text[:-1],
            special_elements=parsed.special_elements,
            paragraph_styles=parsed.paragraph_styles,
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
            }
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
            }
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
                    }
                }
            )
        elif elem_type == "columnbreak":
            # Column break is inserted via insertSectionBreak with CONTINUOUS type
            requests.append(
                {
                    "insertSectionBreak": {
                        "location": make_location(offset),
                        "sectionType": "CONTINUOUS",
                    }
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


def _bullet_type_to_preset(bullet_type: str) -> str:
    """Convert bullet type to Google Docs bullet preset."""
    presets = {
        "bullet": "BULLET_DISC_CIRCLE_SQUARE",
        "decimal": "NUMBERED_DECIMAL_NESTED",
        "alpha": "NUMBERED_UPPERCASE_ALPHA",
        "roman": "NUMBERED_UPPERCASE_ROMAN",
        "checkbox": "BULLET_CHECKBOX",
    }
    return presets.get(bullet_type, "BULLET_DISC_CIRCLE_SQUARE")


def _styles_to_text_style_request(styles: dict[str, str]) -> tuple[dict[str, Any], str]:
    """Convert style dict to Google Docs textStyle and fields string."""
    text_style: dict[str, Any] = {}
    fields: list[str] = []

    if styles.get("bold") == "1":
        text_style["bold"] = True
        fields.append("bold")

    if styles.get("italic") == "1":
        text_style["italic"] = True
        fields.append("italic")

    if styles.get("underline") == "1":
        text_style["underline"] = True
        fields.append("underline")

    if styles.get("strikethrough") == "1":
        text_style["strikethrough"] = True
        fields.append("strikethrough")

    if styles.get("superscript") == "1":
        text_style["baselineOffset"] = "SUPERSCRIPT"
        fields.append("baselineOffset")

    if styles.get("subscript") == "1":
        text_style["baselineOffset"] = "SUBSCRIPT"
        fields.append("baselineOffset")

    if "link" in styles:
        text_style["link"] = {"url": styles["link"]}
        fields.append("link")

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


def _generate_content_delete_requests(
    xml_content: str,
    section: Section,
    segment_id: str | None,
) -> list[dict[str, Any]]:
    """Generate delete requests for content XML.

    Calculates the index range of the content to delete by parsing
    the XML and computing UTF-16 lengths.

    Args:
        xml_content: The ContentBlock XML to delete
        section: The section containing this content (for base index)
        segment_id: The segment ID (header/footer/footnote ID, or None for body)

    Returns:
        List containing a single deleteContentRange request
    """
    if not xml_content or not xml_content.strip():
        return []

    # Calculate the UTF-16 length of the content
    content_length = _calculate_content_length(xml_content)
    if content_length == 0:
        return []

    # Body starts at index 1, headers/footers/footnotes start at 0
    base_index = 1 if section.section_type == "body" else 0

    # Build the delete range
    range_spec: dict[str, Any] = {
        "startIndex": base_index,
        "endIndex": base_index + content_length,
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


def _calculate_content_length(xml_content: str) -> int:
    """Calculate the UTF-16 length of content XML.

    Includes text content, newlines between paragraphs, and special elements.
    """
    # Wrap in root for parsing
    wrapped = f"<root>{xml_content}</root>"
    try:
        root = ET.fromstring(wrapped)
    except ET.ParseError:
        return 0

    total_length = 0

    for para_elem in root:
        # Get text content length
        text_content = _get_element_text(para_elem)
        total_length += utf16_len(text_content)

        # Count special elements (each takes 1 index)
        for special_tag in SPECIAL_ELEMENT_TAGS:
            total_length += len(list(para_elem.iter(special_tag)))

        # Add 1 for paragraph newline
        total_length += 1

    return total_length


def _get_element_text(elem: ET.Element) -> str:
    """Get all text content from an element, excluding special element markers."""
    parts: list[str] = []

    if elem.text:
        parts.append(elem.text)

    for child in elem:
        # Skip special elements
        if child.tag not in SPECIAL_ELEMENT_TAGS:
            parts.append(_get_element_text(child))

        if child.tail:
            parts.append(child.tail)

    return "".join(parts)


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
) -> dict[str, Any] | None:
    """Generate updateTableCellStyle request if cell has style attributes.

    Parses the cell XML to extract style attributes (bg, borders, padding, valign)
    and generates an updateTableCellStyle request if any are present.

    Args:
        cell_xml: The full cell XML (e.g., <td borderTop="1,#FF0000,SOLID">...</td>)
        table_start_index: Start index of the table
        row_index: Row index (0-based)
        col_index: Column index (0-based)
        segment_id: Optional segment ID

    Returns:
        An updateTableCellStyle request dict, or None if no styles to apply
    """
    try:
        root = ET.fromstring(cell_xml)
    except ET.ParseError:
        return None

    # Extract style attributes from the cell element
    styles = dict(root.attrib)

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
                    generate_insert_table_row_request(
                        table_start_index, 0, segment_id, insert_below=False
                    )
                )
            else:
                requests.append(
                    generate_insert_table_row_request(
                        table_start_index, row_index - 1, segment_id, insert_below=True
                    )
                )

        elif row_change.change_type == ChangeType.DELETED:
            # Delete row
            requests.append(
                generate_delete_table_row_request(
                    table_start_index, row_index, segment_id
                )
            )

        elif row_change.change_type == ChangeType.MODIFIED:
            # Row modified - check for cell changes
            # Sort by column index descending so we process from right to left
            # This ensures insertions don't shift indexes for subsequent operations
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

                if cell_change.change_type == ChangeType.ADDED:
                    # Cell added = column added (deduplicate)
                    if col_index not in columns_added:
                        columns_added.add(col_index)
                        requests.append(
                            generate_insert_table_column_request(
                                table_start_index, row_index, col_index, segment_id
                            )
                        )

                elif cell_change.change_type == ChangeType.DELETED:
                    # Cell deleted = column deleted (deduplicate)
                    if col_index not in columns_deleted:
                        columns_deleted.add(col_index)
                        requests.append(
                            generate_delete_table_column_request(
                                table_start_index, row_index, col_index, segment_id
                            )
                        )

                elif (
                    cell_change.change_type == ChangeType.MODIFIED and change.before_xml
                ):
                    # Cell content modified - use reusable content functions
                    # Mark requests to skip reordering so insert+style stay together
                    cell_content_index = _calculate_cell_content_index(
                        table_start_index,
                        row_index,
                        col_index,
                        change.before_xml,
                    )
                    if cell_content_index > 0:
                        # Calculate pristine cell content length for delete
                        pristine_cell_length = _get_pristine_cell_length(
                            change.before_xml, row_index, col_index
                        )
                        # Delete old content (preserve cell's final newline)
                        if pristine_cell_length > 1:
                            delete_reqs = _generate_content_delete_requests_by_index(
                                cell_content_index,
                                cell_content_index + pristine_cell_length - 1,
                                segment_id,
                                cell_content_index + pristine_cell_length,
                            )
                            for req in delete_reqs:
                                req["_skipReorder"] = True
                            requests.extend(delete_reqs)
                        # Insert new content
                        if cell_change.after_xml:
                            # Extract just the cell content (inner paragraphs)
                            cell_inner_xml = _extract_cell_inner_content(
                                cell_change.after_xml
                            )
                            if cell_inner_xml:
                                cell_reqs = _generate_content_insert_requests(
                                    cell_inner_xml,
                                    segment_id,
                                    cell_content_index,
                                    strip_trailing_newline=True,
                                )
                                # Mark to skip reordering - insert+style must stay together
                                for req in cell_reqs:
                                    req["_skipReorder"] = True
                                requests.extend(cell_reqs)

                            # Generate cell style request if cell has style attributes
                            cell_style_req = _generate_cell_style_request(
                                cell_change.after_xml,
                                table_start_index,
                                row_index,
                                col_index,
                                segment_id,
                            )
                            if cell_style_req:
                                cell_style_req["_skipReorder"] = True
                                requests.append(cell_style_req)

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


# Table request generation functions are now delegated to request_generators/table.py
# The following are imported at the top of this file:
# - generate_insert_table_row_request
# - generate_delete_table_row_request
# - generate_insert_table_column_request
# - generate_delete_table_column_request


# --- Request generation helpers (kept from original) ---


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
