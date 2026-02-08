"""ScriptsClient - Main API for extrascripts.

Provides pull, push, diff, create, run, logs, deploy, and version commands
for the Google Apps Script workflow.
"""

from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from extrascripts.linter import LintResult, lint_project
from extrascripts.transport import (
    DeploymentInfo,
    ExecutionResult,
    ProcessInfo,
    ScriptFile,
    Transport,
    VersionInfo,
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


class ScriptsClient:
    """Client for managing Google Apps Script projects.

    Example:
        >>> transport = AppsScriptTransport(access_token="ya29...")
        >>> client = ScriptsClient(transport)
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

        await self._transport.update_content(script_id, script_files)

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

    # --- Run ---

    async def run(
        self,
        script_id: str,
        function: str,
        parameters: list[Any] | None = None,
        dev_mode: bool = True,
    ) -> ExecutionResult:
        """Execute a function in the script project.

        Args:
            script_id: The script project ID.
            function: Name of the function to execute.
            parameters: Optional list of arguments (primitives only).
            dev_mode: If True, runs against HEAD code instead of deployment.

        Returns:
            ExecutionResult with return value or error.
        """
        return await self._transport.run_function(
            script_id, function, parameters, dev_mode
        )

    # --- Logs ---

    async def logs(
        self,
        script_id: str | None = None,
        limit: int = 20,
    ) -> list[ProcessInfo]:
        """List recent execution logs.

        Args:
            script_id: If set, show logs for this project only.
            limit: Maximum number of entries to return.

        Returns:
            List of ProcessInfo objects.
        """
        return await self._transport.list_processes(script_id, limit)

    # --- Versions ---

    async def create_version(
        self, script_id: str, description: str | None = None
    ) -> VersionInfo:
        """Create an immutable version snapshot."""
        return await self._transport.create_version(script_id, description)

    async def list_versions(self, script_id: str) -> list[VersionInfo]:
        """List all versions."""
        return await self._transport.list_versions(script_id)

    # --- Deployments ---

    async def create_deployment(
        self,
        script_id: str,
        version_number: int,
        description: str | None = None,
    ) -> DeploymentInfo:
        """Create a deployment pinned to a version."""
        return await self._transport.create_deployment(
            script_id, version_number, description
        )

    async def list_deployments(self, script_id: str) -> list[DeploymentInfo]:
        """List all deployments."""
        return await self._transport.list_deployments(script_id)

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
            "Is this an extrascripts project folder?"
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
