"""Tests for the diff engine."""

from __future__ import annotations

from extraform.diff import (
    DiffResult,
    ItemChange,
    diff_forms,
)


class TestDiffForms:
    """Tests for diff_forms function."""

    def test_no_changes(self) -> None:
        """Test diffing identical forms."""
        form = {
            "formId": "test_form",
            "info": {"title": "Test Form"},
            "items": [
                {
                    "itemId": "item1",
                    "title": "Question 1",
                    "questionItem": {"question": {"textQuestion": {"paragraph": False}}},
                }
            ],
        }

        result = diff_forms(form, form)

        assert not result.has_changes
        assert result.info_changes is None
        assert result.settings_changes is None
        assert len(result.item_changes) == 0

    def test_title_change(self) -> None:
        """Test detecting title change."""
        pristine = {
            "formId": "test_form",
            "info": {"title": "Old Title"},
            "items": [],
        }
        current = {
            "formId": "test_form",
            "info": {"title": "New Title"},
            "items": [],
        }

        result = diff_forms(pristine, current)

        assert result.has_changes
        assert result.info_changes is not None
        assert "title" in result.info_changes.update_mask
        assert result.info_changes.new_info["title"] == "New Title"

    def test_description_change(self) -> None:
        """Test detecting description change."""
        pristine = {
            "formId": "test_form",
            "info": {"title": "Form", "description": "Old description"},
            "items": [],
        }
        current = {
            "formId": "test_form",
            "info": {"title": "Form", "description": "New description"},
            "items": [],
        }

        result = diff_forms(pristine, current)

        assert result.has_changes
        assert result.info_changes is not None
        assert "description" in result.info_changes.update_mask

    def test_add_item(self) -> None:
        """Test detecting added item."""
        pristine = {
            "formId": "test_form",
            "info": {"title": "Form"},
            "items": [],
        }
        current = {
            "formId": "test_form",
            "info": {"title": "Form"},
            "items": [
                {
                    "title": "New Question",
                    "questionItem": {"question": {"textQuestion": {"paragraph": False}}},
                }
            ],
        }

        result = diff_forms(pristine, current)

        assert result.has_changes
        assert len(result.item_changes) == 1
        assert result.item_changes[0].change_type == "add"
        assert result.item_changes[0].new_index == 0

    def test_delete_item(self) -> None:
        """Test detecting deleted item."""
        pristine = {
            "formId": "test_form",
            "info": {"title": "Form"},
            "items": [
                {
                    "itemId": "item1",
                    "title": "Question to delete",
                    "questionItem": {"question": {"textQuestion": {"paragraph": False}}},
                }
            ],
        }
        current = {
            "formId": "test_form",
            "info": {"title": "Form"},
            "items": [],
        }

        result = diff_forms(pristine, current)

        assert result.has_changes
        assert len(result.item_changes) == 1
        assert result.item_changes[0].change_type == "delete"
        assert result.item_changes[0].item_id == "item1"
        assert result.item_changes[0].old_index == 0

    def test_update_item(self) -> None:
        """Test detecting updated item."""
        pristine = {
            "formId": "test_form",
            "info": {"title": "Form"},
            "items": [
                {
                    "itemId": "item1",
                    "title": "Old title",
                    "questionItem": {"question": {"textQuestion": {"paragraph": False}}},
                }
            ],
        }
        current = {
            "formId": "test_form",
            "info": {"title": "Form"},
            "items": [
                {
                    "itemId": "item1",
                    "title": "New title",
                    "questionItem": {"question": {"textQuestion": {"paragraph": False}}},
                }
            ],
        }

        result = diff_forms(pristine, current)

        assert result.has_changes
        assert len(result.item_changes) == 1
        assert result.item_changes[0].change_type == "update"
        assert result.item_changes[0].item_id == "item1"
        assert result.item_changes[0].new_item["title"] == "New title"

    def test_move_item(self) -> None:
        """Test detecting moved item."""
        pristine = {
            "formId": "test_form",
            "info": {"title": "Form"},
            "items": [
                {"itemId": "item1", "title": "First", "textItem": {}},
                {"itemId": "item2", "title": "Second", "textItem": {}},
            ],
        }
        current = {
            "formId": "test_form",
            "info": {"title": "Form"},
            "items": [
                {"itemId": "item2", "title": "Second", "textItem": {}},
                {"itemId": "item1", "title": "First", "textItem": {}},
            ],
        }

        result = diff_forms(pristine, current)

        assert result.has_changes
        # Should detect moves for both items
        moves = [c for c in result.item_changes if c.change_type == "move"]
        assert len(moves) == 2

    def test_settings_change(self) -> None:
        """Test detecting settings change."""
        pristine = {
            "formId": "test_form",
            "info": {"title": "Form"},
            "settings": {
                "quizSettings": {"isQuiz": False},
            },
            "items": [],
        }
        current = {
            "formId": "test_form",
            "info": {"title": "Form"},
            "settings": {
                "quizSettings": {"isQuiz": True},
            },
            "items": [],
        }

        result = diff_forms(pristine, current)

        assert result.has_changes
        assert result.settings_changes is not None
        assert "quizSettings.isQuiz" in result.settings_changes.update_mask

    def test_multiple_changes(self) -> None:
        """Test detecting multiple changes at once."""
        pristine = {
            "formId": "test_form",
            "info": {"title": "Old Title"},
            "items": [
                {"itemId": "item1", "title": "Q1", "textItem": {}},
                {"itemId": "item2", "title": "Q2", "textItem": {}},
            ],
        }
        current = {
            "formId": "test_form",
            "info": {"title": "New Title"},
            "items": [
                {"itemId": "item1", "title": "Q1 Updated", "textItem": {}},
                # item2 deleted
                {"title": "New Q", "textItem": {}},  # new item
            ],
        }

        result = diff_forms(pristine, current)

        assert result.has_changes
        assert result.info_changes is not None

        # Should have: update for item1, delete for item2, add for new item
        change_types = [c.change_type for c in result.item_changes]
        assert "update" in change_types
        assert "delete" in change_types
        assert "add" in change_types


