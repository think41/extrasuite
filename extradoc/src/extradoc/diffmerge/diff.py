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

No live API calls.  All computation is pure in-memory over typed Pydantic models.
"""

from __future__ import annotations

from extradoc.api_types._generated import (
    Body,
    Document,
    DocumentStyle,
    DocumentTab,
    Footer,
    Footnote,
    Header,
    InlineObject,
    List,
    NamedRanges,
    NamedStyle,
    NamedStyles,
    Paragraph,
    ParagraphElement,
    Range,
    StructuralElement,
    Tab,
    Table,
    TableCell,
    TableCellStyle,
    TableColumnProperties,
    TableRow,
    TableRowStyle,
    TableStyle,
    TabProperties,
)
from extradoc.diffmerge.content_align import (
    ContentAlignment,
    ContentNode,
    align_content,
    content_node_from_element,
)
from extradoc.diffmerge.model import (
    CreateFooterOp,
    CreateHeaderOp,
    DeleteFooterOp,
    DeleteFootnoteOp,
    DeleteHeaderOp,
    DeleteInlineObjectOp,
    DeleteListOp,
    DeleteNamedRangeOp,
    DeleteNamedStyleOp,
    DeleteTabOp,
    InsertFootnoteOp,
    InsertInlineObjectOp,
    InsertListOp,
    InsertNamedRangeOp,
    InsertNamedStyleOp,
    InsertTabOp,
    ReconcileOp,
    UpdateBodyContentOp,
    UpdateDocumentStyleOp,
    UpdateFooterContentOp,
    UpdateFootnoteContentOp,
    UpdateHeaderContentOp,
    UpdateInlineObjectOp,
    UpdateNamedStyleOp,
    UpdateTableCellStyleOp,
    UpdateTableColumnPropertiesOp,
    UpdateTableRowStyleOp,
)
from extradoc.diffmerge.table_diff import diff_tables as _diff_tables_structural
from extradoc.diffmerge.table_diff import get_matched_rows

# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def diff_documents(
    base: Document,
    desired: Document,
) -> list[ReconcileOp]:
    """Return the full op list to transform base → desired.

    Parameters
    ----------
    base:
        Current state of the document.
    desired:
        Target state of the document.

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


def _get_tabs(doc: Document) -> list[Tab]:
    """Return the tabs list from a Document model.

    For legacy single-tab documents (no ``tabs`` field), synthesises a single
    pseudo-tab wrapping the top-level body/headers/etc. fields.
    """
    if doc.tabs:
        return list(doc.tabs)
    # Legacy document: wrap top-level content as a pseudo-tab
    pseudo_tab = Tab(
        tab_properties=TabProperties(tab_id="", title="Tab 1", index=0),
        document_tab=DocumentTab(
            body=doc.body or Body(content=[]),
            headers=doc.headers or {},
            footers=doc.footers or {},
            footnotes=doc.footnotes or {},
            lists=doc.lists or {},
            named_styles=doc.named_styles or NamedStyles(styles=[]),
            document_style=doc.document_style or DocumentStyle(),
            inline_objects=doc.inline_objects or {},
        ),
    )
    return [pseudo_tab]


def _tab_id(tab: Tab) -> str:
    """Extract tabId from a Tab model (empty string for legacy pseudo-tabs)."""
    if tab.tab_properties is None:
        return ""
    return tab.tab_properties.tab_id or ""


def _doc_tab(tab: Tab) -> DocumentTab:
    """Return the DocumentTab portion of a Tab model."""
    return tab.document_tab or DocumentTab()


