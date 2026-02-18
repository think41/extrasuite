"""Comments package: typed models, XML serialization, diff, and injection.

Public exports:
    Comment, Reply, FileComments, DocumentWithComments
    CommentOperations (and operation types)
    diff_comments
    from_raw
    to_xml, from_xml
    inject_comment_refs, strip_comment_refs
"""

from ._diff import diff_comments
from ._from_raw import from_raw
from ._inject import inject_comment_refs, strip_comment_refs
from ._types import (
    Comment,
    CommentOperations,
    DeleteComment,
    DocumentWithComments,
    EditComment,
    EditReply,
    FileComments,
    NewReply,
    Reply,
    Resolve,
)
from ._xml import from_xml, to_xml

__all__ = [
    "Comment",
    "CommentOperations",
    "DeleteComment",
    "DocumentWithComments",
    "EditComment",
    "EditReply",
    "FileComments",
    "NewReply",
    "Reply",
    "Resolve",
    "diff_comments",
    "from_raw",
    "from_xml",
    "inject_comment_refs",
    "strip_comment_refs",
    "to_xml",
]
