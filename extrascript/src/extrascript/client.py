"""ScriptClient - Main API for extrascript.

Provides pull, push, diff, create, and store_script_metadata commands
for the Google Apps Script workflow. API calls are made directly via
httpx.AsyncClient (no transport abstraction).
"""

from __future__ import annotations

import json
import ssl
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import certifi
import httpx

from extrascript.linter import LintResult, lint_project

# Apps Script API v1 base URL
API_BASE = "https://script.googleapis.com/v1"
SHEETS_API_BASE = "https://sheets.googleapis.com/v4"
DEFAULT_TIMEOUT = 60

# Maps Apps Script file types to local file extensions
FILE_TYPE_TO_EXT: dict[str, str] = {
    "SERVER_JS": ".gs",
    "HTML": ".html",
    "JSON": ".json",
}

# Reverse mapping: extension to Apps Script file type
EXT_TO_FILE_TYPE: dict[str, str] = {
    ".gs": "SERVER_JS",
    ".html": "HTML",
    ".json": "JSON",
}


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


@dataclass
class DiffResult:
    """Result of comparing current files against pristine."""

    script_id: str
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.removed or self.modified)


@dataclass
class PushResult:
    """Result of a push operation."""

    success: bool
    message: str
    script_id: str
    files_pushed: int = 0


# --- Errors ---


class ScriptAPIError(Exception):
    """Base exception for Apps Script API errors."""


class AuthenticationError(ScriptAPIError):
    """Raised when authentication fails (401/403)."""


class NotFoundError(ScriptAPIError):
    """Raised when a script project is not found (404)."""


class APIError(ScriptAPIError):
    """Raised when the API returns an error."""

    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


# --- Client ---


