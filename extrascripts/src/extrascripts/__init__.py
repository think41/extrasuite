"""extrascripts - Google Apps Script management for LLM agents.

Pull, edit, push, run, and lint Google Apps Script projects.
Supports both standalone and container-bound scripts.
"""

__version__ = "0.1.0"

from extrascripts.client import ScriptsClient
from extrascripts.transport import (
    APIError,
    AppsScriptTransport,
    AuthenticationError,
    LocalFileTransport,
    NotFoundError,
    Transport,
    TransportError,
)

__all__ = [
    "APIError",
    "AppsScriptTransport",
    "AuthenticationError",
    "LocalFileTransport",
    "NotFoundError",
    "ScriptsClient",
    "Transport",
    "TransportError",
    "__version__",
]