def _match_tabs(
    base_tabs: list[Tab],
    desired_tabs: list[Tab],
) -> tuple[list[tuple[Tab, Tab]], list[ReconcileOp]]:
    """Match base tabs to desired tabs by tabId, with positional fallback.

    Returns
    -------
    pairs:
        Matched (base_tab, desired_tab) pairs.
    ops:
        InsertTabOp and DeleteTabOp for unmatched tabs.
    """
    ops: list[ReconcileOp] = []
    pairs: list[tuple[Tab, Tab]] = []

    # Build lookup by tabId (skip empty IDs — positional only)
    base_by_id: dict[str, Tab] = {}
    for t in base_tabs:
        tid = _tab_id(t)
        if tid:
            base_by_id[tid] = t

    desired_by_id: dict[str, Tab] = {}
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
        b_props = b_tab.tab_properties
        ops.append(
            DeleteTabOp(
                base_tab_id=_tab_id(b_tab),
                base_tab_index=b_props.index
                if b_props and b_props.index is not None
                else 0,
            )
        )

    for d_tab in extra_desired:
        d_props = d_tab.tab_properties
        # Use the tab's explicit index if available, otherwise fall back to
        # its position in the desired_tabs list.
        if d_props and d_props.index is not None:
            tab_index = d_props.index
        else:
            try:
                tab_index = desired_tabs.index(d_tab)
            except ValueError:
                tab_index = len(desired_tabs) - 1
        ops.append(
            InsertTabOp(
                desired_tab_index=tab_index,
                desired_tab=d_tab,
            )
        )

    # Sort pairs to preserve desired ordering
    def _tab_index(pair: tuple[Tab, Tab]) -> int:
        props = pair[1].tab_properties
        if props and props.index is not None:
            return props.index
        return 0

    pairs.sort(key=_tab_index)

    return pairs, ops


# ---------------------------------------------------------------------------
# Per-tab diff
# ---------------------------------------------------------------------------


def _diff_tab(
    base_tab: Tab,
    desired_tab: Tab,
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
    ops.extend(_diff_named_ranges(tab_id, base_dt, desired_dt))
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
# These are camelCase (API alias names) because they go directly into API
# request dicts.
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
    base_dt: DocumentTab,
    desired_dt: DocumentTab,
) -> list[ReconcileOp]:
    # If the desired document has no "documentStyle" (e.g. markdown
    # format does not model document style), leave the existing style
    # untouched.
    if desired_dt.document_style is None:
        return []
    base_style = base_dt.document_style or DocumentStyle()
    desired_style = desired_dt.document_style

    # Compare only writable fields to compute the field mask
    base_dict = base_style.model_dump(by_alias=True, exclude_none=True)
    desired_dict = desired_style.model_dump(by_alias=True, exclude_none=True)

    fields_mask = _fields_mask_for_changed(
        base_dict, desired_dict, _WRITABLE_DOC_STYLE_FIELDS
    )
    if fields_mask is None:
        return []

    return [
        UpdateDocumentStyleOp(
            tab_id=tab_id,
            desired_style=desired_style,
            fields_mask=fields_mask,
        )
    ]


# ---------------------------------------------------------------------------
# 2. NamedStyles
# ---------------------------------------------------------------------------


