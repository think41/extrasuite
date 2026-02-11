"""Transport layer for fetching Apps Script project data.

Defines the Transport protocol and implementations:
- GoogleAppsScriptTransport: Production transport using Google Apps Script API
- LocalFileTransport: Test transport reading from local golden files
"""

from __future__ import annotations

import json
import ssl
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import certifi
import httpx

if TYPE_CHECKING:
    from pathlib import Path

# API constants
API_BASE = "https://script.googleapis.com/v1"
SHEETS_API_BASE = "https://sheets.googleapis.com/v4"
DEFAULT_TIMEOUT = 60


# --- Exceptions ---


class TransportError(Exception):
    """Base exception for transport errors."""


# Backward-compatible alias
ScriptAPIError = TransportError


class AuthenticationError(TransportError):
    """Raised when authentication fails (401/403)."""


class NotFoundError(TransportError):
    """Raised when a script project is not found (404)."""


class APIError(TransportError):
    """Raised when the API returns an error."""

    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


# --- Data classes ---


@dataclass(frozen=True)
class ScriptFile:
    """A single file within an Apps Script project."""

    name: str
    type: str  # SERVER_JS, HTML, or JSON
    source: str
    create_time: str = ""
    update_time: str = ""


@dataclass(frozen=True)
class ProjectMetadata:
    """Metadata about an Apps Script project."""

    script_id: str
    title: str
    parent_id: str = ""  # Non-empty for bound scripts
    create_time: str = ""
    update_time: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProjectContent:
    """Content of an Apps Script project (all files)."""

    script_id: str
    files: tuple[ScriptFile, ...]
    raw: dict[str, Any] = field(default_factory=dict)


# --- Abstract Transport ---


