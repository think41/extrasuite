"""Transport layer for Google Apps Script API.

Defines the Transport protocol and implementations:
- AppsScriptTransport: Production transport using Apps Script API v1
- LocalFileTransport: Test transport reading from local golden files
"""

from __future__ import annotations

import json
import ssl
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import certifi
import httpx

# Apps Script API v1 base URL
API_BASE = "https://script.googleapis.com/v1"
DEFAULT_TIMEOUT = 60


class TransportError(Exception):
    """Base exception for transport errors."""


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


@dataclass(frozen=True)
class ExecutionResult:
    """Result of a script execution via scripts.run."""

    done: bool
    return_value: Any = None
    error: dict[str, Any] | None = None


@dataclass(frozen=True)
class ProcessInfo:
    """Information about a script execution process."""

    function_name: str
    process_status: str
    process_type: str
    start_time: str
    duration: str = ""
    project_name: str = ""


@dataclass(frozen=True)
class VersionInfo:
    """Information about a script version."""

    version_number: int
    description: str = ""
    create_time: str = ""


@dataclass(frozen=True)
class DeploymentInfo:
    """Information about a script deployment."""

    deployment_id: str
    version_number: int
    description: str = ""
    update_time: str = ""
    entry_points: tuple[dict[str, Any], ...] = ()


# --- Transport ABC ---


class Transport(ABC):
    """Abstract base class for Apps Script API transport.

    Implementations must provide methods for managing Apps Script projects.
    """

    @abstractmethod
    async def get_project(self, script_id: str) -> ProjectMetadata:
        """Fetch project metadata."""
        ...

    @abstractmethod
    async def get_content(
        self, script_id: str, version_number: int | None = None
    ) -> ProjectContent:
        """Fetch all files in a project."""
        ...

    @abstractmethod
    async def update_content(
        self, script_id: str, files: list[ScriptFile]
    ) -> ProjectContent:
        """Replace all files in a project (atomic operation)."""
        ...

    @abstractmethod
    async def create_project(
        self, title: str, parent_id: str | None = None
    ) -> ProjectMetadata:
        """Create a new Apps Script project.

        Args:
            title: Project title.
            parent_id: If set, creates a container-bound script attached
                to the Google Drive file with this ID.
        """
        ...

    @abstractmethod
    async def run_function(
        self,
        script_id: str,
        function: str,
        parameters: list[Any] | None = None,
        dev_mode: bool = True,
    ) -> ExecutionResult:
        """Execute a function in the script project."""
        ...

    @abstractmethod
    async def list_processes(
        self,
        script_id: str | None = None,
        limit: int = 20,
    ) -> list[ProcessInfo]:
        """List recent execution processes."""
        ...

    @abstractmethod
    async def create_version(
        self, script_id: str, description: str | None = None
    ) -> VersionInfo:
        """Create an immutable version snapshot."""
        ...

    @abstractmethod
    async def list_versions(self, script_id: str) -> list[VersionInfo]:
        """List all versions of a project."""
        ...

    @abstractmethod
    async def create_deployment(
        self,
        script_id: str,
        version_number: int,
        description: str | None = None,
    ) -> DeploymentInfo:
        """Create a new deployment pinned to a version."""
        ...

    @abstractmethod
    async def list_deployments(self, script_id: str) -> list[DeploymentInfo]:
        """List all deployments of a project."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close any open connections."""
        ...


# --- Production transport ---


