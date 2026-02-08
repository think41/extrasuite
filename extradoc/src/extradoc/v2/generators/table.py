"""Table request generation for ExtraDoc v2.

Handles TABLE change nodes: add, delete, and 5-phase modify.

Phase ordering for MODIFIED tables:
1. Column deletes (highest col_index first)
2. Row deletes (highest row_index first)
3. Cell mods + row inserts (bottom to top) — tracks row_lengths
4. Column inserts (highest col_index first) — uses row_lengths
5. Column widths
"""

from __future__ import annotations

import contextlib
import re
import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING, Any

from extradoc.indexer import utf16_len
from extradoc.request_generators.table import (
    generate_delete_table_column_request,
    generate_delete_table_row_request,
    generate_insert_table_column_request,
    generate_insert_table_row_request,
)
from extradoc.style_converter import (
    TABLE_CELL_STYLE_PROPS,
    build_table_cell_style_request,
    convert_styles,
)

from ..types import ChangeNode, ChangeOp, NodeType, SegmentContext

if TYPE_CHECKING:
    from .content import ContentGenerator

# Special element tags for length calculation
SPECIAL_ELEMENT_TAGS = frozenset(
    {"hr", "pagebreak", "columnbreak", "image", "footnote"}
)

# Paragraph tags
PARAGRAPH_TAGS = frozenset(
    {"p", "h1", "h2", "h3", "h4", "h5", "h6", "title", "subtitle", "li"}
)


