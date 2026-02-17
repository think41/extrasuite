"""Style models for styles.xml, plus factorize and resolve logic.

Factorize: extract styles from a Document, deduplicate, assign class names.
Resolve: look up class names to reconstruct Pydantic style objects.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any
from xml.etree.ElementTree import Element, SubElement, fromstring

from extradoc.api_types._generated import (
    NestingLevel,
    ParagraphStyle,
    ParagraphStyleNamedStyleType,
    TableCellStyle,
    TableColumnProperties,
    TableRowStyle,
    TextStyle,
)

from ._utils import (
    cell_border_to_str,
    dim_to_str,
    element_to_string,
    hex_to_optional_color,
    optional_color_to_hex,
    para_border_to_str,
    str_to_cell_border,
    str_to_para_border,
)

# ---------------------------------------------------------------------------
# Style definition models
# ---------------------------------------------------------------------------


@dataclass
class StyleDef:
    """A single style definition: a class name + attribute dict."""

    class_name: str
    attrs: dict[str, str] = field(default_factory=dict)


@dataclass
class StylesXml:
    """Root model for a per-tab styles.xml."""

    text_styles: list[StyleDef] = field(default_factory=list)
    para_styles: list[StyleDef] = field(default_factory=list)
    list_level_styles: list[StyleDef] = field(default_factory=list)
    col_styles: list[StyleDef] = field(default_factory=list)
    row_styles: list[StyleDef] = field(default_factory=list)
    cell_styles: list[StyleDef] = field(default_factory=list)

    def to_element(self) -> Element:
        root = Element("styles")
        for sd in self.text_styles:
            _style_def_to_element(sd, "text", root)
        for sd in self.para_styles:
            _style_def_to_element(sd, "para", root)
        for sd in self.list_level_styles:
            _style_def_to_element(sd, "listlevel", root)
        for sd in self.col_styles:
            _style_def_to_element(sd, "col", root)
        for sd in self.row_styles:
            _style_def_to_element(sd, "row", root)
        for sd in self.cell_styles:
            _style_def_to_element(sd, "cell", root)
        return root

    def to_xml_string(self) -> str:
        return element_to_string(self.to_element())

    @classmethod
    def from_element(cls, root: Element) -> StylesXml:
        styles = cls()
        for child in root:
            tag = child.tag
            attrs = dict(child.attrib)
            class_name = attrs.pop("class", "")
            sd = StyleDef(class_name=class_name, attrs=attrs)
            if tag == "text":
                styles.text_styles.append(sd)
            elif tag == "para":
                styles.para_styles.append(sd)
            elif tag == "listlevel":
                styles.list_level_styles.append(sd)
            elif tag == "col":
                styles.col_styles.append(sd)
            elif tag == "row":
                styles.row_styles.append(sd)
            elif tag == "cell":
                styles.cell_styles.append(sd)
        return styles

    @classmethod
    def from_xml_string(cls, xml: str) -> StylesXml:
        return cls.from_element(fromstring(xml))

    def lookup(self, tag: str, class_name: str) -> dict[str, str]:
        """Look up a style by tag type and class name."""
        style_list = {
            "text": self.text_styles,
            "para": self.para_styles,
            "listlevel": self.list_level_styles,
            "col": self.col_styles,
            "row": self.row_styles,
            "cell": self.cell_styles,
        }.get(tag, [])
        for sd in style_list:
            if sd.class_name == class_name:
                return sd.attrs
        return {}


def _style_def_to_element(sd: StyleDef, tag: str, parent: Element) -> None:
    elem = SubElement(parent, tag)
    elem.set("class", sd.class_name)
    for k, v in sorted(sd.attrs.items()):
        elem.set(k, v)


# ---------------------------------------------------------------------------
# Extract: Pydantic style model → XML attribute dict
# ---------------------------------------------------------------------------


def extract_text_style(ts: TextStyle | None) -> dict[str, str]:
    """Extract XML style attributes from a TextStyle."""
    if not ts:
        return {}
    attrs: dict[str, str] = {}
    if ts.bold:
        attrs["bold"] = "true"
    if ts.italic:
        attrs["italic"] = "true"
    if ts.underline:
        attrs["underline"] = "true"
    if ts.strikethrough:
        attrs["strikethrough"] = "true"
    if ts.small_caps:
        attrs["smallCaps"] = "true"
    if ts.baseline_offset and ts.baseline_offset.value == "SUPERSCRIPT":
        attrs["superscript"] = "true"
    elif ts.baseline_offset and ts.baseline_offset.value == "SUBSCRIPT":
        attrs["subscript"] = "true"
    if ts.weighted_font_family:
        if ts.weighted_font_family.font_family:
            attrs["font"] = ts.weighted_font_family.font_family
        if ts.weighted_font_family.weight is not None:
            attrs["fontWeight"] = str(ts.weighted_font_family.weight)
    s = dim_to_str(ts.font_size)
    if s:
        attrs["size"] = s
    c = optional_color_to_hex(ts.foreground_color)
    if c:
        attrs["color"] = c
    bg = optional_color_to_hex(ts.background_color)
    if bg:
        attrs["bgColor"] = bg
    if ts.link:
        if ts.link.url:
            attrs["link"] = ts.link.url
        elif ts.link.bookmark_id:
            attrs["linkBookmark"] = ts.link.bookmark_id
        elif ts.link.heading_id:
            attrs["linkHeading"] = ts.link.heading_id
        # tab_id can appear alongside bookmarkId/headingId or standalone
        if ts.link.tab_id:
            attrs["linkTab"] = ts.link.tab_id
    return attrs


def extract_para_style(ps: ParagraphStyle | None) -> dict[str, str]:
    """Extract XML style attributes from a ParagraphStyle.

    Note: namedStyleType is NOT included — it's represented by the element tag.
    headingId is also excluded — it's on the element directly.
    """
    if not ps:
        return {}
    attrs: dict[str, str] = {}
    if ps.alignment:
        attrs["align"] = ps.alignment.value
    if ps.direction:
        attrs["direction"] = ps.direction.value
    if ps.line_spacing is not None:
        attrs["lineSpacing"] = str(ps.line_spacing)
    if ps.spacing_mode:
        attrs["spacingMode"] = ps.spacing_mode.value
    s = dim_to_str(ps.space_above)
    if s:
        attrs["spaceAbove"] = s
    s = dim_to_str(ps.space_below)
    if s:
        attrs["spaceBelow"] = s
    s = dim_to_str(ps.indent_start)
    if s:
        attrs["indentLeft"] = s
    s = dim_to_str(ps.indent_end)
    if s:
        attrs["indentRight"] = s
    s = dim_to_str(ps.indent_first_line)
    if s:
        attrs["indentFirst"] = s
    if ps.keep_lines_together:
        attrs["keepTogether"] = "true"
    if ps.keep_with_next:
        attrs["keepNext"] = "true"
    if ps.avoid_widow_and_orphan:
        attrs["avoidWidow"] = "true"
    if ps.page_break_before:
        attrs["pageBreakBefore"] = "true"
    if ps.shading:
        bg = optional_color_to_hex(ps.shading.background_color)
        if bg:
            attrs["bgColor"] = bg
    for name, border in [
        ("borderTop", ps.border_top),
        ("borderBottom", ps.border_bottom),
        ("borderLeft", ps.border_left),
        ("borderRight", ps.border_right),
        ("borderBetween", ps.border_between),
    ]:
        b = para_border_to_str(border)
        if b:
            attrs[name] = b
    if ps.tab_stops:
        tab_stops_list = []
        for ts in ps.tab_stops:
            ts_d: dict[str, Any] = {}
            if ts.alignment:
                ts_d["alignment"] = ts.alignment.value
            if ts.offset:
                ts_d["offset"] = ts.offset.model_dump(by_alias=True, exclude_none=True)
            tab_stops_list.append(ts_d)
        if tab_stops_list:
            attrs["tabStops"] = json.dumps(tab_stops_list, separators=(",", ":"))
    return attrs


def extract_nesting_level(nl: NestingLevel | None) -> dict[str, str]:
    """Extract XML style attributes from a NestingLevel (for listlevel styles)."""
    if not nl:
        return {}
    attrs: dict[str, str] = {}
    s = dim_to_str(nl.indent_first_line)
    if s:
        attrs["indentFirst"] = s
    s = dim_to_str(nl.indent_start)
    if s:
        attrs["indentLeft"] = s
    if nl.text_style:
        ts = nl.text_style
        if ts.bold:
            attrs["bold"] = "true"
        if ts.italic:
            attrs["italic"] = "true"
        s = dim_to_str(ts.font_size)
        if s:
            attrs["size"] = s
        c = optional_color_to_hex(ts.foreground_color)
        if c:
            attrs["color"] = c
        if ts.weighted_font_family and ts.weighted_font_family.font_family:
            attrs["font"] = ts.weighted_font_family.font_family
    return attrs


def extract_col_style(tcp: TableColumnProperties | None) -> dict[str, str]:
    """Extract XML style attributes from TableColumnProperties."""
    if not tcp:
        return {}
    attrs: dict[str, str] = {}
    s = dim_to_str(tcp.width)
    if s:
        attrs["width"] = s
    if tcp.width_type:
        attrs["widthType"] = tcp.width_type.value
    return attrs


def extract_row_style(trs: TableRowStyle | None) -> dict[str, str]:
    """Extract XML style attributes from TableRowStyle."""
    if not trs:
        return {}
    attrs: dict[str, str] = {}
    s = dim_to_str(trs.min_row_height)
    if s:
        attrs["minHeight"] = s
    if trs.prevent_overflow:
        attrs["preventOverflow"] = "true"
    if trs.table_header:
        attrs["tableHeader"] = "true"
    return attrs


def extract_cell_style(tcs: TableCellStyle | None) -> dict[str, str]:
    """Extract XML style attributes from TableCellStyle."""
    if not tcs:
        return {}
    attrs: dict[str, str] = {}
    bg = optional_color_to_hex(tcs.background_color)
    if bg:
        attrs["bgColor"] = bg
    if tcs.content_alignment:
        attrs["valign"] = tcs.content_alignment.value
    for name, dim in [
        ("paddingTop", tcs.padding_top),
        ("paddingBottom", tcs.padding_bottom),
        ("paddingLeft", tcs.padding_left),
        ("paddingRight", tcs.padding_right),
    ]:
        s = dim_to_str(dim)
        if s:
            attrs[name] = s
    for name, border in [
        ("borderTop", tcs.border_top),
        ("borderBottom", tcs.border_bottom),
        ("borderLeft", tcs.border_left),
        ("borderRight", tcs.border_right),
    ]:
        b = cell_border_to_str(border)
        if b:
            attrs[name] = b
    return attrs


# ---------------------------------------------------------------------------
# Resolve: XML attribute dict → Pydantic style model (using model_validate)
# ---------------------------------------------------------------------------


def resolve_text_style(attrs: dict[str, str]) -> TextStyle:
    """Build a TextStyle from XML style attributes."""
    d: dict[str, Any] = {}
    if attrs.get("bold") == "true":
        d["bold"] = True
    if attrs.get("italic") == "true":
        d["italic"] = True
    if attrs.get("underline") == "true":
        d["underline"] = True
    if attrs.get("strikethrough") == "true":
        d["strikethrough"] = True
    if attrs.get("smallCaps") == "true":
        d["smallCaps"] = True
    if attrs.get("superscript") == "true":
        d["baselineOffset"] = "SUPERSCRIPT"
    elif attrs.get("subscript") == "true":
        d["baselineOffset"] = "SUBSCRIPT"
    font = attrs.get("font")
    font_weight = attrs.get("fontWeight")
    if font or font_weight:
        wff: dict[str, Any] = {}
        if font:
            wff["fontFamily"] = font
        if font_weight:
            wff["weight"] = int(font_weight)
        d["weightedFontFamily"] = wff
    size = attrs.get("size")
    if size:
        num = size.rstrip("pt")
        d["fontSize"] = {"magnitude": float(num), "unit": "PT"}
    c = attrs.get("color")
    if c:
        oc = hex_to_optional_color(c)
        d["foregroundColor"] = oc.model_dump(by_alias=True, exclude_none=True)
    bg = attrs.get("bgColor")
    if bg:
        oc = hex_to_optional_color(bg)
        d["backgroundColor"] = oc.model_dump(by_alias=True, exclude_none=True)
    link_url = attrs.get("link")
    link_bm = attrs.get("linkBookmark")
    link_hd = attrs.get("linkHeading")
    link_tab = attrs.get("linkTab")
    if link_url:
        d["link"] = {"url": link_url}
    elif link_bm:
        link_d: dict[str, str] = {"bookmarkId": link_bm}
        if link_tab:
            link_d["tabId"] = link_tab
        d["link"] = link_d
    elif link_hd:
        link_d = {"headingId": link_hd}
        if link_tab:
            link_d["tabId"] = link_tab
        d["link"] = link_d
    elif link_tab:
        d["link"] = {"tabId": link_tab}
    return TextStyle.model_validate(d)


def resolve_para_style(
    attrs: dict[str, str], named_style_type: ParagraphStyleNamedStyleType | None = None
) -> ParagraphStyle:
    """Build a ParagraphStyle from XML style attributes."""
    d: dict[str, Any] = {}
    if named_style_type:
        d["namedStyleType"] = named_style_type.value
    if "align" in attrs:
        d["alignment"] = attrs["align"]
    if "direction" in attrs:
        d["direction"] = attrs["direction"]
    if "lineSpacing" in attrs:
        d["lineSpacing"] = float(attrs["lineSpacing"])
    if "spacingMode" in attrs:
        d["spacingMode"] = attrs["spacingMode"]
    for xml_key, api_key in [
        ("spaceAbove", "spaceAbove"),
        ("spaceBelow", "spaceBelow"),
        ("indentLeft", "indentStart"),
        ("indentRight", "indentEnd"),
        ("indentFirst", "indentFirstLine"),
    ]:
        if xml_key in attrs:
            num = attrs[xml_key].rstrip("pt")
            d[api_key] = {"magnitude": float(num), "unit": "PT"}
    if attrs.get("keepTogether") == "true":
        d["keepLinesTogether"] = True
    if attrs.get("keepNext") == "true":
        d["keepWithNext"] = True
    if attrs.get("avoidWidow") == "true":
        d["avoidWidowAndOrphan"] = True
    if attrs.get("pageBreakBefore") == "true":
        d["pageBreakBefore"] = True
    bg = attrs.get("bgColor")
    if bg:
        oc = hex_to_optional_color(bg)
        d["shading"] = {
            "backgroundColor": oc.model_dump(by_alias=True, exclude_none=True)
        }
    for xml_key, api_key in [
        ("borderTop", "borderTop"),
        ("borderBottom", "borderBottom"),
        ("borderLeft", "borderLeft"),
        ("borderRight", "borderRight"),
        ("borderBetween", "borderBetween"),
    ]:
        border = str_to_para_border(attrs.get(xml_key))
        if border:
            d[api_key] = border.model_dump(by_alias=True, exclude_none=True)
    tab_stops_json = attrs.get("tabStops")
    if tab_stops_json:
        d["tabStops"] = json.loads(tab_stops_json)
    return ParagraphStyle.model_validate(d)


def resolve_nesting_level(
    attrs: dict[str, str],
    glyph_type: str | None = None,
    glyph_format: str | None = None,
    glyph_symbol: str | None = None,
    bullet_alignment: str | None = None,
    start_number: int | None = None,
) -> NestingLevel:
    """Build a NestingLevel from XML style attrs and list-level attrs."""
    d: dict[str, Any] = {}
    if glyph_type:
        d["glyphType"] = glyph_type
    if glyph_format:
        d["glyphFormat"] = glyph_format
    if glyph_symbol:
        d["glyphSymbol"] = glyph_symbol
    if bullet_alignment:
        d["bulletAlignment"] = bullet_alignment
    if start_number is not None:
        d["startNumber"] = start_number
    for xml_key, api_key in [
        ("indentFirst", "indentFirstLine"),
        ("indentLeft", "indentStart"),
    ]:
        if xml_key in attrs:
            num = attrs[xml_key].rstrip("pt")
            d[api_key] = {"magnitude": float(num), "unit": "PT"}
    # Bullet text style
    ts_attrs: dict[str, str] = {}
    for key in ("bold", "italic", "size", "color", "font"):
        if key in attrs:
            ts_attrs[key] = attrs[key]
    if ts_attrs:
        d["textStyle"] = resolve_text_style(ts_attrs).model_dump(
            by_alias=True, exclude_none=True
        )
    return NestingLevel.model_validate(d)


def resolve_col_style(attrs: dict[str, str]) -> TableColumnProperties:
    """Build TableColumnProperties from XML style attributes."""
    d: dict[str, Any] = {}
    if "width" in attrs:
        num = attrs["width"].rstrip("pt")
        d["width"] = {"magnitude": float(num), "unit": "PT"}
    if "widthType" in attrs:
        d["widthType"] = attrs["widthType"]
    return TableColumnProperties.model_validate(d)


def resolve_row_style(attrs: dict[str, str]) -> TableRowStyle:
    """Build TableRowStyle from XML style attributes."""
    d: dict[str, Any] = {}
    if "minHeight" in attrs:
        num = attrs["minHeight"].rstrip("pt")
        d["minRowHeight"] = {"magnitude": float(num), "unit": "PT"}
    if attrs.get("preventOverflow") == "true":
        d["preventOverflow"] = True
    if attrs.get("tableHeader") == "true":
        d["tableHeader"] = True
    return TableRowStyle.model_validate(d)


def resolve_cell_style(attrs: dict[str, str]) -> TableCellStyle:
    """Build TableCellStyle from XML style attributes."""
    d: dict[str, Any] = {}
    bg = attrs.get("bgColor")
    if bg:
        oc = hex_to_optional_color(bg)
        d["backgroundColor"] = oc.model_dump(by_alias=True, exclude_none=True)
    if "valign" in attrs:
        d["contentAlignment"] = attrs["valign"]
    for xml_key, api_key in [
        ("paddingTop", "paddingTop"),
        ("paddingBottom", "paddingBottom"),
        ("paddingLeft", "paddingLeft"),
        ("paddingRight", "paddingRight"),
    ]:
        if xml_key in attrs:
            num = attrs[xml_key].rstrip("pt")
            d[api_key] = {"magnitude": float(num), "unit": "PT"}
    for xml_key, api_key in [
        ("borderTop", "borderTop"),
        ("borderBottom", "borderBottom"),
        ("borderLeft", "borderLeft"),
        ("borderRight", "borderRight"),
    ]:
        border = str_to_cell_border(attrs.get(xml_key))
        if border:
            d[api_key] = border.model_dump(by_alias=True, exclude_none=True)
    return TableCellStyle.model_validate(d)


# ---------------------------------------------------------------------------
# Sugar tag helpers
# ---------------------------------------------------------------------------


def determine_sugar_tag(attrs: dict[str, str]) -> tuple[str | None, dict[str, str]]:
    """Determine the best sugar tag for a set of text style attributes.

    Returns (tag, remaining_attrs) where tag is None if no sugar applies.
    """
    if (
        "link" in attrs
        or "linkBookmark" in attrs
        or "linkHeading" in attrs
        or "linkTab" in attrs
    ):
        return None, attrs

    for attr_name, tag in [
        ("bold", "b"),
        ("italic", "i"),
        ("underline", "u"),
        ("strikethrough", "s"),
        ("superscript", "sup"),
        ("subscript", "sub"),
    ]:
        if attrs.get(attr_name) == "true":
            remaining = {k: v for k, v in attrs.items() if k != attr_name}
            return tag, remaining

    return None, attrs


def determine_link_href(
    attrs: dict[str, str],
) -> tuple[str | None, dict[str, str], str | None]:
    """Extract link href and return remaining attrs and link type key.

    Returns (href, remaining_attrs, link_type_key).
    The link_type_key is the attribute key used (e.g., "link", "linkBookmark").
    When linkTab coexists with bookmarkId/headingId, linkTab is kept in remaining.
    """
    # Check primary link types first
    for key in ("link", "linkBookmark", "linkHeading"):
        if key in attrs:
            href = attrs[key]
            # Keep linkTab in remaining when it's a cross-tab link modifier
            remaining = {k: v for k, v in attrs.items() if k != key}
            return href, remaining, key
    # linkTab as standalone link
    if "linkTab" in attrs:
        href = attrs["linkTab"]
        remaining = {k: v for k, v in attrs.items() if k != "linkTab"}
        return href, remaining, "linkTab"
    return None, attrs, None


# ---------------------------------------------------------------------------
# Style collector / factorizer
# ---------------------------------------------------------------------------


class StyleCollector:
    """Collects and deduplicates styles during Document→XML conversion."""

    def __init__(self) -> None:
        self._text: dict[str, str] = {}
        self._para: dict[str, str] = {}
        self._listlevel: dict[str, str] = {}
        self._col: dict[str, str] = {}
        self._row: dict[str, str] = {}
        self._cell: dict[str, str] = {}
        self._text_defs: list[StyleDef] = []
        self._para_defs: list[StyleDef] = []
        self._listlevel_defs: list[StyleDef] = []
        self._col_defs: list[StyleDef] = []
        self._row_defs: list[StyleDef] = []
        self._cell_defs: list[StyleDef] = []
        # Usage counts for default promotion (not tracked for text)
        self._para_counts: dict[str, int] = {}
        self._listlevel_counts: dict[str, int] = {}
        self._col_counts: dict[str, int] = {}
        self._row_counts: dict[str, int] = {}
        self._cell_counts: dict[str, int] = {}

    def _freeze(self, attrs: dict[str, str]) -> str:
        return "|".join(f"{k}={v}" for k, v in sorted(attrs.items()))

    def add_text_style(self, attrs: dict[str, str]) -> str | None:
        """Register a text style. Returns class name, or None if empty."""
        if not attrs:
            return None
        key = self._freeze(attrs)
        if key not in self._text:
            name = f"s{len(self._text) + 1}"
            self._text[key] = name
            self._text_defs.append(StyleDef(class_name=name, attrs=dict(attrs)))
        return self._text[key]

    def add_para_style(self, attrs: dict[str, str]) -> str | None:
        if not attrs:
            return None
        key = self._freeze(attrs)
        if key not in self._para:
            name = f"p{len(self._para) + 1}"
            self._para[key] = name
            self._para_defs.append(StyleDef(class_name=name, attrs=dict(attrs)))
        name = self._para[key]
        self._para_counts[name] = self._para_counts.get(name, 0) + 1
        return name

    def add_listlevel_style(self, attrs: dict[str, str]) -> str | None:
        if not attrs:
            return None
        key = self._freeze(attrs)
        if key not in self._listlevel:
            name = f"ls{len(self._listlevel) + 1}"
            self._listlevel[key] = name
            self._listlevel_defs.append(StyleDef(class_name=name, attrs=dict(attrs)))
        name = self._listlevel[key]
        self._listlevel_counts[name] = self._listlevel_counts.get(name, 0) + 1
        return name

    def add_col_style(self, attrs: dict[str, str]) -> str | None:
        if not attrs:
            return None
        key = self._freeze(attrs)
        if key not in self._col:
            name = f"tc{len(self._col) + 1}"
            self._col[key] = name
            self._col_defs.append(StyleDef(class_name=name, attrs=dict(attrs)))
        name = self._col[key]
        self._col_counts[name] = self._col_counts.get(name, 0) + 1
        return name

    def add_row_style(self, attrs: dict[str, str]) -> str | None:
        if not attrs:
            return None
        key = self._freeze(attrs)
        if key not in self._row:
            name = f"tr{len(self._row) + 1}"
            self._row[key] = name
            self._row_defs.append(StyleDef(class_name=name, attrs=dict(attrs)))
        name = self._row[key]
        self._row_counts[name] = self._row_counts.get(name, 0) + 1
        return name

    def add_cell_style(self, attrs: dict[str, str]) -> str | None:
        if not attrs:
            return None
        key = self._freeze(attrs)
        if key not in self._cell:
            name = f"c{len(self._cell) + 1}"
            self._cell[key] = name
            self._cell_defs.append(StyleDef(class_name=name, attrs=dict(attrs)))
        name = self._cell[key]
        self._cell_counts[name] = self._cell_counts.get(name, 0) + 1
        return name

    def promote_defaults(self) -> dict[str, str]:
        """Rename the most-frequent style per category to ``_default``.

        Returns a mapping ``{category: old_class_name}`` for categories where
        a default was promoted.  Text styles are excluded — unstyled ``<t>``
        elements must remain distinguishable from styled ones.
        """
        defaults: dict[str, str] = {}
        for category, counts, defs in [
            ("para", self._para_counts, self._para_defs),
            ("listlevel", self._listlevel_counts, self._listlevel_defs),
            ("col", self._col_counts, self._col_defs),
            ("row", self._row_counts, self._row_defs),
            ("cell", self._cell_counts, self._cell_defs),
        ]:
            if not counts:
                continue
            most_used = max(counts, key=lambda k: counts[k])
            if counts[most_used] < 2:
                continue
            for sd in defs:
                if sd.class_name == most_used:
                    defaults[category] = most_used
                    sd.class_name = "_default"
                    break
        return defaults

    def build(self) -> StylesXml:
        """Build the final StylesXml from collected styles."""
        return StylesXml(
            text_styles=list(self._text_defs),
            para_styles=list(self._para_defs),
            list_level_styles=list(self._listlevel_defs),
            col_styles=list(self._col_defs),
            row_styles=list(self._row_defs),
            cell_styles=list(self._cell_defs),
        )
