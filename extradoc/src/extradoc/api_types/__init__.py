"""Google Docs API Pydantic models.

Re-exports the most commonly used types. For the full set of models,
import directly from ``extradoc.api_types._generated``.
"""

from typing import TypeAlias

from extradoc.api_types._generated import (
    BatchUpdateDocumentRequest,
    BatchUpdateDocumentResponse,
    DeferredID,
    Document,
    Request,
    Response,
)

# Type aliases for IDs that can be real (str) or deferred (DeferredID)
SegmentID: TypeAlias = str | DeferredID | None
TabID: TypeAlias = str | DeferredID | None

__all__ = [
    "BatchUpdateDocumentRequest",
    "BatchUpdateDocumentResponse",
    "DeferredID",
    "Document",
    "Request",
    "Response",
    "SegmentID",
    "TabID",
]
