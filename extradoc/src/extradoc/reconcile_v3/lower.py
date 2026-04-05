"""Op → typed Request translation for reconcile_v3.

Translates ``ReconcileOp`` objects produced by ``diff.py`` into typed
``Request`` objects from ``api_types._generated`` suitable for batchUpdate.

Strategy
--------
- Simple ops (named style updates, tab create/delete, header/footer create/delete)
  are lowered directly.
- Content ops (UpdateBodyContentOp) use index arithmetic against the base
  document: base content elements carry ``startIndex``/``endIndex`` directly
  from the API response.
- Ops that are structurally unsupported raise ``NotImplementedError`` with a
  clear diagnostic message.

Multi-batch ordering
--------------------
Batch 1: Structural creation — createHeader, createFooter, addDocumentTab.
Batch 2: All content operations (deleteContentRange, insertText, updateNamedStyle,
         deleteTab, deleteHeader, deleteFooter).
Batch 3: (currently empty; reserved for footnotes and named ranges)

Deferred IDs
------------
When a header/footer is created in Batch 1, its ID is not yet known.  The
``updateSectionStyle`` request in Batch 2 that attaches the header uses a
``DeferredID`` placeholder that ``resolve_deferred_placeholders`` resolves
after Batch 1 executes.
"""

from __future__ import annotations

import copy
import difflib
from itertools import groupby
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from extradoc.diffmerge import ContentAlignment

