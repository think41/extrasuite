"""extrascript - Google Apps Script management for LLM agents.

Pull, edit, push, and lint Google Apps Script projects.
Supports both standalone and container-bound scripts.
"""

__version__ = "0.1.0"

from extrascript.client import DiffResult, PushResult, ScriptClient
from extrascript.transport import (
    APIError,
    AuthenticationError,
    GoogleAppsScriptTransport,
    LocalFileTransport,
    NotFoundError,
    ProjectContent,
    ProjectMetadata,
    ScriptAPIError,
    ScriptFile,
    Transport,
    TransportError,
)

__all__ = [
    "APIError",
    "AuthenticationError",
    "DiffResult",
    "GoogleAppsScriptTransport",
    "LocalFileTransport",
    "NotFoundError",
    "ProjectContent",
    "ProjectMetadata",
    "PushResult",
    "ScriptAPIError",
    "ScriptClient",
    "ScriptFile",
    "Transport",
    "TransportError",
    "__version__",
]
