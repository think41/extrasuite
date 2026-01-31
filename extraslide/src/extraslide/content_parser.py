"""Parser for the new minimal SML content format.

Parses content.sml files back into structured data for diffing.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ParsedElement:
    """A parsed element from content.sml."""

    # Clean ID
    clean_id: str

    # Element tag (Rect, TextBox, Group, etc.)
    tag: str

    # Position (only for root elements)
    x: float | None = None
    y: float | None = None
    w: float | None = None
    h: float | None = None

    # Pattern hint
    pattern_id: str | None = None

    # Text content (list of paragraph texts)
    paragraphs: list[str] = field(default_factory=list)

    # Children
    children: list[ParsedElement] = field(default_factory=list)

    # Parent ID (for tree reconstruction)
    parent_id: str | None = None

    @property
    def has_position(self) -> bool:
        """Check if this element has position attributes."""
        return self.x is not None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result: dict[str, Any] = {
            "id": self.clean_id,
            "tag": self.tag,
        }
        if self.has_position:
            result["position"] = {
                "x": self.x,
                "y": self.y,
                "w": self.w,
                "h": self.h,
            }
        if self.pattern_id:
            result["pattern"] = self.pattern_id
        if self.paragraphs:
            result["text"] = self.paragraphs
        if self.children:
            result["children"] = [c.to_dict() for c in self.children]
        return result


def parse_slide_content(content: str) -> list[ParsedElement]:
    """Parse a slide's content.sml into structured elements.

    Args:
        content: The content.sml XML string

    Returns:
        List of root ParsedElement objects
    """
    if not content.strip():
        return []

    # Wrap in a root element for valid XML
    wrapped = f"<Root>{content}</Root>"

    try:
        root = ET.fromstring(wrapped)
    except ET.ParseError as e:
        raise ValueError(f"Invalid content.sml XML: {e}") from e

    return [_parse_element(child, None) for child in root]


def _parse_element(elem: ET.Element, parent_id: str | None) -> ParsedElement:
    """Parse a single XML element."""
    clean_id = elem.get("id", "")

    # Parse position attributes
    x = _parse_float(elem.get("x"))
    y = _parse_float(elem.get("y"))
    w = _parse_float(elem.get("w"))
    h = _parse_float(elem.get("h"))

    # Parse pattern hint
    pattern_id = elem.get("pattern")

    # Parse text paragraphs
    paragraphs = []
    for p_elem in elem.findall("P"):
        if p_elem.text:
            paragraphs.append(p_elem.text)

    # Parse children (excluding P elements)
    children = []
    for child in elem:
        if child.tag != "P":
            children.append(_parse_element(child, clean_id))

    return ParsedElement(
        clean_id=clean_id,
        tag=elem.tag,
        x=x,
        y=y,
        w=w,
        h=h,
        pattern_id=pattern_id,
        paragraphs=paragraphs,
        children=children,
        parent_id=parent_id,
    )


def _parse_float(value: str | None) -> float | None:
    """Parse a float value from string."""
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def flatten_elements(roots: list[ParsedElement]) -> dict[str, ParsedElement]:
    """Flatten parsed elements into a dictionary by clean_id.

    Args:
        roots: List of root ParsedElement objects

    Returns:
        Dictionary mapping clean_id to ParsedElement
    """
    result: dict[str, ParsedElement] = {}

    def _collect(elem: ParsedElement) -> None:
        if elem.clean_id:
            result[elem.clean_id] = elem
        for child in elem.children:
            _collect(child)

    for root in roots:
        _collect(root)

    return result


def parse_all_slides(slides_dir: str) -> dict[str, list[ParsedElement]]:
    """Parse all slide content files in a directory.

    Args:
        slides_dir: Path to the slides/ directory

    Returns:
        Dictionary mapping slide index (e.g., "01") to list of ParsedElement
    """
    slides_path = Path(slides_dir)
    result: dict[str, list[ParsedElement]] = {}

    for slide_folder in sorted(slides_path.iterdir()):
        if slide_folder.is_dir():
            content_file = slide_folder / "content.sml"
            if content_file.exists():
                content = content_file.read_text(encoding="utf-8")
                result[slide_folder.name] = parse_slide_content(content)

    return result
