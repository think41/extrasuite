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
    DeleteInlineObjectOp,
    DeleteListOp,
    DeleteNamedStyleOp,
    DeleteTabOp,
    InsertFootnoteOp,
    InsertInlineObjectOp,
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
    UpdateTableCellStyleOp,
    UpdateTableColumnPropertiesOp,
    UpdateTableRowStyleOp,
)
from extradoc.reconcile_v3.table_diff import diff_tables as _diff_tables_structural
from extradoc.reconcile_v3.table_diff import get_matched_rows

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


_HEADER_FOOTER_ID_FIELDS: frozenset[str] = frozenset(
    {
        "defaultHeaderId",
        "firstPageHeaderId",
        "evenPageHeaderId",
        "defaultFooterId",
        "firstPageFooterId",
        "evenPageFooterId",
    }
)

# Writable DocumentStyle fields that can be applied via updateDocumentStyle.
# Header/footer ID fields are excluded — they're managed by structural ops.
_WRITABLE_DOC_STYLE_FIELDS: list[str] = [
    "background",
    "flipPageOrientation",
    "marginBottom",
    "marginFooter",
    "marginHeader",
    "marginLeft",
    "marginRight",
    "marginTop",
    "pageNumberStart",
    "pageSize",
    "useEvenPageHeaderFooter",
    "useFirstPageHeaderFooter",
]


