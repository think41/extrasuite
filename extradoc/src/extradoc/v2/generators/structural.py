"""Structural request generation for ExtraDoc v2.

Handles header/footer/tab/footnote add/delete changes.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any

from ..types import ChangeNode, ChangeOp, SegmentType


class StructuralGenerator:
    """Generates requests for structural changes (headers, footers, tabs, footnotes)."""

    def emit_header_footer(self, node: ChangeNode) -> list[dict[str, Any]]:
        """Handle header/footer add/delete."""
        requests: list[dict[str, Any]] = []

        if node.op == ChangeOp.ADDED:
            if node.segment_type == SegmentType.HEADER:
                requests.append({"createHeader": {"type": "DEFAULT"}})
            elif node.segment_type == SegmentType.FOOTER:
                requests.append({"createFooter": {"type": "DEFAULT"}})

        elif node.op == ChangeOp.DELETED:
            segment_id = node.segment_id or node.node_id
            if node.segment_type == SegmentType.HEADER and segment_id:
                requests.append({"deleteHeader": {"headerId": segment_id}})
            elif node.segment_type == SegmentType.FOOTER and segment_id:
                requests.append({"deleteFooter": {"footerId": segment_id}})

        return requests

    def emit_tab(self, node: ChangeNode) -> list[dict[str, Any]]:
        """Handle document tab add/delete."""
        requests: list[dict[str, Any]] = []

        if node.op == ChangeOp.ADDED:
            tab_properties: dict[str, Any] = {}
            if node.after_xml:
                try:
                    root = ET.fromstring(node.after_xml)
                    title = root.get("title")
                    if title:
                        tab_properties["title"] = title
                except ET.ParseError:
                    pass
            requests.append({"addDocumentTab": {"tabProperties": tab_properties}})

        elif node.op == ChangeOp.DELETED:
            tab_id = node.node_id
            if tab_id:
                requests.append({"deleteTab": {"tabId": tab_id}})

        return requests

    def emit_footnote(
        self,
        node: ChangeNode,
        content_block_xml: str | None = None,
        base_index: int = 1,
    ) -> list[dict[str, Any]]:
        """Handle footnote add/delete.

        For ADDED: Creates footnote at endOfSegmentLocation.
        For DELETED: Deletes the 1-character footnote reference.
        """
        requests: list[dict[str, Any]] = []

        if node.op == ChangeOp.ADDED:
            requests.append({"createFootnote": {"endOfSegmentLocation": {}}})

        elif node.op == ChangeOp.DELETED:
            index = self._calculate_footnote_index(
                content_block_xml, node.node_id, base_index
            )
            if index > 0:
                requests.append(
                    {
                        "deleteContentRange": {
                            "range": {
                                "startIndex": index,
                                "endIndex": index + 1,
                            }
                        }
                    }
                )

        return requests

    def _calculate_footnote_index(
        self,
        content_xml: str | None,
        footnote_id: str,
        base_index: int,
    ) -> int:
        """Calculate the index where a footnote reference is located."""
        if not content_xml:
            return 0

        pattern = rf'<footnote[^>]*id="{re.escape(footnote_id)}"'
        match = re.search(pattern, content_xml)
        if not match:
            return 0

        before_footnote = content_xml[: match.start()]

        text_length = 0
        in_tag = False
        for char in before_footnote:
            if char == "<":
                in_tag = True
            elif char == ">":
                in_tag = False
            elif not in_tag:
                text_length += 1

        newline_count = len(
            re.findall(r"</(?:p|h[1-6]|li|title|subtitle)>", before_footnote)
        )
        text_length += newline_count

        return base_index + text_length