class AppsScriptTransport(Transport):
    """Production transport using Google Apps Script API v1."""

    def __init__(
        self,
        access_token: str,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        self._client = httpx.AsyncClient(
            timeout=timeout,
            verify=ssl_context,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            },
        )

    # -- Core project methods --

    async def get_project(self, script_id: str) -> ProjectMetadata:
        url = f"{API_BASE}/projects/{script_id}"
        data = await self._get(url)
        return _parse_project_metadata(data)

    async def get_content(
        self, script_id: str, version_number: int | None = None
    ) -> ProjectContent:
        url = f"{API_BASE}/projects/{script_id}/content"
        if version_number is not None:
            url += f"?versionNumber={version_number}"
        data = await self._get(url)
        return _parse_project_content(script_id, data)

    async def update_content(
        self, script_id: str, files: list[ScriptFile]
    ) -> ProjectContent:
        url = f"{API_BASE}/projects/{script_id}/content"
        body: dict[str, Any] = {
            "files": [
                {"name": f.name, "type": f.type, "source": f.source} for f in files
            ]
        }
        data = await self._put(url, body)
        return _parse_project_content(script_id, data)

    async def create_project(
        self, title: str, parent_id: str | None = None
    ) -> ProjectMetadata:
        url = f"{API_BASE}/projects"
        body: dict[str, str] = {"title": title}
        if parent_id:
            body["parentId"] = parent_id
        data = await self._post(url, body)
        return _parse_project_metadata(data)

    # -- Execution --

    async def run_function(
        self,
        script_id: str,
        function: str,
        parameters: list[Any] | None = None,
        dev_mode: bool = True,
    ) -> ExecutionResult:
        url = f"{API_BASE}/scripts/{script_id}:run"
        body: dict[str, Any] = {"function": function, "devMode": dev_mode}
        if parameters:
            body["parameters"] = parameters
        data = await self._post(url, body)
        return ExecutionResult(
            done=data.get("done", False),
            return_value=data.get("response", {}).get("result"),
            error=data.get("error"),
        )

    # -- Processes / logs --

    async def list_processes(
        self,
        script_id: str | None = None,
        limit: int = 20,
    ) -> list[ProcessInfo]:
        if script_id:
            url = (
                f"{API_BASE}/processes:listScriptProcesses"
                f"?scriptId={script_id}&pageSize={limit}"
            )
        else:
            url = f"{API_BASE}/processes?pageSize={limit}"
        data = await self._get(url)
        return [
            ProcessInfo(
                function_name=p.get("functionName", ""),
                process_status=p.get("processStatus", ""),
                process_type=p.get("processType", ""),
                start_time=p.get("startTime", ""),
                duration=p.get("duration", ""),
                project_name=p.get("projectName", ""),
            )
            for p in data.get("processes", [])
        ]

    # -- Versions --

    async def create_version(
        self, script_id: str, description: str | None = None
    ) -> VersionInfo:
        url = f"{API_BASE}/projects/{script_id}/versions"
        body: dict[str, Any] = {}
        if description:
            body["description"] = description
        data = await self._post(url, body)
        return VersionInfo(
            version_number=data.get("versionNumber", 0),
            description=data.get("description", ""),
            create_time=data.get("createTime", ""),
        )

    async def list_versions(self, script_id: str) -> list[VersionInfo]:
        url = f"{API_BASE}/projects/{script_id}/versions"
        data = await self._get(url)
        return [
            VersionInfo(
                version_number=v.get("versionNumber", 0),
                description=v.get("description", ""),
                create_time=v.get("createTime", ""),
            )
            for v in data.get("versions", [])
        ]

    # -- Deployments --

    async def create_deployment(
        self,
        script_id: str,
        version_number: int,
        description: str | None = None,
    ) -> DeploymentInfo:
        url = f"{API_BASE}/projects/{script_id}/deployments"
        config: dict[str, Any] = {
            "scriptId": script_id,
            "versionNumber": version_number,
        }
        if description:
            config["description"] = description
        body = {"deploymentConfig": config}
        data = await self._post(url, body)
        dc = data.get("deploymentConfig", {})
        return DeploymentInfo(
            deployment_id=data.get("deploymentId", ""),
            version_number=dc.get("versionNumber", 0),
            description=dc.get("description", ""),
            update_time=data.get("updateTime", ""),
            entry_points=tuple(data.get("entryPoints", [])),
        )

    async def list_deployments(self, script_id: str) -> list[DeploymentInfo]:
        url = f"{API_BASE}/projects/{script_id}/deployments"
        data = await self._get(url)
        results: list[DeploymentInfo] = []
        for d in data.get("deployments", []):
            dc = d.get("deploymentConfig", {})
            results.append(
                DeploymentInfo(
                    deployment_id=d.get("deploymentId", ""),
                    version_number=dc.get("versionNumber", 0),
                    description=dc.get("description", ""),
                    update_time=d.get("updateTime", ""),
                    entry_points=tuple(d.get("entryPoints", [])),
                )
            )
        return results

    async def close(self) -> None:
        await self._client.aclose()

    # -- HTTP helpers --

    async def _get(self, url: str) -> dict[str, Any]:
        try:
            resp = await self._client.get(url)
            resp.raise_for_status()
            result: dict[str, Any] = resp.json()
            return result
        except httpx.HTTPStatusError as e:
            self._handle_http_error(e)
            raise
        except httpx.RequestError as e:
            raise TransportError(f"Network error: {e}") from e

    async def _post(self, url: str, body: dict[str, Any]) -> dict[str, Any]:
        try:
            resp = await self._client.post(url, json=body)
            resp.raise_for_status()
            result: dict[str, Any] = resp.json()
            return result
        except httpx.HTTPStatusError as e:
            self._handle_http_error(e)
            raise
        except httpx.RequestError as e:
            raise TransportError(f"Network error: {e}") from e

    async def _put(self, url: str, body: dict[str, Any]) -> dict[str, Any]:
        try:
            resp = await self._client.put(url, json=body)
            resp.raise_for_status()
            result: dict[str, Any] = resp.json()
            return result
        except httpx.HTTPStatusError as e:
            self._handle_http_error(e)
            raise
        except httpx.RequestError as e:
            raise TransportError(f"Network error: {e}") from e

    def _handle_http_error(self, e: httpx.HTTPStatusError) -> None:
        status = e.response.status_code
        if status == 401:
            raise AuthenticationError("Invalid or expired access token") from e
        if status == 403:
            raise AuthenticationError(
                "Access denied. The Apps Script API requires user OAuth tokens "
                "(service accounts are not supported). Check your scopes."
            ) from e
        if status == 404:
            raise NotFoundError(
                "Script project not found. Check the script ID and permissions."
            ) from e
        body = e.response.text
        raise APIError(f"API error ({status}): {body}", status_code=status) from e


