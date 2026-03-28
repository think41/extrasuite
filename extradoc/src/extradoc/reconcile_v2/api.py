"""Public API surface for the semantic-IR reconciler."""

from __future__ import annotations

from extradoc.api_types._generated import BatchUpdateDocumentRequest, Document


def reconcile(base: Document, desired: Document) -> list[BatchUpdateDocumentRequest]:
    """Return a batchUpdate plan transforming ``base`` into ``desired``.

    This entrypoint is intentionally a stub until the new reconciler is
    implemented task-by-task under ``reconcile_v2``.
    """
    raise NotImplementedError("extradoc.reconcile_v2 is not implemented yet")
