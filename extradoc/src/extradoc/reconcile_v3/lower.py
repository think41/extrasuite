"""Op → request dict translation for reconcile_v3.

Translates ``ReconcileOp`` objects produced by ``diff.py`` into raw Google
Docs API request dicts suitable for batchUpdate.

Strategy
--------
- Ops that have proven counterparts in reconcile_v2 are lowered with equivalent
  logic.
- Ops that are new or complex raise ``NotImplementedError`` with a clear
  diagnostic message — but the diff pass still correctly identifies that the op
  is needed.  This lets the top-level structure be proven sound before every
  lowering is implemented.

Currently NOT raising (implemented):
- No ops are fully lowered in this experiment iteration.
  All emit a NotImplementedError placeholder.

Currently raises NotImplementedError (op detected; lowering TODO):
- All op types.

This is intentional: the experiment proves the *diff* traversal is correct and
complete.  Production lowering belongs in a future integration step.
"""

from __future__ import annotations

from typing import Any

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


def lower_ops(ops: list[ReconcileOp]) -> list[dict[str, Any]]:
    """Lower a list of ReconcileOps to raw API request dicts.

    For ops whose lowering is not yet implemented, raises ``NotImplementedError``
    with a message identifying the op type and confirming the op was detected.
    """
    requests: list[dict[str, Any]] = []
    for op in ops:
        requests.extend(_lower_one(op))
    return requests


