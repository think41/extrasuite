"""Convert Google Drive comments to/from XML format.

Handles conversion between Drive API v3 comment responses and the
comments.xml format used by extradoc for agent interaction.

Position info is NOT stored in comments.xml — instead, <comment-ref>
tags in document.xml mark the commented text inline. comments.xml only
stores comment content, replies, and resolved status.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any
from xml.dom.minidom import parseString

from extradoc.block_indexer import SPECIAL_TAGS, BlockIndexer
from extradoc.indexer import utf16_len
from extradoc.parser import BlockParser
from extradoc.types import ParagraphBlock, SegmentBlock, TableBlock, TableCellBlock


@dataclass
class NewComment:
    """A new comment to create on the document."""

    content: str
    start_index: int | None = None
    end_index: int | None = None
    quoted_text: str = ""


@dataclass
class NewReply:
    """A new reply to add to an existing comment."""

    comment_id: str
    content: str


@dataclass
class ResolveComment:
    """A comment to resolve."""

    comment_id: str


@dataclass
class CommentOperations:
    """Operations extracted from diff between pristine and current comments.xml."""

    new_comments: list[NewComment] = field(default_factory=list)
    new_replies: list[NewReply] = field(default_factory=list)
    resolves: list[ResolveComment] = field(default_factory=list)

    @property
    def has_operations(self) -> bool:
        return bool(self.new_comments or self.new_replies or self.resolves)


def convert_comments_to_xml(
    comments: list[dict[str, Any]],
    file_id: str,
) -> str:
    """Convert Drive API comment responses to comments.xml format.

    No position info is stored — positions are represented by
    <comment-ref> tags in document.xml instead.

    Args:
        comments: List of comment dicts from Drive API v3
        file_id: The document file ID

    Returns:
        XML string for comments.xml
    """
    root = ET.Element("comments", fileId=file_id)

    for comment in comments:
        if comment.get("deleted", False):
            continue

        comment_elem = ET.SubElement(root, "comment")
        comment_elem.set("id", comment["id"])

        # Author
        author = comment.get("author", {})
        author_name = author.get("displayName", "Unknown")
        author_email = author.get("emailAddress", "")
        if author_email:
            comment_elem.set("author", f"{author_name} <{author_email}>")
        else:
            comment_elem.set("author", author_name)

        # Timestamps
        if "createdTime" in comment:
            comment_elem.set("time", comment["createdTime"])

        # Resolved
        comment_elem.set(
            "resolved", "true" if comment.get("resolved", False) else "false"
        )

        # Content
        content_elem = ET.SubElement(comment_elem, "content")
        content_elem.text = comment.get("content", "")

        # Replies
        replies = comment.get("replies", [])
        non_deleted_replies = [r for r in replies if not r.get("deleted", False)]
        if non_deleted_replies:
            replies_elem = ET.SubElement(comment_elem, "replies")
            for reply in non_deleted_replies:
                reply_elem = ET.SubElement(replies_elem, "reply")
                reply_elem.set("id", reply["id"])

                reply_author = reply.get("author", {})
                reply_name = reply_author.get("displayName", "Unknown")
                reply_email = reply_author.get("emailAddress", "")
                if reply_email:
                    reply_elem.set("author", f"{reply_name} <{reply_email}>")
                else:
                    reply_elem.set("author", reply_name)

                if "createdTime" in reply:
                    reply_elem.set("time", reply["createdTime"])

                reply_elem.text = reply.get("content", "")

    # Format with minidom for pretty printing
    rough_string = ET.tostring(root, encoding="unicode", xml_declaration=False)
    xml_declaration = '<?xml version="1.0" encoding="UTF-8"?>\n'
    try:
        dom = parseString(rough_string)
        pretty = dom.toprettyxml(indent="  ", encoding=None)
        # Remove the xml declaration added by minidom (we add our own)
        lines = pretty.split("\n")
        if lines and lines[0].startswith("<?xml"):
            lines = lines[1:]
        # Remove trailing empty lines
        while lines and not lines[-1].strip():
            lines.pop()
        return xml_declaration + "\n".join(lines) + "\n"
    except Exception:
        return xml_declaration + rough_string + "\n"


def parse_comments_xml(xml_content: str) -> tuple[str, list[dict[str, Any]]]:
    """Parse comments.xml into structured data.

    Args:
        xml_content: The comments.xml content

    Returns:
        Tuple of (file_id, list of parsed comment dicts)
    """
    root = ET.fromstring(xml_content)
    file_id = root.get("fileId", "")

    comments: list[dict[str, Any]] = []
    for comment_elem in root.findall("comment"):
        comment: dict[str, Any] = {}

        comment_id = comment_elem.get("id")
        if comment_id:
            comment["id"] = comment_id

        resolved = comment_elem.get("resolved")
        if resolved:
            comment["resolved"] = resolved == "true"

        content_elem = comment_elem.find("content")
        if content_elem is not None and content_elem.text:
            comment["content"] = content_elem.text

        # Parse replies
        replies_elem = comment_elem.find("replies")
        if replies_elem is not None:
            replies: list[dict[str, Any]] = []
            for reply_elem in replies_elem.findall("reply"):
                reply: dict[str, Any] = {}
                reply_id = reply_elem.get("id")
                if reply_id:
                    reply["id"] = reply_id
                if reply_elem.text:
                    reply["content"] = reply_elem.text
                replies.append(reply)
            if replies:
                comment["replies"] = replies

        comments.append(comment)

    return file_id, comments


def extract_comment_ref_ids(document_xml: str) -> set[str]:
    """Scan document.xml for all <comment-ref> element IDs.

    Args:
        document_xml: The document.xml content

    Returns:
        Set of comment-ref IDs found in the document
    """
    # Use regex instead of XML parser to handle comment-ref as unknown tag
    return set(re.findall(r'<comment-ref\s+id="([^"]+)"', document_xml))


@dataclass
class CommentRefPosition:
    """Position information for a comment-ref in the document."""

    comment_ref_id: str
    start_index: int
    end_index: int
    quoted_text: str


def compute_comment_ref_positions(
    document_xml: str,
) -> list[CommentRefPosition]:
    """Compute UTF-16 positions for <comment-ref> tags in document.xml.

    Parses the document using BlockParser + BlockIndexer, then walks
    paragraph XML to find comment-ref elements and compute their positions.

    Args:
        document_xml: The document.xml content

    Returns:
        List of CommentRefPosition with computed positions
    """
    parser = BlockParser()
    doc = parser.parse(document_xml)
    indexer = BlockIndexer()
    indexer.compute(doc)

    positions: list[CommentRefPosition] = []

    def _process_segment(segment: SegmentBlock) -> None:
        for block in segment.children:
            if isinstance(block, ParagraphBlock):
                _process_paragraph(block)
            elif isinstance(block, TableBlock):
                for row in block.rows:
                    for cell in row.cells:
                        _process_cell(cell)

    def _process_cell(cell: TableCellBlock) -> None:
        for block in cell.children:
            if isinstance(block, ParagraphBlock):
                _process_paragraph(block)
            elif isinstance(block, TableBlock):
                for row in block.rows:
                    for c in row.cells:
                        _process_cell(c)

    def _process_paragraph(para: ParagraphBlock) -> None:
        try:
            root = ET.fromstring(para.xml)
        except ET.ParseError:
            return

        # Walk the XML tree tracking UTF-16 offset from paragraph start
        para_start = para.start_index
        _walk_for_comment_refs(root, para_start, positions)

    for tab in doc.tabs:
        for segment in tab.segments:
            _process_segment(segment)

    return positions


def _walk_for_comment_refs(
    elem: ET.Element,
    offset: int,
    positions: list[CommentRefPosition],
) -> int:
    """Walk an XML element tree, tracking UTF-16 offset, finding comment-ref elements.

    Returns the updated offset after processing this element.
    """
    if elem.tag == "comment-ref":
        start = offset
        # Calculate text content length inside the comment-ref
        inner_text = _extract_all_text(elem)
        inner_len = utf16_len(inner_text)
        comment_id = elem.get("id", "")
        if comment_id:
            positions.append(
                CommentRefPosition(
                    comment_ref_id=comment_id,
                    start_index=start,
                    end_index=start + inner_len,
                    quoted_text=inner_text,
                )
            )
        # Process children to advance offset (text inside comment-ref counts)
        offset = _advance_offset_through_children(elem, offset)
        return offset

    if elem.tag in SPECIAL_TAGS:
        # Special elements consume 1 index unit, don't recurse
        return offset + 1

    if elem.tag == "equation":
        eq_len = int(elem.get("length", "1"))
        return offset + eq_len

    # Regular element — process text + children
    if elem.text:
        offset += utf16_len(elem.text)

    for child in elem:
        offset = _walk_for_comment_refs(child, offset, positions)
        if child.tail:
            offset += utf16_len(child.tail)

    return offset


def _advance_offset_through_children(elem: ET.Element, offset: int) -> int:
    """Advance offset through an element's text content (for comment-ref innards)."""
    if elem.text:
        offset += utf16_len(elem.text)

    for child in elem:
        if child.tag in SPECIAL_TAGS:
            offset += 1
        elif child.tag == "equation":
            offset += int(child.get("length", "1"))
        elif child.tag == "comment-ref":
            # Nested comment-ref — just advance through its content
            offset = _advance_offset_through_children(child, offset)
        else:
            offset = _advance_offset_through_children(child, offset)
        if child.tail:
            offset += utf16_len(child.tail)

    return offset


