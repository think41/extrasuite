"""ExtraDoc v2 diff/push pipeline.

Public API:
- DiffEngine: for programmatic diff
- PushClient: for programmatic push
- ChangeNode, ChangeOp, NodeType: for inspecting change trees
"""

from .engine import DiffEngine
from .push import PushClient, PushResult
from .types import (
    ChangeNode,
    ChangeOp,
    DocumentBlock,
    NodeType,
    ParagraphBlock,
    SegmentBlock,
    SegmentType,
    StructuralBlock,
    TableBlock,
)

__all__ = [
    "ChangeNode",
    "ChangeOp",
    "DiffEngine",
    "DocumentBlock",
    "NodeType",
    "ParagraphBlock",
    "PushClient",
    "PushResult",
    "SegmentBlock",
    "SegmentType",
    "StructuralBlock",
    "TableBlock",
]
