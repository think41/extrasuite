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

import difflib
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
) -> list[list[dict[str, Any]]]:
    """Lower ops into an ordered list of request batches.

    Batch 0: Structural creation (createHeader, createFooter, addDocumentTab).
    Batch 1: All content + style + structural-delete operations.
    Batch 2: Footnote operations (reserved; currently empty).

    Returns only non-empty batches.

    Deferred-ID placeholders in Batch 1 refer to Batch 0 responses and must
    be resolved via ``resolve_deferred_placeholders`` before execution.
    """
    batch0: list[dict[str, Any]] = []  # structural creates
    batch1: list[dict[str, Any]] = []  # content + style + structural deletes
    batch2: list[dict[str, Any]] = []  # footnotes (future)

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
            # DocumentStyle
            # ---------------------------------------------------------------- #
            case UpdateDocumentStyleOp():
                # Header/footer ID fields in documentStyle are managed via
                # CreateHeaderOp/CreateFooterOp/DeleteHeaderOp/DeleteFooterOp.
                # Suppress the UpdateDocumentStyleOp if the only difference is
                # header/footer ID fields (those are handled structurally).
                # For other documentStyle changes, raise — they require manual work.
                _HEADER_FOOTER_FIELDS = {
                    "defaultHeaderId",
                    "firstPageHeaderId",
                    "evenPageHeaderId",
                    "defaultFooterId",
                    "firstPageFooterId",
                    "evenPageFooterId",
                    "useFirstPageHeaderFooter",
                    "useEvenPageHeaderFooter",
                }
                base_s = {
                    k: v
                    for k, v in op.base_style.items()
                    if k not in _HEADER_FOOTER_FIELDS
                }
                desired_s = {
                    k: v
                    for k, v in op.desired_style.items()
                    if k not in _HEADER_FOOTER_FIELDS
                }
                if base_s != desired_s:
                    raise NotImplementedError(
                        f"lowering for UpdateDocumentStyleOp not implemented — "
                        f"DocumentStyle changes (excluding header/footer IDs) cannot "
                        f"be applied via batchUpdate. (tab_id={op.tab_id!r})"
                    )
                # Only header/footer ID fields changed — handled structurally.

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
            # InlineObjects — unsupported
            # ---------------------------------------------------------------- #
            case UpdateInlineObjectOp():
                raise NotImplementedError(
                    f"lowering for UpdateInlineObjectOp not supported — "
                    f"inline object properties cannot be edited via batchUpdate. "
                    f"(tab_id={op.tab_id!r}, inline_object_id={op.inline_object_id!r})"
                )

            case InsertInlineObjectOp():
                raise NotImplementedError(
                    f"lowering for InsertInlineObjectOp not supported — "
                    f"inline object insertion is not yet implemented. "
                    f"(tab_id={op.tab_id!r}, inline_object_id={op.inline_object_id!r})"
                )

            case DeleteInlineObjectOp():
                raise NotImplementedError(
                    f"lowering for DeleteInlineObjectOp not supported — "
                    f"inline object deletion is not yet implemented. "
                    f"(tab_id={op.tab_id!r}, inline_object_id={op.inline_object_id!r})"
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
# Content update helpers
# ---------------------------------------------------------------------------


def _lower_story_content_update(
    alignment: Any,
    *,
    base_content: list[dict[str, Any]],
    desired_content: list[dict[str, Any]],
    tab_id: str,
    segment_id: str | None,
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
        )
        requests.extend(insert_requests)

    # Handle matched elements whose content differs (text updates).
    for match in alignment.matches:
        b_el = base_content[match.base_idx]
        d_el = desired_content[match.desired_idx]
        if b_el == d_el:
            continue
        update_reqs = _lower_element_update(
            base_el=b_el,
            desired_el=d_el,
            tab_id=tab_id,
            segment_id=segment_id,
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

    requests: list[dict[str, Any]] = []

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
        )
        requests.extend(reqs)

    return requests


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
) -> list[dict[str, Any]]:
    """Lower an in-place element update (matched element, content changed).

    For paragraphs: replace text runs.
    For tables: raise NotImplementedError (complex; not yet implemented).
    For structural elements: no-op (cannot change their content).
    """
    if "paragraph" in base_el and "paragraph" in desired_el:
        return _lower_paragraph_update(
            base_el=base_el,
            desired_el=desired_el,
            tab_id=tab_id,
            segment_id=segment_id,
        )
    elif "table" in base_el and "table" in desired_el:
        # Table cell content updates are emitted as separate UpdateBodyContentOp
        # ops with story_kind="table_cell" by the diff layer.  At the body level
        # a matched table pair means "same table, cells may have changed" — the
        # cell-level child ops handle the actual content edits.  No body-level
        # request is needed here.
        return []
    else:
        # Section breaks, TOC etc. — no content to update
        return []


