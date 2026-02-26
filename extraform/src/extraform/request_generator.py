"""Generate batchUpdate requests from diff results."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from extraform.diff import DiffResult, ItemChange


@dataclass(frozen=True)
class DeferredItemID:
    """Placeholder for a section itemId that the API assigns after creation.

    After the batch at ``batch_index`` completes, the real ID is found at::

        prior_responses[batch_index]["replies"][request_index]["createItem"]["itemId"]

    The object is embedded directly in a request dict as the value of a
    ``goToSectionId`` key.  ``resolve_deferred_ids`` replaces it with the
    real string before the request is sent to the API.
    """

    placeholder: str       # Agent-chosen placeholder (e.g. "section-happy")
    batch_index: int       # Which batch creates the section
    request_index: int     # Position in that batch's reply list
    response_path: str = "createItem.itemId"


def resolve_deferred_ids(
    prior_responses: list[dict[str, Any]],
    requests: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Replace DeferredItemID objects with real API-assigned IDs.

    Recursively walks every dict and list in *requests*.  Any
    :class:`DeferredItemID` value is replaced by the string ID returned by
    the API in the batch whose index is stored in the object.

    Args:
        prior_responses: Responses from already-executed batches, in order.
        requests: Requests for the next batch (may contain DeferredItemID
            objects as ``goToSectionId`` values).

    Returns:
        New list of requests with all DeferredItemID objects replaced.
    """

    def _resolve(val: Any) -> Any:
        if isinstance(val, DeferredItemID):
            reply = prior_responses[val.batch_index]["replies"][val.request_index]
            result: Any = reply
            for key in val.response_path.split("."):
                result = result[key]
            return result
        if isinstance(val, dict):
            return {k: _resolve(v) for k, v in val.items()}
        if isinstance(val, list):
            return [_resolve(v) for v in val]
        return val

    return [_resolve(req) for req in requests]


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
    # Use the item's position AFTER deletes and creates (not new_index which is
    # the final desired position including moves).  This matters when an item has
    # both a content change (update) and a position change (move) in the same push.
    for change in diff.item_changes:
        if change.change_type == "update":
            idx = _update_item_index(change, deleted_indices, adds)
            requests.append(_generate_update_item(change, idx))

    # 6. Move items - use smart reordering algorithm
    moves = [c for c in diff.item_changes if c.change_type == "move"]
    if moves:
        move_requests = _generate_smart_moves(
            diff.old_item_order, diff.new_item_order, deleted_indices
        )
        requests.extend(move_requests)

    return requests


