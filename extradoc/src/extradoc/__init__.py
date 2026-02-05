"""extradoc - File-based Google Docs representation for LLM agents.

This library transforms Google Docs into a file-based XML representation
optimized for LLM agents, enabling efficient editing with a pull/diff/push workflow.
"""

__version__ = "0.1.0"

from extradoc.block_diff import (
    Block,
    BlockChange,
    BlockDiffDetector,
    BlockType,
    ChangeType,
    diff_documents_block_level,
    format_changes,
)
from extradoc.client import (
    DiffError,
    DiffResult,
    DocsClient,
    PushResult,
    ValidationError,
    ValidationResult,
)
from extradoc.desugar import (
    DesugaredDocument,
    Paragraph,
    Section,
    Table,
    TextRun,
    desugar_document,
)
from extradoc.diff_engine import diff_documents
from extradoc.indexer import (
    IndexCalculator,
    IndexMismatch,
    IndexValidationResult,
    strip_indexes,
    utf16_len,
    validate_document,
)
from extradoc.style_factorizer import (
    FactorizedStyles,
    StyleDefinition,
    factorize_styles,
)
from extradoc.style_hash import style_id
from extradoc.transport import (
    APIError,
    AuthenticationError,
    GoogleDocsTransport,
    LocalFileTransport,
    NotFoundError,
    Transport,
    TransportError,
)
from extradoc.xml_converter import convert_document_to_xml

__all__ = [
    "APIError",
    "AuthenticationError",
    "Block",
    "BlockChange",
    "BlockDiffDetector",
    "BlockType",
    "ChangeType",
    "DesugaredDocument",
    "DiffError",
    "DiffResult",
    "DocsClient",
    "FactorizedStyles",
    "GoogleDocsTransport",
    "IndexCalculator",
    "IndexMismatch",
    "IndexValidationResult",
    "LocalFileTransport",
    "NotFoundError",
    "Paragraph",
    "PushResult",
    "Section",
    "StyleDefinition",
    "Table",
    "TextRun",
    "Transport",
    "TransportError",
    "ValidationError",
    "ValidationResult",
    "__version__",
    "convert_document_to_xml",
    "desugar_document",
    "diff_documents",
    "diff_documents_block_level",
    "factorize_styles",
    "format_changes",
    "strip_indexes",
    "style_id",
    "utf16_len",
    "validate_document",
]
