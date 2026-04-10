"""Apply ReconcileOps in-memory to a base document dict.

This module supports the 3-way merge deserialize workflow:
    ancestor  = parse(pristine)
    mine      = parse(current folder)
    ops       = reconcile_v3.diff(ancestor, mine)
    desired   = apply_ops_to_document(base, ops)

The function works entirely on raw dicts (not Pydantic models).
"""

from __future__ import annotations

import bisect
import copy
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from extradoc.api_types._generated import StructuralElement
    from extradoc.diffmerge.content_align import ContentAlignment
    from extradoc.diffmerge.model import ReconcileOp


def _to_dict(obj: Any) -> Any:
    """Convert a Pydantic model (or list thereof) to a plain dict."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump(by_alias=True, exclude_none=True)
    if isinstance(obj, list):
        return [_to_dict(item) for item in obj]
    return obj


def apply_ops_to_document(
    base_doc: dict[str, Any],
    ops: list[ReconcileOp],
) -> dict[str, Any]:
    """Apply ops in-memory to base_doc.

    Parameters
    ----------
    base_doc:
        Raw dict from base DocumentWithComments.document (via model_dump).
    ops:
        List of ReconcileOps from diff(ancestor, mine).

    Returns
    -------
    dict
        Deep copy of base_doc with all ops applied.
    """
    # Import here to avoid circular imports at module load time
    from extradoc.diffmerge.model import (
        CreateFooterOp,
        CreateHeaderOp,
        DeleteFooterOp,
        DeleteFootnoteOp,
        DeleteHeaderOp,
        DeleteInlineObjectOp,
        DeleteListOp,
        DeleteNamedStyleOp,
        DeleteTableColumnOp,
        DeleteTableRowOp,
        DeleteTabOp,
        InsertFootnoteOp,
        InsertInlineObjectOp,
        InsertListOp,
        InsertNamedStyleOp,
        InsertTableColumnOp,
        InsertTableRowOp,
        InsertTabOp,
        UpdateBodyContentOp,
        UpdateDocumentStyleOp,
        UpdateFooterContentOp,
        UpdateFootnoteContentOp,
        UpdateHeaderContentOp,
        UpdateInlineObjectOp,
        UpdateListOp,
        UpdateNamedStyleOp,
        UpdateTableCellStyleOp,
        UpdateTableColumnPropertiesOp,
        UpdateTableRowStyleOp,
    )

    doc = copy.deepcopy(base_doc)

    # Collect child_ops from UpdateBodyContentOp. These are table structural
    # ops meant for the lowerer (API request generation), not for in-memory
    # application. The UpdateBodyContentOp's alignment already incorporates
    # structural changes (row/column adds/deletes) in its desired content.
    child_ops: set[int] = set()
    for op in ops:
        if isinstance(op, UpdateBodyContentOp):
            for child in op.child_ops:
                child_ops.add(id(child))

    for op in ops:
        if id(op) in child_ops:
            # Skip child ops — already handled by the parent UpdateBodyContentOp
            continue
        if isinstance(op, InsertTabOp):
            _apply_insert_tab(doc, op)
        elif isinstance(op, DeleteTabOp):
            _apply_delete_tab(doc, op)
        elif isinstance(op, UpdateDocumentStyleOp):
            _apply_update_document_style(doc, op)
        elif isinstance(op, UpdateNamedStyleOp | InsertNamedStyleOp):
            _apply_update_named_style(doc, op)
        elif isinstance(op, DeleteNamedStyleOp):
            _apply_delete_named_style(doc, op)
        elif isinstance(op, InsertListOp):
            _apply_insert_list(doc, op)
        elif isinstance(op, DeleteListOp):
            _apply_delete_list(doc, op)
        elif isinstance(op, UpdateListOp):
            # List definition changes are not editable via API — skip
            pass
        elif isinstance(op, UpdateInlineObjectOp):
            # Inline object updates are not supported — skip
            pass
        elif isinstance(op, InsertInlineObjectOp):
            # Inline object insertion is not supported in-memory — skip
            pass
        elif isinstance(op, DeleteInlineObjectOp):
            # Inline object deletion is not supported in-memory — skip
            pass
        elif isinstance(op, CreateHeaderOp):
            _apply_create_header(doc, op)
        elif isinstance(op, DeleteHeaderOp):
            _apply_delete_header(doc, op)
        elif isinstance(op, UpdateHeaderContentOp):
            _apply_update_header_content(doc, op)
        elif isinstance(op, CreateFooterOp):
            _apply_create_footer(doc, op)
        elif isinstance(op, DeleteFooterOp):
            _apply_delete_footer(doc, op)
        elif isinstance(op, UpdateFooterContentOp):
            _apply_update_footer_content(doc, op)
        elif isinstance(op, InsertFootnoteOp):
            _apply_insert_footnote(doc, op)
        elif isinstance(op, DeleteFootnoteOp):
            _apply_delete_footnote(doc, op)
        elif isinstance(op, UpdateFootnoteContentOp):
            _apply_update_footnote_content(doc, op)
        elif isinstance(op, UpdateBodyContentOp):
            _apply_update_body_content(doc, op)
        elif isinstance(
            op,
            InsertTableRowOp
            | DeleteTableRowOp
            | InsertTableColumnOp
            | DeleteTableColumnOp,
        ):
            _apply_table_structural_op(doc, op)
        elif isinstance(
            op,
            UpdateTableCellStyleOp
            | UpdateTableRowStyleOp
            | UpdateTableColumnPropertiesOp,
        ):
            _apply_table_style_op(doc, op)
        # Any unknown op type is silently skipped

    return doc


# ---------------------------------------------------------------------------
# Tab ops
# ---------------------------------------------------------------------------


def _find_tab(doc: dict[str, Any], tab_id: str) -> dict[str, Any] | None:
    """Find a tab dict by tabId."""
    tabs: list[dict[str, Any]] = doc.get("tabs") or []
    for tab in tabs:
        props = tab.get("tabProperties") or {}
        if props.get("tabId") == tab_id:
            return tab
    return None


def _find_doc_tab(doc: dict[str, Any], tab_id: str) -> dict[str, Any] | None:
    """Find the documentTab portion for a given tabId."""
    tab = _find_tab(doc, tab_id)
    if tab is None:
        return None
    return tab.get("documentTab") or {}


def _apply_insert_tab(doc: dict[str, Any], op: Any) -> None:
    """Insert a new tab into the document."""
    tabs: list[dict[str, Any]] = doc.setdefault("tabs", [])
    desired_tab = _to_dict(op.desired_tab)
    # Insert at the right position based on desired_tab_index
    idx = op.desired_tab_index
    tabs.insert(idx, desired_tab)


def _apply_delete_tab(doc: dict[str, Any], op: Any) -> None:
    """Remove a tab from the document."""
    tabs: list[dict[str, Any]] = doc.get("tabs") or []
    doc["tabs"] = [
        t for t in tabs if (t.get("tabProperties") or {}).get("tabId") != op.base_tab_id
    ]


# ---------------------------------------------------------------------------
# DocumentStyle
# ---------------------------------------------------------------------------


def _apply_update_document_style(doc: dict[str, Any], op: Any) -> None:
    """Merge desired_style into the matching tab's documentStyle."""
    dt = _find_doc_tab(doc, op.tab_id)
    if dt is None:
        return
    doc_style: dict[str, Any] = dt.setdefault("documentStyle", {})
    doc_style.update(op.desired_style.model_dump(by_alias=True, exclude_none=True))


