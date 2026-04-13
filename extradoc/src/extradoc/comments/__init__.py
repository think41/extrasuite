"""Comments package: typed models, XML serialization, and diff.

Core exports (used by MarkdownSerde and the push executor):
    Comment, Reply, FileComments, DocumentWithComments
    CommentOperations (and operation types: NewReply, Resolve, EditComment,
        EditReply, DeleteComment)
    diff_comments       -- compare two FileComments → CommentOperations
    from_raw            -- parse Drive API v3 response → FileComments
    to_xml, from_xml    -- serialize/parse comments.xml

XmlSerde-only exports (not used by MarkdownSerde):
    inject_comment_refs, strip_comment_refs
    -- inject/strip <comment-ref> wrappers in document.xml strings.
    -- XmlSerde is broken and not maintained; these functions exist
    -- for legacy compatibility only.
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
