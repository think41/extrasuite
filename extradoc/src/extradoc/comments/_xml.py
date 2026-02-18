"""comments.xml serialization for FileComments.

Written at the folder root, parallel to index.xml. Stores the raw Drive API
anchor strings verbatim. The agent can edit comment/reply content, add
replies, set resolved="true", or delete a <comment> element. All other
attributes are read-only.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from xml.dom.minidom import parseString

from ._types import Comment, FileComments, Reply


def _pretty_xml(root: ET.Element) -> str:
    """Serialize an ElementTree Element to a pretty-printed XML string."""
    rough = ET.tostring(root, encoding="unicode", xml_declaration=False)
    declaration = '<?xml version="1.0" encoding="UTF-8"?>\n'
    try:
        dom = parseString(rough)
        pretty = dom.toprettyxml(indent="  ", encoding=None)
        lines = pretty.split("\n")
        if lines and lines[0].startswith("<?xml"):
            lines = lines[1:]
        while lines and not lines[-1].strip():
            lines.pop()
        return declaration + "\n".join(lines) + "\n"
    except Exception:
        return declaration + rough + "\n"


def to_xml(fc: FileComments) -> str:
    """Serialize FileComments to comments.xml format.

    Deleted comments and replies are excluded.
    """
    root = ET.Element("comments")
    root.set("file-id", fc.file_id)

    for comment in fc.comments:
        if comment.deleted:
            continue

        c_elem = ET.SubElement(root, "comment")
        c_elem.set("id", comment.id)
        c_elem.set("author", comment.author)
        c_elem.set("created", comment.created_time)
        c_elem.set("resolved", "true" if comment.resolved else "false")
        c_elem.set("anchor", comment.anchor)

        content_elem = ET.SubElement(c_elem, "content")
        content_elem.text = comment.content

        non_deleted_replies = [r for r in comment.replies if not r.deleted]
        if non_deleted_replies:
            replies_elem = ET.SubElement(c_elem, "replies")
            for reply in non_deleted_replies:
                r_elem = ET.SubElement(replies_elem, "reply")
                r_elem.set("id", reply.id)
                r_elem.set("author", reply.author)
                r_elem.set("created", reply.created_time)
                content_r = ET.SubElement(r_elem, "content")
                content_r.text = reply.content

    return _pretty_xml(root)


def from_xml(xml_content: str) -> FileComments:
    """Parse comments.xml into a FileComments object."""
    root = ET.fromstring(xml_content)
    file_id = root.get("file-id", "")

    comments: list[Comment] = []
    for c_elem in root.findall("comment"):
        comment_id = c_elem.get("id", "")
        author = c_elem.get("author", "")
        created_time = c_elem.get("created", "")
        resolved = c_elem.get("resolved", "false") == "true"
        anchor = c_elem.get("anchor", "")

        content_elem = c_elem.find("content")
        content = content_elem.text or "" if content_elem is not None else ""

        replies: list[Reply] = []
        replies_elem = c_elem.find("replies")
        if replies_elem is not None:
            for r_elem in replies_elem.findall("reply"):
                reply_id = r_elem.get("id", "")
                reply_author = r_elem.get("author", "")
                reply_created = r_elem.get("created", "")
                r_content_elem = r_elem.find("content")
                r_content = (
                    r_content_elem.text or "" if r_content_elem is not None else ""
                )
                replies.append(
                    Reply(
                        id=reply_id,
                        author=reply_author,
                        created_time=reply_created,
                        content=r_content,
                    )
                )

        comments.append(
            Comment(
                id=comment_id,
                author=author,
                created_time=created_time,
                content=content,
                anchor=anchor,
                resolved=resolved,
                deleted=False,
                replies=replies,
            )
        )

    return FileComments(file_id=file_id, comments=comments)
