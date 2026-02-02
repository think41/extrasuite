"""extradoc - File-based Google Docs representation for LLM agents.

This library transforms Google Docs into a file-based representation
optimized for LLM agents, enabling efficient "fly-blind" editing.
"""

__version__ = "0.1.0"

from extradoc.client import DocsClient
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
    "LocalFileTransport",
    "NotFoundError",
    "Transport",
    "TransportError",
    "__version__",
]
