"""Slide processor for the new ID-based architecture.

Orchestrates the conversion from Google Slides API response to the new format:
- id_mapping.json: clean_id -> google_object_id
- styles.json: clean_id -> style properties (with relative positions for children)
- slides/NN/content.sml: minimal XML with IDs, positions, text, pattern hints
- slides/NN/thumbnail.png: visual reference (optional)
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

from extraslide.content_generator import generate_slide_content
from extraslide.id_manager import assign_ids
from extraslide.patterns import assign_pattern_hints
from extraslide.render_tree import RenderNode, build_render_tree
from extraslide.style_extractor import extract_styles
from extraslide.units import emu_to_pt


def process_presentation(
    presentation_data: dict[str, Any],
) -> dict[str, Any]:
    """Process a presentation into the new format.

    Args:
        presentation_data: Full presentation data from Google Slides API

    Returns:
        Dictionary with:
        - id_mapping: dict mapping clean_id to google_object_id
        - styles: dict mapping clean_id to style properties
        - slides: list of dicts with slide_id and content
        - patterns: dict mapping clean_id to pattern_id (hints)
        - presentation_info: basic presentation metadata
    """
    # Step 1: Assign clean IDs to all elements
    id_manager = assign_ids(presentation_data)

    # Step 2: Build render trees for all slides
    all_slide_roots: list[RenderNode] = []
    slides_data: list[
        tuple[str, str, list[RenderNode]]
    ] = []  # (slide_id, index, roots)

    for idx, slide in enumerate(presentation_data.get("slides", []), 1):
        google_slide_id = slide.get("objectId", "")
        slide_clean_id = id_manager.get_clean_id(google_slide_id)

        if not slide_clean_id:
            continue

        elements = slide.get("pageElements", [])
        roots = build_render_tree(elements, id_manager)

        slides_data.append((slide_clean_id, f"{idx:02d}", roots))
        all_slide_roots.extend(roots)

    # Step 3: Detect patterns across all slides
    pattern_hints = assign_pattern_hints(all_slide_roots)

    # Step 4: Extract styles from all nodes
    all_styles: dict[str, dict[str, Any]] = {}
    for _, _, roots in slides_data:
        slide_styles = extract_styles(roots)
        all_styles.update(slide_styles)

    # Step 5: Generate content for each slide
    slides_output: list[dict[str, Any]] = []
    for slide_id, slide_index, roots in slides_data:
        content = generate_slide_content(roots, pattern_hints)
        slides_output.append(
            {
                "slide_id": slide_id,
                "slide_index": slide_index,
                "content": content,
            }
        )

    # Step 6: Gather presentation info
    presentation_info = {
        "title": presentation_data.get("title", "Untitled"),
        "presentationId": presentation_data.get("presentationId", ""),
        "slideCount": len(slides_data),
        "pageSize": _extract_page_size(presentation_data),
    }

    return {
        "id_mapping": id_manager.to_dict(),
        "styles": all_styles,
        "slides": slides_output,
        "patterns": pattern_hints,
        "presentation_info": presentation_info,
    }


def _extract_page_size(presentation_data: dict[str, Any]) -> dict[str, Any]:
    """Extract page size from presentation data."""
    page_size = presentation_data.get("pageSize", {})
    width = page_size.get("width", {})
    height = page_size.get("height", {})

    return {
        "width": round(emu_to_pt(width.get("magnitude", 0)), 1),
        "height": round(emu_to_pt(height.get("magnitude", 0)), 1),
    }


def write_new_format(
    result: dict[str, Any],
    output_dir: Path,
) -> list[Path]:
    """Write the processed presentation to the new folder format.

    Creates:
    - presentation.json: metadata
    - id_mapping.json: clean_id -> google_object_id
    - styles.json: clean_id -> style properties
    - slides/01/content.sml, slides/02/content.sml, ...

    Args:
        result: Output from process_presentation()
        output_dir: Directory to write files to

    Returns:
        List of paths to written files
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    written_files: list[Path] = []

    # Write presentation.json
    presentation_path = output_dir / "presentation.json"
    presentation_path.write_text(
        json.dumps(result["presentation_info"], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    written_files.append(presentation_path)

    # Write id_mapping.json
    id_mapping_path = output_dir / "id_mapping.json"
    id_mapping_path.write_text(
        json.dumps(result["id_mapping"], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    written_files.append(id_mapping_path)

    # Write styles.json
    styles_path = output_dir / "styles.json"
    styles_path.write_text(
        json.dumps(result["styles"], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    written_files.append(styles_path)

    # Write slides
    slides_dir = output_dir / "slides"
    slides_dir.mkdir(parents=True, exist_ok=True)

    for slide_data in result["slides"]:
        slide_index = slide_data["slide_index"]
        content = slide_data["content"]

        slide_folder = slides_dir / slide_index
        slide_folder.mkdir(parents=True, exist_ok=True)

        content_path = slide_folder / "content.sml"
        content_path.write_text(content, encoding="utf-8")
        written_files.append(content_path)

    return written_files


def process_and_write(
    presentation_data: dict[str, Any],
    output_dir: Path,
) -> list[Path]:
    """Convenience function to process and write in one step.

    Args:
        presentation_data: Full presentation data from Google Slides API
        output_dir: Directory to write files to

    Returns:
        List of paths to written files
    """
    result = process_presentation(presentation_data)
    return write_new_format(result, output_dir)
