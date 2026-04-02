"""Top-down tree diff for reconcile_v3.

Traverses the document tree in a deliberate top-down order, anchoring at
stable IDs wherever the Google Docs API provides them:

  Document
    └── Tab            (matched by tabId; positional fallback)
          ├── DocumentStyle   (singular — diff in place, or raise Unsupported)
          ├── NamedStyles     (matched by namedStyleType enum)
          ├── Lists           (matched by listId — add/delete only)
          ├── InlineObjects   (matched by inlineObjectId — raise Unsupported if changed)
          ├── Headers         (matched by headerId inside section)
          ├── Footers         (matched by footerId inside section)
          ├── Footnotes       (matched by footnoteId)
          └── Body content    (ContentAlignment DP)
                └── TableCell (recursive ContentAlignment DP)

No live API calls.  All computation is pure in-memory over raw dicts.
"""

from __future__ import annotations

from typing import Any

from extradoc.reconcile_v3.content_align import (
    ContentAlignment,
    ContentNode,
    align_content,
    content_node_from_raw,
)
from extradoc.reconcile_v3.model import (
    CreateFooterOp,
    CreateHeaderOp,
    DeleteFooterOp,
    DeleteFootnoteOp,
    DeleteHeaderOp,
    DeleteListOp,
    DeleteNamedStyleOp,
    DeleteTabOp,
    InsertFootnoteOp,
    InsertListOp,
    InsertNamedStyleOp,
    InsertTabOp,
    ReconcileOp,
    UpdateBodyContentOp,
    UpdateDocumentStyleOp,
    UpdateFooterContentOp,
    UpdateFootnoteContentOp,
    UpdateHeaderContentOp,
    UpdateInlineObjectOp,
    UpdateListOp,
    UpdateNamedStyleOp,
)

# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def diff_documents(
    base: dict[str, Any],
    desired: dict[str, Any],
) -> list[ReconcileOp]:
    """Return the full op list to transform base → desired.

    Parameters
    ----------
    base:
        Raw Google Docs API document dict (as returned by documents.get).
    desired:
        The desired target document dict.

    Returns
    -------
    list[ReconcileOp]
        Ordered list of ops covering every detected difference, top-down.
    """
    ops: list[ReconcileOp] = []

    base_tabs = _get_tabs(base)
    desired_tabs = _get_tabs(desired)

    # Match tabs and emit tab-level structural ops
    tab_pairs, tab_ops = _match_tabs(base_tabs, desired_tabs)
    ops.extend(tab_ops)

    # Recurse into matched tab pairs
    for base_tab, desired_tab in tab_pairs:
        ops.extend(_diff_tab(base_tab, desired_tab))

    return ops


# ---------------------------------------------------------------------------
# Tab helpers
# ---------------------------------------------------------------------------