def _diff_named_styles(
    tab_id: str,
    base_dt: DocumentTab,
    desired_dt: DocumentTab,
) -> list[ReconcileOp]:
    base_ns = base_dt.named_styles
    base_styles: list[NamedStyle] = (base_ns.styles or []) if base_ns else []

    # When the desired document has no "namedStyles" at all (e.g. the
    # markdown format does not model named styles), treat it as "preserve
    # whatever the base has" — neither update nor delete anything.
    desired_named_styles_present = desired_dt.named_styles is not None
    desired_ns = desired_dt.named_styles
    desired_styles: list[NamedStyle] = (desired_ns.styles or []) if desired_ns else []

    base_by_type: dict[str, NamedStyle] = {
        s.named_style_type: s for s in base_styles if s.named_style_type is not None
    }
    desired_by_type: dict[str, NamedStyle] = {
        s.named_style_type: s for s in desired_styles if s.named_style_type is not None
    }

    ops: list[ReconcileOp] = []

    if not desired_named_styles_present:
        # Format doesn't model named styles — leave them untouched.
        return ops

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
    base_dt: DocumentTab,
    desired_dt: DocumentTab,
) -> list[ReconcileOp]:
    base_lists: dict[str, List] = base_dt.lists or {}
    desired_lists: dict[str, List] = desired_dt.lists or {}

    ops: list[ReconcileOp] = []

    for list_id, d_def in desired_lists.items():
        if list_id not in base_lists:
            ops.append(InsertListOp(tab_id=tab_id, list_id=list_id, list_def=d_def))
        # else: list exists in both — list defs cannot be changed via API, skip

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
    base_dt: DocumentTab,
    desired_dt: DocumentTab,
) -> list[ReconcileOp]:
    base_objs: dict[str, InlineObject] = base_dt.inline_objects or {}
    desired_objs: dict[str, InlineObject] = desired_dt.inline_objects or {}

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
    base_dt: DocumentTab,
    desired_dt: DocumentTab,
) -> list[ReconcileOp]:
    base_headers: dict[str, Header] = base_dt.headers or {}
    desired_headers: dict[str, Header] = desired_dt.headers or {}

    # Build slot→headerId maps from documentStyle
    base_slots = _header_slots_from_doc_style(base_dt.document_style or DocumentStyle())
    desired_slots = _header_slots_from_doc_style(
        desired_dt.document_style or DocumentStyle()
    )

    ops: list[ReconcileOp] = []

    all_slots = set(base_slots) | set(desired_slots)
    for slot in sorted(all_slots):
        b_id = base_slots.get(slot)
        d_id = desired_slots.get(slot)

        if b_id is None and d_id is not None:
            # New header
            d_header = desired_headers.get(d_id)
            d_content = (d_header.content or []) if d_header else []
            ops.append(
                CreateHeaderOp(
                    tab_id=tab_id,
                    section_slot=slot,
                    desired_header_id=d_id,
                    desired_content=d_content,
                )
            )
        elif b_id is not None and d_id is None:
            # Deleted header
            ops.append(
                DeleteHeaderOp(tab_id=tab_id, section_slot=slot, base_header_id=b_id)
            )
        elif b_id is not None and d_id is not None:
            b_header = base_headers.get(b_id)
            d_header = desired_headers.get(d_id)
            b_content: list[StructuralElement] = (
                (b_header.content or []) if b_header else []
            )
            d_content_list: list[StructuralElement] = (
                (d_header.content or []) if d_header else []
            )
            if b_content != d_content_list:
                alignment = _align_content_sequence(b_content, d_content_list)
                ops.append(
                    UpdateHeaderContentOp(
                        tab_id=tab_id,
                        section_slot=slot,
                        header_id=b_id,
                        alignment=alignment,
                        base_content=b_content,
                        desired_content=d_content_list,
                    )
                )

    return ops


def _header_slots_from_doc_style(doc_style: DocumentStyle) -> dict[str, str]:
    """Extract slot→headerId mapping from a DocumentStyle model."""
    slots: dict[str, str] = {}
    if doc_style.default_header_id is not None:
        slots["DEFAULT"] = doc_style.default_header_id
    if doc_style.first_page_header_id is not None:
        slots["FIRST_PAGE"] = doc_style.first_page_header_id
    if doc_style.even_page_header_id is not None:
        slots["EVEN_PAGE"] = doc_style.even_page_header_id
    return slots


# ---------------------------------------------------------------------------
# 6. Footers
# ---------------------------------------------------------------------------


