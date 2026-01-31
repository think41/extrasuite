"""Style extraction from Google Slides API elements.

Extracts all styling information indexed by clean ID.
Child elements have relative positions (relative to parent).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from extraslide.units import emu_to_pt

if TYPE_CHECKING:
    from extraslide.render_tree import RenderNode


def extract_styles(
    roots: list[RenderNode],
) -> dict[str, dict[str, Any]]:
    """Extract styles from all elements in render trees.

    Args:
        roots: Root nodes of render trees

    Returns:
        Dictionary mapping clean_id to style dictionary
    """
    styles: dict[str, dict[str, Any]] = {}

    def _extract_node(node: RenderNode) -> None:
        if not node.clean_id:
            return

        style = _extract_element_style(node)
        styles[node.clean_id] = style

        for child in node.children:
            _extract_node(child)

    for root in roots:
        _extract_node(root)

    return styles


def _extract_element_style(node: RenderNode) -> dict[str, Any]:
    """Extract style for a single element."""
    elem = node.element
    style: dict[str, Any] = {
        "type": node.element_type,
    }

    # Position - relative if has parent, absolute otherwise
    if node.parent is not None:
        rel_bounds = node.relative_bounds()
        style["position"] = {
            "x": round(rel_bounds.x, 2),
            "y": round(rel_bounds.y, 2),
            "w": round(rel_bounds.w, 2),
            "h": round(rel_bounds.h, 2),
            "relative": True,
        }
    else:
        style["position"] = {
            "x": round(node.bounds.x, 2),
            "y": round(node.bounds.y, 2),
            "w": round(node.bounds.w, 2),
            "h": round(node.bounds.h, 2),
            "relative": False,
        }

    # Extract shape properties
    if "shape" in elem:
        shape = elem["shape"]
        shape_props = shape.get("shapeProperties", {})

        # Fill
        fill = _extract_fill(shape_props)
        if fill:
            style["fill"] = fill

        # Outline/stroke
        stroke = _extract_stroke(shape_props)
        if stroke:
            style["stroke"] = stroke

        # Shadow
        shadow = _extract_shadow(shape_props)
        if shadow:
            style["shadow"] = shadow

        # Autofit settings (important for text layout)
        autofit = shape_props.get("autofit", {})
        if autofit:
            autofit_type = autofit.get("autofitType")
            if autofit_type:
                style["autofit"] = {"type": autofit_type}
                font_scale = autofit.get("fontScale")
                if font_scale is not None:
                    style["autofit"]["fontScale"] = font_scale
                line_spacing = autofit.get("lineSpacingReduction")
                if line_spacing is not None:
                    style["autofit"]["lineSpacingReduction"] = line_spacing

        # Content alignment (vertical alignment of text)
        content_alignment = shape_props.get("contentAlignment")
        if content_alignment:
            style["contentAlignment"] = content_alignment

        # Text styles
        if "text" in shape:
            text_style = _extract_text_style(shape["text"])
            if text_style:
                style["text"] = text_style

    # Extract line properties
    if "line" in elem:
        line = elem["line"]
        line_props = line.get("lineProperties", {})

        # Line type
        style["lineType"] = line.get("lineType", "STRAIGHT_LINE")
        style["lineCategory"] = line.get("lineCategory", "STRAIGHT")

        # Stroke for line
        stroke = _extract_line_stroke(line_props)
        if stroke:
            style["stroke"] = stroke

        # Arrow heads
        if "startArrow" in line_props:
            style["startArrow"] = line_props["startArrow"]
        if "endArrow" in line_props:
            style["endArrow"] = line_props["endArrow"]

    # Extract image properties
    if "image" in elem:
        image = elem["image"]
        style["contentUrl"] = image.get("contentUrl", "")
        style["sourceUrl"] = image.get("sourceUrl", "")

        image_props = image.get("imageProperties", {})
        if image_props:
            style["imageProperties"] = _extract_image_properties(image_props)

        # Store native image size and scale factors for accurate copy
        size = elem.get("size", {})
        transform = elem.get("transform", {})
        if size and transform:
            native_w = size.get("width", {}).get("magnitude", 0)
            native_h = size.get("height", {}).get("magnitude", 0)
            scale_x = transform.get("scaleX", 1)
            scale_y = transform.get("scaleY", 1)
            style["nativeSize"] = {
                "w": native_w,  # EMU
                "h": native_h,  # EMU
            }
            style["nativeScale"] = {
                "x": scale_x,
                "y": scale_y,
            }

    return style


def _extract_fill(shape_props: dict[str, Any]) -> dict[str, Any] | None:
    """Extract fill properties."""
    fill_data = shape_props.get("shapeBackgroundFill", {})

    if fill_data.get("propertyState") == "NOT_RENDERED":
        return {"type": "none"}

    solid_fill = fill_data.get("solidFill", {})
    if solid_fill:
        color = _extract_color(solid_fill.get("color", {}))
        alpha = solid_fill.get("alpha", 1)
        return {
            "type": "solid",
            "color": color,
            "alpha": alpha,
        }

    return None


def _extract_stroke(shape_props: dict[str, Any]) -> dict[str, Any] | None:
    """Extract outline/stroke properties."""
    outline = shape_props.get("outline", {})

    if outline.get("propertyState") == "NOT_RENDERED":
        return {"type": "none"}

    outline_fill = outline.get("outlineFill", {})
    solid_fill = outline_fill.get("solidFill", {})

    if solid_fill:
        color = _extract_color(solid_fill.get("color", {}))
        weight = outline.get("weight", {})
        weight_pt = emu_to_pt(weight.get("magnitude", 0)) if weight else 0
        dash_style = outline.get("dashStyle", "SOLID")

        return {
            "color": color,
            "weight": round(weight_pt, 2),
            "dashStyle": dash_style,
        }

    return None


def _extract_line_stroke(line_props: dict[str, Any]) -> dict[str, Any] | None:
    """Extract stroke properties for lines."""
    line_fill = line_props.get("lineFill", {})
    solid_fill = line_fill.get("solidFill", {})

    if solid_fill:
        color = _extract_color(solid_fill.get("color", {}))
        weight = line_props.get("weight", {})
        weight_pt = emu_to_pt(weight.get("magnitude", 0)) if weight else 0
        dash_style = line_props.get("dashStyle", "SOLID")

        return {
            "color": color,
            "weight": round(weight_pt, 2),
            "dashStyle": dash_style,
        }

    return None


def _extract_shadow(shape_props: dict[str, Any]) -> dict[str, Any] | None:
    """Extract shadow properties."""
    shadow = shape_props.get("shadow", {})

    if shadow.get("propertyState") == "NOT_RENDERED":
        return {"type": "none"}

    if shadow.get("type"):
        color = _extract_color(shadow.get("color", {}))
        blur = shadow.get("blurRadius", {})
        blur_pt = emu_to_pt(blur.get("magnitude", 0)) if blur else 0

        return {
            "type": shadow.get("type", "OUTER"),
            "color": color,
            "blurRadius": round(blur_pt, 2),
            "alignment": shadow.get("alignment", "BOTTOM_LEFT"),
            "alpha": shadow.get("alpha", 1),
        }

    return None


def _extract_color(color_data: dict[str, Any]) -> str:
    """Extract color as hex string or theme reference."""
    rgb = color_data.get("rgbColor", {})
    if rgb and any(rgb.values()):
        r = int(rgb.get("red", 0) * 255)
        g = int(rgb.get("green", 0) * 255)
        b = int(rgb.get("blue", 0) * 255)
        return f"#{r:02x}{g:02x}{b:02x}"

    theme_color = color_data.get("themeColor")
    if theme_color:
        return f"@{theme_color}"

    return "#000000"


def _extract_text_style(text_data: dict[str, Any]) -> dict[str, Any] | None:
    """Extract text styling including paragraph and run styles."""
    text_elements = text_data.get("textElements", [])
    if not text_elements:
        return None

    paragraphs: list[dict[str, Any]] = []
    current_paragraph: dict[str, Any] | None = None

    for te in text_elements:
        if "paragraphMarker" in te:
            # Start new paragraph
            if current_paragraph:
                paragraphs.append(current_paragraph)

            pm = te["paragraphMarker"]
            para_style = pm.get("style", {})
            current_paragraph = {
                "style": _extract_paragraph_style(para_style),
                "runs": [],
            }

        elif "textRun" in te:
            if current_paragraph is None:
                current_paragraph = {"style": {}, "runs": []}

            tr = te["textRun"]
            start_idx = te.get("startIndex", 0)
            end_idx = te.get("endIndex", 0)
            content = tr.get("content", "")
            run_style = tr.get("style", {})

            current_paragraph["runs"].append(
                {
                    "range": [start_idx, end_idx],
                    "content": content,
                    "style": _extract_run_style(run_style),
                }
            )

    if current_paragraph:
        paragraphs.append(current_paragraph)

    return {"paragraphs": paragraphs} if paragraphs else None


def _extract_paragraph_style(para_style: dict[str, Any]) -> dict[str, Any]:
    """Extract paragraph-level styling."""
    style: dict[str, Any] = {}

    if "alignment" in para_style:
        style["alignment"] = para_style["alignment"]

    if "lineSpacing" in para_style:
        style["lineSpacing"] = para_style["lineSpacing"]

    if "spaceAbove" in para_style:
        magnitude = para_style["spaceAbove"].get("magnitude", 0)
        style["spaceAbove"] = round(emu_to_pt(magnitude), 2)

    if "spaceBelow" in para_style:
        magnitude = para_style["spaceBelow"].get("magnitude", 0)
        style["spaceBelow"] = round(emu_to_pt(magnitude), 2)

    if "indentStart" in para_style:
        magnitude = para_style["indentStart"].get("magnitude", 0)
        style["indentStart"] = round(emu_to_pt(magnitude), 2)

    if "indentFirstLine" in para_style:
        magnitude = para_style["indentFirstLine"].get("magnitude", 0)
        style["indentFirstLine"] = round(emu_to_pt(magnitude), 2)

    if "direction" in para_style:
        style["direction"] = para_style["direction"]

    return style


def _extract_run_style(run_style: dict[str, Any]) -> dict[str, Any]:
    """Extract text run styling (character-level)."""
    style: dict[str, Any] = {}

    # Font family
    if "fontFamily" in run_style:
        style["fontFamily"] = run_style["fontFamily"]
    elif "weightedFontFamily" in run_style:
        wff = run_style["weightedFontFamily"]
        style["fontFamily"] = wff.get("fontFamily", "")
        if "weight" in wff:
            style["fontWeight"] = wff["weight"]

    # Font size
    if "fontSize" in run_style:
        size = run_style["fontSize"]
        if isinstance(size, dict):
            magnitude = size.get("magnitude", 0)
            unit = size.get("unit", "PT")
            if unit == "EMU":
                style["fontSize"] = round(emu_to_pt(magnitude), 2)
            else:
                # Already in PT
                style["fontSize"] = magnitude
        else:
            style["fontSize"] = size

    # Colors
    if "foregroundColor" in run_style:
        opt_color = run_style["foregroundColor"].get("opaqueColor", {})
        style["color"] = _extract_color(opt_color)

    if "backgroundColor" in run_style:
        opt_color = run_style["backgroundColor"].get("opaqueColor", {})
        style["backgroundColor"] = _extract_color(opt_color)

    # Text decorations
    if run_style.get("bold"):
        style["bold"] = True
    if run_style.get("italic"):
        style["italic"] = True
    if run_style.get("underline"):
        style["underline"] = True
    if run_style.get("strikethrough"):
        style["strikethrough"] = True
    if run_style.get("smallCaps"):
        style["smallCaps"] = True

    # Baseline offset
    if "baselineOffset" in run_style:
        style["baselineOffset"] = run_style["baselineOffset"]

    # Link
    if "link" in run_style:
        link = run_style["link"]
        if "url" in link:
            style["link"] = link["url"]
        elif "slideIndex" in link:
            style["linkSlideIndex"] = link["slideIndex"]

    return style


def _extract_image_properties(image_props: dict[str, Any]) -> dict[str, Any]:
    """Extract image-specific properties."""
    props: dict[str, Any] = {}

    if "transparency" in image_props:
        props["transparency"] = image_props["transparency"]

    if "brightness" in image_props:
        props["brightness"] = image_props["brightness"]

    if "contrast" in image_props:
        props["contrast"] = image_props["contrast"]

    if "cropProperties" in image_props:
        crop = image_props["cropProperties"]
        props["crop"] = {
            "left": crop.get("leftOffset", 0),
            "right": crop.get("rightOffset", 0),
            "top": crop.get("topOffset", 0),
            "bottom": crop.get("bottomOffset", 0),
        }

    if "recolor" in image_props:
        props["recolor"] = image_props["recolor"].get("name", "")

    if "shadow" in image_props:
        props["shadow"] = _extract_shadow({"shadow": image_props["shadow"]})

    return props