# ---------------------------------------------------------------------------
# NamedStyles
# ---------------------------------------------------------------------------


def _apply_update_named_style(doc: dict[str, Any], op: Any) -> None:
    """Update or insert a named style in the matching tab."""
    dt = _find_doc_tab(doc, op.tab_id)
    if dt is None:
        return
    named_styles: dict[str, Any] = dt.setdefault("namedStyles", {"styles": []})
    styles: list[dict[str, Any]] = named_styles.setdefault("styles", [])

    # If it's an update, replace. If insert, add.
    from extradoc.diffmerge.model import UpdateNamedStyleOp

    if isinstance(op, UpdateNamedStyleOp):
        desired_style = op.desired_style
    else:
        desired_style = op.desired_style  # InsertNamedStyleOp

    # Convert typed model to dict for the raw dict document tree
    desired_dict = desired_style.model_dump(by_alias=True, exclude_none=True)

    style_type = op.named_style_type
    for i, s in enumerate(styles):
        if s.get("namedStyleType") == style_type:
            styles[i] = copy.deepcopy(desired_dict)
            return
    styles.append(copy.deepcopy(desired_dict))


def _apply_delete_named_style(doc: dict[str, Any], op: Any) -> None:
    """Remove a named style from the matching tab."""
    dt = _find_doc_tab(doc, op.tab_id)
    if dt is None:
        return
    named_styles = dt.get("namedStyles") or {}
    styles: list[dict[str, Any]] = named_styles.get("styles") or []
    named_styles["styles"] = [
        s for s in styles if s.get("namedStyleType") != op.named_style_type
    ]


# ---------------------------------------------------------------------------
# Lists
# ---------------------------------------------------------------------------


def _apply_insert_list(doc: dict[str, Any], op: Any) -> None:
    """Insert a new list into the matching tab's lists dict."""
    dt = _find_doc_tab(doc, op.tab_id)
    if dt is None:
        return
    lists: dict[str, Any] = dt.setdefault("lists", {})
    lists[op.list_id] = _to_dict(op.list_def)


def _apply_delete_list(doc: dict[str, Any], op: Any) -> None:
    """Remove a list from the matching tab's lists dict."""
    dt = _find_doc_tab(doc, op.tab_id)
    if dt is None:
        return
    lists: dict[str, Any] = dt.get("lists") or {}
    lists.pop(op.list_id, None)


# ---------------------------------------------------------------------------
# Headers
# ---------------------------------------------------------------------------

_HEADER_SLOT_FIELD = {
    "DEFAULT": "defaultHeaderId",
    "FIRST_PAGE": "firstPageHeaderId",
    "EVEN_PAGE": "evenPageHeaderId",
}


def _apply_create_header(doc: dict[str, Any], op: Any) -> None:
    """Add a header to the tab."""
    dt = _find_doc_tab(doc, op.tab_id)
    if dt is None:
        return
    headers: dict[str, Any] = dt.setdefault("headers", {})
    headers[op.desired_header_id] = {"content": _to_dict(op.desired_content)}
    # Update documentStyle slot
    doc_style: dict[str, Any] = dt.setdefault("documentStyle", {})
    slot_field = _HEADER_SLOT_FIELD.get(op.section_slot)
    if slot_field:
        doc_style[slot_field] = op.desired_header_id


def _apply_delete_header(doc: dict[str, Any], op: Any) -> None:
    """Remove a header from the tab."""
    dt = _find_doc_tab(doc, op.tab_id)
    if dt is None:
        return
    headers: dict[str, Any] = dt.get("headers") or {}
    headers.pop(op.base_header_id, None)
    # Clear documentStyle slot
    doc_style: dict[str, Any] = dt.get("documentStyle") or {}
    slot_field = _HEADER_SLOT_FIELD.get(op.section_slot)
    if slot_field and doc_style.get(slot_field) == op.base_header_id:
        doc_style.pop(slot_field, None)


def _apply_update_header_content(doc: dict[str, Any], op: Any) -> None:
    """Apply ContentAlignment to a header's content list."""
    dt = _find_doc_tab(doc, op.tab_id)
    if dt is None:
        return
    headers: dict[str, Any] = dt.get("headers") or {}
    header = headers.get(op.header_id) or {}
    content: list[dict[str, Any]] = header.get("content") or []
    new_content = _apply_content_alignment(
        content, op.alignment, op.desired_content, op.base_content
    )
    header["content"] = new_content
    headers[op.header_id] = header


# ---------------------------------------------------------------------------
# Footers
# ---------------------------------------------------------------------------

_FOOTER_SLOT_FIELD = {
    "DEFAULT": "defaultFooterId",
    "FIRST_PAGE": "firstPageFooterId",
    "EVEN_PAGE": "evenPageFooterId",
}


def _apply_create_footer(doc: dict[str, Any], op: Any) -> None:
    """Add a footer to the tab."""
    dt = _find_doc_tab(doc, op.tab_id)
    if dt is None:
        return
    footers: dict[str, Any] = dt.setdefault("footers", {})
    footers[op.desired_footer_id] = {"content": _to_dict(op.desired_content)}
    doc_style: dict[str, Any] = dt.setdefault("documentStyle", {})
    slot_field = _FOOTER_SLOT_FIELD.get(op.section_slot)
    if slot_field:
        doc_style[slot_field] = op.desired_footer_id


def _apply_delete_footer(doc: dict[str, Any], op: Any) -> None:
    """Remove a footer from the tab."""
    dt = _find_doc_tab(doc, op.tab_id)
    if dt is None:
        return
    footers: dict[str, Any] = dt.get("footers") or {}
    footers.pop(op.base_footer_id, None)
    doc_style: dict[str, Any] = dt.get("documentStyle") or {}
    slot_field = _FOOTER_SLOT_FIELD.get(op.section_slot)
    if slot_field and doc_style.get(slot_field) == op.base_footer_id:
        doc_style.pop(slot_field, None)


def _apply_update_footer_content(doc: dict[str, Any], op: Any) -> None:
    """Apply ContentAlignment to a footer's content list."""
    dt = _find_doc_tab(doc, op.tab_id)
    if dt is None:
        return
    footers: dict[str, Any] = dt.get("footers") or {}
    footer = footers.get(op.footer_id) or {}
    content: list[dict[str, Any]] = footer.get("content") or []
    new_content = _apply_content_alignment(
        content, op.alignment, op.desired_content, op.base_content
    )
    footer["content"] = new_content
    footers[op.footer_id] = footer


# ---------------------------------------------------------------------------
# Footnotes
# ---------------------------------------------------------------------------


def _apply_insert_footnote(doc: dict[str, Any], op: Any) -> None:
    """Insert a footnote into the tab's footnotes dict."""
    dt = _find_doc_tab(doc, op.tab_id)
    if dt is None:
        return
    footnotes: dict[str, Any] = dt.setdefault("footnotes", {})
    footnotes[op.footnote_id] = {"content": _to_dict(op.desired_content)}


def _apply_delete_footnote(doc: dict[str, Any], op: Any) -> None:
    """Remove a footnote from the tab's footnotes dict."""
    dt = _find_doc_tab(doc, op.tab_id)
    if dt is None:
        return
    footnotes: dict[str, Any] = dt.get("footnotes") or {}
    footnotes.pop(op.footnote_id, None)


