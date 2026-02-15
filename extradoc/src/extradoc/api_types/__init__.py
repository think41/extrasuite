"""Google Docs API Pydantic models.

Re-exports the most commonly used types. For the full set of models,
import directly from ``extradoc.api_types._generated``.
"""

from extradoc.api_types._generated import (
    BatchUpdateDocumentRequest,
    BatchUpdateDocumentResponse,
    Document,
    Request,
    Response,
)

__all__ = [
    "BatchUpdateDocumentRequest",
    "BatchUpdateDocumentResponse",
    "Document",
    "Request",
    "Response",
]