class ScriptClient:
    """Client for managing Google Apps Script projects.

    Makes API calls directly via httpx.AsyncClient.

    Example:
        >>> client = ScriptClient(access_token="ya29...")
        >>> await client.pull("1abc...", Path("./output"))
    """

    def __init__(self, access_token: str) -> None:
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        self._client = httpx.AsyncClient(
            timeout=DEFAULT_TIMEOUT,
            verify=ssl_context,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            },
        )

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    # --- Pull ---

    async def pull(
        self,
        script_id: str,
        output_path: str | Path,
        *,
        save_raw: bool = True,
    ) -> list[Path]:
        """Pull an Apps Script project to local files.

        Creates a folder with the script files, a project.json metadata
        file, and a .pristine/ snapshot for diff/push.

        On-disk layout:
            <script_id>/
                project.json        # Metadata
                appsscript.json     # Manifest
                Code.gs             # SERVER_JS files
                Page.html           # HTML files
                .pristine/project.zip
                .raw/content.json

        Args:
            script_id: The script project ID.
            output_path: Parent directory for the project folder.
            save_raw: If True, saves raw API responses.

        Returns:
            List of paths to written files.
        """
        output_path = Path(output_path)
        project_dir = output_path / script_id

        # Fetch metadata and content
        metadata = await self._get_project(script_id)
        content = await self._get_content(script_id)

        written: list[Path] = []

        # Write project.json (metadata)
        project_json_path = project_dir / "project.json"
        project_json_path.parent.mkdir(parents=True, exist_ok=True)
        meta_dict = {
            "scriptId": metadata.script_id,
            "title": metadata.title,
            "parentId": metadata.parent_id,
            "createTime": metadata.create_time,
            "updateTime": metadata.update_time,
        }
        project_json_path.write_text(json.dumps(meta_dict, indent=2) + "\n")
        written.append(project_json_path)

        # Write each script file with its proper extension
        for sf in content.files:
            ext = FILE_TYPE_TO_EXT.get(sf.type, ".txt")
            filename = sf.name + ext
            file_path = project_dir / filename
            file_path.write_text(sf.source)
            written.append(file_path)

        # Save raw API responses
        if save_raw:
            raw_dir = project_dir / ".raw"
            raw_dir.mkdir(parents=True, exist_ok=True)

            content_raw_path = raw_dir / "content.json"
            content_raw_path.write_text(json.dumps(content.raw, indent=2) + "\n")
            written.append(content_raw_path)

            project_raw_path = raw_dir / "project.json"
            project_raw_path.write_text(json.dumps(metadata.raw, indent=2) + "\n")
            written.append(project_raw_path)

        # Create pristine copy for diff/push
        pristine_path = self._create_pristine(project_dir, written)
        written.append(pristine_path)

        return written

    def _create_pristine(self, project_dir: Path, written_files: list[Path]) -> Path:
        """Create a .pristine/project.zip snapshot of current state."""
        pristine_dir = project_dir / ".pristine"
        pristine_dir.mkdir(parents=True, exist_ok=True)
        zip_path = pristine_dir / "project.zip"

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in written_files:
                if ".raw" in file_path.parts or ".pristine" in file_path.parts:
                    continue
                arcname = file_path.relative_to(project_dir)
                zf.write(file_path, arcname)

        return zip_path

    # --- Diff ---

    def diff(self, folder: str | Path) -> DiffResult:
        """Compare current files against pristine snapshot.

        This is a local-only operation (no API calls).

        Args:
            folder: Path to the project folder (containing project.json).

        Returns:
            DiffResult showing added, removed, modified, and unchanged files.
        """
        folder = Path(folder)
        script_id = _read_script_id(folder)
        pristine_files = _read_pristine_files(folder)
        current_files = _read_current_files(folder)

        result = DiffResult(script_id=script_id)

        all_names = set(pristine_files.keys()) | set(current_files.keys())
        for name in sorted(all_names):
            if name not in pristine_files:
                result.added.append(name)
            elif name not in current_files:
                result.removed.append(name)
            elif pristine_files[name] != current_files[name]:
                result.modified.append(name)
            else:
                result.unchanged.append(name)

        return result

    # --- Push ---

    async def push(self, folder: str | Path) -> PushResult:
        """Push local files to the Apps Script project.

        Reads all script files from the folder and replaces the entire
        project content via updateContent (atomic operation).

        Args:
            folder: Path to the project folder.

        Returns:
            PushResult with success status.
        """
        folder = Path(folder)
        script_id = _read_script_id(folder)
        current_files = _read_current_files(folder)

        if not current_files:
            return PushResult(
                success=False,
                message="No script files found in folder",
                script_id=script_id,
            )

        # Build ScriptFile list for the API
        script_files = _files_dict_to_script_files(current_files)

        # Verify manifest exists
        has_manifest = any(
            f.name == "appsscript" and f.type == "JSON" for f in script_files
        )
        if not has_manifest:
            return PushResult(
                success=False,
                message="Missing appsscript.json manifest. "
                "Every Apps Script project requires this file.",
                script_id=script_id,
            )

        await self._update_content(script_id, script_files)

        # Update pristine to match current state
        self._update_pristine_after_push(folder, current_files)

        return PushResult(
            success=True,
            message=f"Pushed {len(script_files)} files",
            script_id=script_id,
            files_pushed=len(script_files),
        )

    def _update_pristine_after_push(
        self, folder: Path, current_files: dict[str, str]
    ) -> None:
        """Update .pristine/project.zip to match the pushed state."""
        pristine_dir = folder / ".pristine"
        pristine_dir.mkdir(parents=True, exist_ok=True)
        zip_path = pristine_dir / "project.zip"

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            # Include project.json
            project_json = folder / "project.json"
            if project_json.exists():
                zf.write(project_json, "project.json")
            # Include all script files
            for filename, content in current_files.items():
                zf.writestr(filename, content)

    # --- Create ---

    async def create(
        self,
        title: str,
        output_path: str | Path,
        *,
        parent_id: str | None = None,
    ) -> list[Path]:
        """Create a new Apps Script project and pull it locally.

        Args:
            title: Project title.
            output_path: Parent directory for the project folder.
            parent_id: If set, creates a bound script attached to this
                Google Drive file (Sheets, Docs, Slides, or Forms).

        Returns:
            List of paths to written files.
        """
        metadata = await self._create_project(title, parent_id)
        return await self.pull(metadata.script_id, output_path)

    # --- Developer Metadata ---

    async def store_script_metadata(self, parent_id: str, script_id: str) -> None:
        """Store script ID as developer metadata on the parent spreadsheet.

        This uses the Google Sheets API to store the script_id as
        developer metadata, allowing other tools (e.g. extrasheet) to
        discover the associated script when they pull the spreadsheet.

        Args:
            parent_id: The spreadsheet ID.
            script_id: The Apps Script project ID to store.
        """
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

    # --- Lint ---

    def lint(self, folder: str | Path) -> LintResult:
        """Run lint checks on script files in the folder.

        Args:
            folder: Path to the project folder.

        Returns:
            LintResult with diagnostics.
        """
        return lint_project(Path(folder))

    # --- Private API methods ---

    async def _get_project(self, script_id: str) -> ProjectMetadata:
        """Fetch project metadata from Apps Script API."""
        url = f"{API_BASE}/projects/{script_id}"
        data = await self._get(url)
        return _parse_project_metadata(data)

    async def _get_content(self, script_id: str) -> ProjectContent:
        """Fetch all files in a project from Apps Script API."""
        url = f"{API_BASE}/projects/{script_id}/content"
        data = await self._get(url)
        return _parse_project_content(script_id, data)

    async def _update_content(
        self, script_id: str, files: list[ScriptFile]
    ) -> ProjectContent:
        """Replace all files in a project (atomic operation)."""
        url = f"{API_BASE}/projects/{script_id}/content"
        body: dict[str, Any] = {
            "files": [
                {"name": f.name, "type": f.type, "source": f.source} for f in files
            ]
        }
        data = await self._put(url, body)
        return _parse_project_content(script_id, data)

    async def _create_project(
        self, title: str, parent_id: str | None = None
    ) -> ProjectMetadata:
        """Create a new Apps Script project via API."""
        url = f"{API_BASE}/projects"
        body: dict[str, str] = {"title": title}
        if parent_id:
            body["parentId"] = parent_id
        data = await self._post(url, body)
        return _parse_project_metadata(data)

    # --- HTTP helpers ---

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
            raise ScriptAPIError(f"Network error: {e}") from e

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
            raise ScriptAPIError(f"Network error: {e}") from e

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
            raise ScriptAPIError(f"Network error: {e}") from e

    def _handle_http_error(self, e: httpx.HTTPStatusError) -> None:
        status = e.response.status_code
        if status == 401:
            raise AuthenticationError("Invalid or expired access token") from e
        if status == 403:
            body = e.response.text
            raise AuthenticationError(
                f"Access denied (403): {body}. "
                "The Apps Script API requires user OAuth tokens "
                "(service accounts are not supported). Check your scopes."
            ) from e
        if status == 404:
            raise NotFoundError(
                "Script project not found. Check the script ID and permissions."
            ) from e
        body = e.response.text
        raise APIError(f"API error ({status}): {body}", status_code=status) from e


