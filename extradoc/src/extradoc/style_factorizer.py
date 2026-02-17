"""Style factorization for Google Docs.

Extracts styles from a Google Docs document, computes the base style,
and generates minimal style definitions (deviations from base).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from xml.etree.ElementTree import Element

from .style_hash import style_id


@dataclass
class TextRun:
    """A text run with its computed styles."""

    text: str
    char_count: int
    styles: dict[str, str]


@dataclass
class StyleDefinition:
    """A style definition with its ID and properties."""

    id: str
    properties: dict[str, str]

    def to_xml(self) -> Element:
        """Convert to XML element."""
        elem = Element("style")
        elem.set("id", self.id)
        for key, value in sorted(self.properties.items()):
            elem.set(key, value)
        return elem


@dataclass
class FactorizedStyles:
    """Result of style factorization."""

    base_style: StyleDefinition
    deviation_styles: list[StyleDefinition] = field(default_factory=list)

    # Map from original style properties to style ID (for text styles)
    style_map: dict[str, str] = field(default_factory=dict)

    # Cell styles (separate from text styles, prefixed with "cell-")
    cell_styles: list[StyleDefinition] = field(default_factory=list)
    cell_style_map: dict[str, str] = field(default_factory=dict)

    def get_style_id(self, properties: dict[str, str]) -> str:
        """Get the style ID for a set of text style properties.

        Returns "_base" if properties match the base style.
        """
        key = _props_key(properties)
        return self.style_map.get(key, "_base")

    def get_cell_style_id(self, properties: dict[str, str]) -> str | None:
        """Get the style ID for a set of cell style properties.

        Returns None if no style (default cell style).
        """
        if not properties:
            return None
        key = _props_key(properties)
        return self.cell_style_map.get(key)

    def to_xml(self) -> str:
        """Generate styles.xml content."""
        root = Element("styles")

        # Add base style first
        root.append(self.base_style.to_xml())

        # Add text deviation styles
        for style in self.deviation_styles:
            root.append(style.to_xml())

        # Add cell styles
        for style in self.cell_styles:
            root.append(style.to_xml())

        return '<?xml version="1.0" encoding="UTF-8"?>\n' + _indent_xml(root)


def _props_key(props: dict[str, str]) -> str:
    """Generate a hashable key from properties."""
    return "|".join(f"{k}={v}" for k, v in sorted(props.items()))


def _indent_xml(elem: Element, level: int = 0) -> str:
    """Pretty-print XML element."""
    indent = "  " * level
    result = f"{indent}<{elem.tag}"

    for key, value in elem.attrib.items():
        result += f' {key}="{value}"'

    if len(elem) == 0:
        result += "/>\n"
    else:
        result += ">\n"
        for child in elem:
            result += _indent_xml(child, level + 1)
        result += f"{indent}</{elem.tag}>\n"

    return result


# Property extractors for Google Docs text styles
TextStyleExtractor = Callable[[dict[str, Any]], str | None]
ParagraphStyleExtractor = Callable[[dict[str, Any]], str | None]

TEXT_STYLE_PROPS: list[tuple[str, TextStyleExtractor]] = [
    ("font", lambda ts: _get_font(ts)),
    ("size", lambda ts: _get_font_size(ts)),
    ("color", lambda ts: _get_color(ts.get("foregroundColor"))),
    ("bg", lambda ts: _get_color(ts.get("backgroundColor"))),
    ("bold", lambda ts: "1" if ts.get("bold") else None),
    ("italic", lambda ts: "1" if ts.get("italic") else None),
    ("underline", lambda ts: "1" if ts.get("underline") else None),
    ("strikethrough", lambda ts: "1" if ts.get("strikethrough") else None),
]

# Property extractors for Google Docs paragraph styles
PARAGRAPH_STYLE_PROPS: list[tuple[str, ParagraphStyleExtractor]] = [
    ("alignment", lambda ps: ps.get("alignment")),
    ("lineSpacing", lambda ps: _get_line_spacing(ps)),
    ("spaceAbove", lambda ps: _get_dimension(ps.get("spaceAbove"))),
    ("spaceBelow", lambda ps: _get_dimension(ps.get("spaceBelow"))),
    ("indentLeft", lambda ps: _get_dimension(ps.get("indentStart"))),
    ("indentRight", lambda ps: _get_dimension(ps.get("indentEnd"))),
    ("indentFirstLine", lambda ps: _get_dimension(ps.get("indentFirstLine"))),
    # Boolean paragraph properties
    ("keepTogether", lambda ps: "1" if ps.get("keepLinesTogether") else None),
    ("keepNext", lambda ps: "1" if ps.get("keepWithNext") else None),
    ("avoidWidow", lambda ps: "1" if ps.get("avoidWidowAndOrphan") else None),
    # Direction (skip LEFT_TO_RIGHT as it's the default)
    ("direction", lambda ps: _get_direction(ps)),
    # Paragraph background (shading)
    (
        "bgColor",
        lambda ps: (
            _get_color(ps.get("shading", {}).get("backgroundColor"))
            if ps.get("shading")
            else None
        ),
    ),
    # Paragraph borders
    ("borderTop", lambda ps: _get_border(ps.get("borderTop"))),
    ("borderBottom", lambda ps: _get_border(ps.get("borderBottom"))),
    ("borderLeft", lambda ps: _get_border(ps.get("borderLeft"))),
    ("borderRight", lambda ps: _get_border(ps.get("borderRight"))),
]

# Property extractors for Google Docs table cell styles
TableCellStyleExtractor = Callable[[dict[str, Any]], str | None]

TABLE_CELL_STYLE_PROPS: list[tuple[str, TableCellStyleExtractor]] = [
    ("bg", lambda cs: _get_color(cs.get("backgroundColor"))),
    ("valign", lambda cs: _get_valign(cs.get("contentAlignment"))),
    ("paddingTop", lambda cs: _get_dimension(cs.get("paddingTop"))),
    ("paddingBottom", lambda cs: _get_dimension(cs.get("paddingBottom"))),
    ("paddingLeft", lambda cs: _get_dimension(cs.get("paddingLeft"))),
    ("paddingRight", lambda cs: _get_dimension(cs.get("paddingRight"))),
    ("borderTop", lambda cs: _get_border(cs.get("borderTop"))),
    ("borderBottom", lambda cs: _get_border(cs.get("borderBottom"))),
    ("borderLeft", lambda cs: _get_border(cs.get("borderLeft"))),
    ("borderRight", lambda cs: _get_border(cs.get("borderRight"))),
]


def _get_valign(alignment: str | None) -> str | None:
    """Convert content alignment to valign value."""
    if not alignment:
        return None
    mapping = {"TOP": "top", "MIDDLE": "middle", "BOTTOM": "bottom"}
    return mapping.get(alignment)


def _get_border(border_obj: dict[str, Any] | None) -> str | None:
    """Convert border object to string format: width,#color,dashStyle."""
    if not border_obj:
        return None

    width = border_obj.get("width", {})
    width_val = width.get("magnitude", 0)
    if width_val == 0:
        return None

    color = _get_color(border_obj.get("color"))
    dash_style = border_obj.get("dashStyle", "SOLID")

    # Format: width,#color,dashStyle
    parts = [str(width_val)]
    if color:
        parts.append(color)
    else:
        parts.append("#000000")
    parts.append(dash_style)

    return ",".join(parts)


