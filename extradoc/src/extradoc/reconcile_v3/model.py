"""Internal op types for reconcile_v3.

Each dataclass represents one detected difference between base and desired
documents.  The ``lower.py`` module translates these ops into raw Google Docs
API request dicts.

All ops carry a ``tab_id`` identifying which tab they target (empty string for
legacy single-tab documents).

Convention
----------
- ``base_*``    — values/IDs from the base (current) document
- ``desired_*`` — values/IDs from the desired (target) document
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from extradoc.reconcile_v3.content_align import ContentAlignment

# ---------------------------------------------------------------------------
# Tab-level structural ops
# ---------------------------------------------------------------------------


@dataclass
class InsertTabOp:
    """Insert a new tab at the given position."""

    desired_tab_index: int
    desired_tab: dict[str, Any]


@dataclass
class DeleteTabOp:
    """Delete an existing tab."""

    base_tab_id: str
    base_tab_index: int


# ---------------------------------------------------------------------------
# DocumentStyle
# ---------------------------------------------------------------------------


@dataclass
class UpdateDocumentStyleOp:
    """DocumentStyle changed between base and desired.

    Not yet implementable via batchUpdate — lowering raises NotImplementedError.
    Detected and reported so callers know a change exists.
    """

    tab_id: str
    base_style: dict[str, Any]
    desired_style: dict[str, Any]


# ---------------------------------------------------------------------------
# NamedStyles
# ---------------------------------------------------------------------------


@dataclass
class UpdateNamedStyleOp:
    """One named style's properties changed."""

    tab_id: str
    named_style_type: str
    base_style: dict[str, Any]
    desired_style: dict[str, Any]


@dataclass
class InsertNamedStyleOp:
    """A named style present in desired is absent in base."""

    tab_id: str
    named_style_type: str
    desired_style: dict[str, Any]


@dataclass
class DeleteNamedStyleOp:
    """A named style present in base is absent in desired."""

    tab_id: str
    named_style_type: str
    base_style: dict[str, Any]


# ---------------------------------------------------------------------------
# Lists
# ---------------------------------------------------------------------------


@dataclass
class InsertListOp:
    """A list present in desired is absent in base."""

    tab_id: str
    list_id: str
    list_def: dict[str, Any]


@dataclass
class DeleteListOp:
    """A list present in base is absent in desired."""

    tab_id: str
    list_id: str
    base_list_def: dict[str, Any]


@dataclass
class UpdateListOp:
    """A list's definition changed — not editable via API.

    Lowering raises NotImplementedError.
    """

    tab_id: str
    list_id: str
    base_list_def: dict[str, Any]
    desired_list_def: dict[str, Any]


# ---------------------------------------------------------------------------
# InlineObjects
# ---------------------------------------------------------------------------


@dataclass
class UpdateInlineObjectOp:
    """An inline object changed — not supported by reconcile_v3.

    Lowering raises NotImplementedError.
    """

    tab_id: str
    inline_object_id: str
    base_obj: dict[str, Any]
    desired_obj: dict[str, Any]


@dataclass
class InsertInlineObjectOp:
    """An inline object present in desired is absent in base."""

    tab_id: str
    inline_object_id: str
    desired_obj: dict[str, Any]


@dataclass
class DeleteInlineObjectOp:
    """An inline object present in base is absent in desired."""

    tab_id: str
    inline_object_id: str
    base_obj: dict[str, Any]


# ---------------------------------------------------------------------------
# Headers / Footers
# ---------------------------------------------------------------------------


@dataclass
class CreateHeaderOp:
    """A header slot needs to be created."""

    tab_id: str
    section_slot: str  # e.g. "DEFAULT", "FIRST_PAGE", "EVEN_PAGE"
    desired_header_id: str
    desired_content: list[dict[str, Any]]


@dataclass
class DeleteHeaderOp:
    """A header slot needs to be deleted."""

    tab_id: str
    section_slot: str
    base_header_id: str


@dataclass
class UpdateHeaderContentOp:
    """Header content changed — apply ContentAlignment to the header body."""

    tab_id: str
    section_slot: str
    header_id: str
    alignment: ContentAlignment
    base_content: list[dict[str, Any]]
    desired_content: list[dict[str, Any]]


@dataclass
class CreateFooterOp:
    """A footer slot needs to be created."""

    tab_id: str
    section_slot: str
    desired_footer_id: str
    desired_content: list[dict[str, Any]]


@dataclass
class DeleteFooterOp:
    """A footer slot needs to be deleted."""

    tab_id: str
    section_slot: str
    base_footer_id: str


@dataclass
class UpdateFooterContentOp:
    """Footer content changed — apply ContentAlignment to the footer body."""

    tab_id: str
    section_slot: str
    footer_id: str
    alignment: ContentAlignment
    base_content: list[dict[str, Any]]
    desired_content: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# Footnotes
# ---------------------------------------------------------------------------


@dataclass
class InsertFootnoteOp:
    """A footnote present in desired is absent in base (matched by footnoteId).

    ``anchor_index`` is the character offset in the body (base document
    coordinate space) where the ``createFootnote`` request should insert the
    footnote reference.  A value of -1 means the anchor could not be
    determined from the available index information; lowering will raise
    ``NotImplementedError`` in that case.
    """

    tab_id: str
    footnote_id: str
    desired_content: list[dict[str, Any]]
    anchor_index: int = -1


@dataclass
class DeleteFootnoteOp:
    """A footnote present in base is absent in desired.

    ``ref_index`` is the character offset of the ``footnoteReference`` element
    in the base document body.  A value of -1 means the offset could not be
    determined; lowering will raise ``NotImplementedError`` in that case.
    """

    tab_id: str
    footnote_id: str
    ref_index: int = -1


@dataclass
class UpdateFootnoteContentOp:
    """Footnote content changed — matched by footnoteId."""

    tab_id: str
    footnote_id: str
    alignment: ContentAlignment
    base_content: list[dict[str, Any]]
    desired_content: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# Body content
# ---------------------------------------------------------------------------


@dataclass
class UpdateBodyContentOp:
    """The body (or a header/footer/footnote/cell) content diff."""

    tab_id: str
    story_kind: str  # "body" | "header" | "footer" | "footnote" | "table_cell"
    story_id: str  # for scoping; e.g. header_id, footnote_id, "r{r}:c{c}"
    alignment: ContentAlignment
    base_content: list[dict[str, Any]]
    desired_content: list[dict[str, Any]]
    child_ops: list[Any] = field(default_factory=list)


# Unified type alias for all op types.
ReconcileOp = (
    InsertTabOp
    | DeleteTabOp
    | UpdateDocumentStyleOp
    | UpdateNamedStyleOp
    | InsertNamedStyleOp
    | DeleteNamedStyleOp
    | InsertListOp
    | DeleteListOp
    | UpdateListOp
    | UpdateInlineObjectOp
    | InsertInlineObjectOp
    | DeleteInlineObjectOp
    | CreateHeaderOp
    | DeleteHeaderOp
    | UpdateHeaderContentOp
    | CreateFooterOp
    | DeleteFooterOp
    | UpdateFooterContentOp
    | InsertFootnoteOp
    | DeleteFootnoteOp
    | UpdateFootnoteContentOp
    | UpdateBodyContentOp
)
