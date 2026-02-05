"""Block-level diff detection for ExtraDoc XML.

Detects structural changes at the block level:
- Treats consecutive paragraphs as a single "ContentBlock"
- Treats Table, TableOfContents, SectionBreak as individual nodes
- Recursively handles table cells, headers, footers, footnotes
- Returns changes with before/after XML content

The tree structure follows Google Docs' concept hierarchy:
Document -> Tabs/Body/Headers/Footers/Footnotes -> StructuralElements

StructuralElements include:
- Paragraph
- Table (with recursive TableCell content)
- SectionBreak
- TableOfContents

Consecutive Paragraphs are grouped into ContentBlock for diffing purposes,
since text content can be manipulated as a single unit.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class BlockType(Enum):
    """Types of block-level nodes in the document tree."""

    # Composite node: consecutive sequence of paragraphs (used in changes)
    CONTENT_BLOCK = "content_block"

    # Individual paragraph (used during parsing/diffing)
    PARAGRAPH = "paragraph"

    # Individual structural elements (not grouped)
    TABLE = "table"
    TABLE_OF_CONTENTS = "toc"
    SECTION_BREAK = "section_break"

    # Container nodes (for recursive processing)
    DOCUMENT = "document"
    BODY = "body"
    TAB = "tab"
    HEADER = "header"
    FOOTER = "footer"
    FOOTNOTE = "footnote"
    TABLE_CELL = "table_cell"


class ChangeType(Enum):
    """Types of changes detected."""

    ADDED = "added"
    DELETED = "deleted"
    MODIFIED = "modified"


@dataclass
class Block:
    """A block-level node in the document tree.

    Attributes:
        block_type: The type of this block
        block_id: Unique identifier for matching (e.g., header id, footnote id)
        xml_content: The raw XML content of this block
        children: Child blocks (for containers like body, table cells)
        attributes: Additional attributes (e.g., table rows/cols)
        start_index: Starting character index in parent (for ordering)
    """

    block_type: BlockType
    block_id: str = ""
    xml_content: str = ""
    children: list[Block] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)
    start_index: int = 0

    def content_hash(self) -> str:
        """Generate a hash of the content for quick comparison."""
        # Use XML content for comparison
        return self.xml_content

    def structural_key(self) -> str:
        """Generate a key for structural matching (ignores content variations)."""
        if self.block_type == BlockType.TABLE:
            rows = self.attributes.get("rows", 0)
            cols = self.attributes.get("cols", 0)
            return f"TABLE:{rows}x{cols}"
        elif self.block_type == BlockType.CONTENT_BLOCK:
            # For content blocks, use a simple indicator
            return "CONTENT_BLOCK"
        elif self.block_type == BlockType.PARAGRAPH:
            # For paragraphs, include the tag type (p, h1, li, etc.)
            tag = self.attributes.get("tag", "p")
            return f"PARAGRAPH:{tag}"
        elif self.block_type == BlockType.TABLE_OF_CONTENTS:
            return "TOC"
        elif self.block_type == BlockType.SECTION_BREAK:
            return "SECTION_BREAK"
        else:
            return f"{self.block_type.value}:{self.block_id}"


@dataclass
class BlockChange:
    """Represents a detected change between two document versions.

    Attributes:
        change_type: Whether the block was added, deleted, or modified
        block_type: Type of the affected block
        block_id: Identifier for the block (if applicable)
        before_xml: XML content before the change (None for additions)
        after_xml: XML content after the change (None for deletions)
        container_path: Path to the container (e.g., ["body"], ["table_cell", "0,1"])
        child_changes: For modified containers, changes to children
    """

    change_type: ChangeType
    block_type: BlockType
    block_id: str = ""
    before_xml: str | None = None
    after_xml: str | None = None
    container_path: list[str] = field(default_factory=list)
    child_changes: list[BlockChange] = field(default_factory=list)

    def __repr__(self) -> str:
        path_str = "/".join(self.container_path) if self.container_path else "root"
        return f"BlockChange({self.change_type.value}, {self.block_type.value}, path={path_str})"


class BlockDiffDetector:
    """Detects block-level changes between two XML documents.

    Usage:
        detector = BlockDiffDetector()
        changes = detector.diff(pristine_xml, current_xml)

        for change in changes:
            print(f"{change.change_type}: {change.block_type}")
            if change.before_xml:
                print(f"  Before: {change.before_xml[:50]}...")
            if change.after_xml:
                print(f"  After: {change.after_xml[:50]}...")
    """

    def diff(
        self,
        pristine_xml: str,
        current_xml: str,
        pristine_styles: str | None = None,  # noqa: ARG002
        current_styles: str | None = None,  # noqa: ARG002
    ) -> list[BlockChange]:
        """Compare two XML documents and return block-level changes.

        Args:
            pristine_xml: The original document XML
            current_xml: The modified document XML
            pristine_styles: Optional styles.xml for pristine (reserved for future use)
            current_styles: Optional styles.xml for current (reserved for future use)

        Returns:
            List of BlockChange objects describing the differences
        """
        pristine_tree = self._parse_to_block_tree(pristine_xml)
        current_tree = self._parse_to_block_tree(current_xml)

        return self._diff_blocks(pristine_tree, current_tree, [])

    def _parse_to_block_tree(self, xml_content: str) -> Block:
        """Parse XML content into a block tree structure."""
        root = ET.fromstring(xml_content)

        doc_block = Block(
            block_type=BlockType.DOCUMENT,
            block_id=root.get("id", ""),
            attributes={"revision": root.get("revision", "")},
        )

        # Process body
        body = root.find("body")
        if body is not None:
            body_block = self._parse_container(body, BlockType.BODY, "body")
            doc_block.children.append(body_block)

        # Process tabs
        for tab in root.findall("tab"):
            tab_id = tab.get("id", "")
            tab_body = tab.find("body")
            if tab_body is not None:
                tab_block = Block(
                    block_type=BlockType.TAB,
                    block_id=tab_id,
                    xml_content=ET.tostring(tab, encoding="unicode"),
                    attributes={"title": tab.get("title", "")},
                )
                # Parse body content within tab
                body_content = self._parse_structural_elements(tab_body)
                tab_block.children = body_content
                doc_block.children.append(tab_block)

        # Process headers
        for header in root.findall("header"):
            header_block = self._parse_container(
                header, BlockType.HEADER, header.get("id", "")
            )
            doc_block.children.append(header_block)

        # Process footers
        for footer in root.findall("footer"):
            footer_block = self._parse_container(
                footer, BlockType.FOOTER, footer.get("id", "")
            )
            doc_block.children.append(footer_block)

        # Process footnotes
        for footnote in root.findall("footnote"):
            footnote_block = self._parse_container(
                footnote, BlockType.FOOTNOTE, footnote.get("id", "")
            )
            doc_block.children.append(footnote_block)

        return doc_block

    def _parse_container(
        self, elem: ET.Element, block_type: BlockType, block_id: str
    ) -> Block:
        """Parse a container element (body, header, footer, footnote)."""
        block = Block(
            block_type=block_type,
            block_id=block_id,
            xml_content=ET.tostring(elem, encoding="unicode"),
            attributes={"class": elem.get("class", "_base")},
        )
        block.children = self._parse_structural_elements(elem)
        return block

    def _parse_structural_elements(self, parent: ET.Element) -> list[Block]:
        """Parse structural elements into individual blocks.

        This is the key method that implements the parsing logic:
        - Each paragraph (p, h1-h6, title, subtitle, li) -> Individual PARAGRAPH block
        - table -> Table block
        - toc -> TableOfContents block
        - Other elements are handled appropriately

        During diffing, consecutive paragraphs with the same change status
        will be grouped into ContentBlock changes.
        """
        blocks: list[Block] = []

        # Tags that represent paragraph-like elements
        paragraph_tags = {
            "p",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "title",
            "subtitle",
            "li",
        }

        def add_paragraph(elem: ET.Element) -> None:
            """Add a single paragraph as its own block."""
            para_block = Block(
                block_type=BlockType.PARAGRAPH,
                xml_content=ET.tostring(elem, encoding="unicode"),
                attributes={"tag": elem.tag},
                start_index=len(blocks),
            )
            blocks.append(para_block)

        for child in parent:
            tag = child.tag

            if tag in paragraph_tags:
                # Each paragraph is its own block
                add_paragraph(child)

            elif tag == "table":
                # Add table as its own block
                table_block = self._parse_table(child)
                blocks.append(table_block)

            elif tag == "toc":
                # TOC is a single block (its internal paragraphs are part of TOC)
                toc_block = Block(
                    block_type=BlockType.TABLE_OF_CONTENTS,
                    xml_content=ET.tostring(child, encoding="unicode"),
                    start_index=len(blocks),
                )
                blocks.append(toc_block)

            elif tag == "style":
                # Style wrapper - process children
                for styled_child in child:
                    if styled_child.tag in paragraph_tags:
                        add_paragraph(styled_child)
                    elif styled_child.tag == "table":
                        table_block = self._parse_table(styled_child)
                        blocks.append(table_block)
                    # Other styled elements treated similarly

            # Note: sectionBreak is usually handled at conversion time,
            # but if present in XML, we'd handle it here

        return blocks

    def _parse_table(self, table_elem: ET.Element) -> Block:
        """Parse a table element into a Block with cell children."""
        rows = int(table_elem.get("rows", "0"))
        cols = int(table_elem.get("cols", "0"))

        table_block = Block(
            block_type=BlockType.TABLE,
            xml_content=ET.tostring(table_elem, encoding="unicode"),
            attributes={"rows": rows, "cols": cols},
        )

        # Parse table cells recursively
        for row_idx, tr in enumerate(table_elem.findall("tr")):
            for col_idx, td in enumerate(tr.findall("td")):
                cell_id = f"{row_idx},{col_idx}"
                cell_block = Block(
                    block_type=BlockType.TABLE_CELL,
                    block_id=cell_id,
                    xml_content=ET.tostring(td, encoding="unicode"),
                    attributes={
                        "row": row_idx,
                        "col": col_idx,
                        "colspan": int(td.get("colspan", "1")),
                        "rowspan": int(td.get("rowspan", "1")),
                    },
                )
                # Recursively parse cell content
                cell_block.children = self._parse_structural_elements(td)
                table_block.children.append(cell_block)

        return table_block

    def _diff_blocks(
        self,
        pristine: Block,
        current: Block,
        path: list[str],
    ) -> list[BlockChange]:
        """Compare two block trees and return changes.

        This implements a tree diff algorithm that:
        1. Matches blocks by structural key and position
        2. Detects additions, deletions, and modifications
        3. Recurses into containers to find nested changes
        """
        changes: list[BlockChange] = []

        # For DOCUMENT, we need to match children (body, headers, etc.) and recurse
        if pristine.block_type == BlockType.DOCUMENT:
            changes.extend(self._diff_document_children(pristine, current, path))
        # For other containers (BODY, HEADER, etc.), compare their structural element children
        elif pristine.block_type in (
            BlockType.BODY,
            BlockType.TAB,
            BlockType.HEADER,
            BlockType.FOOTER,
            BlockType.FOOTNOTE,
        ):
            child_changes = self._diff_child_lists(
                pristine.children,
                current.children,
                [*path, f"{pristine.block_type.value}:{pristine.block_id}"],
            )
            changes.extend(child_changes)

        return changes

    def _diff_document_children(
        self,
        pristine: Block,
        current: Block,
        path: list[str],
    ) -> list[BlockChange]:
        """Diff children of a DOCUMENT block (body, headers, footers, footnotes).

        These children are matched by type and ID, then recursively diffed.
        """
        changes: list[BlockChange] = []

        # Build lookup by (type, id) for pristine children
        def child_key(block: Block) -> tuple[str, str]:
            return (block.block_type.value, block.block_id)

        pristine_map = {child_key(c): c for c in pristine.children}
        current_map = {child_key(c): c for c in current.children}

        all_keys = set(pristine_map.keys()) | set(current_map.keys())

        for key in sorted(all_keys):
            p_child = pristine_map.get(key)
            c_child = current_map.get(key)

            if p_child is None and c_child is not None:
                # Container added (e.g., new header)
                changes.append(
                    BlockChange(
                        change_type=ChangeType.ADDED,
                        block_type=c_child.block_type,
                        block_id=c_child.block_id,
                        after_xml=c_child.xml_content,
                        container_path=path,
                    )
                )
            elif p_child is not None and c_child is None:
                # Container deleted
                changes.append(
                    BlockChange(
                        change_type=ChangeType.DELETED,
                        block_type=p_child.block_type,
                        block_id=p_child.block_id,
                        before_xml=p_child.xml_content,
                        container_path=path,
                    )
                )
            elif p_child is not None and c_child is not None:
                # Both exist - recursively diff
                child_changes = self._diff_blocks(p_child, c_child, path)
                changes.extend(child_changes)

        return changes

    def _diff_child_lists(
        self,
        pristine_children: list[Block],
        current_children: list[Block],
        path: list[str],
    ) -> list[BlockChange]:
        """Diff two lists of child blocks using LCS-based alignment.

        For paragraph-level changes, consecutive paragraphs with the same
        change status are grouped into ContentBlock changes.
        """
        # Use None as a sentinel for UNCHANGED to properly separate groups
        raw_changes: list[tuple[ChangeType | None, Block | None, Block | None]] = []

        # Build alignment using structural keys and content
        alignment = self._align_blocks(pristine_children, current_children)

        for p_idx, c_idx in alignment:
            if p_idx is None and c_idx is not None:
                # Addition
                added_block = current_children[c_idx]
                raw_changes.append((ChangeType.ADDED, None, added_block))

            elif p_idx is not None and c_idx is None:
                # Deletion
                deleted_block = pristine_children[p_idx]
                raw_changes.append((ChangeType.DELETED, deleted_block, None))

            elif p_idx is not None and c_idx is not None:
                # Both exist - compare content
                p_block = pristine_children[p_idx]
                c_block = current_children[c_idx]

                if p_block.xml_content != c_block.xml_content:
                    raw_changes.append((ChangeType.MODIFIED, p_block, c_block))
                else:
                    # Unchanged - use None as change_type to act as separator
                    raw_changes.append((None, p_block, c_block))

        # Group consecutive paragraph changes into ContentBlock changes
        return self._group_paragraph_changes(raw_changes, path)

    def _group_paragraph_changes(
        self,
        raw_changes: list[tuple[ChangeType | None, Block | None, Block | None]],
        path: list[str],
    ) -> list[BlockChange]:
        """Group consecutive paragraph changes into ContentBlock changes.

        Non-paragraph changes (tables, TOC, etc.) are passed through as-is.
        Consecutive paragraphs with the same change status are grouped.
        Unchanged blocks (change_type=None) act as separators between groups.
        """
        if not raw_changes:
            return []

        grouped_changes: list[BlockChange] = []
        current_group: list[tuple[ChangeType, Block | None, Block | None]] = []
        current_group_type: ChangeType | None = None

        def flush_group() -> None:
            """Flush the current group of paragraph changes."""
            nonlocal current_group, current_group_type
            if not current_group:
                return

            # Combine all paragraphs in the group
            before_parts: list[str] = []
            after_parts: list[str] = []
            for _change_type, p_block, c_block in current_group:
                if p_block and p_block.xml_content:
                    before_parts.append(p_block.xml_content)
                if c_block and c_block.xml_content:
                    after_parts.append(c_block.xml_content)

            assert current_group_type is not None
            grouped_changes.append(
                BlockChange(
                    change_type=current_group_type,
                    block_type=BlockType.CONTENT_BLOCK,
                    before_xml="\n".join(before_parts) if before_parts else None,
                    after_xml="\n".join(after_parts) if after_parts else None,
                    container_path=path,
                )
            )

            current_group = []
            current_group_type = None

        for change_type, p_block, c_block in raw_changes:
            # Handle unchanged blocks (None change_type) - they just flush the group
            if change_type is None:
                flush_group()
                continue

            # Determine if this is a paragraph
            block = c_block if c_block else p_block
            assert block is not None
            is_paragraph = block.block_type == BlockType.PARAGRAPH

            if is_paragraph:
                # Check if we can add to current group
                if current_group_type == change_type:
                    current_group.append((change_type, p_block, c_block))
                else:
                    # Flush existing group and start new one
                    flush_group()
                    current_group = [(change_type, p_block, c_block)]
                    current_group_type = change_type
            else:
                # Non-paragraph: flush any pending paragraphs first
                flush_group()

                # Handle non-paragraph changes directly
                if change_type == ChangeType.ADDED:
                    assert c_block is not None
                    grouped_changes.append(
                        BlockChange(
                            change_type=ChangeType.ADDED,
                            block_type=c_block.block_type,
                            block_id=c_block.block_id,
                            after_xml=c_block.xml_content,
                            container_path=path,
                        )
                    )
                elif change_type == ChangeType.DELETED:
                    assert p_block is not None
                    grouped_changes.append(
                        BlockChange(
                            change_type=ChangeType.DELETED,
                            block_type=p_block.block_type,
                            block_id=p_block.block_id,
                            before_xml=p_block.xml_content,
                            container_path=path,
                        )
                    )
                elif change_type == ChangeType.MODIFIED:
                    assert p_block is not None and c_block is not None
                    # For tables, check for cell-level changes
                    if p_block.block_type == BlockType.TABLE:
                        table_changes = self._diff_single_block(p_block, c_block, path)
                        grouped_changes.extend(table_changes)
                    else:
                        grouped_changes.append(
                            BlockChange(
                                change_type=ChangeType.MODIFIED,
                                block_type=p_block.block_type,
                                before_xml=p_block.xml_content,
                                after_xml=c_block.xml_content,
                                container_path=path,
                            )
                        )

        # Flush any remaining paragraphs
        flush_group()

        return grouped_changes

    def _diff_single_block(
        self,
        pristine: Block,
        current: Block,
        path: list[str],
    ) -> list[BlockChange]:
        """Compare a single matched pair of blocks."""
        changes: list[BlockChange] = []

        # Check if content changed
        if pristine.xml_content != current.xml_content:
            # For container types (TABLE), check if it's a structural or content change
            if pristine.block_type == BlockType.TABLE:
                # Compare table structure
                if pristine.attributes.get("rows") != current.attributes.get(
                    "rows"
                ) or pristine.attributes.get("cols") != current.attributes.get("cols"):
                    # Structural change to table
                    changes.append(
                        BlockChange(
                            change_type=ChangeType.MODIFIED,
                            block_type=BlockType.TABLE,
                            before_xml=pristine.xml_content,
                            after_xml=current.xml_content,
                            container_path=path,
                        )
                    )
                else:
                    # Same structure, check cell contents recursively
                    cell_changes = self._diff_table_cells(pristine, current, path)
                    if cell_changes:
                        # Create a modified change with child changes
                        changes.append(
                            BlockChange(
                                change_type=ChangeType.MODIFIED,
                                block_type=BlockType.TABLE,
                                before_xml=pristine.xml_content,
                                after_xml=current.xml_content,
                                container_path=path,
                                child_changes=cell_changes,
                            )
                        )

            elif pristine.block_type in (
                BlockType.CONTENT_BLOCK,
                BlockType.PARAGRAPH,
            ):
                # Content block or paragraph modified
                changes.append(
                    BlockChange(
                        change_type=ChangeType.MODIFIED,
                        block_type=BlockType.CONTENT_BLOCK,
                        before_xml=pristine.xml_content,
                        after_xml=current.xml_content,
                        container_path=path,
                    )
                )

            elif pristine.block_type == BlockType.TABLE_OF_CONTENTS:
                # TOC modified
                changes.append(
                    BlockChange(
                        change_type=ChangeType.MODIFIED,
                        block_type=BlockType.TABLE_OF_CONTENTS,
                        before_xml=pristine.xml_content,
                        after_xml=current.xml_content,
                        container_path=path,
                    )
                )

        return changes

    def _diff_table_cells(
        self,
        pristine_table: Block,
        current_table: Block,
        path: list[str],
    ) -> list[BlockChange]:
        """Diff table cells recursively."""
        changes: list[BlockChange] = []

        # Build cell lookup by position
        pristine_cells = {c.block_id: c for c in pristine_table.children}
        current_cells = {c.block_id: c for c in current_table.children}

        all_cell_ids = set(pristine_cells.keys()) | set(current_cells.keys())

        for cell_id in sorted(all_cell_ids):
            p_cell = pristine_cells.get(cell_id)
            c_cell = current_cells.get(cell_id)

            cell_path = [*path, f"table_cell:{cell_id}"]

            if p_cell is None and c_cell is not None:
                # Cell added
                changes.append(
                    BlockChange(
                        change_type=ChangeType.ADDED,
                        block_type=BlockType.TABLE_CELL,
                        block_id=cell_id,
                        after_xml=c_cell.xml_content,
                        container_path=path,
                    )
                )
            elif p_cell is not None and c_cell is None:
                # Cell deleted
                changes.append(
                    BlockChange(
                        change_type=ChangeType.DELETED,
                        block_type=BlockType.TABLE_CELL,
                        block_id=cell_id,
                        before_xml=p_cell.xml_content,
                        container_path=path,
                    )
                )
            elif (
                p_cell is not None
                and c_cell is not None
                and p_cell.xml_content != c_cell.xml_content
            ):
                # Cell exists in both and content differs - compare recursively
                child_changes = self._diff_child_lists(
                    p_cell.children,
                    c_cell.children,
                    cell_path,
                )

                if child_changes:
                    changes.append(
                        BlockChange(
                            change_type=ChangeType.MODIFIED,
                            block_type=BlockType.TABLE_CELL,
                            block_id=cell_id,
                            before_xml=p_cell.xml_content,
                            after_xml=c_cell.xml_content,
                            container_path=path,
                            child_changes=child_changes,
                        )
                    )
                else:
                    # Content changed but no structural child changes
                    # This happens when the cell has simple paragraph content
                    changes.append(
                        BlockChange(
                            change_type=ChangeType.MODIFIED,
                            block_type=BlockType.TABLE_CELL,
                            block_id=cell_id,
                            before_xml=p_cell.xml_content,
                            after_xml=c_cell.xml_content,
                            container_path=path,
                        )
                    )

        return changes

    def _align_blocks(
        self,
        pristine: list[Block],
        current: list[Block],
    ) -> list[tuple[int | None, int | None]]:
        """Align blocks from pristine and current lists for comparison.

        Returns a list of (pristine_idx, current_idx) tuples where:
        - (None, j) means current[j] was added
        - (i, None) means pristine[i] was deleted
        - (i, j) means pristine[i] matches current[j]

        Uses a combination of:
        1. Exact content matching for identical blocks
        2. Structural key matching for modified blocks
        3. Position-based matching as fallback
        """
        alignment: list[tuple[int | None, int | None]] = []

        # Build lookup by content hash for exact matches
        pristine_by_content: dict[str, list[int]] = {}
        for i, block in enumerate(pristine):
            content = block.content_hash()
            if content not in pristine_by_content:
                pristine_by_content[content] = []
            pristine_by_content[content].append(i)

        # Track which blocks have been matched
        matched_pristine: set[int] = set()
        matched_current: set[int] = set()

        # First pass: exact content matches
        for j, c_block in enumerate(current):
            content = c_block.content_hash()
            if content in pristine_by_content:
                candidates = pristine_by_content[content]
                for i in candidates:
                    if i not in matched_pristine:
                        alignment.append((i, j))
                        matched_pristine.add(i)
                        matched_current.add(j)
                        break

        # Second pass: structural key matching for unmatched blocks
        unmatched_pristine = [
            (i, pristine[i]) for i in range(len(pristine)) if i not in matched_pristine
        ]
        unmatched_current = [
            (j, current[j]) for j in range(len(current)) if j not in matched_current
        ]

        # Group by structural key
        pristine_by_key: dict[str, list[int]] = {}
        for i, block in unmatched_pristine:
            key = block.structural_key()
            if key not in pristine_by_key:
                pristine_by_key[key] = []
            pristine_by_key[key].append(i)

        for j, c_block in unmatched_current:
            key = c_block.structural_key()
            key_candidates = pristine_by_key.get(key)
            if key_candidates:
                i = key_candidates.pop(0)
                alignment.append((i, j))
                matched_pristine.add(i)
                matched_current.add(j)

        # Remaining unmatched are additions/deletions
        for i in range(len(pristine)):
            if i not in matched_pristine:
                alignment.append((i, None))

        for j in range(len(current)):
            if j not in matched_current:
                alignment.append((None, j))

        # Sort alignment by original positions for stable output
        def sort_key(pair: tuple[int | None, int | None]) -> tuple[int, int]:
            p_idx = pair[0] if pair[0] is not None else len(pristine)
            c_idx = pair[1] if pair[1] is not None else len(current)
            return (p_idx, c_idx)

        alignment.sort(key=sort_key)

        return alignment


def diff_documents_block_level(
    pristine_xml: str,
    current_xml: str,
    pristine_styles: str | None = None,
    current_styles: str | None = None,
) -> list[BlockChange]:
    """Convenience function to diff two documents at the block level.

    Args:
        pristine_xml: The original document.xml content
        current_xml: The modified document.xml content
        pristine_styles: Optional styles.xml for pristine
        current_styles: Optional styles.xml for current

    Returns:
        List of BlockChange objects describing block-level differences
    """
    detector = BlockDiffDetector()
    return detector.diff(pristine_xml, current_xml, pristine_styles, current_styles)


def format_changes(changes: list[BlockChange], indent: int = 0) -> str:
    """Format changes as a human-readable string for debugging."""
    lines: list[str] = []
    prefix = "  " * indent

    for change in changes:
        path_str = "/".join(change.container_path) if change.container_path else "root"
        lines.append(
            f"{prefix}{change.change_type.value.upper()}: "
            f"{change.block_type.value} at {path_str}"
        )

        if change.before_xml:
            # Truncate for display
            before_preview = change.before_xml[:100].replace("\n", "\\n")
            if len(change.before_xml) > 100:
                before_preview += "..."
            lines.append(f"{prefix}  before: {before_preview}")

        if change.after_xml:
            after_preview = change.after_xml[:100].replace("\n", "\\n")
            if len(change.after_xml) > 100:
                after_preview += "..."
            lines.append(f"{prefix}  after: {after_preview}")

        if change.child_changes:
            lines.append(f"{prefix}  child changes:")
            lines.append(format_changes(change.child_changes, indent + 2))

    return "\n".join(lines)