def _get_font(text_style: dict[str, Any]) -> str | None:
    """Extract font family from text style."""
    wff = text_style.get("weightedFontFamily")
    if wff:
        font = wff.get("fontFamily")
        return font if isinstance(font, str) else None
    return None


def _get_font_size(text_style: dict[str, Any]) -> str | None:
    """Extract font size from text style."""
    fs = text_style.get("fontSize")
    if fs:
        mag = fs.get("magnitude")
        unit = fs.get("unit", "PT")
        if mag:
            return f"{mag}{unit.lower()}"
    return None


def _get_color(color_obj: dict[str, Any] | None) -> str | None:
    """Convert Google Docs color to hex string."""
    if not color_obj:
        return None

    color = color_obj.get("color", {}).get("rgbColor", {})
    if not color:
        return None

    r = int(color.get("red", 0) * 255)
    g = int(color.get("green", 0) * 255)
    b = int(color.get("blue", 0) * 255)

    # Skip black (default)
    if r == 0 and g == 0 and b == 0:
        return None

    return f"#{r:02X}{g:02X}{b:02X}"


def _get_line_spacing(para_style: dict[str, Any]) -> str | None:
    """Extract line spacing from paragraph style."""
    ls = para_style.get("lineSpacing")
    if ls:
        return str(ls)
    return None


def _get_direction(para_style: dict[str, Any]) -> str | None:
    """Extract text direction from paragraph style.

    Returns None for LEFT_TO_RIGHT (the default) to keep XML clean.
    """
    direction = para_style.get("direction")
    if direction and direction != "LEFT_TO_RIGHT":
        return str(direction)
    return None


