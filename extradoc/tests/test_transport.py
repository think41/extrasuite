"""Tests for transport layer."""

from __future__ import annotations

import pytest

from extradoc.transport import (
    APIError,
    AuthenticationError,
    DocumentData,
    NotFoundError,
    TransportError,
)


def test_transport_error_hierarchy() -> None:
    """Test that transport errors have correct inheritance."""
    assert issubclass(AuthenticationError, TransportError)
    assert issubclass(NotFoundError, TransportError)
    assert issubclass(APIError, TransportError)


def test_api_error_has_status_code() -> None:
    """Test that APIError stores status code."""
    error = APIError("Test error", status_code=500)
    assert error.status_code == 500
    assert "Test error" in str(error)


def test_document_data_is_frozen() -> None:
    """Test that DocumentData is immutable."""
    data = DocumentData(
        document_id="test123",
        title="Test Document",
        raw={"documentId": "test123"},
    )

    assert data.document_id == "test123"
    assert data.title == "Test Document"

    # Should raise error when trying to modify (FrozenInstanceError)
    with pytest.raises(AttributeError):
        data.document_id = "modified"  # type: ignore[misc]