def _diff_footers(
    tab_id: str,
    base_dt: DocumentTab,
    desired_dt: DocumentTab,
) -> list[ReconcileOp]:
    base_footers: dict[str, Footer] = base_dt.footers or {}
    desired_footers: dict[str, Footer] = desired_dt.footers or {}

    base_slots = _footer_slots_from_doc_style(base_dt.document_style or DocumentStyle())
    desired_slots = _footer_slots_from_doc_style(
        desired_dt.document_style or DocumentStyle()
    )

    ops: list[ReconcileOp] = []

    all_slots = set(base_slots) | set(desired_slots)
    for slot in sorted(all_slots):
        b_id = base_slots.get(slot)
        d_id = desired_slots.get(slot)

        if b_id is None and d_id is not None:
            d_footer = desired_footers.get(d_id)
            d_content = (d_footer.content or []) if d_footer else []
            ops.append(
                CreateFooterOp(
                    tab_id=tab_id,
                    section_slot=slot,
                    desired_footer_id=d_id,
                    desired_content=d_content,
                )
            )
        elif b_id is not None and d_id is None:
            ops.append(
                DeleteFooterOp(tab_id=tab_id, section_slot=slot, base_footer_id=b_id)
            )
        elif b_id is not None and d_id is not None:
            b_footer = base_footers.get(b_id)
            d_footer = desired_footers.get(d_id)
            b_content: list[StructuralElement] = (
                (b_footer.content or []) if b_footer else []
            )
            d_content_list: list[StructuralElement] = (
                (d_footer.content or []) if d_footer else []
            )
            if b_content != d_content_list:
                alignment = _align_content_sequence(b_content, d_content_list)
                ops.append(
                    UpdateFooterContentOp(
                        tab_id=tab_id,
                        section_slot=slot,
                        footer_id=b_id,
                        alignment=alignment,
                        base_content=b_content,
                        desired_content=d_content_list,
                    )
                )

    return ops


def _footer_slots_from_doc_style(doc_style: DocumentStyle) -> dict[str, str]:
    slots: dict[str, str] = {}
    if doc_style.default_footer_id is not None:
        slots["DEFAULT"] = doc_style.default_footer_id
    if doc_style.first_page_footer_id is not None:
        slots["FIRST_PAGE"] = doc_style.first_page_footer_id
    if doc_style.even_page_footer_id is not None:
        slots["EVEN_PAGE"] = doc_style.even_page_footer_id
    return slots


# ---------------------------------------------------------------------------
# 7. Footnotes (matched by footnoteId)
# ---------------------------------------------------------------------------


def _diff_footnotes(
    tab_id: str,
    base_dt: DocumentTab,
    desired_dt: DocumentTab,
) -> list[ReconcileOp]:
    base_fn: dict[str, Footnote] = base_dt.footnotes or {}
    desired_fn: dict[str, Footnote] = desired_dt.footnotes or {}

    ops: list[ReconcileOp] = []

    # Build an index: footnoteId → body character offset from the desired body.
    # Used to populate anchor_index on InsertFootnoteOp.
    desired_body = desired_dt.body
    desired_body_content = (desired_body.content or []) if desired_body else []
    desired_fn_anchors = _footnote_ref_offsets_in_body(desired_body_content)

    # Build an index: footnoteId → body character offset from the base body.
    # Used to populate ref_index on DeleteFootnoteOp.
    base_body = base_dt.body
    base_body_content = (base_body.content or []) if base_body else []
    base_fn_anchors = _footnote_ref_offsets_in_body(base_body_content)

    for fn_id, d_fn in desired_fn.items():
        d_content = d_fn.content or []
        if fn_id not in base_fn:
            ops.append(
                InsertFootnoteOp(
                    tab_id=tab_id,
                    footnote_id=fn_id,
                    desired_content=d_content,
                    anchor_index=desired_fn_anchors.get(fn_id, -1),
                )
            )
        else:
            b_content = base_fn[fn_id].content or []
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


