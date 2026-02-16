"""Reconcile module: diff two Documents to produce a BatchUpdateDocumentRequest.

Public API:
    reconcile(base, desired) -> BatchUpdateDocumentRequest
    verify(base, requests, desired) -> (match, diffs)
    reindex_document(doc) -> Document
"""

from extradoc.reconcile._comparators import documents_match
from extradoc.reconcile._core import reconcile, reindex_document, verify

__all__ = [
    "ReconcileError",
    "documents_match",
    "reconcile",
    "reindex_document",
    "verify",
]


class ReconcileError(Exception):
    """Raised when reconciliation encounters an unsupported or invalid change."""
