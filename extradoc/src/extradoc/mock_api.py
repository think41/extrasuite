"""Mock implementation of Google Docs API for testing.

This module is a re-export shim. The implementation lives in the
extradoc.mock package. All existing imports continue to work:

    from extradoc.mock_api import MockGoogleDocsAPI, MockAPIError, ValidationError
"""

from extradoc.mock.api import MockGoogleDocsAPI
from extradoc.mock.exceptions import MockAPIError, ValidationError

__all__ = ["MockAPIError", "MockGoogleDocsAPI", "ValidationError"]
