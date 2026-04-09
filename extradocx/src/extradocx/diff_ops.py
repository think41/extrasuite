"""
Diff operation types for markdown AST diffing.

Each operation references a node in the **base** AST (via its xpath or index
path) and describes how the user intended to edit the markdown.

The eventual goal (not in scope here) is to project these operations back
onto the original DOCX document.

Operation types:

  Block-level:
    ReplaceHeading    — heading level or text changed
    ReplaceParagraph  — paragraph text/formatting changed
    ReplaceCodeBlock  — code block content or language changed
    InsertBlock       — a new block was added (no base counterpart)
    DeleteBlock       — a base block was removed
    ReplaceTable      — table content changed
    ReplaceListItem   — list item content changed
    ReplaceList       — list structure changed (items added/removed/reordered)
    ReplaceBlockQuote — block quote content changed

  Inline-level (nested within block ops when needed):
    ModifyText        — text content of a run changed
    ModifyFormatting  — formatting flags of a run changed (bold, italic, …)

Public API:
    DiffOp = Union of all operation types
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Union

from extradocx.ast_nodes import BlockNode, InlineNode

# ---------------------------------------------------------------------------
# Block-level operations
# ---------------------------------------------------------------------------


@dataclass
class InsertBlock:
    """A new block was inserted at a given position.

    ``position`` is the index in the parent's children list where the new
    block should be inserted.  ``block`` is the full derived AST node.
    """

    position: int
    block: BlockNode

    def __repr__(self) -> str:
        btype = type(self.block).__name__
        return f"InsertBlock(position={self.position}, block_type={btype})"


@dataclass
class DeleteBlock:
    """A block from the base AST was deleted.

    ``base_index`` is the index of the deleted block in the base document's
    children list.  ``base_xpath`` is the xpath of the deleted node (for
    traceability back to the DOCX).
    """

    base_index: int
    base_xpath: str

    def __repr__(self) -> str:
        return f"DeleteBlock(base_index={self.base_index}, xpath={self.base_xpath!r})"


@dataclass
class ReplaceHeading:
    """A heading's level or inline content changed.

    ``base_index``/``base_xpath`` identify the base node.
    ``new_level`` and ``new_children`` carry the desired state.
    """

    base_index: int
    base_xpath: str
    old_level: int
    new_level: int
    old_text: str
    new_text: str
    new_children: list[InlineNode] = field(default_factory=list)


@dataclass
class ReplaceParagraph:
    """A paragraph's inline content changed."""

    base_index: int
    base_xpath: str
    old_text: str
    new_text: str
    new_children: list[InlineNode] = field(default_factory=list)


@dataclass
class ReplaceCodeBlock:
    """A code block's content or language changed."""

    base_index: int
    base_xpath: str
    old_code: str
    new_code: str
    old_language: str
    new_language: str


@dataclass
class ReplaceTable:
    """Table content changed.  Carries the full derived table node."""

    base_index: int
    base_xpath: str
    new_rows: list  # list of TableRow from the derived AST


@dataclass
class ReplaceList:
    """A list (bullet or ordered) changed — items added, removed, or edited.

    ``item_ops`` describes per-item changes within the list.
    ``new_items`` is the full derived items list.
    """

    base_index: int
    base_xpath: str
    list_type: str  # "bullet" or "ordered"
    item_ops: list[ListItemOp] = field(default_factory=list)
    new_items: list = field(default_factory=list)  # list of ListItem


@dataclass
class ReplaceBlockQuote:
    """Block quote content changed."""

    base_index: int
    base_xpath: str
    inner_ops: list[DiffOp] = field(default_factory=list)


# ---------------------------------------------------------------------------
# List-item level operations (nested within ReplaceList)
# ---------------------------------------------------------------------------


@dataclass
class InsertListItem:
    """A new list item was inserted."""

    position: int
    item: object  # ListItem


@dataclass
class DeleteListItem:
    """A list item was removed."""

    base_item_index: int
    base_xpath: str


@dataclass
class ReplaceListItem:
    """A list item's content changed."""

    base_item_index: int
    base_xpath: str
    old_text: str
    new_text: str


ListItemOp = Union[InsertListItem, DeleteListItem, ReplaceListItem]


# ---------------------------------------------------------------------------
# Union of all diff operations
# ---------------------------------------------------------------------------

DiffOp = Union[
    InsertBlock,
    DeleteBlock,
    ReplaceHeading,
    ReplaceParagraph,
    ReplaceCodeBlock,
    ReplaceTable,
    ReplaceList,
    ReplaceBlockQuote,
]
