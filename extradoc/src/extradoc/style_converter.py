"""Declarative style conversion for ExtraDoc.

Provides declarative mappings between XML style attributes and Google Docs API
style objects. This module centralizes style conversion logic to reduce code
duplication and make style handling more maintainable.

Usage:
    from extradoc.style_converter import convert_styles, TEXT_STYLE_PROPS

    # Convert XML attributes to API style object
    text_style, fields = convert_styles(
        {"bold": "1", "bg": "#FFFF00", "size": "14"},
        TEXT_STYLE_PROPS
    )
    # Returns: ({"bold": True, "backgroundColor": {...}, "fontSize": {...}}, ["bold", "backgroundColor", "fontSize"])
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class StyleType(Enum):
    """Types of style conversions supported."""

    BOOL = "bool"  # "1" -> True
    PT = "pt"  # "12" -> {"magnitude": 12, "unit": "PT"}
    FLOAT = "float"  # "1.5" -> 1.5
    COLOR = "color"  # "#FF0000" -> {"color": {"rgbColor": {...}}}
    ENUM = "enum"  # "CENTER" -> "CENTER"
    ENUM_MAP = "enum_map"  # "RTL" -> "RIGHT_TO_LEFT"
    FONT = "font"  # "Arial" -> {"fontFamily": "Arial"}
    LINK = "link"  # URL/bookmark/heading
    BORDER = "border"  # "1,#000,SOLID,2" -> border object


@dataclass
class StyleProp:
    """Definition of a style property mapping.

    Attributes:
        xml_attr: Attribute name in XML (e.g., "bold", "bg", "align")
        api_field: Field path in API request using dot notation for nested fields
                   (e.g., "bold", "link.url", "shading.backgroundColor")
        style_type: The type of conversion to apply
        enum_value: For ENUM type, the constant value to use
        enum_map: For ENUM_MAP type, the mapping dict from XML values to API values
    """

    xml_attr: str
    api_field: str
    style_type: StyleType
    enum_value: str = ""
    enum_map: dict[str, str] = field(default_factory=dict)


# Text style property mappings
TEXT_STYLE_PROPS: list[StyleProp] = [
    # Boolean styles
    StyleProp("bold", "bold", StyleType.BOOL),
    StyleProp("italic", "italic", StyleType.BOOL),
    StyleProp("underline", "underline", StyleType.BOOL),
    StyleProp("strikethrough", "strikethrough", StyleType.BOOL),
    StyleProp("smallcaps", "smallCaps", StyleType.BOOL),
    # Baseline offset (mutually exclusive)
    StyleProp(
        "superscript", "baselineOffset", StyleType.ENUM, enum_value="SUPERSCRIPT"
    ),
    StyleProp("subscript", "baselineOffset", StyleType.ENUM, enum_value="SUBSCRIPT"),
    # Font
    StyleProp("font", "weightedFontFamily", StyleType.FONT),
    StyleProp("size", "fontSize", StyleType.PT),
    # Colors
    StyleProp("color", "foregroundColor", StyleType.COLOR),
    StyleProp("bg", "backgroundColor", StyleType.COLOR),
    # Links - handled specially since link structure varies
    StyleProp("link", "link.url", StyleType.LINK),
    StyleProp("link-bookmark", "link.bookmarkId", StyleType.LINK),
    StyleProp("link-heading", "link.headingId", StyleType.LINK),
]


# Paragraph style property mappings
PARAGRAPH_STYLE_PROPS: list[StyleProp] = [
    # Alignment
    StyleProp("align", "alignment", StyleType.ENUM),
    # Named style
    StyleProp("namedStyle", "namedStyleType", StyleType.ENUM),
    # Spacing
    StyleProp("lineSpacing", "lineSpacing", StyleType.FLOAT),
    StyleProp("spaceAbove", "spaceAbove", StyleType.PT),
    StyleProp("spaceBelow", "spaceBelow", StyleType.PT),
    # Indentation
    StyleProp("indentLeft", "indentStart", StyleType.PT),
    StyleProp("indentRight", "indentEnd", StyleType.PT),
    StyleProp("indentFirst", "indentFirstLine", StyleType.PT),
    # Boolean properties
    StyleProp("keepTogether", "keepLinesTogether", StyleType.BOOL),
    StyleProp("keepNext", "keepWithNext", StyleType.BOOL),
    StyleProp("avoidWidow", "avoidWidowAndOrphan", StyleType.BOOL),
    # Direction
    StyleProp(
        "direction",
        "direction",
        StyleType.ENUM_MAP,
        enum_map={"RTL": "RIGHT_TO_LEFT", "LTR": "LEFT_TO_RIGHT"},
    ),
    # Shading
    StyleProp("bgColor", "shading.backgroundColor", StyleType.COLOR),
    # Borders
    StyleProp("borderTop", "borderTop", StyleType.BORDER),
    StyleProp("borderBottom", "borderBottom", StyleType.BORDER),
    StyleProp("borderLeft", "borderLeft", StyleType.BORDER),
    StyleProp("borderRight", "borderRight", StyleType.BORDER),
]


# Table cell style property mappings
TABLE_CELL_STYLE_PROPS: list[StyleProp] = [
    StyleProp("bg", "backgroundColor", StyleType.COLOR),
    StyleProp(
        "valign",
        "contentAlignment",
        StyleType.ENUM_MAP,
        enum_map={"top": "TOP", "middle": "MIDDLE", "bottom": "BOTTOM"},
    ),
    StyleProp("paddingTop", "paddingTop", StyleType.PT),
    StyleProp("paddingBottom", "paddingBottom", StyleType.PT),
    StyleProp("paddingLeft", "paddingLeft", StyleType.PT),
    StyleProp("paddingRight", "paddingRight", StyleType.PT),
    # Borders
    StyleProp("borderTop", "borderTop", StyleType.BORDER),
    StyleProp("borderBottom", "borderBottom", StyleType.BORDER),
    StyleProp("borderLeft", "borderLeft", StyleType.BORDER),
    StyleProp("borderRight", "borderRight", StyleType.BORDER),
]


# Element tag -> namedStyleType mapping
NAMED_STYLE_MAP: dict[str, str] = {
    "h1": "HEADING_1",
    "h2": "HEADING_2",
    "h3": "HEADING_3",
    "h4": "HEADING_4",
    "h5": "HEADING_5",
    "h6": "HEADING_6",
    "title": "TITLE",
    "subtitle": "SUBTITLE",
    "p": "NORMAL_TEXT",
}


def convert_styles(
    styles: dict[str, str],
    prop_defs: list[StyleProp],
) -> tuple[dict[str, Any], list[str]]:
    """Convert XML styles to API request using declarative mappings.

    Args:
        styles: Dict of XML attribute name -> value
        prop_defs: List of StyleProp definitions to apply

    Returns:
        Tuple of (style_dict, fields_list) where:
        - style_dict is the API style object ready for use in requests
        - fields_list is the list of top-level field names for the fields mask

    Example:
        >>> text_style, fields = convert_styles(
        ...     {"bold": "1", "bg": "#FFFF00"},
        ...     TEXT_STYLE_PROPS
        ... )
        >>> text_style
        {"bold": True, "backgroundColor": {"color": {"rgbColor": {...}}}}
        >>> fields
        ["bold", "backgroundColor"]
    """
    result: dict[str, Any] = {}
    fields: list[str] = []

    for prop in prop_defs:
        if prop.xml_attr not in styles:
            continue

        value = styles[prop.xml_attr]
        converted = _convert_value(value, prop)

        if converted is not None:
            _set_nested(result, prop.api_field, converted)
            # Use the top-level field for the fields mask
            top_level_field = prop.api_field.split(".")[0]
            if top_level_field not in fields:
                fields.append(top_level_field)

    return result, fields


def _convert_value(value: str, prop: StyleProp) -> Any:
    """Convert a single value based on its StyleType.

    Args:
        value: The string value from XML
        prop: The StyleProp defining the conversion

    Returns:
        The converted value, or None if conversion fails
    """
    match prop.style_type:
        case StyleType.BOOL:
            return value == "1"

        case StyleType.PT:
            try:
                # Handle values like "12pt" or just "12"
                num_str = value.rstrip("pt")
                return {"magnitude": float(num_str), "unit": "PT"}
            except ValueError:
                return None

        case StyleType.FLOAT:
            try:
                return float(value)
            except ValueError:
                return None

        case StyleType.COLOR:
            rgb = _hex_to_rgb(value)
            return {"color": {"rgbColor": rgb}} if rgb else None

        case StyleType.ENUM:
            # If enum_value is specified, use it; otherwise use the value directly
            return prop.enum_value if prop.enum_value else value.upper()

        case StyleType.ENUM_MAP:
            # Map the value through enum_map, defaulting to uppercase if not found
            return prop.enum_map.get(value.upper(), value.upper())

        case StyleType.FONT:
            return {"fontFamily": value}

        case StyleType.LINK:
            # Return the value directly - the API field path handles the nesting
            return value

        case StyleType.BORDER:
            return _parse_border(value)

    return None


def _set_nested(d: dict[str, Any], path: str, value: Any) -> None:
    """Set a nested dict value using dot notation path.

    Args:
        d: The dict to modify
        path: Dot-separated path (e.g., "link.url", "shading.backgroundColor")
        value: The value to set

    Example:
        >>> d = {}
        >>> _set_nested(d, "link.url", "https://example.com")
        >>> d
        {"link": {"url": "https://example.com"}}
    """
    keys = path.split(".")
    for key in keys[:-1]:
        d = d.setdefault(key, {})
    d[keys[-1]] = value


def _hex_to_rgb(hex_color: str) -> dict[str, float] | None:
    """Convert #RRGGBB to {red, green, blue} with 0-1 values.

    Args:
        hex_color: Color string like "#FF0000" or "FF0000"

    Returns:
        Dict with red, green, blue keys (0.0-1.0 values), or None if invalid
    """
    if not hex_color:
        return None

    hex_color = hex_color.lstrip("#")
    if len(hex_color) != 6:
        return None

    try:
        return {
            "red": int(hex_color[0:2], 16) / 255.0,
            "green": int(hex_color[2:4], 16) / 255.0,
            "blue": int(hex_color[4:6], 16) / 255.0,
        }
    except ValueError:
        return None


def _parse_border(border_str: str) -> dict[str, Any] | None:
    """Parse border string to API border object.

    Format: "width,#color,dashStyle,padding"
    Example: "1,#000000,SOLID,2"

    Args:
        border_str: Border specification string

    Returns:
        Border dict for API, or None if invalid
    """
    parts = border_str.split(",")
    if len(parts) < 2:
        return None

    try:
        border: dict[str, Any] = {"width": {"magnitude": float(parts[0]), "unit": "PT"}}
    except ValueError:
        return None

    rgb = _hex_to_rgb(parts[1])
    if rgb:
        border["color"] = {"color": {"rgbColor": rgb}}

    if len(parts) > 2 and parts[2]:
        border["dashStyle"] = parts[2].upper()

    if len(parts) > 3 and parts[3]:
        with contextlib.suppress(ValueError):
            border["padding"] = {"magnitude": float(parts[3]), "unit": "PT"}

    return border


def build_text_style_request(
    styles: dict[str, str],
    start_index: int,
    end_index: int,
    segment_id: str | None = None,
) -> dict[str, Any] | None:
    """Build an updateTextStyle request from XML styles.

    Args:
        styles: Dict of XML style attributes
        start_index: Start index in document
        end_index: End index in document
        segment_id: Optional segment ID for headers/footers/footnotes

    Returns:
        An updateTextStyle request dict, or None if no styles to apply
    """
    text_style, fields = convert_styles(styles, TEXT_STYLE_PROPS)
    if not fields:
        return None

    range_spec: dict[str, Any] = {
        "startIndex": start_index,
        "endIndex": end_index,
    }
    if segment_id:
        range_spec["segmentId"] = segment_id

    return {
        "updateTextStyle": {
            "range": range_spec,
            "textStyle": text_style,
            "fields": ",".join(fields),
        }
    }


def build_paragraph_style_request(
    styles: dict[str, str],
    start_index: int,
    end_index: int,
    segment_id: str | None = None,
) -> dict[str, Any] | None:
    """Build an updateParagraphStyle request from XML styles.

    Args:
        styles: Dict of XML style attributes
        start_index: Start index in document
        end_index: End index in document
        segment_id: Optional segment ID for headers/footers/footnotes

    Returns:
        An updateParagraphStyle request dict, or None if no styles to apply
    """
    para_style, fields = convert_styles(styles, PARAGRAPH_STYLE_PROPS)
    if not fields:
        return None

    range_spec: dict[str, Any] = {
        "startIndex": start_index,
        "endIndex": end_index,
    }
    if segment_id:
        range_spec["segmentId"] = segment_id

    return {
        "updateParagraphStyle": {
            "range": range_spec,
            "paragraphStyle": para_style,
            "fields": ",".join(fields),
        }
    }


def build_table_cell_style_request(
    styles: dict[str, str],
    table_start_index: int,
    row_index: int,
    col_index: int,
    segment_id: str | None = None,
) -> dict[str, Any] | None:
    """Build an updateTableCellStyle request from XML styles.

    Args:
        styles: Dict of XML style attributes
        table_start_index: Start index of the table in the document
        row_index: Row index in the table
        col_index: Column index in the table
        segment_id: Optional segment ID for headers/footers/footnotes

    Returns:
        An updateTableCellStyle request dict, or None if no styles to apply
    """
    cell_style, fields = convert_styles(styles, TABLE_CELL_STYLE_PROPS)
    if not fields:
        return None

    table_start_loc: dict[str, Any] = {"index": table_start_index}
    if segment_id:
        table_start_loc["segmentId"] = segment_id

    return {
        "updateTableCellStyle": {
            "tableRange": {
                "tableCellLocation": {
                    "tableStartLocation": table_start_loc,
                    "rowIndex": row_index,
                    "columnIndex": col_index,
                },
                "rowSpan": 1,
                "columnSpan": 1,
            },
            "tableCellStyle": cell_style,
            "fields": ",".join(fields),
        }
    }