def _apply_update_footnote_content(doc: dict[str, Any], op: Any) -> None:
    """Apply ContentAlignment to a footnote's content list."""
    dt = _find_doc_tab(doc, op.tab_id)
    if dt is None:
        return
    footnotes: dict[str, Any] = dt.get("footnotes") or {}
    footnote = footnotes.get(op.footnote_id) or {}
    content: list[dict[str, Any]] = footnote.get("content") or []
    new_content = _apply_content_alignment(
        content, op.alignment, op.desired_content, op.base_content
    )
    footnote["content"] = new_content
    footnotes[op.footnote_id] = footnote


# ---------------------------------------------------------------------------
# Body content
# ---------------------------------------------------------------------------


def _apply_update_body_content(doc: dict[str, Any], op: Any) -> None:
    """Apply UpdateBodyContentOp to the appropriate content list.

    story_kind == "body" → documentTab.body.content
    Other story_kinds (header/footer/footnote/table_cell) are handled by
    their dedicated ops; table_cell recursion is handled via child_ops.
    """
    if op.story_kind != "body":
        # header/footer/footnote content updates come as dedicated ops;
        # table_cell updates come via child UpdateBodyContentOp with
        # story_kind="table_cell" — apply inline to the matched cell.
        if op.story_kind == "table_cell":
            _apply_table_cell_body_content(doc, op)
        return

    dt = _find_doc_tab(doc, op.tab_id)
    if dt is None:
        return
    body: dict[str, Any] = dt.setdefault("body", {})
    content: list[dict[str, Any]] = body.get("content") or []
    new_content = _apply_content_alignment(
        content, op.alignment, op.desired_content, op.base_content
    )
    body["content"] = new_content


def _apply_table_cell_body_content(doc: dict[str, Any], op: Any) -> None:
    """Apply a table_cell body content op.

    op.story_id is expected to be "r{row}:c{col}" identifying the cell within
    the matched table. We walk all tables in the doc tab to find the cell,
    then apply the alignment to cell.content.
    """
    # story_id for table cells is not reliably structured to locate the cell
    # directly in the base doc (it references desired coords, not base coords).
    # Apply desired_content directly to any matching cell by structure match.
    # This is best-effort: if the cell can't be found, skip.
    dt = _find_doc_tab(doc, op.tab_id)
    if dt is None:
        return
    body_content: list[dict[str, Any]] = (dt.get("body") or {}).get("content") or []
    _update_cell_in_content(body_content, op)


def _update_cell_in_content(content: list[dict[str, Any]], op: Any) -> bool:
    """Walk content recursively to find and update the matching table cell.

    Uses op.story_id (format "r{row}:c{col}") as a hint.
    Returns True if the cell was found and updated.
    """
    import re

    m = re.match(r"r(\d+):c(\d+)", op.story_id or "")
    if not m:
        return False
    row_idx = int(m.group(1))
    col_idx = int(m.group(2))

    for el in content:
        if "table" not in el:
            continue
        table = el["table"]
        rows: list[dict[str, Any]] = table.get("tableRows") or []
        if row_idx >= len(rows):
            continue
        row = rows[row_idx]
        cells: list[dict[str, Any]] = row.get("tableCells") or []
        if col_idx >= len(cells):
            continue
        cell = cells[col_idx]
        cell_content: list[dict[str, Any]] = cell.get("content") or []
        new_content = _apply_content_alignment(
            cell_content, op.alignment, op.desired_content, op.base_content
        )
        cell["content"] = new_content
        return True
    return False


# ---------------------------------------------------------------------------
# Table structural ops
# ---------------------------------------------------------------------------


def _find_table_in_doc(
    doc: dict[str, Any], tab_id: str, table_start_index: int
) -> dict[str, Any] | None:
    """Find a table element dict by tab_id and table_start_index.

    Returns the table dict (the value of the "table" key) or None.
    """
    dt = _find_doc_tab(doc, tab_id)
    if dt is None:
        return None
    body_content: list[dict[str, Any]] = (dt.get("body") or {}).get("content") or []
    for el in body_content:
        if "table" in el and el.get("startIndex") == table_start_index:
            result: dict[str, Any] = el["table"]
            return result
    # Fallback: find by position in list of tables if startIndex isn't set
    tables: list[dict[str, Any]] = [el["table"] for el in body_content if "table" in el]
    if tables:
        # Return the first table as a best-effort fallback
        return tables[0] if len(tables) == 1 else None
    return None


def _apply_table_structural_op(doc: dict[str, Any], op: Any) -> None:
    """Apply row/column insert or delete ops to the matching table."""
    from extradoc.diffmerge.model import (
        DeleteTableColumnOp,
        DeleteTableRowOp,
        InsertTableColumnOp,
        InsertTableRowOp,
    )

    table = _find_table_in_doc(doc, op.tab_id, op.table_start_index)
    if table is None:
        return

    rows: list[dict[str, Any]] = table.setdefault("tableRows", [])

    if isinstance(op, InsertTableRowOp):
        # Build a blank row with the right number of cells
        blank_row: dict[str, Any] = {
            "tableCells": [
                {
                    "content": [
                        {"paragraph": {"elements": [{"textRun": {"content": "\n"}}]}}
                    ]
                }
                for _ in range(op.column_count)
            ]
        }
        insert_at = op.row_index + (1 if op.insert_below else 0)
        rows.insert(insert_at, blank_row)

    elif isinstance(op, DeleteTableRowOp):
        if op.row_index < len(rows):
            del rows[op.row_index]

    elif isinstance(op, InsertTableColumnOp):
        for row in rows:
            cells: list[dict[str, Any]] = row.setdefault("tableCells", [])
            blank_cell: dict[str, Any] = {
                "content": [
                    {"paragraph": {"elements": [{"textRun": {"content": "\n"}}]}}
                ]
            }
            insert_at = op.column_index + (1 if op.insert_right else 0)
            cells.insert(insert_at, blank_cell)

    elif isinstance(op, DeleteTableColumnOp):
        for row in rows:
            cells = row.get("tableCells") or []
            if op.column_index < len(cells):
                del cells[op.column_index]


def _apply_table_style_op(doc: dict[str, Any], op: Any) -> None:
    """Apply cell style, row style, or column properties ops to the matching table."""
    from extradoc.diffmerge.model import (
        UpdateTableCellStyleOp,
        UpdateTableColumnPropertiesOp,
        UpdateTableRowStyleOp,
    )

    table = _find_table_in_doc(doc, op.tab_id, op.table_start_index)
    if table is None:
        return

    rows: list[dict[str, Any]] = table.get("tableRows") or []

    if isinstance(op, UpdateTableCellStyleOp):
        if op.row_index < len(rows):
            cells = rows[op.row_index].get("tableCells") or []
            if op.column_index < len(cells):
                cell = cells[op.column_index]
                cell_style: dict[str, Any] = cell.setdefault("tableCellStyle", {})
                cell_style.update(
                    op.desired_style.model_dump(by_alias=True, exclude_none=True)
                )

    elif isinstance(op, UpdateTableRowStyleOp):
        if op.row_index < len(rows):
            row = rows[op.row_index]
            row_style: dict[str, Any] = row.setdefault("tableRowStyle", {})
            if op.min_row_height is not None:
                row_style["minRowHeight"] = op.min_row_height

    elif isinstance(op, UpdateTableColumnPropertiesOp):
        table_style: dict[str, Any] = table.setdefault("tableStyle", {})
        col_props: list[dict[str, Any]] = table_style.setdefault(
            "tableColumnProperties", []
        )
        # Extend if needed
        while len(col_props) <= op.column_index:
            col_props.append({})
        col = col_props[op.column_index]
        if op.width is not None:
            col["width"] = op.width
        if op.width_type is not None:
            col["widthType"] = op.width_type


