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

        for seg_node in root.children:
            if seg_node.node_type != NodeType.SEGMENT:
                continue

            # Handle segment-level structural changes (add/delete)
            if seg_node.op in (ChangeOp.ADDED, ChangeOp.DELETED):
                if seg_node.segment_type in (SegmentType.HEADER, SegmentType.FOOTER):
                    requests.extend(self._structural_gen.emit_header_footer(seg_node))
                elif seg_node.segment_type == SegmentType.FOOTNOTE:
                    requests.extend(self._structural_gen.emit_footnote(seg_node))
                continue

            # For MODIFIED segments, walk children backwards
            requests.extend(self._walk_segment(seg_node))

        return requests

    def _walk_segment(self, seg_node: ChangeNode) -> list[dict[str, Any]]:
        """Walk a single segment's children from highest to lowest pristine_start."""
        requests: list[dict[str, Any]] = []

        segment_id = self._resolve_segment_id(seg_node)
        ctx = SegmentContext(
            segment_id=segment_id,
            segment_end=seg_node.segment_end,
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

        for child in sorted_children:
            if child.node_type == NodeType.TABLE:
                requests.extend(self._table_gen.emit(child, ctx))
                followed_by_added_table = child.op == ChangeOp.ADDED

            elif child.node_type == NodeType.CONTENT_BLOCK:
                # Handle footnote child changes first
                for fn_child in child.children:
                    if (
                        fn_child.node_type == NodeType.SEGMENT
                        and fn_child.segment_type == SegmentType.FOOTNOTE
                    ):
                        content_xml = (
                            child.after_xml
                            if fn_child.op == ChangeOp.ADDED
                            else child.before_xml
                        )
                        base_index = (
                            child.pristine_start
                            if child.pristine_start > 0
                            else (1 if segment_id is None else 0)
                        )
                        requests.extend(
                            self._structural_gen.emit_footnote(
                                fn_child, content_xml, base_index
                            )
                        )

                ctx.followed_by_added_table = followed_by_added_table
                reqs, consumed = self._content_gen.emit(child, ctx)
                requests.extend(reqs)
                if consumed:
                    ctx.segment_end_consumed = True
                followed_by_added_table = False

        return requests

    def _resolve_segment_id(self, seg_node: ChangeNode) -> str | None:
        """Resolve the segment_id for requests.

        Returns None for body, or the segment ID for headers/footers/footnotes.
        """
        if seg_node.segment_type == SegmentType.BODY:
            return None
        return seg_node.segment_id
