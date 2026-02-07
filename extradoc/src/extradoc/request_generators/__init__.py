"""Request generators for Google Docs batchUpdate operations.

This package contains modules for generating different types of batchUpdate requests:
- structural: Headers, footers, tabs, footnotes, tables (creation/deletion)
- table: Table structure (insert/delete rows and columns)
- content: (reserved for future text insertion and paragraph/text styling)
"""

from .structural import (
    STRUCTURAL_REQUEST_TYPES,
)

__all__ = [
    "STRUCTURAL_REQUEST_TYPES",
]