# ---------------------------------------------------------------------------
# Content alignment application
# ---------------------------------------------------------------------------


def _element_kind(el: dict[str, Any]) -> str:
    """Return the kind of a structural element dict."""
    if "paragraph" in el:
        return "paragraph"
    if "table" in el:
        return "table"
    if "sectionBreak" in el:
        return "section_break"
    if "tableOfContents" in el:
        return "toc"
    return "other"


def _se_kind(el: StructuralElement) -> str:
    """Return the kind of a typed StructuralElement."""
    if el.paragraph is not None:
        return "paragraph"
    if el.table is not None:
        return "table"
    if el.section_break is not None:
        return "section_break"
    if el.table_of_contents is not None:
        return "toc"
    return "other"


def _se_text(el: StructuralElement) -> str:
    """Extract concatenated text from a typed StructuralElement."""
    if el.paragraph is not None:
        return "".join(
            (e.text_run.content if e.text_run and e.text_run.content else "")
            for e in (el.paragraph.elements or [])
        )
    if el.table is not None:
        parts: list[str] = []
        for row in el.table.table_rows or []:
            for cell in row.table_cells or []:
                for cse in cell.content or []:
                    if cse.paragraph is not None:
                        parts.append(
                            "".join(
                                (
                                    e.text_run.content
                                    if e.text_run and e.text_run.content
                                    else ""
                                )
                                for e in (cse.paragraph.elements or [])
                            )
                        )
        return "".join(parts)
    return ""


def _se_elements_equal(a: StructuralElement, b: StructuralElement) -> bool:
    """Compare two typed StructuralElements for equality, ignoring indices.

    Both elements come from the same markdown parse pipeline, so we compare
    the full structure (text, formatting, heading level, bullet, etc.)
    to detect any user edit — not just text content changes.
    """
    a_dict = a.model_dump(by_alias=True, exclude_none=True)
    b_dict = b.model_dump(by_alias=True, exclude_none=True)
    # Strip indices since they differ between ancestor and mine
    _strip_indices_inplace(a_dict)
    _strip_indices_inplace(b_dict)
    return a_dict == b_dict


def _strip_indices_inplace(obj: Any) -> None:
    """Remove startIndex/endIndex from a nested dict/list structure in place."""
    if isinstance(obj, dict):
        obj.pop("startIndex", None)
        obj.pop("endIndex", None)
        for v in obj.values():
            _strip_indices_inplace(v)
    elif isinstance(obj, list):
        for item in obj:
            _strip_indices_inplace(item)


def _dict_text(el: dict[str, Any]) -> str:
    """Extract concatenated text from a structural element dict."""
    para = el.get("paragraph")
    if para is not None:
        return "".join(
            (pe.get("textRun") or {}).get("content", "")
            for pe in (para.get("elements") or [])
        )
    table = el.get("table")
    if table is not None:
        parts: list[str] = []
        for row in table.get("tableRows") or []:
            for cell in row.get("tableCells") or []:
                for cse in cell.get("content") or []:
                    cpara = cse.get("paragraph")
                    if cpara is not None:
                        parts.append(
                            "".join(
                                (pe.get("textRun") or {}).get("content", "")
                                for pe in (cpara.get("elements") or [])
                            )
                        )
        return "".join(parts)
    return ""


def _align_raw_to_ancestor(
    raw_content: list[dict[str, Any]],
    ancestor_content: list[StructuralElement],
) -> tuple[dict[int, int], dict[int, int]]:
    """Align raw API base content to ancestor content.

    The ancestor was produced by serialize(raw_base) → markdown → parse, so
    content-bearing elements (paragraphs with text, tables, headings) appear
    in the same order. The sequences may differ in empty/trivial elements
    (separator paragraphs, trailing newlines) which can cause confusion if
    matched purely by text.

    Strategy: first match content-bearing elements sequentially (they are in
    the same order), then match remaining trivial elements by proximity.

    Returns (raw_to_ancestor, ancestor_to_raw) index mappings.
    """
    if not raw_content or not ancestor_content:
        return {}, {}

    raw_to_anc: dict[int, int] = {}
    anc_to_raw: dict[int, int] = {}

    # Classify elements as "content-bearing" vs "trivial"
    def _is_content_bearing_dict(el: dict[str, Any]) -> bool:
        para = el.get("paragraph")
        if para is not None:
            elements = para.get("elements") or []
            text = "".join(
                (pe.get("textRun") or {}).get("content", "") for pe in elements
            ).strip()
            if len(text) > 0:
                return True
            # Check for non-text elements (HR, inline objects, footnote refs, etc.)
            for pe in elements:
                if any(
                    k in pe
                    for k in (
                        "horizontalRule",
                        "inlineObjectElement",
                        "footnoteReference",
                        "pageBreak",
                        "person",
                        "richLink",
                    )
                ):
                    return True
            return False
        return "table" in el or "tableOfContents" in el

    def _is_content_bearing_se(el: StructuralElement) -> bool:
        if el.paragraph is not None:
            text = _se_text(el).strip()
            if len(text) > 0:
                return True
            # Check for non-text elements
            for pe in el.paragraph.elements or []:
                if (
                    pe.horizontal_rule is not None
                    or pe.inline_object_element is not None
                    or pe.footnote_reference is not None
                    or pe.page_break is not None
                    or pe.person is not None
                    or pe.rich_link is not None
                ):
                    return True
            return False
        return el.table is not None or el.table_of_contents is not None

    # Phase 1: Match content-bearing elements sequentially
    raw_content_indices = [
        i for i in range(len(raw_content)) if _is_content_bearing_dict(raw_content[i])
    ]
    anc_content_indices = [
        i
        for i in range(len(ancestor_content))
        if _is_content_bearing_se(ancestor_content[i])
    ]

    # Also match section breaks (always first element)
    raw_sb = [i for i in range(len(raw_content)) if "sectionBreak" in raw_content[i]]
    anc_sb = [
        i
        for i in range(len(ancestor_content))
        if ancestor_content[i].section_break is not None
    ]
    for rs, as_ in zip(raw_sb, anc_sb, strict=False):
        raw_to_anc[rs] = as_
        anc_to_raw[as_] = rs

    # LCS-based matching for content-bearing elements.
    #
    # The greedy sequential approach breaks when the raw base has more
    # content-bearing elements than the ancestor (e.g. inline objects, HRs
    # that the markdown serializer drops). The extra raw elements consume
    # ancestor slots, shifting all subsequent mappings. An LCS DP finds the
    # longest common subsequence of matchable element pairs, which correctly
    # skips over extra raw elements without consuming ancestor slots.
    from extradoc.diffmerge.content_align import (
        MIN_PARA_MATCH_SIMILARITY,
        text_similarity,
    )

    R = raw_content_indices
    A = anc_content_indices
    nr = len(R)
    na = len(A)

    def _can_match_raw_anc(ri: int, ai: int) -> bool:
        """Return True if raw element ri and ancestor element ai can be matched."""
        raw_kind = _element_kind(raw_content[ri])
        anc_kind = _se_kind(ancestor_content[ai])
        if raw_kind != anc_kind:
            return False
        if raw_kind == "paragraph":
            raw_text = _dict_text(raw_content[ri]).strip()
            anc_text = _se_text(ancestor_content[ai]).strip()
            return text_similarity(raw_text, anc_text) >= MIN_PARA_MATCH_SIMILARITY
        if raw_kind == "table":
            raw_text = _dict_text(raw_content[ri])
            anc_text = _se_text(ancestor_content[ai])
            # Any non-zero text overlap, or both empty (structural match)
            return text_similarity(raw_text, anc_text) > 0.0 or (
                not raw_text.strip() and not anc_text.strip()
            )
        # sectionBreak, toc, other — same kind is sufficient
        return True

    # dp[i][j] = length of LCS of R[:i] and A[:j]
    # Use flat list-of-lists for O(nr*na) memory.
    dp = [[0] * (na + 1) for _ in range(nr + 1)]
    for i in range(1, nr + 1):
        for j in range(1, na + 1):
            if _can_match_raw_anc(R[i - 1], A[j - 1]):
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])

    # Backtrack to recover matched pairs (in reverse order, then reverse).
    lcs_pairs: list[tuple[int, int]] = []
    i, j = nr, na
    while i > 0 and j > 0:
        if _can_match_raw_anc(R[i - 1], A[j - 1]) and dp[i][j] == dp[i - 1][j - 1] + 1:
            lcs_pairs.append((R[i - 1], A[j - 1]))
            i -= 1
            j -= 1
        elif dp[i - 1][j] >= dp[i][j - 1]:
            i -= 1
        else:
            j -= 1
    lcs_pairs.reverse()

    for raw_idx, anc_idx in lcs_pairs:
        raw_to_anc[raw_idx] = anc_idx
        anc_to_raw[anc_idx] = raw_idx

    # Phase 2: Match remaining trivial elements, preserving monotonicity.
    #
    # Each unmatched ancestor index has a window of admissible raw indices
    # bounded by its neighbouring matched anchors (the previous and next
    # matched ancestor's raw indices). Within that window we pair by order,
    # which both preserves monotonicity of anc_to_raw and keeps elements
    # close to their neighbours.
    matched_anc = sorted(anc_to_raw.keys())
    for anc_idx in range(len(ancestor_content)):
        if anc_idx in anc_to_raw:
            continue
        # Find bounding matched ancestor indices.
        lo_raw = -1
        for a in matched_anc:
            if a < anc_idx:
                lo_raw = anc_to_raw[a]
            else:
                break
        hi_raw = len(raw_content)
        for a in matched_anc:
            if a > anc_idx:
                hi_raw = anc_to_raw[a]
                break
        # Candidate raw indices strictly between lo_raw and hi_raw that are
        # unmatched and kind-compatible.
        kind = _se_kind(ancestor_content[anc_idx])
        candidates = [
            r
            for r in range(lo_raw + 1, hi_raw)
            if r not in raw_to_anc and _element_kind(raw_content[r]) == kind
        ]
        if not candidates:
            continue
        # Pick the first candidate — this preserves order-in-window. For a
        # window with k unmatched ancestors and k candidates, successive
        # calls assign one each in order.
        chosen = candidates[0]
        raw_to_anc[chosen] = anc_idx
        anc_to_raw[anc_idx] = chosen
        # Keep matched_anc sorted.
        bisect.insort(matched_anc, anc_idx)

    return raw_to_anc, anc_to_raw


