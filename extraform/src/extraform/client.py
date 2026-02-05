"""Main client for ExtraForm operations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from extraform.diff import DiffResult, diff_forms
from extraform.file_reader import read_current_files, read_form_json
from extraform.pristine import create_pristine, get_pristine_form, update_pristine
from extraform.request_generator import generate_requests
from extraform.transformer import FormTransformer
from extraform.transport import FormTransport
from extraform.writer import FileWriter


@dataclass
class PullResult:
    """Result of a pull operation."""

    form_id: str
    files_written: list[Path]
    truncated: bool = False
    responses_count: int = 0


@dataclass
class PushResult:
    """Result of a push operation."""

    success: bool
    changes_applied: int
    message: str
    form_id: str
    response: dict[str, Any] | None = None


class FormsClient:
    """Main client for ExtraForm operations."""

    def __init__(self, transport: FormTransport) -> None:
        """Initialize the client with a transport.

        Args:
            transport: The transport to use for API operations.
        """
        self._transport = transport

    async def pull(
        self,
        form_id: str,
        output_dir: Path,
        include_responses: bool = False,
        max_responses: int = 100,
        save_raw: bool = True,
    ) -> PullResult:
        """Download form to local folder.

        Args:
            form_id: Google Form ID.
            output_dir: Where to write files (form folder will be created inside).
            include_responses: Whether to fetch and save responses.
            max_responses: Maximum number of responses to fetch.
            save_raw: Whether to save raw API responses in .raw folder.

        Returns:
            PullResult with details of the operation.
        """
        # 1. Fetch form structure
        form_data = await self._transport.get_form(form_id)

        # 2. Optionally fetch responses
        responses_data = None
        responses_count = 0
        if include_responses:
            responses_data = await self._transport.get_responses(form_id, page_size=max_responses)
            responses_count = len(responses_data.get("responses", []))

        # 3. Transform to file format
        transformer = FormTransformer(form_data, responses_data)
        files = transformer.transform()

        # 4. Write files
        form_folder = output_dir / form_id
        writer = FileWriter(form_folder)
        written = writer.write_all(files)

        # 5. Save raw API responses
        if save_raw:
            writer.write_raw("form.json", form_data)
            if responses_data:
                writer.write_raw("responses.json", responses_data)

        # 6. Create pristine copy
        create_pristine(form_folder, files)

        return PullResult(
            form_id=form_id,
            files_written=written,
            responses_count=responses_count,
        )

    def diff(self, folder: Path) -> tuple[DiffResult, list[dict[str, Any]]]:
        """Compare current files against pristine and generate batchUpdate requests.

        This is a local-only operation that doesn't call any APIs.

        Args:
            folder: The form folder to diff.

        Returns:
            Tuple of (DiffResult, list of batchUpdate requests).
        """
        # 1. Get pristine form
        pristine_form = get_pristine_form(folder)

        # 2. Read current form
        current_form = read_form_json(folder)

        # 3. Diff
        diff_result = diff_forms(pristine_form, current_form)

        # 4. Generate requests
        requests = generate_requests(diff_result)

        return diff_result, requests

    async def push(self, folder: Path, force: bool = False) -> PushResult:  # noqa: ARG002
        """Apply changes to Google Form.

        Args:
            folder: The form folder containing edited files.
            force: If True, push even with warnings (not currently used).

        Returns:
            PushResult with details of the operation.
        """
        # 1. Run diff
        diff_result, requests = self.diff(folder)

        if not requests:
            return PushResult(
                success=True,
                changes_applied=0,
                message="No changes to push",
                form_id=diff_result.form_id,
            )

        # 2. Execute batchUpdate
        response = await self._transport.batch_update(
            diff_result.form_id,
            requests,
            include_form_in_response=True,
        )

        # 3. Update pristine copy to match current state
        current_files = read_current_files(folder)
        update_pristine(folder, current_files)

        return PushResult(
            success=True,
            changes_applied=len(requests),
            message=f"Applied {len(requests)} change(s)",
            form_id=diff_result.form_id,
            response=response,
        )
