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

    # Generate a unique object ID for the new element
    # Include slide index and unique suffix to avoid collisions with existing IDs
    suffix = _get_unique_suffix()
    new_object_id = f"copy_{change.slide_index}_{suffix}"

    # Create element based on type
    if elem_type in (
        "RECTANGLE",
        "TEXT_BOX",
        "ROUND_RECTANGLE",
        "ELLIPSE",
        "CUSTOM",
        "SNIP_ROUND_RECTANGLE",
        "ROUND_2_SAME_RECTANGLE",
        "FLOW_CHART_ALTERNATE_PROCESS",
        "FLOW_CHART_PROCESS",
        "TRIANGLE",
        "CHEVRON",
        "ARC",
    ):
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
                position,
                slide_google_id,
                all_styles,
                requests,
                new_object_id,
            )

    elif elem_type == "LINE":
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
                )
            )
            # Apply image properties like transparency
            image_style_requests = _apply_image_style_requests(
                new_object_id, source_style
            )
            requests.extend(image_style_requests)

    elif elem_type == "GROUP":
        # Create children first, then group them
        if change.children:
            child_ids = _create_children_from_data(
                change.children,
                position,
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

    return requests


def _create_children_from_data(
    children: list[dict[str, Any]],
    parent_position: dict[str, float],
    slide_google_id: str,
    all_styles: dict[str, dict[str, Any]],
    requests: list[dict[str, Any]],
    id_prefix: str,
    depth: int = 0,
) -> list[str]:
    """Create child elements from serialized children data.

    Args:
        children: List of child data dicts from Change.children
        parent_position: The parent's absolute position
        slide_google_id: Target slide ID
        all_styles: All element styles for styling lookup
        requests: List to append requests to
        id_prefix: Prefix for generated object IDs
        depth: Recursion depth

    Returns:
        List of created child object IDs
    """
    child_ids: list[str] = []

    for i, child_data in enumerate(children):
        child_obj_id = f"{id_prefix}_c{depth}_{i}"
        child_tag = child_data.get("tag", "Rect")
        child_text = child_data.get("text", [])
        nested_children = child_data.get("children", [])

        # Get style for this child from all_styles
        source_id = child_data.get("id", "")
        child_style = all_styles.get(source_id, {})

        # Calculate absolute position
        # Children in content.sml don't have positions, use style's relative position
        child_rel_pos = child_style.get("position", {})
        if child_rel_pos.get("relative", False):
            abs_position = {
                "x": parent_position["x"] + child_rel_pos.get("x", 0),
                "y": parent_position["y"] + child_rel_pos.get("y", 0),
                "w": child_rel_pos.get("w", 50),
                "h": child_rel_pos.get("h", 50),
            }
        else:
            # If not relative, use parent position with small offset
            abs_position = {
                "x": parent_position["x"] + i * 10,
                "y": parent_position["y"] + i * 10,
                "w": child_rel_pos.get("w", 50),
                "h": child_rel_pos.get("h", 50),
            }

        # Map tag to element type
        elem_type = _tag_to_type(child_tag)

        if elem_type == "GROUP" and nested_children:
            # Create children first, then group them
            nested_child_ids = _create_children_from_data(
                nested_children,
                abs_position,
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
                    abs_position,
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
                        child_obj_id, slide_google_id, abs_position, content_url
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
                    abs_position,
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
                    abs_position,
                    slide_google_id,
                    all_styles,
                    requests,
                    child_obj_id,
                    depth + 1,
                )

    return child_ids


def _tag_to_type(tag: str) -> str:
    """Convert content.sml tag to element type."""
    tag_map = {
        "Rect": "RECTANGLE",
        "TextBox": "TEXT_BOX",
        "RoundRect": "ROUND_RECTANGLE",
        "Ellipse": "ELLIPSE",
        "Line": "LINE",
        "Image": "IMAGE",
        "Group": "GROUP",
        "CUSTOM": "RECTANGLE",  # Custom shapes become rectangles
        "SNIP_ROUND_RECTANGLE": "SNIP_ROUND_RECTANGLE",
        "ROUND_2_SAME_RECTANGLE": "RECTANGLE",
        "FLOW_CHART_ALTERNATE_PROCESS": "FLOW_CHART_ALTERNATE_PROCESS",
        "FLOW_CHART_PROCESS": "FLOW_CHART_PROCESS",
        "TRIANGLE": "TRIANGLE",
        "CHEVRON": "CHEVRON",
        "ARC": "ARC",
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
    # Map our tag names back to Google shape types
    shape_type_map = {
        "RECTANGLE": "RECTANGLE",
        "TEXT_BOX": "TEXT_BOX",
        "ROUND_RECTANGLE": "ROUND_RECTANGLE",
        "ELLIPSE": "ELLIPSE",
        "Rect": "RECTANGLE",
        "TextBox": "TEXT_BOX",
        "RoundRect": "ROUND_RECTANGLE",
        "Ellipse": "ELLIPSE",
    }
    google_shape_type = shape_type_map.get(shape_type, "RECTANGLE")

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
) -> dict[str, Any]:
    """Create a createImage request.

    Unlike shapes, images use their NATIVE dimensions as the base size (determined
    by the image file). We cannot predict this size, so we specify the target
    visual size directly and use scaleX=1, scaleY=1.

    Google will fetch the image, determine its native size, and then apply the
    transform. With scale=1, the translateX/translateY give us exact positioning.
    """
    target_w_emu = pt_to_emu(position["w"])
    target_h_emu = pt_to_emu(position["h"])

    return {
        "createImage": {
            "objectId": object_id,
            "url": url,
            "elementProperties": {
                "pageObjectId": slide_id,
                "size": {
                    "width": {"magnitude": target_w_emu, "unit": "EMU"},
                    "height": {"magnitude": target_h_emu, "unit": "EMU"},
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
