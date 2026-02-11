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
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

import certifi
import httpx

# API constants
API_BASE = "https://docs.googleapis.com/v1/documents"
DRIVE_API_BASE = "https://www.googleapis.com/drive/v3/files"
DEFAULT_TIMEOUT = 60

# Fields to request for comments list
_COMMENTS_FIELDS = (
    "comments(id,content,anchor,author,createdTime,modifiedTime,"
    "resolved,deleted,quotedFileContent,"
    "replies(id,content,author,createdTime,modifiedTime,deleted,action)),"
    "nextPageToken"
)


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
    async def list_comments(self, file_id: str) -> list[dict[str, Any]]:
        """Fetch all comments on a file via Drive API v3.

        Args:
            file_id: The file identifier

        Returns:
            List of comment dicts from the Drive API
        """
        ...

    @abstractmethod
    async def create_comment(
        self,
        file_id: str,
        content: str,
        anchor_json: str | None = None,
    ) -> dict[str, Any]:
        """Create a new comment on a file.

        Args:
            file_id: The file identifier
            content: Comment text
            anchor_json: Optional anchor JSON for positioned comments

        Returns:
            API response with the created comment
        """
        ...

    @abstractmethod
    async def create_reply(
        self,
        file_id: str,
        comment_id: str,
        content: str,
        action: str | None = None,
    ) -> dict[str, Any]:
        """Create a reply on an existing comment.

        Args:
            file_id: The file identifier
            comment_id: The comment to reply to
            content: Reply text
            action: Optional action, e.g. "resolve"

        Returns:
            API response with the created reply
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
        url = f"{API_BASE}/{document_id}?includeTabsContent=true"
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

    async def list_comments(self, file_id: str) -> list[dict[str, Any]]:
        """Fetch all comments via Drive API v3 with pagination."""
        all_comments: list[dict[str, Any]] = []
        page_token: str | None = None
        while True:
            url = (
                f"{DRIVE_API_BASE}/{file_id}/comments"
                f"?fields={_COMMENTS_FIELDS}&pageSize=100"
            )
            if page_token:
                url += f"&pageToken={page_token}"
            response = await self._request(url)
            all_comments.extend(response.get("comments", []))
            page_token = response.get("nextPageToken")
            if not page_token:
                break
        return all_comments

    async def create_comment(
        self,
        file_id: str,
        content: str,
        anchor_json: str | None = None,
    ) -> dict[str, Any]:
        """Create a new comment via Drive API v3."""
        url = f"{DRIVE_API_BASE}/{file_id}/comments?fields=id,content,anchor,author,createdTime"
        body: dict[str, Any] = {"content": content}
        if anchor_json is not None:
            body["anchor"] = anchor_json
        return await self._post_request(url, body)

    async def create_reply(
        self,
        file_id: str,
        comment_id: str,
        content: str,
        action: str | None = None,
    ) -> dict[str, Any]:
        """Create a reply on an existing comment via Drive API v3."""
        url = (
            f"{DRIVE_API_BASE}/{file_id}/comments/{comment_id}/replies"
            f"?fields=id,content,author,createdTime,action"
        )
        body: dict[str, Any] = {"content": content}
        if action is not None:
            body["action"] = action
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

    Expected directory structure:
        golden_dir/
            <document_id>.json
    """

    def __init__(self, golden_dir: Path) -> None:
        """Initialize the transport.

        Args:
            golden_dir: Directory containing golden test files
        """
        self._golden_dir = golden_dir

    async def get_document(self, document_id: str) -> DocumentData:
        """Read document data from local file."""
        path = self._golden_dir / f"{document_id}.json"
        response = json.loads(path.read_text(encoding="utf-8"))

        return DocumentData(
            document_id=response.get("documentId", document_id),
            title=response.get("title", ""),
            raw=response,
        )

    async def batch_update(
        self,
        document_id: str,  # noqa: ARG002
        requests: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Mock batch_update for testing - returns empty replies."""
        return {"replies": [{}] * len(requests)}

    async def list_comments(self, file_id: str) -> list[dict[str, Any]]:
        """Read comments from local golden file."""
        path = self._golden_dir / f"{file_id}_comments.json"
        if not path.exists():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        result: list[dict[str, Any]] = data.get("comments", [])
        return result

    async def create_comment(
        self,
        file_id: str,  # noqa: ARG002
        content: str,
        anchor_json: str | None = None,  # noqa: ARG002
    ) -> dict[str, Any]:
        """Mock create_comment for testing."""
        return {"id": "mock_comment_id", "content": content}

    async def create_reply(
        self,
        file_id: str,  # noqa: ARG002
        comment_id: str,  # noqa: ARG002
        content: str,
        action: str | None = None,
    ) -> dict[str, Any]:
        """Mock create_reply for testing."""
        result: dict[str, Any] = {
            "id": "mock_reply_id",
            "content": content,
        }
        if action:
            result["action"] = action
        return result

    async def close(self) -> None:
        """No-op for local file transport."""
