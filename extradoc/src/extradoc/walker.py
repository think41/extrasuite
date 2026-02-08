"""Backwards walk over the change tree to produce request list.

The walker visits SEGMENT children of the root DOCUMENT node,
then within each segment walks children from highest pristine_start
to lowest, delegating to the appropriate generator.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .types import (
    ChangeNode,
    ChangeOp,
    NodeType,
    SegmentContext,
    SegmentType,
)

if TYPE_CHECKING:
    from .generators.content import ContentGenerator
    from .generators.structural import StructuralGenerator
    from .generators.table import TableGenerator


class RequestWalker:
    """Walks the change tree and produces a flat list of batchUpdate requests."""

    def __init__(
        self,
        content_gen: ContentGenerator,
        table_gen: TableGenerator,
        structural_gen: StructuralGenerator,
    ) -> None:
        self._content_gen = content_gen
        self._table_gen = table_gen
        self._structural_gen = structural_gen

    def walk(self, root: ChangeNode) -> list[dict[str, Any]]:
        """Walk the entire change tree and return requests in execution order."""
        requests: list[dict[str, Any]] = []

        for child in root.children:
            if child.node_type == NodeType.TAB:
                if child.op in (ChangeOp.ADDED, ChangeOp.DELETED):
                    requests.extend(self._structural_gen.emit_tab(child))
                elif child.op == ChangeOp.MODIFIED:
                    requests.extend(self._walk_tab(child))

        return requests

    def _walk_tab(self, tab_node: ChangeNode) -> list[dict[str, Any]]:
        """Walk a single tab's segment children."""
        requests: list[dict[str, Any]] = []
        tab_id = tab_node.tab_id
        if not tab_id:
            raise ValueError("TAB change node must have tab_id set")

        for seg_node in tab_node.children:
            if seg_node.node_type != NodeType.SEGMENT:
                continue

            # Handle segment-level structural changes (add/delete)
            if seg_node.op in (ChangeOp.ADDED, ChangeOp.DELETED):
                if seg_node.segment_type in (SegmentType.HEADER, SegmentType.FOOTER):
                    requests.extend(
                        self._structural_gen.emit_header_footer(seg_node, tab_id=tab_id)
                    )
                elif seg_node.segment_type == SegmentType.FOOTNOTE:
                    requests.extend(
                        self._structural_gen.emit_footnote(seg_node, tab_id=tab_id)
                    )
                continue

            # For MODIFIED segments, walk children backwards
            requests.extend(self._walk_segment(seg_node, tab_id=tab_id))

        return requests

    def _walk_segment(
        self, seg_node: ChangeNode, *, tab_id: str
    ) -> list[dict[str, Any]]:
        """Walk a single segment's children from highest to lowest pristine_start."""
        requests: list[dict[str, Any]] = []

        segment_id = self._resolve_segment_id(seg_node)
        ctx = SegmentContext(
            segment_id=segment_id,
            segment_end=seg_node.segment_end,
            tab_id=tab_id,
        )

        # Sort children by pristine_start DESC for backwards walk.
        # Secondary key: original position DESC — when multiple blocks share
        # the same pristine_start (e.g. all additions at the same point),
        # the last block in document order must be emitted first so that
        # earlier inserts push it down to its correct final position.
        sorted_children = [
            child
            for _, child in sorted(
                enumerate(seg_node.children),
                key=lambda pair: (pair[1].pristine_start, pair[0]),
                reverse=True,
            )
        ]

        followed_by_added_table = False
        # Track whether a non-deleted table follows (in document order).
        # In the backwards walk the table is processed BEFORE the content
        # block that precedes it.
        before_structural_element = False

        for child in sorted_children:
            if child.node_type == NodeType.TABLE:
                requests.extend(self._table_gen.emit(child, ctx))
                followed_by_added_table = child.op == ChangeOp.ADDED
                # A non-deleted table means the preceding content block's
                # trailing \n is the "newline before a table" that the API
                # forbids deleting.
                before_structural_element = child.op != ChangeOp.DELETED

            elif child.node_type == NodeType.CONTENT_BLOCK:
                # Handle DELETED footnote child changes (the content generator
                # handles ADDED footnotes inline via createFootnote at the
                # correct position within the content block).
                for fn_child in child.children:
                    if (
                        fn_child.node_type == NodeType.SEGMENT
                        and fn_child.segment_type == SegmentType.FOOTNOTE
                        and fn_child.op == ChangeOp.DELETED
                    ):
                        content_xml = child.before_xml
                        base_index = (
                            child.pristine_start
                            if child.pristine_start > 0
                            else (1 if segment_id is None else 0)
                        )
                        requests.extend(
                            self._structural_gen.emit_footnote(
                                fn_child,
                                content_xml,
                                base_index,
                                tab_id=tab_id,
                            )
                        )

                ctx.followed_by_added_table = followed_by_added_table
                ctx.before_structural_element = (
                    before_structural_element or child.before_structural_element
                )
                reqs, consumed = self._content_gen.emit(child, ctx)
                requests.extend(reqs)
                if consumed:
                    ctx.segment_end_consumed = True
                followed_by_added_table = False
                before_structural_element = False

        return requests

    def _resolve_segment_id(self, seg_node: ChangeNode) -> str | None:
        """Resolve the segment_id for requests.

        Returns None for body, or the segment ID for headers/footers/footnotes.
        """
        if seg_node.segment_type == SegmentType.BODY:
            return None
        return seg_node.segment_id