def _merge_changed_paragraph(
    raw_para: dict[str, Any],
    desired_el: StructuralElement,
    ancestor_el: StructuralElement | None = None,
) -> dict[str, Any]:
    """Merge a changed paragraph: base structure + desired text content.

    Preserves from raw base: paragraphStyle properties that markdown can't
    represent (direction, lineSpacing, headingId, indents, spacing, etc.),
    bullet properties, and any inline objects.

    Takes from desired: text run content and markdown-representable formatting
    (bold, italic, strikethrough, underline, link, namedStyleType, monospace font).

    ancestor_el: the original parsed ancestor element (before user edits).
    When provided, namedStyleType is only propagated from desired if the user
    actually changed it (i.e. desired differs from ancestor). If the user left
    namedStyleType unchanged, we keep the raw base's namedStyleType — which may
    differ from the parsed ancestor value because the serde round-trip normalises
    some style names (e.g. TITLE → HEADING_1).
    """
    result = copy.deepcopy(raw_para)
    d_para = desired_el.paragraph
    if d_para is None:
        return result

    para = result["paragraph"]

    # Merge paragraphStyle: keep base, overlay only what markdown represents.
    # For namedStyleType: only propagate the desired value if the user actually
    # changed it relative to the ancestor. If ancestor and desired have the same
    # namedStyleType, the user didn't change the heading level — keep the raw
    # base's namedStyleType (which may differ from the parsed ancestor because
    # the serde normalises some style names, e.g. TITLE → HEADING_1).
    base_ps = para.get("paragraphStyle") or {}
    d_ps = d_para.paragraph_style
    if d_ps is not None and d_ps.named_style_type is not None:
        anc_named_style_type = None
        if ancestor_el is not None and ancestor_el.paragraph is not None:
            anc_ps = ancestor_el.paragraph.paragraph_style
            if anc_ps is not None:
                anc_named_style_type = anc_ps.named_style_type
        # Only apply desired namedStyleType if user changed it from the ancestor
        if (
            anc_named_style_type is None
            or d_ps.named_style_type != anc_named_style_type
        ):
            base_ps["namedStyleType"] = str(d_ps.named_style_type)
    para["paragraphStyle"] = base_ps

    # Merge bullet: if desired has a bullet, merge with base's bullet
    # (preserve textStyle from base, take listId/nestingLevel from desired);
    # if desired has no bullet, remove it.
    if d_para.bullet is not None:
        bullet_d = d_para.bullet.model_dump(by_alias=True, exclude_none=True)
        base_bullet = para.get("bullet") or {}
        # Preserve textStyle from base bullet (markdown can't represent it)
        if "textStyle" in base_bullet and "textStyle" not in bullet_d:
            bullet_d["textStyle"] = base_bullet["textStyle"]
        para["bullet"] = bullet_d
    else:
        para.pop("bullet", None)

    # Replace text runs with desired's runs, but carry over non-representable
    # text styles from the base where runs align by position.
    base_elements = para.get("elements") or []
    desired_elements = d_para.elements or []

    # Build a map of base run styles keyed by their text content position
    # so we can carry over styles like foregroundColor, backgroundColor, font, fontSize.
    base_style_by_offset: list[tuple[int, int, dict[str, Any]]] = []
    offset = 0
    for be in base_elements:
        tr = be.get("textRun")
        if tr:
            content = tr.get("content", "")
            ts = tr.get("textStyle") or {}
            base_style_by_offset.append((offset, offset + len(content), ts))
            offset += len(content)
        else:
            # Inline object or other non-text element — track position
            offset += 1

    # Compute per-desired-run base offset adjustments.
    #
    # When text was edited (e.g. a word replaced), the character offsets of
    # desired runs AFTER the edit are shifted relative to the base offsets.
    # We use the ancestor text (before user edits) to compute how much each
    # desired run's offset should be adjusted when looking up the base style.
    #
    # The ancestor is the version the user started editing from.  By comparing
    # the ancestor text to the desired text we find the cumulative delta
    # (base_chars - desired_chars) at the start of each desired run.
    anc_text = _se_text(ancestor_el) if ancestor_el is not None else ""
    desired_run_offsets: list[tuple[int, int]] = []  # (d_offset, base_lookup_offset)
    offset_info: dict[str, Any] = {"delta": 0, "prefix_len": 0, "des_edit_end": 0}
    if anc_text:
        _offs_result = _compute_base_offsets_for_desired_runs(
            anc_text, desired_elements
        )
        desired_run_offsets = _offs_result[0]
        offset_info = _offs_result[1]

    new_elements: list[dict[str, Any]] = []
    d_offset = 0
    for d_i, de in enumerate(desired_elements):
        de_dict = de.model_dump(by_alias=True, exclude_none=True)
        if de.text_run and de.text_run.content:
            d_content = de.text_run.content
            d_len = len(d_content)
            d_ts = (de_dict.get("textRun") or {}).get("textStyle") or {}

            # Determine base offset range for this desired run
            if d_i < len(desired_run_offsets):
                b_start = desired_run_offsets[d_i][1]
            else:
                b_start = d_offset
            # Compute b_end using the base offset of the start of the NEXT run,
            # or if this is the last run, use the total base text length.
            if d_i + 1 < len(desired_run_offsets):
                b_end = desired_run_offsets[d_i + 1][1]
            else:
                b_end = (
                    base_style_by_offset[-1][1]
                    if base_style_by_offset
                    else b_start + d_len
                )

            # Find base run boundaries within [b_start, b_end].
            # Split the desired run at those boundaries so each sub-segment gets
            # the correct base non-representable style.
            split_points = _find_base_splits_in_range(
                base_style_by_offset, b_start, b_end
            )

            if len(split_points) <= 1:
                # Single base run covers this desired run — simple case
                best_base_ts = _find_base_style_at(base_style_by_offset, b_start)
                if best_base_ts:
                    merged_ts = _merge_text_styles(best_base_ts, d_ts)
                    de_dict.setdefault("textRun", {})["textStyle"] = merged_ts
                new_elements.append(de_dict)
            else:
                # Multiple base runs — split desired run at base run boundaries.
                # Convert each base split point to a desired-text position using
                # the delta information from offset_info.
                oi_delta: int = offset_info.get("delta", 0)
                oi_prefix: int = offset_info.get("prefix_len", 0)
                oi_des_edit_end: int = offset_info.get("des_edit_end", 0)
                # base edit region end in base coords
                oi_base_edit_end: int = (
                    oi_prefix + oi_delta + (oi_des_edit_end - oi_prefix)
                    if oi_delta
                    else 0
                )

                def _b_to_d_offset(
                    b_pos: int,
                    run_b_start: int,
                    run_d_start: int,
                    run_d_len: int,
                    delta: int,
                    prefix: int,
                    des_edit_end: int,
                    base_edit_end: int,
                ) -> int:
                    """Convert a base split position to an offset within the desired run."""
                    if delta == 0:
                        return b_pos - run_b_start
                    if b_pos <= prefix:
                        abs_d = b_pos
                    elif b_pos >= base_edit_end:
                        abs_d = b_pos - delta
                    else:
                        abs_d = des_edit_end
                    return max(0, min(run_d_len, abs_d - run_d_start))

                seg_start_d = 0  # offset within desired run
                seg_start_b = b_start
                for sp_b in split_points[1:]:  # each split point in base coords
                    sp_d = _b_to_d_offset(
                        sp_b,
                        b_start,
                        d_offset,
                        d_len,
                        oi_delta,
                        oi_prefix,
                        oi_des_edit_end,
                        oi_base_edit_end,
                    )
                    sp_d = max(seg_start_d, min(d_len, sp_d))
                    seg_text = d_content[seg_start_d:sp_d]
                    if seg_text:
                        seg_base_ts = (
                            _find_base_style_at(base_style_by_offset, seg_start_b) or {}
                        )
                        seg_merged_ts = _merge_text_styles(seg_base_ts, d_ts)
                        new_elements.append(
                            {
                                "textRun": {
                                    "content": seg_text,
                                    "textStyle": seg_merged_ts,
                                }
                            }
                        )
                    seg_start_d = sp_d
                    seg_start_b = sp_b
                # Last segment
                seg_text = d_content[seg_start_d:]
                if seg_text:
                    seg_base_ts = (
                        _find_base_style_at(base_style_by_offset, seg_start_b) or {}
                    )
                    seg_merged_ts = _merge_text_styles(seg_base_ts, d_ts)
                    new_elements.append(
                        {
                            "textRun": {
                                "content": seg_text,
                                "textStyle": seg_merged_ts,
                            }
                        }
                    )
            d_offset += d_len
        elif de.inline_object_element or de.footnote_reference:
            d_offset += 1
            new_elements.append(de_dict)
            continue
        else:
            new_elements.append(de_dict)

    # Preserve inline objects from base that desired doesn't have
    # (images, footnote refs, etc. that markdown can't represent)
    base_inline_objects = [
        be
        for be in base_elements
        if "inlineObjectElement" in be
        or "footnoteReference" in be
        or "person" in be
        or "richLink" in be
        or "autoText" in be
    ]
    # Insert base inline objects at their original relative positions
    # Only if desired has no inline objects at all (markdown dropped them)
    desired_has_inlines = any(
        de.inline_object_element is not None or de.footnote_reference is not None
        for de in desired_elements
    )
    if not desired_has_inlines and base_inline_objects:
        # Find where inline objects were in the base element list
        for be in base_elements:
            if "inlineObjectElement" in be or "footnoteReference" in be:
                # Insert before the trailing \n run
                insert_pos = max(0, len(new_elements) - 1)
                new_elements.insert(insert_pos, copy.deepcopy(be))

    # Preserve trailing whitespace (before the final \n) from the base paragraph.
    # Markdown round-trips strip trailing spaces, so the desired runs won't have
    # them.  Without this, every edited paragraph with trailing whitespace in the
    # original doc would produce a spurious deleteContentRange request.
    _restore_trailing_whitespace(new_elements, base_elements)

    para["elements"] = new_elements
    return result