# --- Module-level helpers ---


def _read_script_id(folder: Path) -> str:
    """Read scriptId from project.json."""
    project_json = folder / "project.json"
    if not project_json.exists():
        raise FileNotFoundError(
            f"project.json not found in {folder}. "
            "Is this an extrascript project folder?"
        )
    data = json.loads(project_json.read_text())
    script_id: str = data.get("scriptId", "")
    if not script_id:
        raise ValueError("scriptId missing from project.json")
    return script_id


def _read_pristine_files(folder: Path) -> dict[str, str]:
    """Read file contents from .pristine/project.zip.

    Returns:
        Dict mapping filename -> content (excludes project.json).
    """
    zip_path = folder / ".pristine" / "project.zip"
    if not zip_path.exists():
        raise FileNotFoundError(
            f"Pristine snapshot not found: {zip_path}. Run 'pull' first."
        )

    files: dict[str, str] = {}
    with zipfile.ZipFile(zip_path, "r") as zf:
        for name in zf.namelist():
            if name.endswith("/") or name == "project.json":
                continue
            files[name] = zf.read(name).decode("utf-8")
    return files


def _read_current_files(folder: Path) -> dict[str, str]:
    """Read current script files from the project folder.

    Returns:
        Dict mapping filename -> content. Excludes project.json,
        .pristine/, and .raw/ directories.
    """
    files: dict[str, str] = {}
    for path in sorted(folder.iterdir()):
        if path.name.startswith(".") or path.name == "project.json":
            continue
        if path.is_file() and path.suffix in EXT_TO_FILE_TYPE:
            files[path.name] = path.read_text()
    return files


def _files_dict_to_script_files(files: dict[str, str]) -> list[ScriptFile]:
    """Convert filename->content dict to list of ScriptFile objects."""
    result: list[ScriptFile] = []
    for filename, content in files.items():
        stem = Path(filename).stem
        ext = Path(filename).suffix
        file_type = EXT_TO_FILE_TYPE.get(ext, "SERVER_JS")
        result.append(ScriptFile(name=stem, type=file_type, source=content))
    return result


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
