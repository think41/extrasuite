"""Transport layer for fetching document data.

Defines the Transport protocol and implementations:
- GoogleDocsTransport: Production transport using Google Docs API
- LocalFileTransport: Test transport reading from local golden files
"""

from __future__ import annotations

import json
import ssl
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import certifi
import httpx

# API constants
API_BASE = "https://docs.googleapis.com/v1/documents"
DEFAULT_TIMEOUT = 60


class TransportError(Exception):
    """Base exception for transport errors."""


class AuthenticationError(TransportError):
    """Raised when authentication fails (401/403)."""


class NotFoundError(TransportError):
    """Raised when document is not found (404)."""


class APIError(TransportError):
    """Raised when the API returns an error."""

    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class DocumentData:
    """Complete document data from Google Docs API.

    Contains the full API response including document structure,
    content, and styling information.
    """

    document_id: str
    title: str
    raw: dict[str, Any]  # Full API response


class Transport(ABC):
    """Abstract base class for document data transport.

    Implementations must provide methods to fetch document data
    from a document source (Google API, local files, etc.).
    """

    @abstractmethod
    async def get_document(self, document_id: str) -> DocumentData:
        """Fetch complete document data.

        Args:
            document_id: The document identifier

        Returns:
            DocumentData with full document contents
        """
        ...

    @abstractmethod
    async def batch_update(
        self, document_id: str, requests: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Apply batchUpdate requests to a document.

        Args:
            document_id: The document identifier
            requests: List of batchUpdate request objects

        Returns:
            API response containing replies for each request
        """
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close any open connections."""
        ...


class GoogleDocsTransport(Transport):
    """Production transport that fetches data from Google Docs API.

    Handles authentication, SSL, and HTTP communication.
    """

    def __init__(
        self,
        access_token: str,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        """Initialize the transport.

        Args:
            access_token: OAuth2 access token with documents.readonly scope
            timeout: Request timeout in seconds
        """
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        self._client = httpx.AsyncClient(
            timeout=timeout,
            verify=ssl_context,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            },
        )

    async def get_document(self, document_id: str) -> DocumentData:
        """Fetch document data from Google Docs API."""
        url = f"{API_BASE}/{document_id}"
        response = await self._request(url)

        return DocumentData(
            document_id=response.get("documentId", document_id),
            title=response.get("title", ""),
            raw=response,
        )

    async def batch_update(
        self, document_id: str, requests: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Apply batchUpdate requests to Google Docs API."""
        url = f"{API_BASE}/{document_id}:batchUpdate"
        body = {"requests": requests}
        return await self._post_request(url, body)

    async def _request(self, url: str) -> dict[str, Any]:
        """Make an authenticated GET request."""
        try:
            response = await self._client.get(url)
            response.raise_for_status()
            result: dict[str, Any] = response.json()
            return result
        except httpx.HTTPStatusError as e:
            self._handle_http_error(e)
            raise  # unreachable, but makes type checker happy
        except httpx.RequestError as e:
            raise TransportError(f"Network error: {e}") from e

    async def _post_request(self, url: str, body: dict[str, Any]) -> dict[str, Any]:
        """Make an authenticated POST request."""
        try:
            response = await self._client.post(url, json=body)
            response.raise_for_status()
            result: dict[str, Any] = response.json()
            return result
        except httpx.HTTPStatusError as e:
            self._handle_http_error(e)
            raise  # unreachable, but makes type checker happy
        except httpx.RequestError as e:
            raise TransportError(f"Network error: {e}") from e

    def _handle_http_error(self, e: httpx.HTTPStatusError) -> None:
        """Handle HTTP errors and raise appropriate exceptions."""
        status = e.response.status_code
        if status == 401:
            raise AuthenticationError("Invalid or expired access token") from e
        if status == 403:
            raise AuthenticationError(
                "Access denied. Check your scopes and permissions."
            ) from e
        if status == 404:
            raise NotFoundError(
                "Document not found. Check the ID and sharing permissions."
            ) from e
        body = e.response.text
        raise APIError(f"API error ({status}): {body}", status_code=status) from e

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()


class LocalFileTransport(Transport):
    """Test transport that reads from local golden files.

    Supports two directory structures:
    1. Directory format: golden_dir/<document_id>/document.json
    2. Flat file format: golden_dir/<document_id>.json
    """

    def __init__(self, golden_dir: Path) -> None:
        """Initialize the transport.

        Args:
            golden_dir: Directory containing golden test files
        """
        self._golden_dir = golden_dir

    async def get_document(self, document_id: str) -> DocumentData:
        """Read document from local file."""
        # Try directory format first
        dir_path = self._golden_dir / document_id / "document.json"
        if dir_path.exists():
            path = dir_path
        else:
            # Fall back to flat file format
            path = self._golden_dir / f"{document_id}.json"

        response = json.loads(path.read_text())

        return DocumentData(
            document_id=response.get("documentId", document_id),
            title=response.get("title", ""),
            raw=response,
        )

    async def batch_update(
        self, document_id: str, requests: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Mock batch_update for testing - returns empty replies."""
        return {
            "documentId": document_id,
            "replies": [{} for _ in requests],
        }

    async def close(self) -> None:
        """No-op for local file transport."""
        pass
