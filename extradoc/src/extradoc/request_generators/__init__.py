"""Request generators for Google Docs batchUpdate operations.

This package contains modules for generating different types of batchUpdate requests:
- structural: Headers, footers, tabs, footnotes, tables (creation/deletion)
- table: Table structure and cell content
- content: Text insertion and paragraph/text styling
"""

from .content import generate_content_requests
from .structural import (
    STRUCTURAL_REQUEST_TYPES,
    extract_created_ids,
    separate_structural_requests,
    substitute_placeholder_ids,
)
from .table import generate_table_cell_style_requests

__all__ = [
    "STRUCTURAL_REQUEST_TYPES",
    "extract_created_ids",
    "generate_content_requests",
    "generate_table_cell_style_requests",
    "separate_structural_requests",
    "substitute_placeholder_ids",
]
