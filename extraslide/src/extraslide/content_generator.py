"""Generate minimal SML content from render trees.

Produces clean, minimal XML with:
- Clean IDs on all elements
- Position only on root-level elements (children have no position)
- Pattern hints as attributes
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
    pattern_hints: dict[str, str] | None = None,
) -> str:
    """Generate minimal SML content for a slide.

    Args:
        roots: Root nodes for this slide
        pattern_hints: Optional mapping of clean_id to pattern_id

    Returns:
        Minimal SML XML string
    """
    if pattern_hints is None:
        pattern_hints = {}

    lines: list[str] = []

    for root in roots:
        _generate_node(root, lines, pattern_hints, indent=0, is_root=True)

    return "\n".join(lines)


def _generate_node(
    node: RenderNode,
    lines: list[str],
    pattern_hints: dict[str, str],
    indent: int,
    is_root: bool,
) -> None:
    """Generate XML for a single node and its children."""
    if not node.clean_id:
        return

    prefix = "  " * indent
    tag = _get_tag_name(node)
    attrs = _build_attributes(node, pattern_hints, is_root)

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
            _generate_node(child, lines, pattern_hints, indent + 1, is_root=False)

        # Closing tag
        lines.append(f"{prefix}</{tag}>")


def _get_tag_name(node: RenderNode) -> str:
    """Get the XML tag name for an element type."""
    elem_type = node.element_type

    # Map Google Slides types to concise tag names
    tag_map = {
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
        "SHAPE": "Shape",
        # Add more as needed
    }

    return tag_map.get(elem_type, elem_type)


def _build_attributes(
    node: RenderNode,
    pattern_hints: dict[str, str],
    is_root: bool,
) -> str:
    """Build attribute string for an element."""
    attrs: list[str] = []

    # Always include clean ID
    attrs.append(f'id="{node.clean_id}"')

    # Position - only for root elements
    if is_root:
        bounds = node.bounds
        attrs.append(f'x="{round(bounds.x, 1)}"')
        attrs.append(f'y="{round(bounds.y, 1)}"')
        attrs.append(f'w="{round(bounds.w, 1)}"')
        attrs.append(f'h="{round(bounds.h, 1)}"')

    # Pattern hint if available
    pattern_id = pattern_hints.get(node.clean_id)
    if pattern_id:
        attrs.append(f'pattern="{pattern_id}"')

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
    pattern_hints: dict[str, str] | None = None,
) -> dict[str, str]:
    """Generate content for all slides in a presentation.

    Args:
        slides_data: List of (slide_clean_id, roots) tuples
        pattern_hints: Optional mapping of clean_id to pattern_id

    Returns:
        Dictionary mapping slide_clean_id to content XML string
    """
    if pattern_hints is None:
        pattern_hints = {}

    result: dict[str, str] = {}

    for slide_id, roots in slides_data:
        content = generate_slide_content(roots, pattern_hints)
        result[slide_id] = content

    return result
