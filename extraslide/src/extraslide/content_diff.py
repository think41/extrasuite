"""Diff algorithm for the new content format.

Compares pristine vs edited content and generates change operations.
Key feature: Detects copy operations when the LLM duplicates elements.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from extraslide.content_parser import (
    ParsedElement,
    flatten_elements,
    parse_slide_content,
)


class ChangeType(Enum):
    """Types of changes detected."""

    # Element was deleted
    DELETE = "delete"

    # Element position changed
    MOVE = "move"

    # Element text changed
    TEXT_UPDATE = "text_update"

    # Element was copied from another element
    COPY = "copy"

    # Truly new element (no source)
    CREATE = "create"


@dataclass
class Change:
    """A single change operation."""

    change_type: ChangeType

    # Target element ID (clean_id)
    target_id: str

    # For COPY: source element ID
    source_id: str | None = None

    # For MOVE: new position
    new_position: dict[str, float] | None = None

    # For TEXT_UPDATE: new text
    new_text: list[str] | None = None

    # Slide index where this change occurs
    slide_index: str | None = None

    # Parent element ID (for hierarchy reconstruction)
    parent_id: str | None = None

    # For GROUP COPY: list of child elements (recursive structure)
    # Each child is a dict with: id, tag, position (relative), text, children
    children: list[dict[str, Any]] | None = None

    # Element tag (for creates/copies)
    tag: str | None = None

    # Additional metadata
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DiffResult:
    """Result of diffing pristine vs edited content."""

    changes: list[Change] = field(default_factory=list)

    # Elements by ID in edited version (for reconstruction)
    edited_elements: dict[str, ParsedElement] = field(default_factory=dict)

    # Styles from pristine (for copy operations)
    pristine_styles: dict[str, dict[str, Any]] = field(default_factory=dict)


def diff_presentation(
    pristine_slides: dict[str, list[ParsedElement]],
    edited_slides: dict[str, list[ParsedElement]],
    pristine_styles: dict[str, dict[str, Any]],
    _id_mapping: dict[str, str],
) -> DiffResult:
    """Diff pristine and edited presentation content.

    Detects:
    - Deleted elements
    - Moved elements (position changed)
    - Text updates
    - Copied elements (duplicate IDs in edited)
    - New elements

    Args:
        pristine_slides: Original slide content (from pull)
        edited_slides: Modified slide content (after LLM edits)
        pristine_styles: Original styles.json
        id_mapping: Original id_mapping.json

    Returns:
        DiffResult with all detected changes
    """
    result = DiffResult(pristine_styles=pristine_styles)

    # Flatten pristine elements
    pristine_elements: dict[str, ParsedElement] = {}
    pristine_slide_map: dict[str, str] = {}  # element_id -> slide_index
    for slide_idx, roots in pristine_slides.items():
        flattened = flatten_elements(roots)
        for elem_id, elem in flattened.items():
            pristine_elements[elem_id] = elem
            pristine_slide_map[elem_id] = slide_idx

    # Flatten edited elements, tracking duplicates
    # Note: We can't use flatten_elements because it returns a dict which loses duplicates
    edited_elements: dict[
        str, list[tuple[str, ParsedElement]]
    ] = {}  # id -> [(slide_idx, elem)]
    for slide_idx, roots in edited_slides.items():
        all_elements = _collect_all_elements(roots)
        for elem in all_elements:
            if elem.clean_id:
                if elem.clean_id not in edited_elements:
                    edited_elements[elem.clean_id] = []
                edited_elements[elem.clean_id].append((slide_idx, elem))

    # Store first instance of each edited element for reconstruction
    for elem_id, instances in edited_elements.items():
        if instances:
            result.edited_elements[elem_id] = instances[0][1]

    # Known IDs from pristine (these are original elements)
    known_ids = set(pristine_elements.keys())

    # First pass: identify which elements are being copied as groups
    # We need to skip children of copied groups to avoid duplicates
    copied_group_ids: set[str] = set()
    copied_group_descendant_ids: set[str] = set()

    for elem_id, instances in edited_elements.items():
        if elem_id in known_ids and len(instances) > 1:
            # This is a copy - check if it's a group with children
            for _, edited_elem in instances[1:]:  # Skip first (original)
                if edited_elem.children:
                    copied_group_ids.add(elem_id)
                    # Collect all descendant IDs
                    _collect_descendant_ids(edited_elem, copied_group_descendant_ids)

    # Detect changes
    for elem_id, instances in edited_elements.items():
        # Skip elements that are descendants of a copied group
        if elem_id in copied_group_descendant_ids:
            continue

        if elem_id in known_ids:
            # This ID existed in pristine
            pristine_elem = pristine_elements[elem_id]

            if len(instances) == 1:
                # Single instance - check for modifications
                slide_idx, edited_elem = instances[0]
                changes = _compare_elements(pristine_elem, edited_elem, slide_idx)
                result.changes.extend(changes)
            else:
                # Multiple instances - first is original, rest are copies
                for i, (slide_idx, edited_elem) in enumerate(instances):
                    if i == 0:
                        # Original - check for modifications
                        changes = _compare_elements(
                            pristine_elem, edited_elem, slide_idx
                        )
                        result.changes.extend(changes)
                    else:
                        # Copy! Include children for groups
                        children_data = None
                        if edited_elem.children:
                            children_data = _serialize_children(edited_elem.children)

                        result.changes.append(
                            Change(
                                change_type=ChangeType.COPY,
                                target_id=f"{elem_id}_copy{i}",
                                source_id=elem_id,
                                slide_index=slide_idx,
                                parent_id=edited_elem.parent_id,
                                new_position=_get_position(edited_elem),
                                new_text=edited_elem.paragraphs
                                if edited_elem.paragraphs
                                else None,
                                children=children_data,
                                tag=edited_elem.tag,
                            )
                        )
        else:
            # ID doesn't exist in pristine
            # Check if it looks like it was copied from another element
            for slide_idx, edited_elem in instances:
                # For now, treat as new element
                # Could enhance to detect copies by content similarity
                result.changes.append(
                    Change(
                        change_type=ChangeType.CREATE,
                        target_id=elem_id,
                        slide_index=slide_idx,
                        parent_id=edited_elem.parent_id,
                        new_position=_get_position(edited_elem),
                        new_text=edited_elem.paragraphs
                        if edited_elem.paragraphs
                        else None,
                        metadata={"tag": edited_elem.tag},
                    )
                )

    # Detect deletions
    for elem_id in known_ids:
        if elem_id not in edited_elements:
            slide_idx = pristine_slide_map.get(elem_id, "")
            result.changes.append(
                Change(
                    change_type=ChangeType.DELETE,
                    target_id=elem_id,
                    slide_index=slide_idx,
                )
            )

    return result


def _compare_elements(
    pristine: ParsedElement,
    edited: ParsedElement,
    slide_idx: str,
) -> list[Change]:
    """Compare two elements with the same ID and generate changes."""
    changes: list[Change] = []

    # Check position change (only for root elements)
    if (
        pristine.has_position
        and edited.has_position
        and (
            pristine.x != edited.x
            or pristine.y != edited.y
            or pristine.w != edited.w
            or pristine.h != edited.h
        )
    ):
        changes.append(
            Change(
                change_type=ChangeType.MOVE,
                target_id=pristine.clean_id,
                slide_index=slide_idx,
                new_position=_get_position(edited),
            )
        )

    # Check text change
    if pristine.paragraphs != edited.paragraphs:
        changes.append(
            Change(
                change_type=ChangeType.TEXT_UPDATE,
                target_id=pristine.clean_id,
                slide_index=slide_idx,
                new_text=edited.paragraphs,
            )
        )

    return changes


def _serialize_children(children: list[ParsedElement]) -> list[dict[str, Any]]:
    """Serialize children elements for inclusion in a Change.

    This captures all the information needed to recreate the children
    when generating copy requests.
    """
    result: list[dict[str, Any]] = []

    for child in children:
        child_data: dict[str, Any] = {
            "id": child.clean_id,
            "tag": child.tag,
        }

        # Include position if available
        if child.has_position:
            child_data["position"] = {
                "x": child.x,
                "y": child.y,
                "w": child.w,
                "h": child.h,
            }

        # Include text if available
        if child.paragraphs:
            child_data["text"] = child.paragraphs

        # Recursively include nested children
        if child.children:
            child_data["children"] = _serialize_children(child.children)

        result.append(child_data)

    return result


def _collect_all_elements(roots: list[ParsedElement]) -> list[ParsedElement]:
    """Collect all elements from a tree, including duplicates.

    Unlike flatten_elements which returns a dict (losing duplicates),
    this returns a list preserving all elements including duplicates.
    """
    result: list[ParsedElement] = []

    def _collect(elem: ParsedElement) -> None:
        result.append(elem)
        for child in elem.children:
            _collect(child)

    for root in roots:
        _collect(root)

    return result


def _collect_descendant_ids(elem: ParsedElement, result: set[str]) -> None:
    """Recursively collect IDs of all descendants of an element.

    This is used to identify children of copied groups so we don't
    create duplicate copies of them as top-level elements.
    """
    for child in elem.children:
        if child.clean_id:
            result.add(child.clean_id)
        _collect_descendant_ids(child, result)


def _get_position(elem: ParsedElement) -> dict[str, float] | None:
    """Extract position dictionary from element."""
    if not elem.has_position:
        return None
    return {
        "x": elem.x or 0,
        "y": elem.y or 0,
        "w": elem.w or 0,
        "h": elem.h or 0,
    }


def diff_slide_content(
    pristine_content: str,
    edited_content: str,
    pristine_styles: dict[str, dict[str, Any]],
    slide_index: str,
) -> list[Change]:
    """Diff a single slide's content.

    Convenience function for diffing one slide at a time.

    Args:
        pristine_content: Original content.sml
        edited_content: Modified content.sml
        pristine_styles: Styles from original styles.json
        slide_index: The slide index (e.g., "01")

    Returns:
        List of changes for this slide
    """
    pristine_elements = parse_slide_content(pristine_content)
    edited_elements = parse_slide_content(edited_content)

    result = diff_presentation(
        {slide_index: pristine_elements},
        {slide_index: edited_elements},
        pristine_styles,
        {},
    )

    return result.changes
