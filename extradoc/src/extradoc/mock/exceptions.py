"""Exception classes for the mock Google Docs API."""

from __future__ import annotations


class MockAPIError(Exception):
    """Base class for mock API errors."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class ValidationError(MockAPIError):
    """Raised when request validation fails."""

    pass
