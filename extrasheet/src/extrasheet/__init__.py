"""extrasheet - File-based Google Sheets representation for LLM agents.

This library transforms Google Sheets into a file-based representation
optimized for LLM agents, enabling efficient "fly-blind" editing.
"""

__version__ = "0.1.0"

from extrasheet.client import (
    SheetsClient,
)
from extrasheet.transformer import SpreadsheetTransformer
from extrasheet.transport import (
    APIError,
    AuthenticationError,
    GoogleSheetsTransport,
    LocalFileTransport,
    NotFoundError,
    Transport,
    TransportError,
)
from extrasheet.writer import FileWriter

__all__ = [
    "APIError",
    "AuthenticationError",
    "FileWriter",
    "GoogleSheetsTransport",
    "LocalFileTransport",
    "NotFoundError",
    "SheetsClient",
    "SpreadsheetTransformer",
    "Transport",
    "TransportError",
    "__version__",
]
