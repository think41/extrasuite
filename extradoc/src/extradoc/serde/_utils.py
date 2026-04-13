"""Utility functions for the serde module."""

from __future__ import annotations

import re
import urllib.parse
from typing import Any
from xml.etree.ElementTree import Element, indent, tostring

from extradoc.api_types._generated import (
    Dimension,
    OptionalColor,
    ParagraphBorder,
    TableCellBorder,
)


def sanitize_tab_name(name: str) -> str:
    """Sanitize a tab name for use as a folder name.

    Replaces special characters with underscores and collapses multiples.
    """
    sanitized = re.sub(r"[^\w\-]", "_", name)
    sanitized = re.sub(r"_+", "_", sanitized)
    sanitized = sanitized.strip("_")
    return sanitized or "untitled"


# ---------------------------------------------------------------------------
# Color conversions
# ---------------------------------------------------------------------------


def rgb_to_hex(r: float, g: float, b: float) -> str:
    """Convert RGB 0-1 floats to #RRGGBB hex string."""
    return f"#{round(r * 255):02X}{round(g * 255):02X}{round(b * 255):02X}"


def hex_to_rgb(hex_color: str) -> tuple[float, float, float]:
    """Convert #RRGGBB hex string to RGB 0-1 floats."""
    h = hex_color.lstrip("#")
    return (
        int(h[0:2], 16) / 255.0,
        int(h[2:4], 16) / 255.0,
        int(h[4:6], 16) / 255.0,
    )


def optional_color_to_hex(oc: OptionalColor | None) -> str | None:
    """Convert OptionalColor to hex string, or None if unset."""
    if not oc or not oc.color or not oc.color.rgb_color:
        return None
    rgb = oc.color.rgb_color
    r = rgb.red if rgb.red is not None else 0.0
    g = rgb.green if rgb.green is not None else 0.0
    b = rgb.blue if rgb.blue is not None else 0.0
    return rgb_to_hex(r, g, b)


def hex_to_optional_color(hex_color: str) -> OptionalColor:
    """Convert hex string to OptionalColor."""
    r, g, b = hex_to_rgb(hex_color)
    return OptionalColor.model_validate(
        {"color": {"rgbColor": {"red": r, "green": g, "blue": b}}}
    )


# ---------------------------------------------------------------------------
# Dimension conversions
# ---------------------------------------------------------------------------


def dim_to_str(dim: Dimension | None) -> str | None:
    """Convert Dimension to string like '12pt'."""
    if not dim or dim.magnitude is None:
        return None
    return f"{dim.magnitude}pt"


def str_to_dim(s: str | None) -> Dimension | None:
    """Convert string like '12pt' to Dimension."""
    if not s:
        return None
    num_str = s.rstrip("pt")
    return Dimension.model_validate({"magnitude": float(num_str), "unit": "PT"})


# ---------------------------------------------------------------------------
# Border conversions
# ---------------------------------------------------------------------------


def para_border_to_str(border: ParagraphBorder | None) -> str | None:
    """Convert ParagraphBorder to 'width,#color,dash,padding' string."""
    if not border or not border.width or border.width.magnitude is None:
        return None
    parts = [str(border.width.magnitude)]
    color_hex = optional_color_to_hex(border.color)
    parts.append(color_hex or "#000000")
    parts.append(border.dash_style.value if border.dash_style else "SOLID")
    if border.padding and border.padding.magnitude is not None:
        parts.append(str(border.padding.magnitude))
    return ",".join(parts)


def str_to_para_border(s: str | None) -> ParagraphBorder | None:
    """Convert 'width,#color,dash,padding' string to ParagraphBorder."""
    if not s:
        return None
    parts = s.split(",")
    if len(parts) < 2:
        return None
    d: dict[str, Any] = {
        "width": {"magnitude": float(parts[0]), "unit": "PT"},
        "color": _hex_to_color_dict(parts[1]),
    }
    if len(parts) > 2 and parts[2]:
        d["dashStyle"] = parts[2]
    if len(parts) > 3 and parts[3]:
        d["padding"] = {"magnitude": float(parts[3]), "unit": "PT"}
    return ParagraphBorder.model_validate(d)


def cell_border_to_str(border: TableCellBorder | None) -> str | None:
    """Convert TableCellBorder to 'width,#color,dash' string."""
    if not border or not border.width or border.width.magnitude is None:
        return None
    parts = [str(border.width.magnitude)]
    color_hex = optional_color_to_hex(border.color)
    parts.append(color_hex or "#000000")
    parts.append(border.dash_style.value if border.dash_style else "SOLID")
    return ",".join(parts)


