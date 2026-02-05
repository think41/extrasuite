"""Custom exceptions for ExtraForm."""

from __future__ import annotations


class ExtraFormError(Exception):
    """Base exception for all ExtraForm errors."""

    pass


class TransportError(ExtraFormError):
    """Base exception for transport-related errors."""

    pass


class AuthenticationError(TransportError):
    """Raised when authentication fails (401/403)."""

    pass


class NotFoundError(TransportError):
    """Raised when a form is not found (404)."""

    def __init__(self, form_id: str, message: str | None = None) -> None:
        self.form_id = form_id
        super().__init__(message or f"Form not found: {form_id}")


class APIError(TransportError):
    """Raised for other API errors."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        super().__init__(f"API error {status_code}: {message}")


class DiffError(ExtraFormError):
    """Base exception for diff-related errors."""

    pass


class MissingPristineError(DiffError):
    """Raised when .pristine/form.zip is missing."""

    def __init__(self, folder: str) -> None:
        self.folder = folder
        super().__init__(
            f"Missing pristine copy at {folder}/.pristine/form.zip. Run 'extraform pull' first."
        )


class InvalidFileError(ExtraFormError):
    """Raised when a file is invalid or corrupted."""

    def __init__(self, path: str, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(f"Invalid file {path}: {reason}")


class ValidationError(ExtraFormError):
    """Raised when form validation fails."""

    def __init__(self, message: str, errors: list[str] | None = None) -> None:
        self.errors = errors or []
        super().__init__(message)
