"""Diff engine for ExtraDoc XML.

Compares pristine and edited documents to generate Google Docs batchUpdate requests.
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
    """Rebuild body content from current_xml.

    Strategy: delete the pristine body and reinsert the current body in order.
    This avoids the unstable structural diff that was interleaving content.
    """
    pristine = desugar_document(pristine_xml, pristine_styles)
    current = desugar_document(current_xml, current_styles)

    pristine_body = next(
        (s for s in pristine.sections if s.section_type == "body"), None
    )
    current_body = next((s for s in current.sections if s.section_type == "body"), None)

    if not current_body:
        return []

    requests: list[dict[str, Any]] = []

    if pristine_body and pristine_body.content:
        flattened = _flatten_elements(pristine_body.content, "body")
        end_index = max(1, flattened[-1][2] - 1)  # exclude terminal newline
        if end_index > 1:
            requests.append(
                {
                    "deleteContentRange": {
                        "range": {
                            "startIndex": 1,
                            "endIndex": end_index,
                        }
                    }
                }
            )

    cursor = 1
    for elem in current_body.content:
        elem_requests, added = _emit_element(elem, cursor, current_styles)
        requests.extend(elem_requests)
        cursor += added

    return requests


def _find_matching_section(target: Section, sections: list[Section]) -> Section | None:
    """Find a section in the list that matches the target."""
    for section in sections:
        if section.section_type == target.section_type:
            if section.section_id == target.section_id:
                return section
            # For body sections without IDs, match by type
            if not target.section_id and not section.section_id:
                return section
    return None


def _diff_section(_pristine: Section, _current: Section) -> list[DiffOperation]:
    """Legacy diff (unused in rebuild strategy)."""
    return []


def _element_to_key(elem: Paragraph | Table | SpecialElement) -> str:
    """Generate a structural key for element matching (ignores content)."""
    if isinstance(elem, Paragraph):
        prefix = ""
        if elem.named_style != "NORMAL_TEXT":
            prefix = f"[{elem.named_style}]"
        if elem.bullet_type:
            prefix = f"[{elem.bullet_type}:{elem.bullet_level}]"
        return f"P{prefix}"
    elif isinstance(elem, Table):
        return f"TABLE:{elem.rows}x{elem.cols}"
    elif isinstance(elem, SpecialElement):
        return f"SPECIAL:{elem.element_type}"
    return ""


def _diff_element_content(
    pristine: Paragraph | Table | SpecialElement,
    current: Paragraph | Table | SpecialElement,
    p_start: int,
    p_end: int,
    segment_id: str | None,
    section_type: str,
) -> list[DiffOperation]:
    """Diff content within structurally matching elements."""
    operations: list[DiffOperation] = []

    if isinstance(pristine, Paragraph) and isinstance(current, Paragraph):
        # Diff paragraph text content
        p_text = pristine.text_content()
        c_text = current.text_content()

        if p_text != c_text:
            # Replace entire paragraph content (including newline)
            operations.append(
                DiffOperation(
                    op_type="delete",
                    index=p_start,
                    end_index=p_end,
                    segment_id=segment_id,
                )
            )
            # Legacy path unused

        # Check for style changes
        style_ops = _diff_element_styles(
            (pristine, p_start, p_end),
            (current, p_start, p_end),
            segment_id,
        )
        operations.extend(style_ops)

    elif isinstance(pristine, Table) and isinstance(current, Table):
        # Diff table cell by cell
        table_ops = _diff_table_content(
            pristine, current, p_start, segment_id, section_type
        )
        operations.extend(table_ops)

    return operations


def _diff_table_content(
    pristine: Table,
    current: Table,
    table_start: int,
    segment_id: str | None,
    _section_type: str,
) -> list[DiffOperation]:
    """Diff table content cell by cell, comparing paragraphs individually."""
    operations: list[DiffOperation] = []

    # Build cell lookup by position
    p_cells = {(c.row, c.col): c for c in pristine.cells}
    c_cells = {(c.row, c.col): c for c in current.cells}

    # Calculate cell start indexes for pristine table
    cell_indexes = _calculate_table_cell_indexes(pristine, table_start)

    # Compare cells at same positions
    for pos, p_cell in p_cells.items():
        if pos not in c_cells:
            continue

        c_cell = c_cells[pos]
        cell_start = cell_indexes.get(pos, table_start)

        # Get paragraphs from both cells
        p_paras = [e for e in p_cell.content if isinstance(e, Paragraph)]
        c_paras = [e for e in c_cell.content if isinstance(e, Paragraph)]

        # Diff paragraphs within cell
        cell_ops = _diff_cell_paragraphs(p_paras, c_paras, cell_start, segment_id)
        operations.extend(cell_ops)

    return operations


def _diff_cell_paragraphs(
    pristine_paras: list[Paragraph],
    current_paras: list[Paragraph],
    cell_start: int,
    segment_id: str | None,
) -> list[DiffOperation]:
    """Diff paragraphs within a cell, preserving paragraph structure."""
    operations: list[DiffOperation] = []

    # Calculate paragraph start indexes for pristine
    para_indexes: list[tuple[int, int]] = []  # (start, end) for each paragraph
    current_idx = cell_start
    for para in pristine_paras:
        para_start = current_idx
        para_end = para_start + para.utf16_length()
        para_indexes.append((para_start, para_end))
        current_idx = para_end

    # Compare paragraphs up to the minimum length
    min_len = min(len(pristine_paras), len(current_paras))

    for i in range(min_len):
        p_para = pristine_paras[i]
        c_para = current_paras[i]
        p_start, _p_end = para_indexes[i]

        p_text = p_para.text_content()
        c_text = c_para.text_content()

        if p_text != c_text:
            # Text changed - delete old text (not newline), insert new text
            text_end = p_start + utf16_len(p_text)
            if p_text:
                operations.append(
                    DiffOperation(
                        op_type="delete",
                        index=p_start,
                        end_index=text_end,
                        segment_id=segment_id,
                    )
                )
            if c_text:
                operations.append(
                    DiffOperation(
                        op_type="insert",
                        index=p_start,
                        content=c_text,
                        segment_id=segment_id,
                    )
                )

    # Handle extra paragraphs in current (content added)
    # For now, we append to the last paragraph - full implementation would insert new paragraphs
    if len(current_paras) > len(pristine_paras) and pristine_paras:
        # Get the end of the last pristine paragraph (before its newline)
        last_para = pristine_paras[-1]
        last_start, _last_end = para_indexes[-1]
        insert_idx = last_start + utf16_len(last_para.text_content())

        # Collect text from extra paragraphs
        extra_text_parts = []
        for para in current_paras[len(pristine_paras) :]:
            text = para.text_content()
            if text:
                extra_text_parts.append("\n" + text)

        if extra_text_parts:
            operations.append(
                DiffOperation(
                    op_type="insert",
                    index=insert_idx,
                    content="".join(extra_text_parts),
                    segment_id=segment_id,
                )
            )

    return operations


def _calculate_table_cell_indexes(
    table: Table, table_start: int
) -> dict[tuple[int, int], int]:
    """Calculate the start index of text content in each table cell.

    Google Docs table structure (observed from API):
    - Table start marker: 1 index
    - First row marker: 1 index (combined with table = 2 indexes before first cell)
    - Each subsequent row: 1 row marker index
    - Cell structure: 1 index for cell start, then paragraph content
    - Each paragraph in cell includes +1 for newline
    """
    cell_indexes: dict[tuple[int, int], int] = {}

    # Table start (1) + first row marker (1) = 2 indexes before first cell
    current_idx = table_start + 2

    # Group cells by row
    cells_by_row: dict[int, list[TableCell]] = {}
    for cell in table.cells:
        cells_by_row.setdefault(cell.row, []).append(cell)

    for row in sorted(cells_by_row.keys()):
        if row > 0:
            current_idx += 1  # Row marker for subsequent rows

        row_cells = sorted(cells_by_row[row], key=lambda c: c.col)
        for cell in row_cells:
            # Cell start marker takes 1 index, then paragraph content starts
            current_idx += 1  # Cell content start marker

            # Record where paragraph text starts
            cell_indexes[(cell.row, cell.col)] = current_idx

            # Calculate content length (each paragraph includes +1 for newline)
            for elem in cell.content:
                if isinstance(elem, Paragraph):
                    current_idx += elem.utf16_length()

    return cell_indexes


def _get_cell_text(cell: TableCell) -> str:
    """Get text content of a cell, preserving paragraph breaks.

    Each paragraph in Google Docs ends with a newline character.
    We must preserve these for proper diffing and insertion.
    """
    parts = []
    for elem in cell.content:
        if isinstance(elem, Paragraph):
            text = elem.text_content()
            # Each paragraph ends with newline in Google Docs
            if text and not text.endswith("\n"):
                text += "\n"
            parts.append(text)
    return "".join(parts)


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
            # Simplified table index calculation
            end_idx = _calculate_table_end(elem, start_idx)
            result.append((elem, start_idx, end_idx))
            current_idx = end_idx

        elif isinstance(elem, SpecialElement):
            end_idx = start_idx + elem.utf16_length()
            result.append((elem, start_idx, end_idx))
            current_idx = end_idx

    return result


def _calculate_table_end(table: Table, start_idx: int) -> int:
    """Calculate the end index of a table."""
    current = start_idx + 1  # table start marker

    # Build lookup for cells by row to respect ordering
    cells_by_row: dict[int, list[TableCell]] = {}
    for cell in table.cells:
        cells_by_row.setdefault(cell.row, []).append(cell)

    for row in range(table.rows):
        current += 1  # row marker
        row_cells = sorted(cells_by_row.get(row, []), key=lambda c: c.col)
        for col in range(table.cols):
            # Each physical cell slot, even if empty, exists
            cell_obj = next((c for c in row_cells if c.col == col), None)
            current += 1  # cell marker
            if cell_obj and cell_obj.content:
                last_para_empty = (
                    isinstance(cell_obj.content[-1], Paragraph)
                    and cell_obj.content[-1].text_content() == ""
                )
                for elem in cell_obj.content:
                    if isinstance(elem, Paragraph):
                        current += elem.utf16_length()
                    elif isinstance(elem, SpecialElement):
                        current += 1
                # Docs keeps an empty paragraph at the end of the cell; skip if the
                # content already ends with an empty paragraph.
                if not last_para_empty:
                    current += 1
            else:
                current += 1  # default empty paragraph

    return current + 1  # table end marker


def _element_to_text(elem: Paragraph | Table | SpecialElement) -> str:
    """Convert an element to a text representation for comparison."""
    if isinstance(elem, Paragraph):
        text = elem.text_content()
        # Include structural info in the comparison key
        prefix = ""
        if elem.named_style != "NORMAL_TEXT":
            prefix = f"[{elem.named_style}]"
        if elem.bullet_type:
            prefix = f"[{elem.bullet_type}:{elem.bullet_level}]"
        return prefix + text

    elif isinstance(elem, Table):
        # Use a simple representation for tables
        parts = ["[TABLE]"]
        for cell in elem.cells:
            cell_text = ""
            for ce in cell.content:
                if isinstance(ce, Paragraph):
                    cell_text += ce.text_content()
            parts.append(f"[{cell.row},{cell.col}]{cell_text}")
        return "|".join(parts)

    elif isinstance(elem, SpecialElement):
        return f"[{elem.element_type}]"

    return ""


def _element_to_insert_text(elem: Paragraph | Table | SpecialElement) -> str:
    """Convert an element to the text to insert."""
    if isinstance(elem, Paragraph):
        # Get text content with newline
        text = elem.text_content()
        if not text.endswith("\n"):
            text += "\n"
        return text

    elif isinstance(elem, SpecialElement):
        # Special elements are handled differently
        return ""

    elif isinstance(elem, Table):
        # Tables need special handling
        return ""

    return ""


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
                last_para_empty = (
                    isinstance(cell.content[-1], Paragraph)
                    and cell.content[-1].text_content() == ""
                )
                for item in cell.content:
                    length += _element_length(item)
                # Docs keeps an empty paragraph at the end of each cell; if one is
                # already present in content, don't double count it.
                if not last_para_empty:
                    length += 1
            else:
                # Default empty paragraph
                length += 1
    length += 1  # table end marker
    return length


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


def _emit_element(
    elem: Paragraph | Table | SpecialElement, insert_idx: int, _styles_xml: str | None
) -> tuple[list[dict[str, Any]], int]:
    """Emit operations for an element at a given index and return (ops, length)."""
    ops: list[DiffOperation] = []
    added = 0

    if isinstance(elem, Paragraph):
        para_ops, para_len = _generate_paragraph_insert(elem, insert_idx, None)
        ops.extend(para_ops)
        added = para_len

    elif isinstance(elem, SpecialElement):
        spec_ops, spec_len = _generate_special_insert(elem, insert_idx, None)
        ops.extend(spec_ops)
        added = spec_len

    elif isinstance(elem, Table):
        table_ops, table_len = _generate_table_insert(elem, insert_idx, None)
        ops.extend(table_ops)
        added = table_len

    return [_operation_to_request(op) for op in ops], added


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
        content = "—\n"
        ops.append(
            DiffOperation(
                op_type="insert",
                index=insert_idx,
                content=content,
                segment_id=segment_id,
            )
        )
        added = utf16_len(content)
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


def _diff_element_styles(
    pristine: tuple[Paragraph | Table | SpecialElement, int, int],
    current: tuple[Paragraph | Table | SpecialElement, int, int],
    segment_id: str | None,
) -> list[DiffOperation]:
    """Diff styles between two elements."""
    operations: list[DiffOperation] = []

    pristine_elem, pristine_start, pristine_end = pristine
    current_elem, _, _ = current

    if not isinstance(pristine_elem, Paragraph) or not isinstance(
        current_elem, Paragraph
    ):
        return operations

    # Check for named style changes
    if pristine_elem.named_style != current_elem.named_style:
        operations.append(
            DiffOperation(
                op_type="update_paragraph_style",
                index=pristine_start,
                end_index=pristine_end,
                paragraph_style={"namedStyleType": current_elem.named_style},
                fields="namedStyleType",
                segment_id=segment_id,
            )
        )

    # Check for bullet changes
    if pristine_elem.bullet_type != current_elem.bullet_type:
        if current_elem.bullet_type:
            # Add bullet
            preset = _bullet_type_to_preset(current_elem.bullet_type)
            operations.append(
                DiffOperation(
                    op_type="create_bullets",
                    index=pristine_start,
                    end_index=pristine_end,
                    bullet_preset=preset,
                    segment_id=segment_id,
                )
            )
        else:
            # Remove bullet
            operations.append(
                DiffOperation(
                    op_type="delete_bullets",
                    index=pristine_start,
                    end_index=pristine_end,
                    segment_id=segment_id,
                )
            )

    # Check for text style changes within runs
    # This is a simplified comparison - a full implementation would do character-level diff
    pristine_runs = pristine_elem.runs
    current_runs = current_elem.runs

    if len(pristine_runs) == len(current_runs):
        run_start = pristine_start
        for p_run, c_run in zip(pristine_runs, current_runs, strict=False):
            run_end = run_start + p_run.utf16_length()

            # Compare styles
            style_diff = _diff_run_styles(p_run.styles, c_run.styles)
            if style_diff:
                text_style, fields = style_diff
                operations.append(
                    DiffOperation(
                        op_type="update_text_style",
                        index=run_start,
                        end_index=run_end,
                        text_style=text_style,
                        fields=fields,
                        segment_id=segment_id,
                    )
                )

            run_start = run_end

    return operations


def _diff_run_styles(
    pristine: dict[str, str], current: dict[str, str]
) -> tuple[dict[str, Any], str] | None:
    """Diff text run styles and return (style_dict, fields) if changed."""
    changes: dict[str, Any] = {}
    fields: list[str] = []

    # Check for added/changed styles
    for key, value in current.items():
        if key == "_special":
            continue
        if key not in pristine or pristine[key] != value:
            if key == "bold":
                changes["bold"] = value == "1"
                fields.append("bold")
            elif key == "italic":
                changes["italic"] = value == "1"
                fields.append("italic")
            elif key == "underline":
                changes["underline"] = value == "1"
                fields.append("underline")
            elif key == "strikethrough":
                changes["strikethrough"] = value == "1"
                fields.append("strikethrough")
            elif key == "link":
                changes["link"] = {"url": value}
                fields.append("link")

    # Check for removed styles
    for key, _value in pristine.items():
        if key == "_special":
            continue
        if key not in current:
            if key == "bold":
                changes["bold"] = False
                fields.append("bold")
            elif key == "italic":
                changes["italic"] = False
                fields.append("italic")
            elif key == "underline":
                changes["underline"] = False
                fields.append("underline")
            elif key == "strikethrough":
                changes["strikethrough"] = False
                fields.append("strikethrough")
            elif key == "link":
                changes["link"] = None
                fields.append("link")

    if changes:
        return changes, ",".join(fields)
    return None


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

    # Fallback - should not happen
    return {}
