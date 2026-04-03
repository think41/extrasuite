"""reindex_document — the only surviving function from the v1 reconcile package."""

from __future__ import annotations

from extradoc.api_types._generated import Document
from extradoc.mock.reindex import reindex_and_normalize_all_tabs


def reindex_document(doc: Document) -> Document:
    """Reindex a Document using mock/reindex.py logic.

    Converts to dict, runs reindex_and_normalize_all_tabs(), converts back.
    Allows tests to create Documents without worrying about indices.
    """
    doc_dict = doc.model_dump(by_alias=True, exclude_none=True)
    reindex_and_normalize_all_tabs(doc_dict)
    return Document.model_validate(doc_dict)
