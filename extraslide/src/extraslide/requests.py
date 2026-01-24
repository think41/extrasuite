"""Request generation from SML diffs.

Converts DiffResult into Google Slides API batchUpdate requests.

Spec reference: sml-reconciliation-spec.md#request-generation-by-change-type
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from extraslide.classes import (
    PropertyState,
    parse_fill_class,
    parse_position_classes,
    parse_stroke_classes,
    parse_text_style_classes,
)
from extraslide.diff import (
    ChangeType,
    DiffResult,
    ElementChange,
    ParagraphChange,
    SlideChange,
)
from extraslide.units import hex_to_rgb, pt_to_emu

# Reverse mapping from SML element tags to API shape types
TAG_TO_SHAPE_TYPE: dict[str, str] = {
    "TextBox": "TEXT_BOX",
    "Rect": "RECTANGLE",
    "RoundRect": "ROUND_RECTANGLE",
    "Ellipse": "ELLIPSE",
    "Triangle": "TRIANGLE",
    "Diamond": "DIAMOND",
    "Pentagon": "PENTAGON",
    "Hexagon": "HEXAGON",
    "Star5": "STAR_5",
    "Heart": "HEART",
    "Cloud": "CLOUD",
    "Arrow": "ARROW_RIGHT",
    "CustomShape": "CUSTOM",
    # Add more as needed
}

# Line category mapping
LINE_CLASS_TO_CATEGORY: dict[str, str] = {
    "line-straight": "STRAIGHT",
    "line-straight-1": "STRAIGHT",
    "line-bent-2": "BENT",
    "line-bent-3": "BENT",
    "line-bent-4": "BENT",
    "line-bent-5": "BENT",
    "line-curved-2": "CURVED",
    "line-curved-3": "CURVED",
    "line-curved-4": "CURVED",
    "line-curved-5": "CURVED",
}


@dataclass
class RequestBuilder:
    """Builds batchUpdate requests from diff results."""

    slide_id: str = ""  # Current slide being processed
    requests: list[dict[str, Any]] = field(default_factory=list)
    images: dict[str, str] = field(default_factory=dict)  # hash -> url mapping

    def _resolve_image_url(self, src: str) -> str:
        """Resolve image URL, expanding short img: references."""
        if src.startswith("img:"):
            img_hash = src[4:]
            return self.images.get(img_hash, src)
        return src

    def build(
        self, diff: DiffResult, _slide_id_for_new: str | None = None
    ) -> list[dict[str, Any]]:
        """Build batchUpdate requests from diff result.

        Args:
            diff: The diff result to convert.
            slide_id_for_new: Slide ID to use for new elements (if any).

        Returns:
            List of request objects for batchUpdate.

        Spec: sml-reconciliation-spec.md#operation-ordering
        """
        self.requests = []

        # Process in topological order per spec:
        # Phase 1: Structural creates (slides, shapes)
        # Phase 2: Content operations (insert text)
        # Phase 3: Style updates
        # Phase 7: Deletions (reverse order)

        # Collect all operations by phase
        creates: list[dict[str, Any]] = []
        content_ops: list[dict[str, Any]] = []
        style_ops: list[dict[str, Any]] = []
        deletes: list[dict[str, Any]] = []

        for slide_change in diff.slide_changes:
            self.slide_id = slide_change.slide_id

            if slide_change.change_type == ChangeType.ADDED:
                # Create slide
                creates.append(self._create_slide_request(slide_change))

                # Create elements on new slide
                for elem_change in slide_change.element_changes:
                    if elem_change.change_type == ChangeType.ADDED:
                        creates.extend(
                            self._create_element_requests(
                                elem_change, slide_change.slide_id
                            )
                        )

            elif slide_change.change_type == ChangeType.DELETED:
                # Delete elements first, then slide
                deletes.append({"deleteObject": {"objectId": slide_change.slide_id}})

            elif slide_change.change_type == ChangeType.MODIFIED:
                # Handle slide property changes
                if set(slide_change.original_classes) != set(slide_change.new_classes):
                    style_ops.extend(self._update_slide_properties(slide_change))

                # Handle element changes
                for elem_change in slide_change.element_changes:
                    if elem_change.change_type == ChangeType.ADDED:
                        if elem_change.duplicate_of:
                            creates.extend(
                                self._duplicate_element_requests(elem_change)
                            )
                        else:
                            creates.extend(
                                self._create_element_requests(
                                    elem_change, slide_change.slide_id
                                )
                            )

                    elif elem_change.change_type == ChangeType.DELETED:
                        deletes.append(
                            {"deleteObject": {"objectId": elem_change.element_id}}
                        )

                    elif elem_change.change_type == ChangeType.MODIFIED:
                        # Style changes
                        if set(elem_change.original_classes) != set(
                            elem_change.new_classes
                        ):
                            style_ops.extend(
                                self._update_element_properties(elem_change)
                            )

                        # Text content changes
                        for para_change in elem_change.paragraph_changes:
                            ops = self._text_change_requests(
                                elem_change.element_id, para_change
                            )
                            content_ops.extend(ops.get("content", []))
                            style_ops.extend(ops.get("style", []))
                            deletes.extend(ops.get("delete", []))

        # Handle slide reordering
        if diff.slides_reordered:
            # Generate updateSlidesPosition request
            # This is placed after creates and before deletes
            style_ops.append(
                {
                    "updateSlidesPosition": {
                        "slideObjectIds": diff.slide_order,
                        "insertionIndex": 0,
                    }
                }
            )

        # Combine in correct order
        self.requests = creates + content_ops + style_ops + list(reversed(deletes))

        return self.requests

    def _create_slide_request(self, slide_change: SlideChange) -> dict[str, Any]:
        """Generate createSlide request.

        Spec: sml-reconciliation-spec.md#create-slide
        """
        request: dict[str, Any] = {
            "createSlide": {
                "objectId": slide_change.slide_id,
            }
        }

        if slide_change.layout:
            request["createSlide"]["slideLayoutReference"] = {
                "layoutId": slide_change.layout
            }

        if slide_change.new_index is not None:
            request["createSlide"]["insertionIndex"] = slide_change.new_index

        return request

    def _create_element_requests(
        self, elem_change: ElementChange, slide_id: str
    ) -> list[dict[str, Any]]:
        """Generate requests to create an element.

        Spec: sml-reconciliation-spec.md#create-shape
        """
        requests: list[dict[str, Any]] = []

        tag = elem_change.element_tag
        element_id = elem_change.element_id
        classes = elem_change.new_classes

        # Get position/size from classes
        position = parse_position_classes(classes)

        # Build element properties
        element_props: dict[str, Any] = {
            "pageObjectId": slide_id,
        }

        # Size
        if "w" in position or "h" in position:
            element_props["size"] = {}
            if "w" in position:
                element_props["size"]["width"] = {
                    "magnitude": position["w"],
                    "unit": "PT",
                }
            if "h" in position:
                element_props["size"]["height"] = {
                    "magnitude": position["h"],
                    "unit": "PT",
                }

        # Transform (position)
        if "x" in position or "y" in position:
            element_props["transform"] = {
                "scaleX": 1,
                "scaleY": 1,
                "translateX": position.get("x", 0),
                "translateY": position.get("y", 0),
                "unit": "PT",
            }

        # Create based on element type
        if tag == "Line":
            # Create line
            line_category = "STRAIGHT"
            for cls in classes:
                if cls in LINE_CLASS_TO_CATEGORY:
                    line_category = LINE_CLASS_TO_CATEGORY[cls]
                    break

            requests.append(
                {
                    "createLine": {
                        "objectId": element_id,
                        "lineCategory": line_category,
                        "elementProperties": element_props,
                    }
                }
            )

        elif tag == "Image":
            # Create image - resolve short img: references to full URLs
            src = elem_change.new_attrs.get("src", "")
            full_url = self._resolve_image_url(src)
            requests.append(
                {
                    "createImage": {
                        "objectId": element_id,
                        "url": full_url,
                        "elementProperties": element_props,
                    }
                }
            )

        elif tag == "Table":
            # Create table - rows/cols are stored on ParsedElement, not in attrs
            rows = 1
            cols = 1
            if elem_change.new_element:
                rows = elem_change.new_element.rows or 1
                cols = elem_change.new_element.cols or 1
            requests.append(
                {
                    "createTable": {
                        "objectId": element_id,
                        "rows": rows,
                        "columns": cols,
                        "elementProperties": element_props,
                    }
                }
            )

        elif tag == "Video":
            # Create video
            src = elem_change.new_attrs.get("src", "")
            video_source = "YOUTUBE"
            video_id = ""
            if src.startswith("youtube:"):
                video_id = src[8:]
            elif src.startswith("drive:"):
                video_source = "DRIVE"
                video_id = src[6:]

            requests.append(
                {
                    "createVideo": {
                        "objectId": element_id,
                        "source": video_source,
                        "id": video_id,
                        "elementProperties": element_props,
                    }
                }
            )

        else:
            # Create shape
            shape_type = TAG_TO_SHAPE_TYPE.get(tag, "RECTANGLE")
            requests.append(
                {
                    "createShape": {
                        "objectId": element_id,
                        "shapeType": shape_type,
                        "elementProperties": element_props,
                    }
                }
            )

        # Add style update if element has fill/stroke
        style_requests = self._shape_style_requests(element_id, classes)
        requests.extend(style_requests)

        # If element has text content, add insert text requests
        if elem_change.new_element and elem_change.new_element.paragraphs:
            text_content = ""
            for para in elem_change.new_element.paragraphs:
                for run in para.runs:
                    if hasattr(run, "content"):
                        text_content += run.content
                text_content += "\n"

            if text_content.strip():
                requests.append(
                    {
                        "insertText": {
                            "objectId": element_id,
                            "insertionIndex": 0,
                            "text": text_content.rstrip("\n"),
                        }
                    }
                )

        return requests

    def _duplicate_element_requests(
        self, elem_change: ElementChange
    ) -> list[dict[str, Any]]:
        """Generate requests to duplicate an element.

        Spec: sml-reconciliation-spec.md#duplicate-element
        """
        requests: list[dict[str, Any]] = []

        requests.append(
            {
                "duplicateObject": {
                    "objectId": elem_change.duplicate_of,
                    "objectIds": {
                        elem_change.duplicate_of: elem_change.element_id,
                    },
                }
            }
        )

        # If there are style overrides, add update requests
        if elem_change.new_classes:
            style_requests = self._shape_style_requests(
                elem_change.element_id, elem_change.new_classes
            )
            requests.extend(style_requests)

        return requests

    def _update_slide_properties(
        self, slide_change: SlideChange
    ) -> list[dict[str, Any]]:
        """Generate requests to update slide properties.

        Spec: sml-reconciliation-spec.md#update-slide-properties
        """
        requests: list[dict[str, Any]] = []

        # Check for background color change
        old_bg = self._extract_bg_color(slide_change.original_classes)
        new_bg = self._extract_bg_color(slide_change.new_classes)

        if old_bg != new_bg and new_bg:
            page_props: dict[str, Any] = {}
            fields: list[str] = []

            fill = parse_fill_class(f"fill-{new_bg}")
            if fill and fill.color and fill.color.hex:
                r, g, b = hex_to_rgb(fill.color.hex)
                page_props["pageBackgroundFill"] = {
                    "solidFill": {
                        "color": {"rgbColor": {"red": r, "green": g, "blue": b}}
                    }
                }
                fields.append("pageBackgroundFill.solidFill.color")

            if page_props:
                requests.append(
                    {
                        "updatePageProperties": {
                            "objectId": slide_change.slide_id,
                            "pageProperties": page_props,
                            "fields": ",".join(fields),
                        }
                    }
                )

        return requests

    def _update_element_properties(
        self, elem_change: ElementChange
    ) -> list[dict[str, Any]]:
        """Generate requests to update element properties.

        Spec: sml-reconciliation-spec.md#update-shape-transform
        """
        requests: list[dict[str, Any]] = []

        # Check for position/size changes
        old_pos = parse_position_classes(elem_change.original_classes)
        new_pos = parse_position_classes(elem_change.new_classes)

        if old_pos != new_pos:
            transform: dict[str, Any] = {
                "scaleX": 1,
                "scaleY": 1,
                "shearX": 0,
                "shearY": 0,
                "translateX": new_pos.get("x", 0),
                "translateY": new_pos.get("y", 0),
                "unit": "PT",
            }

            requests.append(
                {
                    "updatePageElementTransform": {
                        "objectId": elem_change.element_id,
                        "applyMode": "ABSOLUTE",
                        "transform": transform,
                    }
                }
            )

        # Check for style changes (fill, stroke, shadow)
        style_requests = self._diff_style_requests(
            elem_change.element_id,
            elem_change.original_classes,
            elem_change.new_classes,
            elem_change.element_tag,
        )
        requests.extend(style_requests)

        return requests

    def _shape_style_requests(
        self, element_id: str, classes: list[str]
    ) -> list[dict[str, Any]]:
        """Generate style update requests for a shape from classes."""
        requests: list[dict[str, Any]] = []

        shape_props: dict[str, Any] = {}
        fields: list[str] = []

        # Fill
        for cls in classes:
            if cls.startswith("fill-"):
                fill = parse_fill_class(cls)
                if fill:
                    if fill.color and fill.color.hex:
                        r, g, b = hex_to_rgb(fill.color.hex)
                        shape_props["shapeBackgroundFill"] = {
                            "solidFill": {
                                "color": {"rgbColor": {"red": r, "green": g, "blue": b}}
                            }
                        }
                        if fill.color.alpha < 1.0:
                            shape_props["shapeBackgroundFill"]["solidFill"]["alpha"] = (
                                fill.color.alpha
                            )
                        fields.append("shapeBackgroundFill.solidFill.color")
                    elif fill.state:
                        if fill.state == PropertyState.NOT_RENDERED:
                            shape_props["shapeBackgroundFill"] = {
                                "propertyState": "NOT_RENDERED"
                            }
                            fields.append("shapeBackgroundFill.propertyState")
                break

        # Stroke
        stroke = parse_stroke_classes(classes)
        if stroke:
            outline: dict[str, Any] = {}
            if stroke.color and stroke.color.hex:
                r, g, b = hex_to_rgb(stroke.color.hex)
                outline["outlineFill"] = {
                    "solidFill": {
                        "color": {"rgbColor": {"red": r, "green": g, "blue": b}}
                    }
                }
                fields.append("outline.outlineFill.solidFill.color")
            if stroke.weight_pt is not None:
                outline["weight"] = {
                    "magnitude": pt_to_emu(stroke.weight_pt),
                    "unit": "EMU",
                }
                fields.append("outline.weight")
            if stroke.state and stroke.state == PropertyState.NOT_RENDERED:
                outline["propertyState"] = "NOT_RENDERED"
                fields.append("outline.propertyState")
            if outline:
                shape_props["outline"] = outline

        if shape_props and fields:
            requests.append(
                {
                    "updateShapeProperties": {
                        "objectId": element_id,
                        "shapeProperties": shape_props,
                        "fields": ",".join(fields),
                    }
                }
            )

        return requests

    def _diff_style_requests(
        self,
        element_id: str,
        original_classes: list[str],
        new_classes: list[str],
        element_tag: str,
    ) -> list[dict[str, Any]]:
        """Generate style update requests based on class diff."""
        requests: list[dict[str, Any]] = []

        # Determine what changed
        shape_props: dict[str, Any] = {}
        fields: list[str] = []

        # Check fill changes
        old_fill = next((c for c in original_classes if c.startswith("fill-")), None)
        new_fill = next((c for c in new_classes if c.startswith("fill-")), None)

        if old_fill != new_fill:
            if new_fill:
                fill = parse_fill_class(new_fill)
                if fill and fill.color and fill.color.hex:
                    r, g, b = hex_to_rgb(fill.color.hex)
                    shape_props["shapeBackgroundFill"] = {
                        "solidFill": {
                            "color": {"rgbColor": {"red": r, "green": g, "blue": b}}
                        }
                    }
                    fields.append("shapeBackgroundFill.solidFill.color")
                elif fill and fill.state:
                    if fill.state == PropertyState.NOT_RENDERED:
                        shape_props["shapeBackgroundFill"] = {
                            "propertyState": "NOT_RENDERED"
                        }
                        fields.append("shapeBackgroundFill.propertyState")
                    elif fill.state == PropertyState.INHERIT:
                        shape_props["shapeBackgroundFill"] = {
                            "propertyState": "INHERIT"
                        }
                        fields.append("shapeBackgroundFill.propertyState")
            elif old_fill and not new_fill:
                # Fill removed - set to inherit
                shape_props["shapeBackgroundFill"] = {"propertyState": "INHERIT"}
                fields.append("shapeBackgroundFill.propertyState")

        if shape_props and fields:
            if element_tag == "Line":
                # Lines use updateLineProperties
                line_props: dict[str, Any] = {}
                line_fields: list[str] = []

                # Convert fill to lineFill
                if "shapeBackgroundFill" in shape_props:
                    bg = shape_props["shapeBackgroundFill"]
                    if "solidFill" in bg:
                        line_props["lineFill"] = bg
                        line_fields.append("lineFill.solidFill.color")

                if line_props:
                    requests.append(
                        {
                            "updateLineProperties": {
                                "objectId": element_id,
                                "lineProperties": line_props,
                                "fields": ",".join(line_fields),
                            }
                        }
                    )
            else:
                requests.append(
                    {
                        "updateShapeProperties": {
                            "objectId": element_id,
                            "shapeProperties": shape_props,
                            "fields": ",".join(fields),
                        }
                    }
                )

        return requests

    def _text_change_requests(
        self, element_id: str, para_change: ParagraphChange
    ) -> dict[str, list[dict[str, Any]]]:
        """Generate requests for text changes.

        Returns dict with keys: content, style, delete

        Spec: sml-reconciliation-spec.md#text-operations
        """
        result: dict[str, list[dict[str, Any]]] = {
            "content": [],
            "style": [],
            "delete": [],
        }

        if para_change.change_type == ChangeType.ADDED:
            # New paragraph - insert text
            text_content = ""
            for text_change in para_change.text_changes:
                if text_change.new_content:
                    text_content += text_change.new_content

            if text_content:
                result["content"].append(
                    {
                        "insertText": {
                            "objectId": element_id,
                            "insertionIndex": 0,  # At end for now
                            "text": text_content + "\n",
                        }
                    }
                )

        elif para_change.change_type == ChangeType.DELETED:
            # Delete entire paragraph
            if (
                para_change.range_start is not None
                and para_change.range_end is not None
            ):
                result["delete"].append(
                    {
                        "deleteText": {
                            "objectId": element_id,
                            "textRange": {
                                "type": "FIXED_RANGE",
                                "startIndex": para_change.range_start,
                                "endIndex": para_change.range_end,
                            },
                        }
                    }
                )

        elif para_change.change_type == ChangeType.MODIFIED:
            # Handle text run changes
            # Sort by start index descending (process from end to start)
            sorted_changes = sorted(
                para_change.text_changes,
                key=lambda tc: tc.range_start if tc.range_start else 0,
                reverse=True,
            )

            for text_change in sorted_changes:
                if text_change.change_type == ChangeType.DELETED:
                    if (
                        text_change.range_start is not None
                        and text_change.range_end is not None
                    ):
                        result["delete"].append(
                            {
                                "deleteText": {
                                    "objectId": element_id,
                                    "textRange": {
                                        "type": "FIXED_RANGE",
                                        "startIndex": text_change.range_start,
                                        "endIndex": text_change.range_end,
                                    },
                                }
                            }
                        )

                elif text_change.change_type == ChangeType.ADDED:
                    if text_change.new_content:
                        # Insert at appropriate position
                        insert_idx = 0
                        if text_change.insert_after_index is not None:
                            # This would need more context to calculate correctly
                            pass

                        result["content"].append(
                            {
                                "insertText": {
                                    "objectId": element_id,
                                    "insertionIndex": insert_idx,
                                    "text": text_change.new_content,
                                }
                            }
                        )

                        # Style the inserted text
                        if text_change.new_classes:
                            style_request = self._text_style_request(
                                element_id,
                                insert_idx,
                                insert_idx + len(text_change.new_content),
                                text_change.new_classes,
                            )
                            if style_request:
                                result["style"].append(style_request)

                elif text_change.change_type == ChangeType.MODIFIED:
                    # Content changed - delete old, insert new
                    if text_change.original_content != text_change.new_content:
                        if (
                            text_change.range_start is not None
                            and text_change.range_end is not None
                        ):
                            result["delete"].append(
                                {
                                    "deleteText": {
                                        "objectId": element_id,
                                        "textRange": {
                                            "type": "FIXED_RANGE",
                                            "startIndex": text_change.range_start,
                                            "endIndex": text_change.range_end,
                                        },
                                    }
                                }
                            )

                        if text_change.new_content:
                            insert_idx = text_change.range_start or 0
                            result["content"].append(
                                {
                                    "insertText": {
                                        "objectId": element_id,
                                        "insertionIndex": insert_idx,
                                        "text": text_change.new_content,
                                    }
                                }
                            )

                            # Style if needed
                            if text_change.new_classes:
                                style_request = self._text_style_request(
                                    element_id,
                                    insert_idx,
                                    insert_idx + len(text_change.new_content),
                                    text_change.new_classes,
                                )
                                if style_request:
                                    result["style"].append(style_request)

                    # Style-only change
                    elif set(text_change.original_classes) != set(
                        text_change.new_classes
                    ):
                        if (
                            text_change.range_start is not None
                            and text_change.range_end is not None
                        ):
                            style_request = self._text_style_request(
                                element_id,
                                text_change.range_start,
                                text_change.range_end,
                                text_change.new_classes,
                            )
                            if style_request:
                                result["style"].append(style_request)

            # Check for paragraph style changes
            if set(para_change.original_classes) != set(para_change.new_classes):
                para_style = self._paragraph_style_request(
                    element_id,
                    para_change.range_start or 0,
                    para_change.range_end or 0,
                    para_change.new_classes,
                )
                if para_style:
                    result["style"].append(para_style)

        return result

    def _text_style_request(
        self,
        element_id: str,
        start_index: int,
        end_index: int,
        classes: list[str],
    ) -> dict[str, Any] | None:
        """Generate updateTextStyle request."""
        style: dict[str, Any] = {}
        fields: list[str] = []

        ts = parse_text_style_classes(classes)

        if ts.bold:
            style["bold"] = True
            fields.append("bold")
        if ts.italic:
            style["italic"] = True
            fields.append("italic")
        if ts.underline:
            style["underline"] = True
            fields.append("underline")
        if ts.strikethrough:
            style["strikethrough"] = True
            fields.append("strikethrough")

        if ts.font_size_pt:
            style["fontSize"] = {"magnitude": ts.font_size_pt, "unit": "PT"}
            fields.append("fontSize")

        if ts.font_family:
            style["fontFamily"] = ts.font_family
            fields.append("fontFamily")

        if ts.foreground_color and ts.foreground_color.hex:
            r, g, b = hex_to_rgb(ts.foreground_color.hex)
            style["foregroundColor"] = {
                "opaqueColor": {"rgbColor": {"red": r, "green": g, "blue": b}}
            }
            fields.append("foregroundColor")

        if not style:
            return None

        return {
            "updateTextStyle": {
                "objectId": element_id,
                "textRange": {
                    "type": "FIXED_RANGE",
                    "startIndex": start_index,
                    "endIndex": end_index,
                },
                "style": style,
                "fields": ",".join(fields),
            }
        }

    def _paragraph_style_request(
        self,
        element_id: str,
        start_index: int,
        end_index: int,
        classes: list[str],
    ) -> dict[str, Any] | None:
        """Generate updateParagraphStyle request."""
        style: dict[str, Any] = {}
        fields: list[str] = []

        # Check for alignment
        for cls in classes:
            if cls == "text-align-left":
                style["alignment"] = "START"
                fields.append("alignment")
            elif cls == "text-align-center":
                style["alignment"] = "CENTER"
                fields.append("alignment")
            elif cls == "text-align-right":
                style["alignment"] = "END"
                fields.append("alignment")
            elif cls == "text-align-justify":
                style["alignment"] = "JUSTIFIED"
                fields.append("alignment")

        if not style:
            return None

        return {
            "updateParagraphStyle": {
                "objectId": element_id,
                "textRange": {
                    "type": "FIXED_RANGE",
                    "startIndex": start_index,
                    "endIndex": end_index,
                },
                "paragraphStyle": style,
                "fields": ",".join(fields),
            }
        }

    def _extract_bg_color(self, classes: list[str]) -> str | None:
        """Extract background color from classes."""
        for cls in classes:
            if cls.startswith("bg-"):
                return cls[3:]
        return None


# ============================================================================
# Public API
# ============================================================================


def generate_requests(
    diff: DiffResult, images: dict[str, str] | None = None
) -> list[dict[str, Any]]:
    """Generate batchUpdate requests from diff result.

    Args:
        diff: The diff result to convert.
        images: Optional mapping of image hash to full URL for resolving
            short img: references.

    Returns:
        List of request objects for batchUpdate.
    """
    builder = RequestBuilder(images=images or {})
    return builder.build(diff)
