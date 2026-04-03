"""Op → request dict translation for reconcile_v3.

Translates ``ReconcileOp`` objects produced by ``diff.py`` into raw Google
Docs API request dicts suitable for batchUpdate.

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
deferred-ID placeholder dict that ``resolve_deferred_placeholders`` resolves
after Batch 1 executes.  The placeholder format matches the existing v2
executor contract::

    {
        "placeholder": True,
        "batch_index": 0,        # index into prior_responses
        "request_index": N,      # index of the createHeader request
        "response_path": "createHeader.headerId",
    }
"""

from __future__ import annotations

import copy
import difflib
from itertools import groupby
from typing import Any

from extradoc.indexer import utf16_len
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


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def lower_ops(ops: list[ReconcileOp]) -> list[dict[str, Any]]:
    """Lower a list of ReconcileOps to raw API request dicts (single batch).

    For ops whose lowering is not yet implemented, raises ``NotImplementedError``
    with a message identifying the op type and confirming the op was detected.
    """
    requests: list[dict[str, Any]] = []
    for op in ops:
        requests.extend(_lower_one(op))
    return requests


def lower_batches(
    ops: list[ReconcileOp],
    desired_lists_by_tab: dict[str, dict[str, Any]] | None = None,
    base_lists_by_tab: dict[str, dict[str, Any]] | None = None,
) -> list[list[dict[str, Any]]]:
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
    batch0: list[dict[str, Any]] = []  # structural creates
    batch1: list[dict[str, Any]] = []  # content + style + structural deletes
    batch2: list[dict[str, Any]] = []  # footnotes (future)

    _desired_lists_by_tab: dict[str, dict[str, Any]] = desired_lists_by_tab or {}
    _base_lists_by_tab: dict[str, dict[str, Any]] = base_lists_by_tab or {}

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
                deferred_id: dict[str, Any] = {
                    "placeholder": True,
                    "batch_index": 0,
                    "request_index": req_index,
                    "response_path": "createHeader.headerId",
                }
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
                    _lower_story_content_insert(
                        content=op.desired_content,
                        tab_id=op.tab_id,
                        deferred_segment_id=deferred_id,
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
                deferred_id = {
                    "placeholder": True,
                    "batch_index": 0,
                    "request_index": req_index,
                    "response_path": "createFooter.footerId",
                }
                field_name = _FOOTER_SLOT_FIELD[op.section_slot]
                batch1.append(
                    _make_update_section_style_deferred(
                        tab_id=op.tab_id,
                        field_name=field_name,
                        deferred_id=deferred_id,
                    )
                )
                batch1.extend(
                    _lower_story_content_insert(
                        content=op.desired_content,
                        tab_id=op.tab_id,
                        deferred_segment_id=deferred_id,
                    )
                )

            case InsertTabOp():
                props = op.desired_tab.get("tabProperties", {})
                title = props.get("title", "Untitled")
                index = props.get("index")
                parent_tab_id = props.get("parentTabId")
                batch0.append(
                    _make_add_document_tab(
                        title=title,
                        index=index,
                        parent_tab_id=parent_tab_id,
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
                # op.changed_fields already excludes header/footer ID fields
                # (those are managed structurally by CreateHeader/Footer ops).
                req: dict[str, Any] = {
                    "updateDocumentStyle": {
                        "documentStyle": op.changed_fields,
                        "fields": op.fields_mask,
                    }
                }
                if op.tab_id:
                    req["updateDocumentStyle"]["tabId"] = op.tab_id
                batch1.append(req)

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
                insert_req: dict[str, Any] = {
                    "insertInlineImage": {
                        "uri": op.content_uri,
                        "location": {
                            "index": op.insert_index,
                            "segmentId": op.tab_id,
                        },
                    }
                }
                if op.object_size is not None:
                    insert_req["insertInlineImage"]["objectSize"] = op.object_size
                batch1.append(insert_req)

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
                deferred_fn_id: dict[str, Any] = {
                    "placeholder": True,
                    "batch_index": 0,
                    "request_index": req_index,
                    "response_path": "createFootnote.footnoteId",
                }
                batch1.extend(
                    _lower_story_content_insert(
                        content=op.desired_content,
                        tab_id=op.tab_id,
                        deferred_segment_id=deferred_fn_id,
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
                        style_changes=op.style_changes,
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

    batches: list[list[dict[str, Any]]] = []
    if batch0:
        batches.append(batch0)
    if batch1:
        batches.append(batch1)
    if batch2:
        batches.append(batch2)
    return batches


def _lower_one(op: ReconcileOp) -> list[dict[str, Any]]:
    """Lower a single op to zero or more request dicts (single-batch mode).

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


def _infer_bullet_preset(bullet: dict[str, Any], lists: dict[str, Any]) -> str:
    """Infer the createParagraphBullets preset from the bullet's list definition.

    Reads the first NestingLevel from the lists dict to detect whether the list
    is numbered (glyphType set), a checkbox (GLYPH_TYPE_UNSPECIFIED), or
    unordered (glyphSymbol set).  Falls back to BULLET_DISC_CIRCLE_SQUARE for
    any missing or unrecognised data.
    """
    list_id = bullet.get("listId")
    if not list_id or not lists or list_id not in lists:
        return _DEFAULT_BULLET_PRESET

    list_obj = lists[list_id]
    lp = list_obj.get("listProperties", {})
    if not lp:
        return _DEFAULT_BULLET_PRESET
    nesting = lp.get("nestingLevels", [])
    if not nesting:
        return _DEFAULT_BULLET_PRESET

    level_0 = nesting[0]
    glyph_type: str = level_0.get("glyphType", "")
    glyph_symbol: str = level_0.get("glyphSymbol", "")

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
    tab_id: str,
    segment_id: str | None,
) -> dict[str, Any]:
    """Build a createParagraphBullets request dict."""
    range_: dict[str, Any] = {"startIndex": start, "endIndex": end}
    if tab_id:
        range_["tabId"] = tab_id
    if segment_id:
        range_["segmentId"] = segment_id
    return {"createParagraphBullets": {"range": range_, "bulletPreset": preset}}


def _make_delete_paragraph_bullets(
    *,
    start: int,
    end: int,
    tab_id: str,
    segment_id: str | None,
) -> dict[str, Any]:
    """Build a deleteParagraphBullets request dict."""
    range_: dict[str, Any] = {"startIndex": start, "endIndex": end}
    if tab_id:
        range_["tabId"] = tab_id
    if segment_id:
        range_["segmentId"] = segment_id
    return {"deleteParagraphBullets": {"range": range_}}


# ---------------------------------------------------------------------------
# Content update helpers
# ---------------------------------------------------------------------------


def _lower_story_content_update(
    alignment: Any,
    *,
    base_content: list[dict[str, Any]],
    desired_content: list[dict[str, Any]],
    tab_id: str,
    segment_id: str | None,
    desired_lists: dict[str, Any] | None = None,
    base_lists: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Lower a ContentAlignment into delete/insert/update request dicts.

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
    requests: list[dict[str, Any]] = []

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
    alignment: Any,
    base_content: list[dict[str, Any]],
    desired_content: list[dict[str, Any]],
    tab_id: str,
    segment_id: str | None,
    desired_lists: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
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
    planned: list[tuple[int, int, list[dict[str, Any]]]] = []

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
    requests: list[dict[str, Any]] = []

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
    reqs: list[dict[str, Any]],
    offset: int,
) -> list[dict[str, Any]]:
    """Return copies of style requests with all index values shifted by ``offset``.

    Only shifts ``updateParagraphStyle`` and ``updateTextStyle`` requests.
    Other request types are returned unchanged.  The shift is applied to the
    ``range`` dict's ``startIndex`` and ``endIndex`` fields.
    """
    if offset == 0:
        return reqs

    shifted: list[dict[str, Any]] = []
    for req in reqs:
        if "updateParagraphStyle" in req or "updateTextStyle" in req:
            req = copy.deepcopy(req)
            key = (
                "updateParagraphStyle"
                if "updateParagraphStyle" in req
                else "updateTextStyle"
            )
            rng = req[key].get("range", {})
            if "startIndex" in rng:
                rng["startIndex"] += offset
            if "endIndex" in rng:
                rng["endIndex"] += offset
        shifted.append(req)
    return shifted


def _emit_same_position_group(
    group: list[tuple[int, int, list[dict[str, Any]]]],
) -> list[dict[str, Any]]:
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
    per_element: list[
        tuple[dict[str, Any], dict[str, Any] | None, list[dict[str, Any]]]
    ] = []

    for _insert_pos, _desired_idx, reqs in reversed(group):
        ins: dict[str, Any] | None = None
        cb: dict[str, Any] | None = None
        style_reqs: list[dict[str, Any]] = []
        for req in reqs:
            if "insertText" in req:
                ins = req
            elif "createParagraphBullets" in req:
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

    combined_insert_texts: list[dict[str, Any]] = []
    merged_create_bullets: list[dict[str, Any]] = []
    all_style_reqs: list[dict[str, Any]] = []

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
        item_len = utf16_len(ins_req["insertText"].get("text", ""))
        all_style_reqs.extend(_shift_request_indices(s_reqs, cumulative))
        if cb_req is None:
            # Non-bullet item: just advance cumulative offset
            cumulative += item_len
            i += 1
            continue
        # Start of a bullet run — collect consecutive items with the same preset
        cb_inner = cb_req["createParagraphBullets"]
        preset = cb_inner.get("bulletPreset", "")
        tab_id = str(cb_inner.get("range", {}).get("tabId", ""))
        segment_id = cb_inner.get("range", {}).get("segmentId")
        run_start = base_pos + cumulative
        run_len = item_len
        j = i + 1
        inner_cumulative = item_len  # cumulative within the bullet run
        while j < len(desired_order):
            next_ins, next_cb, next_s_reqs = desired_order[j]
            if next_cb is None:
                break
            next_cb_inner = next_cb["createParagraphBullets"]
            next_preset = next_cb_inner.get("bulletPreset", "")
            next_tab = str(next_cb_inner.get("range", {}).get("tabId", ""))
            next_seg = next_cb_inner.get("range", {}).get("segmentId")
            if (next_preset, next_tab, next_seg) != (preset, tab_id, segment_id):
                break
            all_style_reqs.extend(
                _shift_request_indices(next_s_reqs, cumulative + inner_cumulative)
            )
            next_item_len = utf16_len(next_ins["insertText"].get("text", ""))
            run_len += next_item_len
            inner_cumulative += next_item_len
            j += 1
        # Emit ONE createParagraphBullets for this run
        merged: dict[str, Any] = {
            "createParagraphBullets": {
                "bulletPreset": preset,
                "range": {
                    "startIndex": run_start,
                    "endIndex": run_start + run_len,
                },
            }
        }
        if tab_id:
            merged["createParagraphBullets"]["range"]["tabId"] = tab_id
        if segment_id:
            merged["createParagraphBullets"]["range"]["segmentId"] = segment_id
        merged_create_bullets.append(merged)
        cumulative += run_len
        i = j

    # Emit: insertTexts first (reverse order, for correct document ordering),
    # then merged createParagraphBullets, then style requests.
    return combined_insert_texts + merged_create_bullets + all_style_reqs


def _deleted_chars_before(
    *,
    deleted_sizes: dict[int, int],
    base_content: list[dict[str, Any]],
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
    base_el: dict[str, Any],
    desired_el: dict[str, Any],
    tab_id: str,
    segment_id: str | None,
    pre_delete_shift: int = 0,
    desired_lists: dict[str, Any] | None = None,
    base_lists: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Lower an in-place element update (matched element, content changed).

    For paragraphs: replace text runs.
    For tables: raise NotImplementedError (complex; not yet implemented).
    For structural elements: no-op (cannot change their content).

    ``pre_delete_shift`` is the total number of characters removed by
    whole-element base_deletes whose startIndex is below this element's
    startIndex.  All generated request indices are shifted down by this
    amount to account for the prior deletions.
    """
    if "paragraph" in base_el and "paragraph" in desired_el:
        return _lower_paragraph_update(
            base_el=base_el,
            desired_el=desired_el,
            tab_id=tab_id,
            segment_id=segment_id,
            pre_delete_shift=pre_delete_shift,
            desired_lists=desired_lists or {},
            base_lists=base_lists or {},
        )
    elif "table" in base_el and "table" in desired_el:
        # Table cell content updates are emitted as separate UpdateBodyContentOp
        # ops with story_kind="table_cell" by the diff layer.  At the body level
        # a matched table pair means "same table, cells may have changed" — the
        # cell-level child ops handle the actual content edits.  No body-level
        # request is needed here.
        return []
    elif "sectionBreak" in base_el and "sectionBreak" in desired_el:
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
    base_el: dict[str, Any],
    desired_el: dict[str, Any],
    tab_id: str,
    segment_id: str | None,
    pre_delete_shift: int = 0,
    desired_lists: dict[str, Any] | None = None,
    base_lists: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
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
    base_para = base_el.get("paragraph", {})
    desired_para = desired_el.get("paragraph", {})

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


def _extract_runs(para: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Return list of (text, text_style) for each textRun element in a paragraph.

    Non-textRun elements (inline objects, footnote refs, etc.) are skipped.
    """
    runs: list[tuple[str, dict[str, Any]]] = []
    for el in para.get("elements", []):
        if "textRun" in el:
            tr = el["textRun"]
            text = tr.get("content", "")
            style = tr.get("textStyle", {})
            runs.append((text, style))
    return runs


def _runs_to_spans(
    runs: list[tuple[str, dict[str, Any]]],
) -> list[tuple[int, int, str, dict[str, Any]]]:
    """Convert runs to (start, end, text, style) spans with character offsets.

    Offsets are relative to the start of the paragraph (0-based).
    """
    spans: list[tuple[int, int, str, dict[str, Any]]] = []
    cursor = 0
    for text, style in runs:
        length = utf16_len(text)
        spans.append((cursor, cursor + length, text, style))
        cursor += length
    return spans


def _styles_equal(s1: dict[str, Any], s2: dict[str, Any]) -> bool:
    """Return True if two textStyle dicts are effectively equal.

    Missing keys are treated as default (falsy/None).
    """
    all_keys = set(s1) | set(s2)
    for k in all_keys:
        v1 = s1.get(k)
        v2 = s2.get(k)
        if v1 != v2:
            return False
    return True


def _diff_paragraph_runs(
    *,
    base_para: dict[str, Any],
    desired_para: dict[str, Any],
    story_offset: int,
    tab_id: str,
    segment_id: str | None,
) -> list[dict[str, Any]]:
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

    def style_at(
        spans: list[tuple[int, int, str, dict[str, Any]]], pos: int
    ) -> dict[str, Any]:
        """Return the textStyle for the character at the given offset."""
        for start, end, _text, style in spans:
            if start <= pos < end:
                return style
        return {}

    # Compute character-level diff
    matcher = difflib.SequenceMatcher(None, base_body, desired_body, autojunk=False)
    opcodes = matcher.get_opcodes()

    # Collect pending ops as (abs_start, abs_end, kind, extra)
    # kind ∈ {"delete", "insert", "update_style", "replace"}
    # We process in reverse order (highest index first).

    # Pending ops list: (sort_key, requests_list)
    # sort_key is the document-absolute start index (for descending sort)
    pending: list[tuple[int, list[dict[str, Any]]]] = []

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
            # The insertion happens at base position i1 (before any characters there).
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
    requests: list[dict[str, Any]] = []
    for _key, reqs in pending:
        requests.extend(reqs)

    return requests


def _style_update_ops_for_equal_span(
    *,
    base_spans: list[tuple[int, int, str, dict[str, Any]]],
    desired_spans: list[tuple[int, int, str, dict[str, Any]]],
    base_start: int,
    base_end: int,
    desired_start: int,
    desired_end: int,
    story_offset: int,
    tab_id: str,
    segment_id: str | None,
) -> list[tuple[int, list[dict[str, Any]]]]:
    """For an 'equal' diff chunk, emit updateTextStyle where style changed.

    We walk character-by-character through the equal span and group consecutive
    characters that share the same (base_style, desired_style) pair, then emit
    an updateTextStyle for each group where styles differ.

    Returns list of (abs_start, [request_dict]) pairs.
    """
    # Find all style-change sub-ranges within the equal span
    # Group by consecutive chars with same (base_style != desired_style)
    result: list[tuple[int, list[dict[str, Any]]]] = []

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
            changed_fields = _style_fields(b_style, d_style)
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
    spans: list[tuple[int, int, str, dict[str, Any]]],
    offset: int,
) -> dict[str, Any]:
    """Return the textStyle for the character at the given offset within spans."""
    for start, end, _text, style in spans:
        if start <= offset < end:
            return style
    return {}


def _next_span_boundary(
    spans: list[tuple[int, int, str, dict[str, Any]]],
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
    desired_spans: list[tuple[int, int, str, dict[str, Any]]],
    desired_start: int,
    desired_end: int,
    base_pos: int,
    story_offset: int,
    tab_id: str,
    segment_id: str | None,
) -> list[dict[str, Any]]:
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
    reqs: list[dict[str, Any]] = [
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
        if style:
            fields = list(style.keys())
            if fields:
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
    tab_id: str,
    segment_id: str | None,
    text_style: dict[str, Any],
    fields: list[str],
) -> dict[str, Any]:
    """Build an updateTextStyle request dict."""
    range_: dict[str, Any] = {
        "startIndex": start_index,
        "endIndex": end_index,
    }
    if tab_id:
        range_["tabId"] = tab_id
    if segment_id:
        range_["segmentId"] = segment_id
    return {
        "updateTextStyle": {
            "range": range_,
            "textStyle": text_style,
            "fields": ",".join(fields),
        }
    }


def _lower_para_style_update(
    *,
    base_para: dict[str, Any],
    desired_para: dict[str, Any],
    start_index: int,
    end_index: int,
    tab_id: str,
    segment_id: str | None,
    desired_lists: dict[str, Any] | None = None,
    base_lists: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
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
    requests: list[dict[str, Any]] = []

    base_bullet = base_para.get("bullet")
    desired_bullet = desired_para.get("bullet")

    if not base_bullet and desired_bullet:
        # Case A: paragraph gains a bullet
        nesting_level = desired_bullet.get("nestingLevel", 0) or 0
        preset = _infer_bullet_preset(desired_bullet, desired_lists or {})
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
        base_nesting = base_bullet.get("nestingLevel", 0) or 0
        desired_nesting = desired_bullet.get("nestingLevel", 0) or 0
        base_preset = _infer_bullet_preset(base_bullet, base_lists or {})
        desired_preset = _infer_bullet_preset(desired_bullet, desired_lists or {})
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
    base_ps = base_para.get("paragraphStyle", {})
    desired_ps = desired_para.get("paragraphStyle", {})

    if base_ps != desired_ps and desired_ps:
        # Compute changed fields — exclude bullet-managed indentation when
        # bullet ops were already emitted above (they set indentation).
        fields = _style_fields(base_ps, desired_ps)
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
    el: dict[str, Any],
    index: int,
    tab_id: str,
    segment_id: str | None,
    desired_lists: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Generate request(s) to insert a content element at the given index.

    For page break paragraphs: insertPageBreak.
    For paragraphs: insertText (text + \\n) + style requests.
    For tables: insertTable (dimensions only; cell content not yet supported).
    For section breaks: insertSectionBreak + optional updateSectionStyle.
    """
    if "paragraph" in el and _is_pagebreak_para(el["paragraph"]):
        return _lower_page_break_insert(
            index=index,
            tab_id=tab_id,
        )
    elif "paragraph" in el:
        return _lower_paragraph_insert(
            el=el,
            index=index,
            tab_id=tab_id,
            segment_id=segment_id,
            desired_lists=desired_lists or {},
        )
    elif "table" in el:
        return _lower_table_insert(
            el=el,
            index=index,
            tab_id=tab_id,
            segment_id=segment_id,
        )
    elif "sectionBreak" in el:
        return _lower_section_break_insert(
            el=el,
            index=index,
            tab_id=tab_id,
        )
    else:
        raise NotImplementedError(
            f"lowering for insertion of element kind {list(el.keys())!r} not yet implemented"
        )


def _lower_paragraph_insert(
    *,
    el: dict[str, Any],
    index: int,
    tab_id: str,
    segment_id: str | None,
    desired_lists: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
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
    requests: list[dict[str, Any]] = []

    para = el.get("paragraph", {})
    text = _para_text(para)
    text_len = utf16_len(text)

    bullet = para.get("bullet")
    if bullet:
        nesting_level = bullet.get("nestingLevel", 0) or 0
        tabs = "\t" * nesting_level
        preset = _infer_bullet_preset(bullet, desired_lists or {})
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
        desired_ps = para.get("paragraphStyle", {})
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
            if run_len > 0 and style:
                requests.append(
                    _make_update_text_style(
                        start_index=run_offset,
                        end_index=run_offset + run_len,
                        tab_id=tab_id,
                        segment_id=segment_id,
                        text_style=style,
                        fields=list(style.keys()),
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
        desired_ps = para.get("paragraphStyle", {})
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
            if run_len > 0 and style:
                requests.append(
                    _make_update_text_style(
                        start_index=run_offset,
                        end_index=run_offset + run_len,
                        tab_id=tab_id,
                        segment_id=segment_id,
                        text_style=style,
                        fields=list(style.keys()),
                    )
                )
            run_offset += run_len

    return requests


def _lower_table_insert(
    *,
    el: dict[str, Any],
    index: int,
    tab_id: str,
    segment_id: str | None,
) -> list[dict[str, Any]]:
    """Insert a table at ``index``.

    Only the table dimensions are lowered — cell content requires a separate
    pass that is not yet implemented.  Callers receive a single insertTable
    request with the correct row/column count.
    """
    table = el.get("table", {})
    rows = table.get("rows", len(table.get("tableRows", [])))
    cols = table.get("columns", 0)
    if cols == 0 and table.get("tableRows"):
        cols = len(table["tableRows"][0].get("tableCells", []))

    location: dict[str, Any] = {"index": index, "tabId": tab_id}
    if segment_id:
        location["segmentId"] = segment_id

    return [
        {
            "insertTable": {
                "rows": rows,
                "columns": cols,
                "location": location,
            }
        }
    ]


def _is_pagebreak_para(para: dict[str, Any]) -> bool:
    """Return True if a paragraph dict's only content element(s) include a pageBreak.

    A page break paragraph has a ``pageBreak`` element among its elements (plus
    an optional terminal ``\\n`` textRun).  Such paragraphs must be inserted via
    ``insertPageBreak``, not ``insertText``.
    """
    has_page_break = False
    for elem in para.get("elements", []):
        if "pageBreak" in elem:
            has_page_break = True
        elif "textRun" in elem:
            content = elem["textRun"].get("content", "")
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
    tab_id: str,
) -> list[dict[str, Any]]:
    """Insert a page break via ``insertPageBreak`` at ``index``.

    ``insertPageBreak`` inserts two characters (pageBreak element + newline).
    The ``segmentId`` field must be omitted — the API only allows page breaks
    in the document body.
    """
    location: dict[str, Any] = {"index": index}
    if tab_id:
        location["tabId"] = tab_id
    return [{"insertPageBreak": {"location": location}}]


def _lower_section_break_insert(
    *,
    el: dict[str, Any],
    index: int,
    tab_id: str,
) -> list[dict[str, Any]]:
    """Insert a section break via ``insertSectionBreak`` at ``index``.

    Reads ``sectionType`` from ``el["sectionBreak"]["sectionStyle"]["sectionType"]``;
    defaults to ``"NEXT_PAGE"`` if absent.

    If the ``sectionStyle`` contains additional style fields beyond
    ``sectionType``, emits a follow-up ``updateSectionStyle`` request covering
    the newly inserted section break character.
    """
    section_break = el.get("sectionBreak", {})
    section_style = section_break.get("sectionStyle", {})
    section_type = section_style.get("sectionType", "NEXT_PAGE")

    location: dict[str, Any] = {"index": index}
    if tab_id:
        location["tabId"] = tab_id

    requests: list[dict[str, Any]] = [
        {
            "insertSectionBreak": {
                "location": location,
                "sectionType": section_type,
            }
        }
    ]

    # Emit updateSectionStyle for any non-default style fields.
    # insertSectionBreak inserts 2 characters (newline + section break element),
    # so the section break lands at index+1 in the post-insert document.
    style_fields = [k for k in section_style if k != "sectionType"]
    if style_fields and section_style:
        style_to_apply = {k: section_style[k] for k in style_fields}
        range_: dict[str, Any] = {
            "startIndex": index + 1,
            "endIndex": index + 2,
        }
        if tab_id:
            range_["tabId"] = tab_id
        requests.append(
            {
                "updateSectionStyle": {
                    "range": range_,
                    "sectionStyle": style_to_apply,
                    "fields": ",".join(sorted(style_fields)),
                }
            }
        )

    return requests


def _lower_section_break_update(
    *,
    base_el: dict[str, Any],
    desired_el: dict[str, Any],
    tab_id: str,
) -> list[dict[str, Any]]:
    """Emit ``updateSectionStyle`` when a matched section break's style changed.

    The range covers the section break character itself (startIndex → endIndex).
    If ``sectionStyle`` is identical, returns an empty list.
    """
    base_style = base_el.get("sectionBreak", {}).get("sectionStyle", {})
    desired_style = desired_el.get("sectionBreak", {}).get("sectionStyle", {})

    changed_fields = _style_fields(base_style, desired_style)
    if not changed_fields:
        return []

    start, end = _element_range(base_el)
    if start is None or end is None:
        return []

    range_: dict[str, Any] = {"startIndex": start, "endIndex": end}
    if tab_id:
        range_["tabId"] = tab_id

    return [
        {
            "updateSectionStyle": {
                "range": range_,
                "sectionStyle": desired_style,
                "fields": ",".join(sorted(changed_fields)),
            }
        }
    ]


def _lower_story_content_insert(
    *,
    content: list[dict[str, Any]],
    tab_id: str,
    deferred_segment_id: dict[str, Any],
) -> list[dict[str, Any]]:
    """Insert desired content into a freshly created header or footer.

    The segment ID is deferred (not yet known from Batch 0 response).
    Uses ``endOfSegmentLocation`` with the deferred segment ID.

    Only simple paragraph text is supported here.  The terminal paragraph
    (trailing \\n) already exists in a new header/footer, so we skip it.
    """
    requests: list[dict[str, Any]] = []

    # Skip last element (terminal paragraph already exists in new segment)
    content_to_insert = content[:-1]

    # Track running offset for style requests.
    # A freshly created header/footer/footnote has one empty paragraph at [1, 2).
    cumulative_offset = 0

    for el in content_to_insert:
        if "paragraph" in el:
            para = el.get("paragraph", {})
            text = _para_text(para)
            # Use endOfSegmentLocation with deferred segment ID
            location: dict[str, Any] = {
                "tabId": tab_id,
                "segmentId": deferred_segment_id,
            }
            requests.append(
                {
                    "insertText": {
                        "endOfSegmentLocation": location,
                        "text": text,
                    }
                }
            )
            # Paragraph starts at 1 + cumulative_offset in the new segment
            para_start = 1 + cumulative_offset
            text_len = utf16_len(text)

            # Apply paragraph style
            desired_ps = para.get("paragraphStyle", {})
            if desired_ps:
                fields = list(desired_ps.keys())
                if fields:
                    range_: dict[str, Any] = {
                        "startIndex": para_start,
                        "endIndex": para_start + text_len,
                        "segmentId": deferred_segment_id,
                    }
                    if tab_id:
                        range_["tabId"] = tab_id
                    requests.append(
                        {
                            "updateParagraphStyle": {
                                "range": range_,
                                "paragraphStyle": desired_ps,
                                "fields": ",".join(fields),
                            }
                        }
                    )

            # Apply text styles for each run
            runs = _extract_runs(para)
            run_offset = para_start
            for text_content, style in runs:
                run_len = utf16_len(text_content)
                if run_len > 0 and style:
                    run_range: dict[str, Any] = {
                        "startIndex": run_offset,
                        "endIndex": run_offset + run_len,
                        "segmentId": deferred_segment_id,
                    }
                    if tab_id:
                        run_range["tabId"] = tab_id
                    requests.append(
                        {
                            "updateTextStyle": {
                                "range": run_range,
                                "textStyle": style,
                                "fields": ",".join(style.keys()),
                            }
                        }
                    )
                run_offset += run_len

            cumulative_offset += text_len

    return requests


# ---------------------------------------------------------------------------
# Element index helpers
# ---------------------------------------------------------------------------


def _element_range(el: dict[str, Any]) -> tuple[int | None, int | None]:
    """Return (startIndex, endIndex) from a content element dict, or (None, None)."""
    start = el.get("startIndex")
    end = el.get("endIndex")
    if isinstance(start, int) and isinstance(end, int):
        return start, end
    return None, None


def _element_start(el: dict[str, Any]) -> int | None:
    """Return startIndex from a content element dict, or None."""
    start = el.get("startIndex")
    return start if isinstance(start, int) else None


def _para_text(para: dict[str, Any]) -> str:
    """Return concatenated text from a paragraph dict."""
    return "".join(
        e.get("textRun", {}).get("content", "") for e in para.get("elements", [])
    )


def _style_fields(
    base_style: dict[str, Any],
    desired_style: dict[str, Any],
) -> list[str]:
    """Return the field names that differ between base and desired style dicts."""
    all_keys = set(base_style) | set(desired_style)
    return [k for k in all_keys if base_style.get(k) != desired_style.get(k)]


# ---------------------------------------------------------------------------
# Request builder helpers
# ---------------------------------------------------------------------------


def _make_create_header(
    *,
    tab_id: str,
    header_type: str,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"type": header_type}
    if tab_id:
        payload["sectionBreakLocation"] = {"index": 0, "tabId": tab_id}
    return {"createHeader": payload}


def _make_create_footer(
    *,
    tab_id: str,
    footer_type: str,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"type": footer_type}
    if tab_id:
        payload["sectionBreakLocation"] = {"index": 0, "tabId": tab_id}
    return {"createFooter": payload}


def _make_delete_header(*, header_id: str, tab_id: str) -> dict[str, Any]:
    req: dict[str, Any] = {"headerId": header_id}
    if tab_id:
        req["tabId"] = tab_id
    return {"deleteHeader": req}


def _make_delete_footer(*, footer_id: str, tab_id: str) -> dict[str, Any]:
    req: dict[str, Any] = {"footerId": footer_id}
    if tab_id:
        req["tabId"] = tab_id
    return {"deleteFooter": req}


def _make_delete_tab(*, tab_id: str) -> dict[str, Any]:
    return {"deleteDocumentTab": {"tabId": tab_id}}


def _make_add_document_tab(
    *,
    title: str,
    index: int | None = None,
    parent_tab_id: str | None = None,
) -> dict[str, Any]:
    tab_properties: dict[str, Any] = {"title": title}
    if index is not None:
        tab_properties["index"] = index
    if parent_tab_id is not None:
        tab_properties["parentTabId"] = parent_tab_id
    return {"addDocumentTab": {"tabProperties": tab_properties}}


def _make_create_footnote(*, index: int, tab_id: str) -> dict[str, Any]:
    """Build a createFootnote request dict."""
    payload: dict[str, Any] = {
        "location": {
            "index": index,
        }
    }
    if tab_id:
        payload["location"]["tabId"] = tab_id
    return {"createFootnote": payload}


def _make_delete_content_range(
    *,
    start_index: int,
    end_index: int,
    tab_id: str,
    segment_id: str | None = None,
) -> dict[str, Any]:
    range_: dict[str, Any] = {
        "startIndex": start_index,
        "endIndex": end_index,
    }
    if tab_id:
        range_["tabId"] = tab_id
    if segment_id:
        range_["segmentId"] = segment_id
    return {"deleteContentRange": {"range": range_}}


def _make_insert_text(
    *,
    index: int,
    tab_id: str,
    segment_id: str | None,
    text: str,
) -> dict[str, Any]:
    location: dict[str, Any] = {"index": index}
    if tab_id:
        location["tabId"] = tab_id
    if segment_id:
        location["segmentId"] = segment_id
    return {"insertText": {"location": location, "text": text}}


def _make_update_paragraph_style(
    *,
    start_index: int,
    end_index: int,
    tab_id: str,
    segment_id: str | None,
    paragraph_style: dict[str, Any],
    fields: list[str],
) -> dict[str, Any]:
    range_: dict[str, Any] = {
        "startIndex": start_index,
        "endIndex": end_index,
    }
    if tab_id:
        range_["tabId"] = tab_id
    if segment_id:
        range_["segmentId"] = segment_id
    return {
        "updateParagraphStyle": {
            "range": range_,
            "paragraphStyle": paragraph_style,
            "fields": ",".join(fields),
        }
    }


def _make_update_named_style(
    *,
    tab_id: str,
    style: dict[str, Any],
) -> dict[str, Any]:
    """Emit an updateDocumentStyle request to update/insert a single named style."""
    payload: dict[str, Any] = {
        "namedStyles": {
            "styles": [style],
        }
    }
    req: dict[str, Any] = {
        "namedStyles": payload["namedStyles"],
        "fields": "namedStyles",
    }
    if tab_id:
        req["tabId"] = tab_id
    return {"updateDocumentStyle": req}


def _make_update_section_style_deferred(
    *,
    tab_id: str,
    field_name: str,
    deferred_id: dict[str, Any],
) -> dict[str, Any]:
    """Emit an updateSectionStyle that attaches a freshly created header/footer.

    The header/footer ID is a deferred-ID placeholder resolved after Batch 0.
    We use a full-document range (0→1) which is the typical pattern for
    applying a header/footer to the DEFAULT slot.
    """
    range_: dict[str, Any] = {"startIndex": 0, "endIndex": 1}
    if tab_id:
        range_["tabId"] = tab_id
    return {
        "updateSectionStyle": {
            "range": range_,
            "sectionStyle": {
                field_name: deferred_id,
            },
            "fields": field_name,
        }
    }


# ---------------------------------------------------------------------------
# Table structural request helpers
# ---------------------------------------------------------------------------


def _table_start_location(
    *,
    table_start_index: int,
    tab_id: str,
) -> dict[str, Any]:
    loc: dict[str, Any] = {"index": table_start_index}
    if tab_id:
        loc["tabId"] = tab_id
    return loc


def _make_insert_table_row(
    *,
    table_start_index: int,
    row_index: int,
    insert_below: bool,
    tab_id: str,
) -> dict[str, Any]:
    return {
        "insertTableRow": {
            "tableCellLocation": {
                "tableStartLocation": _table_start_location(
                    table_start_index=table_start_index,
                    tab_id=tab_id,
                ),
                "rowIndex": row_index,
                "columnIndex": 0,
            },
            "insertBelow": insert_below,
        }
    }


def _make_delete_table_row(
    *,
    table_start_index: int,
    row_index: int,
    tab_id: str,
) -> dict[str, Any]:
    return {
        "deleteTableRow": {
            "tableCellLocation": {
                "tableStartLocation": _table_start_location(
                    table_start_index=table_start_index,
                    tab_id=tab_id,
                ),
                "rowIndex": row_index,
                "columnIndex": 0,
            }
        }
    }


def _make_insert_table_column(
    *,
    table_start_index: int,
    column_index: int,
    insert_right: bool,
    tab_id: str,
) -> dict[str, Any]:
    return {
        "insertTableColumn": {
            "tableCellLocation": {
                "tableStartLocation": _table_start_location(
                    table_start_index=table_start_index,
                    tab_id=tab_id,
                ),
                "rowIndex": 0,
                "columnIndex": column_index,
            },
            "insertRight": insert_right,
        }
    }


def _make_delete_table_column(
    *,
    table_start_index: int,
    column_index: int,
    tab_id: str,
) -> dict[str, Any]:
    return {
        "deleteTableColumn": {
            "tableCellLocation": {
                "tableStartLocation": _table_start_location(
                    table_start_index=table_start_index,
                    tab_id=tab_id,
                ),
                "rowIndex": 0,
                "columnIndex": column_index,
            }
        }
    }


def _make_update_table_cell_style(
    *,
    table_start_index: int,
    row_index: int,
    column_index: int,
    style_changes: dict[str, Any],
    fields_mask: str,
    tab_id: str,
) -> dict[str, Any]:
    return {
        "updateTableCellStyle": {
            "tableStartLocation": _table_start_location(
                table_start_index=table_start_index,
                tab_id=tab_id,
            ),
            "tableRange": {
                "tableCellLocation": {
                    "tableStartLocation": _table_start_location(
                        table_start_index=table_start_index,
                        tab_id=tab_id,
                    ),
                    "rowIndex": row_index,
                    "columnIndex": column_index,
                },
                "rowSpan": 1,
                "columnSpan": 1,
            },
            "tableCellStyle": style_changes,
            "fields": fields_mask,
        }
    }


def _make_update_table_row_style(
    *,
    table_start_index: int,
    row_index: int,
    min_row_height: dict[str, Any] | None,
    tab_id: str,
) -> dict[str, Any]:
    return {
        "updateTableRowStyle": {
            "tableStartLocation": _table_start_location(
                table_start_index=table_start_index,
                tab_id=tab_id,
            ),
            "rowIndices": [row_index],
            "tableRowStyle": {"minRowHeight": min_row_height},
            "fields": "minRowHeight",
        }
    }


def _make_update_table_column_properties(
    *,
    table_start_index: int,
    column_index: int,
    width: dict[str, Any] | None,
    width_type: str | None,
    tab_id: str,
) -> dict[str, Any]:
    col_props: dict[str, Any] = {}
    fields_parts: list[str] = []
    if width is not None:
        col_props["width"] = width
        fields_parts.append("width")
    if width_type is not None:
        col_props["widthType"] = width_type
        fields_parts.append("widthType")
    fields_mask = ",".join(sorted(fields_parts)) if fields_parts else "widthType"
    return {
        "updateTableColumnProperties": {
            "tableStartLocation": _table_start_location(
                table_start_index=table_start_index,
                tab_id=tab_id,
            ),
            "columnIndices": [column_index],
            "tableColumnProperties": col_props,
            "fields": fields_mask,
        }
    }
