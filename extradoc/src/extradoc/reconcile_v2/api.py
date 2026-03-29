"""Public API surface for the semantic-IR reconciler."""

from __future__ import annotations

from typing import TYPE_CHECKING

from extradoc.api_types._generated import BatchUpdateDocumentRequest
from extradoc.reconcile_v2.batches import lower_document_batches
from extradoc.reconcile_v2.canonical import canonical_signature, canonicalize_document
from extradoc.reconcile_v2.diff import diff_documents
from extradoc.reconcile_v2.lower import lower_document_edits
from extradoc.reconcile_v2.parse import parse_document
from extradoc.reconcile_v2.testing import summarize_document_ir

if TYPE_CHECKING:
    from extradoc.api_types._generated import Document
    from extradoc.reconcile_v2.canonical import CanonicalDocumentSignature
    from extradoc.reconcile_v2.diff import SemanticEdit
    from extradoc.reconcile_v2.ir import DocumentIR


def inspect_document(document: Document) -> DocumentIR:
    """Parse a transport document into the semantic IR."""
    return parse_document(document)


def summarize_document(document: Document) -> str:
    """Parse and summarize a transport document for design inspection."""
    return summarize_document_ir(parse_document(document))


def canonicalize_transport_document(document: Document) -> DocumentIR:
    """Parse and canonicalize a transport document."""
    return canonicalize_document(document)


def canonical_document_signature(document: Document) -> CanonicalDocumentSignature:
    """Return a comparison-friendly canonical signature."""
    return canonical_signature(canonicalize_document(document))


def semantic_diff(base: Document, desired: Document) -> list[SemanticEdit]:
    """Return the supported semantic edit list for ``base`` -> ``desired``."""
    return diff_documents(base, desired)


def lower_semantic_diff(base: Document, desired: Document) -> list[dict[str, object]]:
    """Lower the supported semantic diff slice into raw request dicts."""
    return lower_document_edits(base, semantic_diff(base, desired), desired=desired)


def lower_semantic_diff_batches(
    base: Document,
    desired: Document,
    *,
    transport_base: Document | None = None,
) -> list[list[dict[str, object]]]:
    """Lower the supported semantic diff slice into one or more request batches."""
    return lower_document_batches(base, desired, transport_base=transport_base)


def reconcile(
    base: Document,
    desired: Document,
    *,
    transport_base: Document | None = None,
) -> list[BatchUpdateDocumentRequest]:
    """Return one or more batchUpdate plans transforming ``base`` into ``desired``.

    The semantic reconciler can require multiple request batches when later
    batches depend on response-derived IDs such as newly created tab IDs.
    Callers should execute the returned batches sequentially, resolving any
    deferred placeholders between batches.
    """
    return [
        BatchUpdateDocumentRequest.model_validate({"requests": batch})
        for batch in lower_document_batches(
            base,
            desired,
            transport_base=transport_base,
        )
    ]