def _diff_document_style(
    tab_id: str,
    base_dt: dict[str, Any],
    desired_dt: dict[str, Any],
) -> list[ReconcileOp]:
    base_style = base_dt.get("documentStyle", {})
    desired_style = desired_dt.get("documentStyle", {})

    result = _styles_changed(base_style, desired_style, _WRITABLE_DOC_STYLE_FIELDS)
    if result is None:
        return []

    changed_fields, fields_mask = result
    return [
        UpdateDocumentStyleOp(
            tab_id=tab_id,
            changed_fields=changed_fields,
            fields_mask=fields_mask,
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

    desired_inline_objects: dict[str, Any] = desired_dt.get("inlineObjects", {}) or {}
    base_inline_objects: dict[str, Any] = base_dt.get("inlineObjects", {}) or {}
    alignment = _align_content_sequence(b_content, d_content)
    child_ops = _diff_table_cells_in_alignment(
        tab_id=tab_id,
        alignment=alignment,
        base_content=b_content,
        desired_content=d_content,
        desired_inline_objects=desired_inline_objects,
        base_inline_objects=base_inline_objects,
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
    desired_inline_objects: dict[str, Any] | None = None,
    base_inline_objects: dict[str, Any] | None = None,
) -> list[ReconcileOp]:
    """For matched element pairs, recurse into table cells and check inline images."""
    ops: list[ReconcileOp] = []
    _desired_objs = desired_inline_objects or {}
    _base_objs = base_inline_objects or {}
    for match in alignment.matches:
        b_el = base_content[match.base_idx]
        d_el = desired_content[match.desired_idx]
        if "table" in b_el and "table" in d_el:
            # Extract the table's startIndex from the base element for lowering
            table_start_index: int = b_el.get("startIndex", 0)
            ops.extend(
                _diff_table(
                    tab_id=tab_id,
                    base_table=b_el["table"],
                    desired_table=d_el["table"],
                    table_label=f"body_table_{match.base_idx}",
                    table_start_index=table_start_index,
                    desired_inline_objects=_desired_objs,
                    base_inline_objects=_base_objs,
                )
            )
        elif "paragraph" in b_el and "paragraph" in d_el:
            ops.extend(
                _diff_paragraph_inline_images(
                    tab_id=tab_id,
                    base_para=b_el["paragraph"],
                    desired_para=d_el["paragraph"],
                    desired_inline_objects=_desired_objs,
                    base_inline_objects=_base_objs,
                )
            )
    return ops


def _diff_paragraph_inline_images(
    tab_id: str,
    base_para: dict[str, Any],
    desired_para: dict[str, Any],
    desired_inline_objects: dict[str, Any],
    base_inline_objects: dict[str, Any],  # noqa: ARG001 — reserved for future use
) -> list[ReconcileOp]:
    """Detect inline images added or removed in a matched paragraph pair.

    Walks the ``elements`` arrays of both paragraphs and compares
    ``inlineObjectElement`` entries.  When an image appears in the desired
    paragraph but not in the base, emits ``InsertInlineObjectOp``.  When an
    image appears in the base but not in the desired, emits
    ``DeleteInlineObjectOp``.

    Only the simple add/remove case is handled.  Reordering images within a
    paragraph is not supported in this implementation.
    """
    ops: list[ReconcileOp] = []

    base_elements = base_para.get("elements", [])
    desired_elements = desired_para.get("elements", [])

    # Collect inlineObjectIds present in each paragraph
    base_image_ids: set[str] = set()
    for pe in base_elements:
        ioe = pe.get("inlineObjectElement")
        if ioe is not None:
            obj_id = ioe.get("inlineObjectId")
            if obj_id:
                base_image_ids.add(obj_id)

    desired_image_ids: set[str] = set()
    # Also build a map from id → element for index lookup
    desired_image_elements: dict[str, dict[str, Any]] = {}
    for pe in desired_elements:
        ioe = pe.get("inlineObjectElement")
        if ioe is not None:
            obj_id = ioe.get("inlineObjectId")
            if obj_id:
                desired_image_ids.add(obj_id)
                desired_image_elements[obj_id] = pe

    # Images added: present in desired but not in base
    for obj_id in desired_image_ids - base_image_ids:
        inline_obj = desired_inline_objects.get(obj_id, {})
        props = inline_obj.get("inlineObjectProperties", {})
        embedded = props.get("embeddedObject", {})
        image_props = embedded.get("imageProperties", {})
        content_uri: str = image_props.get("contentUri", "")
        object_size: dict[str, Any] | None = embedded.get("size") or None

        # Get the insert_index from the desired paragraph element
        pe = desired_image_elements[obj_id]
        insert_index: int = pe.get("startIndex", 0)

        ops.append(
            InsertInlineObjectOp(
                tab_id=tab_id,
                inline_object_id=obj_id,
                content_uri=content_uri,
                insert_index=insert_index,
                object_size=object_size,
            )
        )

    # Images deleted: present in base but not in desired
    for pe in base_elements:
        ioe = pe.get("inlineObjectElement")
        if ioe is None:
            continue
        obj_id = ioe.get("inlineObjectId")
        if not obj_id or obj_id in desired_image_ids:
            continue
        delete_index: int = pe.get("startIndex", 0)
        ops.append(
            DeleteInlineObjectOp(
                tab_id=tab_id,
                inline_object_id=obj_id,
                delete_index=delete_index,
            )
        )

    return ops


def _styles_changed(
    base: dict[str, Any],
    desired: dict[str, Any],
    fields: list[str],
) -> tuple[dict[str, Any], str] | None:
    """Compare specific fields between base and desired dicts.

    Returns (changed_fields_dict, fields_mask) if any of the given fields
    differ between base and desired, or None if they are identical.
    """
    changed: dict[str, Any] = {}
    for field in fields:
        b_val = base.get(field)
        d_val = desired.get(field)
        if b_val != d_val:
            changed[field] = d_val
    if not changed:
        return None
    fields_mask = ",".join(sorted(changed.keys()))
    return changed, fields_mask


def _diff_table(
    tab_id: str,
    base_table: dict[str, Any],
    desired_table: dict[str, Any],
    table_label: str,
    table_start_index: int = 0,
    desired_inline_objects: dict[str, Any] | None = None,
    base_inline_objects: dict[str, Any] | None = None,
) -> list[ReconcileOp]:
    """Diff two matched tables: emit structural row/column ops + cell content ops."""
    ops: list[ReconcileOp] = []
    _desired_objs = desired_inline_objects or {}
    _base_objs = base_inline_objects or {}

    # Phase 1: Structural ops (row/column inserts and deletes)
    structural_ops = _diff_tables_structural(
        base_table,
        desired_table,
        tab_id=tab_id,
        table_start_index=table_start_index,
    )
    ops.extend(structural_ops)

    # Phase 2: Cell content ops for matched rows (fuzzy LCS matching)
    row_matches = get_matched_rows(base_table, desired_table)
    base_rows = base_table.get("tableRows", [])
    desired_rows = desired_table.get("tableRows", [])

    for base_row_idx, desired_row_idx in row_matches:
        b_row = base_rows[base_row_idx]
        d_row = desired_rows[desired_row_idx]
        b_cells = b_row.get("tableCells", [])
        d_cells = d_row.get("tableCells", [])
        # Only emit cell content ops when row column counts match
        # (mismatched counts will be fixed by column structural ops in a later pass)
        if len(b_cells) != len(d_cells):
            continue
        for col_idx, (b_cell, d_cell) in enumerate(zip(b_cells, d_cells, strict=False)):
            b_content = b_cell.get("content", [])
            d_content = d_cell.get("content", [])
            if b_content != d_content:
                cell_label = f"{table_label}:r{base_row_idx}:c{col_idx}"
                alignment = _align_content_sequence(b_content, d_content)
                child_ops = _diff_table_cells_in_alignment(
                    tab_id=tab_id,
                    alignment=alignment,
                    base_content=b_content,
                    desired_content=d_content,
                    desired_inline_objects=_desired_objs,
                    base_inline_objects=_base_objs,
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

            # Phase 3: Cell style ops
            b_cell_style = b_cell.get("tableCellStyle", {})
            d_cell_style = d_cell.get("tableCellStyle", {})
            _CELL_STYLE_FIELDS = [
                "backgroundColor",
                "borderBottom",
                "borderLeft",
                "borderRight",
                "borderTop",
                "contentAlignment",
                "paddingBottom",
                "paddingLeft",
                "paddingRight",
                "paddingTop",
            ]
            result = _styles_changed(b_cell_style, d_cell_style, _CELL_STYLE_FIELDS)
            if result is not None:
                style_changes, fields_mask = result
                ops.append(
                    UpdateTableCellStyleOp(
                        tab_id=tab_id,
                        table_start_index=table_start_index,
                        row_index=base_row_idx,
                        column_index=col_idx,
                        style_changes=style_changes,
                        fields_mask=fields_mask,
                    )
                )

        # Phase 4: Row style ops
        b_row_style = b_row.get("tableRowStyle", {})
        d_row_style = d_row.get("tableRowStyle", {})
        b_min_height = b_row_style.get("minRowHeight") if b_row_style else None
        d_min_height = d_row_style.get("minRowHeight") if d_row_style else None
        if b_min_height != d_min_height:
            ops.append(
                UpdateTableRowStyleOp(
                    tab_id=tab_id,
                    table_start_index=table_start_index,
                    row_index=base_row_idx,
                    min_row_height=d_min_height,
                )
            )

    # Phase 5: Column properties ops
    b_table_style = base_table.get("tableStyle", {}) or {}
    d_table_style = desired_table.get("tableStyle", {}) or {}
    b_col_props: list[dict[str, Any]] = b_table_style.get("tableColumnProperties") or []
    d_col_props: list[dict[str, Any]] = d_table_style.get("tableColumnProperties") or []
    _COL_FIELDS = ["width", "widthType"]
    for col_idx, (b_col, d_col) in enumerate(
        zip(b_col_props, d_col_props, strict=False)
    ):
        result = _styles_changed(b_col, d_col, _COL_FIELDS)
        if result is not None:
            ops.append(
                UpdateTableColumnPropertiesOp(
                    tab_id=tab_id,
                    table_start_index=table_start_index,
                    column_index=col_idx,
                    width=d_col.get("width"),
                    width_type=d_col.get("widthType"),
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