def _walk_table_for_footnotes(
    table: Table,
    cursor: int,
    offsets: dict[str, int],
) -> int:
    """Walk table cells recursively, collecting footnote ref offsets.

    Returns the cursor position after the table.

    Table structure in Google Docs index space:
      1 char for table opener
      per row: 1 char for row opener
        per cell: 1 char for cell opener + cell content
      1 char trailing newline after table
    """
    cursor += 1  # table opener
    for row in table.table_rows or []:
        cursor += 1  # row opener
        for cell in row.table_cells or []:
            cursor += 1  # cell opener
            for content_el in cell.content or []:
                if content_el.paragraph is not None:
                    para = content_el.paragraph
                    for pe in para.elements or []:
                        fn_ref = pe.footnote_reference
                        if fn_ref is not None and fn_ref.footnote_id is not None:
                            offsets[fn_ref.footnote_id] = cursor
                            cursor += 1
                        elif (
                            pe.text_run is not None and pe.text_run.content is not None
                        ):
                            cursor += len(pe.text_run.content)
                        else:
                            cursor += 1
                elif content_el.table is not None:
                    # Nested table
                    cursor = _walk_table_for_footnotes(
                        content_el.table, cursor, offsets
                    )
                else:
                    cursor += 1
    cursor += 1  # trailing newline after table
    return cursor


def _footnote_ref_offsets_in_body(
    body_content: list[StructuralElement],
) -> dict[str, int]:
    """Walk body content and return a mapping of footnoteId → startIndex.

    Each ``footnoteReference`` paragraph element occupies exactly one character
    in the document.  We collect the ``startIndex`` of the element if present,
    so that ``InsertFootnoteOp`` can carry the anchor location for
    ``createFootnote``.

    When ``startIndex`` is not available on the ParagraphElement (e.g. in a
    desired document constructed without API indices), we compute positions by
    walking the body content and counting character sizes.  The body starts at
    index 0 (or the first element's startIndex if available).
    """
    offsets: dict[str, int] = {}

    # First pass: try to collect from explicit startIndex values.
    # Walk into table cells recursively to find footnote refs there too.
    def _collect_from_indices(elements: list[StructuralElement]) -> None:
        for el in elements:
            if el.paragraph is not None:
                for pe in el.paragraph.elements or []:
                    fn_ref = pe.footnote_reference
                    if fn_ref is None:
                        continue
                    fn_id = fn_ref.footnote_id
                    if fn_id is None:
                        continue
                    start = pe.start_index
                    if isinstance(start, int):
                        offsets[fn_id] = start
            elif el.table is not None:
                for row in el.table.table_rows or []:
                    for cell in row.table_cells or []:
                        _collect_from_indices(cell.content or [])

    _collect_from_indices(body_content)

    if offsets:
        return offsets

    # Second pass: compute positions by walking body content
    # Determine start offset from the first element, or default to 1
    # (body content typically starts at index 1 after the section break)
    cursor = 1
    if body_content and isinstance(body_content[0].start_index, int):
        cursor = body_content[0].start_index

    for el in body_content:
        if el.paragraph is not None:
            para = el.paragraph
            for pe in para.elements or []:
                fn_ref = pe.footnote_reference
                if fn_ref is not None and fn_ref.footnote_id is not None:
                    offsets[fn_ref.footnote_id] = cursor
                    cursor += 1  # footnote ref occupies 1 character
                elif pe.text_run is not None and pe.text_run.content is not None:
                    cursor += len(pe.text_run.content)
                else:
                    cursor += 1  # other non-text elements occupy 1 character
        elif el.section_break is not None:
            cursor += 1
        elif el.table is not None:
            # Use startIndex/endIndex if available, otherwise walk into
            # the table cells recursively to find footnote refs.
            start, end = el.start_index, el.end_index
            if isinstance(start, int) and isinstance(end, int):
                # Walk into cells to find footnote refs even when indices
                # are available (use the known start to position cursor).
                cursor = _walk_table_for_footnotes(el.table, start, offsets)
                cursor = end
            else:
                # No indices: walk recursively and compute positions.
                cursor = _walk_table_for_footnotes(el.table, cursor, offsets)
        else:
            cursor += 1

    return offsets


# ---------------------------------------------------------------------------
# 7b. Named Ranges
# ---------------------------------------------------------------------------


