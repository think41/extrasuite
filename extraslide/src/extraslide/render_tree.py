"""Render tree construction.

Converts flat element list from Google Slides API into visual containment hierarchy.
Elements that are visually contained within others become children in the tree.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from extraslide.bounds import BoundingBox, Transform, get_bounds, get_group_bounds


@dataclass
class RenderNode:
    """A node in the render tree.

    Represents an element with its visual containment children.
    """

    # Element data from API
    element: dict[str, Any]

    # Computed bounding box
    bounds: BoundingBox

    # Clean ID (assigned by IDManager)
    clean_id: str = ""

    # Children in the render tree (visually contained elements)
    children: list[RenderNode] = field(default_factory=list)

    # Parent node (None for top-level elements)
    parent: RenderNode | None = None

    # Pattern ID if this element matches a detected pattern
    pattern_id: str | None = None

    @property
    def google_id(self) -> str:
        """Get the Google object ID."""
        object_id: str = self.element.get("objectId", "")
        return object_id

    @property
    def element_type(self) -> str:
        """Get the element type (shape type, IMAGE, LINE, GROUP, etc.)."""
        if "shape" in self.element:
            shape_type: str = self.element["shape"].get("shapeType", "SHAPE")
            return shape_type
        if "image" in self.element:
            return "IMAGE"
        if "line" in self.element:
            return "LINE"
        if "elementGroup" in self.element:
            return "GROUP"
        if "table" in self.element:
            return "TABLE"
        if "video" in self.element:
            return "VIDEO"
        if "sheetsChart" in self.element:
            return "SHEETS_CHART"
        return "UNKNOWN"

    @property
    def is_group(self) -> bool:
        """Check if this is a group element."""
        return "elementGroup" in self.element

    @property
    def has_text(self) -> bool:
        """Check if this element contains text."""
        if "shape" in self.element:
            return "text" in self.element["shape"]
        return False

    def get_text_content(self) -> str | None:
        """Extract text content from the element."""
        if not self.has_text:
            return None

        shape = self.element.get("shape", {})
        text = shape.get("text", {})
        text_elements = text.get("textElements", [])

        texts = []
        for te in text_elements:
            if "textRun" in te:
                content = te["textRun"].get("content", "").strip()
                if content:
                    texts.append(content)

        return " ".join(texts) if texts else None

    @property
    def depth(self) -> int:
        """Compute depth of this subtree."""
        if not self.children:
            return 1
        return 1 + max(child.depth for child in self.children)

    @property
    def node_count(self) -> int:
        """Count total nodes in this subtree."""
        return 1 + sum(child.node_count for child in self.children)

    def relative_bounds(self) -> BoundingBox:
        """Get bounds relative to parent.

        If no parent, returns absolute bounds.
        """
        if self.parent is None:
            return self.bounds
        return self.bounds.relative_to(self.parent.bounds)


def build_render_tree(
    elements: list[dict[str, Any]],
    id_manager: Any | None = None,
    containment_threshold: float = 0.7,
) -> list[RenderNode]:
    """Build render tree from flat element list.

    Creates a visual containment hierarchy where elements that are visually
    contained within larger elements become children.

    Args:
        elements: List of pageElements from Google Slides API
        id_manager: Optional IDManager to look up clean IDs
        containment_threshold: Fraction of area that must be inside for containment

    Returns:
        List of root nodes (top-level elements)
    """
    if not elements:
        return []

    # First, flatten any API groups and create nodes
    nodes = _create_nodes(elements, id_manager)

    if not nodes:
        return []

    # Sort by area descending (largest first = potential parents first)
    nodes.sort(key=lambda n: -n.bounds.area)

    # Build containment tree
    roots: list[RenderNode] = []

    for node in nodes:
        # Find smallest container that contains this element
        best_parent: RenderNode | None = None
        best_area = float("inf")

        for potential_parent in nodes:
            if potential_parent is node:
                continue
            if potential_parent.bounds.area <= node.bounds.area:
                continue
            if (
                potential_parent.bounds.contains(node.bounds, containment_threshold)
                and potential_parent.bounds.area < best_area
            ):
                best_parent = potential_parent
                best_area = potential_parent.bounds.area

        if best_parent:
            best_parent.children.append(node)
            node.parent = best_parent
        else:
            roots.append(node)

    # Sort children by position (top-left to bottom-right)
    _sort_children(roots)

    return roots


def _create_nodes(
    elements: list[dict[str, Any]],
    id_manager: Any | None,
    parent_transform: Transform | None = None,
) -> list[RenderNode]:
    """Create RenderNodes from elements, handling groups.

    Args:
        elements: List of pageElements from Google Slides API
        id_manager: Optional IDManager to look up clean IDs
        parent_transform: Transform from parent element (for nested groups)
    """
    nodes: list[RenderNode] = []

    for elem in elements:
        google_id = elem.get("objectId", "")
        clean_id = ""
        if id_manager:
            clean_id = id_manager.get_clean_id(google_id) or ""

        # Handle groups specially - they contain children
        if "elementGroup" in elem:
            # Get this group's transform and compose with parent
            group_transform = Transform.from_element(elem)
            if parent_transform:
                composed_transform = parent_transform.compose(group_transform)
            else:
                composed_transform = group_transform

            # Create nodes for children, passing composed transform
            children_elements = elem["elementGroup"].get("children", [])
            child_nodes = _create_nodes(
                children_elements, id_manager, composed_transform
            )

            # Compute group bounds from children
            if child_nodes:
                child_bounds = [n.bounds for n in child_nodes]
                group_bounds = get_group_bounds(child_bounds)
            else:
                group_bounds = get_bounds(elem, parent_transform)

            # Create group node
            group_node = RenderNode(
                element=elem,
                bounds=group_bounds,
                clean_id=clean_id,
            )

            # Attach children to group (these are API group children, not render tree children)
            # For groups, we keep the API structure
            for child_node in child_nodes:
                child_node.parent = group_node
                group_node.children.append(child_node)

            nodes.append(group_node)
        else:
            # Regular element - compute bounds with parent transform
            bounds = get_bounds(elem, parent_transform)
            node = RenderNode(
                element=elem,
                bounds=bounds,
                clean_id=clean_id,
            )
            nodes.append(node)

    return nodes


def _sort_children(nodes: list[RenderNode]) -> None:
    """Recursively sort children by position (top-left to bottom-right)."""
    for node in nodes:
        if node.children:
            node.children.sort(key=lambda n: (n.bounds.y, n.bounds.x))
            _sort_children(node.children)


def flatten_tree(roots: list[RenderNode]) -> list[RenderNode]:
    """Flatten render tree to list of all nodes (depth-first)."""
    result: list[RenderNode] = []

    def _collect(node: RenderNode) -> None:
        result.append(node)
        for child in node.children:
            _collect(child)

    for root in roots:
        _collect(root)

    return result