def _restore_trailing_whitespace(
    new_elements: list[dict[str, Any]],
    base_elements: list[dict[str, Any]],
) -> None:
    """Re-add trailing whitespace (before \\n) that markdown round-trips strip.

    Modifies *new_elements* in place.  Compares the base paragraph's trailing
    whitespace (the spaces/tabs between the last visible character and the
    paragraph-ending ``\\n``) with what the desired elements have, and appends
    the missing whitespace to the last non-newline text run.
    """
    # Extract trailing whitespace from base
    base_text = ""
    for be in base_elements:
        tr = be.get("textRun")
        if tr:
            base_text += tr.get("content", "")
    if base_text.endswith("\n"):
        base_before_nl = base_text[:-1]
    else:
        return
    base_trailing_ws = base_before_nl[len(base_before_nl.rstrip()) :]
    if not base_trailing_ws:
        return

    # Extract trailing whitespace from desired
    des_text = ""
    for ne in new_elements:
        tr = ne.get("textRun")
        if tr:
            des_text += tr.get("content", "")
    if des_text.endswith("\n"):
        des_before_nl = des_text[:-1]
    else:
        return
    des_trailing_ws = des_before_nl[len(des_before_nl.rstrip()) :]
    if des_trailing_ws:
        return  # desired already has trailing whitespace

    # Find the last non-newline text run and append the base trailing whitespace
    for i in range(len(new_elements) - 1, -1, -1):
        tr = new_elements[i].get("textRun")
        if tr and tr.get("content", "") != "\n":
            tr["content"] = tr["content"] + base_trailing_ws
            break


def _find_base_splits_in_range(
    base_style_by_offset: list[tuple[int, int, dict[str, Any]]],
    b_start: int,
    b_end: int,
) -> list[int]:
    """Return the list of base run start offsets that fall within [b_start, b_end).

    The first element is always b_start (or the start of the base run containing
    b_start).  Subsequent elements are the starts of base runs that begin within
    [b_start, b_end).

    Returns a list of at least 1 element (just [b_start] if covered by one run).
    """
    splits: list[int] = [b_start]
    for run_start, _run_end, _ in base_style_by_offset:
        if run_start > b_start and run_start < b_end:
            splits.append(run_start)
    return splits


