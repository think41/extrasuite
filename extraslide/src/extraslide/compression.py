"""SML Compression module.

Provides ID removal with external mapping for cleaner SML editing.
Element IDs are verbose (e.g., "g3b91ac73820_0_287") and clutter the XML.
This module removes them and stores a mapping for restoration during diff/push.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


def remove_ids(sml_content: str) -> tuple[str, dict[str, Any]]:
    """Remove element IDs and build an external mapping.

    Element IDs are verbose (e.g., "g3b91ac73820_0_287") and only needed
    for the diff/push operation. This removes them from the XML and stores
    a mapping that can be used to restore them.

    Args:
        sml_content: SML content with IDs

    Returns:
        Tuple of (cleaned_sml, id_mapping)
    """
    # Parse XML
    # Wrap in a root if needed (for Slides-only content)
    try:
        root = ET.fromstring(sml_content)
    except ET.ParseError:
        # Try wrapping
        root = ET.fromstring(f"<Root>{sml_content}</Root>")

    mapping: dict[str, Any] = {"elements": []}

    # Track element positions for XPath generation
    def process_element(
        elem: ET.Element,
        parent_path: str,
        sibling_counts: dict[str, int],
    ) -> dict[str, Any] | None:
        """Process an element and its children, extracting IDs."""
        tag = elem.tag
        sibling_counts[tag] = sibling_counts.get(tag, 0) + 1
        xpath = f"{parent_path}/{tag}[{sibling_counts[tag]}]"

        elem_data: dict[str, Any] = {}

        # Extract and remove ID attributes
        id_attrs = ["id", "layout", "master", "placeholder-parent"]
        for attr in id_attrs:
            if attr in elem.attrib:
                elem_data[attr] = elem.attrib[attr]
                del elem.attrib[attr]

        # Process children
        child_counts: dict[str, int] = {}
        children_data: list[dict[str, Any]] = []

        for child in elem:
            child_data = process_element(child, xpath, child_counts)
            if child_data:
                children_data.append(child_data)

        # Only include in mapping if this element or its children have IDs
        if elem_data or children_data:
            elem_data["xpath"] = xpath
            if children_data:
                elem_data["children"] = children_data
            return elem_data

        return None

    # Process all top-level elements (Slides, Masters, etc.)
    root_counts: dict[str, int] = {}
    for child in root:
        child_data = process_element(child, "", root_counts)
        if child_data:
            mapping["elements"].append(child_data)

    # Convert back to string
    cleaned_sml = ET.tostring(root, encoding="unicode")

    # Remove the wrapper if we added one
    if cleaned_sml.startswith("<Root>"):
        cleaned_sml = cleaned_sml[6:-7]  # Remove <Root> and </Root>

    return cleaned_sml, mapping


def restore_ids(sml_content: str, mapping: dict[str, Any]) -> str:
    """Restore IDs to SML content using the mapping.

    This is called before diff/push to reconstruct the original IDs.

    Args:
        sml_content: SML content without IDs
        mapping: ID mapping from remove_ids()

    Returns:
        SML content with IDs restored
    """
    if not mapping.get("elements"):
        return sml_content

    # Parse XML
    try:
        root = ET.fromstring(sml_content)
    except ET.ParseError:
        root = ET.fromstring(f"<Root>{sml_content}</Root>")

    def find_by_xpath(current: ET.Element, xpath: str) -> ET.Element | None:
        """Find element by simplified XPath."""
        parts = xpath.strip("/").split("/")
        if not parts or not parts[0]:
            return current

        for part in parts:
            match = re.match(r"(\w+)\[(\d+)\]", part)
            if not match:
                return None

            tag, index_str = match.groups()
            index = int(index_str)

            children = [c for c in current if c.tag == tag]
            if index > len(children):
                return None

            current = children[index - 1]

        return current

    def apply_mapping(elem_mapping: dict[str, Any]) -> None:
        """Apply ID mapping to an element."""
        xpath = elem_mapping.get("xpath", "")
        elem = find_by_xpath(root, xpath)

        if elem is not None:
            # Restore ID attributes
            for attr in ["id", "layout", "master", "placeholder-parent"]:
                if attr in elem_mapping:
                    elem.attrib[attr] = elem_mapping[attr]

            # Process children
            for child_mapping in elem_mapping.get("children", []):
                apply_mapping(child_mapping)

    # Apply all mappings
    for elem_mapping in mapping.get("elements", []):
        apply_mapping(elem_mapping)

    # Convert back to string
    result = ET.tostring(root, encoding="unicode")

    # Remove wrapper if present
    if result.startswith("<Root>"):
        result = result[6:-7]

    return result


def save_metadata(metadata: dict[str, Any], meta_dir: Path) -> None:
    """Save ID mapping metadata to .meta directory.

    Args:
        metadata: Dict containing id_mapping
        meta_dir: Path to .meta directory
    """
    meta_dir.mkdir(parents=True, exist_ok=True)

    # Save ID mapping
    if "id_mapping" in metadata:
        mapping_path = meta_dir / "id_mapping.json"
        with mapping_path.open("w", encoding="utf-8") as f:
            json.dump(metadata["id_mapping"], f, indent=2)


def load_metadata(meta_dir: Path) -> dict[str, Any]:
    """Load ID mapping metadata from .meta directory.

    Args:
        meta_dir: Path to .meta directory

    Returns:
        Metadata dict with id_mapping
    """
    metadata: dict[str, Any] = {}

    mapping_path = meta_dir / "id_mapping.json"
    if mapping_path.exists():
        with mapping_path.open(encoding="utf-8") as f:
            metadata["id_mapping"] = json.load(f)

    return metadata
