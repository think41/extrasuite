"""Inject and strip <comment-ref> tags in serde document.xml strings.

inject_comment_refs(xml_str, comments) is called after serde writes a tab's
document.xml. It inserts <comment-ref> wrapper elements around the block
elements that correspond to each comment's anchor range.

strip_comment_refs(xml_str) is called during deserialization to remove
<comment-ref> wrappers and let the inner elements flow normally.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING
from xml.etree.ElementTree import indent, tostring

from ._snap import (
    compute_element_spans,
    find_overlapping_elements,
    parse_anchor_range,
)

if TYPE_CHECKING:
    from ._types import FileComments


def _element_to_string(elem: ET.Element) -> str:
    """Convert Element to pretty-printed XML string with declaration."""
    indent(elem)
    xml_str = tostring(elem, encoding="unicode")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_str + "\n"


def _truncate_message(text: str) -> str:
    """Truncate message to ~80 chars with ellipsis if needed."""
    if len(text) > 80:
        return text[:77] + "..."
    return text


def inject_comment_refs(xml_str: str, comments: FileComments) -> str:
    """Inject <comment-ref> wrappers into a serde document.xml string.

    For each active comment with a parseable anchor, finds the body elements
    that overlap with the anchor range and wraps them with <comment-ref>.

    Args:
        xml_str: A serde document.xml string (output of TabXml.to_xml_string())
        comments: The FileComments for this document

    Returns:
        Modified XML string with <comment-ref> wrappers injected
    """
    active = [c for c in comments.comments if not c.deleted]
    if not active:
        return xml_str

    root = ET.fromstring(xml_str)
    body = root.find("body")
    if body is None:
        return xml_str

    # Compute spans for all body children
    spans = compute_element_spans(body)
    if not spans:
        return xml_str

    # For each comment, find the indices of overlapping body elements
    # elem_comment_ids[i] = first comment_id covering body element i
    elem_comment_ids: dict[int, str] = {}
    comment_attrs: dict[str, dict[str, object]] = {}

    for comment in active:
        rng = parse_anchor_range(comment.anchor)
        if rng is None:
            continue
        anchor_start, anchor_end = rng

        overlapping = find_overlapping_elements(spans, anchor_start, anchor_end)
        if not overlapping:
            continue

        comment_attrs[comment.id] = {
            "message": _truncate_message(comment.content),
            "replies": sum(1 for r in comment.replies if not r.deleted),
            "resolved": comment.resolved,
        }

        for span in overlapping:
            idx = next((i for i, s in enumerate(spans) if s is span), None)
            if idx is None:
                continue
            # First comment wins if multiple overlap the same element
            if idx not in elem_comment_ids:
                elem_comment_ids[idx] = comment.id

    if not elem_comment_ids:
        return xml_str

    # Build new body children list with comment-ref wrappers
    children = list(body)
    new_children: list[ET.Element] = []
    i = 0
    while i < len(children):
        cid = elem_comment_ids.get(i)
        if cid is None:
            new_children.append(children[i])
            i += 1
            continue

        # Find the contiguous run of elements with this same comment_id
        j = i
        while j < len(children) and elem_comment_ids.get(j) == cid:
            j += 1

        attrs = comment_attrs.get(cid, {})
        ref = ET.Element("comment-ref")
        ref.set("id", cid)
        ref.set("message", str(attrs.get("message", "")))
        ref.set("replies", str(attrs.get("replies", 0)))
        ref.set("resolved", "true" if attrs.get("resolved") else "false")

        for elem in children[i:j]:
            ref.append(elem)

        new_children.append(ref)
        i = j

    # Replace body children with new_children
    for child in list(body):
        body.remove(child)
    for child in new_children:
        body.append(child)

    return _element_to_string(root)


def strip_comment_refs(xml_str: str) -> str:
    """Strip <comment-ref> wrappers from a serde document.xml string.

    Called during deserialization: removes all <comment-ref> elements and
    promotes their children to the parent level. The document body is
    reconstructed without any trace of comment anchors.

    Args:
        xml_str: A serde document.xml string that may contain <comment-ref>

    Returns:
        XML string with all <comment-ref> wrappers removed
    """
    if "comment-ref" not in xml_str:
        return xml_str

    root = ET.fromstring(xml_str)
    body = root.find("body")
    if body is None:
        return xml_str

    _strip_comment_refs_from(body)
    return _element_to_string(root)


def _strip_comment_refs_from(parent: ET.Element) -> None:
    """Strip <comment-ref> wrappers from an element's direct children."""
    children = list(parent)
    for child in children:
        parent.remove(child)

    pos = 0
    for child in children:
        if child.tag == "comment-ref":
            _strip_comment_refs_from(child)
            for grandchild in list(child):
                parent.insert(pos, grandchild)
                pos += 1
        else:
            _strip_comment_refs_from(child)
            parent.insert(pos, child)
            pos += 1
