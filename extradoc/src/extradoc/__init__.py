"""extradoc - File-based Google Docs representation for LLM agents.

This library transforms Google Docs into a file-based representation
optimized for LLM agents, enabling efficient "fly-blind" editing.
"""

__version__ = "0.1.0"

from extradoc.client import DocsClient
from extradoc.indexer import (
    IndexCalculator,
    IndexMismatch,
    IndexValidationResult,
    strip_indexes,
    utf16_len,
    validate_document,
)
from extradoc.transport import (
    APIError,
    AuthenticationError,
    GoogleDocsTransport,
    LocalFileTransport,
    NotFoundError,
    Transport,
    TransportError,
)

__all__ = [
    "APIError",
    "AuthenticationError",
    "DocsClient",
    "GoogleDocsTransport",
    "IndexCalculator",
    "IndexMismatch",
    "IndexValidationResult",
    "LocalFileTransport",
    "NotFoundError",
    "Transport",
    "TransportError",
    "__version__",
    "strip_indexes",
    "utf16_len",
    "validate_document",
]
