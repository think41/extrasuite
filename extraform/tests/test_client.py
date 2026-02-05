"""Tests for the FormsClient."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from extraform.client import FormsClient, PullResult, PushResult
from extraform.transport import LocalFileTransport


class MockTransport(LocalFileTransport):
    """Mock transport for testing."""

    def __init__(self, form_data: dict[str, Any]) -> None:
        super().__init__(Path("."))
        self._form_data = form_data
        self._batch_update_calls: list[list[dict[str, Any]]] = []

    async def get_form(self, form_id: str) -> dict[str, Any]:  # noqa: ARG002
        return self._form_data

    async def get_responses(
        self,
        form_id: str,  # noqa: ARG002
        page_size: int = 100,  # noqa: ARG002
        page_token: str | None = None,  # noqa: ARG002
    ) -> dict[str, Any]:
        return {"responses": []}

    async def batch_update(
        self,
        form_id: str,  # noqa: ARG002
        requests: list[dict[str, Any]],
        include_form_in_response: bool = False,  # noqa: ARG002
    ) -> dict[str, Any]:
        self._batch_update_calls.append(requests)
        return {"replies": [{} for _ in requests]}


class TestFormsClientPull:
    """Tests for FormsClient.pull()."""

    @pytest.mark.asyncio
    async def test_pull_basic(self, tmp_path: Path) -> None:
        """Test basic pull operation."""
        form_data = {
            "formId": "test123",
            "revisionId": "rev1",
            "info": {"title": "Test Form", "description": "A test"},
            "items": [
                {
                    "itemId": "item1",
                    "title": "Name",
                    "questionItem": {
                        "question": {
                            "questionId": "q1",
                            "textQuestion": {"paragraph": False},
                        }
                    },
                }
            ],
        }

        transport = MockTransport(form_data)
        client = FormsClient(transport)

        result = await client.pull("test123", tmp_path, save_raw=True)

        assert isinstance(result, PullResult)
        assert result.form_id == "test123"
        assert len(result.files_written) > 0

        # Check form.json was written
        form_path = tmp_path / "test123" / "form.json"
        assert form_path.exists()
        written_form = json.loads(form_path.read_text())
        assert written_form["formId"] == "test123"

        # Check pristine was created
        pristine_path = tmp_path / "test123" / ".pristine" / "form.zip"
        assert pristine_path.exists()

    @pytest.mark.asyncio
    async def test_pull_with_raw(self, tmp_path: Path) -> None:
        """Test pull saves raw API responses."""
        form_data = {"formId": "test123", "info": {"title": "Test"}, "items": []}

        transport = MockTransport(form_data)
        client = FormsClient(transport)

        await client.pull("test123", tmp_path, save_raw=True)

        raw_form_path = tmp_path / "test123" / ".raw" / "form.json"
        assert raw_form_path.exists()

    @pytest.mark.asyncio
    async def test_pull_without_raw(self, tmp_path: Path) -> None:
        """Test pull without saving raw responses."""
        form_data = {"formId": "test123", "info": {"title": "Test"}, "items": []}

        transport = MockTransport(form_data)
        client = FormsClient(transport)

        await client.pull("test123", tmp_path, save_raw=False)

        raw_dir = tmp_path / "test123" / ".raw"
        assert not raw_dir.exists()


class TestFormsClientDiff:
    """Tests for FormsClient.diff()."""

    def test_diff_no_changes(self, tmp_path: Path) -> None:
        """Test diff with no changes."""
        form_folder = tmp_path / "form123"
        form_folder.mkdir()

        # Create form.json
        form_data = {"formId": "123", "info": {"title": "Test"}, "items": []}
        (form_folder / "form.json").write_text(json.dumps(form_data))

        # Create pristine
        pristine_dir = form_folder / ".pristine"
        pristine_dir.mkdir()
        import zipfile

        with zipfile.ZipFile(pristine_dir / "form.zip", "w") as zf:
            zf.writestr("form.json", json.dumps(form_data))

        transport = LocalFileTransport(tmp_path)
        client = FormsClient(transport)

        diff_result, requests = client.diff(form_folder)

        assert not diff_result.has_changes
        assert requests == []

    def test_diff_with_changes(self, tmp_path: Path) -> None:
        """Test diff detects changes."""
        form_folder = tmp_path / "form123"
        form_folder.mkdir()

        # Create current form.json with new title
        current_form = {"formId": "123", "info": {"title": "New Title"}, "items": []}
        (form_folder / "form.json").write_text(json.dumps(current_form))

        # Create pristine with old title
        pristine_form = {"formId": "123", "info": {"title": "Old Title"}, "items": []}
        pristine_dir = form_folder / ".pristine"
        pristine_dir.mkdir()
        import zipfile

        with zipfile.ZipFile(pristine_dir / "form.zip", "w") as zf:
            zf.writestr("form.json", json.dumps(pristine_form))

        transport = LocalFileTransport(tmp_path)
        client = FormsClient(transport)

        diff_result, requests = client.diff(form_folder)

        assert diff_result.has_changes
        assert len(requests) == 1
        assert "updateFormInfo" in requests[0]


class TestFormsClientPush:
    """Tests for FormsClient.push()."""

    @pytest.mark.asyncio
    async def test_push_no_changes(self, tmp_path: Path) -> None:
        """Test push with no changes."""
        form_folder = tmp_path / "form123"
        form_folder.mkdir()

        form_data = {"formId": "123", "info": {"title": "Test"}, "items": []}
        (form_folder / "form.json").write_text(json.dumps(form_data))

        pristine_dir = form_folder / ".pristine"
        pristine_dir.mkdir()
        import zipfile

        with zipfile.ZipFile(pristine_dir / "form.zip", "w") as zf:
            zf.writestr("form.json", json.dumps(form_data))

        transport = MockTransport(form_data)
        client = FormsClient(transport)

        result = await client.push(form_folder)

        assert isinstance(result, PushResult)
        assert result.success
        assert result.changes_applied == 0
        assert len(transport._batch_update_calls) == 0

    @pytest.mark.asyncio
    async def test_push_with_changes(self, tmp_path: Path) -> None:
        """Test push applies changes."""
        form_folder = tmp_path / "form123"
        form_folder.mkdir()

        # Current form with new title
        current_form = {"formId": "123", "info": {"title": "New Title"}, "items": []}
        (form_folder / "form.json").write_text(json.dumps(current_form))

        # Pristine with old title
        pristine_form = {"formId": "123", "info": {"title": "Old Title"}, "items": []}
        pristine_dir = form_folder / ".pristine"
        pristine_dir.mkdir()
        import zipfile

        with zipfile.ZipFile(pristine_dir / "form.zip", "w") as zf:
            zf.writestr("form.json", json.dumps(pristine_form))

        transport = MockTransport(current_form)
        client = FormsClient(transport)

        result = await client.push(form_folder)

        assert result.success
        assert result.changes_applied == 1
        assert len(transport._batch_update_calls) == 1


class TestPullResult:
    """Tests for PullResult dataclass."""

    def test_pull_result_creation(self) -> None:
        """Test PullResult creation."""
        result = PullResult(
            form_id="test123",
            files_written=[Path("form.json")],
            responses_count=5,
        )
        assert result.form_id == "test123"
        assert len(result.files_written) == 1
        assert result.responses_count == 5


class TestPushResult:
    """Tests for PushResult dataclass."""

    def test_push_result_creation(self) -> None:
        """Test PushResult creation."""
        result = PushResult(
            success=True,
            changes_applied=3,
            message="Applied 3 changes",
            form_id="test123",
        )
        assert result.success
        assert result.changes_applied == 3
        assert result.form_id == "test123"