def str_to_cell_border(s: str | None) -> TableCellBorder | None:
    """Convert 'width,#color,dash' string to TableCellBorder."""
    if not s:
        return None
    parts = s.split(",")
    if len(parts) < 2:
        return None
    d: dict[str, Any] = {
        "width": {"magnitude": float(parts[0]), "unit": "PT"},
        "color": _hex_to_color_dict(parts[1]),
    }
    if len(parts) > 2 and parts[2]:
        d["dashStyle"] = parts[2]
    return TableCellBorder.model_validate(d)


def _hex_to_color_dict(hex_color: str) -> dict[str, Any]:
    """Convert hex color to OptionalColor-compatible dict."""
    r, g, b = hex_to_rgb(hex_color)
    return {"color": {"rgbColor": {"red": r, "green": g, "blue": b}}}


# ---------------------------------------------------------------------------
# XML helpers
# ---------------------------------------------------------------------------


def element_to_string(elem: Element) -> str:
    """Convert Element to pretty-printed XML string with declaration."""
    indent(elem)
    xml_str = tostring(elem, encoding="unicode")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_str + "\n"


# ---------------------------------------------------------------------------
# Markdown text-run serialization
# (shared by _to_markdown.py and _special_elements.py to avoid circular import)
# ---------------------------------------------------------------------------

# Monospace font families treated as inline code
_MONOSPACE_FAMILIES = frozenset(
    {"Courier New", "Courier", "Source Code Pro", "Roboto Mono", "Consolas"}
)


def _escape_md(text: str) -> str:
    """Minimal markdown escaping to prevent unintended formatting."""
    return text.replace("\\", "\\\\").replace("`", "\\`")


def _normalize_url(url: str) -> str:
    """Strip spurious http:// prepended by the Docs API to relative URLs.

    The Docs API prepends http:// to scheme-less URLs (e.g. LICENSE → http://LICENSE).
    Detect these by checking whether the netloc contains no dot — real HTTP hosts
    always have a dot (example.com) or are localhost.
    """
    if not url.startswith("http://"):
        return url
    netloc = urllib.parse.urlparse(url).netloc
    if "." not in netloc and netloc.lower() not in {"localhost"}:
        return url[7:]  # strip "http://"
    return url


def _style_has_attrs(style: Any) -> bool:
    return bool(
        style.bold
        or style.italic
        or style.strikethrough
        or style.underline
        or style.link
    )


def _is_monospace(style: Any) -> bool:
    """Return True if the text style specifies a monospace font family."""
    wff = style.weighted_font_family
    return bool(wff and wff.font_family in _MONOSPACE_FAMILIES)


def _wrap_markers(text: str, marker: str) -> str:
    """Wrap text with markdown bold/italic markers.

    Moves leading/trailing whitespace outside the markers so that the result
    is CommonMark-compliant.  For example, a bold run whose content is
    ' Send Test ' would otherwise produce '** Send Test **', which most
    parsers (including mistletoe) do NOT recognise as bold because the
    delimiter run is followed/preceded by whitespace.  The correct form is
    ' **Send Test** '.
    """
    stripped = text.strip()
    if not stripped:
        return text  # only whitespace — wrapping would produce invalid markup
    leading = text[: len(text) - len(text.lstrip())]
    trailing = text[len(text.rstrip()) :]
    return f"{leading}{marker}{stripped}{marker}{trailing}"


def _apply_formatting(text: str, style: Any, *, skip_underline: bool = False) -> str:
    result = _escape_md(text)
    if style.strikethrough:
        result = f"~~{result}~~"
    if style.underline and not skip_underline:
        result = f"<u>{result}</u>"
    if style.bold and style.italic:
        result = _wrap_markers(result, "***")
    elif style.bold:
        result = _wrap_markers(result, "**")
    elif style.italic:
        result = _wrap_markers(result, "*")
    return result