class TableGenerator:
    """Generates batchUpdate requests for TABLE change nodes."""

    def __init__(self, content_gen: ContentGenerator) -> None:
        self._content_gen = content_gen

    def emit(self, node: ChangeNode, ctx: SegmentContext) -> list[dict[str, Any]]:
        """Emit requests for a TABLE change."""
        if node.op == ChangeOp.ADDED:
            return self._add_table(node, ctx)
        elif node.op == ChangeOp.DELETED:
            return self._delete_table(node, ctx)
        elif node.op == ChangeOp.MODIFIED:
            return self._modify_table(node, ctx)
        return []

    # --- ADD TABLE ---

    def _add_table(self, node: ChangeNode, ctx: SegmentContext) -> list[dict[str, Any]]:
        """Insert a new table with cell content."""
        if not node.after_xml:
            return []

        requests: list[dict[str, Any]] = []
        table_info = _parse_table_xml(node.after_xml)
        rows = table_info["rows"]
        cols = table_info["cols"]

        insert_index = node.pristine_start if node.pristine_start > 0 else 0

        # Clamp to valid range — can't insert past segment_end - 1
        if ctx.segment_end > 0 and insert_index > ctx.segment_end - 1:
            insert_index = ctx.segment_end - 1

        if insert_index > 0:
            location: dict[str, Any] = {"index": insert_index}
            if ctx.segment_id:
                location["segmentId"] = ctx.segment_id
            requests.append(
                {
                    "insertTable": {
                        "rows": rows,
                        "columns": cols,
                        "location": location,
                    }
                }
            )
        else:
            end_location: dict[str, Any] = {}
            if ctx.segment_id:
                end_location["segmentId"] = ctx.segment_id
            requests.append(
                {
                    "insertTable": {
                        "rows": rows,
                        "columns": cols,
                        "endOfSegmentLocation": end_location or {"segmentId": ""},
                    }
                }
            )
            return requests

        # Calculate cell positions and insert content
        try:
            root = ET.fromstring(node.after_xml)
        except ET.ParseError:
            return requests

        cell_contents: list[tuple[int, int, str]] = []
        for row_idx, tr in enumerate(root.findall("tr")):
            for col_idx, td in enumerate(tr.findall("td")):
                inner_parts = [ET.tostring(c, encoding="unicode") for c in td]
                if inner_parts:
                    cell_contents.append((row_idx, col_idx, "".join(inner_parts)))

        cell_starts = _calculate_new_table_cell_starts(insert_index, rows, cols)

        for row_idx, col_idx, inner_xml in sorted(
            cell_contents,
            key=lambda x: cell_starts.get((x[0], x[1]), 0),
            reverse=True,
        ):
            cell_start = cell_starts.get((row_idx, col_idx))
            if cell_start is None:
                continue
            cell_reqs = self._content_gen._generate_content_insert_requests(
                inner_xml,
                ctx.segment_id,
                insert_index=cell_start,
                strip_trailing_newline=True,
            )
            requests.extend(cell_reqs)

        return requests

    # --- DELETE TABLE ---

    def _delete_table(
        self, node: ChangeNode, ctx: SegmentContext
    ) -> list[dict[str, Any]]:
        """Delete a table by its index range."""
        if not node.before_xml or node.pristine_start <= 0:
            return []

        try:
            root = ET.fromstring(node.before_xml)
            table_size = _calculate_nested_table_length(root)
        except ET.ParseError:
            return []

        range_obj: dict[str, Any] = {
            "startIndex": node.pristine_start,
            "endIndex": node.pristine_start + table_size,
        }
        if ctx.segment_id:
            range_obj["segmentId"] = ctx.segment_id

        return [{"deleteContentRange": {"range": range_obj}}]

    # --- MODIFY TABLE (5 phases) ---

    def _modify_table(
        self, node: ChangeNode, ctx: SegmentContext
    ) -> list[dict[str, Any]]:
        """Modify a table using 5-phase approach."""
        requests: list[dict[str, Any]] = []
        table_start = node.table_start

        # Separate child changes by type
        col_changes = [c for c in node.children if c.node_type == NodeType.TABLE_COLUMN]
        row_changes = [c for c in node.children if c.node_type == NodeType.TABLE_ROW]

        # Phase 5: Column widths (uses current table start, can be emitted anytime)
        requests.extend(self._phase_column_widths(node, ctx))

        if table_start == 0:
            return requests

        segment_id = ctx.segment_id

        # Phase 1: Column deletes
        requests.extend(self._phase_column_deletes(node, col_changes, segment_id))

        # Phase 2: Row deletes
        requests.extend(self._phase_row_deletes(node, row_changes, segment_id))

        # Phase 3: Cell mods + row inserts
        cell_reqs, row_lengths = self._phase_cell_mods_and_row_inserts(
            node, row_changes, ctx
        )
        requests.extend(cell_reqs)

        # Phase 4: Column inserts
        requests.extend(self._phase_column_inserts(node, col_changes, row_lengths, ctx))

        return requests

    def _phase_column_deletes(
        self,
        node: ChangeNode,
        col_changes: list[ChangeNode],
        segment_id: str | None,
    ) -> list[dict[str, Any]]:
        """Phase 1: Delete columns highest col_index first."""
        requests: list[dict[str, Any]] = []
        deletes = [c for c in col_changes if c.op == ChangeOp.DELETED]
        for col_change in sorted(deletes, key=lambda c: c.col_index, reverse=True):
            requests.append(
                generate_delete_table_column_request(
                    node.table_start, 0, col_change.col_index, segment_id
                )
            )
        return requests

    def _phase_row_deletes(
        self,
        node: ChangeNode,
        row_changes: list[ChangeNode],
        segment_id: str | None,
    ) -> list[dict[str, Any]]:
        """Phase 2: Delete rows highest row_index first."""
        requests: list[dict[str, Any]] = []
        deletes = [c for c in row_changes if c.op == ChangeOp.DELETED]
        for row_change in sorted(deletes, key=lambda c: c.row_index, reverse=True):
            requests.append(
                generate_delete_table_row_request(
                    node.table_start, row_change.row_index, segment_id
                )
            )
        return requests

    def _phase_cell_mods_and_row_inserts(
        self,
        node: ChangeNode,
        row_changes: list[ChangeNode],
        ctx: SegmentContext,
    ) -> tuple[list[dict[str, Any]], dict[int, int]]:
        """Phase 3: Cell modifications and row inserts (bottom-to-top).

        Returns (requests, row_lengths) where row_lengths maps
        row_index to post-modification length.
        """
        requests: list[dict[str, Any]] = []
        row_lengths: dict[int, int] = {}
        table_start = node.table_start
        segment_id = ctx.segment_id

        # Determine pristine row count
        pristine_row_count = 0
        if node.before_xml:
            with contextlib.suppress(ET.ParseError):
                pristine_row_count = len(ET.fromstring(node.before_xml).findall("tr"))
        last_pristine_row = max(pristine_row_count - 1, 0)

        # Collect columns that were added/deleted for cell filtering
        col_changes = [c for c in node.children if c.node_type == NodeType.TABLE_COLUMN]
        cols_added = {c.col_index for c in col_changes if c.op == ChangeOp.ADDED}
        cols_deleted = {c.col_index for c in col_changes if c.op == ChangeOp.DELETED}

        # Deferred row inserts
        deferred_row_adds: list[tuple[int, dict[str, Any], str | None]] = []

        # Process bottom-to-top
        for row_change in sorted(row_changes, key=lambda c: c.row_index, reverse=True):
            row_idx = row_change.row_index

            if row_change.op == ChangeOp.ADDED:
                if row_idx == 0 or pristine_row_count == 0:
                    deferred_row_adds.append(
                        (
                            row_idx,
                            generate_insert_table_row_request(
                                table_start, 0, segment_id, insert_below=False
                            ),
                            row_change.after_xml,
                        )
                    )
                else:
                    anchor = min(row_idx - 1, last_pristine_row)
                    deferred_row_adds.append(
                        (
                            row_idx,
                            generate_insert_table_row_request(
                                table_start, anchor, segment_id, insert_below=True
                            ),
                            row_change.after_xml,
                        )
                    )

            elif row_change.op == ChangeOp.MODIFIED:
                # Walk cells right-to-left
                cell_changes = sorted(
                    [
                        c
                        for c in row_change.children
                        if c.node_type == NodeType.TABLE_CELL
                    ],
                    key=lambda c: c.col_index,
                    reverse=True,
                )
                for cell_change in cell_changes:
                    col_idx = cell_change.col_index
                    if col_idx in cols_added or col_idx in cols_deleted:
                        continue

                    if cell_change.op == ChangeOp.MODIFIED and node.before_xml:
                        cell_content_idx = cell_change.pristine_start
                        cell_end = cell_change.pristine_end
                        if cell_content_idx > 0 and cell_end >= cell_content_idx:
                            before_inner = _extract_cell_inner_content(
                                cell_change.before_xml or ""
                            )
                            after_inner = _extract_cell_inner_content(
                                cell_change.after_xml or ""
                            )

                            content_change = ChangeNode(
                                node_type=NodeType.CONTENT_BLOCK,
                                op=ChangeOp.MODIFIED,
                                before_xml=before_inner,
                                after_xml=after_inner,
                                pristine_start=cell_content_idx,
                                pristine_end=max(cell_end - 1, cell_content_idx),
                            )
                            cell_ctx = SegmentContext(
                                segment_id=segment_id,
                                segment_end=cell_end,
                            )
                            cell_reqs, _ = self._content_gen.emit(
                                content_change, cell_ctx
                            )
                            requests.extend(cell_reqs)

                            # Cell style
                            cell_style_req = _generate_cell_style_request(
                                cell_change.after_xml or "",
                                table_start,
                                row_change.row_index,
                                col_idx,
                                segment_id,
                                self._content_gen._style_defs,
                            )
                            if cell_style_req:
                                requests.append(cell_style_req)

        # Emit deferred row inserts (highest first)
        for _, req, _row_xml in sorted(
            deferred_row_adds, key=lambda item: item[0], reverse=True
        ):
            requests.append(req)

        # Populate added row cells
        if deferred_row_adds and node.after_xml:
            for row_idx, _, row_xml in sorted(
                deferred_row_adds, key=lambda item: item[0]
            ):
                if not row_xml:
                    continue
                try:
                    row_root = ET.fromstring(row_xml)
                except ET.ParseError:
                    continue
                cells = list(row_root.findall("td"))
                if not cells:
                    continue
                cell_0_start = _calculate_cell_content_index(
                    table_start, row_idx, 0, node.after_xml
                )
                if cell_0_start <= 0:
                    continue
                for col_idx in reversed(range(len(cells))):
                    td = cells[col_idx]
                    inner = _extract_cell_inner_content(
                        ET.tostring(td, encoding="unicode")
                    )
                    if not inner.strip():
                        continue
                    cell_start = cell_0_start + 2 * col_idx
                    cell_reqs = self._content_gen._generate_content_insert_requests(
                        inner,
                        segment_id,
                        insert_index=cell_start,
                        strip_trailing_newline=True,
                    )
                    requests.extend(cell_reqs)

        return requests, row_lengths

    def _phase_column_inserts(
        self,
        node: ChangeNode,
        col_changes: list[ChangeNode],
        _row_lengths: dict[int, int],
        ctx: SegmentContext,
    ) -> list[dict[str, Any]]:
        """Phase 4: Insert columns (highest col_index first)."""
        requests: list[dict[str, Any]] = []
        adds = [c for c in col_changes if c.op == ChangeOp.ADDED]

        for col_change in sorted(adds, key=lambda c: c.col_index, reverse=True):
            requests.append(
                generate_insert_table_column_request(
                    node.table_start, 0, col_change.col_index, ctx.segment_id
                )
            )

        # Populate new column cells
        if adds and node.after_xml and node.before_xml:
            try:
                after_root = ET.fromstring(node.after_xml)
            except ET.ParseError:
                return requests

            cols_added_set = {c.col_index for c in adds}
            rows_after = after_root.findall("tr")
            for col_idx in sorted(cols_added_set, reverse=True):
                for row_idx in reversed(range(len(rows_after))):
                    td_xml = _get_cell_xml_from_table(node.after_xml, row_idx, col_idx)
                    if not td_xml:
                        continue
                    inner = _extract_cell_inner_content(td_xml)
                    if not inner.strip():
                        continue
                    if col_idx == 0:
                        base = _calculate_cell_content_index(
                            node.table_start, row_idx, 0, node.before_xml
                        )
                        cell_start = base + 2 * row_idx
                    else:
                        pristine_col = col_idx - 1
                        base = _calculate_cell_content_index(
                            node.table_start, row_idx, pristine_col, node.before_xml
                        )
                        pristine_len = _get_pristine_cell_length(
                            node.before_xml, row_idx, pristine_col
                        )
                        cell_start = base + pristine_len + 2 * row_idx + 1
                    if cell_start <= 0:
                        continue
                    content_reqs = self._content_gen._generate_content_insert_requests(
                        inner,
                        ctx.segment_id,
                        insert_index=cell_start,
                        strip_trailing_newline=True,
                    )
                    requests.extend(content_reqs)

        return requests

    def _phase_column_widths(
        self, node: ChangeNode, ctx: SegmentContext
    ) -> list[dict[str, Any]]:
        """Phase 5: Column width changes."""
        before_widths = _extract_column_widths(node.before_xml)
        after_widths = _extract_column_widths(node.after_xml)

        if before_widths == after_widths:
            return []

        # Use table_start for column width requests
        table_start = node.table_start
        if table_start <= 0:
            return []

        return _generate_column_width_requests(
            table_start, before_widths, after_widths, ctx.segment_id
        )