def _get_dimension(dim_obj: dict[str, Any] | None) -> str | None:
    """Convert dimension object to string."""
    if not dim_obj:
        return None
    mag = dim_obj.get("magnitude")
    unit = dim_obj.get("unit", "PT")
    if mag and mag > 0:
        return f"{mag}{unit.lower()}"
    return None


def extract_text_style(text_style: dict[str, Any]) -> dict[str, str]:
    """Extract style properties from a Google Docs text style."""
    props: dict[str, str] = {}

    for prop_name, extractor in TEXT_STYLE_PROPS:
        value = extractor(text_style)
        if value:
            props[prop_name] = value

    return props


def extract_cell_style(cell_style: dict[str, Any]) -> dict[str, str]:
    """Extract style properties from a Google Docs table cell style."""
    props: dict[str, str] = {}

    for prop_name, extractor in TABLE_CELL_STYLE_PROPS:
        value = extractor(cell_style)
        if value:
            props[prop_name] = value

    return props


def collect_text_runs(document: dict[str, Any]) -> list[TextRun]:
    """Collect all text runs from a document with their styles.

    Args:
        document: Raw document JSON from Google Docs API

    Returns:
        List of TextRun objects
    """
    runs: list[TextRun] = []

    # Process tabs (modern API)
    tabs = document.get("tabs", [])
    if tabs:
        for tab in tabs:
            doc_tab = tab.get("documentTab", {})
            _collect_from_body(doc_tab.get("body", {}), runs)
            _collect_from_sections(doc_tab, runs)
    else:
        # Legacy single-tab document
        _collect_from_body(document.get("body", {}), runs)
        _collect_from_sections(document, runs)

    return runs


def _collect_from_body(body: dict[str, Any], runs: list[TextRun]) -> None:
    """Collect text runs from a body."""
    content = body.get("content", [])
    _collect_from_content(content, runs)


def _collect_from_sections(doc: dict[str, Any], runs: list[TextRun]) -> None:
    """Collect text runs from headers, footers, and footnotes."""
    for header in doc.get("headers", {}).values():
        _collect_from_content(header.get("content", []), runs)

    for footer in doc.get("footers", {}).values():
        _collect_from_content(footer.get("content", []), runs)

    for footnote in doc.get("footnotes", {}).values():
        _collect_from_content(footnote.get("content", []), runs)


def _collect_from_content(content: list[dict[str, Any]], runs: list[TextRun]) -> None:
    """Recursively collect text runs from structural elements."""
    for element in content:
        if "paragraph" in element:
            _collect_from_paragraph(element["paragraph"], runs)
        elif "table" in element:
            for row in element["table"].get("tableRows", []):
                for cell in row.get("tableCells", []):
                    _collect_from_content(cell.get("content", []), runs)
        elif "tableOfContents" in element:
            _collect_from_content(element["tableOfContents"].get("content", []), runs)


def _collect_from_paragraph(para: dict[str, Any], runs: list[TextRun]) -> None:
    """Collect text runs from a paragraph."""
    for elem in para.get("elements", []):
        if "textRun" in elem:
            text_run = elem["textRun"]
            text = text_run.get("content", "")
            text_style = text_run.get("textStyle", {})

            # Skip empty or newline-only runs
            stripped = text.rstrip("\n")
            if not stripped:
                continue

            styles = extract_text_style(text_style)
            char_count = len(stripped)

            runs.append(TextRun(text=stripped, char_count=char_count, styles=styles))


def extract_base_style_from_named_styles(document: dict[str, Any]) -> dict[str, str]:
    """Extract base style from the document's NORMAL_TEXT named style.

    This uses the document's defined NORMAL_TEXT style as the base,
    rather than computing from text run frequency. This ensures the
    base style reflects the document's intended defaults, not styles
    that happen to appear most often in content.

    Args:
        document: Raw document JSON from Google Docs API

    Returns:
        Base style properties from NORMAL_TEXT
    """
    # Find namedStyles - could be at top level or in documentTab
    named_styles = document.get("namedStyles")
    if not named_styles:
        tabs = document.get("tabs", [])
        if tabs:
            doc_tab = tabs[0].get("documentTab", {})
            named_styles = doc_tab.get("namedStyles")

    if not named_styles:
        # Fallback to empty base if no named styles found
        return {}

    # Find NORMAL_TEXT style
    for style in named_styles.get("styles", []):
        if style.get("namedStyleType") == "NORMAL_TEXT":
            text_style = style.get("textStyle", {})
            return extract_text_style(text_style)

    return {}


