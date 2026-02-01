"""Generate minimal SML content from render trees.

Produces clean, minimal XML with:
- <Slide> root tag for valid XML
- Clean IDs on all elements
- Absolute position (x, y, w, h) on ALL elements
- Text content preserved
- NO styling (that goes in styles.json)
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any
from xml.sax.saxutils import escape

# Pattern to match XML-invalid control characters (except tab, newline, carriage return)
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _sanitize_text(text: str) -> str:
    """Remove XML-invalid control characters from text."""
    return _CONTROL_CHARS.sub("", text)


if TYPE_CHECKING:
    from extraslide.render_tree import RenderNode


def generate_slide_content(
    roots: list[RenderNode],
    slide_id: str = "s1",
) -> str:
    """Generate minimal SML content for a slide.

    Args:
        roots: Root nodes for this slide
        slide_id: The slide's clean ID (e.g., "s1")

    Returns:
        Minimal SML XML string with <Slide> root tag
    """
    lines: list[str] = []

    # Add Slide root tag
    lines.append(f'<Slide id="{slide_id}">')

    for root in roots:
        _generate_node(root, lines, indent=1)

    lines.append("</Slide>")

    return "\n".join(lines)


def _generate_node(
    node: RenderNode,
    lines: list[str],
    indent: int,
) -> None:
    """Generate XML for a single node and its children."""
    if not node.clean_id:
        return

    prefix = "  " * indent
    tag = _get_tag_name(node)
    attrs = _build_attributes(node)

    # Check if this is a self-closing element (no text, no children)
    has_text = node.has_text
    has_children = bool(node.children)

    if not has_text and not has_children:
        # Self-closing tag
        lines.append(f"{prefix}<{tag}{attrs} />")
    else:
        # Opening tag
        lines.append(f"{prefix}<{tag}{attrs}>")

        # Add text content if present
        if has_text:
            _generate_text_content(node, lines, indent + 1)

        # Add children
        for child in node.children:
            _generate_node(child, lines, indent + 1)

        # Closing tag
        lines.append(f"{prefix}</{tag}>")


def _get_tag_name(node: RenderNode) -> str:
    """Get the XML tag name for an element type."""
    elem_type = node.element_type

    # Map Google Slides types to concise tag names
    # Full spectrum of supported shapes
    tag_map = {
        # Basic shapes
        "RECTANGLE": "Rect",
        "ELLIPSE": "Ellipse",
        "ROUND_RECTANGLE": "RoundRect",
        "TEXT_BOX": "TextBox",
        "IMAGE": "Image",
        "LINE": "Line",
        "GROUP": "Group",
        "TABLE": "Table",
        "VIDEO": "Video",
        "SHEETS_CHART": "Chart",
        # Triangles
        "TRIANGLE": "Triangle",
        "RIGHT_TRIANGLE": "RightTriangle",
        # Parallelograms
        "PARALLELOGRAM": "Parallelogram",
        "TRAPEZOID": "Trapezoid",
        # Polygons
        "PENTAGON": "Pentagon",
        "HEXAGON": "Hexagon",
        "HEPTAGON": "Heptagon",
        "OCTAGON": "Octagon",
        "DECAGON": "Decagon",
        "DODECAGON": "Dodecagon",
        # Stars
        "STAR_4": "Star4",
        "STAR_5": "Star5",
        "STAR_6": "Star6",
        "STAR_8": "Star8",
        "STAR_10": "Star10",
        "STAR_12": "Star12",
        "STAR_16": "Star16",
        "STAR_24": "Star24",
        "STAR_32": "Star32",
        # Other shapes
        "DIAMOND": "Diamond",
        "CHEVRON": "Chevron",
        "HOME_PLATE": "HomePlate",
        "PLUS": "Plus",
        "DONUT": "Donut",
        "PIE": "Pie",
        "ARC": "Arc",
        "CHORD": "Chord",
        "BLOCK_ARC": "BlockArc",
        "FRAME": "Frame",
        "HALF_FRAME": "HalfFrame",
        "CORNER": "Corner",
        "DIAGONAL_STRIPE": "DiagonalStripe",
        "L_SHAPE": "LShape",
        "CAN": "Can",
        "CUBE": "Cube",
        "BEVEL": "Bevel",
        "FOLDED_CORNER": "FoldedCorner",
        "SMILEY_FACE": "SmileyFace",
        "HEART": "Heart",
        "LIGHTNING_BOLT": "LightningBolt",
        "SUN": "Sun",
        "MOON": "Moon",
        "CLOUD": "Cloud",
        "PLAQUE": "Plaque",
        # Arrows
        "ARROW": "Arrow",
        "LEFT_ARROW": "ArrowLeft",
        "RIGHT_ARROW": "ArrowRight",
        "UP_ARROW": "ArrowUp",
        "DOWN_ARROW": "ArrowDown",
        "LEFT_RIGHT_ARROW": "ArrowLeftRight",
        "UP_DOWN_ARROW": "ArrowUpDown",
        "QUAD_ARROW": "ArrowQuad",
        "LEFT_RIGHT_UP_ARROW": "ArrowLeftRightUp",
        "BENT_ARROW": "ArrowBent",
        "U_TURN_ARROW": "ArrowUTurn",
        "CURVED_LEFT_ARROW": "ArrowCurvedLeft",
        "CURVED_RIGHT_ARROW": "ArrowCurvedRight",
        "CURVED_UP_ARROW": "ArrowCurvedUp",
        "CURVED_DOWN_ARROW": "ArrowCurvedDown",
        "STRIPED_RIGHT_ARROW": "ArrowStripedRight",
        "NOTCHED_RIGHT_ARROW": "ArrowNotchedRight",
        "PENTAGON_ARROW": "ArrowPentagon",
        "CHEVRON_ARROW": "ArrowChevron",
        "CIRCULAR_ARROW": "ArrowCircular",
        # Callouts
        "WEDGE_RECTANGLE_CALLOUT": "CalloutRect",
        "WEDGE_ROUND_RECTANGLE_CALLOUT": "CalloutRoundRect",
        "WEDGE_ELLIPSE_CALLOUT": "CalloutEllipse",
        "CLOUD_CALLOUT": "CalloutCloud",
        # Flowchart shapes
        "FLOW_CHART_PROCESS": "FlowProcess",
        "FLOW_CHART_DECISION": "FlowDecision",
        "FLOW_CHART_INPUT_OUTPUT": "FlowInputOutput",
        "FLOW_CHART_PREDEFINED_PROCESS": "FlowPredefinedProcess",
        "FLOW_CHART_INTERNAL_STORAGE": "FlowInternalStorage",
        "FLOW_CHART_DOCUMENT": "FlowDocument",
        "FLOW_CHART_MULTIDOCUMENT": "FlowMultidocument",
        "FLOW_CHART_TERMINATOR": "FlowTerminator",
        "FLOW_CHART_PREPARATION": "FlowPreparation",
        "FLOW_CHART_MANUAL_INPUT": "FlowManualInput",
        "FLOW_CHART_MANUAL_OPERATION": "FlowManualOperation",
        "FLOW_CHART_CONNECTOR": "FlowConnector",
        "FLOW_CHART_PUNCHED_CARD": "FlowPunchedCard",
        "FLOW_CHART_PUNCHED_TAPE": "FlowPunchedTape",
        "FLOW_CHART_SUMMING_JUNCTION": "FlowSummingJunction",
        "FLOW_CHART_OR": "FlowOr",
        "FLOW_CHART_COLLATE": "FlowCollate",
        "FLOW_CHART_SORT": "FlowSort",
        "FLOW_CHART_EXTRACT": "FlowExtract",
        "FLOW_CHART_MERGE": "FlowMerge",
        "FLOW_CHART_ONLINE_STORAGE": "FlowOnlineStorage",
        "FLOW_CHART_MAGNETIC_TAPE": "FlowMagneticTape",
        "FLOW_CHART_MAGNETIC_DISK": "FlowMagneticDisk",
        "FLOW_CHART_MAGNETIC_DRUM": "FlowMagneticDrum",
        "FLOW_CHART_DISPLAY": "FlowDisplay",
        "FLOW_CHART_DELAY": "FlowDelay",
        "FLOW_CHART_ALTERNATE_PROCESS": "FlowAlternateProcess",
        "FLOW_CHART_OFFPAGE_CONNECTOR": "FlowOffpageConnector",
        "FLOW_CHART_DATA": "FlowData",
        # Equation shapes
        "MATH_PLUS": "MathPlus",
        "MATH_MINUS": "MathMinus",
        "MATH_MULTIPLY": "MathMultiply",
        "MATH_DIVIDE": "MathDivide",
        "MATH_EQUAL": "MathEqual",
        "MATH_NOT_EQUAL": "MathNotEqual",
        # Brackets
        "LEFT_BRACKET": "BracketLeft",
        "RIGHT_BRACKET": "BracketRight",
        "LEFT_BRACE": "BraceLeft",
        "RIGHT_BRACE": "BraceRight",
        "BRACKET_PAIR": "BracketPair",
        "BRACE_PAIR": "BracePair",
        # Ribbons and banners
        "RIBBON": "Ribbon",
        "RIBBON_2": "Ribbon2",
        # Rounded rectangles variants
        "SNIP_ROUND_RECTANGLE": "SnipRoundRect",
        "SNIP_2_SAME_RECTANGLE": "Snip2SameRect",
        "SNIP_2_DIAGONAL_RECTANGLE": "Snip2DiagRect",
        "ROUND_1_RECTANGLE": "Round1Rect",
        "ROUND_2_SAME_RECTANGLE": "Round2SameRect",
        "ROUND_2_DIAGONAL_RECTANGLE": "Round2DiagRect",
        # Custom/unknown
        "CUSTOM": "Custom",
        "SHAPE": "Shape",
    }

    return tag_map.get(elem_type, elem_type)


def _build_attributes(node: RenderNode) -> str:
    """Build attribute string for an element.

    All elements get absolute x, y, w, h positions.
    """
    attrs: list[str] = []

    # Always include clean ID
    attrs.append(f'id="{node.clean_id}"')

    # Absolute position for ALL elements
    bounds = node.bounds
    attrs.append(f'x="{round(bounds.x, 1)}"')
    attrs.append(f'y="{round(bounds.y, 1)}"')
    attrs.append(f'w="{round(bounds.w, 1)}"')
    attrs.append(f'h="{round(bounds.h, 1)}"')

    if attrs:
        return " " + " ".join(attrs)
    return ""


def _generate_text_content(
    node: RenderNode,
    lines: list[str],
    indent: int,
) -> None:
    """Generate text content with paragraph structure."""
    prefix = "  " * indent

    shape = node.element.get("shape", {})
    text = shape.get("text", {})
    text_elements = text.get("textElements", [])

    if not text_elements:
        return

    # Group text runs by paragraph
    paragraphs: list[list[dict[str, Any]]] = []
    current_para: list[dict[str, Any]] = []

    for te in text_elements:
        if "paragraphMarker" in te:
            if current_para:
                paragraphs.append(current_para)
            current_para = []
        elif "textRun" in te:
            current_para.append(te["textRun"])

    if current_para:
        paragraphs.append(current_para)

    # Generate paragraph elements
    for para_runs in paragraphs:
        # Combine runs into single text content
        text_content = ""
        for run in para_runs:
            content = run.get("content", "")
            # Strip trailing newline from paragraph
            content = content.rstrip("\n")
            if content:
                text_content += content

        if text_content.strip():
            sanitized = _sanitize_text(text_content.strip())
            escaped = escape(sanitized)
            lines.append(f"{prefix}<P>{escaped}</P>")


def generate_presentation_content(
    slides_data: list[tuple[str, list[RenderNode]]],
) -> dict[str, str]:
    """Generate content for all slides in a presentation.

    Args:
        slides_data: List of (slide_clean_id, roots) tuples

    Returns:
        Dictionary mapping slide_clean_id to content XML string
    """
    result: dict[str, str] = {}

    for slide_id, roots in slides_data:
        content = generate_slide_content(roots, slide_id)
        result[slide_id] = content

    return result