class Transport(ABC):
    """Abstract base class for Apps Script data transport.

    Implementations must provide methods to fetch project metadata and content,
    update content, create projects, and manage script metadata.
    """

    @abstractmethod
    async def get_project(self, script_id: str) -> ProjectMetadata:
        """Fetch project metadata.

        Args:
            script_id: The Apps Script project identifier.

        Returns:
            ProjectMetadata with project info.
        """
        ...

    @abstractmethod
    async def get_content(self, script_id: str) -> ProjectContent:
        """Fetch all files in a project.

        Args:
            script_id: The Apps Script project identifier.

        Returns:
            ProjectContent with all script files.
        """
        ...

    @abstractmethod
    async def update_content(
        self, script_id: str, files: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Replace all files in a project (atomic operation).

        Args:
            script_id: The Apps Script project identifier.
            files: List of file dicts with name, type, source keys.

        Returns:
            Raw API response dict.
        """
        ...

    @abstractmethod
    async def create_project(
        self, title: str, parent_id: str | None = None
    ) -> ProjectMetadata:
        """Create a new Apps Script project.

        Args:
            title: Project title.
            parent_id: Optional Google Drive file ID to bind the script to.

        Returns:
            ProjectMetadata for the newly created project.
        """
        ...

    @abstractmethod
    async def store_script_metadata(self, parent_id: str, script_id: str) -> None:
        """Store script ID as developer metadata on the parent spreadsheet.

        Args:
            parent_id: The spreadsheet ID.
            script_id: The Apps Script project ID to store.
        """
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close any open connections."""
        ...


# --- Parsing helpers ---


def _parse_project_metadata(data: dict[str, Any]) -> ProjectMetadata:
    return ProjectMetadata(
        script_id=data.get("scriptId", ""),
        title=data.get("title", ""),
        parent_id=data.get("parentId", ""),
        create_time=data.get("createTime", ""),
        update_time=data.get("updateTime", ""),
        raw=data,
    )


def _parse_project_content(script_id: str, data: dict[str, Any]) -> ProjectContent:
    files: list[ScriptFile] = []
    for f in data.get("files", []):
        files.append(
            ScriptFile(
                name=f.get("name", ""),
                type=f.get("type", "SERVER_JS"),
                source=f.get("source", ""),
                create_time=f.get("createTime", ""),
                update_time=f.get("updateTime", ""),
            )
        )
    return ProjectContent(
        script_id=data.get("scriptId", script_id),
        files=tuple(files),
        raw=data,
    )


# --- Google Apps Script Transport ---


class GoogleAppsScriptTransport(Transport):
    """Production transport that fetches data from Google Apps Script API.

    Handles authentication, SSL, and HTTP communication.
    """

    def __init__(
        self,
        access_token: str,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        """Initialize the transport.

        Args:
            access_token: OAuth2 access token with script.projects scope.
            timeout: Request timeout in seconds.
        """
        self._access_token = access_token
        self._timeout = timeout
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        self._client = httpx.AsyncClient(
            timeout=timeout,
            verify=ssl_context,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            },
        )

    async def get_project(self, script_id: str) -> ProjectMetadata:
        """Fetch project metadata from Apps Script API."""
        url = f"{API_BASE}/projects/{script_id}"
        data = await self._get(url)
        return _parse_project_metadata(data)

    async def get_content(self, script_id: str) -> ProjectContent:
        """Fetch all files in a project from Apps Script API."""
        url = f"{API_BASE}/projects/{script_id}/content"
        data = await self._get(url)
        return _parse_project_content(script_id, data)

    async def update_content(
        self, script_id: str, files: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Replace all files in a project (atomic operation)."""
        url = f"{API_BASE}/projects/{script_id}/content"
        body: dict[str, Any] = {"files": files}
        data = await self._put(url, body)
        return data

    async def create_project(
        self, title: str, parent_id: str | None = None
    ) -> ProjectMetadata:
        """Create a new Apps Script project via API."""
        url = f"{API_BASE}/projects"
        body: dict[str, str] = {"title": title}
        if parent_id:
            body["parentId"] = parent_id
        data = await self._post(url, body)
        return _parse_project_metadata(data)

    async def store_script_metadata(self, parent_id: str, script_id: str) -> None:
        """Store script ID as developer metadata on the parent spreadsheet."""
        url = f"{SHEETS_API_BASE}/spreadsheets/{parent_id}:batchUpdate"
        body: dict[str, Any] = {
            "requests": [
                {
                    "createDeveloperMetadata": {
                        "developerMetadata": {
                            "metadataKey": "extrascript.scriptId",
                            "metadataValue": script_id,
                            "location": {"spreadsheet": True},
                            "visibility": "PROJECT",
                        }
                    }
                }
            ]
        }
        await self._post(url, body)

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    # --- HTTP helpers ---

    async def _get(self, url: str) -> dict[str, Any]:
        try:
            resp = await self._client.get(url)
            resp.raise_for_status()
            result: dict[str, Any] = resp.json()
            return result
        except httpx.HTTPStatusError as e:
            raise self._handle_http_error(e) from e
        except httpx.RequestError as e:
            raise TransportError(f"Network error: {e}") from e

    async def _post(self, url: str, body: dict[str, Any]) -> dict[str, Any]:
        try:
            resp = await self._client.post(url, json=body)
            resp.raise_for_status()
            result: dict[str, Any] = resp.json()
            return result
        except httpx.HTTPStatusError as e:
            raise self._handle_http_error(e) from e
        except httpx.RequestError as e:
            raise TransportError(f"Network error: {e}") from e

    async def _put(self, url: str, body: dict[str, Any]) -> dict[str, Any]:
        try:
            resp = await self._client.put(url, json=body)
            resp.raise_for_status()
            result: dict[str, Any] = resp.json()
            return result
        except httpx.HTTPStatusError as e:
            raise self._handle_http_error(e) from e
        except httpx.RequestError as e:
            raise TransportError(f"Network error: {e}") from e

    def _handle_http_error(self, e: httpx.HTTPStatusError) -> TransportError:
        """Convert HTTP errors to appropriate transport exceptions."""
        status = e.response.status_code
        if status == 401:
            return AuthenticationError("Invalid or expired access token")
        if status == 403:
            body = e.response.text
            return AuthenticationError(
                f"Access denied (403): {body}. "
                "The Apps Script API requires user OAuth tokens "
                "(service accounts are not supported). Check your scopes."
            )
        if status == 404:
            return NotFoundError(
                "Script project not found. Check the script ID and permissions."
            )
        body = e.response.text
        return APIError(f"API error ({status}): {body}", status_code=status)


# --- Local File Transport ---


class LocalFileTransport(Transport):
    """Test transport that reads from local golden files.

    Expected directory structure:
        golden_dir/
            project.json     # Project metadata
            content.json     # Project content (files)
    """

    def __init__(self, golden_dir: Path) -> None:
        """Initialize the transport.

        Args:
            golden_dir: Directory containing golden test files.
        """
        self._golden_dir = golden_dir
        self._update_calls: list[dict[str, Any]] = []

    async def get_project(self, script_id: str) -> ProjectMetadata:  # noqa: ARG002
        """Read project metadata from local file."""
        path = self._golden_dir / "project.json"
        if not path.exists():
            raise NotFoundError(f"Golden file not found: {path}")
        data = json.loads(path.read_text())
        return _parse_project_metadata(data)

    async def get_content(self, script_id: str) -> ProjectContent:
        """Read project content from local file."""
        path = self._golden_dir / "content.json"
        if not path.exists():
            raise NotFoundError(f"Golden file not found: {path}")
        data = json.loads(path.read_text())
        return _parse_project_content(script_id, data)

    async def update_content(
        self, script_id: str, files: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Record update call and return mock response."""
        self._update_calls.append({"script_id": script_id, "files": files})
        return {"scriptId": script_id, "files": files}

    async def create_project(
        self, title: str, parent_id: str | None = None
    ) -> ProjectMetadata:
        """Return mock ProjectMetadata."""
        return ProjectMetadata(
            script_id="mock_script_id",
            title=title,
            parent_id=parent_id or "",
            raw={"scriptId": "mock_script_id", "title": title},
        )

    async def store_script_metadata(self, parent_id: str, script_id: str) -> None:
        """No-op for local file transport."""

    async def close(self) -> None:
        """No-op for local file transport."""

    @property
    def update_calls(self) -> list[dict[str, Any]]:
        """Get recorded update calls (for test assertions)."""
        return self._update_calls
