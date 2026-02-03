"""extradoc - File-based Google Docs representation for LLM agents.

This library transforms Google Docs into a file-based representation
optimized for LLM agents, enabling efficient "fly-blind" editing.
"""

__version__ = "0.1.0"

from extradoc.client import (
    DiffError,
    DiffResult,
    DocsClient,
    PushResult,
    ValidationError,
    ValidationResult,
)
from extradoc.html_converter import (
    ConversionContext,
    convert_document_to_html,
)
from extradoc.html_parser import (
    HTMLDocument,
    HTMLParagraph,
    HTMLTable,
    TextSpan,
    generate_delete_content_request,
    generate_insert_text_request,
    generate_update_text_style_request,
    parse_html,
)
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
    "ConversionContext",
    "DiffError",
    "DiffResult",
    "DocsClient",
    "GoogleDocsTransport",
    "HTMLDocument",
    "HTMLParagraph",
    "HTMLTable",
    "IndexCalculator",
    "IndexMismatch",
    "IndexValidationResult",
    "LocalFileTransport",
    "NotFoundError",
    "PushResult",
    "TextSpan",
    "Transport",
    "TransportError",
    "ValidationError",
    "ValidationResult",
    "__version__",
    "convert_document_to_html",
    "generate_delete_content_request",
    "generate_insert_text_request",
    "generate_update_text_style_request",
    "parse_html",
    "strip_indexes",
    "utf16_len",
    "validate_document",
]