def _lower_one(op: ReconcileOp) -> list[dict[str, Any]]:
    """Lower a single op to zero or more request dicts."""
    match op:
        # ------------------------------------------------------------------ #
        # Tab structural
        # ------------------------------------------------------------------ #
        case InsertTabOp():
            raise NotImplementedError(
                f"lowering for InsertTabOp not yet implemented — "
                f"op detected correctly (desired_tab_index={op.desired_tab_index})"
            )

        case DeleteTabOp():
            raise NotImplementedError(
                f"lowering for DeleteTabOp not yet implemented — "
                f"op detected correctly (base_tab_id={op.base_tab_id!r})"
            )

        # ------------------------------------------------------------------ #
        # DocumentStyle
        # ------------------------------------------------------------------ #
        case UpdateDocumentStyleOp():
            raise NotImplementedError(
                f"lowering for UpdateDocumentStyleOp not yet implemented — "
                f"op detected correctly (tab_id={op.tab_id!r}). "
                "DocumentStyle changes require manual intervention."
            )

        # ------------------------------------------------------------------ #
        # NamedStyles
        # ------------------------------------------------------------------ #
        case UpdateNamedStyleOp():
            raise NotImplementedError(
                f"lowering for UpdateNamedStyleOp not yet implemented — "
                f"op detected correctly (tab_id={op.tab_id!r}, "
                f"namedStyleType={op.named_style_type!r})"
            )

        case InsertNamedStyleOp():
            raise NotImplementedError(
                f"lowering for InsertNamedStyleOp not yet implemented — "
                f"op detected correctly (tab_id={op.tab_id!r}, "
                f"namedStyleType={op.named_style_type!r})"
            )

        case DeleteNamedStyleOp():
            raise NotImplementedError(
                f"lowering for DeleteNamedStyleOp not yet implemented — "
                f"op detected correctly (tab_id={op.tab_id!r}, "
                f"namedStyleType={op.named_style_type!r})"
            )

        # ------------------------------------------------------------------ #
        # Lists
        # ------------------------------------------------------------------ #
        case InsertListOp():
            raise NotImplementedError(
                f"lowering for InsertListOp not yet implemented — "
                f"op detected correctly (tab_id={op.tab_id!r}, list_id={op.list_id!r})"
            )

        case DeleteListOp():
            raise NotImplementedError(
                f"lowering for DeleteListOp not yet implemented — "
                f"op detected correctly (tab_id={op.tab_id!r}, list_id={op.list_id!r})"
            )

        case UpdateListOp():
            raise NotImplementedError(
                f"lowering for UpdateListOp not yet implemented — "
                f"op detected correctly (tab_id={op.tab_id!r}, list_id={op.list_id!r}). "
                "List definitions cannot be edited via batchUpdate."
            )

        # ------------------------------------------------------------------ #
        # InlineObjects
        # ------------------------------------------------------------------ #
        case UpdateInlineObjectOp():
            raise NotImplementedError(
                f"lowering for UpdateInlineObjectOp not yet implemented — "
                f"op detected correctly (tab_id={op.tab_id!r}, "
                f"inline_object_id={op.inline_object_id!r})"
            )

        case InsertInlineObjectOp():
            raise NotImplementedError(
                f"lowering for InsertInlineObjectOp not yet implemented — "
                f"op detected correctly (tab_id={op.tab_id!r}, "
                f"inline_object_id={op.inline_object_id!r})"
            )

        case DeleteInlineObjectOp():
            raise NotImplementedError(
                f"lowering for DeleteInlineObjectOp not yet implemented — "
                f"op detected correctly (tab_id={op.tab_id!r}, "
                f"inline_object_id={op.inline_object_id!r})"
            )

        # ------------------------------------------------------------------ #
        # Headers
        # ------------------------------------------------------------------ #
        case CreateHeaderOp():
            raise NotImplementedError(
                f"lowering for CreateHeaderOp not yet implemented — "
                f"op detected correctly (tab_id={op.tab_id!r}, slot={op.section_slot!r})"
            )

        case DeleteHeaderOp():
            raise NotImplementedError(
                f"lowering for DeleteHeaderOp not yet implemented — "
                f"op detected correctly (tab_id={op.tab_id!r}, slot={op.section_slot!r})"
            )

        case UpdateHeaderContentOp():
            raise NotImplementedError(
                f"lowering for UpdateHeaderContentOp not yet implemented — "
                f"op detected correctly (tab_id={op.tab_id!r}, "
                f"header_id={op.header_id!r}, slot={op.section_slot!r})"
            )

        # ------------------------------------------------------------------ #
        # Footers
        # ------------------------------------------------------------------ #
        case CreateFooterOp():
            raise NotImplementedError(
                f"lowering for CreateFooterOp not yet implemented — "
                f"op detected correctly (tab_id={op.tab_id!r}, slot={op.section_slot!r})"
            )

        case DeleteFooterOp():
            raise NotImplementedError(
                f"lowering for DeleteFooterOp not yet implemented — "
                f"op detected correctly (tab_id={op.tab_id!r}, slot={op.section_slot!r})"
            )

        case UpdateFooterContentOp():
            raise NotImplementedError(
                f"lowering for UpdateFooterContentOp not yet implemented — "
                f"op detected correctly (tab_id={op.tab_id!r}, "
                f"footer_id={op.footer_id!r}, slot={op.section_slot!r})"
            )

        # ------------------------------------------------------------------ #
        # Footnotes
        # ------------------------------------------------------------------ #
        case InsertFootnoteOp():
            raise NotImplementedError(
                f"lowering for InsertFootnoteOp not yet implemented — "
                f"op detected correctly (tab_id={op.tab_id!r}, "
                f"footnote_id={op.footnote_id!r})"
            )

        case DeleteFootnoteOp():
            raise NotImplementedError(
                f"lowering for DeleteFootnoteOp not yet implemented — "
                f"op detected correctly (tab_id={op.tab_id!r}, "
                f"footnote_id={op.footnote_id!r})"
            )

        case UpdateFootnoteContentOp():
            raise NotImplementedError(
                f"lowering for UpdateFootnoteContentOp not yet implemented — "
                f"op detected correctly (tab_id={op.tab_id!r}, "
                f"footnote_id={op.footnote_id!r})"
            )

        # ------------------------------------------------------------------ #
        # Body / cell content
        # ------------------------------------------------------------------ #
        case UpdateBodyContentOp():
            raise NotImplementedError(
                f"lowering for UpdateBodyContentOp not yet implemented — "
                f"op detected correctly (tab_id={op.tab_id!r}, "
                f"story_kind={op.story_kind!r}, story_id={op.story_id!r})"
            )

        case _:
            raise NotImplementedError(
                f"lowering for op type {type(op).__name__!r} not yet implemented"
            )