def _extract_all_text(elem: ET.Element) -> str:
    """Extract all text from an element and its children (recursively)."""
    parts: list[str] = []
    if elem.text:
        parts.append(elem.text)
    for child in elem:
        parts.append(_extract_all_text(child))
        if child.tail:
            parts.append(child.tail)
    return "".join(parts)


def diff_comments(
    pristine_xml: str | None,
    current_xml: str,
    new_comment_ref_positions: list[CommentRefPosition] | None = None,
) -> CommentOperations:
    """Compare pristine and current comments.xml to extract operations.

    Args:
        pristine_xml: Pristine comments.xml content (None if no comments existed)
        current_xml: Current comments.xml content
        new_comment_ref_positions: Positions for new comment-refs from document.xml

    Returns:
        CommentOperations with new comments, replies, and resolves
    """
    ops = CommentOperations()

    # Parse current
    _file_id, current_comments = parse_comments_xml(current_xml)

    # Parse pristine
    pristine_comment_ids: set[str] = set()
    pristine_resolved: set[str] = set()
    pristine_reply_ids: dict[str, set[str]] = {}

    if pristine_xml:
        _pristine_file_id, pristine_comments = parse_comments_xml(pristine_xml)
        for pc in pristine_comments:
            cid = pc.get("id", "")
            if cid:
                pristine_comment_ids.add(cid)
                if pc.get("resolved", False):
                    pristine_resolved.add(cid)
                pristine_reply_ids[cid] = set()
                for pr in pc.get("replies", []):
                    rid = pr.get("id", "")
                    if rid:
                        pristine_reply_ids[cid].add(rid)

    # Build lookup from comment-ref positions
    ref_positions: dict[str, CommentRefPosition] = {}
    if new_comment_ref_positions:
        for pos in new_comment_ref_positions:
            ref_positions[pos.comment_ref_id] = pos

    for comment in current_comments:
        comment_id = comment.get("id")

        if not comment_id or comment_id not in pristine_comment_ids:
            # New comment — look up position from comment-ref
            content = comment.get("content", "")
            cid = comment_id or ""
            if content:
                ref_pos = ref_positions.get(cid)
                if ref_pos is not None:
                    ops.new_comments.append(
                        NewComment(
                            content=content,
                            start_index=ref_pos.start_index,
                            end_index=ref_pos.end_index,
                            quoted_text=ref_pos.quoted_text,
                        )
                    )
                else:
                    # No position (unanchored comment)
                    ops.new_comments.append(NewComment(content=content))
            continue

        # Existing comment — check for resolve
        if (
            comment_id in pristine_comment_ids
            and comment.get("resolved", False)
            and comment_id not in pristine_resolved
        ):
            ops.resolves.append(ResolveComment(comment_id=comment_id))

        # Check for new replies
        for reply in comment.get("replies", []):
            reply_id = reply.get("id")
            if not reply_id:
                # New reply (no id)
                reply_content = reply.get("content", "")
                if reply_content:
                    ops.new_replies.append(
                        NewReply(comment_id=comment_id, content=reply_content)
                    )

    return ops