def generate_batched_requests(diff: DiffResult) -> list[list[dict[str, Any]]]:
    """Split requests into dependency-ordered batches.

    When agents add new page-break sections and reference them via
    ``goToSectionId``, the section must be created first so the API can
    assign its real ``itemId``.  This function builds a dependency graph and
    splits requests into the minimum number of batches needed:

    * **Batch 0** – info / settings / deletes + *non-dependent* creates
      (including the placeholder sections themselves, with indices adjusted
      for the items deferred to a later batch).
    * **Batch 1** – creates / updates whose ``goToSectionId`` points to a
      new section (a :class:`DeferredItemID` is embedded in place of the
      placeholder string; :func:`resolve_deferred_ids` replaces it with the
      real ID before the batch is sent).

    If no placeholder IDs are referenced the function returns a single batch
    identical to :func:`generate_requests` output.

    For the current Google Forms API model, the dependency graph is at most
    one level deep (only ``choiceQuestion`` options reference sections, and
    sections never reference other sections).  The pattern generalises to N
    batches should deeper chains become possible.

    Args:
        diff: The diff result (must include ``pristine_items`` and
            ``current_items`` populated by :func:`~extraform.diff.diff_forms`).

    Returns:
        A list of request-batches.  The caller iterates over them, calling
        :func:`resolve_deferred_ids` between each pair.
    """
    placeholder_ids = _find_placeholder_section_ids(diff.pristine_items, diff.current_items)
    referenced = _find_referenced_placeholders(diff.current_items, placeholder_ids)

    if not referenced:
        return [generate_requests(diff)]

    # ------------------------------------------------------------------
    # Determine which creates are "dependent" (reference a placeholder ID).
    # ------------------------------------------------------------------
    adds = sorted(
        [c for c in diff.item_changes if c.change_type == "add"],
        key=lambda c: c.new_index if c.new_index is not None else 0,
    )
    dependent_new_indices: set[int] = set()
    for change in adds:
        if _item_has_goto_placeholder(change.new_item or {}, referenced):
            dependent_new_indices.add(change.new_index or 0)

    # ------------------------------------------------------------------
    # Build Batch 0: info / settings / deletes + non-dependent creates.
    #
    # Index adjustment for non-dependent creates:
    #   adj_idx = new_idx - count(dependent creates at desired positions < new_idx)
    #
    # Rationale: new_idx is the position in the fully-desired form (which
    # includes all creates).  In Batch 0 the dependent creates are absent,
    # so items that would sit after them need a lower index.  Deletes are
    # executed first within the batch, so they don't affect the formula.
    # ------------------------------------------------------------------
    batch0: list[dict[str, Any]] = []

    if diff.info_changes and diff.info_changes.has_changes:
        batch0.append(_generate_update_form_info(diff.info_changes))
    if diff.settings_changes and diff.settings_changes.has_changes:
        batch0.append(_generate_update_settings(diff.settings_changes))

    deletes = sorted(
        [c for c in diff.item_changes if c.change_type == "delete"],
        key=lambda c: c.old_index if c.old_index is not None else 0,
        reverse=True,
    )
    deleted_indices: set[int] = set()
    for change in deletes:
        if change.old_index is not None:
            deleted_indices.add(change.old_index)
        batch0.append(_generate_delete_item(change))

    # Maps placeholder_id → request index inside batch0, so Batch 1 can
    # build DeferredItemID objects pointing at the right reply slot.
    placeholder_to_b0_idx: dict[str, int] = {}

    for change in adds:
        new_idx = change.new_index or 0
        if new_idx in dependent_new_indices:
            continue  # goes to Batch 1

        adj_idx = new_idx - sum(1 for p in dependent_new_indices if p < new_idx)
        item = _clean_item_for_creation(change.new_item or {})
        req: dict[str, Any] = {
            "createItem": {
                "item": item,
                "location": {"index": adj_idx},
            }
        }

        # Track placeholder sections so Batch 1 can embed DeferredItemID.
        item_id = (change.new_item or {}).get("itemId")
        if item_id and item_id in referenced and "pageBreakItem" in item:
            placeholder_to_b0_idx[item_id] = len(batch0)

        batch0.append(req)

    # ------------------------------------------------------------------
    # Build Batch 1: dependent creates + updates + moves.
    #
    # Dependent creates use new_index directly because Batch 0 has already
    # inserted every non-dependent item into the form; the sequential
    # processing of Batch-1 creates (in new_index order) then places each
    # item at the correct final position.
    # ------------------------------------------------------------------
    batch1: list[dict[str, Any]] = []

    for change in adds:
        new_idx = change.new_index or 0
        if new_idx not in dependent_new_indices:
            continue

        item = copy.deepcopy(_clean_item_for_creation(change.new_item or {}))
        _embed_deferred_ids(item, referenced, placeholder_to_b0_idx, batch_index=0)
        batch1.append({"createItem": {"item": item, "location": {"index": new_idx}}})

    for change in diff.item_changes:
        if change.change_type != "update":
            continue
        item = copy.deepcopy(_clean_item_for_update(change.new_item or {}))
        _embed_deferred_ids(item, referenced, placeholder_to_b0_idx, batch_index=0)
        # Compute the item's actual position in the batch:
        # batch0 ran all deletes + non-dependent creates; batch1 runs dependent
        # creates first (those are in sorted adds order).  Passing all adds to
        # _update_item_index gives the correct count of creates inserted before
        # this item across both batches combined.
        idx = _update_item_index(change, deleted_indices, adds)
        batch1.append({
            "updateItem": {
                "item": item,
                "location": {"index": idx},
                "updateMask": "*",
            }
        })

    moves = [c for c in diff.item_changes if c.change_type == "move"]
    if moves:
        batch1.extend(_generate_smart_moves(diff.old_item_order, diff.new_item_order, deleted_indices))

    if batch1:
        return [batch0, batch1]
    return [batch0]


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _generate_update_form_info(info_changes: Any) -> dict[str, Any]:
    """Generate updateFormInfo request."""
    info: dict[str, Any] = {}
    new_info = info_changes.new_info

    for field in info_changes.update_mask.split(","):
        if field == "title" and "title" in new_info:
            info["title"] = new_info["title"]
        elif field == "description":
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
    item = _clean_item_for_creation(change.new_item or {})
    return {
        "createItem": {
            "item": item,
            "location": {"index": change.new_index},
        }
    }


def _generate_update_item(change: ItemChange, index: int) -> dict[str, Any]:
    """Generate updateItem request at *index*.

    The caller must supply the item's actual position within the batch at the
    time this request runs (i.e. after preceding deletes and creates have been
    applied), which may differ from ``change.new_index`` when the item is also
    being moved in the same batch.
    """
    item = _clean_item_for_update(change.new_item or {})
    return {
        "updateItem": {
            "item": item,
            "location": {"index": index},
            "updateMask": "*",
        }
    }


