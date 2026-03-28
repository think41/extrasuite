"""Second-generation reconciler under active development.

This package is intentionally isolated from ``extradoc.reconcile`` so the new
semantic-IR architecture can be implemented incrementally in-tree.
"""

from __future__ import annotations

from extradoc.reconcile_v2.api import (
    inspect_document,
    reconcile,
    semantic_diff,
    summarize_document,
)
from extradoc.reconcile_v2.diff import summarize_semantic_edits

__all__ = [
    "inspect_document",
    "reconcile",
    "semantic_diff",
    "summarize_document",
    "summarize_semantic_edits",
]
