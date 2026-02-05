"""Generate batchUpdate requests from diff results."""

from __future__ import annotations

from typing import Any

from extraform.diff import DiffResult, ItemChange


def generate_requests(diff: DiffResult) -> list[dict[str, Any]]:
    """Convert DiffResult to batchUpdate requests.

    The order of requests is important:
    1. Form info changes (updateFormInfo)
    2. Settings changes (updateSettings)
    3. Delete items (from end to start to preserve indices)
    4. Add items (in index order)
    5. Update items
    6. Move items (with adjusted indices after deletes)

    Args:
        diff: The diff result to convert.

    Returns:
        List of batchUpdate request objects.
    """
    requests: list[dict[str, Any]] = []

    # 1. Form info changes
    if diff.info_changes and diff.info_changes.has_changes:
        requests.append(_generate_update_form_info(diff.info_changes))

    # 2. Settings changes
    if diff.settings_changes and diff.settings_changes.has_changes:
        requests.append(_generate_update_settings(diff.settings_changes))

    # Collect deleted indices for adjusting move operations
    deleted_indices: set[int] = set()
    deletes = sorted(
        [c for c in diff.item_changes if c.change_type == "delete"],
        key=lambda c: c.old_index if c.old_index is not None else 0,
        reverse=True,
    )

    # 3. Delete items (from end to start to preserve indices)
    for change in deletes:
        if change.old_index is not None:
            deleted_indices.add(change.old_index)
        requests.append(_generate_delete_item(change))

    # 4. Add items (in index order)
    adds = sorted(
        [c for c in diff.item_changes if c.change_type == "add"],
        key=lambda c: c.new_index if c.new_index is not None else 0,
    )
    for change in adds:
        requests.append(_generate_create_item(change))

    # 5. Update items
    for change in diff.item_changes:
        if change.change_type == "update":
            requests.append(_generate_update_item(change))

    # 6. Move items - use smart reordering algorithm
    moves = [c for c in diff.item_changes if c.change_type == "move"]
    if moves:
        move_requests = _generate_smart_moves(
            diff.old_item_order, diff.new_item_order, deleted_indices
        )
        requests.extend(move_requests)

    return requests


def _generate_update_form_info(info_changes: Any) -> dict[str, Any]:
    """Generate updateFormInfo request."""
    # Build info object with only changed fields
    info: dict[str, Any] = {}
    new_info = info_changes.new_info

    for field in info_changes.update_mask.split(","):
        if field == "title" and "title" in new_info:
            info["title"] = new_info["title"]
        elif field == "description":
            # Include description even if empty (to clear it)
            info["description"] = new_info.get("description", "")

    return {
        "updateFormInfo": {
            "info": info,
            "updateMask": info_changes.update_mask,
        }
    }


def _generate_update_settings(settings_changes: Any) -> dict[str, Any]:
    """Generate updateSettings request."""
    return {
        "updateSettings": {
            "settings": settings_changes.new_settings,
            "updateMask": settings_changes.update_mask,
        }
    }


def _generate_delete_item(change: ItemChange) -> dict[str, Any]:
    """Generate deleteItem request."""
    return {
        "deleteItem": {
            "location": {"index": change.old_index},
        }
    }


def _generate_create_item(change: ItemChange) -> dict[str, Any]:
    """Generate createItem request."""
    # Clean the item for creation (remove read-only fields)
    item = _clean_item_for_creation(change.new_item or {})

    return {
        "createItem": {
            "item": item,
            "location": {"index": change.new_index},
        }
    }


def _generate_update_item(change: ItemChange) -> dict[str, Any]:
    """Generate updateItem request."""
    # Clean the item for update
    item = _clean_item_for_update(change.new_item or {})

    return {
        "updateItem": {
            "item": item,
            "location": {"index": change.new_index},
            "updateMask": "*",  # Update all fields
        }
    }


def _generate_move_item(change: ItemChange) -> dict[str, Any]:
    """Generate moveItem request."""
    return {
        "moveItem": {
            "originalLocation": {"index": change.old_index},
            "newLocation": {"index": change.new_index},
        }
    }


def _generate_smart_moves(
    old_item_order: list[str],
    new_item_order: list[str],
    deleted_indices: set[int],
) -> list[dict[str, Any]]:
    """Generate minimal moveItem requests using simulation.

    The Google Forms API applies moves sequentially, so each move changes
    the indices for subsequent moves. This function simulates the process
    to generate correct requests.

    Args:
        old_item_order: List of item IDs in pristine order.
        new_item_order: List of item IDs in target order.
        deleted_indices: Set of original indices that were deleted.

    Returns:
        List of moveItem requests.
    """
    if not old_item_order or not new_item_order:
        return []

    # Build working order: start with old order, remove deleted items
    working_order = [
        item_id
        for i, item_id in enumerate(old_item_order)
        if i not in deleted_indices
    ]

    # Filter new_item_order to only include items in working_order
    # (this handles adds that happen before moves)
    existing_items = set(working_order)
    target_order = [item_id for item_id in new_item_order if item_id in existing_items]

    # If already in correct order, no moves needed
    if working_order == target_order:
        return []

    # Simulate moves to achieve target order
    requests: list[dict[str, Any]] = []

    for target_idx, target_item in enumerate(target_order):
        if target_idx >= len(working_order):
            break

        current_idx = working_order.index(target_item)

        if current_idx != target_idx:
            # Need to move this item
            requests.append({
                "moveItem": {
                    "originalLocation": {"index": current_idx},
                    "newLocation": {"index": target_idx},
                }
            })
            # Update working order to reflect the move
            working_order.pop(current_idx)
            working_order.insert(target_idx, target_item)

    return requests


def _clean_item_for_creation(item: dict[str, Any]) -> dict[str, Any]:
    """Remove read-only fields from item for creation.

    When creating a new item, we should not include:
    - itemId (will be assigned by API)
    - questionId (will be assigned by API)
    """
    cleaned = dict(item)

    # Remove itemId if present (API will assign)
    cleaned.pop("itemId", None)

    # Remove questionId from questions
    if "questionItem" in cleaned:
        question_item = dict(cleaned["questionItem"])
        if "question" in question_item:
            question = dict(question_item["question"])
            question.pop("questionId", None)
            question_item["question"] = question
        cleaned["questionItem"] = question_item

    if "questionGroupItem" in cleaned:
        group = dict(cleaned["questionGroupItem"])
        if "questions" in group:
            questions = []
            for q in group["questions"]:
                q_copy = dict(q)
                q_copy.pop("questionId", None)
                questions.append(q_copy)
            group["questions"] = questions
        cleaned["questionGroupItem"] = group

    return cleaned


def _clean_item_for_update(item: dict[str, Any]) -> dict[str, Any]:
    """Clean item for update request.

    For updates, we keep the itemId (to identify the item)
    but remove questionId (read-only).
    """
    cleaned = dict(item)

    # Keep itemId for identification

    # Remove questionId from questions (read-only after creation)
    if "questionItem" in cleaned:
        question_item = dict(cleaned["questionItem"])
        if "question" in question_item:
            question = dict(question_item["question"])
            question.pop("questionId", None)
            question_item["question"] = question
        cleaned["questionItem"] = question_item

    if "questionGroupItem" in cleaned:
        group = dict(cleaned["questionGroupItem"])
        if "questions" in group:
            questions = []
            for q in group["questions"]:
                q_copy = dict(q)
                q_copy.pop("questionId", None)
                questions.append(q_copy)
            group["questions"] = questions
        cleaned["questionGroupItem"] = group

    return cleaned
