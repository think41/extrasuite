"""Top-level orchestrator for ExtraDoc v2 diff pipeline.

Pipeline:
1. Parse both XMLs → DocumentBlock
2. Compute indexes on pristine tree
3. Diff → ChangeNode tree
4. Walk → request list
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING, Any

from .aligner import BlockAligner
from .block_indexer import BlockIndexer
from .differ import TreeDiffer
from .generators.content import ContentGenerator
from .generators.structural import StructuralGenerator
from .generators.table import TableGenerator
from .parser import BlockParser
from .walker import RequestWalker

if TYPE_CHECKING:
    from .types import ChangeNode


class DiffEngine:
    """Orchestrates the v2 diff pipeline."""

    def diff(
        self,
        pristine_xml: str,
        current_xml: str,
        pristine_styles: str | None = None,  # noqa: ARG002
        current_styles: str | None = None,
    ) -> tuple[list[dict[str, Any]], ChangeNode]:
        """Diff two documents and return (requests, change_tree).

        Args:
            pristine_xml: The pristine document.xml content
            current_xml: The current document.xml content
            pristine_styles: Optional pristine styles.xml
            current_styles: Optional current styles.xml

        Returns:
            Tuple of (batchUpdate requests, change tree root node)
        """
        # 1. Parse
        parser = BlockParser()
        pristine_doc = parser.parse(pristine_xml)
        current_doc = parser.parse(current_xml)

        # 2. Index pristine
        indexer = BlockIndexer()
        indexer.compute(pristine_doc)

        # 3. Diff
        aligner = BlockAligner()
        differ = TreeDiffer(aligner)
        change_tree = differ.diff(pristine_doc, current_doc)

        # 4. Walk
        # Parse style definitions for request generation
        style_defs = _parse_text_styles(current_styles)
        content_gen = ContentGenerator(style_defs=style_defs)
        table_gen = TableGenerator(content_gen)
        structural_gen = StructuralGenerator()
        walker = RequestWalker(content_gen, table_gen, structural_gen)
        requests = walker.walk(change_tree)

        return requests, change_tree


def _parse_text_styles(styles_xml: str | None) -> dict[str, dict[str, str]] | None:
    """Parse text styles from styles.xml."""
    if not styles_xml:
        return None

    try:
        root = ET.fromstring(styles_xml)
    except ET.ParseError:
        return None

    text_styles: dict[str, dict[str, str]] = {}
    for style_elem in root.findall("style"):
        style_id = style_elem.get("id", "")
        if style_id.startswith("cell-"):
            continue
        props = {k: v for k, v in style_elem.attrib.items() if k != "id"}
        if props:
            text_styles[style_id] = props

    return text_styles if text_styles else None