# --- Helper functions (cherry-picked from v1 diff_engine.py) ---


def _parse_table_xml(xml_content: str) -> dict[str, Any]:
    """Parse table XML to extract dimensions."""
    root = ET.fromstring(xml_content)
    tr_elements = list(root.iter("tr"))
    num_rows = len(tr_elements)
    num_cols = len(list(tr_elements[0].iter("td"))) if tr_elements else 0
    return {"rows": num_rows, "cols": num_cols, "id": root.get("id", "")}


def _calculate_new_table_cell_starts(
    insert_location_index: int, rows: int, cols: int
) -> dict[tuple[int, int], int]:
    """Calculate cell content start indexes for a newly inserted empty table."""
    cell_starts: dict[tuple[int, int], int] = {}
    idx = insert_location_index + 1 + 1  # +1 newline, +1 table marker

    for row in range(rows):
        idx += 1  # Row marker
        for col in range(cols):
            idx += 1  # Cell marker
            cell_starts[(row, col)] = idx
            idx += 1  # Default empty paragraph

    return cell_starts


def _calculate_nested_table_length(table_elem: ET.Element) -> int:
    """Calculate the UTF-16 length of a table."""
    length = 1  # Table start marker

    for tr in table_elem.findall("tr"):
        length += 1  # Row marker
        for td in tr.findall("td"):
            length += 1  # Cell marker
            length += _calculate_cell_content_length(td)

    length += 1  # Table end marker
    return length


