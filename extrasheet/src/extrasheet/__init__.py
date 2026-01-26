"""
extrasheet - File-based Google Sheets representation for LLM agents.

This library transforms Google Sheets into a file-based representation
optimized for LLM agents, enabling efficient "fly-blind" editing.
"""

__version__ = "0.1.0"

from extrasheet.client import (
    APIError,
    AuthenticationError,
    SheetsClient,
    SheetsClientError,
)
from extrasheet.transformer import SpreadsheetTransformer
from extrasheet.writer import FileWriter

__all__ = [
    "APIError",
    "AuthenticationError",
    "FileWriter",
    "SheetsClient",
    "SheetsClientError",
    "SpreadsheetTransformer",
    "__version__",
]