def _diff_named_ranges(
    tab_id: str,
    base_dt: DocumentTab,
    desired_dt: DocumentTab,
) -> list[ReconcileOp]:
    """Diff named ranges between base and desired DocumentTab.

    Named ranges are keyed by name in the ``namedRanges`` dict, but each
    ``NamedRanges`` object may contain multiple ``NamedRange`` entries (each
    with its own ``namedRangeId``).  We match at the ``namedRangeId`` level.

    - ID only in desired → ``InsertNamedRangeOp``
    - ID only in base → ``DeleteNamedRangeOp``
    - Same ID, different ranges → ``DeleteNamedRangeOp`` + ``InsertNamedRangeOp``
    - Same ID, identical ranges → no op

    If the desired tab has ``named_ranges=None`` we treat it as "preserve
    whatever the base has" (no ops).  If desired has ``{}`` we treat it as
    "delete everything in base".
    """
    # If the desired doc doesn't model named ranges at all, leave base untouched.
    if desired_dt.named_ranges is None:
        return []

    base_nr_dict: dict[str, NamedRanges] = base_dt.named_ranges or {}
    desired_nr_dict: dict[str, NamedRanges] = desired_dt.named_ranges or {}

    # Flatten to id→(name, ranges) for both sides.
    def _flatten(
        nr_dict: dict[str, NamedRanges],
    ) -> dict[str, tuple[str, list[Range]]]:
        result: dict[str, tuple[str, list[Range]]] = {}
        for _name, named_ranges_obj in nr_dict.items():
            for nr in named_ranges_obj.named_ranges or []:
                nr_id = nr.named_range_id
                name = nr.name or _name
                ranges = list(nr.ranges or [])
                if nr_id:
                    result[nr_id] = (name, ranges)
        return result

    base_flat = _flatten(base_nr_dict)
    desired_flat = _flatten(desired_nr_dict)

    ops: list[ReconcileOp] = []

    # Present in desired but not in base → insert
    for nr_id, (name, ranges) in desired_flat.items():
        if nr_id not in base_flat:
            ops.append(
                InsertNamedRangeOp(
                    tab_id=tab_id,
                    name=name,
                    named_range_id=nr_id,
                    ranges=ranges,
                )
            )
        else:
            # Same ID: compare ranges
            base_ranges = base_flat[nr_id][1]
            if ranges != base_ranges:
                # Delete old, create new
                ops.append(
                    DeleteNamedRangeOp(
                        tab_id=tab_id,
                        named_range_id=nr_id,
                        name=base_flat[nr_id][0],
                    )
                )
                ops.append(
                    InsertNamedRangeOp(
                        tab_id=tab_id,
                        name=name,
                        named_range_id=nr_id,
                        ranges=ranges,
                    )
                )
            # else: identical — no op

    # Present in base but not in desired → delete
    for nr_id, (name, _ranges) in base_flat.items():
        if nr_id not in desired_flat:
            ops.append(
                DeleteNamedRangeOp(
                    tab_id=tab_id,
                    named_range_id=nr_id,
                    name=name,
                )
            )

    return ops


# ---------------------------------------------------------------------------
# 8. Body content (and table cell recursion)
# ---------------------------------------------------------------------------


