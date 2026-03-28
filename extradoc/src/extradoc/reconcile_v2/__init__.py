"""Second-generation reconciler under active development.

This package is intentionally isolated from ``extradoc.reconcile`` so the new
semantic-IR architecture can be implemented incrementally in-tree.
"""

from __future__ import annotations

from extradoc.reconcile_v2.api import (
    canonical_document_signature,
    canonicalize_transport_document,
    inspect_document,
    lower_semantic_diff,
    reconcile,
    semantic_diff,
    summarize_document,
)
from extradoc.reconcile_v2.diff import summarize_semantic_edits

__all__ = [
    "canonical_document_signature",
    "canonicalize_transport_document",
    "inspect_document",
    "lower_semantic_diff",
    "reconcile",
    "semantic_diff",
    "summarize_document",
    "summarize_semantic_edits",
]