def _calculate_cell_content_length(td_elem: ET.Element) -> int:
    """Calculate the UTF-16 length of a table cell's content."""
    total_length = 0
    children = list(td_elem)
    if not children:
        return 1  # Empty cell

    for child in children:
        if child.tag in PARAGRAPH_TAGS:
            text_length = _get_element_text_length(child)
            special_count = sum(
                1 for elem in child.iter() if elem.tag in SPECIAL_ELEMENT_TAGS
            )
            total_length += text_length + special_count + 1
        elif child.tag == "table":
            total_length += _calculate_nested_table_length(child)

    return total_length if total_length > 0 else 1


def _get_element_text_length(elem: ET.Element) -> int:
    """Get the UTF-16 length of text content."""
    length = 0
    if elem.text:
        length += utf16_len(elem.text)
    for child in elem:
        if child.tag not in SPECIAL_ELEMENT_TAGS:
            length += _get_element_text_length(child)
        if child.tail:
            length += utf16_len(child.tail)
    return length


def _calculate_cell_content_index(
    table_start_index: int,
    target_row: int,
    target_col: int,
    table_xml: str,
) -> int:
    """Calculate the content start index for a specific table cell."""
    try:
        root = ET.fromstring(table_xml)
    except ET.ParseError:
        return 0

    current_index = table_start_index + 1  # Table start marker

    for row_idx, tr in enumerate(root.findall("tr")):
        current_index += 1  # Row marker
        for col_idx, td in enumerate(tr.findall("td")):
            current_index += 1  # Cell marker
            if row_idx == target_row and col_idx == target_col:
                return current_index
            current_index += _calculate_cell_content_length(td)
        if row_idx == target_row:
            break

    return 0


