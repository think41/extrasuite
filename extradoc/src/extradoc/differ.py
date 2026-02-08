"""Build change tree from two DocumentBlock trees.

The TreeDiffer compares pristine and current document trees, producing
a ChangeNode tree that captures all differences. Unlike v1's flat
list[BlockChange], the v2 change tree preserves hierarchy:
DOCUMENT → SEGMENT → CONTENT_BLOCK/TABLE → TABLE_ROW → TABLE_CELL
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from .aligner import BlockAligner
from .types import (
    AlignedPair,
    ChangeNode,
    ChangeOp,
    DocumentBlock,
    NodeType,
    ParagraphBlock,
    SegmentBlock,
    SegmentType,
    StructuralBlock,
    TabBlock,
    TableBlock,
    TableRowBlock,
)


class TreeDiffer:
    """Builds a ChangeNode tree from pristine and current DocumentBlocks."""

    def __init__(self, aligner: BlockAligner | None = None) -> None:
        self._aligner = aligner or BlockAligner()

    def diff(self, pristine: DocumentBlock, current: DocumentBlock) -> ChangeNode:
        """Diff two document trees and return a change tree.

        Returns a DOCUMENT-level ChangeNode whose children are TAB nodes.
        Each TAB node has SEGMENT children. Only tabs/segments/blocks with
        changes produce nodes.
        """
        root = ChangeNode(
            node_type=NodeType.DOCUMENT,
            op=ChangeOp.UNCHANGED,
            node_id=pristine.doc_id,
        )

        tab_pairs = self._match_tabs(pristine, current)
        for p_tab, c_tab in tab_pairs:
            if p_tab is None and c_tab is not None:
                # Tab added
                root.children.append(
                    ChangeNode(
                        node_type=NodeType.TAB,
                        op=ChangeOp.ADDED,
                        node_id=c_tab.tab_id,
                        tab_id=c_tab.tab_id,
                        after_xml=c_tab.xml,
                    )
                )
            elif p_tab is not None and c_tab is None:
                # Tab deleted
                root.children.append(
                    ChangeNode(
                        node_type=NodeType.TAB,
                        op=ChangeOp.DELETED,
                        node_id=p_tab.tab_id,
                        tab_id=p_tab.tab_id,
                        before_xml=p_tab.xml,
                    )
                )
            elif p_tab is not None and c_tab is not None:
                tab_node = self._diff_tab(p_tab, c_tab)
                if tab_node is not None:
                    root.children.append(tab_node)

        return root

    def _match_tabs(
        self,
        pristine: DocumentBlock,
        current: DocumentBlock,
    ) -> list[tuple[TabBlock | None, TabBlock | None]]:
        """Match tabs by tab_id."""
        p_map = {t.tab_id: t for t in pristine.tabs}
        c_map = {t.tab_id: t for t in current.tabs}

        all_keys = list(
            dict.fromkeys(
                [t.tab_id for t in pristine.tabs] + [t.tab_id for t in current.tabs]
            )
        )
        pairs: list[tuple[TabBlock | None, TabBlock | None]] = []
        for key in all_keys:
            pairs.append((p_map.get(key), c_map.get(key)))
        return pairs

    def _diff_tab(self, p_tab: TabBlock, c_tab: TabBlock) -> ChangeNode | None:
        """Diff a matched pair of tabs. Returns None if no changes."""
        children: list[ChangeNode] = []

        segment_pairs = self._match_segments(p_tab, c_tab)
        for p_seg, c_seg in segment_pairs:
            if p_seg is None and c_seg is not None:
                children.append(
                    ChangeNode(
                        node_type=NodeType.SEGMENT,
                        op=ChangeOp.ADDED,
                        node_id=c_seg.segment_id,
                        segment_type=c_seg.segment_type,
                        segment_id=c_seg.segment_id,
                        after_xml=self._segment_xml(c_seg),
                    )
                )
            elif p_seg is not None and c_seg is None:
                children.append(
                    ChangeNode(
                        node_type=NodeType.SEGMENT,
                        op=ChangeOp.DELETED,
                        node_id=p_seg.segment_id,
                        segment_type=p_seg.segment_type,
                        segment_id=p_seg.segment_id,
                        before_xml=self._segment_xml(p_seg),
                    )
                )
            elif p_seg is not None and c_seg is not None:
                seg_node = self._diff_segment(p_seg, c_seg)
                if seg_node is not None:
                    children.append(seg_node)

        if not children:
            return None

        return ChangeNode(
            node_type=NodeType.TAB,
            op=ChangeOp.MODIFIED,
            node_id=p_tab.tab_id,
            tab_id=p_tab.tab_id,
            children=children,
        )

    def _segment_xml(self, seg: SegmentBlock) -> str:
        """Build a minimal XML representation for a segment (for structural changes)."""
        # For add/delete of entire segments we just need the type and id
        return f'<{seg.segment_type.value} id="{seg.segment_id}"/>'

    def _match_segments(
        self,
        pristine: TabBlock,
        current: TabBlock,
    ) -> list[tuple[SegmentBlock | None, SegmentBlock | None]]:
        """Match segments by (type, id).

        For headers/footers, match by type only (there's typically one default).
        """

        def seg_key(seg: SegmentBlock) -> tuple[str, str]:
            if seg.segment_type in (SegmentType.HEADER, SegmentType.FOOTER):
                return (seg.segment_type.value, "")
            return (seg.segment_type.value, seg.segment_id)

        p_map = {seg_key(s): s for s in pristine.segments}
        c_map = {seg_key(s): s for s in current.segments}

        all_keys = set(p_map.keys()) | set(c_map.keys())
        pairs: list[tuple[SegmentBlock | None, SegmentBlock | None]] = []
        for key in sorted(all_keys):
            pairs.append((p_map.get(key), c_map.get(key)))
        return pairs

    def _diff_segment(
        self, p_seg: SegmentBlock, c_seg: SegmentBlock
    ) -> ChangeNode | None:
        """Diff a matched pair of segments. Returns None if no changes."""
        children = self._diff_structural_elements(
            p_seg.children,
            c_seg.children,
            p_seg.start_index,
            p_seg.end_index,
        )

        if not children:
            return None

        return ChangeNode(
            node_type=NodeType.SEGMENT,
            op=ChangeOp.MODIFIED,
            node_id=p_seg.segment_id,
            segment_type=p_seg.segment_type,
            segment_id=p_seg.segment_id,
            segment_end=p_seg.end_index,
            children=children,
        )

    def _diff_structural_elements(
        self,
        p_children: list[StructuralBlock],
        c_children: list[StructuralBlock],
        seg_start: int,
        seg_end: int,
    ) -> list[ChangeNode]:
        """Align and classify structural elements, group into change nodes."""
        alignment = self._aligner.align(p_children, c_children)

        # Build raw change list: (op, pristine_block, current_block, current_idx)
        raw: list[
            tuple[
                ChangeOp | None,
                StructuralBlock | None,
                StructuralBlock | None,
                int | None,
            ]
        ] = []

        for pair in alignment:
            p_idx, c_idx = pair.pristine_idx, pair.current_idx

            if p_idx is None and c_idx is not None:
                raw.append((ChangeOp.ADDED, None, c_children[c_idx], c_idx))
            elif p_idx is not None and c_idx is None:
                raw.append((ChangeOp.DELETED, p_children[p_idx], None, None))
            elif p_idx is not None and c_idx is not None:
                p_block = p_children[p_idx]
                c_block = c_children[c_idx]
                if p_block.content_hash() != c_block.content_hash():
                    raw.append((ChangeOp.MODIFIED, p_block, c_block, c_idx))
                else:
                    # Unchanged — acts as separator
                    raw.append((None, p_block, c_block, c_idx))

        return self._group_into_change_nodes(raw, seg_start, seg_end)

    def _group_into_change_nodes(
        self,
        raw: list[
            tuple[
                ChangeOp | None,
                StructuralBlock | None,
                StructuralBlock | None,
                int | None,
            ]
        ],
        seg_start: int,
        _seg_end: int,
    ) -> list[ChangeNode]:
        """Group consecutive same-op paragraphs into CONTENT_BLOCK nodes.

        Non-paragraph changes (tables) are emitted individually.
        Unchanged paragraphs update the pristine tracker but produce no node.
        """
        nodes: list[ChangeNode] = []
        # Current group of consecutive same-op same-tag paragraphs
        group: list[tuple[ChangeOp, ParagraphBlock | None, ParagraphBlock | None]] = []
        group_op: ChangeOp | None = None
        last_current_idx: int | None = None
        last_pristine_end = seg_start
        # Set to True before flush_group() when the trigger element is a
        # non-deleted table (i.e. the content block being flushed is
        # immediately followed by a structural element in document order).
        flush_before_structural = False

        def flush_group() -> None:
            nonlocal group, group_op, last_current_idx, last_pristine_end
            nonlocal flush_before_structural
            if not group:
                flush_before_structural = False
                return
            assert group_op is not None

            before_parts: list[str] = []
            after_parts: list[str] = []
            p_start = 0
            p_end = 0

            for _op, p_blk, c_blk in group:
                if p_blk and p_blk.xml:
                    before_parts.append(p_blk.xml)
                    if p_start == 0:
                        p_start = p_blk.start_index
                    p_end = p_blk.end_index
                    last_pristine_end = p_blk.end_index
                if c_blk and c_blk.xml:
                    after_parts.append(c_blk.xml)

            # For ADDED blocks with no pristine reference
            if p_start == 0 and group_op == ChangeOp.ADDED:
                p_start = last_pristine_end
                p_end = last_pristine_end

            # Collect footnote changes
            footnote_children = self._collect_footnote_changes(group)

            node = ChangeNode(
                node_type=NodeType.CONTENT_BLOCK,
                op=group_op,
                before_xml="\n".join(before_parts) if before_parts else None,
                after_xml="\n".join(after_parts) if after_parts else None,
                pristine_start=p_start,
                pristine_end=p_end,
                children=footnote_children,
                before_structural_element=flush_before_structural,
            )
            nodes.append(node)

            group = []
            group_op = None
            last_current_idx = None
            flush_before_structural = False

        # Suppress deletion of structural separators before tables
        for i in range(len(raw)):
            op_i, p_block_i, _, _ = raw[i]
            if (
                op_i == ChangeOp.DELETED
                and isinstance(p_block_i, ParagraphBlock)
                and _is_empty_paragraph(p_block_i)
                and i + 1 < len(raw)
                and isinstance(raw[i + 1][1] or raw[i + 1][2], TableBlock)
                and raw[i + 1][0] != ChangeOp.DELETED
            ):
                raw[i] = (None, p_block_i, None, None)

        for op, p_block, c_block, current_idx in raw:
            # Unchanged → flush and track position
            if op is None:
                # If the unchanged element is a table, the preceding content
                # block's trailing \n is the newline-before-table that the
                # Google Docs API forbids deleting.
                if group and isinstance(p_block or c_block, TableBlock):
                    flush_before_structural = True
                flush_group()
                if p_block is not None and p_block.end_index > 0:
                    last_pristine_end = p_block.end_index
                continue

            block = c_block if c_block is not None else p_block
            assert block is not None
            is_paragraph = isinstance(block, ParagraphBlock)

            if is_paragraph:
                assert isinstance(block, ParagraphBlock)
                p_para = p_block if isinstance(p_block, ParagraphBlock) else None
                c_para = c_block if isinstance(c_block, ParagraphBlock) else None

                # Check adjacency and same tag for grouping
                is_adjacent = (
                    last_current_idx is None
                    or current_idx is None
                    or current_idx == last_current_idx + 1
                )
                current_tag = block.tag
                last_tag = None
                if group:
                    last_blk = group[-1][2] or group[-1][1]
                    if last_blk:
                        last_tag = last_blk.tag
                same_type = last_tag is None or current_tag == last_tag

                if group_op == op and is_adjacent and same_type:
                    group.append((op, p_para, c_para))
                    if current_idx is not None:
                        last_current_idx = current_idx
                else:
                    flush_group()
                    group = [(op, p_para, c_para)]
                    group_op = op
                    last_current_idx = current_idx
            else:
                # Non-paragraph (table)
                if group and op != ChangeOp.DELETED:
                    flush_before_structural = True
                flush_group()

                if op == ChangeOp.ADDED:
                    assert isinstance(c_block, TableBlock)
                    nodes.append(
                        ChangeNode(
                            node_type=NodeType.TABLE,
                            op=ChangeOp.ADDED,
                            after_xml=c_block.xml,
                            pristine_start=last_pristine_end,
                            pristine_end=last_pristine_end,
                            table_start=last_pristine_end,
                        )
                    )
                elif op == ChangeOp.DELETED:
                    assert isinstance(p_block, TableBlock)
                    nodes.append(
                        ChangeNode(
                            node_type=NodeType.TABLE,
                            op=ChangeOp.DELETED,
                            before_xml=p_block.xml,
                            pristine_start=p_block.start_index,
                            pristine_end=p_block.end_index,
                            table_start=p_block.start_index,
                        )
                    )
                    last_pristine_end = p_block.end_index
                elif op == ChangeOp.MODIFIED:
                    assert isinstance(p_block, TableBlock)
                    assert isinstance(c_block, TableBlock)
                    table_node = self._diff_table(p_block, c_block)
                    if table_node is not None:
                        nodes.append(table_node)
                    last_pristine_end = p_block.end_index

        flush_group()
        return nodes

    def _collect_footnote_changes(
        self,
        group: list[tuple[ChangeOp, ParagraphBlock | None, ParagraphBlock | None]],
    ) -> list[ChangeNode]:
        """Detect added/deleted/modified footnotes within a paragraph group."""
        p_footnotes: dict[str, str] = {}
        c_footnotes: dict[str, str] = {}

        for _op, p_blk, c_blk in group:
            if p_blk:
                for fn in p_blk.footnotes:
                    p_footnotes[fn.footnote_id] = fn.xml
            if c_blk:
                for fn in c_blk.footnotes:
                    c_footnotes[fn.footnote_id] = fn.xml

        children: list[ChangeNode] = []

        # Added footnotes
        for fn_id, fn_xml in c_footnotes.items():
            if fn_id not in p_footnotes:
                children.append(
                    ChangeNode(
                        node_type=NodeType.SEGMENT,
                        op=ChangeOp.ADDED,
                        node_id=fn_id,
                        segment_type=SegmentType.FOOTNOTE,
                        segment_id=fn_id,
                        after_xml=fn_xml,
                    )
                )

        # Deleted footnotes
        for fn_id, fn_xml in p_footnotes.items():
            if fn_id not in c_footnotes:
                children.append(
                    ChangeNode(
                        node_type=NodeType.SEGMENT,
                        op=ChangeOp.DELETED,
                        node_id=fn_id,
                        segment_type=SegmentType.FOOTNOTE,
                        segment_id=fn_id,
                        before_xml=fn_xml,
                    )
                )

        # Modified footnotes
        for fn_id in p_footnotes.keys() & c_footnotes.keys():
            if p_footnotes[fn_id] != c_footnotes[fn_id]:
                children.append(
                    ChangeNode(
                        node_type=NodeType.SEGMENT,
                        op=ChangeOp.MODIFIED,
                        node_id=fn_id,
                        segment_type=SegmentType.FOOTNOTE,
                        segment_id=fn_id,
                        before_xml=p_footnotes[fn_id],
                        after_xml=c_footnotes[fn_id],
                    )
                )

        return children

    def _diff_table(self, p: TableBlock, c: TableBlock) -> ChangeNode | None:
        """Diff two matched tables, producing a TABLE node with sub-changes."""
        children: list[ChangeNode] = []

        # Column diff
        col_children, col_alignment = self._diff_columns(p, c)
        children.extend(col_children)

        # Row diff
        row_children = self._diff_rows(p, c, col_alignment)
        children.extend(row_children)

        # Check for column width changes
        has_width_changes = self._has_column_width_changes(p, c)

        if not children and not has_width_changes:
            return None

        return ChangeNode(
            node_type=NodeType.TABLE,
            op=ChangeOp.MODIFIED,
            before_xml=p.xml,
            after_xml=c.xml,
            pristine_start=p.start_index,
            pristine_end=p.end_index,
            table_start=p.start_index,
            children=children,
        )

    def _has_column_width_changes(self, p: TableBlock, c: TableBlock) -> bool:
        """Check if column widths changed between pristine and current."""
        p_widths = {col.col_id: col.width for col in p.columns}
        c_widths = {col.col_id: col.width for col in c.columns}
        return p_widths != c_widths

    def _diff_columns(
        self, p: TableBlock, c: TableBlock
    ) -> tuple[list[ChangeNode], list[AlignedPair]]:
        """Diff columns by col_id. Returns (changes, alignment)."""
        changes: list[ChangeNode] = []

        p_ids = [col.col_id for col in p.columns]
        c_ids = [col.col_id for col in c.columns]

        # Match by ID
        p_id_to_idx: dict[str, int] = {}
        for i, cid in enumerate(p_ids):
            if cid not in p_id_to_idx:
                p_id_to_idx[cid] = i

        matched_p: set[int] = set()
        alignment: list[AlignedPair] = []

        for c_i, cid in enumerate(c_ids):
            p_i = p_id_to_idx.get(cid)
            if p_i is not None and p_i not in matched_p:
                alignment.append(AlignedPair(p_i, c_i))
                matched_p.add(p_i)
            else:
                alignment.append(AlignedPair(None, c_i))

        # Pristine columns not matched are deleted
        for p_i in range(len(p_ids)):
            if p_i not in matched_p:
                alignment.append(AlignedPair(p_i, None))

        # Build change nodes
        for pair in alignment:
            if pair.pristine_idx is None and pair.current_idx is not None:
                changes.append(
                    ChangeNode(
                        node_type=NodeType.TABLE_COLUMN,
                        op=ChangeOp.ADDED,
                        col_index=pair.current_idx,
                    )
                )
            elif pair.pristine_idx is not None and pair.current_idx is None:
                changes.append(
                    ChangeNode(
                        node_type=NodeType.TABLE_COLUMN,
                        op=ChangeOp.DELETED,
                        col_index=pair.pristine_idx,
                    )
                )

        return changes, alignment

    def _diff_rows(
        self,
        p: TableBlock,
        c: TableBlock,
        col_alignment: list[AlignedPair],
    ) -> list[ChangeNode]:
        """Diff rows using ID-based alignment."""
        changes: list[ChangeNode] = []
        row_alignment = self._aligner.align_table_rows(p.rows, c.rows)

        last_pristine_end = p.start_index + 1

        for pair in row_alignment:
            p_idx, c_idx = pair.pristine_idx, pair.current_idx
            p_row = p.rows[p_idx] if p_idx is not None else None
            c_row = c.rows[c_idx] if c_idx is not None else None

            row_idx = (
                c_idx if c_idx is not None else (p_idx if p_idx is not None else 0)
            )

            if p_row is None and c_row is not None:
                changes.append(
                    ChangeNode(
                        node_type=NodeType.TABLE_ROW,
                        op=ChangeOp.ADDED,
                        node_id=c_row.row_id,
                        row_index=row_idx,
                        after_xml=c_row.xml,
                        pristine_start=last_pristine_end,
                        pristine_end=last_pristine_end,
                    )
                )
            elif p_row is not None and c_row is None:
                changes.append(
                    ChangeNode(
                        node_type=NodeType.TABLE_ROW,
                        op=ChangeOp.DELETED,
                        node_id=p_row.row_id,
                        row_index=row_idx,
                        before_xml=p_row.xml,
                        pristine_start=p_row.start_index,
                        pristine_end=p_row.end_index,
                    )
                )
            elif p_row is not None and c_row is not None:
                cell_children = self._diff_cells(p_row, c_row, col_alignment)
                id_differs = p_row.row_id != c_row.row_id
                content_differs = p_row.xml != c_row.xml

                if id_differs or content_differs or cell_children:
                    changes.append(
                        ChangeNode(
                            node_type=NodeType.TABLE_ROW,
                            op=ChangeOp.MODIFIED,
                            node_id=p_row.row_id,
                            row_index=row_idx,
                            before_xml=p_row.xml,
                            after_xml=c_row.xml,
                            pristine_start=p_row.start_index,
                            pristine_end=p_row.end_index,
                            children=cell_children,
                        )
                    )

            if p_row is not None:
                last_pristine_end = p_row.end_index

        return changes

    def _diff_cells(
        self,
        p_row: TableRowBlock,
        c_row: TableRowBlock,
        col_alignment: list[AlignedPair],
    ) -> list[ChangeNode]:
        """Diff cells within a row using column alignment."""
        changes: list[ChangeNode] = []

        p_cells = p_row.cells
        c_cells = c_row.cells

        # If no column alignment, use positional matching
        if not col_alignment:
            max_cells = max(len(p_cells), len(c_cells))
            col_alignment = [
                AlignedPair(
                    i if i < len(p_cells) else None,
                    i if i < len(c_cells) else None,
                )
                for i in range(max_cells)
            ]

        # Build sets of added/deleted columns
        cols_added = {
            pair.current_idx
            for pair in col_alignment
            if pair.pristine_idx is None and pair.current_idx is not None
        }
        cols_deleted = {
            pair.pristine_idx
            for pair in col_alignment
            if pair.pristine_idx is not None and pair.current_idx is None
        }

        for pair in col_alignment:
            p_idx, c_idx = pair.pristine_idx, pair.current_idx
            p_cell = (
                p_cells[p_idx] if p_idx is not None and p_idx < len(p_cells) else None
            )
            c_cell = (
                c_cells[c_idx] if c_idx is not None and c_idx < len(c_cells) else None
            )
            col_idx = (
                c_idx if c_idx is not None else (p_idx if p_idx is not None else 0)
            )

            # Skip structurally added/deleted columns
            if col_idx in cols_added or col_idx in cols_deleted:
                continue

            if p_cell is None and c_cell is not None:
                changes.append(
                    ChangeNode(
                        node_type=NodeType.TABLE_CELL,
                        op=ChangeOp.ADDED,
                        node_id=c_cell.cell_id,
                        col_index=col_idx,
                        after_xml=c_cell.xml,
                        pristine_start=p_row.end_index,
                        pristine_end=p_row.end_index,
                    )
                )
            elif p_cell is not None and c_cell is None:
                changes.append(
                    ChangeNode(
                        node_type=NodeType.TABLE_CELL,
                        op=ChangeOp.DELETED,
                        node_id=p_cell.cell_id,
                        col_index=col_idx,
                        before_xml=p_cell.xml,
                        pristine_start=p_cell.start_index,
                        pristine_end=p_cell.end_index,
                    )
                )
            elif (
                p_cell is not None
                and c_cell is not None
                and p_cell.xml.strip() != c_cell.xml.strip()
            ):
                changes.append(
                    ChangeNode(
                        node_type=NodeType.TABLE_CELL,
                        op=ChangeOp.MODIFIED,
                        node_id=p_cell.cell_id,
                        col_index=col_idx,
                        before_xml=p_cell.xml,
                        after_xml=c_cell.xml,
                        pristine_start=p_cell.start_index,
                        pristine_end=p_cell.end_index,
                    )
                )

        return changes


def _is_empty_paragraph(block: ParagraphBlock) -> bool:
    """Check if paragraph is empty (structural separator)."""
    try:
        elem = ET.fromstring(block.xml)
        text = (elem.text or "") + "".join(
            (c.text or "") + (c.tail or "") for c in elem
        )
        return not text.strip()
    except ET.ParseError:
        return False
