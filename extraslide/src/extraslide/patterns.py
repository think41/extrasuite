"""Pattern detection for slide elements.

Detects repeated element structures across the presentation.
Patterns are hints for the LLM - they have no operational significance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from extraslide.render_tree import RenderNode


@dataclass
class Pattern:
    """A detected pattern (repeated element structure)."""

    # Pattern ID (p1, p2, ...)
    pattern_id: str

    # List of clean_ids that match this pattern
    instances: list[str] = field(default_factory=list)

    # Description of the pattern for the LLM
    description: str = ""

    # The "canonical" instance (first one found)
    canonical_id: str = ""


def detect_patterns(
    roots: list[RenderNode],
    min_instances: int = 2,
) -> list[Pattern]:
    """Detect repeated element structures across the presentation.

    Args:
        roots: Root nodes of render trees (all slides)
        min_instances: Minimum instances to qualify as a pattern

    Returns:
        List of detected patterns
    """
    # Collect all nodes with their signatures
    signature_to_nodes: dict[str, list[RenderNode]] = {}

    def _collect_node(node: RenderNode) -> None:
        if not node.clean_id:
            return

        sig = _compute_signature(node)
        if sig:
            if sig not in signature_to_nodes:
                signature_to_nodes[sig] = []
            signature_to_nodes[sig].append(node)

        for child in node.children:
            _collect_node(child)

    for root in roots:
        _collect_node(root)

    # Create patterns from signatures with multiple instances
    patterns: list[Pattern] = []
    pattern_counter = 0

    for _sig, nodes in signature_to_nodes.items():
        if len(nodes) >= min_instances:
            pattern_counter += 1
            pattern_id = f"p{pattern_counter}"

            # Get clean IDs
            instance_ids = [n.clean_id for n in nodes if n.clean_id]

            # Generate description
            first_node = nodes[0]
            desc = _generate_description(first_node, len(nodes))

            pattern = Pattern(
                pattern_id=pattern_id,
                instances=instance_ids,
                description=desc,
                canonical_id=instance_ids[0] if instance_ids else "",
            )
            patterns.append(pattern)

            # Assign pattern_id to nodes
            for node in nodes:
                node.pattern_id = pattern_id

    return patterns


def _compute_signature(node: RenderNode) -> str:
    """Compute a structural signature for a node.

    The signature captures the element type, child structure,
    and approximate size ratios - but NOT position or exact dimensions.
    """
    parts: list[str] = []

    # Element type
    parts.append(node.element_type)

    # Has text?
    if node.has_text:
        parts.append("T")

    # Child structure (recursive, but shallow)
    if node.children:
        child_sigs = []
        for child in node.children:
            child_sig = child.element_type
            if child.has_text:
                child_sig += "T"
            child_sigs.append(child_sig)
        parts.append(f"[{','.join(sorted(child_sigs))}]")

    # Approximate aspect ratio (binned)
    if node.bounds.w > 0 and node.bounds.h > 0:
        ratio = node.bounds.w / node.bounds.h
        if ratio < 0.5:
            parts.append("tall")
        elif ratio < 1.5:
            parts.append("square")
        elif ratio < 3:
            parts.append("wide")
        else:
            parts.append("banner")

    return "|".join(parts)


def _generate_description(node: RenderNode, count: int) -> str:
    """Generate a human-readable description of the pattern."""
    elem_type = node.element_type

    # Describe based on element type and children
    if node.is_group:
        child_types = [c.element_type for c in node.children]
        has_text_elements = "TEXT_BOX" in child_types or "RECTANGLE" in child_types
        if has_text_elements and any(c.has_text for c in node.children):
            return f"Group with text ({count} instances)"
        return f"Group with {len(node.children)} elements ({count} instances)"

    if node.has_text:
        text = node.get_text_content()
        if text:
            # Truncate long text
            preview = text[:30] + "..." if len(text) > 30 else text
            return f"{elem_type} with text like '{preview}' ({count} instances)"
        return f"{elem_type} with text ({count} instances)"

    if elem_type == "IMAGE":
        return f"Image ({count} instances)"

    if elem_type == "LINE":
        return f"Line ({count} instances)"

    return f"{elem_type} ({count} instances)"


def assign_pattern_hints(roots: list[RenderNode]) -> dict[str, str]:
    """Detect patterns and return mapping of clean_id to pattern_id.

    This is a convenience function that runs pattern detection
    and returns just the ID mapping for use in content generation.

    Args:
        roots: Root nodes of render trees

    Returns:
        Dictionary mapping clean_id to pattern_id for elements that match patterns
    """
    patterns = detect_patterns(roots)

    hints: dict[str, str] = {}
    for pattern in patterns:
        for instance_id in pattern.instances:
            hints[instance_id] = pattern.pattern_id

    return hints
