"""diff_comments: compare two FileComments and produce CommentOperations.

Compares base (pristine) and desired (edited) FileComments by comment id.
"""

from __future__ import annotations

import logging

from ._types import (
    Comment,
    CommentOperations,
    DeleteComment,
    EditComment,
    EditReply,
    FileComments,
    NewReply,
    Reply,
    Resolve,
)

logger = logging.getLogger(__name__)


def diff_comments(base: FileComments, desired: FileComments) -> CommentOperations:
    """Compare two FileComments and produce the operations needed.

    Args:
        base: The pristine (original) comments
        desired: The desired (edited) comments

    Returns:
        CommentOperations describing what needs to change
    """
    ops = CommentOperations()

    # Build lookups for base
    base_by_id: dict[str, object] = {}
    base_resolved: set[str] = set()
    base_replies_by_comment: dict[str, dict[str, object]] = {}
    base_content: dict[str, str] = {}

    for comment in base.comments:
        if comment.deleted:
            continue
        base_by_id[comment.id] = comment
        base_content[comment.id] = comment.content
        if comment.resolved:
            base_resolved.add(comment.id)
        base_replies_by_comment[comment.id] = {}
        for reply in comment.replies:
            if not reply.deleted:
                base_replies_by_comment[comment.id][reply.id] = reply

    # Walk desired comments
    desired_ids: set[str] = set()
    for comment in desired.comments:
        # comments.xml only stores non-deleted comments, so no deleted field here
        comment_id = comment.id
        desired_ids.add(comment_id)

        if comment_id not in base_by_id:
            # New top-level comment — blocked (anchor-creation limitation)
            logger.warning(
                "Skipping new comment '%s': creating anchored top-level comments "
                "is not supported by the Google Drive API",
                comment.content[:60],
            )
            continue

        base_comment = base_by_id[comment_id]
        assert isinstance(base_comment, Comment)

        # Check content edit
        if comment.content != base_content[comment_id]:
            ops.edits.append(
                EditComment(comment_id=comment_id, content=comment.content)
            )

        # Check resolve (flip false→true only; re-opening is not supported)
        if comment.resolved and comment_id not in base_resolved:
            ops.resolves.append(Resolve(comment_id=comment_id))

        # Check replies
        base_replies = base_replies_by_comment.get(comment_id, {})
        for reply in comment.replies:
            if reply.id not in base_replies:
                # New reply (no id in base)
                if reply.content:
                    ops.new_replies.append(
                        NewReply(comment_id=comment_id, content=reply.content)
                    )
            else:
                # Existing reply — check content edit
                base_reply = base_replies[reply.id]
                assert isinstance(base_reply, Reply)
                if reply.content != base_reply.content:
                    ops.reply_edits.append(
                        EditReply(
                            comment_id=comment_id,
                            reply_id=reply.id,
                            content=reply.content,
                        )
                    )

    # Check for deleted comments (present in base but absent in desired)
    for comment_id in base_by_id:
        if comment_id not in desired_ids:
            ops.deletes.append(DeleteComment(comment_id=comment_id))

    return ops