def _compute_base_offsets_for_desired_runs(
    anc_text: str,
    desired_elements: list[Any],  # list[ParagraphElement]
) -> tuple[list[tuple[int, int]], dict[str, Any]]:
    """Compute (desired_offset, base_offset) pairs for the start of each desired run.

    Uses the ancestor text to identify the common prefix and suffix.  Text
    before the first edit point has the same base and desired offsets.  Text
    after the edit has a shifted desired offset (base_offset = desired_offset +
    delta, where delta = len(anc_edit) - len(desired_edit)).

    Returns one entry per desired element.  For non-text-run elements the
    offsets track position but are less meaningful.

    This allows offset-based base style lookup to remain accurate even when a
    word in the middle of a paragraph was replaced with a word of different
    length.
    """
    # Concatenate all desired run texts
    desired_runs_text: list[str] = []
    for de in desired_elements:
        if de.text_run and de.text_run.content:
            desired_runs_text.append(de.text_run.content)
        else:
            desired_runs_text.append("")
    desired_text = "".join(desired_runs_text)

    n_anc = len(anc_text)
    n_des = len(desired_text)

    # Common prefix length
    prefix_len = 0
    while (
        prefix_len < n_anc
        and prefix_len < n_des
        and anc_text[prefix_len] == desired_text[prefix_len]
    ):
        prefix_len += 1

    # Common suffix length (don't overlap with prefix)
    suffix_len = 0
    while (
        suffix_len < n_anc - prefix_len
        and suffix_len < n_des - prefix_len
        and anc_text[n_anc - 1 - suffix_len] == desired_text[n_des - 1 - suffix_len]
    ):
        suffix_len += 1

    # Delta: positive means base is longer (desired chars are shifted left relative to base)
    anc_edit_len = n_anc - prefix_len - suffix_len
    des_edit_len = n_des - prefix_len - suffix_len
    delta = (
        anc_edit_len - des_edit_len
    )  # base_offset = desired_offset + delta (for positions after edit)
    # Edit region in desired: [prefix_len, prefix_len + des_edit_len)
    des_edit_end = prefix_len + des_edit_len

    def _d_to_b(d_pos: int) -> int:
        """Convert a desired-text position to a base-text position."""
        if d_pos <= prefix_len:
            return d_pos
        elif d_pos >= des_edit_end:
            return d_pos + delta
        else:
            # Inside the edit region — map to the start of the base edit
            return prefix_len

    result: list[tuple[int, int]] = []
    d_offset = 0
    for run_text in desired_runs_text:
        d_run_start = d_offset
        base_offset = _d_to_b(d_run_start)
        result.append((d_run_start, base_offset))
        d_offset += len(run_text)

    # Also return info needed to convert base split points back to desired positions
    info: dict[str, Any] = {
        "delta": delta,
        "prefix_len": prefix_len,
        "des_edit_end": des_edit_end,
    }
    return result, info


def _find_base_style_at(
    base_styles: list[tuple[int, int, dict[str, Any]]], offset: int
) -> dict[str, Any] | None:
    """Find the base text style that covers the given character offset."""
    for start, end, ts in base_styles:
        if start <= offset < end:
            return ts
    # If offset is past all base styles, use the last one
    if base_styles:
        return base_styles[-1][2]
    return None


# Text style fields that markdown CAN represent — these come from desired
_MD_REPRESENTABLE_STYLE_FIELDS = {
    "bold",
    "italic",
    "strikethrough",
    "underline",
    "link",
    # Monospace font is representable via backticks
    "weightedFontFamily",
    "fontSize",
}

# Text style fields that markdown CANNOT represent — these come from base
_MD_NON_REPRESENTABLE_STYLE_FIELDS = {
    "foregroundColor",
    "backgroundColor",
    "baselineOffset",
    "smallCaps",
}


def _merge_text_styles(
    base_ts: dict[str, Any], desired_ts: dict[str, Any]
) -> dict[str, Any]:
    """Merge base and desired text styles.

    Desired wins for markdown-representable fields.
    Base wins for non-representable fields (colors, fonts not from markdown).
    """
    merged = copy.deepcopy(base_ts)

    # Apply all desired fields (markdown-representable ones take precedence)
    for key in _MD_REPRESENTABLE_STYLE_FIELDS:
        if key in desired_ts:
            merged[key] = copy.deepcopy(desired_ts[key])
        elif (
            key in merged
            and key not in desired_ts
            and key in ("bold", "italic", "strikethrough", "underline")
            and merged[key]  # Only pop if currently True; leave explicit False alone
        ):
            merged.pop(key, None)

    # If desired has a link, also carry link-related styles from desired
    if "link" in desired_ts:
        # Links in the base may have foregroundColor (blue) and underline
        # These are implicit link styles — keep them from base
        pass
    elif "link" not in desired_ts and "link" in merged:
        # Base had a link but desired doesn't — remove link
        merged.pop("link", None)

    return merged


def _merge_changed_table(
    raw_table_el: dict[str, Any],
    desired_el: StructuralElement,
    ancestor_el: StructuralElement | None = None,
) -> dict[str, Any]:
    """Merge a changed table: preserve base structure, update cell text.

    For cells at matching positions: preserve tableCellStyle and paragraph
    styles from base, update text content from desired.
    If row/column count changed, fall back to desired for structural changes.
    """
    result = copy.deepcopy(raw_table_el)
    d_table = desired_el.table
    if d_table is None:
        return result

    raw_table = result["table"]
    raw_rows = raw_table.get("tableRows") or []
    d_rows = d_table.table_rows or []

    a_table = ancestor_el.table if ancestor_el is not None else None
    a_rows = a_table.table_rows or [] if a_table is not None else []

    # Merge overlapping rows; append/trim for structural changes.
    # This preserves tableStyle, tableCellStyle, and paragraph styles on
    # existing cells even when rows or columns are added/removed.
    common_rows = min(len(raw_rows), len(d_rows))
    for row_i in range(common_rows):
        raw_row = raw_rows[row_i]
        d_row = d_rows[row_i]
        a_row = a_rows[row_i] if row_i < len(a_rows) else None
        _merge_table_row(raw_row, d_row, a_row)

    if len(d_rows) > len(raw_rows):
        # New rows added — append from desired
        for d_row in d_rows[len(raw_rows) :]:
            raw_rows.append(d_row.model_dump(by_alias=True, exclude_none=True))
        raw_table["rows"] = len(d_rows)
    elif len(d_rows) < len(raw_rows):
        # Rows removed
        del raw_rows[len(d_rows) :]
        raw_table["rows"] = len(d_rows)

    return result


def _merge_table_row(
    raw_row: dict[str, Any], d_row: Any, a_row: Any | None = None
) -> None:
    """Merge a single table row: preserve base cell styles, update content."""
    raw_cells = raw_row.get("tableCells") or []
    d_cells = d_row.table_cells or []
    a_cells = (a_row.table_cells or []) if a_row is not None else []

    common_cols = min(len(raw_cells), len(d_cells))
    for col_i in range(common_cols):
        a_cell = a_cells[col_i] if col_i < len(a_cells) else None
        _merge_table_cell(raw_cells[col_i], d_cells[col_i], a_cell)

    if len(d_cells) > len(raw_cells):
        # New columns added — append from desired
        for d_cell in d_cells[len(raw_cells) :]:
            raw_cells.append(d_cell.model_dump(by_alias=True, exclude_none=True))
    elif len(d_cells) < len(raw_cells):
        # Columns removed
        del raw_cells[len(d_cells) :]

    raw_row["tableCells"] = raw_cells