def compute_deviation(styles: dict[str, str], base: dict[str, str]) -> dict[str, str]:
    """Compute the deviation of a style from the base.

    Args:
        styles: The style properties
        base: The base style properties

    Returns:
        Properties that differ from base
    """
    deviation: dict[str, str] = {}

    # Properties in styles that differ from base
    for prop, value in styles.items():
        if prop not in base or base[prop] != value:
            deviation[prop] = value

    return deviation


def factorize_styles(document: dict[str, Any]) -> FactorizedStyles:
    """Factorize all styles in a document.

    Args:
        document: Raw document JSON from Google Docs API

    Returns:
        FactorizedStyles with base and deviation styles
    """
    # Collect all text runs
    runs = collect_text_runs(document)

    # Extract base style from NORMAL_TEXT named style
    # This uses the document's defined defaults, not computed from text frequency
    base_props = extract_base_style_from_named_styles(document)

    # Create base style definition
    base_style = StyleDefinition(id="_base", properties=base_props)

    # Group runs by deviation
    deviation_groups: dict[str, dict[str, str]] = {}
    style_map: dict[str, str] = {}

    for run in runs:
        deviation = compute_deviation(run.styles, base_props)
        key = _props_key(deviation)

        if not deviation:
            # Matches base style
            style_map[_props_key(run.styles)] = "_base"
        else:
            if key not in deviation_groups:
                deviation_groups[key] = deviation
            style_map[_props_key(run.styles)] = key

    # Create deviation style definitions
    deviation_styles: list[StyleDefinition] = []
    key_to_id: dict[str, str] = {}

    for key, props in deviation_groups.items():
        sid = style_id(props)
        deviation_styles.append(StyleDefinition(id=sid, properties=props))
        key_to_id[key] = sid

    # Update style_map to use actual IDs
    final_style_map: dict[str, str] = {}
    for orig_key, deviation_key in style_map.items():
        if deviation_key == "_base":
            final_style_map[orig_key] = "_base"
        else:
            final_style_map[orig_key] = key_to_id[deviation_key]

    # Collect and factorize cell styles
    cell_styles_list = collect_cell_styles(document)
    cell_styles, cell_style_map = _factorize_cell_styles(cell_styles_list)

    return FactorizedStyles(
        base_style=base_style,
        deviation_styles=deviation_styles,
        style_map=final_style_map,
        cell_styles=cell_styles,
        cell_style_map=cell_style_map,
    )


def collect_cell_styles(document: dict[str, Any]) -> list[dict[str, str]]:
    """Collect all table cell styles from a document.

    Args:
        document: Raw document JSON from Google Docs API

    Returns:
        List of cell style property dicts
    """
    styles: list[dict[str, str]] = []

    # Process tabs (modern API)
    tabs = document.get("tabs", [])
    if tabs:
        for tab in tabs:
            doc_tab = tab.get("documentTab", {})
            _collect_cell_styles_from_body(doc_tab.get("body", {}), styles)
    else:
        # Legacy single-tab document
        _collect_cell_styles_from_body(document.get("body", {}), styles)

    return styles


def _collect_cell_styles_from_body(
    body: dict[str, Any], styles: list[dict[str, str]]
) -> None:
    """Collect cell styles from a body."""
    content = body.get("content", [])
    _collect_cell_styles_from_content(content, styles)


def _collect_cell_styles_from_content(
    content: list[dict[str, Any]], styles: list[dict[str, str]]
) -> None:
    """Recursively collect cell styles from structural elements."""
    for element in content:
        if "table" in element:
            for row in element["table"].get("tableRows", []):
                for cell in row.get("tableCells", []):
                    cell_style = cell.get("tableCellStyle", {})
                    props = extract_cell_style(cell_style)
                    if props:
                        styles.append(props)
                    # Recurse into nested tables
                    _collect_cell_styles_from_content(cell.get("content", []), styles)


def _factorize_cell_styles(
    cell_styles: list[dict[str, str]],
) -> tuple[list[StyleDefinition], dict[str, str]]:
    """Factorize cell styles into unique style definitions.

    Unlike text styles, cell styles don't have a base style.
    Each unique set of cell properties gets its own style ID.

    Args:
        cell_styles: List of cell style property dicts

    Returns:
        Tuple of (list of StyleDefinitions, map from props key to style ID)
    """
    style_defs: list[StyleDefinition] = []
    style_map: dict[str, str] = {}
    seen_keys: dict[str, str] = {}

    for props in cell_styles:
        key = _props_key(props)
        if key in seen_keys:
            continue

        # Generate a unique cell style ID with "cell-" prefix
        sid = "cell-" + style_id(props)
        style_defs.append(StyleDefinition(id=sid, properties=props))
        seen_keys[key] = sid
        style_map[key] = sid

    return style_defs, style_map
