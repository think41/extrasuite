"""Reconcile module: diff two Documents to produce a BatchUpdateDocumentRequest.

Public API:
    reconcile(base, desired) -> list[BatchUpdateDocumentRequest]
    resolve_deferred_ids(prior_responses, batch) -> BatchUpdateDocumentRequest
    verify(base, batches, desired) -> (match, diffs)
    reindex_document(doc) -> Document
"""

from __future__ import annotations

from extradoc.api_types import DeferredID
from extradoc.reconcile._comparators import documents_match
from extradoc.reconcile._core import (
    reconcile,
    reindex_document,
    resolve_deferred_ids,
    verify,
)
from extradoc.reconcile._generators import ReconcileError

__all__ = [
    "DeferredID",
    "ReconcileError",
    "documents_match",
    "reconcile",
    "reindex_document",
    "resolve_deferred_ids",
    "verify",
]
