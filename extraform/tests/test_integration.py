"""Integration tests using golden files."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from extraform.client import FormsClient
from extraform.transformer import FormTransformer
from extraform.transport import LocalFileTransport

GOLDEN_DIR = Path(__file__).parent / "golden"


class TestGoldenFilePull:
    """Tests that use golden files to verify pull behavior."""

    @pytest.mark.asyncio
    async def test_pull_simple_form(self, tmp_path: Path) -> None:
        """Test pulling a simple form from golden files."""
        transport = LocalFileTransport(GOLDEN_DIR)
        client = FormsClient(transport)

        result = await client.pull(
            "simple_form",
            tmp_path,
            save_raw=True,
        )

        assert result.form_id == "simple_form"

        # Check form.json was created correctly
        form_path = tmp_path / "simple_form" / "form.json"
        assert form_path.exists()

        form = json.loads(form_path.read_text())
        assert form["formId"] == "1FAIpQLSdTest123"
        assert form["info"]["title"] == "Simple Test Form"
        assert len(form["items"]) == 5

        # Verify question types
        items = form["items"]
        assert "textQuestion" in items[0]["questionItem"]["question"]
        assert "choiceQuestion" in items[1]["questionItem"]["question"]
        assert "scaleQuestion" in items[2]["questionItem"]["question"]
        assert "pageBreakItem" in items[3]
        assert "textQuestion" in items[4]["questionItem"]["question"]


class TestGoldenFileRoundTrip:
    """Tests for pull → no changes → diff returning empty."""

    @pytest.mark.asyncio
    async def test_roundtrip_no_changes(self, tmp_path: Path) -> None:
        """Test that pulling and diffing without changes returns no requests."""
        transport = LocalFileTransport(GOLDEN_DIR)
        client = FormsClient(transport)

        # Pull the form
        await client.pull("simple_form", tmp_path, save_raw=False)

        # Diff without making changes
        form_folder = tmp_path / "simple_form"
        diff_result, requests = client.diff(form_folder)

        assert not diff_result.has_changes
        assert requests == []


class TestGoldenFileEdit:
    """Tests for editing golden files and generating requests."""

    @pytest.mark.asyncio
    async def test_edit_title(self, tmp_path: Path) -> None:
        """Test editing the form title generates correct request."""
        transport = LocalFileTransport(GOLDEN_DIR)
        client = FormsClient(transport)

        # Pull the form
        await client.pull("simple_form", tmp_path, save_raw=False)

        # Edit the title
        form_path = tmp_path / "simple_form" / "form.json"
        form = json.loads(form_path.read_text())
        form["info"]["title"] = "Updated Form Title"
        form_path.write_text(json.dumps(form, indent=2))

        # Diff
        diff_result, requests = client.diff(tmp_path / "simple_form")

        assert diff_result.has_changes
        assert len(requests) == 1
        assert "updateFormInfo" in requests[0]
        assert requests[0]["updateFormInfo"]["info"]["title"] == "Updated Form Title"

    @pytest.mark.asyncio
    async def test_add_question(self, tmp_path: Path) -> None:
        """Test adding a question generates correct request."""
        transport = LocalFileTransport(GOLDEN_DIR)
        client = FormsClient(transport)

        # Pull the form
        await client.pull("simple_form", tmp_path, save_raw=False)

        # Add a new question
        form_path = tmp_path / "simple_form" / "form.json"
        form = json.loads(form_path.read_text())
        form["items"].append(
            {
                "title": "New Question",
                "questionItem": {
                    "question": {"required": True, "textQuestion": {"paragraph": False}}
                },
            }
        )
        form_path.write_text(json.dumps(form, indent=2))

        # Diff
        diff_result, requests = client.diff(tmp_path / "simple_form")

        assert diff_result.has_changes

        # Find the createItem request
        create_requests = [r for r in requests if "createItem" in r]
        assert len(create_requests) == 1
        assert create_requests[0]["createItem"]["item"]["title"] == "New Question"

    @pytest.mark.asyncio
    async def test_delete_question(self, tmp_path: Path) -> None:
        """Test deleting a question generates correct request."""
        transport = LocalFileTransport(GOLDEN_DIR)
        client = FormsClient(transport)

        # Pull the form
        await client.pull("simple_form", tmp_path, save_raw=False)

        # Delete first question
        form_path = tmp_path / "simple_form" / "form.json"
        form = json.loads(form_path.read_text())
        del form["items"][0]
        form_path.write_text(json.dumps(form, indent=2))

        # Diff
        diff_result, requests = client.diff(tmp_path / "simple_form")

        assert diff_result.has_changes

        # Find the deleteItem request
        delete_requests = [r for r in requests if "deleteItem" in r]
        assert len(delete_requests) == 1
        assert delete_requests[0]["deleteItem"]["location"]["index"] == 0

    @pytest.mark.asyncio
    async def test_update_question(self, tmp_path: Path) -> None:
        """Test updating a question generates correct request."""
        transport = LocalFileTransport(GOLDEN_DIR)
        client = FormsClient(transport)

        # Pull the form
        await client.pull("simple_form", tmp_path, save_raw=False)

        # Update first question's title
        form_path = tmp_path / "simple_form" / "form.json"
        form = json.loads(form_path.read_text())
        form["items"][0]["title"] = "Updated Question Title"
        form_path.write_text(json.dumps(form, indent=2))

        # Diff
        diff_result, requests = client.diff(tmp_path / "simple_form")

        assert diff_result.has_changes

        # Find the updateItem request
        update_requests = [r for r in requests if "updateItem" in r]
        assert len(update_requests) == 1
        assert update_requests[0]["updateItem"]["item"]["title"] == "Updated Question Title"


class TestTransformerWithGolden:
    """Tests for FormTransformer using golden files."""

    def test_transform_golden_form(self) -> None:
        """Test transforming golden file form data."""
        golden_form = json.loads((GOLDEN_DIR / "simple_form" / "form.json").read_text())

        transformer = FormTransformer(golden_form)
        files = transformer.transform()

        assert "form.json" in files
        form = files["form.json"]

        # Verify structure preserved
        assert form["formId"] == golden_form["formId"]
        assert form["info"]["title"] == golden_form["info"]["title"]
        assert len(form["items"]) == len(golden_form["items"])
