"""Mock Google Docs API package for testing."""

from extradoc.mock.api import MockGoogleDocsAPI
from extradoc.mock.exceptions import MockAPIError, ValidationError

__all__ = ["MockAPIError", "MockGoogleDocsAPI", "ValidationError"]