def _diff_body(
    tab_id: str,
    base_dt: DocumentTab,
    desired_dt: DocumentTab,
) -> list[ReconcileOp]:
    base_body = base_dt.body
    desired_body = desired_dt.body
    b_content: list[StructuralElement] = (base_body.content or []) if base_body else []
    d_content: list[StructuralElement] = (
        (desired_body.content or []) if desired_body else []
    )

    if b_content == d_content:
        return []

    desired_inline_objects: dict[str, InlineObject] = desired_dt.inline_objects or {}
    base_inline_objects: dict[str, InlineObject] = base_dt.inline_objects or {}
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
    base_content: list[StructuralElement],
    desired_content: list[StructuralElement],
    desired_inline_objects: dict[str, InlineObject] | None = None,
    base_inline_objects: dict[str, InlineObject] | None = None,
) -> list[ReconcileOp]:
    """For matched element pairs, recurse into table cells and check inline images."""
    ops: list[ReconcileOp] = []
    _desired_objs = desired_inline_objects or {}
    _base_objs = base_inline_objects or {}
    for match in alignment.matches:
        b_el = base_content[match.base_idx]
        d_el = desired_content[match.desired_idx]
        if b_el.table is not None and d_el.table is not None:
            # Extract the table's startIndex from the base element for lowering
            table_start_index: int = b_el.start_index or 0
            ops.extend(
                _diff_table(
                    tab_id=tab_id,
                    base_table=b_el.table,
                    desired_table=d_el.table,
                    table_label=f"body_table_{match.base_idx}",
                    table_start_index=table_start_index,
                    desired_inline_objects=_desired_objs,
                    base_inline_objects=_base_objs,
                )
            )
        elif b_el.paragraph is not None and d_el.paragraph is not None:
            ops.extend(
                _diff_paragraph_inline_images(
                    tab_id=tab_id,
                    base_para=b_el.paragraph,
                    desired_para=d_el.paragraph,
                    desired_inline_objects=_desired_objs,
                    base_inline_objects=_base_objs,
                )
            )
    return ops


