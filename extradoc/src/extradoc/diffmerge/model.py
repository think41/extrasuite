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
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from extradoc.api_types._generated import (
        Dimension,
        DocumentStyle,
        InlineObject,
        List,
        NamedStyle,
        Range,
        Size,
        StructuralElement,
        Tab,
        TableCellStyle,
    )
    from extradoc.diffmerge.content_align import ContentAlignment

# ---------------------------------------------------------------------------
# Tab-level structural ops
# ---------------------------------------------------------------------------


@dataclass
class InsertTabOp:
    """Insert a new tab at the given position."""

    desired_tab_index: int
    desired_tab: Tab


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
    """Writable DocumentStyle fields changed between base and desired.

    Only carries the fields that actually changed (header/footer ID fields are
    excluded — those are managed structurally by header/footer ops).

    ``desired_style`` carries the full desired ``DocumentStyle`` model.
    ``fields_mask`` is the comma-separated field-mask string required by the
    Google Docs ``updateDocumentStyle`` request (only the changed fields).
    """

    tab_id: str
    desired_style: DocumentStyle
    fields_mask: str


# ---------------------------------------------------------------------------
# NamedStyles
# ---------------------------------------------------------------------------


@dataclass
class UpdateNamedStyleOp:
    """One named style's properties changed."""

    tab_id: str
    named_style_type: str
    base_style: NamedStyle
    desired_style: NamedStyle


@dataclass
class InsertNamedStyleOp:
    """A named style present in desired is absent in base."""

    tab_id: str
    named_style_type: str
    desired_style: NamedStyle


@dataclass
class DeleteNamedStyleOp:
    """A named style present in base is absent in desired."""

    tab_id: str
    named_style_type: str
    base_style: NamedStyle


# ---------------------------------------------------------------------------
# Lists
# ---------------------------------------------------------------------------


@dataclass
class InsertListOp:
    """A list present in desired is absent in base."""

    tab_id: str
    list_id: str
    list_def: List


@dataclass
class DeleteListOp:
    """A list present in base is absent in desired."""

    tab_id: str
    list_id: str
    base_list_def: List


@dataclass
class UpdateListOp:
    """A list's definition changed — not editable via API.

    Lowering raises NotImplementedError.
    """

    tab_id: str
    list_id: str
    base_list_def: List
    desired_list_def: List


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
    base_obj: InlineObject
    desired_obj: InlineObject


@dataclass
class InsertInlineObjectOp:
    """Insert an inline image into a paragraph.

    Emitted when an ``inlineObjectElement`` appears in the desired paragraph
    but not in the base paragraph.  The image is inserted via
    ``insertInlineImage`` at ``insert_index`` in the flat document space.

    Fields
    ------
    tab_id:
        Target tab (empty string for legacy single-tab documents).
    inline_object_id:
        The ``inlineObjectId`` key from the desired document's
        ``inlineObjects`` map.
    content_uri:
        The ``imageProperties.contentUri`` from the desired inline object —
        this is the URL passed to ``insertInlineImage``.
    insert_index:
        The character position in the flat document space where the image
        element should be inserted.
    object_size:
        Optional ``embeddedObject.size`` dict (contains ``width`` and
        ``height`` Dimension dicts).  Passed as ``objectSize`` to
        ``insertInlineImage`` when present.
    """

    tab_id: str
    inline_object_id: str
    content_uri: str
    insert_index: int
    object_size: Size | None = None


@dataclass
class DeleteInlineObjectOp:
    """Delete an inline image from a paragraph.

    Emitted when an ``inlineObjectElement`` appears in the base paragraph but
    not in the desired paragraph.  Deletion is done via ``deleteContentRange``
    on the single character occupied by the element.

    Fields
    ------
    tab_id:
        Target tab (empty string for legacy single-tab documents).
    inline_object_id:
        The ``inlineObjectId`` key from the base document's ``inlineObjects``
        map.
    delete_index:
        The ``startIndex`` of the ``inlineObjectElement`` in the base
        document.  The element occupies exactly 1 character, so the range
        ``[delete_index, delete_index + 1)`` is deleted.
    """

    tab_id: str
    inline_object_id: str
    delete_index: int


# ---------------------------------------------------------------------------
# Headers / Footers
# ---------------------------------------------------------------------------


@dataclass
class CreateHeaderOp:
    """A header slot needs to be created."""

    tab_id: str
    section_slot: str  # e.g. "DEFAULT", "FIRST_PAGE", "EVEN_PAGE"
    desired_header_id: str
    desired_content: list[StructuralElement]


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
    base_content: list[StructuralElement]
    desired_content: list[StructuralElement]


@dataclass
class CreateFooterOp:
    """A footer slot needs to be created."""

    tab_id: str
    section_slot: str
    desired_footer_id: str
    desired_content: list[StructuralElement]


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
    base_content: list[StructuralElement]
    desired_content: list[StructuralElement]


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
    desired_content: list[StructuralElement]
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
    base_content: list[StructuralElement]
    desired_content: list[StructuralElement]


# ---------------------------------------------------------------------------
# Table structural ops
# ---------------------------------------------------------------------------