def _lower_paragraph_update(
    *,
    base_el: dict[str, Any],
    desired_el: dict[str, Any],
    tab_id: str,
    segment_id: str | None,
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

    # Always compute run-level diff (handles text changes + text-style changes).
    # For the same-text case this emits only updateTextStyle for changed runs.
    # For the changed-text case this emits delete/insert/updateTextStyle as needed.
    requests = _diff_paragraph_runs(
        base_para=base_para,
        desired_para=desired_para,
        story_offset=start,
        tab_id=tab_id,
        segment_id=segment_id,
    )

    # Additionally apply paragraph-level style changes (alignment, spacing, etc.)
    # regardless of whether text changed.
    style_reqs = _lower_para_style_update(
        base_para=base_para,
        desired_para=desired_para,
        start_index=start,
        end_index=end,
        tab_id=tab_id,
        segment_id=segment_id,
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

        # Find next boundary in either base or desired spans
        b_next = _next_span_boundary(base_spans, i, base_end)
        d_next = _next_span_boundary(desired_spans, j, desired_end)
        chunk_end = min(b_next, d_next)

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

        step = chunk_end - i
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
) -> list[dict[str, Any]]:
    """Emit paragraphStyle / textStyle update requests if styles changed."""
    requests: list[dict[str, Any]] = []

    base_ps = base_para.get("paragraphStyle", {})
    desired_ps = desired_para.get("paragraphStyle", {})

    if base_ps != desired_ps and desired_ps:
        # Compute changed fields
        fields = _style_fields(base_ps, desired_ps)
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
) -> list[dict[str, Any]]:
    """Generate request(s) to insert a content element at the given index.

    For paragraphs: insertText (text + \\n) + style requests.
    For tables: insertTable (dimensions only; cell content not yet supported).
    For structural elements: raises NotImplementedError.
    """
    if "paragraph" in el:
        return _lower_paragraph_insert(
            el=el,
            index=index,
            tab_id=tab_id,
            segment_id=segment_id,
        )
    elif "table" in el:
        return _lower_table_insert(
            el=el,
            index=index,
            tab_id=tab_id,
            segment_id=segment_id,
        )
    elif "sectionBreak" in el:
        # Section breaks cannot be inserted via insertText; skip.
        raise NotImplementedError(
            "lowering for section break insertion not yet implemented"
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
) -> list[dict[str, Any]]:
    """Insert a paragraph at ``index`` via insertText + optional style."""
    requests: list[dict[str, Any]] = []

    para = el.get("paragraph", {})
    text = _para_text(para)

    # Ensure text ends with \n (paragraph terminator)
    if not text.endswith("\n"):
        text = text + "\n"

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
        fields = list(desired_ps.keys())
        if fields:
            requests.append(
                _make_update_paragraph_style(
                    start_index=index,
                    end_index=index + utf16_len(text),
                    tab_id=tab_id,
                    segment_id=segment_id,
                    paragraph_style=desired_ps,
                    fields=fields,
                )
            )

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

    # Filter out trailing terminal paragraphs (already exist in new segment)
    content_to_insert = [el for el in content if not _is_terminal_paragraph(el)]

    for el in content_to_insert:
        if "paragraph" in el:
            para = el.get("paragraph", {})
            text = _para_text(para)
            if not text.endswith("\n"):
                text = text + "\n"
            if text.strip():
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


def _is_terminal_paragraph(el: dict[str, Any]) -> bool:
    """Return True if el is a paragraph whose only content is a bare newline."""
    if "paragraph" not in el:
        return False
    text = _para_text(el["paragraph"])
    return text == "\n"


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
