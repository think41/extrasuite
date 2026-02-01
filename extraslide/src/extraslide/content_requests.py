"""Generate Google Slides API requests from diff changes.

Converts Change operations to batchUpdate request objects.
Key feature: Handles copy operations by recreating elements with source styles.
"""

from __future__ import annotations

import time
from typing import Any

from extraslide.content_diff import Change, ChangeType, DiffResult
from extraslide.units import pt_to_emu

# Global counter for unique ID generation within a session
_id_counter = 0


def _get_unique_suffix() -> str:
    """Generate a unique suffix for object IDs."""
    global _id_counter
    _id_counter += 1
    # Use timestamp (last 6 digits) + counter for uniqueness
    ts = int(time.time() * 1000) % 1000000
    return f"{ts}_{_id_counter}"


def generate_batch_requests(
    diff_result: DiffResult,
    id_mapping: dict[str, str],
    slide_id_mapping: dict[str, str],
    _pristine_element_types: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Generate batchUpdate requests from diff result.

    Args:
        diff_result: Result from diff_presentation()
        id_mapping: clean_id -> google_object_id mapping
        slide_id_mapping: slide_index (e.g., "01") -> google_slide_id mapping
        pristine_element_types: Optional mapping of google_id -> element_type
            Used to skip deleting groups (which auto-delete when empty)

    Returns:
        List of Google Slides API batchUpdate request objects
    """
    requests: list[dict[str, Any]] = []

    # Make a mutable copy of slide_id_mapping for adding new slides
    slide_ids = dict(slide_id_mapping)

    # Process changes in order: deletes first, then modifications, then creates/copies
    # This ensures space is freed before new elements are created

    # Group changes by type
    deletes = [c for c in diff_result.changes if c.change_type == ChangeType.DELETE]
    moves = [c for c in diff_result.changes if c.change_type == ChangeType.MOVE]
    text_updates = [
        c for c in diff_result.changes if c.change_type == ChangeType.TEXT_UPDATE
    ]
    copies = [c for c in diff_result.changes if c.change_type == ChangeType.COPY]
    creates = [c for c in diff_result.changes if c.change_type == ChangeType.CREATE]

    # Detect new slides needed
    # Check all copies and creates for slides not in slide_ids
    new_slide_indices: set[str] = set()
    for change in copies + creates:
        if change.slide_index and change.slide_index not in slide_ids:
            new_slide_indices.add(change.slide_index)

    # Generate createSlide requests for new slides (in order)
    for slide_index in sorted(new_slide_indices):
        new_slide_id = f"new_slide_{slide_index}"
        requests.append(_create_slide_request(new_slide_id))
        slide_ids[slide_index] = new_slide_id

    # Generate delete requests
    # Order: deepest leaves first, then root shapes (groups auto-delete when empty)
    delete_ids = {
        id_mapping.get(c.target_id) for c in deletes if id_mapping.get(c.target_id)
    }
    ordered_delete_ids = _order_deletes_for_safe_removal(delete_ids)

    for google_id in ordered_delete_ids:
        requests.append(
            {
                "deleteObject": {
                    "objectId": google_id,
                }
            }
        )

    # Generate move requests (updatePageElementTransform)
    for change in moves:
        move_google_id = id_mapping.get(change.target_id)
        if move_google_id and change.new_position:
            requests.append(_create_move_request(move_google_id, change.new_position))

    # Generate text update requests
    for change in text_updates:
        text_google_id = id_mapping.get(change.target_id)
        if text_google_id and change.new_text is not None:
            text_requests = _create_text_update_requests(
                text_google_id, change.new_text
            )
            requests.extend(text_requests)

    # Generate copy requests (recreate elements with source styles)
    for change in copies:
        if change.source_id and change.slide_index:
            slide_google_id = slide_ids.get(change.slide_index)
            source_google_id = id_mapping.get(change.source_id)
            source_style = diff_result.pristine_styles.get(change.source_id, {})

            if slide_google_id and source_google_id:
                copy_requests = _create_copy_requests(
                    change,
                    source_style,
                    slide_google_id,
                    diff_result.pristine_styles,
                )
                requests.extend(copy_requests)

    # Generate create requests (new elements)
    for change in creates:
        if change.slide_index:
            slide_google_id = slide_ids.get(change.slide_index)
            if slide_google_id:
                create_requests = _create_element_requests(change, slide_google_id)
                requests.extend(create_requests)

    return requests


def _order_deletes_for_safe_removal(delete_ids: set[str | None]) -> list[str]:
    """Order deletes to safely remove all elements.

    Google Slides behavior:
    - Deleting a group UNGROUPS its children (doesn't delete them)
    - A group auto-deletes when all its children are deleted

    Strategy:
    1. Delete leaf elements first (deepest children)
    2. Parent groups auto-delete as they become empty
    3. Delete root-level shapes last (they don't auto-delete)

    We skip deleting parent groups explicitly since they'll auto-delete.
    But we DO delete root shapes (depth 0) which don't auto-delete.

    Args:
        delete_ids: Set of Google object IDs to delete

    Returns:
        Ordered list: deepest leaves first, then root shapes
    """
    valid_ids = {id for id in delete_ids if id is not None}

    def get_depth(id: str) -> int:
        return id.count("_c")

    # Separate into:
    # 1. Leaf elements (no children) - will be deleted
    # 2. Parent elements (have children) - will auto-delete when empty
    # 3. Root shapes (depth 0, no children) - must delete explicitly

    leaf_ids: list[str] = []
    root_shapes: list[str] = []

    for id in valid_ids:
        is_parent = False
        for other_id in valid_ids:
            if other_id != id and other_id.startswith(id + "_c"):
                is_parent = True
                break

        depth = get_depth(id)
        if not is_parent:
            if depth == 0:
                # Root-level shape - delete last
                root_shapes.append(id)
            else:
                # Leaf child - delete first
                leaf_ids.append(id)

    # Sort leaves by depth descending, then add root shapes at the end
    sorted_leaves = sorted(leaf_ids, key=get_depth, reverse=True)
    return sorted_leaves + root_shapes


def _create_slide_request(slide_id: str) -> dict[str, Any]:
    """Create a createSlide request."""
    return {
        "createSlide": {
            "objectId": slide_id,
            # Insert at the end (no insertionIndex means end)
        }
    }


def _create_move_request(google_id: str, position: dict[str, float]) -> dict[str, Any]:
    """Create updatePageElementTransform request."""
    return {
        "updatePageElementTransform": {
            "objectId": google_id,
            "transform": {
                "scaleX": 1,
                "scaleY": 1,
                "translateX": pt_to_emu(position["x"]),
                "translateY": pt_to_emu(position["y"]),
                "unit": "EMU",
            },
            "applyMode": "ABSOLUTE",
        }
    }


def _create_text_update_requests(
    google_id: str,
    new_text: list[str],
) -> list[dict[str, Any]]:
    """Create requests to update element text.

    Strategy: Delete all existing text, then insert new text.
    """
    requests: list[dict[str, Any]] = []

    # Delete all existing text
    requests.append(
        {
            "deleteText": {
                "objectId": google_id,
                "textRange": {
                    "type": "ALL",
                },
            }
        }
    )

    # Insert new text (join paragraphs with newlines)
    if new_text:
        combined_text = "\n".join(new_text)
        requests.append(
            {
                "insertText": {
                    "objectId": google_id,
                    "insertionIndex": 0,
                    "text": combined_text,
                }
            }
        )

    return requests


def _create_copy_requests(
    change: Change,
    source_style: dict[str, Any],
    slide_google_id: str,
    all_styles: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Create requests to copy an element.

    Since duplicateObject only works on same slide, we recreate
    the element with properties from the source.

    For groups, recursively creates all children and then groups them.
    Uses translation (dx, dy) from change to calculate child positions.
    """
    requests: list[dict[str, Any]] = []

    # Determine element type from source style
    elem_type = source_style.get("type", "RECTANGLE")

    # Use the new position if provided, otherwise use source position
    position = change.new_position
    if not position:
        source_pos = source_style.get("position", {})
        position = {
            "x": source_pos.get("x", 0),
            "y": source_pos.get("y", 0),
            "w": source_pos.get("w", 100),
            "h": source_pos.get("h", 100),
        }

    # Get translation for child positioning
    translation = change.translation or {"dx": 0, "dy": 0}

    # Generate a unique object ID for the new element
    # Include slide index and unique suffix to avoid collisions with existing IDs
    suffix = _get_unique_suffix()
    new_object_id = f"copy_{change.slide_index}_{suffix}"

    # Create element based on type
    # Special types: LINE, IMAGE, GROUP need special handling
    # Everything else is a shape that can be created with createShape

    if elem_type == "LINE":
        requests.append(
            _create_line_request(
                new_object_id,
                slide_google_id,
                position,
            )
        )

        # Apply line styling
        style_requests = _apply_line_style_requests(new_object_id, source_style)
        requests.extend(style_requests)

    elif elem_type == "IMAGE":
        # Images need special handling - need the source URL
        content_url = source_style.get("contentUrl", "")
        if content_url:
            requests.append(
                _create_image_request(
                    new_object_id,
                    slide_google_id,
                    position,
                    content_url,
                    native_size=source_style.get("nativeSize"),
                    native_scale=source_style.get("nativeScale"),
                )
            )
            # Apply image properties like transparency
            image_style_requests = _apply_image_style_requests(
                new_object_id, source_style
            )
            requests.extend(image_style_requests)

        # Handle visual children for images (e.g., cropped images)
        if change.children:
            _create_children_from_data(
                change.children,
                translation,
                slide_google_id,
                all_styles,
                requests,
                new_object_id,
            )

    elif elem_type == "GROUP":
        # Create children first, then group them
        if change.children:
            child_ids = _create_children_from_data(
                change.children,
                translation,
                slide_google_id,
                all_styles,
                requests,
                new_object_id,
            )
            # Group the children together
            if child_ids:
                requests.append(
                    {
                        "groupObjects": {
                            "groupObjectId": new_object_id,
                            "childrenObjectIds": child_ids,
                        }
                    }
                )

    else:
        # All other types are shapes (RECTANGLE, TEXT_BOX, ROUND_RECTANGLE, etc.)
        requests.append(
            _create_shape_request(
                new_object_id,
                slide_google_id,
                elem_type,
                position,
            )
        )

        # Apply styling from source
        style_requests = _apply_style_requests(new_object_id, source_style)
        requests.extend(style_requests)

        # Add text if provided
        if change.new_text:
            text_requests = _create_text_insert_requests(new_object_id, change.new_text)
            requests.extend(text_requests)
            # Apply text styling from source
            text_style_info = source_style.get("text", {})
            if text_style_info:
                text_style_reqs = _apply_text_style_requests(
                    new_object_id, change.new_text, text_style_info
                )
                requests.extend(text_style_reqs)

        # Handle visual children (any element can have children in our format)
        if change.children:
            _create_children_from_data(
                change.children,
                translation,
                slide_google_id,
                all_styles,
                requests,
                new_object_id,
            )

    return requests


def _create_children_from_data(
    children: list[dict[str, Any]],
    translation: dict[str, float],
    slide_google_id: str,
    all_styles: dict[str, dict[str, Any]],
    requests: list[dict[str, Any]],
    id_prefix: str,
    depth: int = 0,
) -> list[str]:
    """Create child elements from serialized children data.

    Uses translation-based positioning:
    - Children have their original absolute positions in child_data["position"]
    - New position = original position + translation (dx, dy)

    Args:
        children: List of child data dicts from Change.children
        translation: Translation offset {"dx": float, "dy": float}
        slide_google_id: Target slide ID
        all_styles: All element styles for styling lookup
        requests: List to append requests to
        id_prefix: Prefix for generated object IDs
        depth: Recursion depth

    Returns:
        List of created child object IDs
    """
    child_ids: list[str] = []
    dx = translation.get("dx", 0)
    dy = translation.get("dy", 0)

    for i, child_data in enumerate(children):
        child_obj_id = f"{id_prefix}_c{depth}_{i}"
        child_tag = child_data.get("tag", "Rect")
        child_text = child_data.get("text", [])
        nested_children = child_data.get("children", [])

        # Get style for this child from all_styles
        source_id = child_data.get("id", "")
        child_style = all_styles.get(source_id, {})

        # Calculate new position using translation
        # Children have absolute positions in child_data["position"]
        # New position = original position + translation
        child_orig_pos = child_data.get("position", {})
        if child_orig_pos:
            abs_position = {
                "x": child_orig_pos.get("x", 0) + dx,
                "y": child_orig_pos.get("y", 0) + dy,
                "w": child_orig_pos.get("w", 50),
                "h": child_orig_pos.get("h", 50),
            }
        else:
            # Fallback: use style's position if child_data doesn't have position
            style_pos = child_style.get("position", {})
            abs_position = {
                "x": style_pos.get("x", 0) + dx,
                "y": style_pos.get("y", 0) + dy,
                "w": style_pos.get("w", 50),
                "h": style_pos.get("h", 50),
            }

        # Map tag to element type
        elem_type = _tag_to_type(child_tag)

        if elem_type == "GROUP" and nested_children:
            # Create children first, then group them
            # Pass the same translation - children already have absolute positions
            nested_child_ids = _create_children_from_data(
                nested_children,
                translation,
                slide_google_id,
                all_styles,
                requests,
                child_obj_id,
                depth + 1,
            )
            # Group the nested children together
            if nested_child_ids:
                requests.append(
                    {
                        "groupObjects": {
                            "groupObjectId": child_obj_id,
                            "childrenObjectIds": nested_child_ids,
                        }
                    }
                )
                child_ids.append(child_obj_id)
        elif elem_type == "LINE":
            requests.append(
                _create_line_request(child_obj_id, slide_google_id, abs_position)
            )
            style_reqs = _apply_line_style_requests(child_obj_id, child_style)
            requests.extend(style_reqs)
            child_ids.append(child_obj_id)
            # Process nested children for lines too
            if nested_children:
                _create_children_from_data(
                    nested_children,
                    translation,
                    slide_google_id,
                    all_styles,
                    requests,
                    child_obj_id,
                    depth + 1,
                )
        elif elem_type == "IMAGE":
            content_url = child_style.get("contentUrl", "")
            if content_url:
                requests.append(
                    _create_image_request(
                        child_obj_id,
                        slide_google_id,
                        abs_position,
                        content_url,
                        native_size=child_style.get("nativeSize"),
                        native_scale=child_style.get("nativeScale"),
                    )
                )
                # Apply image properties like transparency
                image_style_reqs = _apply_image_style_requests(
                    child_obj_id, child_style
                )
                requests.extend(image_style_reqs)
                child_ids.append(child_obj_id)
            # Process nested children for images too (e.g. cropped images)
            if nested_children:
                _create_children_from_data(
                    nested_children,
                    translation,
                    slide_google_id,
                    all_styles,
                    requests,
                    child_obj_id,
                    depth + 1,
                )
        else:
            # Shape types (RECTANGLE, TEXT_BOX, ROUND_RECTANGLE, etc.)
            requests.append(
                _create_shape_request(
                    child_obj_id, slide_google_id, elem_type, abs_position
                )
            )
            style_reqs = _apply_style_requests(child_obj_id, child_style)
            requests.extend(style_reqs)
            # Add text if any
            if child_text:
                text_reqs = _create_text_insert_requests(child_obj_id, child_text)
                requests.extend(text_reqs)
                # Apply text styling from source
                text_style_info = child_style.get("text", {})
                if text_style_info:
                    text_style_reqs = _apply_text_style_requests(
                        child_obj_id, child_text, text_style_info
                    )
                    requests.extend(text_style_reqs)
            child_ids.append(child_obj_id)
            # Process nested children for shapes (visual containment)
            if nested_children:
                _create_children_from_data(
                    nested_children,
                    translation,
                    slide_google_id,
                    all_styles,
                    requests,
                    child_obj_id,
                    depth + 1,
                )

    return child_ids


def _tag_to_type(tag: str) -> str:
    """Convert content.sml tag to Google Slides element type.

    Reverse mapping of content_generator._get_tag_name().
    Supports the full spectrum of Google Slides shape types.
    """
    tag_map = {
        # Basic shapes
        "Rect": "RECTANGLE",
        "Ellipse": "ELLIPSE",
        "RoundRect": "ROUND_RECTANGLE",
        "TextBox": "TEXT_BOX",
        "Image": "IMAGE",
        "Line": "LINE",
        "Group": "GROUP",
        "Table": "TABLE",
        "Video": "VIDEO",
        "Chart": "SHEETS_CHART",
        # Triangles
        "Triangle": "TRIANGLE",
        "RightTriangle": "RIGHT_TRIANGLE",
        # Parallelograms
        "Parallelogram": "PARALLELOGRAM",
        "Trapezoid": "TRAPEZOID",
        # Polygons
        "Pentagon": "PENTAGON",
        "Hexagon": "HEXAGON",
        "Heptagon": "HEPTAGON",
        "Octagon": "OCTAGON",
        "Decagon": "DECAGON",
        "Dodecagon": "DODECAGON",
        # Stars
        "Star4": "STAR_4",
        "Star5": "STAR_5",
        "Star6": "STAR_6",
        "Star8": "STAR_8",
        "Star10": "STAR_10",
        "Star12": "STAR_12",
        "Star16": "STAR_16",
        "Star24": "STAR_24",
        "Star32": "STAR_32",
        # Other shapes
        "Diamond": "DIAMOND",
        "Chevron": "CHEVRON",
        "HomePlate": "HOME_PLATE",
        "Plus": "PLUS",
        "Donut": "DONUT",
        "Pie": "PIE",
        "Arc": "ARC",
        "Chord": "CHORD",
        "BlockArc": "BLOCK_ARC",
        "Frame": "FRAME",
        "HalfFrame": "HALF_FRAME",
        "Corner": "CORNER",
        "DiagonalStripe": "DIAGONAL_STRIPE",
        "LShape": "L_SHAPE",
        "Can": "CAN",
        "Cube": "CUBE",
        "Bevel": "BEVEL",
        "FoldedCorner": "FOLDED_CORNER",
        "SmileyFace": "SMILEY_FACE",
        "Heart": "HEART",
        "LightningBolt": "LIGHTNING_BOLT",
        "Sun": "SUN",
        "Moon": "MOON",
        "Cloud": "CLOUD",
        "Plaque": "PLAQUE",
        # Arrows
        "Arrow": "ARROW",
        "ArrowLeft": "LEFT_ARROW",
        "ArrowRight": "RIGHT_ARROW",
        "ArrowUp": "UP_ARROW",
        "ArrowDown": "DOWN_ARROW",
        "ArrowLeftRight": "LEFT_RIGHT_ARROW",
        "ArrowUpDown": "UP_DOWN_ARROW",
        "ArrowQuad": "QUAD_ARROW",
        "ArrowLeftRightUp": "LEFT_RIGHT_UP_ARROW",
        "ArrowBent": "BENT_ARROW",
        "ArrowUTurn": "U_TURN_ARROW",
        "ArrowCurvedLeft": "CURVED_LEFT_ARROW",
        "ArrowCurvedRight": "CURVED_RIGHT_ARROW",
        "ArrowCurvedUp": "CURVED_UP_ARROW",
        "ArrowCurvedDown": "CURVED_DOWN_ARROW",
        "ArrowStripedRight": "STRIPED_RIGHT_ARROW",
        "ArrowNotchedRight": "NOTCHED_RIGHT_ARROW",
        "ArrowPentagon": "PENTAGON_ARROW",
        "ArrowChevron": "CHEVRON_ARROW",
        "ArrowCircular": "CIRCULAR_ARROW",
        # Callouts
        "CalloutRect": "WEDGE_RECTANGLE_CALLOUT",
        "CalloutRoundRect": "WEDGE_ROUND_RECTANGLE_CALLOUT",
        "CalloutEllipse": "WEDGE_ELLIPSE_CALLOUT",
        "CalloutCloud": "CLOUD_CALLOUT",
        # Flowchart shapes
        "FlowProcess": "FLOW_CHART_PROCESS",
        "FlowDecision": "FLOW_CHART_DECISION",
        "FlowInputOutput": "FLOW_CHART_INPUT_OUTPUT",
        "FlowPredefinedProcess": "FLOW_CHART_PREDEFINED_PROCESS",
        "FlowInternalStorage": "FLOW_CHART_INTERNAL_STORAGE",
        "FlowDocument": "FLOW_CHART_DOCUMENT",
        "FlowMultidocument": "FLOW_CHART_MULTIDOCUMENT",
        "FlowTerminator": "FLOW_CHART_TERMINATOR",
        "FlowPreparation": "FLOW_CHART_PREPARATION",
        "FlowManualInput": "FLOW_CHART_MANUAL_INPUT",
        "FlowManualOperation": "FLOW_CHART_MANUAL_OPERATION",
        "FlowConnector": "FLOW_CHART_CONNECTOR",
        "FlowPunchedCard": "FLOW_CHART_PUNCHED_CARD",
        "FlowPunchedTape": "FLOW_CHART_PUNCHED_TAPE",
        "FlowSummingJunction": "FLOW_CHART_SUMMING_JUNCTION",
        "FlowOr": "FLOW_CHART_OR",
        "FlowCollate": "FLOW_CHART_COLLATE",
        "FlowSort": "FLOW_CHART_SORT",
        "FlowExtract": "FLOW_CHART_EXTRACT",
        "FlowMerge": "FLOW_CHART_MERGE",
        "FlowOnlineStorage": "FLOW_CHART_ONLINE_STORAGE",
        "FlowMagneticTape": "FLOW_CHART_MAGNETIC_TAPE",
        "FlowMagneticDisk": "FLOW_CHART_MAGNETIC_DISK",
        "FlowMagneticDrum": "FLOW_CHART_MAGNETIC_DRUM",
        "FlowDisplay": "FLOW_CHART_DISPLAY",
        "FlowDelay": "FLOW_CHART_DELAY",
        "FlowAlternateProcess": "FLOW_CHART_ALTERNATE_PROCESS",
        "FlowOffpageConnector": "FLOW_CHART_OFFPAGE_CONNECTOR",
        "FlowData": "FLOW_CHART_DATA",
        # Equation shapes
        "MathPlus": "MATH_PLUS",
        "MathMinus": "MATH_MINUS",
        "MathMultiply": "MATH_MULTIPLY",
        "MathDivide": "MATH_DIVIDE",
        "MathEqual": "MATH_EQUAL",
        "MathNotEqual": "MATH_NOT_EQUAL",
        # Brackets
        "BracketLeft": "LEFT_BRACKET",
        "BracketRight": "RIGHT_BRACKET",
        "BraceLeft": "LEFT_BRACE",
        "BraceRight": "RIGHT_BRACE",
        "BracketPair": "BRACKET_PAIR",
        "BracePair": "BRACE_PAIR",
        # Ribbons and banners
        "Ribbon": "RIBBON",
        "Ribbon2": "RIBBON_2",
        # Rounded rectangles variants
        "SnipRoundRect": "SNIP_ROUND_RECTANGLE",
        "Snip2SameRect": "SNIP_2_SAME_RECTANGLE",
        "Snip2DiagRect": "SNIP_2_DIAGONAL_RECTANGLE",
        "Round1Rect": "ROUND_1_RECTANGLE",
        "Round2SameRect": "ROUND_2_SAME_RECTANGLE",
        "Round2DiagRect": "ROUND_2_DIAGONAL_RECTANGLE",
        # Custom/unknown
        "Custom": "CUSTOM",
        "Shape": "SHAPE",
    }
    return tag_map.get(tag, "RECTANGLE")


def _create_shape_request(
    object_id: str,
    slide_id: str,
    shape_type: str,
    position: dict[str, float],
) -> dict[str, Any]:
    """Create a createShape request.

    Google Slides internally uses a base size of 3000024 EMU (236.2 pt) for shapes
    and applies scale factors to achieve the desired visual size. We calculate
    the scale factors to match the requested size.
    """
    # If shape_type is already a valid Google shape type (uppercase with underscores),
    # use it directly. Otherwise, fall back to RECTANGLE.
    # Valid Google shape types are uppercase like RECTANGLE, ROUND_RECTANGLE, etc.
    valid_google_types = {
        "RECTANGLE",
        "ELLIPSE",
        "ROUND_RECTANGLE",
        "TEXT_BOX",
        "TRIANGLE",
        "RIGHT_TRIANGLE",
        "PARALLELOGRAM",
        "TRAPEZOID",
        "PENTAGON",
        "HEXAGON",
        "HEPTAGON",
        "OCTAGON",
        "DECAGON",
        "DODECAGON",
        "STAR_4",
        "STAR_5",
        "STAR_6",
        "STAR_8",
        "STAR_10",
        "STAR_12",
        "STAR_16",
        "STAR_24",
        "STAR_32",
        "DIAMOND",
        "CHEVRON",
        "HOME_PLATE",
        "PLUS",
        "DONUT",
        "PIE",
        "ARC",
        "CHORD",
        "BLOCK_ARC",
        "FRAME",
        "HALF_FRAME",
        "CORNER",
        "DIAGONAL_STRIPE",
        "L_SHAPE",
        "CAN",
        "CUBE",
        "BEVEL",
        "FOLDED_CORNER",
        "SMILEY_FACE",
        "HEART",
        "LIGHTNING_BOLT",
        "SUN",
        "MOON",
        "CLOUD",
        "PLAQUE",
        "ARROW",
        "LEFT_ARROW",
        "RIGHT_ARROW",
        "UP_ARROW",
        "DOWN_ARROW",
        "LEFT_RIGHT_ARROW",
        "UP_DOWN_ARROW",
        "QUAD_ARROW",
        "LEFT_RIGHT_UP_ARROW",
        "BENT_ARROW",
        "U_TURN_ARROW",
        "CURVED_LEFT_ARROW",
        "CURVED_RIGHT_ARROW",
        "CURVED_UP_ARROW",
        "CURVED_DOWN_ARROW",
        "STRIPED_RIGHT_ARROW",
        "NOTCHED_RIGHT_ARROW",
        "PENTAGON_ARROW",
        "CHEVRON_ARROW",
        "CIRCULAR_ARROW",
        "WEDGE_RECTANGLE_CALLOUT",
        "WEDGE_ROUND_RECTANGLE_CALLOUT",
        "WEDGE_ELLIPSE_CALLOUT",
        "CLOUD_CALLOUT",
        "FLOW_CHART_PROCESS",
        "FLOW_CHART_DECISION",
        "FLOW_CHART_INPUT_OUTPUT",
        "FLOW_CHART_PREDEFINED_PROCESS",
        "FLOW_CHART_INTERNAL_STORAGE",
        "FLOW_CHART_DOCUMENT",
        "FLOW_CHART_MULTIDOCUMENT",
        "FLOW_CHART_TERMINATOR",
        "FLOW_CHART_PREPARATION",
        "FLOW_CHART_MANUAL_INPUT",
        "FLOW_CHART_MANUAL_OPERATION",
        "FLOW_CHART_CONNECTOR",
        "FLOW_CHART_PUNCHED_CARD",
        "FLOW_CHART_PUNCHED_TAPE",
        "FLOW_CHART_SUMMING_JUNCTION",
        "FLOW_CHART_OR",
        "FLOW_CHART_COLLATE",
        "FLOW_CHART_SORT",
        "FLOW_CHART_EXTRACT",
        "FLOW_CHART_MERGE",
        "FLOW_CHART_ONLINE_STORAGE",
        "FLOW_CHART_MAGNETIC_TAPE",
        "FLOW_CHART_MAGNETIC_DISK",
        "FLOW_CHART_MAGNETIC_DRUM",
        "FLOW_CHART_DISPLAY",
        "FLOW_CHART_DELAY",
        "FLOW_CHART_ALTERNATE_PROCESS",
        "FLOW_CHART_OFFPAGE_CONNECTOR",
        "FLOW_CHART_DATA",
        "MATH_PLUS",
        "MATH_MINUS",
        "MATH_MULTIPLY",
        "MATH_DIVIDE",
        "MATH_EQUAL",
        "MATH_NOT_EQUAL",
        "LEFT_BRACKET",
        "RIGHT_BRACKET",
        "LEFT_BRACE",
        "RIGHT_BRACE",
        "BRACKET_PAIR",
        "BRACE_PAIR",
        "RIBBON",
        "RIBBON_2",
        "SNIP_ROUND_RECTANGLE",
        "SNIP_2_SAME_RECTANGLE",
        "SNIP_2_DIAGONAL_RECTANGLE",
        "ROUND_1_RECTANGLE",
        "ROUND_2_SAME_RECTANGLE",
        "ROUND_2_DIAGONAL_RECTANGLE",
        "CUSTOM",
        "SHAPE",
    }

    google_shape_type = shape_type if shape_type in valid_google_types else "RECTANGLE"

    # Google Slides uses a base size of 3000024 EMU (236.2 pt) and applies
    # scale factors to get the visual size
    base_size_emu = 3000024
    target_w_emu = pt_to_emu(position["w"])
    target_h_emu = pt_to_emu(position["h"])

    # Calculate scale factors
    scale_x = target_w_emu / base_size_emu if base_size_emu > 0 else 1
    scale_y = target_h_emu / base_size_emu if base_size_emu > 0 else 1

    return {
        "createShape": {
            "objectId": object_id,
            "shapeType": google_shape_type,
            "elementProperties": {
                "pageObjectId": slide_id,
                "size": {
                    "width": {"magnitude": base_size_emu, "unit": "EMU"},
                    "height": {"magnitude": base_size_emu, "unit": "EMU"},
                },
                "transform": {
                    "scaleX": scale_x,
                    "scaleY": scale_y,
                    "translateX": pt_to_emu(position["x"]),
                    "translateY": pt_to_emu(position["y"]),
                    "unit": "EMU",
                },
            },
        }
    }


def _create_line_request(
    object_id: str,
    slide_id: str,
    position: dict[str, float],
) -> dict[str, Any]:
    """Create a createLine request."""
    return {
        "createLine": {
            "objectId": object_id,
            "lineCategory": "STRAIGHT",
            "elementProperties": {
                "pageObjectId": slide_id,
                "size": {
                    "width": {"magnitude": pt_to_emu(position["w"]), "unit": "EMU"},
                    "height": {"magnitude": pt_to_emu(position["h"]), "unit": "EMU"},
                },
                "transform": {
                    "scaleX": 1,
                    "scaleY": 1,
                    "translateX": pt_to_emu(position["x"]),
                    "translateY": pt_to_emu(position["y"]),
                    "unit": "EMU",
                },
            },
        }
    }


def _create_image_request(
    object_id: str,
    slide_id: str,
    position: dict[str, float],
    url: str,
    native_size: dict[str, float] | None = None,
    native_scale: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Create a createImage request.

    For accurate image copying, we need to use the native image dimensions and
    calculate appropriate scale factors. Google Slides uses native image size
    as the base and applies scale factors from there.

    Args:
        object_id: The new object ID
        slide_id: Target slide ID
        position: Target position {x, y, w, h} in points
        url: Image URL
        native_size: Native image dimensions {w, h} in EMU (from source style)
        native_scale: Original scale factors {x, y} (from source style)
    """
    target_w_emu = pt_to_emu(position["w"])
    target_h_emu = pt_to_emu(position["h"])

    if native_size and native_scale:
        # Use native dimensions as base and calculate scale factors
        # to achieve target visual size
        native_w = native_size.get("w", 0)
        native_h = native_size.get("h", 0)

        if native_w > 0 and native_h > 0:
            scale_x = target_w_emu / native_w
            scale_y = target_h_emu / native_h

            return {
                "createImage": {
                    "objectId": object_id,
                    "url": url,
                    "elementProperties": {
                        "pageObjectId": slide_id,
                        "size": {
                            "width": {"magnitude": native_w, "unit": "EMU"},
                            "height": {"magnitude": native_h, "unit": "EMU"},
                        },
                        "transform": {
                            "scaleX": scale_x,
                            "scaleY": scale_y,
                            "translateX": pt_to_emu(position["x"]),
                            "translateY": pt_to_emu(position["y"]),
                            "unit": "EMU",
                        },
                    },
                }
            }

    # Fallback: use standard base size approach (less accurate)
    base_size_emu = 3000024
    scale_x = target_w_emu / base_size_emu if base_size_emu > 0 else 1
    scale_y = target_h_emu / base_size_emu if base_size_emu > 0 else 1

    return {
        "createImage": {
            "objectId": object_id,
            "url": url,
            "elementProperties": {
                "pageObjectId": slide_id,
                "size": {
                    "width": {"magnitude": base_size_emu, "unit": "EMU"},
                    "height": {"magnitude": base_size_emu, "unit": "EMU"},
                },
                "transform": {
                    "scaleX": scale_x,
                    "scaleY": scale_y,
                    "translateX": pt_to_emu(position["x"]),
                    "translateY": pt_to_emu(position["y"]),
                    "unit": "EMU",
                },
            },
        }
    }


def _apply_style_requests(
    object_id: str,
    style: dict[str, Any],
) -> list[dict[str, Any]]:
    """Generate requests to apply styling to a shape."""
    requests: list[dict[str, Any]] = []

    # Apply fill
    fill = style.get("fill")
    if fill:
        if fill.get("type") == "solid":
            color = fill.get("color", "#000000")
            alpha = fill.get("alpha", 1.0)
            requests.append(_create_fill_request(object_id, color, alpha))
        elif fill.get("type") == "none":
            # Explicitly remove fill
            requests.append(
                {
                    "updateShapeProperties": {
                        "objectId": object_id,
                        "shapeProperties": {
                            "shapeBackgroundFill": {
                                "propertyState": "NOT_RENDERED",
                            },
                        },
                        "fields": "shapeBackgroundFill",
                    }
                }
            )

    # Apply stroke/outline
    stroke = style.get("stroke")
    if stroke:
        if stroke.get("type") == "none":
            # Explicitly remove outline
            requests.append(
                {
                    "updateShapeProperties": {
                        "objectId": object_id,
                        "shapeProperties": {
                            "outline": {
                                "propertyState": "NOT_RENDERED",
                            },
                        },
                        "fields": "outline",
                    }
                }
            )
        elif stroke.get("type") == "solid" or stroke.get("color"):
            requests.append(_create_outline_request(object_id, stroke))

    # Apply autofit and contentAlignment settings
    shape_props: dict[str, Any] = {}
    fields: list[str] = []

    # Note: autofit is read-only in Google Slides API (cannot be updated via API)
    # We only extract it for informational purposes but don't try to set it

    # Content alignment (vertical text alignment) - this IS writable
    content_alignment = style.get("contentAlignment")
    if content_alignment:
        shape_props["contentAlignment"] = content_alignment
        fields.append("contentAlignment")

    # Apply shape properties if any
    if fields:
        requests.append(
            {
                "updateShapeProperties": {
                    "objectId": object_id,
                    "shapeProperties": shape_props,
                    "fields": ",".join(fields),
                }
            }
        )

    return requests


def _apply_line_style_requests(
    object_id: str,
    style: dict[str, Any],
) -> list[dict[str, Any]]:
    """Generate requests to apply styling to a line."""
    requests: list[dict[str, Any]] = []

    stroke = style.get("stroke")
    if stroke:
        color = stroke.get("color", "#000000")
        weight = stroke.get("weight", 1)
        dash_style = stroke.get("dashStyle", "SOLID")

        requests.append(
            {
                "updateLineProperties": {
                    "objectId": object_id,
                    "lineProperties": {
                        "lineFill": {
                            "solidFill": {
                                "color": _parse_color(color),
                            },
                        },
                        "weight": {"magnitude": pt_to_emu(weight), "unit": "EMU"},
                        "dashStyle": dash_style,
                    },
                    "fields": "lineFill,weight,dashStyle",
                }
            }
        )

    return requests


def _apply_image_style_requests(
    _object_id: str,
    _style: dict[str, Any],
) -> list[dict[str, Any]]:
    """Generate requests to apply styling to an image.

    Note: Google Slides API has limited support for image properties.
    Most properties (transparency, brightness, contrast) are read-only
    and can only be set through the UI, not the API.

    Only outline properties can be updated via UpdateImagePropertiesRequest.
    """
    # Currently no image properties can be updated via API
    # Transparency, brightness, contrast are all read-only
    return []


def _apply_text_style_requests(
    object_id: str,
    _text_lines: list[str],
    text_style_info: dict[str, Any],
) -> list[dict[str, Any]]:
    """Generate requests to apply text styling.

    Applies font, color, bold, etc. to inserted text.

    Args:
        object_id: The shape containing the text
        _text_lines: The text that was inserted (reserved for future range calculation)
        text_style_info: The source text styling from styles.json
    """
    requests: list[dict[str, Any]] = []

    paragraphs = text_style_info.get("paragraphs", [])
    if not paragraphs:
        return requests

    # Apply styling from the first paragraph's first run to all text
    # This is a simplification - ideally we'd match run ranges
    first_para = paragraphs[0]
    runs = first_para.get("runs", [])

    if runs:
        first_run = runs[0]
        run_style = first_run.get("style", {})

        # Build the text style
        text_style: dict[str, Any] = {}
        fields: list[str] = []

        # Font family
        font_family = run_style.get("fontFamily")
        if font_family:
            text_style["fontFamily"] = font_family
            fields.append("fontFamily")

        # Font size (if non-zero)
        font_size = run_style.get("fontSize")
        if font_size and font_size > 0:
            text_style["fontSize"] = {"magnitude": font_size, "unit": "PT"}
            fields.append("fontSize")

        # Bold
        bold = run_style.get("bold")
        if bold is not None:
            text_style["bold"] = bold
            fields.append("bold")

        # Foreground color
        color = run_style.get("color")
        if color:
            text_style["foregroundColor"] = {"opaqueColor": _parse_color(color)}
            fields.append("foregroundColor")

        # Only create request if we have styles to apply
        if fields:
            requests.append(
                {
                    "updateTextStyle": {
                        "objectId": object_id,
                        "textRange": {
                            "type": "ALL",
                        },
                        "style": text_style,
                        "fields": ",".join(fields),
                    }
                }
            )

    # Apply paragraph styling if needed
    para_style = first_para.get("style", {})
    alignment = para_style.get("alignment")
    if alignment and alignment != "START":
        requests.append(
            {
                "updateParagraphStyle": {
                    "objectId": object_id,
                    "textRange": {
                        "type": "ALL",
                    },
                    "style": {
                        "alignment": alignment,
                    },
                    "fields": "alignment",
                }
            }
        )

    return requests


def _create_fill_request(
    object_id: str,
    color: str,
    alpha: float,
) -> dict[str, Any]:
    """Create updateShapeProperties request for fill."""
    return {
        "updateShapeProperties": {
            "objectId": object_id,
            "shapeProperties": {
                "shapeBackgroundFill": {
                    "solidFill": {
                        "color": _parse_color(color),
                        "alpha": alpha,
                    },
                },
            },
            "fields": "shapeBackgroundFill",
        }
    }


def _create_outline_request(
    object_id: str,
    stroke: dict[str, Any],
) -> dict[str, Any]:
    """Create updateShapeProperties request for outline."""
    color = stroke.get("color", "#000000")
    weight = stroke.get("weight", 1)
    dash_style = stroke.get("dashStyle", "SOLID")

    return {
        "updateShapeProperties": {
            "objectId": object_id,
            "shapeProperties": {
                "outline": {
                    "outlineFill": {
                        "solidFill": {
                            "color": _parse_color(color),
                        },
                    },
                    "weight": {"magnitude": pt_to_emu(weight), "unit": "EMU"},
                    "dashStyle": dash_style,
                },
            },
            "fields": "outline",
        }
    }


def _create_text_insert_requests(
    object_id: str,
    text_lines: list[str],
) -> list[dict[str, Any]]:
    """Create requests to insert text into an element."""
    if not text_lines:
        return []

    combined_text = "\n".join(text_lines)
    return [
        {
            "insertText": {
                "objectId": object_id,
                "insertionIndex": 0,
                "text": combined_text,
            }
        }
    ]


def _create_element_requests(
    change: Change,
    slide_google_id: str,
) -> list[dict[str, Any]]:
    """Create requests for a new element."""
    requests: list[dict[str, Any]] = []

    # Determine shape type from metadata
    tag = change.metadata.get("tag", "Rect")
    position = change.new_position or {"x": 0, "y": 0, "w": 100, "h": 100}

    # Generate unique ID
    new_object_id = f"new_{change.target_id}"

    # Map tags to shape types
    tag_to_shape = {
        "Rect": "RECTANGLE",
        "TextBox": "TEXT_BOX",
        "RoundRect": "ROUND_RECTANGLE",
        "Ellipse": "ELLIPSE",
        "Line": "LINE",
    }

    shape_type = tag_to_shape.get(tag, "RECTANGLE")

    if shape_type == "LINE":
        requests.append(_create_line_request(new_object_id, slide_google_id, position))
    else:
        requests.append(
            _create_shape_request(
                new_object_id,
                slide_google_id,
                shape_type,
                position,
            )
        )

    # Add text if provided
    if change.new_text:
        requests.extend(_create_text_insert_requests(new_object_id, change.new_text))

    return requests


def _parse_color(color: str) -> dict[str, Any]:
    """Parse color string to Google Slides API format.

    For updateShapeProperties, the color format is:
    - For theme colors: {"themeColor": "DARK1"}
    - For RGB colors: {"rgbColor": {"red": 0.5, "green": 0.5, "blue": 0.5}}
    """
    if color.startswith("@"):
        # Theme color reference
        return {"themeColor": color[1:]}

    # Hex color
    hex_color = color.lstrip("#")
    if len(hex_color) == 6:
        r = int(hex_color[0:2], 16) / 255
        g = int(hex_color[2:4], 16) / 255
        b = int(hex_color[4:6], 16) / 255
        return {"rgbColor": {"red": r, "green": g, "blue": b}}

    return {"rgbColor": {"red": 0, "green": 0, "blue": 0}}
