"""ScriptClient - Main API for extrascript.

Provides pull, push, diff, create, and store_script_metadata commands
for the Google Apps Script workflow. Uses a Transport abstraction for
API communication.
"""

from __future__ import annotations

import json
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from extrascript.linter import LintResult, lint_project
from extrascript.transport import (
    APIError,  # noqa: F401 (re-export for backward compat)
    AuthenticationError,  # noqa: F401 (re-export for backward compat)
    NotFoundError,  # noqa: F401 (re-export for backward compat)
    ProjectContent,  # noqa: F401 (re-export for backward compat)
    ProjectMetadata,  # noqa: F401 (re-export for backward compat)
    ScriptAPIError,  # noqa: F401 (re-export for backward compat)
    ScriptFile,
    Transport,
    TransportError,  # noqa: F401 (re-export for backward compat)
    _parse_project_content,  # noqa: F401 (re-export for backward compat)
    _parse_project_metadata,  # noqa: F401 (re-export for backward compat)
)

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


# --- Data classes (client-specific) ---


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


# --- Client ---


class ScriptClient:
    """Client for managing Google Apps Script projects.

    Uses a Transport for all API communication.

    Example:
        >>> from extrascript.transport import GoogleAppsScriptTransport
        >>> transport = GoogleAppsScriptTransport(access_token="ya29...")
        >>> client = ScriptClient(transport)
        >>> await client.pull("1abc...", Path("./output"))
    """

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

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
        metadata = await self._transport.get_project(script_id)
        content = await self._transport.get_content(script_id)

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

        # Convert ScriptFile objects to dicts for transport
        file_dicts: list[dict[str, Any]] = [
            {"name": f.name, "type": f.type, "source": f.source} for f in script_files
        ]
        await self._transport.update_content(script_id, file_dicts)

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
        metadata = await self._transport.create_project(title, parent_id)
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
        await self._transport.store_script_metadata(parent_id, script_id)

    # --- Lint ---

    def lint(self, folder: str | Path) -> LintResult:
        """Run lint checks on script files in the folder.

        Args:
            folder: Path to the project folder.

        Returns:
            LintResult with diagnostics.
        """
        return lint_project(Path(folder))


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


# --- URL parsing helpers ---


def parse_script_id(id_or_url: str) -> str:
    """Extract script ID from a URL or return as-is.

    Supports URLs like:
      https://script.google.com/d/SCRIPT_ID/edit
      https://script.google.com/home/projects/SCRIPT_ID/edit
    """
    patterns = [
        r"script\.google\.com/d/([a-zA-Z0-9_-]+)",
        r"script\.google\.com/home/projects/([a-zA-Z0-9_-]+)",
        r"script\.google\.com/macros/d/([a-zA-Z0-9_-]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, id_or_url)
        if match:
            return match.group(1)
    return id_or_url


def parse_file_id(id_or_url: str) -> str:
    """Extract Google Drive file ID from a URL or return as-is.

    Supports Sheets, Docs, Slides, and Forms URLs.
    """
    patterns = [
        r"docs\.google\.com/spreadsheets/d/([a-zA-Z0-9_-]+)",
        r"docs\.google\.com/document/d/([a-zA-Z0-9_-]+)",
        r"docs\.google\.com/presentation/d/([a-zA-Z0-9_-]+)",
        r"docs\.google\.com/forms/d/([a-zA-Z0-9_-]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, id_or_url)
        if match:
            return match.group(1)
    return id_or_url
