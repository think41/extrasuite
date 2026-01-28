"""Overview generation for progressive disclosure.

Generates a lightweight overview.json file that allows LLMs to quickly
understand presentation content without parsing the full SML file.

The overview contains:
- Presentation metadata (title, dimensions, slide count)
- Per-slide summaries (title, full text, word count, image count)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def extract_text_from_page_elements(page_elements: list[dict[str, Any]]) -> str:
    """Recursively extract all text from page elements.

    Args:
        page_elements: List of page element dicts from the API response

    Returns:
        Concatenated text content
    """
    texts: list[str] = []

    for elem in page_elements:
        # Handle shapes with text
        if "shape" in elem:
            shape = elem["shape"]
            if "text" in shape:
                text_elements = shape["text"].get("textElements", [])
                for text_elem in text_elements:
                    if "textRun" in text_elem:
                        content = text_elem["textRun"].get("content", "")
                        content = content.strip()
                        if content:
                            texts.append(content)

        # Handle tables
        if "table" in elem:
            table = elem["table"]
            for row in table.get("tableRows", []):
                for cell in row.get("tableCells", []):
                    if "text" in cell:
                        for text_elem in cell["text"].get("textElements", []):
                            if "textRun" in text_elem:
                                content = text_elem["textRun"].get("content", "")
                                content = content.strip()
                                if content:
                                    texts.append(content)

        # Handle groups (recursive)
        if "elementGroup" in elem:
            children = elem["elementGroup"].get("children", [])
            child_text = extract_text_from_page_elements(children)
            if child_text:
                texts.append(child_text)

    return " ".join(texts)


def extract_title_from_page_elements(
    page_elements: list[dict[str, Any]], max_length: int = 60
) -> str:
    """Extract the title from page elements.

    Looks for the first text element, typically the title placeholder.

    Args:
        page_elements: List of page element dicts
        max_length: Maximum title length

    Returns:
        Title text or empty string
    """
    for elem in page_elements:
        if "shape" in elem:
            shape = elem["shape"]

            # Prefer title placeholders
            placeholder = shape.get("placeholder", {})
            placeholder_type = placeholder.get("type", "")

            if "text" in shape:
                text = extract_text_from_page_elements([elem])
                if text:
                    # If this is a title placeholder, return immediately
                    if placeholder_type in ("TITLE", "CENTERED_TITLE"):
                        return text[:max_length]

                    # Otherwise, continue looking but remember this as fallback
                    if not hasattr(extract_title_from_page_elements, "_fallback"):
                        extract_title_from_page_elements._fallback = text[:max_length]  # type: ignore

    # Return fallback if we have one
    fallback = getattr(extract_title_from_page_elements, "_fallback", "")
    if hasattr(extract_title_from_page_elements, "_fallback"):
        delattr(extract_title_from_page_elements, "_fallback")
    return fallback


def count_images(page_elements: list[dict[str, Any]]) -> int:
    """Count image elements in a page.

    Args:
        page_elements: List of page element dicts

    Returns:
        Number of image elements
    """
    count = 0

    for elem in page_elements:
        if "image" in elem:
            count += 1

        # Handle groups (recursive)
        if "elementGroup" in elem:
            children = elem["elementGroup"].get("children", [])
            count += count_images(children)

    return count


def generate_overview(presentation_data: dict[str, Any]) -> dict[str, Any]:
    """Generate overview.json from raw presentation data.

    Args:
        presentation_data: Raw Google Slides API response

    Returns:
        Overview dict ready for JSON serialization
    """
    # Page size
    page_size = presentation_data.get("pageSize", {})
    width = page_size.get("width", {})
    height = page_size.get("height", {})

    # Format dimensions
    def format_dim(dim: dict[str, Any]) -> str:
        magnitude = dim.get("magnitude", 0)
        unit = dim.get("unit", "EMU")
        if unit == "EMU":
            # Convert EMU to points (1 point = 12700 EMU)
            pts = magnitude / 12700
            return f"{pts:.0f}pt"
        return f"{magnitude}{unit}"

    overview: dict[str, Any] = {
        "presentationId": presentation_data.get("presentationId", ""),
        "title": presentation_data.get("title", ""),
        "dimensions": {
            "w": format_dim(width),
            "h": format_dim(height),
        },
        "slideCount": len(presentation_data.get("slides", [])),
        "slides": [],
    }

    for idx, slide in enumerate(presentation_data.get("slides", []), 1):
        page_elements = slide.get("pageElements", [])

        # Extract text content
        text = extract_text_from_page_elements(page_elements)

        # Extract title
        title = extract_title_from_page_elements(page_elements)

        # Count images
        img_count = count_images(page_elements)

        overview["slides"].append(
            {
                "i": idx,
                "id": slide.get("objectId", ""),
                "t": title,
                "txt": text,
                "w": len(text.split()) if text else 0,
                "img": img_count,
            }
        )

    return overview


def write_overview(overview: dict[str, Any], output_path: Path) -> None:
    """Write overview.json to disk.

    Uses compact JSON formatting to minimize size.

    Args:
        overview: Overview dict from generate_overview()
        output_path: Path to write overview.json
    """
    with output_path.open("w", encoding="utf-8") as f:
        # Use compact separators but keep some readability with indent=2
        # For maximum compression, use separators=(',', ':') and no indent
        json.dump(overview, f, indent=2, ensure_ascii=False)


def read_overview(overview_path: Path) -> dict[str, Any]:
    """Read overview.json from disk.

    Args:
        overview_path: Path to overview.json

    Returns:
        Overview dict
    """
    with overview_path.open(encoding="utf-8") as f:
        result: dict[str, Any] = json.load(f)
        return result