from extradoc.api_types._generated import (
    AddDocumentTabRequest,
    Bullet,
    CreateFooterRequest,
    CreateFooterRequestType,
    CreateFootnoteRequest,
    CreateHeaderRequest,
    CreateParagraphBulletsRequest,
    CreateParagraphBulletsRequestBulletPreset,
    DeferredID,
    DeleteContentRangeRequest,
    DeleteFooterRequest,
    DeleteHeaderRequest,
    DeleteParagraphBulletsRequest,
    DeleteTableColumnRequest,
    DeleteTableRowRequest,
    DeleteTabRequest,
    Dimension,
    InsertInlineImageRequest,
    InsertPageBreakRequest,
    InsertSectionBreakRequest,
    InsertTableColumnRequest,
    InsertTableRequest,
    InsertTableRowRequest,
    InsertTextRequest,
    Location,
    NamedStyle,
    Paragraph,
    ParagraphStyle,
    Range,
    Request,
    SectionStyle,
    StructuralElement,
    Tab,
    TableCellLocation,
    TableCellStyle,
    TableColumnProperties,
    TableRange,
    TableRowStyle,
    TabProperties,
    TextStyle,
    UpdateDocumentStyleRequest,
    UpdateParagraphStyleRequest,
    UpdateSectionStyleRequest,
    UpdateTableCellStyleRequest,
    UpdateTableColumnPropertiesRequest,
    UpdateTableRowStyleRequest,
    UpdateTextStyleRequest,
)
from extradoc.api_types._generated import (
    List as DocList,
)
from extradoc.diffmerge import (
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
from extradoc.diffmerge import (
    DiffOp as ReconcileOp,
)
from extradoc.indexer import utf16_len

# Slot → API type string
_HEADER_TYPE = {
    "DEFAULT": "DEFAULT",
    "FIRST_PAGE": "FIRST_PAGE",
    "EVEN_PAGE": "EVEN_PAGE",
}

_FOOTER_TYPE = {
    "DEFAULT": "DEFAULT",
    "FIRST_PAGE": "FIRST_PAGE",
    "EVEN_PAGE": "EVEN_PAGE",
}

_HEADER_SLOT_FIELD = {
    "DEFAULT": "defaultHeaderId",
    "FIRST_PAGE": "firstPageHeaderId",
    "EVEN_PAGE": "evenPageHeaderId",
}

_FOOTER_SLOT_FIELD = {
    "DEFAULT": "defaultFooterId",
    "FIRST_PAGE": "firstPageFooterId",
    "EVEN_PAGE": "evenPageFooterId",
}

# ParagraphStyle fields that are server-managed and cannot be set via the API.
# Including them in an updateParagraphStyle field mask causes a 400 error.
_PARA_STYLE_READONLY_FIELDS: frozenset[str] = frozenset(
    {
        "headingId",  # assigned by server when namedStyleType=HEADING_*
    }
)

# A resolved string ID or a DeferredID placeholder that the executor
# will substitute after an earlier batch completes.
_StrOrDeferred = str | DeferredID


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def lower_ops(ops: list[ReconcileOp]) -> list[Request]:
    """Lower a list of ReconcileOps to typed Request objects (single batch).

    For ops whose lowering is not yet implemented, raises ``NotImplementedError``
    with a message identifying the op type and confirming the op was detected.
    """
    requests: list[Request] = []
    for op in ops:
        requests.extend(_lower_one(op))
    return requests


def lower_batches(
    ops: list[ReconcileOp],
    desired_lists_by_tab: dict[str, dict[str, DocList]] | None = None,
    base_lists_by_tab: dict[str, dict[str, DocList]] | None = None,
) -> list[list[Request]]:
    """Lower ops into an ordered list of request batches.

    Batch 0: Structural creation (createHeader, createFooter, addDocumentTab).
    Batch 1: All content + style + structural-delete operations.
    Batch 2: Footnote operations (reserved; currently empty).

    Returns only non-empty batches.

    Deferred-ID placeholders in Batch 1 refer to Batch 0 responses and must
    be resolved via ``resolve_deferred_placeholders`` before execution.

    Parameters
    ----------
    ops:
        The list of ReconcileOp objects to lower.
    desired_lists_by_tab:
        Optional mapping of tab_id → lists dict from the desired document.
        Used to infer bullet presets when inserting or updating bullet paragraphs.
        If not provided, bullet presets fall back to BULLET_DISC_CIRCLE_SQUARE.
    base_lists_by_tab:
        Optional mapping of tab_id → lists dict from the base document.
        Used alongside desired_lists_by_tab to detect list-type changes when
        both base and desired have the same synthetic list ID.
    """
    batch0: list[Request] = []  # structural creates
    batch1: list[Request] = []  # content + style + structural deletes
    batch2: list[Request] = []  # footnotes (future)

    _desired_lists_by_tab: dict[str, dict[str, DocList]] = desired_lists_by_tab or {}
    _base_lists_by_tab: dict[str, dict[str, DocList]] = base_lists_by_tab or {}

    # Track which requests in batch0 return IDs, keyed by (kind, slot, tab_id)
    # so that batch1 content-attachment requests can reference them.
    batch0_index: dict[str, int] = {}  # key → index in batch0

    for op in ops:
        match op:
            # ---------------------------------------------------------------- #
            # Structural creates → batch 0
            # ---------------------------------------------------------------- #
            case CreateHeaderOp():
                key = f"header:{op.tab_id}:{op.section_slot}"
                req_index = len(batch0)
                batch0_index[key] = req_index
                batch0.append(
                    _make_create_header(
                        tab_id=op.tab_id,
                        header_type=_HEADER_TYPE[op.section_slot],
                    )
                )
                # Batch1: attach header via updateSectionStyle with deferred ID
                deferred_id = DeferredID(
                    placeholder=f"header_{req_index}",
                    batch_index=0,
                    request_index=req_index,
                    response_path="createHeader.headerId",
                )
                field_name = _HEADER_SLOT_FIELD[op.section_slot]
                batch1.append(
                    _make_update_section_style_deferred(
                        tab_id=op.tab_id,
                        field_name=field_name,
                        deferred_id=deferred_id,
                    )
                )
                # Batch1: insert header content
                batch1.extend(
                    _lower_content_insert(
                        content=op.desired_content,
                        start_index=1,
                        tab_id=op.tab_id,
                        segment_id=deferred_id,
                    )
                )

            case CreateFooterOp():
                key = f"footer:{op.tab_id}:{op.section_slot}"
                req_index = len(batch0)
                batch0_index[key] = req_index
                batch0.append(
                    _make_create_footer(
                        tab_id=op.tab_id,
                        footer_type=_FOOTER_TYPE[op.section_slot],
                    )
                )
                deferred_id = DeferredID(
                    placeholder=f"footer_{req_index}",
                    batch_index=0,
                    request_index=req_index,
                    response_path="createFooter.footerId",
                )
                field_name = _FOOTER_SLOT_FIELD[op.section_slot]
                batch1.append(
                    _make_update_section_style_deferred(
                        tab_id=op.tab_id,
                        field_name=field_name,
                        deferred_id=deferred_id,
                    )
                )
                batch1.extend(
                    _lower_content_insert(
                        content=op.desired_content,
                        start_index=1,
                        tab_id=op.tab_id,
                        segment_id=deferred_id,
                    )
                )

            case InsertTabOp():
                props = op.desired_tab.tab_properties
                title = props.title if props and props.title else "Untitled"
                index = props.index if props else None
                parent_tab_id = props.parent_tab_id if props else None
                req_index = len(batch0)
                batch0.append(
                    _make_add_document_tab(
                        title=title,
                        index=index,
                        parent_tab_id=parent_tab_id,
                    )
                )
                deferred_tab_id = DeferredID(
                    placeholder=f"tab_{req_index}",
                    batch_index=0,
                    request_index=req_index,
                    response_path="addDocumentTab.tabProperties.tabId",
                )
                body_content = _extract_tab_body_content(op.desired_tab)
                if body_content:
                    batch1.extend(
                        _lower_content_insert(
                            content=body_content,
                            start_index=1,
                            tab_id=deferred_tab_id,
                            segment_id=None,
                        )
                    )

            # ---------------------------------------------------------------- #
            # Structural deletes → batch 1
            # ---------------------------------------------------------------- #
            case DeleteHeaderOp():
                batch1.append(
                    _make_delete_header(
                        header_id=op.base_header_id,
                        tab_id=op.tab_id,
                    )
                )

            case DeleteFooterOp():
                batch1.append(
                    _make_delete_footer(
                        footer_id=op.base_footer_id,
                        tab_id=op.tab_id,
                    )
                )

            case DeleteTabOp():
                batch1.append(_make_delete_tab(tab_id=op.base_tab_id))

            # ---------------------------------------------------------------- #
            # NamedStyles → batch 1
            # ---------------------------------------------------------------- #
            case UpdateNamedStyleOp():
                batch1.append(
                    _make_update_named_style(
                        tab_id=op.tab_id,
                        style=op.desired_style,
                    )
                )

            case InsertNamedStyleOp():
                batch1.append(
                    _make_update_named_style(
                        tab_id=op.tab_id,
                        style=op.desired_style,
                    )
                )

            case DeleteNamedStyleOp():
                # Named styles cannot be truly deleted via the API.
                # Raise so callers know this is unsupported.
                raise NotImplementedError(
                    f"lowering for DeleteNamedStyleOp not supported — "
                    f"Google Docs API does not support removing a namedStyle. "
                    f"(tab_id={op.tab_id!r}, namedStyleType={op.named_style_type!r})"
                )

            # ---------------------------------------------------------------- #
            # DocumentStyle → batch 1
            # ---------------------------------------------------------------- #
            case UpdateDocumentStyleOp():
                # op.desired_style carries the full desired DocumentStyle;
                # op.fields_mask restricts the update to only changed fields.
                batch1.append(
                    Request(
                        update_document_style=UpdateDocumentStyleRequest(
                            document_style=op.desired_style,
                            fields=op.fields_mask,
                            tab_id=op.tab_id if op.tab_id else None,
                        )
                    )
                )

            # ---------------------------------------------------------------- #
            # Lists — InsertListOp is handled implicitly via paragraph bullets;
            # DeleteListOp can be ignored (bullets are removed via
            # deleteParagraphBullets on content).  UpdateListOp is unsupported.
            # ---------------------------------------------------------------- #
            case InsertListOp():
                # List defs are created implicitly by createParagraphBullets;
                # no explicit request needed.
                pass

            case DeleteListOp():
                # List cleanup is handled implicitly by deleteParagraphBullets
                # on the paragraph content; no explicit request needed here.
                pass

            case UpdateListOp():
                raise NotImplementedError(
                    f"lowering for UpdateListOp not supported — "
                    f"list definitions cannot be edited via batchUpdate. "
                    f"(tab_id={op.tab_id!r}, list_id={op.list_id!r})"
                )

            # ---------------------------------------------------------------- #
            # InlineObjects
            # ---------------------------------------------------------------- #
            case UpdateInlineObjectOp():
                raise NotImplementedError(
                    f"lowering for UpdateInlineObjectOp not supported — "
                    f"inline object properties cannot be edited via batchUpdate. "
                    f"(tab_id={op.tab_id!r}, inline_object_id={op.inline_object_id!r})"
                )

            case InsertInlineObjectOp():
                # Insert an inline image via insertInlineImage → batch 1
                batch1.append(
                    Request(
                        insert_inline_image=InsertInlineImageRequest(
                            uri=op.content_uri,
                            location=Location(
                                index=op.insert_index,
                                segment_id=op.tab_id if op.tab_id else None,
                            ),
                            object_size=op.object_size,
                        )
                    )
                )

            case DeleteInlineObjectOp():
                # Delete the inlineObjectElement (occupies exactly 1 character)
                # via deleteContentRange → batch 1
                batch1.append(
                    _make_delete_content_range(
                        start_index=op.delete_index,
                        end_index=op.delete_index + 1,
                        tab_id=op.tab_id,
                        segment_id=None,
                    )
                )

            # ---------------------------------------------------------------- #
            # Header / footer content updates → batch 1
            # ---------------------------------------------------------------- #
            case UpdateHeaderContentOp():
                batch1.extend(
                    _lower_story_content_update(
                        op.alignment,
                        base_content=op.base_content,
                        desired_content=op.desired_content,
                        tab_id=op.tab_id,
                        segment_id=op.header_id,
                        desired_lists=_desired_lists_by_tab.get(op.tab_id, {}),
                        base_lists=_base_lists_by_tab.get(op.tab_id, {}),
                    )
                )

            case UpdateFooterContentOp():
                batch1.extend(
                    _lower_story_content_update(
                        op.alignment,
                        base_content=op.base_content,
                        desired_content=op.desired_content,
                        tab_id=op.tab_id,
                        segment_id=op.footer_id,
                        desired_lists=_desired_lists_by_tab.get(op.tab_id, {}),
                        base_lists=_base_lists_by_tab.get(op.tab_id, {}),
                    )
                )

            # ---------------------------------------------------------------- #
            # Footnotes — batch 0 (createFootnote) + batch 1 (content)
            # ---------------------------------------------------------------- #
            case InsertFootnoteOp():
                if op.anchor_index < 0:
                    raise NotImplementedError(
                        f"lowering for InsertFootnoteOp: anchor_index is unknown "
                        f"(no footnoteReference with index found in desired body). "
                        f"(tab_id={op.tab_id!r}, footnote_id={op.footnote_id!r})"
                    )
                req_index = len(batch0)
                batch0.append(
                    _make_create_footnote(
                        index=op.anchor_index,
                        tab_id=op.tab_id,
                    )
                )
                deferred_fn_id = DeferredID(
                    placeholder=f"footnote_{req_index}",
                    batch_index=0,
                    request_index=req_index,
                    response_path="createFootnote.footnoteId",
                )
                batch1.extend(
                    _lower_content_insert(
                        content=op.desired_content,
                        start_index=1,
                        tab_id=op.tab_id,
                        segment_id=deferred_fn_id,
                    )
                )

            case DeleteFootnoteOp():
                # Deleting a footnote is done by removing its footnoteReference
                # element (a single character) from the base document body.
                # The footnote story is automatically cleaned up by the API.
                # The base_doc is not available here, so we rely on the op
                # carrying the ref_index set by the diff layer.
                if op.ref_index < 0:
                    raise NotImplementedError(
                        f"lowering for DeleteFootnoteOp: ref_index is unknown "
                        f"(no footnoteReference with index found in base body). "
                        f"(tab_id={op.tab_id!r}, footnote_id={op.footnote_id!r})"
                    )
                # footnoteReference occupies exactly 1 character
                batch1.append(
                    _make_delete_content_range(
                        start_index=op.ref_index,
                        end_index=op.ref_index + 1,
                        tab_id=op.tab_id,
                        segment_id=None,
                    )
                )

            case UpdateFootnoteContentOp():
                batch1.extend(
                    _lower_story_content_update(
                        op.alignment,
                        base_content=op.base_content,
                        desired_content=op.desired_content,
                        tab_id=op.tab_id,
                        segment_id=op.footnote_id,
                        desired_lists=_desired_lists_by_tab.get(op.tab_id, {}),
                        base_lists=_base_lists_by_tab.get(op.tab_id, {}),
                    )
                )

            # ---------------------------------------------------------------- #
            # Body / story content → batch 1
            # ---------------------------------------------------------------- #
            case UpdateBodyContentOp():
                batch1.extend(
                    _lower_story_content_update(
                        op.alignment,
                        base_content=op.base_content,
                        desired_content=op.desired_content,
                        tab_id=op.tab_id,
                        segment_id=None,
                        desired_lists=_desired_lists_by_tab.get(op.tab_id, {}),
                        base_lists=_base_lists_by_tab.get(op.tab_id, {}),
                    )
                )

            # ---------------------------------------------------------------- #
            # Table structural ops → batch 1
            # ---------------------------------------------------------------- #
            case InsertTableRowOp():
                batch1.append(
                    _make_insert_table_row(
                        table_start_index=op.table_start_index,
                        row_index=op.row_index,
                        insert_below=op.insert_below,
                        tab_id=op.tab_id,
                    )
                )

            case DeleteTableRowOp():
                batch1.append(
                    _make_delete_table_row(
                        table_start_index=op.table_start_index,
                        row_index=op.row_index,
                        tab_id=op.tab_id,
                    )
                )

            case InsertTableColumnOp():
                batch1.append(
                    _make_insert_table_column(
                        table_start_index=op.table_start_index,
                        column_index=op.column_index,
                        insert_right=op.insert_right,
                        tab_id=op.tab_id,
                    )
                )

            case DeleteTableColumnOp():
                batch1.append(
                    _make_delete_table_column(
                        table_start_index=op.table_start_index,
                        column_index=op.column_index,
                        tab_id=op.tab_id,
                    )
                )

            # ---------------------------------------------------------------- #
            # Table style ops → batch 1
            # ---------------------------------------------------------------- #
            case UpdateTableCellStyleOp():
                batch1.append(
                    _make_update_table_cell_style(
                        table_start_index=op.table_start_index,
                        row_index=op.row_index,
                        column_index=op.column_index,
                        desired_style=op.desired_style,
                        fields_mask=op.fields_mask,
                        tab_id=op.tab_id,
                    )
                )

            case UpdateTableRowStyleOp():
                batch1.append(
                    _make_update_table_row_style(
                        table_start_index=op.table_start_index,
                        row_index=op.row_index,
                        min_row_height=op.min_row_height,
                        tab_id=op.tab_id,
                    )
                )

            case UpdateTableColumnPropertiesOp():
                batch1.append(
                    _make_update_table_column_properties(
                        table_start_index=op.table_start_index,
                        column_index=op.column_index,
                        width=op.width,
                        width_type=op.width_type,
                        tab_id=op.tab_id,
                    )
                )

            case _:
                raise NotImplementedError(
                    f"lowering for op type {type(op).__name__!r} not yet implemented"
                )

    batches: list[list[Request]] = []
    if batch0:
        batches.append(batch0)
    if batch1:
        batches.append(batch1)
    if batch2:
        batches.append(batch2)
    return batches


def _lower_one(op: ReconcileOp) -> list[Request]:
    """Lower a single op to zero or more Request objects (single-batch mode).

    This is a convenience wrapper around ``lower_batches`` that flattens all
    batches into one list.  It raises for ops that cannot be lowered.
    """
    batches = lower_batches([op])
    return [req for batch in batches for req in batch]


# ---------------------------------------------------------------------------
# Bullet preset helpers (ported from reconcile/_generators.py)
# ---------------------------------------------------------------------------

# Maps level-0 glyphType to the createParagraphBullets preset string
_GLYPH_TYPE_TO_PRESET: dict[str, str] = {
    "DECIMAL": "NUMBERED_DECIMAL_NESTED",
    "UPPER_ALPHA": "NUMBERED_UPPERALPHA_ALPHA_ROMAN",
    "ALPHA": "NUMBERED_DECIMAL_ALPHA_ROMAN",
    "UPPER_ROMAN": "NUMBERED_UPPERROMAN_UPPERALPHA_DECIMAL",
    "ROMAN": "NUMBERED_UPPERROMAN_UPPERALPHA_DECIMAL",
    "ZERO_DECIMAL": "NUMBERED_ZERODECIMAL_ALPHA_ROMAN",
}

# Maps level-0 glyphSymbol to the createParagraphBullets preset string
_GLYPH_SYMBOL_TO_PRESET: dict[str, str] = {
    "●": "BULLET_DISC_CIRCLE_SQUARE",
    "❖": "BULLET_DIAMONDX_ARROW3D_SQUARE",
    "☐": "BULLET_CHECKBOX",
    "➔": "BULLET_ARROW_DIAMOND_DISC",
    "★": "BULLET_STAR_CIRCLE_SQUARE",
    "➢": "BULLET_ARROW3D_CIRCLE_SQUARE",
    "◀": "BULLET_LEFTTRIANGLE_DIAMOND_DISC",
}

_DEFAULT_BULLET_PRESET = "BULLET_DISC_CIRCLE_SQUARE"


def _infer_bullet_preset_from_model(bullet: Bullet, lists: dict[str, DocList]) -> str:
    """Infer the createParagraphBullets preset from a typed Bullet and lists."""
    list_id = bullet.list_id
    if not list_id or not lists or list_id not in lists:
        return _DEFAULT_BULLET_PRESET

    list_obj = lists[list_id]
    lp = list_obj.list_properties
    if not lp:
        return _DEFAULT_BULLET_PRESET
    nesting = lp.nesting_levels
    if not nesting:
        return _DEFAULT_BULLET_PRESET
    level_0 = nesting[0]
    glyph_type: str = level_0.glyph_type or ""
    glyph_symbol: str = level_0.glyph_symbol or ""

    # Numbered list: a real glyphType is set (not NONE / GLYPH_TYPE_UNSPECIFIED)
    if glyph_type and glyph_type not in ("GLYPH_TYPE_UNSPECIFIED", "NONE", ""):
        return _GLYPH_TYPE_TO_PRESET.get(glyph_type, "NUMBERED_DECIMAL_NESTED")

    # Checkbox: GLYPH_TYPE_UNSPECIFIED with no glyph symbol
    if glyph_type == "GLYPH_TYPE_UNSPECIFIED":
        return "BULLET_CHECKBOX"

    # Unordered: glyph symbol determines the preset
    if glyph_symbol:
        return _GLYPH_SYMBOL_TO_PRESET.get(glyph_symbol, _DEFAULT_BULLET_PRESET)

    return _DEFAULT_BULLET_PRESET


def _make_create_paragraph_bullets(
    *,
    start: int,
    end: int,
    preset: str,
    tab_id: _StrOrDeferred,
    segment_id: _StrOrDeferred | None,
) -> Request:
    """Build a createParagraphBullets Request."""
    return Request(
        create_paragraph_bullets=CreateParagraphBulletsRequest(
            range=Range(
                start_index=start,
                end_index=end,
                tab_id=tab_id if tab_id else None,
                segment_id=segment_id if segment_id else None,
            ),
            bullet_preset=CreateParagraphBulletsRequestBulletPreset(preset),
        )
    )


def _make_delete_paragraph_bullets(
    *,
    start: int,
    end: int,
    tab_id: _StrOrDeferred,
    segment_id: _StrOrDeferred | None,
) -> Request:
    """Build a deleteParagraphBullets Request."""
    return Request(
        delete_paragraph_bullets=DeleteParagraphBulletsRequest(
            range=Range(
                start_index=start,
                end_index=end,
                tab_id=tab_id if tab_id else None,
                segment_id=segment_id if segment_id else None,
            ),
        )
    )


# ---------------------------------------------------------------------------
# Content update helpers
# ---------------------------------------------------------------------------


def _lower_story_content_update(
    alignment: ContentAlignment,
    *,
    base_content: list[StructuralElement],
    desired_content: list[StructuralElement],
    tab_id: str,
    segment_id: str | None,
    desired_lists: dict[str, DocList] | None = None,
    base_lists: dict[str, DocList] | None = None,
) -> list[Request]:
    """Lower a ContentAlignment into delete/insert/update Request objects.

    Strategy
    --------
    We process operations in reverse document order (highest index first) so
    that each deletion/insertion does not affect the indices of earlier
    elements.

    1. Delete elements in ``alignment.base_deletes`` (in reverse order).
    2. Insert elements in ``alignment.desired_inserts`` at the appropriate
       position in the post-deletion document.
    3. Update matched elements whose content differs (in-place text replacement).

    Only paragraphs with simple text runs are fully lowered.  Tables and other
    structural elements raise ``NotImplementedError`` for insert/update — delete
    is always supported via ``deleteContentRange``.

    Index arithmetic
    ----------------
    The base content elements carry ``startIndex``/``endIndex`` from the
    Google Docs API response.  We use these directly for deletions.  For
    insertions, we compute the target position based on the surrounding matched
    elements.

    The terminal paragraph (last element) is never deleted — it is always
    matched.  Insertions before the terminal are handled by inserting before
    the terminal's startIndex.
    """
    requests: list[Request] = []

    # Sort deletes in descending base_idx order so each delete does not
    # invalidate indices for subsequent deletes.
    sorted_deletes = sorted(alignment.base_deletes, reverse=True)

    for base_idx in sorted_deletes:
        el = base_content[base_idx]
        start, end = _element_range(el)
        if start is None or end is None:
            # Element has no index info — skip (shouldn't happen on real docs)
            continue
        requests.append(
            _make_delete_content_range(
                start_index=start,
                end_index=end,
                tab_id=tab_id,
                segment_id=segment_id,
            )
        )

    # Insertions: we need to find where to insert each desired element.
    # Strategy: for each desired_insert index, find the closest preceding
    # matched element and insert after it, or before the terminal if none.
    #
    # We process inserts in ascending order (they are into the post-deletion
    # document).  Since we process deletes first (in reverse), the base indices
    # have been consumed; the positions of surviving elements shift by the
    # cumulative character count deleted before them.
    #
    # For simplicity in this v3 experiment, we use the desired element's text
    # and find the insertion point using the base document's known element
    # indices BEFORE deletions, then apply an offset for the characters deleted
    # before that point.
    #
    # We compute the insertion point for each desired_insert by looking at the
    # alignment: find the last matched base element whose base_idx < the
    # "virtual" position and use its endIndex (adjusted for prior deletions).

    if alignment.desired_inserts:
        # Build a map from desired_idx → base insertion point (startIndex of
        # the NEXT surviving base element after where we want to insert).
        # For the simple case, we insert before the next matched element or
        # before the terminal.
        insert_requests = _plan_insertions(
            alignment=alignment,
            base_content=base_content,
            desired_content=desired_content,
            tab_id=tab_id,
            segment_id=segment_id,
            desired_lists=desired_lists or {},
        )
        requests.extend(insert_requests)

    # Handle matched elements whose content differs (text updates).
    # The update requests must use coordinates that account for whole-element
    # deletions (base_deletes) applied earlier in this batch.  Compute the
    # number of characters deleted BEFORE each matched element's startIndex so
    # we can shift the generated request indices accordingly.
    deleted_sizes: dict[int, int] = {}
    for base_idx in alignment.base_deletes:
        el = base_content[base_idx]
        start, end = _element_range(el)
        if start is not None and end is not None:
            deleted_sizes[base_idx] = end - start
        else:
            deleted_sizes[base_idx] = 0

    # Process matched element updates in DESCENDING start-index order.
    # Each in-place paragraph update may grow or shrink the paragraph.  If we
    # processed in ascending order, a size change in paragraph N would shift
    # the indices of paragraph N+1, making the pre-computed requests for N+1
    # use stale positions.  Descending order ensures that updates to later
    # (higher-index) elements are emitted first; a size change there only
    # affects positions below it, which we haven't emitted yet — so they will
    # use the correct original positions (no cumulative shift needed).
    matches_desc = sorted(
        alignment.matches,
        key=lambda m: _element_start(base_content[m.base_idx]) or 0,
        reverse=True,
    )
    for match in matches_desc:
        b_el = base_content[match.base_idx]
        d_el = desired_content[match.desired_idx]
        if b_el == d_el:
            continue
        b_el_start = _element_start(b_el)
        shift = (
            _deleted_chars_before(
                deleted_sizes=deleted_sizes,
                base_content=base_content,
                before_pos=b_el_start,
            )
            if b_el_start is not None
            else 0
        )
        update_reqs = _lower_element_update(
            base_el=b_el,
            desired_el=d_el,
            tab_id=tab_id,
            segment_id=segment_id,
            pre_delete_shift=shift,
            desired_lists=desired_lists or {},
            base_lists=base_lists or {},
        )
        requests.extend(update_reqs)

    return requests


def _plan_insertions(
    *,
    alignment: ContentAlignment,
    base_content: list[StructuralElement],
    desired_content: list[StructuralElement],
    tab_id: str,
    segment_id: str | None,
    desired_lists: dict[str, DocList] | None = None,
) -> list[Request]:
    """Plan insertion requests for desired_inserts.

    For each desired index to insert, we determine the insertion position in
    the base document's coordinate space (before deletes are applied) and
    generate an insertText or insertTable request.

    The net offset calculation
    --------------------------
    After processing all deletes (highest first), positions shift.  We must
    adjust the insertion indices by the total characters deleted BEFORE the
    target position.

    Since we cannot easily compute post-delete positions without simulating
    the entire batchUpdate, we use a forward-pass approach:

    - Sort desired_inserts ascending.
    - For each insert, find the base index to insert BEFORE by looking at the
      alignment for the nearest match or using the terminal element.
    - Compute offset adjustment = sum of sizes of deleted base elements whose
      startIndex < insertion_point.

    This gives the correct insertion index after all deletes have been applied.
    Always uses explicit indices — the real terminal paragraph has a real
    startIndex that is a valid insertion point.
    """
    if not alignment.desired_inserts:
        return []

    # Build sorted list of matched (base_idx, desired_idx) pairs
    matches_sorted = sorted(alignment.matches, key=lambda m: m.desired_idx)

    # Precompute sizes of deleted elements (for offset adjustment)
    deleted_sizes: dict[int, int] = {}
    for base_idx in alignment.base_deletes:
        el = base_content[base_idx]
        start, end = _element_range(el)
        if start is not None and end is not None:
            deleted_sizes[base_idx] = end - start
        else:
            deleted_sizes[base_idx] = 0

    # Phase 1: Compute (insert_pos, desired_idx, element_requests) for each insert.
    # We collect them first so we can reorder within same-position groups.
    planned: list[tuple[int, int, list[Request]]] = []

    for desired_idx in sorted(alignment.desired_inserts):
        # Find the base insertion point: the startIndex of the next surviving
        # base element after this desired_idx in the alignment.
        # "after this desired_idx" = first match with desired_idx > desired_idx.
        insert_before_base_idx: int | None = None
        for m in matches_sorted:
            if m.desired_idx > desired_idx:
                insert_before_base_idx = m.base_idx
                break

        if insert_before_base_idx is not None:
            base_el = base_content[insert_before_base_idx]
            raw_insert_pos = _element_start(base_el)
        else:
            # Insert before terminal (last element in base_content)
            terminal = base_content[-1]
            raw_insert_pos = _element_start(terminal)

        if raw_insert_pos is None:
            # No index info — skip
            continue

        # Adjust for characters deleted before this insertion point
        offset = _deleted_chars_before(
            deleted_sizes=deleted_sizes,
            base_content=base_content,
            before_pos=raw_insert_pos,
        )
        insert_pos = raw_insert_pos - offset

        d_el = desired_content[desired_idx]
        reqs = _lower_element_insert(
            el=d_el,
            index=insert_pos,
            tab_id=tab_id,
            segment_id=segment_id,
            desired_lists=desired_lists or {},
        )
        planned.append((insert_pos, desired_idx, reqs))

    # Phase 2: Emit requests in the correct order.
    #
    # When multiple elements are inserted at the SAME index, Google Docs
    # processes requests sequentially.  Each insertText(index=X) pushes all
    # existing content at X upward.  So inserting [A, B, C] all at X gives the
    # final order [C, B, A] — reversed.
    #
    # Fix: within a same-position group, reverse the emission order (emit the
    # element that should appear LAST first).  Elements with different target
    # positions are emitted in ascending position order (lower positions first),
    # which is correct because inserting at a lower position does not affect the
    # absolute position of a later insert at a higher position.
    #
    # Additionally, when multiple consecutive items in the same logical list are
    # all inserted at the same position, we must emit a SINGLE createParagraphBullets
    # covering the entire range.  Individual per-item calls create separate lists.
    requests: list[Request] = []

    # Sort entries by insert_pos DESCENDING, then desired_idx ascending within a group.
    #
    # Rationale: requests are processed sequentially by the API.  Inserting at
    # a lower position shifts all higher-position content rightward, which would
    # corrupt positions in subsequent requests.  By emitting from the HIGHEST
    # position down to the LOWEST, each group's requests run before any
    # lower-position group can shift its content.  Within a same-position group
    # we still need the items in their original desired_idx order (so that the
    # final reverse-insertion trick places them correctly).
    planned.sort(key=lambda t: (-t[0], t[1]))
    for _pos, group_iter in groupby(planned, key=lambda t: t[0]):
        group = list(group_iter)
        # Within the group, emit in REVERSE desired_idx order so that the first
        # desired element ends up first after all same-position inserts land.
        # We split each element's reqs into: insertText, createParagraphBullets,
        # and style requests (updateParagraphStyle, updateTextStyle).  Same-list
        # items have their createParagraphBullets merged into a single call.
        requests.extend(_emit_same_position_group(group))

    return requests


def _shift_request_indices(
    reqs: list[Request],
    offset: int,
) -> list[Request]:
    """Return copies of style requests with all index values shifted by ``offset``.

    Only shifts ``updateParagraphStyle`` and ``updateTextStyle`` requests.
    Other request types are returned unchanged.  The shift is applied to the
    ``range`` field's ``startIndex`` and ``endIndex``.
    """
    if offset == 0:
        return reqs

    shifted: list[Request] = []
    for req in reqs:
        if req.update_paragraph_style is not None or req.update_text_style is not None:
            req = copy.deepcopy(req)
            inner = req.update_paragraph_style or req.update_text_style
            assert inner is not None
            rng = inner.range
            if rng is not None:
                if rng.start_index is not None:
                    rng.start_index += offset
                if rng.end_index is not None:
                    rng.end_index += offset
        shifted.append(req)
    return shifted


def _get_insert_text_content(req: Request) -> str | None:
    """Extract the text from an insertText request, or None."""
    if req.insert_text is not None and req.insert_text.text is not None:
        return req.insert_text.text
    return None


def _get_create_bullets_info(
    req: Request,
) -> tuple[str, str, str | DeferredID | None] | None:
    """Extract (preset, tab_id_str, segment_id) from a createParagraphBullets request.

    Returns None if the request is not createParagraphBullets.
    """
    if req.create_paragraph_bullets is None:
        return None
    cb = req.create_paragraph_bullets
    preset = str(cb.bullet_preset) if cb.bullet_preset else ""
    tab_id = ""
    segment_id = None
    if cb.range is not None:
        tab_id_val = cb.range.tab_id
        tab_id = str(tab_id_val) if tab_id_val is not None else ""
        segment_id = cb.range.segment_id
    return (preset, tab_id, segment_id)


def _emit_same_position_group(
    group: list[tuple[int, int, list[Request]]],
) -> list[Request]:
    """Emit requests for a same-position insertion group.

    For bullet items that all share the same preset+tab, we suppress individual
    createParagraphBullets calls and emit a SINGLE call that covers the total
    inserted text range.  This ensures all same-preset items land in the SAME
    Google Docs list rather than each getting their own list.

    The ordering:
    1. All insertText calls in reverse desired_idx order (so item 1 ends up first)
    2. One merged createParagraphBullets per distinct (preset, tabId) combination,
       covering the full range of items in that list
    3. All style requests (updateParagraphStyle, updateTextStyle)

    Items in different lists (different presets) or non-bullet items fall back to
    the standard per-element order within their own group.
    """
    if len(group) == 1:
        # Single item — no merging needed
        return group[0][2]

    # Separate each element's requests into components.
    # Items arrive in reverse desired_idx order (last desired item first),
    # which is the order we insert them at position P.  After all inserts,
    # the items appear in desired_idx order in the document:
    #   item[desired_idx=0] at P, item[desired_idx=1] at P+len0, ...
    #
    # Per-element structure: (insert_req, create_bullets_req_or_None, style_reqs)
    per_element: list[tuple[Request, Request | None, list[Request]]] = []

    for _insert_pos, _desired_idx, reqs in reversed(group):
        ins: Request | None = None
        cb: Request | None = None
        style_reqs: list[Request] = []
        for req in reqs:
            if req.insert_text is not None:
                ins = req
            elif req.create_paragraph_bullets is not None:
                cb = req
            else:
                style_reqs.append(req)
        if ins is not None:
            per_element.append((ins, cb, style_reqs))

    # Now per_element[0] = LAST desired item (inserted first at P), so after all
    # inserts, the DOCUMENT ORDER is the reverse of per_element's order.
    # We need to compute positions in document order (ascending desired_idx).
    # The items in document order (desired order) are: reversed(per_element).
    desired_order = list(reversed(per_element))

    # Compute each item's document position = base_pos + cumulative len of prior items.
    # The base position is the insert_pos from the group (all items share the same pos).
    base_pos = group[0][0]  # insert_pos from the first planned entry

    combined_insert_texts: list[Request] = []
    merged_create_bullets: list[Request] = []
    all_style_reqs: list[Request] = []

    # Collect insertTexts in the reversed order (as they will be emitted)
    for ins_req, _cb, _s in per_element:
        combined_insert_texts.append(ins_req)

    # Compute merged createParagraphBullets by grouping consecutive same-preset
    # items in DESIRED (document) order, with correct cumulative offsets.
    #
    # Style requests (updateParagraphStyle, updateTextStyle) from
    # _lower_paragraph_insert were computed with index=base_pos for every item
    # (all insertions share the same insert_pos).  After all insertText calls
    # have run, item k actually lives at base_pos + cumulative_before_k.  We
    # must shift every range in the style requests by that cumulative offset.
    cumulative = 0
    i = 0
    while i < len(desired_order):
        ins_req, cb_req, s_reqs = desired_order[i]
        text_content = _get_insert_text_content(ins_req)
        item_len = utf16_len(text_content) if text_content else 0
        all_style_reqs.extend(_shift_request_indices(s_reqs, cumulative))
        if cb_req is None:
            # Non-bullet item: just advance cumulative offset
            cumulative += item_len
            i += 1
            continue
        # Start of a bullet run — collect consecutive items with the same preset
        cb_info = _get_create_bullets_info(cb_req)
        assert cb_info is not None
        preset, tab_id_str, segment_id = cb_info
        run_start = base_pos + cumulative
        run_len = item_len
        j = i + 1
        inner_cumulative = item_len  # cumulative within the bullet run
        while j < len(desired_order):
            next_ins, next_cb, next_s_reqs = desired_order[j]
            if next_cb is None:
                break
            next_cb_info = _get_create_bullets_info(next_cb)
            assert next_cb_info is not None
            next_preset, next_tab, next_seg = next_cb_info
            if (next_preset, next_tab, str(next_seg) if next_seg else None) != (
                preset,
                tab_id_str,
                str(segment_id) if segment_id else None,
            ):
                break
            all_style_reqs.extend(
                _shift_request_indices(next_s_reqs, cumulative + inner_cumulative)
            )
            next_text = _get_insert_text_content(next_ins)
            next_item_len = utf16_len(next_text) if next_text else 0
            run_len += next_item_len
            inner_cumulative += next_item_len
            j += 1
        # Emit ONE createParagraphBullets for this run
        merged_range = Range(
            start_index=run_start,
            end_index=run_start + run_len,
            tab_id=tab_id_str if tab_id_str else None,
            segment_id=segment_id if segment_id else None,
        )
        merged_create_bullets.append(
            Request(
                create_paragraph_bullets=CreateParagraphBulletsRequest(
                    bullet_preset=CreateParagraphBulletsRequestBulletPreset(preset),
                    range=merged_range,
                )
            )
        )
        cumulative += run_len
        i = j

    # Emit: insertTexts first (reverse order, for correct document ordering),
    # then merged createParagraphBullets, then style requests.
    return combined_insert_texts + merged_create_bullets + all_style_reqs


def _deleted_chars_before(
    *,
    deleted_sizes: dict[int, int],
    base_content: list[StructuralElement],
    before_pos: int,
) -> int:
    """Return total character count deleted from positions < before_pos."""
    total = 0
    for bidx, size in deleted_sizes.items():
        el_start = _element_start(base_content[bidx])
        if el_start is not None and el_start < before_pos:
            total += size
    return total


def _lower_element_update(
    *,
    base_el: StructuralElement,
    desired_el: StructuralElement,
    tab_id: str,
    segment_id: str | None,
    pre_delete_shift: int = 0,
    desired_lists: dict[str, DocList] | None = None,
    base_lists: dict[str, DocList] | None = None,
) -> list[Request]:
    """Lower an in-place element update (matched element, content changed).

    For paragraphs: replace text runs.
    For tables: raise NotImplementedError (complex; not yet implemented).

    For structural elements: no-op (cannot change their content).

    ``pre_delete_shift`` is the total number of characters removed by
    whole-element base_deletes whose startIndex is below this element's
    startIndex.  All generated request indices are shifted down by this
    amount to account for the prior deletions.
    """
    if base_el.paragraph is not None and desired_el.paragraph is not None:
        return _lower_paragraph_update(
            base_el=base_el,
            desired_el=desired_el,
            tab_id=tab_id,
            segment_id=segment_id,
            pre_delete_shift=pre_delete_shift,
            desired_lists=desired_lists or {},
            base_lists=base_lists or {},
        )
    elif base_el.table is not None and desired_el.table is not None:
        # Table cell content updates are emitted as separate UpdateBodyContentOp
        # ops with story_kind="table_cell" by the diff layer.  At the body level
        # a matched table pair means "same table, cells may have changed" — the
        # cell-level child ops handle the actual content edits.  No body-level
        # request is needed here.
        return []
    elif base_el.section_break is not None and desired_el.section_break is not None:
        return _lower_section_break_update(
            base_el=base_el,
            desired_el=desired_el,
            tab_id=tab_id,
        )
    else:
        # TOC etc. — no content to update
        return []


def _lower_paragraph_update(
    *,
    base_el: StructuralElement,
    desired_el: StructuralElement,
    tab_id: str,
    segment_id: str | None,
    pre_delete_shift: int = 0,
    desired_lists: dict[str, DocList] | None = None,
    base_lists: dict[str, DocList] | None = None,
) -> list[Request]:
    """Replace the text content of a paragraph in place using surgical ops.

    Approach:
    1. Compute a character-level diff on non-terminal text to find minimal edits.
    2. For unchanged spans: emit updateTextStyle if the style changed.
    3. For deleted spans: emit deleteContentRange.
    4. For inserted spans: emit insertText + updateTextStyle if non-default style.
    5. Always emit updateParagraphStyle if paragraph-level style changed.

    Operations are emitted in descending character order (highest index first)
    so that earlier ops do not corrupt later indices.
    """
    assert base_el.paragraph is not None
    assert desired_el.paragraph is not None
    base_para = base_el.paragraph
    desired_para = desired_el.paragraph

    start, end = _element_range(base_el)
    if start is None or end is None:
        return []

    adjusted_start = start - pre_delete_shift
    adjusted_end = end - pre_delete_shift

    # Always compute run-level diff (handles text changes + text-style changes).
    # For the same-text case this emits only updateTextStyle for changed runs.
    # For the changed-text case this emits delete/insert/updateTextStyle as needed.
    requests = _diff_paragraph_runs(
        base_para=base_para,
        desired_para=desired_para,
        story_offset=adjusted_start,
        tab_id=tab_id,
        segment_id=segment_id,
    )

    # Additionally apply paragraph-level style changes (alignment, spacing, etc.)
    # regardless of whether text changed.
    style_reqs = _lower_para_style_update(
        base_para=base_para,
        desired_para=desired_para,
        start_index=adjusted_start,
        end_index=adjusted_end,
        tab_id=tab_id,
        segment_id=segment_id,
        desired_lists=desired_lists or {},
        base_lists=base_lists or {},
    )
    requests.extend(style_reqs)

    return requests


_EMPTY_TEXT_STYLE = TextStyle()


def _extract_runs(
    para: Paragraph,
) -> list[tuple[str, TextStyle]]:
    """Return list of (text, TextStyle) for each textRun element in a paragraph.

    Non-textRun elements (inline objects, footnote refs, etc.) are skipped.
    """
    runs: list[tuple[str, TextStyle]] = []
    for el in para.elements or []:
        if el.text_run is not None:
            tr = el.text_run
            text = tr.content or ""
            style = tr.text_style or _EMPTY_TEXT_STYLE
            runs.append((text, style))
    return runs


def _runs_to_spans(
    runs: list[tuple[str, TextStyle]],
) -> list[tuple[int, int, str, TextStyle]]:
    """Convert runs to (start, end, text, style) spans with character offsets.

    Offsets are relative to the start of the paragraph (0-based).
    """
    spans: list[tuple[int, int, str, TextStyle]] = []
    cursor = 0
    for text, style in runs:
        length = utf16_len(text)
        spans.append((cursor, cursor + length, text, style))
        cursor += length
    return spans


def _styles_equal(s1: TextStyle, s2: TextStyle) -> bool:
    """Return True if two TextStyle models are effectively equal.

    Compares via model_dump to handle None vs missing field equivalence.
    """
    return s1.model_dump(by_alias=True, exclude_none=True) == s2.model_dump(
        by_alias=True, exclude_none=True
    )


def _diff_paragraph_runs(
    *,
    base_para: Paragraph,
    desired_para: Paragraph,
    story_offset: int,
    tab_id: str,
    segment_id: str | None,
) -> list[Request]:
    """Compute surgical API requests for a paragraph whose text changed.

    Algorithm:
    1. Extract text runs from base and desired paragraphs.
    2. Build a plain-text string (excluding the terminal \\n) for each.
    3. Run a character-level diff (SequenceMatcher) to find equal/insert/delete chunks.
    4. For each chunk:
       - 'equal': check if style changed → emit updateTextStyle if so.
       - 'delete': emit deleteContentRange.
       - 'insert': emit insertText + updateTextStyle if non-default style.
       - 'replace': emit deleteContentRange + insertText + optional updateTextStyle.
    5. All ops are collected and returned in descending character order so they
       can be applied sequentially without index corruption.

    The terminal \\n is never touched.
    """
    base_runs = _extract_runs(base_para)
    desired_runs = _extract_runs(desired_para)

    # Build plain text (all runs concatenated)
    base_full_text = "".join(t for t, _ in base_runs)
    desired_full_text = "".join(t for t, _ in desired_runs)

    # Strip terminal \n for diffing (we never touch it)
    base_body = (
        base_full_text.rstrip("\n") if base_full_text.endswith("\n") else base_full_text
    )
    desired_body = (
        desired_full_text.rstrip("\n")
        if desired_full_text.endswith("\n")
        else desired_full_text
    )

    # Build span maps for style lookup: char_offset → style
    # We need to find the style at any character position in base/desired.
    base_spans = _runs_to_spans(base_runs)
    desired_spans = _runs_to_spans(desired_runs)

    # Compute character-level diff
    matcher = difflib.SequenceMatcher(None, base_body, desired_body, autojunk=False)
    opcodes = matcher.get_opcodes()

    # Collect pending ops as (abs_start, abs_end, kind, extra)
    # kind ∈ {"delete", "insert", "update_style", "replace"}
    # We process in reverse order (highest index first).

    # Pending ops list: (sort_key, requests_list)
    # sort_key is the document-absolute start index (for descending sort)
    pending: list[tuple[int, list[Request]]] = []

    for tag, i1, i2, j1, j2 in opcodes:
        if tag == "equal":
            # Check if style changed for this span
            # We check style at the first char of the base span
            if i2 <= i1:
                continue
            # Find all distinct style sub-ranges within this equal span
            sub_ops = _style_update_ops_for_equal_span(
                base_spans=base_spans,
                desired_spans=desired_spans,
                base_start=i1,
                base_end=i2,
                desired_start=j1,
                desired_end=j2,
                story_offset=story_offset,
                tab_id=tab_id,
                segment_id=segment_id,
            )
            for abs_start, reqs in sub_ops:
                pending.append((abs_start, reqs))

        elif tag == "delete":
            # Delete [i1, i2) in base
            abs_start = story_offset + i1
            abs_end = story_offset + i2
            pending.append(
                (
                    abs_start,
                    [
                        _make_delete_content_range(
                            start_index=abs_start,
                            end_index=abs_end,
                            tab_id=tab_id,
                            segment_id=segment_id,
                        )
                    ],
                )
            )

        elif tag == "insert":
            # Insert desired[j1:j2] at position i1 in base (after deletions)
            # We'll compute the insertion position relative to the base document.
            # The insertion happens at base position i1 (before any character there).
            # We group chars by style from desired spans.
            insert_reqs = _insert_ops_for_span(
                desired_spans=desired_spans,
                desired_start=j1,
                desired_end=j2,
                base_pos=i1,
                story_offset=story_offset,
                tab_id=tab_id,
                segment_id=segment_id,
            )
            if insert_reqs:
                pending.append((story_offset + i1, insert_reqs))

        elif tag == "replace":
            # Delete base[i1:i2], insert desired[j1:j2]
            abs_start = story_offset + i1
            abs_end = story_offset + i2

            # Deletion first (will run last since descending order)
            del_req = _make_delete_content_range(
                start_index=abs_start,
                end_index=abs_end,
                tab_id=tab_id,
                segment_id=segment_id,
            )
            # Insertion at the same position (after deletion, index is abs_start)
            insert_reqs = _insert_ops_for_span(
                desired_spans=desired_spans,
                desired_start=j1,
                desired_end=j2,
                base_pos=i1,
                story_offset=story_offset,
                tab_id=tab_id,
                segment_id=segment_id,
            )
            # Delete and insert at the same logical position.
            # We emit the insert first (smaller sort key → processed before delete
            # in descending order — actually we want delete before insert when
            # applying).  Use a tuple to break ties: (abs_start, priority) where
            # delete=0 (higher priority = applied first in descending scan).
            # To ensure delete comes before insert in the final request list,
            # we emit them as a single group in delete-first order.
            combined = [del_req, *insert_reqs]
            pending.append((abs_start, combined))

    # Sort pending ops by sort_key descending (highest document index first)
    pending.sort(key=lambda item: item[0], reverse=True)

    # Flatten
    requests: list[Request] = []
    for _key, reqs in pending:
        requests.extend(reqs)

    return requests


def _style_update_ops_for_equal_span(
    *,
    base_spans: list[tuple[int, int, str, TextStyle]],
    desired_spans: list[tuple[int, int, str, TextStyle]],
    base_start: int,
    base_end: int,
    desired_start: int,
    desired_end: int,
    story_offset: int,
    tab_id: str,
    segment_id: str | None,
) -> list[tuple[int, list[Request]]]:
    """For an 'equal' diff chunk, emit updateTextStyle where style changed.

    We walk character-by-character through the equal span and group consecutive
    characters that share the same (base_style, desired_style) pair, then emit
    an updateTextStyle for each group where styles differ.

    Returns list of (abs_start, [Request]) pairs.
    """
    # Find all style-change sub-ranges within the equal span
    # Group by consecutive chars with same (base_style != desired_style)
    result: list[tuple[int, list[Request]]] = []

    # Walk through the span and find style boundaries
    i = base_start
    j = desired_start
    while i < base_end:
        b_style = _style_at_offset(base_spans, i)
        d_style = _style_at_offset(desired_spans, j)

        # Find next boundary in either base or desired spans.
        # b_next and d_next are in their respective coordinate spaces
        # (base: [base_start, base_end), desired: [desired_start, desired_end)).
        # Advance by the smaller of the two distances so we never overshoot
        # a span boundary in either sequence.
        b_next = _next_span_boundary(base_spans, i, base_end)
        d_next = _next_span_boundary(desired_spans, j, desired_end)
        step = min(b_next - i, d_next - j)
        if step <= 0:
            # Defensive guard: should never happen given well-formed spans,
            # but prevent an infinite loop if spans don't cover the position.
            break
        chunk_end = i + step

        if not _styles_equal(b_style, d_style):
            abs_start = story_offset + i
            abs_end = story_offset + chunk_end
            changed_fields = _text_style_changed_fields(b_style, d_style)
            if changed_fields:
                result.append(
                    (
                        abs_start,
                        [
                            _make_update_text_style(
                                start_index=abs_start,
                                end_index=abs_end,
                                tab_id=tab_id,
                                segment_id=segment_id,
                                text_style=d_style,
                                fields=changed_fields,
                            )
                        ],
                    )
                )

        i += step
        j += step

    return result


def _style_at_offset(
    spans: list[tuple[int, int, str, TextStyle]],
    offset: int,
) -> TextStyle:
    """Return the TextStyle for the character at the given offset within spans."""
    for start, end, _text, style in spans:
        if start <= offset < end:
            return style
    return _EMPTY_TEXT_STYLE


def _next_span_boundary(
    spans: list[tuple[int, int, str, TextStyle]],
    pos: int,
    limit: int,
) -> int:
    """Return the end of the span containing pos (capped at limit)."""
    for start, end, _text, _style in spans:
        if start <= pos < end:
            return min(end, limit)
    return limit


def _insert_ops_for_span(
    *,
    desired_spans: list[tuple[int, int, str, TextStyle]],
    desired_start: int,
    desired_end: int,
    base_pos: int,
    story_offset: int,
    tab_id: str,
    segment_id: str | None,
) -> list[Request]:
    """Emit insertText + optional updateTextStyle for desired[desired_start:desired_end].

    The text is inserted at base_pos (before any character at that position in base).
    We group consecutive characters by their textStyle and emit one insertText per
    contiguous group with the same style — but since insertText inserts at the same
    index and text flows forward, we emit a single insertText with all the text and
    then style each sub-range.
    """
    if desired_start >= desired_end:
        return []

    # Collect the full text to insert
    full_text = ""
    i = desired_start
    while i < desired_end:
        for start, end, text, _style in desired_spans:
            if start <= i < end:
                # Take the portion of this span in [desired_start, desired_end)
                offset_in_span = i - start
                take = min(end, desired_end) - i
                full_text += text[offset_in_span : offset_in_span + take]
                i += take
                break
        else:
            break

    if not full_text:
        return []

    abs_insert = story_offset + base_pos
    reqs: list[Request] = [
        _make_insert_text(
            index=abs_insert,
            tab_id=tab_id,
            segment_id=segment_id,
            text=full_text,
        )
    ]

    # Apply styles to sub-ranges of the inserted text
    cursor = abs_insert
    i = desired_start
    while i < desired_end:
        style = _style_at_offset(desired_spans, i)
        end_of_span = _next_span_boundary(desired_spans, i, desired_end)
        span_len = end_of_span - i
        style_dict = style.model_dump(by_alias=True, exclude_none=True)
        if style_dict:
            fields = list(style_dict.keys())
            reqs.append(
                _make_update_text_style(
                    start_index=cursor,
                    end_index=cursor + span_len,
                    tab_id=tab_id,
                    segment_id=segment_id,
                    text_style=style,
                    fields=fields,
                )
            )
        cursor += span_len
        i = end_of_span

    return reqs


def _make_update_text_style(
    *,
    start_index: int,
    end_index: int,
    tab_id: _StrOrDeferred,
    segment_id: _StrOrDeferred | None,
    text_style: TextStyle,
    fields: list[str],
) -> Request:
    """Build an updateTextStyle Request."""
    return Request(
        update_text_style=UpdateTextStyleRequest(
            range=Range(
                start_index=start_index,
                end_index=end_index,
                tab_id=tab_id if tab_id else None,
                segment_id=segment_id if segment_id else None,
            ),
            text_style=text_style,
            fields=",".join(fields),
        )
    )


def _lower_para_style_update(
    *,
    base_para: Paragraph,
    desired_para: Paragraph,
    start_index: int,
    end_index: int,
    tab_id: str,
    segment_id: str | None,
    desired_lists: dict[str, DocList] | None = None,
    base_lists: dict[str, DocList] | None = None,
) -> list[Request]:
    """Emit paragraphStyle / bullet / textStyle update requests if styles changed.

    Bullet handling for matched paragraphs:

    Case A — paragraph gains a bullet (base has none, desired has one):
        1. Prepend ``"\\t" * nesting_level`` tabs via insertText at start_index.
        2. Emit createParagraphBullets covering the extended range.

    Case B — paragraph loses a bullet (base has one, desired has none):
        1. Emit deleteParagraphBullets.
        2. Emit updateParagraphStyle clearing indentStart (deleteParagraphBullets
           adds visual indent to preserve appearance).

    Case C — nesting level or list type changes (both have bullet):
        1. Emit deleteParagraphBullets.
        2. Prepend new tabs at start_index.
        3. Emit createParagraphBullets with desired preset.
    """
    requests: list[Request] = []

    base_bullet = base_para.bullet
    desired_bullet = desired_para.bullet

    if not base_bullet and desired_bullet:
        # Case A: paragraph gains a bullet
        nesting_level = desired_bullet.nesting_level or 0
        preset = _infer_bullet_preset_from_model(desired_bullet, desired_lists or {})
        tabs = "\t" * nesting_level
        tabs_len = utf16_len(tabs)
        if tabs_len > 0:
            requests.append(
                _make_insert_text(
                    index=start_index,
                    tab_id=tab_id,
                    segment_id=segment_id,
                    text=tabs,
                )
            )
        # createParagraphBullets covers the tabs + paragraph content
        requests.append(
            _make_create_paragraph_bullets(
                start=start_index,
                end=start_index + tabs_len + (end_index - start_index),
                preset=preset,
                tab_id=tab_id,
                segment_id=segment_id,
            )
        )

    elif base_bullet and not desired_bullet:
        # Case B: paragraph loses a bullet
        requests.append(
            _make_delete_paragraph_bullets(
                start=start_index,
                end=end_index,
                tab_id=tab_id,
                segment_id=segment_id,
            )
        )
        # deleteParagraphBullets adds visual indent — clear it
        requests.append(
            _make_update_paragraph_style(
                start_index=start_index,
                end_index=end_index,
                tab_id=tab_id,
                segment_id=segment_id,
                paragraph_style={"indentStart": None, "indentFirstLine": None},
                fields=["indentStart", "indentFirstLine"],
            )
        )

    elif base_bullet and desired_bullet:
        # Case C: both have bullet — check if nesting level or list type changed.
        # List type change is detected by comparing the inferred bullet preset:
        # base preset (from base_lists) vs desired preset (from desired_lists).
        base_nesting = base_bullet.nesting_level or 0
        desired_nesting = desired_bullet.nesting_level or 0
        base_preset = _infer_bullet_preset_from_model(base_bullet, base_lists or {})
        desired_preset = _infer_bullet_preset_from_model(
            desired_bullet, desired_lists or {}
        )
        if base_nesting != desired_nesting or base_preset != desired_preset:
            # Delete then re-add with new nesting level / list type
            requests.append(
                _make_delete_paragraph_bullets(
                    start=start_index,
                    end=end_index,
                    tab_id=tab_id,
                    segment_id=segment_id,
                )
            )
            preset = desired_preset
            tabs = "\t" * desired_nesting
            tabs_len = utf16_len(tabs)
            if tabs_len > 0:
                requests.append(
                    _make_insert_text(
                        index=start_index,
                        tab_id=tab_id,
                        segment_id=segment_id,
                        text=tabs,
                    )
                )
            requests.append(
                _make_create_paragraph_bullets(
                    start=start_index,
                    end=start_index + tabs_len + (end_index - start_index),
                    preset=preset,
                    tab_id=tab_id,
                    segment_id=segment_id,
                )
            )

    # Paragraph style changes (beyond bullet-related indentation)
    base_ps = (
        base_para.paragraph_style.model_dump(by_alias=True, exclude_none=True)
        if base_para.paragraph_style
        else {}
    )
    desired_ps = (
        desired_para.paragraph_style.model_dump(by_alias=True, exclude_none=True)
        if desired_para.paragraph_style
        else {}
    )

    if base_ps != desired_ps and desired_ps:
        # Compute changed fields — exclude bullet-managed indentation when
        # bullet ops were already emitted above (they set indentation).
        fields = _dict_changed_fields(base_ps, desired_ps)
        # Always exclude server-managed readonly fields from the field mask.
        fields = [f for f in fields if f not in _PARA_STYLE_READONLY_FIELDS]
        if base_bullet or desired_bullet:
            # Exclude indent fields that createParagraphBullets manages
            fields = [f for f in fields if f not in ("indentFirstLine", "indentStart")]
        if fields:
            requests.append(
                _make_update_paragraph_style(
                    start_index=start_index,
                    end_index=end_index,
                    tab_id=tab_id,
                    segment_id=segment_id,
                    paragraph_style=desired_ps,
                    fields=fields,
                )
            )

    return requests


def _lower_element_insert(
    *,
    el: StructuralElement,
    index: int,
    tab_id: _StrOrDeferred,
    segment_id: _StrOrDeferred | None,
    desired_lists: dict[str, DocList] | None = None,
) -> list[Request]:
    """Generate request(s) to insert a content element at the given index.

    For page break paragraphs: insertPageBreak.
    For paragraphs: insertText (text + \\n) + style requests.
    For tables: insertTable (dimensions only; cell content not yet supported).
    For section breaks: insertSectionBreak + optional updateSectionStyle.
    """
    if el.paragraph is not None and _is_pagebreak_para(el.paragraph):
        return _lower_page_break_insert(
            index=index,
            tab_id=tab_id,
        )
    elif el.paragraph is not None:
        return _lower_paragraph_insert(
            el=el,
            index=index,
            tab_id=tab_id,
            segment_id=segment_id,
            desired_lists=desired_lists or {},
        )
    elif el.table is not None:
        return _lower_table_insert(
            el=el,
            index=index,
            tab_id=tab_id,
            segment_id=segment_id,
        )
    elif el.section_break is not None:
        return _lower_section_break_insert(
            el=el,
            index=index,
            tab_id=tab_id,
        )
    else:
        el_keys = []
        if el.paragraph is not None:
            el_keys.append("paragraph")
        if el.table is not None:
            el_keys.append("table")
        if el.section_break is not None:
            el_keys.append("sectionBreak")
        if el.table_of_contents is not None:
            el_keys.append("tableOfContents")
        raise NotImplementedError(
            f"lowering for insertion of element kind {el_keys!r} not yet implemented"
        )


def _lower_paragraph_insert(
    *,
    el: StructuralElement,
    index: int,
    tab_id: _StrOrDeferred,
    segment_id: _StrOrDeferred | None,
    desired_lists: dict[str, DocList] | None = None,
) -> list[Request]:
    """Insert a paragraph at ``index`` via insertText + optional style.

    For bullet paragraphs, the approach is:
    1. Prepend ``"\\t" * nesting_level`` to the text before insertText.
    2. Emit createParagraphBullets covering the range (including tabs).
       The API strips the tabs and sets the nesting level from them.
    3. Style requests (updateParagraphStyle, updateTextStyle) use the
       tab-free ``index`` as start — by the time they execute in the batch,
       createParagraphBullets has already removed the tabs.
    4. Net index advance for subsequent elements = len(text), not len(tabs+text).
    """
    requests: list[Request] = []

    assert el.paragraph is not None
    para = el.paragraph
    text = _para_text(para)
    text_len = utf16_len(text)

    bullet = para.bullet
    if bullet:
        nesting_level = bullet.nesting_level or 0
        tabs = "\t" * nesting_level
        preset = _infer_bullet_preset_from_model(bullet, desired_lists or {})
        full_text = tabs + text  # text already ends with \n

        # insertText with leading tabs for nesting
        requests.append(
            _make_insert_text(
                index=index,
                tab_id=tab_id,
                segment_id=segment_id,
                text=full_text,
            )
        )

        # createParagraphBullets: range covers tabs+text before removal.
        # After this runs, tabs are removed and the nesting level is set.
        full_text_len = utf16_len(full_text)
        requests.append(
            _make_create_paragraph_bullets(
                start=index,
                end=index + full_text_len,
                preset=preset,
                tab_id=tab_id,
                segment_id=segment_id,
            )
        )

        # Style requests use tab-free indices: createParagraphBullets has
        # already removed the tabs by the time these run in the batch.
        desired_ps = (
            para.paragraph_style.model_dump(by_alias=True, exclude_none=True)
            if para.paragraph_style
            else {}
        )
        if desired_ps:
            # Exclude indentation fields — createParagraphBullets sets them.
            # Also exclude server-managed readonly fields (e.g. headingId).
            ps_fields = [
                k
                for k in desired_ps
                if k not in ("indentFirstLine", "indentStart")
                and k not in _PARA_STYLE_READONLY_FIELDS
            ]
            if ps_fields:
                requests.append(
                    _make_update_paragraph_style(
                        start_index=index,
                        end_index=index + text_len,
                        tab_id=tab_id,
                        segment_id=segment_id,
                        paragraph_style={k: desired_ps[k] for k in ps_fields},
                        fields=ps_fields,
                    )
                )

        # Apply text styles for each run (use tab-free index)
        runs = _extract_runs(para)
        run_offset = index
        for text_content, style in runs:
            run_len = utf16_len(text_content)
            style_dict = style.model_dump(by_alias=True, exclude_none=True)
            if run_len > 0 and style_dict:
                requests.append(
                    _make_update_text_style(
                        start_index=run_offset,
                        end_index=run_offset + run_len,
                        tab_id=tab_id,
                        segment_id=segment_id,
                        text_style=style,
                        fields=list(style_dict.keys()),
                    )
                )
            run_offset += run_len

    else:
        # Non-bullet paragraph: plain insertText + style
        requests.append(
            _make_insert_text(
                index=index,
                tab_id=tab_id,
                segment_id=segment_id,
                text=text,
            )
        )

        # Apply paragraph style
        desired_ps = (
            para.paragraph_style.model_dump(by_alias=True, exclude_none=True)
            if para.paragraph_style
            else {}
        )
        if desired_ps:
            # Exclude server-managed readonly fields (e.g. headingId) from mask.
            fields = [k for k in desired_ps if k not in _PARA_STYLE_READONLY_FIELDS]
            if fields:
                requests.append(
                    _make_update_paragraph_style(
                        start_index=index,
                        end_index=index + text_len,
                        tab_id=tab_id,
                        segment_id=segment_id,
                        paragraph_style={k: desired_ps[k] for k in fields},
                        fields=fields,
                    )
                )

        # Apply text styles for each run
        runs = _extract_runs(para)
        run_offset = index
        for text_content, style in runs:
            run_len = utf16_len(text_content)
            style_dict = style.model_dump(by_alias=True, exclude_none=True)
            if run_len > 0 and style_dict:
                requests.append(
                    _make_update_text_style(
                        start_index=run_offset,
                        end_index=run_offset + run_len,
                        tab_id=tab_id,
                        segment_id=segment_id,
                        text_style=style,
                        fields=list(style_dict.keys()),
                    )
                )
            run_offset += run_len

    return requests


def _lower_table_insert(
    *,
    el: StructuralElement,
    index: int,
    tab_id: _StrOrDeferred,
    segment_id: _StrOrDeferred | None,
) -> list[Request]:
    """Insert a table at ``index`` and populate cell content.

    Emits ``insertTable`` first, then ``insertText`` + style requests for each
    cell's desired content at the correct absolute index.

    Index arithmetic
    ----------------
    After ``insertTable`` creates an empty table, each empty cell occupies
    exactly 2 characters: one cell-opener character and one terminal ``\\n``.
    When we insert ``s`` characters of content into a cell at position P+1
    (after the cell opener at P), all subsequent cells shift right by ``s``.
    The loop tracks this running shift via ``table_pos``.

    Structural layout immediately after ``insertTable`` at ``index``::

        index     : table opener  (1 char)
        index+1   : row[0] opener (1 char)
        index+2   : cell[0][0] opener (1 char)
        index+3   : cell[0][0] terminal \\n (1 char) — empty
        index+4   : cell[0][1] opener (1 char)
        ...
    """
    assert el.table is not None
    table = el.table
    table_rows = table.table_rows or []
    rows = table.rows or len(table_rows)
    cols = table.columns or 0
    if cols == 0 and table_rows:
        cols = len(table_rows[0].table_cells or [])

    loc = Location(
        index=index,
        tab_id=tab_id if tab_id else None,
        segment_id=segment_id if segment_id else None,
    )

    requests: list[Request] = [
        Request(
            insert_table=InsertTableRequest(
                rows=rows,
                columns=cols,
                location=loc,
            )
        )
    ]

    # table_pos tracks the next position as it shifts with each insertion.
    # Start at index+1 to skip the table opener; each row opener advances by 1.
    table_pos = index + 1

    for row in table_rows:
        table_pos += 1  # skip row opener (1 char)
        for cell in row.table_cells or []:
            cell_content: list[StructuralElement] = cell.content or []
            if not cell_content:
                # Fully empty cell (no content list at all) — skip.
                # An empty cell still occupies 2 chars (opener + terminal \n).
                table_pos += 2
                continue

            # First element in cell starts at table_pos + 1 (after cell opener).
            content_start = table_pos + 1

            # Filter out terminal paragraphs (bare "\n").  We skip them because
            # insertTable creates one terminal \n per cell automatically.
            #
            # We filter rather than blindly using content[:-1] because the
            # markdown deserialiser produces cells with a single paragraph whose
            # text already ends with "\n" (no separate terminal element), while a
            # real API pull produces [content_para, terminal_para].  Both cases
            # must work correctly.
            insertable = [e for e in cell_content if not _is_cell_terminal(e)]
            inserted_chars = sum(_element_size(e) for e in insertable)

            if inserted_chars > 0:
                running = content_start
                for e in insertable:
                    requests.extend(
                        _lower_element_insert(
                            el=e,
                            index=running,
                            tab_id=tab_id,
                            segment_id=segment_id,
                        )
                    )
                    running += _element_size(e)

            # Advance past this cell:
            # originally 2 chars (opener + terminal \n), now 2 + inserted_chars.
            table_pos += inserted_chars + 2

    return requests


def _is_pagebreak_para(para: Paragraph) -> bool:
    """Return True if a Paragraph's only content element(s) include a pageBreak.

    A page break paragraph has a ``pageBreak`` element among its elements (plus
    an optional terminal ``\\n`` textRun).  Such paragraphs must be inserted via
    ``insertPageBreak``, not ``insertText``.
    """
    has_page_break = False
    for elem in para.elements or []:
        if elem.page_break is not None:
            has_page_break = True
        elif elem.text_run is not None:
            content = elem.text_run.content or ""
            if content not in ("", "\n"):
                # Real text alongside the page break — not a pure page break para
                return False
        else:
            # Other inline elements (inlineObject, footnoteReference, etc.)
            return False
    return has_page_break


def _lower_page_break_insert(
    *,
    index: int,
    tab_id: _StrOrDeferred,
) -> list[Request]:
    """Insert a page break via ``insertPageBreak`` at ``index``.

    ``insertPageBreak`` inserts two characters (pageBreak element + newline).
    The ``segmentId`` field must be omitted — the API only allows page breaks
    in the document body.
    """
    return [
        Request(
            insert_page_break=InsertPageBreakRequest(
                location=Location(
                    index=index,
                    tab_id=tab_id if tab_id else None,
                ),
            )
        )
    ]


def _lower_section_break_insert(
    *,
    el: StructuralElement,
    index: int,
    tab_id: _StrOrDeferred,
) -> list[Request]:
    """Insert a section break via ``insertSectionBreak`` at ``index``.

    Reads ``sectionType`` from ``el.section_break.section_style.section_type``;
    defaults to ``"NEXT_PAGE"`` if absent.

    If the ``sectionStyle`` contains additional style fields beyond
    ``sectionType``, emits a follow-up ``updateSectionStyle`` request covering
    the newly inserted section break character.
    """
    assert el.section_break is not None
    section_style = el.section_break.section_style
    section_style_dict = (
        section_style.model_dump(by_alias=True, exclude_none=True)
        if section_style
        else {}
    )
    section_type = section_style_dict.get("sectionType", "NEXT_PAGE")

    requests: list[Request] = [
        Request(
            insert_section_break=InsertSectionBreakRequest(
                location=Location(
                    index=index,
                    tab_id=tab_id if tab_id else None,
                ),
                section_type=section_type,
            )
        )
    ]

    # Emit updateSectionStyle for any non-default style fields.
    # insertSectionBreak inserts 2 characters (newline + section break element),
    # so the section break lands at index+1 in the post-insert document.
    style_fields = [k for k in section_style_dict if k != "sectionType"]
    if style_fields and section_style_dict:
        style_to_apply = {k: section_style_dict[k] for k in style_fields}
        requests.append(
            Request(
                update_section_style=UpdateSectionStyleRequest(
                    range=Range(
                        start_index=index + 1,
                        end_index=index + 2,
                        tab_id=tab_id if tab_id else None,
                    ),
                    section_style=SectionStyle.model_validate(style_to_apply),
                    fields=",".join(sorted(style_fields)),
                )
            )
        )

    return requests


def _lower_section_break_update(
    *,
    base_el: StructuralElement,
    desired_el: StructuralElement,
    tab_id: str,
) -> list[Request]:
    """Emit ``updateSectionStyle`` when a matched section break's style changed.

    The range covers the section break character itself (startIndex → endIndex).
    If ``sectionStyle`` is identical, returns an empty list.
    """
    assert base_el.section_break is not None
    assert desired_el.section_break is not None
    base_style = (
        base_el.section_break.section_style.model_dump(by_alias=True, exclude_none=True)
        if base_el.section_break.section_style
        else {}
    )
    desired_style = (
        desired_el.section_break.section_style.model_dump(
            by_alias=True, exclude_none=True
        )
        if desired_el.section_break.section_style
        else {}
    )

    changed_fields = _dict_changed_fields(base_style, desired_style)
    if not changed_fields:
        return []

    start, end = _element_range(base_el)
    if start is None or end is None:
        return []

    return [
        Request(
            update_section_style=UpdateSectionStyleRequest(
                range=Range(
                    start_index=start,
                    end_index=end,
                    tab_id=tab_id if tab_id else None,
                ),
                section_style=SectionStyle.model_validate(desired_style),
                fields=",".join(sorted(changed_fields)),
            )
        )
    ]


def _lower_content_insert(
    *,
    content: list[StructuralElement],
    start_index: int,
    tab_id: _StrOrDeferred,
    segment_id: _StrOrDeferred | None,
    desired_lists: dict[str, DocList] | None = None,
) -> list[Request]:
    """Insert a list of StructuralElements starting at ``start_index``.

    This is the single unified pure-insert entry point for all five content
    containers (body, header, footer, footnote, table cell).

    The terminal paragraph (the trailing ``\\n`` that every container already
    has) is skipped — ``content[:-1]`` is processed.

    ``tab_id`` and ``segment_id`` may be DeferredID placeholders; they
    flow through to ``_lower_element_insert`` and ultimately to the builder
    helpers, where ``resolve_deferred_placeholders`` substitutes them before
    the batch executes.

    Index arithmetic
    ----------------
    A freshly created segment (header, footer, footnote) has one empty
    paragraph whose ``\\n`` sits at index 1 in the segment's coordinate
    space.  Pass ``start_index=1`` for those containers.

    For a body (new tab), content also starts at index 1.

    For a table cell, pass the pre-computed absolute index of the first
    position inside the cell (cell_opener_index + 1).
    """
    requests: list[Request] = []
    running_index = start_index

    for el in content[:-1]:  # skip terminal paragraph
        reqs = _lower_element_insert(
            el=el,
            index=running_index,
            tab_id=tab_id,
            segment_id=segment_id,
            desired_lists=desired_lists,
        )
        requests.extend(reqs)
        running_index += _element_size(el)

    return requests


# ---------------------------------------------------------------------------
# Tab body extraction helper
# ---------------------------------------------------------------------------


def _extract_tab_body_content(tab: Tab) -> list[StructuralElement]:
    """Return the body StructuralElements from a Tab.

    Skips any leading ``sectionBreak`` element — ``addDocumentTab`` creates
    it automatically, so it must not be re-inserted.

    Returns an empty list if the body has no content beyond the terminal
    paragraph (nothing to insert into the new tab).
    """
    doc_tab = tab.document_tab
    if doc_tab is None:
        return []
    body = doc_tab.body
    if body is None:
        return []
    content: list[StructuralElement] = body.content or []
    # Drop leading sectionBreak (inserted automatically by addDocumentTab)
    filtered = [el for el in content if el.section_break is None]
    # Nothing to do if the only remaining element is the terminal paragraph
    if len(filtered) <= 1:
        return []
    return filtered


# ---------------------------------------------------------------------------
# Element index helpers
# ---------------------------------------------------------------------------


def _is_cell_terminal(el: StructuralElement) -> bool:
    """Return True if ``el`` is a bare terminal paragraph (text == "\\n").

    Table cells may or may not include an explicit terminal paragraph depending
    on whether the content came from a real API pull (always has one) or from
    the markdown/XML deserialiser (may omit it).  Either way, ``insertTable``
    creates the terminal automatically, so we must never re-insert it.
    """
    if el.paragraph is None:
        return False
    return _para_text(el.paragraph) == "\n"


def _element_size(el: StructuralElement) -> int:
    """Return the number of UTF-16 code units occupied by a StructuralElement.

    For paragraphs the size is always derivable from the text content.
    For section breaks the API allocates exactly one character.
    For tables and other elements we read ``startIndex``/``endIndex`` if
    present; these are set on elements that came from a real API pull.
    """
    if el.paragraph is not None:
        return utf16_len(_para_text(el.paragraph))
    if el.section_break is not None:
        return 1
    start, end = _element_range(el)
    if start is not None and end is not None:
        return end - start
    el_keys = []
    if el.table is not None:
        el_keys.append("table")
    if el.table_of_contents is not None:
        el_keys.append("tableOfContents")
    raise NotImplementedError(
        f"Cannot compute size of element with keys {el_keys!r} "
        "without startIndex/endIndex. Ensure the desired document was "
        "pulled from the Google API so that index information is present."
    )


def _element_range(el: StructuralElement) -> tuple[int | None, int | None]:
    """Return (startIndex, endIndex) from a StructuralElement, or (None, None)."""
    start = el.start_index
    end = el.end_index
    if isinstance(start, int) and isinstance(end, int):
        return start, end
    return None, None


def _element_start(el: StructuralElement) -> int | None:
    """Return startIndex from a StructuralElement, or None."""
    start = el.start_index
    return start if isinstance(start, int) else None


def _para_text(para: Paragraph) -> str:
    """Return concatenated text from a Paragraph."""
    texts: list[str] = []
    for e in para.elements or []:
        if e.text_run is not None and e.text_run.content is not None:
            texts.append(e.text_run.content)
    return "".join(texts)


def _dict_changed_fields(
    base_dict: dict[str, object],
    desired_dict: dict[str, object],
) -> list[str]:
    """Return the camelCase field names that differ between two style dicts."""
    all_keys = set(base_dict) | set(desired_dict)
    return [k for k in all_keys if base_dict.get(k) != desired_dict.get(k)]


def _text_style_changed_fields(
    base_style: TextStyle,
    desired_style: TextStyle,
) -> list[str]:
    """Return the camelCase field names that differ between two TextStyle models."""
    return _dict_changed_fields(
        base_style.model_dump(by_alias=True, exclude_none=True),
        desired_style.model_dump(by_alias=True, exclude_none=True),
    )


# ---------------------------------------------------------------------------
# Request builder helpers
# ---------------------------------------------------------------------------


def _make_create_header(
    *,
    tab_id: str,
    header_type: str,
) -> Request:
    section_break_loc = Location(index=0, tab_id=tab_id) if tab_id else None
    return Request(
        create_header=CreateHeaderRequest(
            type=CreateFooterRequestType(header_type),
            section_break_location=section_break_loc,
        )
    )


def _make_create_footer(
    *,
    tab_id: str,
    footer_type: str,
) -> Request:
    section_break_loc = Location(index=0, tab_id=tab_id) if tab_id else None
    return Request(
        create_footer=CreateFooterRequest(
            type=CreateFooterRequestType(footer_type),
            section_break_location=section_break_loc,
        )
    )


def _make_delete_header(*, header_id: str, tab_id: str) -> Request:
    return Request(
        delete_header=DeleteHeaderRequest(
            header_id=header_id,
            tab_id=tab_id if tab_id else None,
        )
    )


def _make_delete_footer(*, footer_id: str, tab_id: str) -> Request:
    return Request(
        delete_footer=DeleteFooterRequest(
            footer_id=footer_id,
            tab_id=tab_id if tab_id else None,
        )
    )


def _make_delete_tab(*, tab_id: str) -> Request:
    return Request(
        delete_tab=DeleteTabRequest(tab_id=tab_id),
    )


def _make_add_document_tab(
    *,
    title: str,
    index: int | None = None,
    parent_tab_id: str | None = None,
) -> Request:
    return Request(
        add_document_tab=AddDocumentTabRequest(
            tab_properties=TabProperties(
                title=title,
                index=index,
                parent_tab_id=parent_tab_id,
            ),
        )
    )


def _make_create_footnote(*, index: int, tab_id: str) -> Request:
    """Build a createFootnote Request."""
    return Request(
        create_footnote=CreateFootnoteRequest(
            location=Location(
                index=index,
                tab_id=tab_id if tab_id else None,
            ),
        )
    )


def _make_delete_content_range(
    *,
    start_index: int,
    end_index: int,
    tab_id: _StrOrDeferred,
    segment_id: _StrOrDeferred | None = None,
) -> Request:
    return Request(
        delete_content_range=DeleteContentRangeRequest(
            range=Range(
                start_index=start_index,
                end_index=end_index,
                tab_id=tab_id if tab_id else None,
                segment_id=segment_id if segment_id else None,
            ),
        )
    )


def _make_insert_text(
    *,
    index: int,
    tab_id: _StrOrDeferred,
    segment_id: _StrOrDeferred | None,
    text: str,
) -> Request:
    return Request(
        insert_text=InsertTextRequest(
            location=Location(
                index=index,
                tab_id=tab_id if tab_id else None,
                segment_id=segment_id if segment_id else None,
            ),
            text=text,
        )
    )


def _make_update_paragraph_style(
    *,
    start_index: int,
    end_index: int,
    tab_id: _StrOrDeferred,
    segment_id: _StrOrDeferred | None,
    paragraph_style: ParagraphStyle | dict[str, object],
    fields: list[str],
) -> Request:
    ps = (
        paragraph_style
        if isinstance(paragraph_style, ParagraphStyle)
        else ParagraphStyle.model_validate(paragraph_style)
    )
    return Request(
        update_paragraph_style=UpdateParagraphStyleRequest(
            range=Range(
                start_index=start_index,
                end_index=end_index,
                tab_id=tab_id if tab_id else None,
                segment_id=segment_id if segment_id else None,
            ),
            paragraph_style=ps,
            fields=",".join(fields),
        )
    )


def _make_update_named_style(
    *,
    tab_id: str,
    style: NamedStyle,
) -> Request:
    """Emit an updateDocumentStyle request to update/insert a single named style.

    The Google Docs API uses ``updateDocumentStyle`` with a ``namedStyles``
    payload to update named styles.  Since the typed ``UpdateDocumentStyleRequest``
    model doesn't have a ``namedStyles`` field, we use ``model_validate`` with
    the raw dict to leverage ``extra="allow"`` on the model.
    """
    style_dict = style.model_dump(by_alias=True, exclude_none=True)
    inner: dict[str, object] = {
        "namedStyles": {
            "styles": [style_dict],
        },
        "fields": "namedStyles",
    }
    if tab_id:
        inner["tabId"] = tab_id
    return Request(
        update_document_style=UpdateDocumentStyleRequest.model_validate(inner),
    )


def _make_update_section_style_deferred(
    *,
    tab_id: str,
    field_name: str,
    deferred_id: DeferredID,
) -> Request:
    """Emit an updateSectionStyle that attaches a freshly created header/footer.

    The header/footer ID is a DeferredID placeholder resolved after Batch 0.
    We use a full-document range (0→1) which is the typical pattern for
    applying a header/footer to the DEFAULT slot.
    """
    # The field_name is a camelCase alias (e.g. "defaultHeaderId") and the
    # value is a DeferredID.  SectionStyle's typed fields are str | None,
    # so we use model_construct to bypass validation and inject the DeferredID.
    # Map camelCase alias → snake_case Python field name.
    _ALIAS_TO_FIELD = {
        "defaultHeaderId": "default_header_id",
        "firstPageHeaderId": "first_page_header_id",
        "evenPageHeaderId": "even_page_header_id",
        "defaultFooterId": "default_footer_id",
        "firstPageFooterId": "first_page_footer_id",
        "evenPageFooterId": "even_page_footer_id",
    }
    python_field = _ALIAS_TO_FIELD.get(field_name, field_name)
    # Deliberately inject DeferredID into a str field; resolved before execution.
    section_style = SectionStyle.model_construct(**{python_field: deferred_id})  # type: ignore[arg-type]
    return Request(
        update_section_style=UpdateSectionStyleRequest(
            range=Range(
                start_index=0,
                end_index=1,
                tab_id=tab_id if tab_id else None,
            ),
            section_style=section_style,
            fields=field_name,
        )
    )


# ---------------------------------------------------------------------------
# Table structural request helpers
# ---------------------------------------------------------------------------


def _table_start_location(
    *,
    table_start_index: int,
    tab_id: str,
) -> Location:
    return Location(
        index=table_start_index,
        tab_id=tab_id if tab_id else None,
    )


def _make_insert_table_row(
    *,
    table_start_index: int,
    row_index: int,
    insert_below: bool,
    tab_id: str,
) -> Request:
    return Request(
        insert_table_row=InsertTableRowRequest(
            table_cell_location=TableCellLocation(
                table_start_location=_table_start_location(
                    table_start_index=table_start_index,
                    tab_id=tab_id,
                ),
                row_index=row_index,
                column_index=0,
            ),
            insert_below=insert_below,
        )
    )


def _make_delete_table_row(
    *,
    table_start_index: int,
    row_index: int,
    tab_id: str,
) -> Request:
    return Request(
        delete_table_row=DeleteTableRowRequest(
            table_cell_location=TableCellLocation(
                table_start_location=_table_start_location(
                    table_start_index=table_start_index,
                    tab_id=tab_id,
                ),
                row_index=row_index,
                column_index=0,
            ),
        )
    )


def _make_insert_table_column(
    *,
    table_start_index: int,
    column_index: int,
    insert_right: bool,
    tab_id: str,
) -> Request:
    return Request(
        insert_table_column=InsertTableColumnRequest(
            table_cell_location=TableCellLocation(
                table_start_location=_table_start_location(
                    table_start_index=table_start_index,
                    tab_id=tab_id,
                ),
                row_index=0,
                column_index=column_index,
            ),
            insert_right=insert_right,
        )
    )


def _make_delete_table_column(
    *,
    table_start_index: int,
    column_index: int,
    tab_id: str,
) -> Request:
    return Request(
        delete_table_column=DeleteTableColumnRequest(
            table_cell_location=TableCellLocation(
                table_start_location=_table_start_location(
                    table_start_index=table_start_index,
                    tab_id=tab_id,
                ),
                row_index=0,
                column_index=column_index,
            ),
        )
    )


def _make_update_table_cell_style(
    *,
    table_start_index: int,
    row_index: int,
    column_index: int,
    desired_style: TableCellStyle,
    fields_mask: str,
    tab_id: str,
) -> Request:
    loc = _table_start_location(
        table_start_index=table_start_index,
        tab_id=tab_id,
    )
    return Request(
        update_table_cell_style=UpdateTableCellStyleRequest(
            table_start_location=loc,
            table_range=TableRange(
                table_cell_location=TableCellLocation(
                    table_start_location=_table_start_location(
                        table_start_index=table_start_index,
                        tab_id=tab_id,
                    ),
                    row_index=row_index,
                    column_index=column_index,
                ),
                row_span=1,
                column_span=1,
            ),
            table_cell_style=desired_style,
            fields=fields_mask,
        )
    )


def _make_update_table_row_style(
    *,
    table_start_index: int,
    row_index: int,
    min_row_height: Dimension | None,
    tab_id: str,
) -> Request:
    return Request(
        update_table_row_style=UpdateTableRowStyleRequest(
            table_start_location=_table_start_location(
                table_start_index=table_start_index,
                tab_id=tab_id,
            ),
            row_indices=[row_index],
            table_row_style=TableRowStyle(min_row_height=min_row_height),
            fields="minRowHeight",
        )
    )


def _make_update_table_column_properties(
    *,
    table_start_index: int,
    column_index: int,
    width: Dimension | None,
    width_type: str | None,
    tab_id: str,
) -> Request:
    fields_parts: list[str] = []
    if width is not None:
        fields_parts.append("width")
    if width_type is not None:
        fields_parts.append("widthType")
    fields_mask = ",".join(sorted(fields_parts)) if fields_parts else "widthType"
    return Request(
        update_table_column_properties=UpdateTableColumnPropertiesRequest(
            table_start_location=_table_start_location(
                table_start_index=table_start_index,
                tab_id=tab_id,
            ),
            column_indices=[column_index],
            table_column_properties=TableColumnProperties(
                width=width,
                width_type=width_type,
            ),
            fields=fields_mask,
        )
    )