@dataclass
class InsertTableRowOp:
    """Insert a new row into an existing table.

    ``new_cell_texts`` carries the desired text for each of the new row's cells
    (one entry per column, in column order). The lowering layer uses this to
    emit ``insertText`` requests that populate the newly-created (otherwise
    empty) cells. When the desired row has no text content, each entry is the
    empty string.

    ``new_row_start_index`` is the byte index in the BASE document where the
    new row will begin after ``insertTableRow`` executes. For ``insert_below``
    this is the anchor row's ``end_index``; for ``insert_above`` it is the
    anchor row's ``start_index``. It is used by lowering to compute the byte
    offsets of each new cell's first paragraph for the ``insertText`` calls.
    """

    tab_id: str
    table_start_index: int  # startIndex of the table in the flat doc space
    row_index: int  # where to insert (0-based, refers to base row)
    insert_below: bool  # True = insert after row_index, False = insert before
    column_count: int  # needed to create blank cells
    # ``new_row_start_index`` is the byte index where the new row will begin
    # after ``insertTableRow`` executes. It is populated whenever the base
    # anchor row carries API-assigned indices (i.e. when reconciling real
    # pulled documents). Synthetic unit-test tables without index info leave
    # this unset; in that case ``new_cell_texts`` is also empty and lowering
    # emits only the structural ``insertTableRow`` request (no cell-text
    # population).
    new_row_start_index: int | None = None
    new_cell_texts: list[str] = field(default_factory=list)  # one text per column


@dataclass
class DeleteTableRowOp:
    """Delete a row from an existing table."""

    tab_id: str
    table_start_index: int
    row_index: int


@dataclass
class InsertTableColumnOp:
    """Insert a new column into an existing table.

    ``new_cell_texts`` carries the desired text for each of the new column's
    cells, one entry per base row in row order. ``new_cell_anchor_indices``
    carries the corresponding BASE byte index of the anchor cell's boundary
    used to compute each new cell's paragraph offset after
    ``insertTableColumn`` executes:

    - For ``insert_right=True`` this is the anchor cell's ``end_index``.
    - For ``insert_right=False`` this is the anchor cell's ``start_index``.

    Lowering converts each (anchor, row_idx) pair into the post-insert
    absolute byte index of that new cell's ``\\n`` paragraph (shifted by
    ``row_idx * _EMPTY_CELL_SIZE`` bytes for the earlier rows' new cells) and
    emits an ``insertText`` per non-empty cell in reverse row order so earlier
    inserts do not invalidate later offsets.

    ``new_cell_anchor_indices`` is populated whenever the base table carries
    API-assigned indices. Synthetic unit-test tables without index info leave
    it as an empty list; in that case ``new_cell_texts`` is also empty and
    lowering emits only the structural ``insertTableColumn`` request.
    """

    tab_id: str
    table_start_index: int
    column_index: int  # where to insert (0-based, refers to base column)
    insert_right: bool  # True = insert after column_index, False = insert before
    # Per-base-row anchor byte indices (from the base document). Same length as
    # ``new_cell_texts`` when populated, empty otherwise. Each entry's value
    # is the base cell's ``end_index`` (insert_right=True) or ``start_index``
    # (insert_right=False). ``None`` at a given row means that specific row
    # had no index info — lowering will raise if any cell at that row has
    # non-empty text.
    new_cell_anchor_indices: list[int | None] = field(default_factory=list)
    new_cell_texts: list[str] = field(default_factory=list)  # one text per base row


@dataclass
class DeleteTableColumnOp:
    """Delete a column from an existing table."""

    tab_id: str
    table_start_index: int
    column_index: int


# ---------------------------------------------------------------------------
# Table style ops
# ---------------------------------------------------------------------------


@dataclass
class UpdateTableCellStyleOp:
    """A table cell's style changed."""

    tab_id: str
    table_start_index: int
    row_index: int
    column_index: int
    desired_style: TableCellStyle
    fields_mask: str  # comma-separated field names for the updateFields mask


@dataclass
class UpdateTableRowStyleOp:
    """A table row's style changed."""

    tab_id: str
    table_start_index: int
    row_index: int
    min_row_height: Dimension | None  # Dimension or None


@dataclass
class UpdateTableColumnPropertiesOp:
    """A table column's properties changed."""

    tab_id: str
    table_start_index: int
    column_index: int
    width: Dimension | None  # Dimension or None
    width_type: str | None  # "EVENLY_DISTRIBUTED" | "FIXED_WIDTH" | None


# ---------------------------------------------------------------------------
# Named Ranges
# ---------------------------------------------------------------------------


@dataclass
class InsertNamedRangeOp:
    """A named range present in desired is absent in base (or has changed spans).

    One request per Range in ``ranges`` must be emitted
    (``createNamedRange`` does not accept multiple spans at once).
    """

    tab_id: str
    name: str
    named_range_id: str  # from the desired document
    ranges: list[Range]  # the spans to create


@dataclass
class DeleteNamedRangeOp:
    """A named range present in base is absent in desired (or has changed spans)."""

    tab_id: str
    named_range_id: str  # from the base document
    name: str  # for diagnostic clarity


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
    base_content: list[StructuralElement]
    desired_content: list[StructuralElement]
    child_ops: list[ReconcileOp] = field(default_factory=list)


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
    | InsertNamedRangeOp
    | DeleteNamedRangeOp
    | UpdateBodyContentOp
    | InsertTableRowOp
    | DeleteTableRowOp
    | InsertTableColumnOp
    | DeleteTableColumnOp
    | UpdateTableCellStyleOp
    | UpdateTableRowStyleOp
    | UpdateTableColumnPropertiesOp
)