def _update_item_index(
    change: ItemChange,
    deleted_old_indices: set[int],
    sorted_adds: list[ItemChange],
) -> int:
    """Compute the correct location index for an updateItem request.

    ``generate_requests`` applies requests in this order: deletes → creates →
    updates → moves.  By the time an updateItem executes, all deletes and
    creates have already shifted item positions:

    * Each deleted item at an index *below* ``old_index`` shifts the item
      one slot towards index 0.
    * Each created item inserted at an index *at or below* the adjusted
      position shifts the item one slot up.

    Falls back to ``new_index`` when ``old_index`` is ``None`` (only for
    manually constructed :class:`ItemChange` objects in unit tests).
    """
    if change.old_index is None:
        return change.new_index or 0

    idx = change.old_index

    # Each deleted item at a lower index collapses our slot.
    for del_idx in deleted_old_indices:
        if del_idx < idx:
            idx -= 1

    # Each created item inserted at or before our adjusted position pushes us up.
    # Process in ascending new_index order so the threshold evolves correctly.
    for add in sorted_adds:
        if add.new_index is not None and add.new_index <= idx:
            idx += 1

    return idx


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

    working_order = [
        item_id for i, item_id in enumerate(old_item_order) if i not in deleted_indices
    ]

    existing_items = set(working_order)
    target_order = [item_id for item_id in new_item_order if item_id in existing_items]

    if working_order == target_order:
        return []

    requests: list[dict[str, Any]] = []

    for target_idx, target_item in enumerate(target_order):
        if target_idx >= len(working_order):
            break

        current_idx = working_order.index(target_item)

        if current_idx != target_idx:
            requests.append(
                {
                    "moveItem": {
                        "originalLocation": {"index": current_idx},
                        "newLocation": {"index": target_idx},
                    }
                }
            )
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
    cleaned.pop("itemId", None)

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


# ---------------------------------------------------------------------------
# Placeholder ID detection helpers
# ---------------------------------------------------------------------------


def _find_placeholder_section_ids(
    pristine_items: list[dict[str, Any]],
    current_items: list[dict[str, Any]],
) -> set[str]:
    """Return agent-chosen itemIds on new pageBreakItem sections.

    A placeholder ID is one that appears on a pageBreakItem in current_items
    but is absent from pristine_items (i.e., the API has not assigned it yet).
    """
    pristine_ids = {item.get("itemId") for item in pristine_items if item.get("itemId")}
    placeholders: set[str] = set()
    for item in current_items:
        item_id = item.get("itemId")
        if item_id and item_id not in pristine_ids and "pageBreakItem" in item:
            placeholders.add(item_id)
    return placeholders


def _find_referenced_placeholders(
    current_items: list[dict[str, Any]],
    placeholder_ids: set[str],
) -> set[str]:
    """Return the subset of placeholder_ids actually referenced by goToSectionId."""
    referenced: set[str] = set()
    for item in current_items:
        if "questionItem" not in item:
            continue
        question = item["questionItem"].get("question", {})
        if "choiceQuestion" not in question:
            continue
        for option in question["choiceQuestion"].get("options", []):
            goto_id = option.get("goToSectionId")
            if goto_id and goto_id in placeholder_ids:
                referenced.add(goto_id)
    return referenced


def _item_has_goto_placeholder(item: dict[str, Any], referenced: set[str]) -> bool:
    """Return True if *item* has any goToSectionId that is a referenced placeholder."""
    if "questionItem" not in item:
        return False
    question = item["questionItem"].get("question", {})
    if "choiceQuestion" not in question:
        return False
    for option in question["choiceQuestion"].get("options", []):
        if option.get("goToSectionId") in referenced:
            return True
    return False


def _embed_deferred_ids(
    item: dict[str, Any],
    referenced: set[str],
    placeholder_to_b0_idx: dict[str, int],
    batch_index: int,
) -> None:
    """Replace placeholder goToSectionId strings with DeferredItemID objects.

    Modifies *item* in place.  Caller must ensure *item* is a deep copy so
    that original form data is not mutated.
    """
    if "questionItem" not in item:
        return
    question = item["questionItem"].get("question", {})
    if "choiceQuestion" not in question:
        return
    for option in question["choiceQuestion"].get("options", []):
        goto_id = option.get("goToSectionId")
        if goto_id and goto_id in referenced:
            request_index = placeholder_to_b0_idx.get(goto_id)
            if request_index is not None:
                option["goToSectionId"] = DeferredItemID(
                    placeholder=goto_id,
                    batch_index=batch_index,
                    request_index=request_index,
                )
