"""extrascript - Google Apps Script management for LLM agents.

Pull, edit, push, and lint Google Apps Script projects.
Supports both standalone and container-bound scripts.
"""

__version__ = "0.1.0"

from extrascript.client import DiffResult, PushResult, ScriptClient

__all__ = [
    "DiffResult",
    "PushResult",
    "ScriptClient",
    "__version__",
]