# --- Test transport ---


class LocalFileTransport(Transport):
    """Test transport that reads from local golden files.

    Expected directory structure:
        golden_dir/
            <script_id>/
                content.json     # Raw getContent response
                project.json     # Raw get project response (optional)
    """

    def __init__(self, golden_dir: Path) -> None:
        self._golden_dir = golden_dir

    async def get_project(self, script_id: str) -> ProjectMetadata:
        path = self._golden_dir / script_id / "project.json"
        if path.exists():
            data = json.loads(path.read_text())
            return _parse_project_metadata(data)
        # Fallback: derive metadata from content.json
        await self.get_content(script_id)
        return ProjectMetadata(
            script_id=script_id,
            title=script_id,
            raw={"scriptId": script_id, "title": script_id},
        )

    async def get_content(
        self, script_id: str, version_number: int | None = None
    ) -> ProjectContent:
        path = self._golden_dir / script_id / "content.json"
        data = json.loads(path.read_text())
        return _parse_project_content(script_id, data)

    async def update_content(
        self, script_id: str, files: list[ScriptFile]
    ) -> ProjectContent:
        return ProjectContent(
            script_id=script_id,
            files=tuple(files),
            raw={"scriptId": script_id, "files": []},
        )

    async def create_project(
        self, title: str, parent_id: str | None = None
    ) -> ProjectMetadata:
        return ProjectMetadata(
            script_id="mock_script_id",
            title=title,
            parent_id=parent_id or "",
            raw={"scriptId": "mock_script_id", "title": title},
        )

    async def run_function(
        self,
        script_id: str,
        function: str,
        parameters: list[Any] | None = None,
        dev_mode: bool = True,
    ) -> ExecutionResult:
        return ExecutionResult(done=True, return_value=None)

    async def list_processes(
        self,
        script_id: str | None = None,
        limit: int = 20,
    ) -> list[ProcessInfo]:
        return []

    async def create_version(
        self, script_id: str, description: str | None = None
    ) -> VersionInfo:
        return VersionInfo(version_number=1, description=description or "")

    async def list_versions(self, script_id: str) -> list[VersionInfo]:
        return []

    async def create_deployment(
        self,
        script_id: str,
        version_number: int,
        description: str | None = None,
    ) -> DeploymentInfo:
        return DeploymentInfo(
            deployment_id="mock_deployment_id",
            version_number=version_number,
            description=description or "",
        )

    async def list_deployments(self, script_id: str) -> list[DeploymentInfo]:
        return []

    async def close(self) -> None:
        pass


# --- Helpers ---


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
