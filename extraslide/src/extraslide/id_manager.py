"""ID management for clean IDs.

Assigns short, readable IDs to elements and maintains mapping to Google object IDs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class IDManager:
    """Manages assignment of clean IDs to elements.

    Clean IDs use prefixes:
    - s1, s2, ... for slides
    - e1, e2, ... for page elements (shapes, images, lines)
    - g1, g2, ... for groups
    - m1, m2, ... for masters
    - l1, l2, ... for layouts

    The mapping from clean ID to Google object ID is stored for use during push.
    """

    # Mapping: clean_id -> google_object_id
    id_mapping: dict[str, str] = field(default_factory=dict)

    # Reverse mapping: google_object_id -> clean_id
    _reverse_mapping: dict[str, str] = field(default_factory=dict)

    # Counters for each prefix
    _counters: dict[str, int] = field(default_factory=dict)

    def _next_id(self, prefix: str) -> str:
        """Generate next ID for a given prefix."""
        count = self._counters.get(prefix, 0) + 1
        self._counters[prefix] = count
        return f"{prefix}{count}"

    def assign_slide_id(self, google_id: str) -> str:
        """Assign a clean slide ID."""
        clean_id = self._next_id("s")
        self.id_mapping[clean_id] = google_id
        self._reverse_mapping[google_id] = clean_id
        return clean_id

    def assign_element_id(self, google_id: str) -> str:
        """Assign a clean element ID."""
        clean_id = self._next_id("e")
        self.id_mapping[clean_id] = google_id
        self._reverse_mapping[google_id] = clean_id
        return clean_id

    def assign_group_id(self, google_id: str) -> str:
        """Assign a clean group ID."""
        clean_id = self._next_id("g")
        self.id_mapping[clean_id] = google_id
        self._reverse_mapping[google_id] = clean_id
        return clean_id

    def assign_master_id(self, google_id: str) -> str:
        """Assign a clean master ID."""
        clean_id = self._next_id("m")
        self.id_mapping[clean_id] = google_id
        self._reverse_mapping[google_id] = clean_id
        return clean_id

    def assign_layout_id(self, google_id: str) -> str:
        """Assign a clean layout ID."""
        clean_id = self._next_id("l")
        self.id_mapping[clean_id] = google_id
        self._reverse_mapping[google_id] = clean_id
        return clean_id

    def get_clean_id(self, google_id: str) -> str | None:
        """Get clean ID for a Google object ID."""
        return self._reverse_mapping.get(google_id)

    def get_google_id(self, clean_id: str) -> str | None:
        """Get Google object ID for a clean ID."""
        return self.id_mapping.get(clean_id)

    def to_dict(self) -> dict[str, str]:
        """Export mapping as dictionary for JSON serialization."""
        return dict(self.id_mapping)

    @classmethod
    def from_dict(cls, mapping: dict[str, str]) -> IDManager:
        """Create IDManager from a saved mapping dictionary."""
        manager = cls()
        manager.id_mapping = dict(mapping)
        manager._reverse_mapping = {v: k for k, v in mapping.items()}

        # Reconstruct counters from existing IDs
        for clean_id in mapping:
            prefix = clean_id.rstrip("0123456789")
            num = int(clean_id[len(prefix) :])
            manager._counters[prefix] = max(manager._counters.get(prefix, 0), num)

        return manager


def assign_ids(presentation: dict[str, Any]) -> IDManager:
    """Assign clean IDs to all elements in a presentation.

    Processes in order:
    1. Masters
    2. Layouts
    3. Slides (in order)
       - Page elements within each slide (in document order)

    Args:
        presentation: Full presentation data from Google Slides API

    Returns:
        IDManager with all IDs assigned
    """
    manager = IDManager()

    # Assign master IDs
    for master in presentation.get("masters", []):
        google_id = master.get("objectId", "")
        if google_id:
            manager.assign_master_id(google_id)
            _assign_page_element_ids(master.get("pageElements", []), manager)

    # Assign layout IDs
    for layout in presentation.get("layouts", []):
        google_id = layout.get("objectId", "")
        if google_id:
            manager.assign_layout_id(google_id)
            _assign_page_element_ids(layout.get("pageElements", []), manager)

    # Assign slide IDs and their elements
    for slide in presentation.get("slides", []):
        google_id = slide.get("objectId", "")
        if google_id:
            manager.assign_slide_id(google_id)
            _assign_page_element_ids(slide.get("pageElements", []), manager)

    return manager


def _assign_page_element_ids(
    elements: list[dict[str, Any]], manager: IDManager
) -> None:
    """Assign IDs to page elements, including group children."""
    for elem in elements:
        google_id = elem.get("objectId", "")
        if not google_id:
            continue

        # Check if this is a group
        if "elementGroup" in elem:
            manager.assign_group_id(google_id)
            # Recursively assign IDs to children
            children = elem["elementGroup"].get("children", [])
            _assign_page_element_ids(children, manager)
        else:
            manager.assign_element_id(google_id)