def _extract_cell_inner_content(cell_xml: str) -> str:
    """Extract inner content (paragraphs) from cell XML."""
    try:
        root = ET.fromstring(cell_xml)
    except ET.ParseError:
        return ""
    return "\n".join(ET.tostring(child, encoding="unicode") for child in root)


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
    """Get the content length of a specific cell."""
    try:
        root = ET.fromstring(table_xml)
    except ET.ParseError:
        return 1
    trs = root.findall("tr")
    if row >= len(trs):
        return 1
    tds = trs[row].findall("td")
    if col >= len(tds):
        return 1
    return _calculate_cell_content_length(tds[col])


def _generate_cell_style_request(
    cell_xml: str,
    table_start_index: int,
    row_index: int,
    col_index: int,
    segment_id: str | None,
    cell_styles: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any] | None:
    """Generate updateTableCellStyle request if cell has style attributes."""
    try:
        root = ET.fromstring(cell_xml)
    except ET.ParseError:
        return None

    attrs = dict(root.attrib)
    styles: dict[str, str] = {}

    class_name = attrs.get("class")
    if class_name and cell_styles and class_name in cell_styles:
        styles = cell_styles[class_name].copy()

    for key, value in attrs.items():
        if key not in ("id", "class", "colspan", "rowspan"):
            styles[key] = value

    _, fields = convert_styles(styles, TABLE_CELL_STYLE_PROPS)
    if not fields:
        return None

    return build_table_cell_style_request(
        styles, table_start_index, row_index, col_index, segment_id
    )


def _extract_column_widths(table_xml: str | None) -> dict[int, str]:
    """Extract column widths from table XML."""
    if not table_xml:
        return {}
    try:
        root = ET.fromstring(table_xml)
    except ET.ParseError:
        return {}

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
    """Generate UpdateTableColumnPropertiesRequest for width changes."""
    requests: list[dict[str, Any]] = []
    all_columns = set(before_widths.keys()) | set(after_widths.keys())

    for col_index in sorted(all_columns):
        before_width = before_widths.get(col_index)
        after_width = after_widths.get(col_index)
        if before_width == after_width:
            continue

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
            match = re.match(r"([\d.]+)(pt|in|mm)?", after_width, re.IGNORECASE)
            if match:
                magnitude = float(match.group(1))
                unit = (match.group(2) or "pt").upper()
                col_props["widthType"] = "FIXED_WIDTH"
                col_props["width"] = {"magnitude": magnitude, "unit": unit}
                fields.extend(["widthType", "width"])
        else:
            col_props["widthType"] = "EVENLY_DISTRIBUTED"
            fields.append("widthType")

        request["updateTableColumnProperties"]["fields"] = ",".join(fields)
        requests.append(request)

    return requests
