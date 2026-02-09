"""Top-level orchestrator for ExtraDoc v2 diff pipeline.

Pipeline:
0. Validate XML (no embedded newlines)
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
        # 0. Validate
        _validate_no_embedded_newlines(current_xml)

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
        props = {k: v for k, v in style_elem.attrib.items() if k != "id"}
        if props:
            text_styles[style_id] = props

    return text_styles if text_styles else None


# Container/structural tags that only hold child elements.
# Whitespace (including newlines) between children is normal XML indentation.
# Everything NOT in this set is a content element where newlines are forbidden.
_CONTAINER_TAGS = frozenset(
    {
        # Document structure
        "doc",
        "meta",
        "tab",
        "body",
        # Segments (separate index spaces)
        "header",
        "footer",
        "footnote",
        # Table structure
        "table",
        "tr",
        "td",
        "col",
        # Other containers
        "toc",
        "style",
        # styles.xml (validated alongside document.xml)
        "styles",
    }
)


def _validate_no_embedded_newlines(xml_content: str) -> None:
    """Validate that no content element contains embedded newline characters.

    Google Docs API interprets newlines as paragraph separators. Newlines
    inside element text cause corruption (e.g. spurious list items).

    Container tags (doc, tab, body, table, tr, td, header, footer, footnote,
    toc, style, meta, col) naturally have whitespace between child elements
    and are skipped.

    All other tags (p, h1-h6, li, title, subtitle, b, i, u, s, sup, sub,
    span, a, etc.) are content elements where newlines are not allowed.

    Raises:
        ValueError: If an element contains an embedded newline, with the
            tag name and a snippet of the offending text.
    """
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError:
        # Let the parser handle malformed XML later.
        return

    for elem in root.iter():
        tag = elem.tag
        if tag in _CONTAINER_TAGS:
            continue

        # Check .text (content before first child)
        if elem.text and "\n" in elem.text:
            snippet = elem.text[:80].replace("\n", "\\n")
            raise ValueError(
                f"Newline character found inside <{tag}> element: "
                f'"{snippet}"\n'
                f"Each element must be a single line of text. "
                f"To create a new line, close the element and open a new one."
            )

        # Check .tail (content after this element's closing tag,
        # still belonging to the parent)
        if elem.tail and "\n" in elem.tail:
            # tail text belongs to the parent — only flag if parent
            # is also a content tag
            parent_tag = _find_parent_tag(root, elem)
            if parent_tag and parent_tag not in _CONTAINER_TAGS:
                snippet = elem.tail[:80].replace("\n", "\\n")
                raise ValueError(
                    f"Newline character found after </{tag}> inside "
                    f'<{parent_tag}> element: "{snippet}"\n'
                    f"Each element must be a single line of text. "
                    f"To create a new line, close the element and open a new one."
                )


def _find_parent_tag(root: ET.Element, target: ET.Element) -> str | None:
    """Find the parent tag of a target element."""
    for parent in root.iter():
        for child in parent:
            if child is target:
                return parent.tag
    return None
