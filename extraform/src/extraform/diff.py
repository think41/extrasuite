"""Diff engine for comparing form states."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class InfoChanges:
    """Changes to form info (title, description)."""

    old_info: dict[str, Any]
    new_info: dict[str, Any]
    update_mask: str  # Comma-separated field names

    @property
    def has_changes(self) -> bool:
        return bool(self.update_mask)


@dataclass
class SettingsChanges:
    """Changes to form settings."""

    old_settings: dict[str, Any]
    new_settings: dict[str, Any]
    update_mask: str

    @property
    def has_changes(self) -> bool:
        return bool(self.update_mask)


@dataclass
class ItemChange:
    """A single item change (add, delete, update, move)."""

    change_type: Literal["add", "delete", "update", "move"]
    item_id: str | None = None  # None for new items
    old_item: dict[str, Any] | None = None
    new_item: dict[str, Any] | None = None
    old_index: int | None = None
    new_index: int | None = None


@dataclass
class DiffResult:
    """Result of comparing two form states."""

    form_id: str
    info_changes: InfoChanges | None = None
    settings_changes: SettingsChanges | None = None
    item_changes: list[ItemChange] = field(default_factory=list)
    # Item IDs in pristine order (for move simulation)
    old_item_order: list[str] = field(default_factory=list)
    # Item IDs in current order (for move simulation)
    new_item_order: list[str] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        """Check if there are any changes."""
        if self.info_changes and self.info_changes.has_changes:
            return True
        if self.settings_changes and self.settings_changes.has_changes:
            return True
        return len(self.item_changes) > 0


def diff_forms(pristine: dict[str, Any], current: dict[str, Any]) -> DiffResult:
    """Compare two form structures and return changes.

    Args:
        pristine: The original form state.
        current: The current (edited) form state.

    Returns:
        A DiffResult containing all detected changes.
    """
    form_id = current.get("formId") or pristine.get("formId", "")

    # Diff form info
    info_changes = _diff_info(pristine.get("info", {}), current.get("info", {}))

    # Diff settings
    settings_changes = _diff_settings(pristine.get("settings", {}), current.get("settings", {}))

    # Diff items
    pristine_items = pristine.get("items", [])
    current_items = current.get("items", [])
    item_changes = _diff_items(pristine_items, current_items)

    # Build item order lists for move simulation
    old_item_order = [item.get("itemId", "") for item in pristine_items if item.get("itemId")]
    new_item_order = [item.get("itemId", "") for item in current_items if item.get("itemId")]

    return DiffResult(
        form_id=form_id,
        info_changes=info_changes,
        settings_changes=settings_changes,
        item_changes=item_changes,
        old_item_order=old_item_order,
        new_item_order=new_item_order,
    )


def _diff_info(old_info: dict[str, Any], new_info: dict[str, Any]) -> InfoChanges | None:
    """Compare form info sections."""
    changed_fields: list[str] = []

    # Check title
    if old_info.get("title") != new_info.get("title"):
        changed_fields.append("title")

    # Check description
    if old_info.get("description") != new_info.get("description"):
        changed_fields.append("description")

    # Note: documentTitle is read-only, don't diff it

    if not changed_fields:
        return None

    return InfoChanges(
        old_info=old_info,
        new_info=new_info,
        update_mask=",".join(changed_fields),
    )


def _diff_settings(
    old_settings: dict[str, Any], new_settings: dict[str, Any]
) -> SettingsChanges | None:
    """Compare form settings."""
    if old_settings == new_settings:
        return None

    # Build update mask from changed fields
    changed_fields: list[str] = []

    # Check quiz settings
    old_quiz = old_settings.get("quizSettings", {})
    new_quiz = new_settings.get("quizSettings", {})
    if old_quiz != new_quiz and old_quiz.get("isQuiz") != new_quiz.get("isQuiz"):
        changed_fields.append("quizSettings.isQuiz")

    # Check email collection
    if old_settings.get("emailCollectionType") != new_settings.get("emailCollectionType"):
        changed_fields.append("emailCollectionType")

    if not changed_fields:
        return None

    return SettingsChanges(
        old_settings=old_settings,
        new_settings=new_settings,
        update_mask=",".join(changed_fields),
    )


def _diff_items(
    pristine_items: list[dict[str, Any]], current_items: list[dict[str, Any]]
) -> list[ItemChange]:
    """Compare form items and detect changes.

    Strategy:
    1. Match items by itemId
    2. Detect additions (in current but not pristine, or items without itemId)
    3. Detect deletions (in pristine but not current)
    4. Detect updates (same item, different content)
    5. Detect moves (same item at different index)
    """
    changes: list[ItemChange] = []

    # Build maps of itemId -> (index, item) for items that have itemIds
    pristine_map: dict[str, tuple[int, dict[str, Any]]] = {}
    for i, item in enumerate(pristine_items):
        item_id = item.get("itemId")
        if item_id:
            pristine_map[item_id] = (i, item)

    current_map: dict[str, tuple[int, dict[str, Any]]] = {}
    for i, item in enumerate(current_items):
        item_id = item.get("itemId")
        if item_id:
            current_map[item_id] = (i, item)

    # Process all current items
    for curr_idx, curr_item in enumerate(current_items):
        item_id = curr_item.get("itemId")

        if item_id is None:
            # Item without itemId is always a new addition
            changes.append(
                ItemChange(
                    change_type="add",
                    item_id=None,  # Will be assigned by API
                    new_item=curr_item,
                    new_index=curr_idx,
                )
            )
        elif item_id in pristine_map:
            prist_idx, prist_item = pristine_map[item_id]

            # Check for content change
            if _item_content_changed(prist_item, curr_item):
                changes.append(
                    ItemChange(
                        change_type="update",
                        item_id=item_id,
                        old_item=prist_item,
                        new_item=curr_item,
                        old_index=prist_idx,
                        new_index=curr_idx,
                    )
                )
            # Check for position change only (no content change)
            elif prist_idx != curr_idx:
                changes.append(
                    ItemChange(
                        change_type="move",
                        item_id=item_id,
                        old_item=prist_item,
                        new_item=curr_item,
                        old_index=prist_idx,
                        new_index=curr_idx,
                    )
                )
        else:
            # Item with itemId that's not in pristine - treat as new
            changes.append(
                ItemChange(
                    change_type="add",
                    item_id=None,  # Will be assigned by API
                    new_item=curr_item,
                    new_index=curr_idx,
                )
            )

    # Detect deletions
    for item_id, (prist_idx, prist_item) in pristine_map.items():
        if item_id not in current_map:
            changes.append(
                ItemChange(
                    change_type="delete",
                    item_id=item_id,
                    old_item=prist_item,
                    old_index=prist_idx,
                )
            )

    return changes


def _item_content_changed(old_item: dict[str, Any], new_item: dict[str, Any]) -> bool:
    """Check if item content has changed (excluding position).

    We compare everything except itemId since that's the identity.
    """
    # Create copies without itemId for comparison
    old_copy = {k: v for k, v in old_item.items() if k != "itemId"}
    new_copy = {k: v for k, v in new_item.items() if k != "itemId"}

    return old_copy != new_copy
