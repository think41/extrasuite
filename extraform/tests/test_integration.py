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


class TestConditionalBranching:
    """Tests for conditional section branching via goToSectionId."""

    @pytest.mark.asyncio
    async def test_pull_conditional_form_preserves_goto(self, tmp_path: Path) -> None:
        """Pulling a form with goToSectionId preserves the branching fields."""
        transport = LocalFileTransport(GOLDEN_DIR)
        client = FormsClient(transport)

        await client.pull("conditional_form", tmp_path, save_raw=False)

        form_path = tmp_path / "conditional_form" / "form.json"
        form = json.loads(form_path.read_text())

        # The branching question is first
        question = form["items"][0]["questionItem"]["question"]
        options = question["choiceQuestion"]["options"]
        assert options[0]["value"] == "Yes"
        assert options[0]["goToSectionId"] == "section-existing"
        assert options[1]["value"] == "No"
        assert options[1]["goToSectionId"] == "section-new"

    @pytest.mark.asyncio
    async def test_existing_goto_no_two_phase(self, tmp_path: Path) -> None:
        """Modifying goToSectionId that references existing sections uses one batch."""
        transport = LocalFileTransport(GOLDEN_DIR)
        client = FormsClient(transport)

        await client.pull("conditional_form", tmp_path, save_raw=False)

        # Swap which section each answer goes to
        form_path = tmp_path / "conditional_form" / "form.json"
        form = json.loads(form_path.read_text())
        options = form["items"][0]["questionItem"]["question"]["choiceQuestion"]["options"]
        options[0]["goToSectionId"] = "section-new"
        options[1]["goToSectionId"] = "section-existing"
        form_path.write_text(json.dumps(form, indent=2))

        from extraform.request_generator import generate_batched_requests

        diff_result, _ = client.diff(tmp_path / "conditional_form")
        batches = generate_batched_requests(diff_result)

        # Existing sections → no placeholder IDs → single batch
        assert len(batches) == 1
        assert len(batches[0]) == 1  # one updateItem
        assert "updateItem" in batches[0][0]

    @pytest.mark.asyncio
    async def test_new_section_with_goto_triggers_two_phase(self, tmp_path: Path) -> None:
        """Adding a new section referenced by goToSectionId triggers a 2-batch push.

        The new branching question (which references "feedback-section") goes into
        Batch 1 because it depends on the section's API-assigned ID.
        Batch 0 contains the placeholder section and other non-dependent creates.
        """
        transport = LocalFileTransport(GOLDEN_DIR)
        client = FormsClient(transport)

        await client.pull("simple_form", tmp_path, save_raw=False)

        # Add a branching question and two new sections with agent-chosen IDs
        form_path = tmp_path / "simple_form" / "form.json"
        form = json.loads(form_path.read_text())
        form["items"].extend([
            {
                "title": "Would you like to give feedback?",
                "questionItem": {
                    "question": {
                        "required": True,
                        "choiceQuestion": {
                            "type": "RADIO",
                            "options": [
                                {"value": "Yes", "goToSectionId": "feedback-section"},
                                {"value": "No", "goToAction": "SUBMIT_FORM"},
                            ],
                        },
                    }
                },
            },
            {
                "itemId": "feedback-section",
                "title": "Feedback",
                "pageBreakItem": {},
            },
            {
                "title": "Please share your feedback",
                "questionItem": {
                    "question": {"textQuestion": {"paragraph": True}}
                },
            },
        ])
        form_path.write_text(json.dumps(form, indent=2))

        from extraform.request_generator import DeferredItemID, generate_batched_requests

        diff_result, _ = client.diff(tmp_path / "simple_form")
        batches = generate_batched_requests(diff_result)

        # "feedback-section" is a placeholder → 2 batches required
        assert len(batches) == 2

        # Batch 0: non-dependent creates only (section + text question, NOT the branching Q)
        batch0_creates = [r for r in batches[0] if "createItem" in r]
        assert len(batch0_creates) == 2
        assert any("pageBreakItem" in r["createItem"]["item"] for r in batch0_creates)

        # Batch 1: the branching question (createItem with DeferredItemID in goToSectionId)
        assert len(batches[1]) == 1
        assert "createItem" in batches[1][0]
        branch_item = batches[1][0]["createItem"]["item"]
        options = branch_item["questionItem"]["question"]["choiceQuestion"]["options"]
        yes_option = next(o for o in options if o.get("value") == "Yes")
        assert isinstance(yes_option["goToSectionId"], DeferredItemID)
        assert yes_option["goToSectionId"].placeholder == "feedback-section"

    @pytest.mark.asyncio
    async def test_two_phase_push_resolves_ids(self, tmp_path: Path) -> None:
        """2-phase push resolves placeholder IDs with real API-assigned IDs."""
        transport = LocalFileTransport(GOLDEN_DIR)
        client = FormsClient(transport)

        await client.pull("simple_form", tmp_path, save_raw=False)

        form_path = tmp_path / "simple_form" / "form.json"
        form = json.loads(form_path.read_text())
        form["items"].extend([
            {
                "title": "Continue?",
                "questionItem": {
                    "question": {
                        "choiceQuestion": {
                            "type": "RADIO",
                            "options": [
                                {"value": "Yes", "goToSectionId": "extra-section"},
                                {"value": "No", "goToAction": "SUBMIT_FORM"},
                            ],
                        }
                    }
                },
            },
            {
                "itemId": "extra-section",
                "title": "Extra Questions",
                "pageBreakItem": {},
            },
        ])
        form_path.write_text(json.dumps(form, indent=2))

        # Execute the full push - LocalFileTransport returns fake itemIds
        result = await client.push(tmp_path / "simple_form")

        assert result.success
        assert result.changes_applied > 0
        assert "2 phases" in result.message

    @pytest.mark.asyncio
    async def test_goToAction_no_two_phase(self, tmp_path: Path) -> None:
        """goToAction (not goToSectionId) never requires a 2-batch push."""
        transport = LocalFileTransport(GOLDEN_DIR)
        client = FormsClient(transport)

        await client.pull("simple_form", tmp_path, save_raw=False)

        form_path = tmp_path / "simple_form" / "form.json"
        form = json.loads(form_path.read_text())
        # Add a question using goToAction (no section ID needed)
        form["items"].append({
            "title": "Submit or continue?",
            "questionItem": {
                "question": {
                    "choiceQuestion": {
                        "type": "RADIO",
                        "options": [
                            {"value": "Submit now", "goToAction": "SUBMIT_FORM"},
                            {"value": "Continue", "goToAction": "NEXT_SECTION"},
                        ],
                    }
                }
            },
        })
        form_path.write_text(json.dumps(form, indent=2))

        from extraform.request_generator import generate_batched_requests

        diff_result, _ = client.diff(tmp_path / "simple_form")
        batches = generate_batched_requests(diff_result)

        # goToAction has no section ID dependency → single batch
        assert len(batches) == 1


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