class TestItemChange:
    """Tests for ItemChange dataclass."""

    def test_add_change(self) -> None:
        """Test add change creation."""
        change = ItemChange(
            change_type="add",
            new_item={"title": "New"},
            new_index=0,
        )
        assert change.change_type == "add"
        assert change.item_id is None
        assert change.old_item is None

    def test_delete_change(self) -> None:
        """Test delete change creation."""
        change = ItemChange(
            change_type="delete",
            item_id="item1",
            old_item={"title": "Old"},
            old_index=0,
        )
        assert change.change_type == "delete"
        assert change.item_id == "item1"
        assert change.new_item is None

    def test_update_change(self) -> None:
        """Test update change creation."""
        change = ItemChange(
            change_type="update",
            item_id="item1",
            old_item={"title": "Old"},
            new_item={"title": "New"},
            old_index=0,
            new_index=0,
        )
        assert change.change_type == "update"
        assert change.old_item["title"] == "Old"
        assert change.new_item["title"] == "New"


class TestDiffResult:
    """Tests for DiffResult dataclass."""

    def test_has_changes_empty(self) -> None:
        """Test has_changes returns False for empty result."""
        result = DiffResult(form_id="test")
        assert not result.has_changes

    def test_has_changes_with_info(self) -> None:
        """Test has_changes returns True with info changes."""
        from extraform.diff import InfoChanges

        result = DiffResult(
            form_id="test",
            info_changes=InfoChanges(
                old_info={"title": "Old"},
                new_info={"title": "New"},
                update_mask="title",
            ),
        )
        assert result.has_changes

    def test_has_changes_with_items(self) -> None:
        """Test has_changes returns True with item changes."""
        result = DiffResult(
            form_id="test",
            item_changes=[ItemChange(change_type="add", new_item={}, new_index=0)],
        )
        assert result.has_changes
