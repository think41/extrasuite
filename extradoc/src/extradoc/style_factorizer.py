"""Style factorization for Google Docs.

Extracts styles from a Google Docs document, computes the base style,
and generates minimal style definitions (deviations from base).
"""

from __future__ import annotations

from collections import Counter
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

    # Map from original style properties to style ID
    style_map: dict[str, str] = field(default_factory=dict)

    def get_style_id(self, properties: dict[str, str]) -> str:
        """Get the style ID for a set of properties.

        Returns "_base" if properties match the base style.
        """
        key = _props_key(properties)
        return self.style_map.get(key, "_base")

    def to_xml(self) -> str:
        """Generate styles.xml content."""
        root = Element("styles")

        # Add base style first
        root.append(self.base_style.to_xml())

        # Add deviation styles
        for style in self.deviation_styles:
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
]


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


def extract_paragraph_style(para_style: dict[str, Any]) -> dict[str, str]:
    """Extract style properties from a Google Docs paragraph style."""
    props: dict[str, str] = {}

    for prop_name, extractor in PARAGRAPH_STYLE_PROPS:
        value = extractor(para_style)
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


def compute_base_style(runs: list[TextRun]) -> dict[str, str]:
    """Compute the base style from all text runs.

    For each property, the base value is the one that appears most frequently
    (weighted by character count).

    Args:
        runs: List of text runs

    Returns:
        Base style properties
    """
    # Property -> value -> total character count
    prop_counts: dict[str, Counter[str]] = {}

    for run in runs:
        for prop, value in run.styles.items():
            if prop not in prop_counts:
                prop_counts[prop] = Counter()
            prop_counts[prop][value] += run.char_count

    # Select most common value for each property
    base: dict[str, str] = {}
    for prop, counts in prop_counts.items():
        if counts:
            most_common = counts.most_common(1)[0][0]
            base[prop] = most_common

    return base


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

    # Compute base style
    base_props = compute_base_style(runs)

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

    return FactorizedStyles(
        base_style=base_style,
        deviation_styles=deviation_styles,
        style_map=final_style_map,
    )
