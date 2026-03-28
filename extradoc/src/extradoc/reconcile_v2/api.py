"""Public API surface for the semantic-IR reconciler."""

from __future__ import annotations

from typing import TYPE_CHECKING

from extradoc.reconcile_v2.diff import diff_documents
from extradoc.reconcile_v2.parse import parse_document
from extradoc.reconcile_v2.testing import summarize_document_ir

if TYPE_CHECKING:
    from extradoc.api_types._generated import BatchUpdateDocumentRequest, Document
    from extradoc.reconcile_v2.diff import SemanticEdit
    from extradoc.reconcile_v2.ir import DocumentIR


def inspect_document(document: Document) -> DocumentIR:
    """Parse a transport document into the spike semantic IR."""
    return parse_document(document)


def summarize_document(document: Document) -> str:
    """Parse and summarize a transport document for design inspection."""
    return summarize_document_ir(parse_document(document))


def semantic_diff(base: Document, desired: Document) -> list[SemanticEdit]:
    """Return a narrow semantic edit list for confidence-sprint fixtures."""
    return diff_documents(base, desired)


def reconcile(base: Document, desired: Document) -> list[BatchUpdateDocumentRequest]:
    """Return a batchUpdate plan transforming ``base`` into ``desired``.

    This entrypoint is intentionally a stub until the new reconciler is
    implemented task-by-task under ``reconcile_v2``.
    """
    raise NotImplementedError("extradoc.reconcile_v2 is not implemented yet")