def serialize_text_run(
    tr: Any, *, heading_id_to_name: dict[str, str] | None = None
) -> str:
    """Serialize a single TextRun to markdown.

    Handles inline code, links (including heading/bookmark anchors), and
    bold/italic/strikethrough/underline formatting.

    When *heading_id_to_name* is provided, heading links are serialized using
    the human-readable heading name (e.g. ``[text](#Overview)``) instead of
    the opaque ID.  Placeholder URLs of the form ``#heading-ref:Name`` are
    also resolved back to ``[text](#Name)``.
    """
    content = (tr.content or "").rstrip("\n").replace("\u000b", " ")
    if not content:
        return ""

    style = tr.text_style

    # Inline code: monospace font without a link → backtick notation.
    if style and _is_monospace(style) and not style.link:
        return f"`{content}`"

    if not style or not _style_has_attrs(style):
        return _escape_md(content)

    h_map = heading_id_to_name or {}
    link = style.link
    if link:
        if link.heading:
            hid = link.heading.id or ""
            name = h_map.get(hid)
            if name is not None:
                raw_url = f"#{urllib.parse.quote(name, safe='/')}"
            elif link.heading.tab_id:
                raw_url = f"#heading:{link.heading.tab_id}/{hid}"
            else:
                raw_url = f"#heading:{hid}"
        elif link.heading_id:
            name = h_map.get(link.heading_id)
            if name is not None:
                raw_url = f"#{urllib.parse.quote(name, safe='/')}"
            else:
                raw_url = f"#heading:{link.heading_id}"
        elif link.bookmark:
            # New structured format.
            # Cross-tab: #bookmark:{tab_id}/{bookmark_id}
            # Same-tab:  #bookmark:{bookmark_id}
            bid = link.bookmark.id or ""
            if link.bookmark.tab_id:
                raw_url = f"#bookmark:{link.bookmark.tab_id}/{bid}"
            else:
                raw_url = f"#bookmark:{bid}"
        elif link.bookmark_id:
            # Legacy format.
            raw_url = f"#bookmark:{link.bookmark_id}"
        elif link.tab_id:
            # Direct link to a tab (no specific heading/bookmark).
            raw_url = f"#tab:{link.tab_id}"
        else:
            raw_url = link.url or "#"
            # Resolve #heading-ref: placeholders back to name-based links
            if raw_url.startswith("#heading-ref:"):
                raw_url = "#" + urllib.parse.quote(
                    raw_url[len("#heading-ref:") :], safe="/"
                )
        url = _normalize_url(raw_url)
        # Underline is implied by markdown link syntax — skip it inside links
        inner = _apply_formatting(content, style, skip_underline=True)
        return f"[{inner}]({url})"

    return _apply_formatting(content, style)


# ---------------------------------------------------------------------------
# Heading maps for name-based heading links
# ---------------------------------------------------------------------------


def build_heading_maps(
    doc: Any,
) -> tuple[dict[str, str], dict[str, tuple[str, str | None]]]:
    """Build heading_id_to_name and heading_name_to_info maps from a Document.

    Walks all tabs to extract headings with their IDs and text content.

    Returns:
        (heading_id_to_name, heading_name_to_info).
        heading_name_to_info maps heading name → (heading_id, tab_id).
        It includes per-tab entries ("HeadingName") and cross-tab entries
        ("FolderName/HeadingName"). First occurrence wins for duplicate
        heading names within the same scope.
    """
    id_to_name: dict[str, str] = {}
    name_to_info: dict[str, tuple[str, str | None]] = {}

    _HEADING_STYLES = {
        "TITLE",
        "SUBTITLE",
        "HEADING_1",
        "HEADING_2",
        "HEADING_3",
        "HEADING_4",
        "HEADING_5",
        "HEADING_6",
    }

    for tab in doc.tabs or []:
        props = tab.tab_properties
        tab_title = (props.title or "Tab 1") if props else "Tab 1"
        tab_id = (props.tab_id or None) if props else None
        folder = sanitize_tab_name(tab_title)

        dt = tab.document_tab if tab else None
        body = dt.body if dt else None
        for se in (body.content or []) if body else []:
            para = se.paragraph
            if not para:
                continue
            ps = para.paragraph_style
            if not ps or not ps.named_style_type:
                continue
            style_name = (
                ps.named_style_type.value
                if hasattr(ps.named_style_type, "value")
                else str(ps.named_style_type)
            )
            if style_name not in _HEADING_STYLES:
                continue
            hid = ps.heading_id
            if not hid:
                continue
            text = "".join(
                (pe.text_run.content or "").rstrip("\n")
                for pe in (para.elements or [])
                if pe.text_run and pe.text_run.content
            ).strip()
            if not text:
                continue

            id_to_name.setdefault(hid, text)
            name_to_info.setdefault(text, (hid, tab_id))
            cross_key = f"{folder}/{text}"
            name_to_info.setdefault(cross_key, (hid, tab_id))

    return id_to_name, name_to_info