def _get_tabs(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the tabs list from a document dict.

    For legacy single-tab documents (no ``tabs`` field), synthesises a single
    pseudo-tab dict wrapping the top-level body/headers/etc. fields.
    """
    tabs = doc.get("tabs")
    if tabs:
        return list(tabs)
    # Legacy document: wrap top-level content as a pseudo-tab
    pseudo_tab: dict[str, Any] = {
        "tabProperties": {"tabId": "", "title": "Tab 1", "index": 0},
        "documentTab": {
            "body": doc.get("body", {"content": []}),
            "headers": doc.get("headers", {}),
            "footers": doc.get("footers", {}),
            "footnotes": doc.get("footnotes", {}),
            "lists": doc.get("lists", {}),
            "namedStyles": doc.get("namedStyles", {"styles": []}),
            "documentStyle": doc.get("documentStyle", {}),
            "inlineObjects": doc.get("inlineObjects", {}),
        },
    }
    return [pseudo_tab]


def _tab_id(tab: dict[str, Any]) -> str:
    """Extract tabId from a tab dict (empty string for legacy pseudo-tabs)."""
    props: dict[str, Any] = tab.get("tabProperties") or {}
    return str(props.get("tabId", ""))


def _doc_tab(tab: dict[str, Any]) -> dict[str, Any]:
    """Return the documentTab portion of a tab dict."""
    result: dict[str, Any] = tab.get("documentTab") or {}
    return result


def _match_tabs(
    base_tabs: list[dict[str, Any]],
    desired_tabs: list[dict[str, Any]],
) -> tuple[list[tuple[dict[str, Any], dict[str, Any]]], list[ReconcileOp]]:
    """Match base tabs to desired tabs by tabId, with positional fallback.

    Returns
    -------
    pairs:
        Matched (base_tab, desired_tab) pairs.
    ops:
        InsertTabOp and DeleteTabOp for unmatched tabs.
    """
    ops: list[ReconcileOp] = []
    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []

    # Build lookup by tabId (skip empty IDs — positional only)
    base_by_id: dict[str, dict[str, Any]] = {}
    for t in base_tabs:
        tid = _tab_id(t)
        if tid:
            base_by_id[tid] = t

    desired_by_id: dict[str, dict[str, Any]] = {}
    for t in desired_tabs:
        tid = _tab_id(t)
        if tid:
            desired_by_id[tid] = t

    matched_base_ids: set[str] = set()
    matched_desired_ids: set[str] = set()

    # Match by ID first
    for tid, d_tab in desired_by_id.items():
        if tid in base_by_id:
            pairs.append((base_by_id[tid], d_tab))
            matched_base_ids.add(tid)
            matched_desired_ids.add(tid)

    # Positional fallback for tabs with no IDs or unmatched tabs
    unmatched_base = [t for t in base_tabs if _tab_id(t) not in matched_base_ids]
    unmatched_desired = [
        t for t in desired_tabs if _tab_id(t) not in matched_desired_ids
    ]

    for b_tab, d_tab in zip(unmatched_base, unmatched_desired, strict=False):
        pairs.append((b_tab, d_tab))

    extra_base = unmatched_base[len(unmatched_desired) :]
    extra_desired = unmatched_desired[len(unmatched_base) :]

    for b_tab in extra_base:
        ops.append(
            DeleteTabOp(
                base_tab_id=_tab_id(b_tab),
                base_tab_index=b_tab.get("tabProperties", {}).get("index", 0),
            )
        )

    for d_tab in extra_desired:
        ops.append(
            InsertTabOp(
                desired_tab_index=d_tab.get("tabProperties", {}).get("index", 0),
                desired_tab=d_tab,
            )
        )

    # Sort pairs to preserve desired ordering
    pairs.sort(key=lambda p: p[1].get("tabProperties", {}).get("index", 0))

    return pairs, ops


# ---------------------------------------------------------------------------
# Per-tab diff
# ---------------------------------------------------------------------------


def _diff_tab(
    base_tab: dict[str, Any],
    desired_tab: dict[str, Any],
) -> list[ReconcileOp]:
    """Diff all tree levels within a matched tab pair."""
    tab_id = _tab_id(base_tab)
    base_dt = _doc_tab(base_tab)
    desired_dt = _doc_tab(desired_tab)

    ops: list[ReconcileOp] = []

    ops.extend(_diff_document_style(tab_id, base_dt, desired_dt))
    ops.extend(_diff_named_styles(tab_id, base_dt, desired_dt))
    ops.extend(_diff_lists(tab_id, base_dt, desired_dt))
    ops.extend(_diff_inline_objects(tab_id, base_dt, desired_dt))
    ops.extend(_diff_headers(tab_id, base_dt, desired_dt))
    ops.extend(_diff_footers(tab_id, base_dt, desired_dt))
    ops.extend(_diff_footnotes(tab_id, base_dt, desired_dt))
    ops.extend(_diff_body(tab_id, base_dt, desired_dt))

    return ops


# ---------------------------------------------------------------------------
# 1. DocumentStyle
# ---------------------------------------------------------------------------


def _diff_document_style(
    tab_id: str,
    base_dt: dict[str, Any],
    desired_dt: dict[str, Any],
) -> list[ReconcileOp]:
    base_style = base_dt.get("documentStyle", {})
    desired_style = desired_dt.get("documentStyle", {})

    if base_style == desired_style:
        return []

    return [
        UpdateDocumentStyleOp(
            tab_id=tab_id,
            base_style=base_style,
            desired_style=desired_style,
        )
    ]


# ---------------------------------------------------------------------------
# 2. NamedStyles
# ---------------------------------------------------------------------------


def _diff_named_styles(
    tab_id: str,
    base_dt: dict[str, Any],
    desired_dt: dict[str, Any],
) -> list[ReconcileOp]:
    base_styles = base_dt.get("namedStyles", {}).get("styles", [])
    desired_styles = desired_dt.get("namedStyles", {}).get("styles", [])

    base_by_type: dict[str, dict[str, Any]] = {
        s["namedStyleType"]: s for s in base_styles if "namedStyleType" in s
    }
    desired_by_type: dict[str, dict[str, Any]] = {
        s["namedStyleType"]: s for s in desired_styles if "namedStyleType" in s
    }

    ops: list[ReconcileOp] = []

    # Updated or added
    for style_type, d_style in desired_by_type.items():
        if style_type not in base_by_type:
            ops.append(
                InsertNamedStyleOp(
                    tab_id=tab_id,
                    named_style_type=style_type,
                    desired_style=d_style,
                )
            )
        elif base_by_type[style_type] != d_style:
            ops.append(
                UpdateNamedStyleOp(
                    tab_id=tab_id,
                    named_style_type=style_type,
                    base_style=base_by_type[style_type],
                    desired_style=d_style,
                )
            )

    # Deleted
    for style_type, b_style in base_by_type.items():
        if style_type not in desired_by_type:
            ops.append(
                DeleteNamedStyleOp(
                    tab_id=tab_id,
                    named_style_type=style_type,
                    base_style=b_style,
                )
            )

    return ops


# ---------------------------------------------------------------------------
# 3. Lists
# ---------------------------------------------------------------------------


def _diff_lists(
    tab_id: str,
    base_dt: dict[str, Any],
    desired_dt: dict[str, Any],
) -> list[ReconcileOp]:
    base_lists: dict[str, Any] = base_dt.get("lists", {}) or {}
    desired_lists: dict[str, Any] = desired_dt.get("lists", {}) or {}

    ops: list[ReconcileOp] = []

    for list_id, d_def in desired_lists.items():
        if list_id not in base_lists:
            ops.append(InsertListOp(tab_id=tab_id, list_id=list_id, list_def=d_def))
        elif base_lists[list_id] != d_def:
            # List content changed — cannot edit via API
            ops.append(
                UpdateListOp(
                    tab_id=tab_id,
                    list_id=list_id,
                    base_list_def=base_lists[list_id],
                    desired_list_def=d_def,
                )
            )

    for list_id, b_def in base_lists.items():
        if list_id not in desired_lists:
            ops.append(
                DeleteListOp(tab_id=tab_id, list_id=list_id, base_list_def=b_def)
            )

    return ops


# ---------------------------------------------------------------------------
# 4. InlineObjects
# ---------------------------------------------------------------------------


def _diff_inline_objects(
    tab_id: str,
    base_dt: dict[str, Any],
    desired_dt: dict[str, Any],
) -> list[ReconcileOp]:
    base_objs: dict[str, Any] = base_dt.get("inlineObjects", {}) or {}
    desired_objs: dict[str, Any] = desired_dt.get("inlineObjects", {}) or {}

    ops: list[ReconcileOp] = []

    for obj_id, d_obj in desired_objs.items():
        if obj_id in base_objs and base_objs[obj_id] != d_obj:
            ops.append(
                UpdateInlineObjectOp(
                    tab_id=tab_id,
                    inline_object_id=obj_id,
                    base_obj=base_objs[obj_id],
                    desired_obj=d_obj,
                )
            )

    return ops


# ---------------------------------------------------------------------------
# 5. Headers
# ---------------------------------------------------------------------------


def _diff_headers(
    tab_id: str,
    base_dt: dict[str, Any],
    desired_dt: dict[str, Any],
) -> list[ReconcileOp]:
    base_headers: dict[str, Any] = base_dt.get("headers", {}) or {}
    desired_headers: dict[str, Any] = desired_dt.get("headers", {}) or {}

    # Build slot→headerId maps from documentStyle
    base_slots = _header_slots_from_doc_style(base_dt.get("documentStyle", {}))
    desired_slots = _header_slots_from_doc_style(desired_dt.get("documentStyle", {}))

    ops: list[ReconcileOp] = []

    all_slots = set(base_slots) | set(desired_slots)
    for slot in sorted(all_slots):
        b_id = base_slots.get(slot)
        d_id = desired_slots.get(slot)

        if b_id is None and d_id is not None:
            # New header
            d_header = desired_headers.get(d_id, {})
            ops.append(
                CreateHeaderOp(
                    tab_id=tab_id,
                    section_slot=slot,
                    desired_header_id=d_id,
                    desired_content=d_header.get("content", []),
                )
            )
        elif b_id is not None and d_id is None:
            # Deleted header
            ops.append(
                DeleteHeaderOp(tab_id=tab_id, section_slot=slot, base_header_id=b_id)
            )
        elif b_id is not None and d_id is not None:
            b_header = base_headers.get(b_id, {})
            d_header = desired_headers.get(d_id, {})
            b_content = b_header.get("content", [])
            d_content = d_header.get("content", [])
            if b_content != d_content:
                alignment = _align_content_sequence(b_content, d_content)
                ops.append(
                    UpdateHeaderContentOp(
                        tab_id=tab_id,
                        section_slot=slot,
                        header_id=b_id,
                        alignment=alignment,
                        base_content=b_content,
                        desired_content=d_content,
                    )
                )

    return ops


def _header_slots_from_doc_style(doc_style: dict[str, Any]) -> dict[str, str]:
    """Extract slot→headerId mapping from a documentStyle dict."""
    slots: dict[str, str] = {}
    if "defaultHeaderId" in doc_style:
        slots["DEFAULT"] = doc_style["defaultHeaderId"]
    if "firstPageHeaderId" in doc_style:
        slots["FIRST_PAGE"] = doc_style["firstPageHeaderId"]
    if "evenPageHeaderId" in doc_style:
        slots["EVEN_PAGE"] = doc_style["evenPageHeaderId"]
    return slots


# ---------------------------------------------------------------------------
# 6. Footers
# ---------------------------------------------------------------------------


def _diff_footers(
    tab_id: str,
    base_dt: dict[str, Any],
    desired_dt: dict[str, Any],
) -> list[ReconcileOp]:
    base_footers: dict[str, Any] = base_dt.get("footers", {}) or {}
    desired_footers: dict[str, Any] = desired_dt.get("footers", {}) or {}

    base_slots = _footer_slots_from_doc_style(base_dt.get("documentStyle", {}))
    desired_slots = _footer_slots_from_doc_style(desired_dt.get("documentStyle", {}))

    ops: list[ReconcileOp] = []

    all_slots = set(base_slots) | set(desired_slots)
    for slot in sorted(all_slots):
        b_id = base_slots.get(slot)
        d_id = desired_slots.get(slot)

        if b_id is None and d_id is not None:
            d_footer = desired_footers.get(d_id, {})
            ops.append(
                CreateFooterOp(
                    tab_id=tab_id,
                    section_slot=slot,
                    desired_footer_id=d_id,
                    desired_content=d_footer.get("content", []),
                )
            )
        elif b_id is not None and d_id is None:
            ops.append(
                DeleteFooterOp(tab_id=tab_id, section_slot=slot, base_footer_id=b_id)
            )
        elif b_id is not None and d_id is not None:
            b_footer = base_footers.get(b_id, {})
            d_footer = desired_footers.get(d_id, {})
            b_content = b_footer.get("content", [])
            d_content = d_footer.get("content", [])
            if b_content != d_content:
                alignment = _align_content_sequence(b_content, d_content)
                ops.append(
                    UpdateFooterContentOp(
                        tab_id=tab_id,
                        section_slot=slot,
                        footer_id=b_id,
                        alignment=alignment,
                        base_content=b_content,
                        desired_content=d_content,
                    )
                )

    return ops


def _footer_slots_from_doc_style(doc_style: dict[str, Any]) -> dict[str, str]:
    slots: dict[str, str] = {}
    if "defaultFooterId" in doc_style:
        slots["DEFAULT"] = doc_style["defaultFooterId"]
    if "firstPageFooterId" in doc_style:
        slots["FIRST_PAGE"] = doc_style["firstPageFooterId"]
    if "evenPageFooterId" in doc_style:
        slots["EVEN_PAGE"] = doc_style["evenPageFooterId"]
    return slots


# ---------------------------------------------------------------------------
# 7. Footnotes (matched by footnoteId)
# ---------------------------------------------------------------------------


def _diff_footnotes(
    tab_id: str,
    base_dt: dict[str, Any],
    desired_dt: dict[str, Any],
) -> list[ReconcileOp]:
    base_fn: dict[str, Any] = base_dt.get("footnotes", {}) or {}
    desired_fn: dict[str, Any] = desired_dt.get("footnotes", {}) or {}

    ops: list[ReconcileOp] = []

    # Build an index: footnoteId → body character offset from the desired body.
    # Used to populate anchor_index on InsertFootnoteOp.
    desired_fn_anchors = _footnote_ref_offsets_in_body(
        desired_dt.get("body", {}).get("content", [])
    )

    # Build an index: footnoteId → body character offset from the base body.
    # Used to populate ref_index on DeleteFootnoteOp.
    base_fn_anchors = _footnote_ref_offsets_in_body(
        base_dt.get("body", {}).get("content", [])
    )

    for fn_id, d_fn in desired_fn.items():
        if fn_id not in base_fn:
            ops.append(
                InsertFootnoteOp(
                    tab_id=tab_id,
                    footnote_id=fn_id,
                    desired_content=d_fn.get("content", []),
                    anchor_index=desired_fn_anchors.get(fn_id, -1),
                )
            )
        else:
            b_content = base_fn[fn_id].get("content", [])
            d_content = d_fn.get("content", [])
            if b_content != d_content:
                alignment = _align_content_sequence(b_content, d_content)
                ops.append(
                    UpdateFootnoteContentOp(
                        tab_id=tab_id,
                        footnote_id=fn_id,
                        alignment=alignment,
                        base_content=b_content,
                        desired_content=d_content,
                    )
                )

    for fn_id in base_fn:
        if fn_id not in desired_fn:
            ops.append(
                DeleteFootnoteOp(
                    tab_id=tab_id,
                    footnote_id=fn_id,
                    ref_index=base_fn_anchors.get(fn_id, -1),
                )
            )

    return ops


def _footnote_ref_offsets_in_body(
    body_content: list[dict[str, Any]],
) -> dict[str, int]:
    """Walk body content and return a mapping of footnoteId → startIndex.

    Each ``footnoteReference`` paragraph element occupies exactly one character
    in the document.  We collect the ``startIndex`` of the element if present,
    so that ``InsertFootnoteOp`` can carry the anchor location for
    ``createFootnote``.
    """
    offsets: dict[str, int] = {}
    for el in body_content:
        if "paragraph" not in el:
            continue
        para = el["paragraph"]
        for pe in para.get("elements", []):
            fn_ref = pe.get("footnoteReference")
            if fn_ref is None:
                continue
            fn_id = fn_ref.get("footnoteId")
            if fn_id is None:
                continue
            start = pe.get("startIndex")
            if isinstance(start, int):
                offsets[fn_id] = start
    return offsets


# ---------------------------------------------------------------------------
# 8. Body content (and table cell recursion)
# ---------------------------------------------------------------------------


def _diff_body(
    tab_id: str,
    base_dt: dict[str, Any],
    desired_dt: dict[str, Any],
) -> list[ReconcileOp]:
    b_content = base_dt.get("body", {}).get("content", [])
    d_content = desired_dt.get("body", {}).get("content", [])

    if b_content == d_content:
        return []

    alignment = _align_content_sequence(b_content, d_content)
    child_ops = _diff_table_cells_in_alignment(
        tab_id=tab_id,
        alignment=alignment,
        base_content=b_content,
        desired_content=d_content,
    )

    # Emit body op first, then all table-cell child ops flat at the top level.
    # This keeps the op list a flat sequence (no nesting) and makes it easy
    # for callers to inspect all ops without recursive traversal.
    return [
        UpdateBodyContentOp(
            tab_id=tab_id,
            story_kind="body",
            story_id="body",
            alignment=alignment,
            base_content=b_content,
            desired_content=d_content,
            child_ops=child_ops,
        ),
        *child_ops,
    ]


def _diff_table_cells_in_alignment(
    tab_id: str,
    alignment: ContentAlignment,
    base_content: list[dict[str, Any]],
    desired_content: list[dict[str, Any]],
) -> list[ReconcileOp]:
    """For matched table pairs, recurse into table cells."""
    ops: list[ReconcileOp] = []
    for match in alignment.matches:
        b_el = base_content[match.base_idx]
        d_el = desired_content[match.desired_idx]
        if "table" in b_el and "table" in d_el:
            ops.extend(
                _diff_table(
                    tab_id=tab_id,
                    base_table=b_el["table"],
                    desired_table=d_el["table"],
                    table_label=f"body_table_{match.base_idx}",
                )
            )
    return ops


def _diff_table(
    tab_id: str,
    base_table: dict[str, Any],
    desired_table: dict[str, Any],
    table_label: str,
) -> list[ReconcileOp]:
    """Diff two matched tables by recursing into each matched cell."""
    base_rows = base_table.get("tableRows", [])
    desired_rows = desired_table.get("tableRows", [])

    ops: list[ReconcileOp] = []

    # Simple positional matching for cells within matched rows
    for row_idx, (b_row, d_row) in enumerate(
        zip(base_rows, desired_rows, strict=False)
    ):
        b_cells = b_row.get("tableCells", [])
        d_cells = d_row.get("tableCells", [])
        for col_idx, (b_cell, d_cell) in enumerate(zip(b_cells, d_cells, strict=False)):
            b_content = b_cell.get("content", [])
            d_content = d_cell.get("content", [])
            if b_content == d_content:
                continue
            cell_label = f"{table_label}:r{row_idx}:c{col_idx}"
            alignment = _align_content_sequence(b_content, d_content)
            child_ops = _diff_table_cells_in_alignment(
                tab_id=tab_id,
                alignment=alignment,
                base_content=b_content,
                desired_content=d_content,
            )
            ops.append(
                UpdateBodyContentOp(
                    tab_id=tab_id,
                    story_kind="table_cell",
                    story_id=cell_label,
                    alignment=alignment,
                    base_content=b_content,
                    desired_content=d_content,
                    child_ops=child_ops,
                )
            )

    return ops


# ---------------------------------------------------------------------------
# Content alignment helper
# ---------------------------------------------------------------------------


def _align_content_sequence(
    base_content: list[dict[str, Any]],
    desired_content: list[dict[str, Any]],
) -> ContentAlignment:
    """Convert raw content lists to ContentNodes and run alignment DP."""
    if not base_content and not desired_content:
        return ContentAlignment(
            matches=[], base_deletes=[], desired_inserts=[], total_cost=0.0
        )

    def _nodes(content: list[dict[str, Any]]) -> list[ContentNode]:
        nodes = [content_node_from_raw(el) for el in content]
        if nodes:
            nodes[-1].is_terminal = True
        return nodes

    base_nodes = _nodes(base_content)
    desired_nodes = _nodes(desired_content)
    return align_content(base_nodes, desired_nodes)
