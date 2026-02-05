"""Tests for the request generator."""

from __future__ import annotations

from extraform.diff import DiffResult, InfoChanges, ItemChange, SettingsChanges
from extraform.request_generator import generate_requests


class TestGenerateRequests:
    """Tests for generate_requests function."""

    def test_empty_diff(self) -> None:
        """Test generating requests for empty diff."""
        diff = DiffResult(form_id="test_form")
        requests = generate_requests(diff)
        assert requests == []

    def test_update_form_info(self) -> None:
        """Test generating updateFormInfo request."""
        diff = DiffResult(
            form_id="test_form",
            info_changes=InfoChanges(
                old_info={"title": "Old Title"},
                new_info={"title": "New Title"},
                update_mask="title",
            ),
        )

        requests = generate_requests(diff)

        assert len(requests) == 1
        assert "updateFormInfo" in requests[0]
        req = requests[0]["updateFormInfo"]
        assert req["info"]["title"] == "New Title"
        assert req["updateMask"] == "title"

    def test_update_settings(self) -> None:
        """Test generating updateSettings request."""
        diff = DiffResult(
            form_id="test_form",
            settings_changes=SettingsChanges(
                old_settings={"quizSettings": {"isQuiz": False}},
                new_settings={"quizSettings": {"isQuiz": True}},
                update_mask="quizSettings.isQuiz",
            ),
        )

        requests = generate_requests(diff)

        assert len(requests) == 1
        assert "updateSettings" in requests[0]
        req = requests[0]["updateSettings"]
        assert req["settings"]["quizSettings"]["isQuiz"] is True

    def test_create_item(self) -> None:
        """Test generating createItem request."""
        diff = DiffResult(
            form_id="test_form",
            item_changes=[
                ItemChange(
                    change_type="add",
                    new_item={
                        "title": "New Question",
                        "questionItem": {
                            "question": {
                                "questionId": "q1",  # Should be stripped
                                "textQuestion": {"paragraph": False},
                            }
                        },
                    },
                    new_index=0,
                )
            ],
        )

        requests = generate_requests(diff)

        assert len(requests) == 1
        assert "createItem" in requests[0]
        req = requests[0]["createItem"]
        assert req["item"]["title"] == "New Question"
        assert req["location"]["index"] == 0
        # questionId should be removed
        assert "questionId" not in req["item"]["questionItem"]["question"]

    def test_delete_item(self) -> None:
        """Test generating deleteItem request."""
        diff = DiffResult(
            form_id="test_form",
            item_changes=[
                ItemChange(
                    change_type="delete",
                    item_id="item1",
                    old_item={"itemId": "item1", "title": "Old Q"},
                    old_index=2,
                )
            ],
        )

        requests = generate_requests(diff)

        assert len(requests) == 1
        assert "deleteItem" in requests[0]
        req = requests[0]["deleteItem"]
        assert req["location"]["index"] == 2

    def test_update_item(self) -> None:
        """Test generating updateItem request."""
        diff = DiffResult(
            form_id="test_form",
            item_changes=[
                ItemChange(
                    change_type="update",
                    item_id="item1",
                    old_item={"itemId": "item1", "title": "Old"},
                    new_item={"itemId": "item1", "title": "New"},
                    old_index=0,
                    new_index=0,
                )
            ],
        )

        requests = generate_requests(diff)

        assert len(requests) == 1
        assert "updateItem" in requests[0]
        req = requests[0]["updateItem"]
        assert req["item"]["title"] == "New"
        assert req["updateMask"] == "*"

    def test_move_item(self) -> None:
        """Test generating moveItem request."""
        # Move item1 from index 0 to index 2
        # Old order: [item1, item2, item3]
        # New order: [item2, item3, item1]
        # Algorithm simulates sequential moves:
        #   1. Move 1→0: [item2, item1, item3]
        #   2. Move 2→1: [item2, item3, item1] ✓
        diff = DiffResult(
            form_id="test_form",
            item_changes=[
                ItemChange(
                    change_type="move",
                    item_id="item1",
                    old_item={"itemId": "item1"},
                    new_item={"itemId": "item1"},
                    old_index=0,
                    new_index=2,
                )
            ],
            old_item_order=["item1", "item2", "item3"],
            new_item_order=["item2", "item3", "item1"],
        )

        requests = generate_requests(diff)

        # Verify all requests are moveItem
        for req in requests:
            assert "moveItem" in req

        # Simulate the moves and verify we reach target order
        working = ["item1", "item2", "item3"]
        for req in requests:
            move = req["moveItem"]
            from_idx = move["originalLocation"]["index"]
            to_idx = move["newLocation"]["index"]
            item = working.pop(from_idx)
            working.insert(to_idx, item)
        assert working == ["item2", "item3", "item1"]

    def test_request_order(self) -> None:
        """Test that requests are generated in correct order."""
        diff = DiffResult(
            form_id="test_form",
            info_changes=InfoChanges(
                old_info={"title": "Old"},
                new_info={"title": "New"},
                update_mask="title",
            ),
            settings_changes=SettingsChanges(
                old_settings={},
                new_settings={"quizSettings": {"isQuiz": True}},
                update_mask="quizSettings.isQuiz",
            ),
            item_changes=[
                ItemChange(change_type="delete", item_id="item1", old_index=1),
                ItemChange(change_type="add", new_item={"title": "New"}, new_index=0),
                ItemChange(
                    change_type="update",
                    item_id="item2",
                    new_item={"title": "Updated"},
                    new_index=1,
                ),
                ItemChange(change_type="move", item_id="item3", old_index=2, new_index=3),
            ],
            # Old: [item0, item1, item2, item3, item4]
            # After delete item1: [item0, item2, item3, item4]
            # Move item3 from 2 to 3: [item0, item2, item4, item3]
            old_item_order=["item0", "item1", "item2", "item3", "item4"],
            new_item_order=["item0", "item2", "item4", "item3"],
        )

        requests = generate_requests(diff)

        # Expected order: info, settings, delete, add, update, move
        request_types = [list(r.keys())[0] for r in requests]
        assert request_types == [
            "updateFormInfo",
            "updateSettings",
            "deleteItem",
            "createItem",
            "updateItem",
            "moveItem",
        ]

    def test_multiple_deletes_from_end(self) -> None:
        """Test that deletes are processed from end to preserve indices."""
        diff = DiffResult(
            form_id="test_form",
            item_changes=[
                ItemChange(change_type="delete", item_id="item1", old_index=0),
                ItemChange(change_type="delete", item_id="item2", old_index=2),
                ItemChange(change_type="delete", item_id="item3", old_index=1),
            ],
        )

        requests = generate_requests(diff)

        # Should delete from highest index first
        delete_indices = [r["deleteItem"]["location"]["index"] for r in requests]
        assert delete_indices == [2, 1, 0]

    def test_multiple_adds_in_order(self) -> None:
        """Test that adds are processed in index order."""
        diff = DiffResult(
            form_id="test_form",
            item_changes=[
                ItemChange(change_type="add", new_item={"title": "Q3"}, new_index=2),
                ItemChange(change_type="add", new_item={"title": "Q1"}, new_index=0),
                ItemChange(change_type="add", new_item={"title": "Q2"}, new_index=1),
            ],
        )

        requests = generate_requests(diff)

        # Should add in index order
        add_indices = [r["createItem"]["location"]["index"] for r in requests]
        assert add_indices == [0, 1, 2]

    def test_clean_item_for_creation(self) -> None:
        """Test that read-only fields are removed when creating items."""
        diff = DiffResult(
            form_id="test_form",
            item_changes=[
                ItemChange(
                    change_type="add",
                    new_item={
                        "itemId": "should_be_removed",
                        "title": "New Question",
                        "questionItem": {
                            "question": {
                                "questionId": "should_be_removed",
                                "textQuestion": {"paragraph": False},
                            }
                        },
                    },
                    new_index=0,
                )
            ],
        )

        requests = generate_requests(diff)

        item = requests[0]["createItem"]["item"]
        assert "itemId" not in item
        assert "questionId" not in item["questionItem"]["question"]

    def test_update_description(self) -> None:
        """Test updating description with empty value."""
        diff = DiffResult(
            form_id="test_form",
            info_changes=InfoChanges(
                old_info={"title": "Form", "description": "Old desc"},
                new_info={"title": "Form"},  # description removed
                update_mask="description",
            ),
        )

        requests = generate_requests(diff)

        req = requests[0]["updateFormInfo"]
        # Description should be empty string to clear it
        assert req["info"]["description"] == ""