def _merge_table_cell(
    raw_cell: dict[str, Any], d_cell: Any, a_cell: Any | None = None
) -> None:
    """Merge a single table cell: preserve tableCellStyle, update content."""
    raw_cell_content = raw_cell.get("content") or []
    d_cell_content = d_cell.content or []

    # Short-circuit: if the ancestor (pristine) and desired (current) cells
    # are semantically equal, the user did not edit this cell. Any structural
    # difference between base and desired is purely round-trip flattening (e.g.
    # HTML <td> collapsing N paragraphs into 1). Preserve raw base unchanged so
    # the reconciler emits no requests for this cell.
    #
    # We compare the full Pydantic model dump rather than just flattened text,
    # so edits that only change styles (bold/italic/link) are NOT short-circuited.
    if a_cell is not None:
        try:
            a_dump = a_cell.model_dump(by_alias=True, exclude_none=True)
            d_dump = d_cell.model_dump(by_alias=True, exclude_none=True)
        except AttributeError:
            a_dump = None
            d_dump = None
        if a_dump is not None and a_dump == d_dump:
            return

    # Merge paragraphs at matching positions
    common_paras = min(len(raw_cell_content), len(d_cell_content))
    for para_i in range(common_paras):
        raw_cse = raw_cell_content[para_i]
        d_cse = d_cell_content[para_i]
        if "paragraph" in raw_cse and d_cse.paragraph is not None:
            merged = _merge_changed_paragraph(
                {"paragraph": raw_cse["paragraph"]}, d_cse
            )
            raw_cse["paragraph"] = merged["paragraph"]

    if len(d_cell_content) > len(raw_cell_content):
        # New paragraphs added — append from desired
        for d_cse in d_cell_content[len(raw_cell_content) :]:
            raw_cell_content.append(d_cse.model_dump(by_alias=True, exclude_none=True))
    elif len(d_cell_content) < len(raw_cell_content):
        # The desired content has fewer paragraphs than the raw base cell.
        # This is almost always because the editable format (e.g. GFM
        # markdown tables) only models a single paragraph per cell, while
        # Google Docs cells may contain trailing empty paragraphs carrying
        # border/padding style.  Dropping those trailing paragraphs causes
        # the reconciler to emit cascading delete+insert ops across cells,
        # which fail with stale index errors on the real API.  Preserve the
        # trailing raw paragraphs unchanged.
        pass

    raw_cell["content"] = raw_cell_content


def _merge_changed_element(
    raw_base: dict[str, Any],
    desired_el: StructuralElement,
    ancestor_el: StructuralElement | None = None,
) -> dict[str, Any]:
    """Merge a changed element: start from raw base, apply text-level changes.

    Dispatches to type-specific merge functions.
    """
    kind = _element_kind(raw_base)
    if kind == "paragraph":
        return _merge_changed_paragraph(raw_base, desired_el, ancestor_el)
    if kind == "table":
        return _merge_changed_table(raw_base, desired_el, ancestor_el)
    # For other types (section_break, toc, etc.), use base as-is
    return copy.deepcopy(raw_base)


def _apply_content_alignment(
    raw_base_content: list[dict[str, Any]],
    alignment: ContentAlignment,
    desired_content: list[StructuralElement],
    ancestor_content: list[StructuralElement] | None = None,
) -> list[dict[str, Any]]:
    """Apply a ContentAlignment to a base content list.

    Uses the alignment (computed between ancestor and mine) to determine
    which elements changed, and merges changes into the raw API base
    while preserving properties that markdown can't represent.

    For unchanged matched elements: uses the raw base element as-is.
    For changed matched elements: merges text changes into the raw base.
    For inserts: uses the desired element directly.
    For deletes: omits the base element.
    """
    # Fallback: if no ancestor provided, use old behavior
    if ancestor_content is None:
        return [
            copy.deepcopy(
                d_el
                if isinstance(d_el, dict)
                else d_el.model_dump(by_alias=True, exclude_none=True)
            )
            for d_el in desired_content
        ]

    # Step 1: Align raw base to ancestor by sequential kind matching
    raw_to_anc, anc_to_raw = _align_raw_to_ancestor(raw_base_content, ancestor_content)

    # Step 2: Build lookup from alignment (ancestor ↔ mine)
    desired_insert_set = set(alignment.desired_inserts)
    desired_to_ancestor: dict[int, int] = {}
    for m in alignment.matches:
        desired_to_ancestor[m.desired_idx] = m.base_idx  # base_idx is ancestor idx

    # Step 3: Build output by iterating desired content in order, while also
    # carrying through any raw_base elements that have no ancestor counterpart
    # (the serde promise: preserve anything the format can't represent).
    #
    # Unmatched raw elements are emitted at their original relative position:
    # immediately before the reconciled element for the next raw element that
    # IS matched to ancestor (and thus has a place in the desired output).
    result: list[dict[str, Any]] = []
    last_emitted_r_idx = -1

    def _emit_unmatched_raw_up_to(r_stop: int) -> None:
        """Emit raw_base elements with no ancestor counterpart in (last_emitted_r_idx, r_stop)."""
        nonlocal last_emitted_r_idx
        for r in range(last_emitted_r_idx + 1, r_stop):
            if r not in raw_to_anc:
                result.append(copy.deepcopy(raw_base_content[r]))
                last_emitted_r_idx = r

    for d_idx in range(len(desired_content)):
        d_el = desired_content[d_idx]

        if d_idx in desired_insert_set:
            # Pure insert — no base element to merge with.
            # Do NOT flush unmatched raw elements here: they should stick to
            # their original raw neighbours, not to newly inserted content.
            result.append(d_el.model_dump(by_alias=True, exclude_none=True))
            continue

        # This is a matched element
        a_idx = desired_to_ancestor.get(d_idx)
        if a_idx is None:
            # Shouldn't happen, but safety fallback
            result.append(d_el.model_dump(by_alias=True, exclude_none=True))
            continue

        r_idx = anc_to_raw.get(a_idx)
        if r_idx is None:
            # No raw base counterpart: the ancestor element was synthetic
            # (e.g. a trailing "\n" paragraph added by the markdown parser
            # because every segment must end with a paragraph). If the
            # element is unchanged vs ancestor, drop it — raw base doesn't
            # have it and shouldn't gain it. If the user changed it, keep
            # the desired element.
            ancestor_el = ancestor_content[a_idx]
            if not _se_elements_equal(ancestor_el, d_el):
                result.append(d_el.model_dump(by_alias=True, exclude_none=True))
            continue

        # Before emitting this matched raw element, emit any unmatched raw
        # elements that sit between the last-emitted raw index and this one.
        _emit_unmatched_raw_up_to(r_idx)

        # Check if the element actually changed (compare full structure, not just text)
        ancestor_el = ancestor_content[a_idx]
        if _se_elements_equal(ancestor_el, d_el):
            # Element is unchanged — use raw base as-is (preserves all rich formatting)
            result.append(copy.deepcopy(raw_base_content[r_idx]))
        else:
            # Element changed — merge text changes into raw base
            result.append(
                _merge_changed_element(raw_base_content[r_idx], d_el, ancestor_el)
            )
        last_emitted_r_idx = r_idx

    # Tail: any unmatched raw elements after the last matched one.
    _emit_unmatched_raw_up_to(len(raw_base_content))

    return result
