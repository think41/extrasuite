"""extradoc - File-based Google Docs representation for LLM agents."""

__version__ = "0.1.0"

from extradoc.client import DocsClient, PushResult
from extradoc.transport import (
    APIError,
    AuthenticationError,
    DocumentData,
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
    "DocumentData",
    "GoogleDocsTransport",
    "LocalFileTransport",
    "NotFoundError",
    "PushResult",
    "Transport",
    "TransportError",
]