def _diff_paragraph_inline_images(
    tab_id: str,
    base_para: Paragraph,
    desired_para: Paragraph,
    desired_inline_objects: dict[str, InlineObject],
    base_inline_objects: dict[str, InlineObject],  # noqa: ARG001 — reserved for future use
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

    base_elements: list[ParagraphElement] = base_para.elements or []
    desired_elements: list[ParagraphElement] = desired_para.elements or []

    # Collect inlineObjectIds present in each paragraph
    base_image_ids: set[str] = set()
    for pe in base_elements:
        ioe = pe.inline_object_element
        if ioe is not None:
            obj_id = ioe.inline_object_id
            if obj_id:
                base_image_ids.add(obj_id)

    desired_image_ids: set[str] = set()
    # Also build a map from id → element for index lookup
    desired_image_elements: dict[str, ParagraphElement] = {}
    for pe in desired_elements:
        ioe = pe.inline_object_element
        if ioe is not None:
            obj_id = ioe.inline_object_id
            if obj_id:
                desired_image_ids.add(obj_id)
                desired_image_elements[obj_id] = pe

    # Images added: present in desired but not in base
    for obj_id in desired_image_ids - base_image_ids:
        inline_obj = desired_inline_objects.get(obj_id)
        if inline_obj is None:
            content_uri = ""
            object_size = None
        else:
            props = inline_obj.inline_object_properties
            embedded = props.embedded_object if props else None
            image_props = embedded.image_properties if embedded else None
            content_uri = (image_props.content_uri or "") if image_props else ""
            object_size = embedded.size if embedded else None

        # Get the insert_index from the desired paragraph element
        pe = desired_image_elements[obj_id]
        insert_index: int = pe.start_index or 0

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
        ioe = pe.inline_object_element
        if ioe is None:
            continue
        obj_id = ioe.inline_object_id
        if not obj_id or obj_id in desired_image_ids:
            continue
        delete_index: int = pe.start_index or 0
        ops.append(
            DeleteInlineObjectOp(
                tab_id=tab_id,
                inline_object_id=obj_id,
                delete_index=delete_index,
            )
        )

    return ops


def _fields_mask_for_changed(
    base: dict[str, object],
    desired: dict[str, object],
    fields: list[str],
) -> str | None:
    """Compare specific camelCase fields between two model_dump dicts.

    Returns a comma-separated fields_mask string if any of the given fields
    differ, or None if they are identical.
    """
    changed: list[str] = []
    for field in fields:
        b_val = base.get(field)
        d_val = desired.get(field)
        if b_val != d_val:
            changed.append(field)
    if not changed:
        return None
    return ",".join(sorted(changed))


def _diff_table(
    tab_id: str,
    base_table: Table,
    desired_table: Table,
    table_label: str,
    table_start_index: int = 0,
    desired_inline_objects: dict[str, InlineObject] | None = None,
    base_inline_objects: dict[str, InlineObject] | None = None,
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
    base_rows: list[TableRow] = base_table.table_rows or []
    desired_rows: list[TableRow] = desired_table.table_rows or []

    for base_row_idx, desired_row_idx in row_matches:
        b_row: TableRow = base_rows[base_row_idx]
        d_row: TableRow = desired_rows[desired_row_idx]
        b_cells: list[TableCell] = b_row.table_cells or []
        d_cells: list[TableCell] = d_row.table_cells or []
        # Only emit cell content ops when row column counts match
        # (mismatched counts will be fixed by column structural ops in a later pass)
        if len(b_cells) != len(d_cells):
            continue
        for col_idx, (b_cell, d_cell) in enumerate(zip(b_cells, d_cells, strict=False)):
            b_content: list[StructuralElement] = b_cell.content or []
            d_content: list[StructuralElement] = d_cell.content or []
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
            b_cell_style: TableCellStyle = b_cell.table_cell_style or TableCellStyle()
            d_cell_style: TableCellStyle = d_cell.table_cell_style or TableCellStyle()
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
            b_cell_dict = b_cell_style.model_dump(by_alias=True, exclude_none=True)
            d_cell_dict = d_cell_style.model_dump(by_alias=True, exclude_none=True)
            fields_mask = _fields_mask_for_changed(
                b_cell_dict, d_cell_dict, _CELL_STYLE_FIELDS
            )
            if fields_mask is not None:
                ops.append(
                    UpdateTableCellStyleOp(
                        tab_id=tab_id,
                        table_start_index=table_start_index,
                        row_index=base_row_idx,
                        column_index=col_idx,
                        desired_style=d_cell_style,
                        fields_mask=fields_mask,
                    )
                )

        # Phase 4: Row style ops
        b_row_style: TableRowStyle | None = b_row.table_row_style
        d_row_style: TableRowStyle | None = d_row.table_row_style
        b_min_height = b_row_style.min_row_height if b_row_style else None
        d_min_height = d_row_style.min_row_height if d_row_style else None
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
    b_table_style: TableStyle | None = base_table.table_style
    d_table_style: TableStyle | None = desired_table.table_style
    b_col_props: list[TableColumnProperties] = (
        (b_table_style.table_column_properties or []) if b_table_style else []
    )
    d_col_props: list[TableColumnProperties] = (
        (d_table_style.table_column_properties or []) if d_table_style else []
    )
    _COL_FIELDS = ["width", "widthType"]
    for col_idx, (b_col, d_col) in enumerate(
        zip(b_col_props, d_col_props, strict=False)
    ):
        b_col_dict = b_col.model_dump(by_alias=True, exclude_none=True)
        d_col_dict = d_col.model_dump(by_alias=True, exclude_none=True)
        col_fields_mask = _fields_mask_for_changed(b_col_dict, d_col_dict, _COL_FIELDS)
        if col_fields_mask is not None:
            ops.append(
                UpdateTableColumnPropertiesOp(
                    tab_id=tab_id,
                    table_start_index=table_start_index,
                    column_index=col_idx,
                    width=d_col.width,
                    width_type=d_col.width_type,
                )
            )

    return ops


# ---------------------------------------------------------------------------
# Content alignment helper
# ---------------------------------------------------------------------------


def _align_content_sequence(
    base_content: list[StructuralElement],
    desired_content: list[StructuralElement],
) -> ContentAlignment:
    """Convert typed content lists to ContentNodes and run alignment DP."""
    if not base_content and not desired_content:
        return ContentAlignment(
            matches=[], base_deletes=[], desired_inserts=[], total_cost=0.0
        )

    def _nodes(content: list[StructuralElement]) -> list[ContentNode]:
        nodes = [content_node_from_element(el) for el in content]
        if nodes:
            nodes[-1].is_terminal = True
        return nodes

    base_nodes = _nodes(base_content)
    desired_nodes = _nodes(desired_content)
    return align_content(base_nodes, desired_nodes)
