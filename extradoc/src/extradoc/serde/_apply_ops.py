"""Apply ReconcileOps in-memory to a base document dict.

This module supports the 3-way merge deserialize workflow:
    ancestor  = parse(pristine)
    mine      = parse(current folder)
    ops       = reconcile_v3.diff(ancestor, mine)
    desired   = apply_ops_to_document(base, ops)

The function works entirely on raw dicts (not Pydantic models).
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from extradoc.reconcile_v3.model import ReconcileOp


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
    from extradoc.reconcile_v3.model import (
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

    for op in ops:
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
    desired_tab = copy.deepcopy(op.desired_tab)
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
    """Merge changed_fields into the matching tab's documentStyle."""
    dt = _find_doc_tab(doc, op.tab_id)
    if dt is None:
        return
    doc_style: dict[str, Any] = dt.setdefault("documentStyle", {})
    doc_style.update(op.changed_fields)


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
    from extradoc.reconcile_v3.model import UpdateNamedStyleOp

    if isinstance(op, UpdateNamedStyleOp):
        desired_style = op.desired_style
    else:
        desired_style = op.desired_style  # InsertNamedStyleOp

    style_type = op.named_style_type
    for i, s in enumerate(styles):
        if s.get("namedStyleType") == style_type:
            styles[i] = copy.deepcopy(desired_style)
            return
    styles.append(copy.deepcopy(desired_style))


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
    lists[op.list_id] = copy.deepcopy(op.list_def)


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
    headers[op.desired_header_id] = {"content": copy.deepcopy(op.desired_content)}
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
    new_content = _apply_content_alignment(content, op.alignment, op.desired_content)
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
    footers[op.desired_footer_id] = {"content": copy.deepcopy(op.desired_content)}
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
    new_content = _apply_content_alignment(content, op.alignment, op.desired_content)
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
    footnotes[op.footnote_id] = {"content": copy.deepcopy(op.desired_content)}


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
    new_content = _apply_content_alignment(content, op.alignment, op.desired_content)
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
    new_content = _apply_content_alignment(content, op.alignment, op.desired_content)
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
            cell_content, op.alignment, op.desired_content
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
    from extradoc.reconcile_v3.model import (
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
    from extradoc.reconcile_v3.model import (
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
                cell_style.update(op.style_changes)

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


def _apply_content_alignment(
    _base_content: list[dict[str, Any]],
    _alignment: Any,  # ContentAlignment — unused; desired_content already encodes the target
    desired_content: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Apply a ContentAlignment to a base content list.

    Produces the merged content list by:
    - Keeping matched pairs (updating base element with desired element)
    - Removing deleted base elements
    - Inserting desired elements at the right positions

    This works on raw dict lists (not Pydantic models). The result preserves
    base elements where matched and inserts/removes as directed by the
    alignment.

    The base content is unused because the 3-way merge algorithm applies
    desired elements directly (matched or inserted). Deleted base elements
    are implicitly excluded by not appearing in the desired sequence.
    """
    # The desired_content encodes the full target state: matched elements
    # (edits of base elements) plus pure inserts. We walk it in order and
    # copy each element to the result. Deleted base elements are absent from
    # desired_content and are thus dropped automatically.
    #
    # The alignment object tells us which desired positions are pure inserts
    # vs matches, but we don't need to distinguish them here — both kinds
    # land in the result as the desired element.
    return [copy.deepcopy(d_el) for d_el in desired_content]
