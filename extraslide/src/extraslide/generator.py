"""JSON to SML generator.

Converts Google Slides API JSON response to SML (Slide Markup Language).

Spec reference: markup-syntax-design.md
"""

from __future__ import annotations

import base64
import hashlib
import html
import re
from typing import Any

from extraslide.classes import (
    Fill,
    ParagraphStyle,
    Shadow,
    Stroke,
    TextStyle,
    Transform,
)
from extraslide.units import emu_to_pt, format_pt


def _sanitize_xml_content(text: str) -> str:
    """Remove invalid XML 1.0 control characters from text.

    XML 1.0 only allows: #x9, #xA, #xD, #x20-#xD7FF, #xE000-#xFFFD, #x10000-#x10FFFF
    This removes characters like vertical tab (0x0B), form feed (0x0C), etc.
    """
    # Pattern matches invalid XML 1.0 characters
    # Allows: tab (0x9), newline (0xA), carriage return (0xD), and chars >= 0x20
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)


# Mapping from API shape types to SML element names
SHAPE_TYPE_MAP: dict[str, str] = {
    "TEXT_BOX": "TextBox",
    "RECTANGLE": "Rect",
    "ROUND_RECTANGLE": "RoundRect",
    "ELLIPSE": "Ellipse",
    "TRIANGLE": "Triangle",
    "RIGHT_TRIANGLE": "RightTriangle",
    "DIAMOND": "Diamond",
    "PENTAGON": "Pentagon",
    "HEXAGON": "Hexagon",
    "HEPTAGON": "Heptagon",
    "OCTAGON": "Octagon",
    "DECAGON": "Decagon",
    "DODECAGON": "Dodecagon",
    "PARALLELOGRAM": "Parallelogram",
    "TRAPEZOID": "Trapezoid",
    "STAR_4": "Star4",
    "STAR_5": "Star5",
    "STAR_6": "Star6",
    "STAR_7": "Star7",
    "STAR_8": "Star8",
    "STAR_10": "Star10",
    "STAR_12": "Star12",
    "STAR_16": "Star16",
    "STAR_24": "Star24",
    "STAR_32": "Star32",
    "STARBURST": "Starburst",
    "HEART": "Heart",
    "MOON": "Moon",
    "SUN": "Sun",
    "CLOUD": "Cloud",
    "LIGHTNING_BOLT": "Lightning",
    "TEARDROP": "Teardrop",
    "SMILEY_FACE": "SmileyFace",
    "NO_SMOKING": "NoSmoking",
    "IRREGULAR_SEAL_1": "IrregularSeal1",
    "IRREGULAR_SEAL_2": "IrregularSeal2",
    "ARROW_LEFT": "ArrowLeft",
    "ARROW_RIGHT": "ArrowRight",
    "ARROW_UP": "ArrowUp",
    "ARROW_DOWN": "ArrowDown",
    "ARROW_NORTH": "ArrowNorth",
    "ARROW_EAST": "ArrowEast",
    "ARROW_NORTH_EAST": "ArrowNorthEast",
    "BENT_ARROW": "ArrowBent",
    "BENT_UP_ARROW": "ArrowBentUp",
    "U_TURN_ARROW": "ArrowUturn",
    "CURVED_LEFT_ARROW": "ArrowCurvedLeft",
    "CURVED_RIGHT_ARROW": "ArrowCurvedRight",
    "CURVED_UP_ARROW": "ArrowCurvedUp",
    "CURVED_DOWN_ARROW": "ArrowCurvedDown",
    "NOTCHED_RIGHT_ARROW": "ArrowNotchedRight",
    "STRIPED_RIGHT_ARROW": "ArrowStripedRight",
    "LEFT_RIGHT_ARROW": "ArrowLeftRight",
    "UP_DOWN_ARROW": "ArrowUpDown",
    "LEFT_RIGHT_UP_ARROW": "ArrowLeftRightUp",
    "LEFT_UP_ARROW": "ArrowLeftUp",
    "QUAD_ARROW": "ArrowQuad",
    "LEFT_ARROW_CALLOUT": "CalloutArrowLeft",
    "RIGHT_ARROW_CALLOUT": "CalloutArrowRight",
    "UP_ARROW_CALLOUT": "CalloutArrowUp",
    "DOWN_ARROW_CALLOUT": "CalloutArrowDown",
    "LEFT_RIGHT_ARROW_CALLOUT": "CalloutArrowLeftRight",
    "QUAD_ARROW_CALLOUT": "CalloutArrowQuad",
    "WEDGE_RECTANGLE_CALLOUT": "CalloutWedgeRect",
    "WEDGE_ROUND_RECTANGLE_CALLOUT": "CalloutWedgeRoundRect",
    "WEDGE_ELLIPSE_CALLOUT": "CalloutWedgeEllipse",
    "CLOUD_CALLOUT": "CalloutCloud",
    "SPEECH": "Speech",
    "BRACE_PAIR": "BracePair",
    "BRACKET_PAIR": "BracketPair",
    "LEFT_BRACE": "BraceLeft",
    "RIGHT_BRACE": "BraceRight",
    "LEFT_BRACKET": "BracketLeft",
    "RIGHT_BRACKET": "BracketRight",
    "PLUS": "Plus",
    "MATH_PLUS": "MathPlus",
    "MATH_MINUS": "MathMinus",
    "MATH_MULTIPLY": "MathMultiply",
    "MATH_DIVIDE": "MathDivide",
    "MATH_EQUAL": "MathEqual",
    "MATH_NOT_EQUAL": "MathNotEqual",
    "FLOWCHART_PROCESS": "FlowProcess",
    "FLOWCHART_ALTERNATE_PROCESS": "FlowAlternateProcess",
    "FLOWCHART_DECISION": "FlowDecision",
    "FLOWCHART_TERMINATOR": "FlowTerminator",
    "FLOWCHART_INPUT_OUTPUT": "FlowIO",
    "FLOWCHART_DOCUMENT": "FlowDocument",
    "FLOWCHART_MULTIDOCUMENT": "FlowMultiDoc",
    "FLOWCHART_PREPARATION": "FlowPreparation",
    "FLOWCHART_PREDEFINED_PROCESS": "FlowPredefinedProcess",
    "FLOWCHART_CONNECTOR": "FlowConnector",
    "FLOWCHART_OFFPAGE_CONNECTOR": "FlowOffpageConnector",
    "FLOWCHART_MERGE": "FlowMerge",
    "FLOWCHART_EXTRACT": "FlowExtract",
    "FLOWCHART_SORT": "FlowSort",
    "FLOWCHART_COLLATE": "FlowCollate",
    "FLOWCHART_SUMMING_JUNCTION": "FlowSummingJunction",
    "FLOWCHART_OR": "FlowOr",
    "FLOWCHART_MANUAL_INPUT": "FlowManualInput",
    "FLOWCHART_MANUAL_OPERATION": "FlowManualOperation",
    "FLOWCHART_DELAY": "FlowDelay",
    "FLOWCHART_DISPLAY": "FlowDisplay",
    "FLOWCHART_INTERNAL_STORAGE": "FlowInternalStorage",
    "FLOWCHART_MAGNETIC_DISK": "FlowMagneticDisk",
    "FLOWCHART_MAGNETIC_DRUM": "FlowMagneticDrum",
    "FLOWCHART_MAGNETIC_TAPE": "FlowMagneticTape",
    "FLOWCHART_ONLINE_STORAGE": "FlowOnlineStorage",
    "FLOWCHART_OFFLINE_STORAGE": "FlowOfflineStorage",
    "FLOWCHART_PUNCHED_CARD": "FlowPunchedCard",
    "FLOWCHART_PUNCHED_TAPE": "FlowPunchedTape",
    "RIBBON": "Ribbon",
    "RIBBON_2": "Ribbon2",
    "ELLIPSE_RIBBON": "EllipseRibbon",
    "ELLIPSE_RIBBON_2": "EllipseRibbon2",
    "CUBE": "Cube",
    "CAN": "Can",
    "BEVEL": "Bevel",
    "FRAME": "Frame",
    "HALF_FRAME": "HalfFrame",
    "CORNER": "Corner",
    "PLAQUE": "Plaque",
    "FOLDED_CORNER": "FoldedCorner",
    "DONUT": "Donut",
    "ARC": "Arc",
    "BLOCK_ARC": "BlockArc",
    "CHORD": "Chord",
    "PIE": "Pie",
    "WAVE": "Wave",
    "DOUBLE_WAVE": "DoubleWave",
    "HORIZONTAL_SCROLL": "Scroll",
    "VERTICAL_SCROLL": "ScrollV",
    "CHEVRON": "Chevron",
    "DIAGONAL_STRIPE": "DiagonalStripe",
    "HOME_PLATE": "HomeBase",
    "CUSTOM": "CustomShape",
    # Round rect variants
    "ROUND_1_RECTANGLE": "Round1Rect",
    "ROUND_2_DIAGONAL_RECTANGLE": "Round2DiagRect",
    "ROUND_2_SAME_RECTANGLE": "Round2SameRect",
    "SNIP_ROUND_RECTANGLE": "SnipRoundRect",
    # Snip rect variants
    "SNIP_1_RECTANGLE": "Snip1Rect",
    "SNIP_2_DIAGONAL_RECTANGLE": "Snip2DiagRect",
    "SNIP_2_SAME_RECTANGLE": "Snip2SameRect",
}

# Line type to class mapping
LINE_TYPE_MAP: dict[str, str] = {
    "STRAIGHT_LINE": "line-straight",
    "STRAIGHT_CONNECTOR_1": "line-straight-1",
    "BENT_CONNECTOR_2": "line-bent-2",
    "BENT_CONNECTOR_3": "line-bent-3",
    "BENT_CONNECTOR_4": "line-bent-4",
    "BENT_CONNECTOR_5": "line-bent-5",
    "CURVED_CONNECTOR_2": "line-curved-2",
    "CURVED_CONNECTOR_3": "line-curved-3",
    "CURVED_CONNECTOR_4": "line-curved-4",
    "CURVED_CONNECTOR_5": "line-curved-5",
}

# Arrow style to class mapping
ARROW_STYLE_MAP: dict[str, str] = {
    "NONE": "none",
    "FILL_ARROW": "fill",
    "STEALTH_ARROW": "stealth",
    "OPEN_ARROW": "open",
    "FILL_CIRCLE": "fill-circle",
    "OPEN_CIRCLE": "open-circle",
    "FILL_SQUARE": "fill-square",
    "OPEN_SQUARE": "open-square",
    "FILL_DIAMOND": "fill-diamond",
    "OPEN_DIAMOND": "open-diamond",
}


class SMLGenerator:
    """Generator for converting Google Slides JSON to SML."""

    def __init__(self, pretty: bool = True) -> None:
        """Initialize generator.

        Args:
            pretty: If True, format output with indentation.
        """
        self.pretty = pretty
        self._indent_level = 0

    def generate(self, presentation: dict[str, Any]) -> str:
        """Generate SML from a presentation JSON.

        Args:
            presentation: Google Slides API presentation response.

        Returns:
            SML string.
        """
        lines: list[str] = []

        # Presentation element
        pres_attrs = self._presentation_attrs(presentation)
        lines.append(self._tag("Presentation", pres_attrs, close=False))
        self._indent_level += 1

        # Images container (will be populated during generation)
        # Stored for later output after collecting all images
        self._image_registry: dict[str, str] = {}

        # Masters container
        masters = presentation.get("masters", [])
        if masters:
            lines.append("")
            lines.append(self._indent() + "<Masters>")
            self._indent_level += 1
            for master in masters:
                lines.append("")
                lines.extend(self._generate_master(master))
            self._indent_level -= 1
            lines.append(self._indent() + "</Masters>")

        # Layouts container
        layouts = presentation.get("layouts", [])
        if layouts:
            lines.append("")
            lines.append(self._indent() + "<Layouts>")
            self._indent_level += 1
            for layout in layouts:
                lines.append("")
                lines.extend(self._generate_layout(layout))
            self._indent_level -= 1
            lines.append(self._indent() + "</Layouts>")

        # Slides container
        slides = presentation.get("slides", [])
        if slides:
            lines.append("")
            lines.append(self._indent() + "<Slides>")
            self._indent_level += 1
            for slide in slides:
                lines.append("")
                lines.extend(self._generate_slide(slide))
            self._indent_level -= 1
            lines.append(self._indent() + "</Slides>")

        self._indent_level -= 1
        lines.append("")
        lines.append("</Presentation>")

        # Insert Images container after Presentation opening if we have images
        if self._image_registry:
            images_lines: list[str] = []
            images_lines.append("")
            images_lines.append("  <Images>")
            for img_hash, url in sorted(self._image_registry.items()):
                images_lines.append(
                    f'    <Img id="{img_hash}" url="{html.escape(url, quote=True)}"/>'
                )
            images_lines.append("  </Images>")
            # Insert after the Presentation opening tag
            insert_pos = 1
            for img_line in images_lines:
                lines.insert(insert_pos, img_line)
                insert_pos += 1

        return "\n".join(lines)

    def _presentation_attrs(self, pres: dict[str, Any]) -> dict[str, str]:
        """Extract presentation attributes."""
        attrs: dict[str, str] = {}

        attrs["id"] = pres.get("presentationId", "")

        if "title" in pres:
            attrs["title"] = pres["title"]

        # Page size
        page_size = pres.get("pageSize", {})
        width = page_size.get("width", {})
        height = page_size.get("height", {})

        if width.get("magnitude"):
            attrs["w"] = format_pt(emu_to_pt(width["magnitude"])) + "pt"
        if height.get("magnitude"):
            attrs["h"] = format_pt(emu_to_pt(height["magnitude"])) + "pt"

        if "locale" in pres:
            attrs["locale"] = pres["locale"]

        if "revisionId" in pres:
            attrs["revision"] = pres["revisionId"]

        return attrs

    def _generate_master(self, master: dict[str, Any]) -> list[str]:
        """Generate SML for a master slide."""
        lines: list[str] = []

        attrs: dict[str, str] = {"id": master.get("objectId", "")}

        # Get master name from masterProperties
        props = master.get("masterProperties", {})
        if "displayName" in props:
            attrs["name"] = props["displayName"]

        lines.append(self._tag("Master", attrs, close=False))
        self._indent_level += 1

        # TODO: Generate ColorScheme from master.pageProperties.colorScheme

        # Page elements
        for element in master.get("pageElements", []):
            lines.extend(self._generate_page_element(element))

        self._indent_level -= 1
        lines.append(self._indent() + "</Master>")

        return lines

    def _generate_layout(self, layout: dict[str, Any]) -> list[str]:
        """Generate SML for a layout slide."""
        lines: list[str] = []

        attrs: dict[str, str] = {"id": layout.get("objectId", "")}

        # Get layout properties
        props = layout.get("layoutProperties", {})
        if "masterObjectId" in props:
            attrs["master"] = props["masterObjectId"]
        if "name" in props:
            attrs["name"] = props["name"]
        if "displayName" in props:
            attrs["display-name"] = props["displayName"]

        lines.append(self._tag("Layout", attrs, close=False))
        self._indent_level += 1

        # Page elements
        for element in layout.get("pageElements", []):
            lines.extend(self._generate_page_element(element))

        self._indent_level -= 1
        lines.append(self._indent() + "</Layout>")

        return lines

    def _generate_slide(self, slide: dict[str, Any]) -> list[str]:
        """Generate SML for a slide."""
        lines: list[str] = []

        attrs: dict[str, str] = {"id": slide.get("objectId", "")}

        # Get slide properties
        props = slide.get("slideProperties", {})
        if "layoutObjectId" in props:
            attrs["layout"] = props["layoutObjectId"]
        if "masterObjectId" in props:
            attrs["master"] = props["masterObjectId"]
        if props.get("isSkipped"):
            attrs["skipped"] = "true"

        # Background class
        bg_classes = self._page_background_classes(slide)
        if bg_classes:
            attrs["class"] = " ".join(bg_classes)

        lines.append(self._tag("Slide", attrs, close=False))
        self._indent_level += 1

        # Page elements
        for element in slide.get("pageElements", []):
            lines.extend(self._generate_page_element(element))

        self._indent_level -= 1
        lines.append(self._indent() + "</Slide>")

        return lines

    def _page_background_classes(self, page: dict[str, Any]) -> list[str]:
        """Get background classes from page properties."""
        classes: list[str] = []

        props = page.get("pageProperties", {})
        bg_fill = props.get("pageBackgroundFill", {})

        fill = Fill.from_api(bg_fill)
        if fill:
            cls = fill.to_class(prefix="bg")
            if cls:
                classes.append(cls)

        return classes

    def _generate_page_element(self, element: dict[str, Any]) -> list[str]:
        """Generate SML for a page element."""
        lines: list[str] = []

        object_id = element.get("objectId", "")

        # Determine element type
        if "shape" in element:
            lines.extend(self._generate_shape(element))
        elif "line" in element:
            lines.extend(self._generate_line(element))
        elif "image" in element:
            lines.extend(self._generate_image(element))
        elif "table" in element:
            lines.extend(self._generate_table(element))
        elif "video" in element:
            lines.extend(self._generate_video(element))
        elif "sheetsChart" in element:
            lines.extend(self._generate_chart(element))
        elif "wordArt" in element:
            lines.extend(self._generate_wordart(element))
        elif "elementGroup" in element:
            lines.extend(self._generate_group(element))
        elif "speakerSpotlight" in element:
            lines.extend(self._generate_spotlight(element))
        else:
            # Unknown element type - output as comment
            lines.append(self._indent() + f"<!-- Unknown element type: {object_id} -->")

        return lines

    def _generate_shape(self, element: dict[str, Any]) -> list[str]:
        """Generate SML for a shape element."""
        lines: list[str] = []

        shape = element.get("shape", {})
        shape_type = shape.get("shapeType", "RECTANGLE")
        tag_name = SHAPE_TYPE_MAP.get(shape_type, "Rect")

        attrs = self._element_attrs(element)

        # Shape properties classes
        shape_props = shape.get("shapeProperties", {})
        shape_classes = self._shape_properties_classes(shape_props)
        attrs = self._merge_classes(attrs, shape_classes)

        # Content alignment
        content_align = shape_props.get("contentAlignment")
        if content_align:
            align_class = self._content_alignment_class(content_align)
            if align_class:
                attrs = self._merge_classes(attrs, [align_class])

        # Autofit
        autofit = shape_props.get("autofit", {})
        autofit_type = autofit.get("autofitType")
        if autofit_type:
            autofit_class = self._autofit_class(autofit_type)
            if autofit_class:
                attrs = self._merge_classes(attrs, [autofit_class])

        # Placeholder
        placeholder = shape.get("placeholder")
        if placeholder:
            ph_attrs = self._placeholder_attrs(placeholder)
            attrs.update(ph_attrs)

        # Check if shape has text
        text = shape.get("text")
        if text and text.get("textElements"):
            lines.append(self._tag(tag_name, attrs, close=False))
            self._indent_level += 1
            lines.extend(self._generate_text_content(text))
            self._indent_level -= 1
            lines.append(self._indent() + f"</{tag_name}>")
        else:
            lines.append(self._tag(tag_name, attrs, close=True))

        return lines

    def _generate_line(self, element: dict[str, Any]) -> list[str]:
        """Generate SML for a line element."""
        lines: list[str] = []

        line = element.get("line", {})
        attrs = self._element_attrs(element)

        # Line type class
        line_type = line.get("lineType", "STRAIGHT_LINE")
        line_class = LINE_TYPE_MAP.get(line_type, "line-straight")
        attrs = self._merge_classes(attrs, [line_class])

        # Line properties
        line_props = line.get("lineProperties", {})

        # Stroke color and weight
        stroke = Stroke.from_api(
            {"outlineFill": line_props.get("lineFill"), **line_props}
        )
        if stroke:
            stroke_classes = stroke.to_classes()
            attrs = self._merge_classes(attrs, stroke_classes)

        # Arrow styles
        start_arrow = line_props.get("startArrow", "NONE")
        if start_arrow != "NONE":
            arrow_cls = ARROW_STYLE_MAP.get(start_arrow, "")
            if arrow_cls:
                attrs = self._merge_classes(attrs, [f"arrow-start-{arrow_cls}"])

        end_arrow = line_props.get("endArrow", "NONE")
        if end_arrow != "NONE":
            arrow_cls = ARROW_STYLE_MAP.get(end_arrow, "")
            if arrow_cls:
                attrs = self._merge_classes(attrs, [f"arrow-end-{arrow_cls}"])

        # Connection info
        start_conn = line.get("lineProperties", {}).get("startConnection")
        end_conn = line.get("lineProperties", {}).get("endConnection")
        if start_conn:
            conn_id = start_conn.get("connectedObjectId", "")
            conn_idx = start_conn.get("connectionSiteIndex", 0)
            attrs["connect-start"] = f"{conn_id}:{conn_idx}"
        if end_conn:
            conn_id = end_conn.get("connectedObjectId", "")
            conn_idx = end_conn.get("connectionSiteIndex", 0)
            attrs["connect-end"] = f"{conn_id}:{conn_idx}"

        lines.append(self._tag("Line", attrs, close=True))
        return lines

    def _hash_url(self, url: str) -> str:
        """Generate a short hash for a URL.

        Uses SHA256 truncated to 8 chars (base64url encoding).
        """
        sha = hashlib.sha256(url.encode("utf-8")).digest()
        # Use base64url encoding (- and _ instead of + and /)
        b64 = base64.urlsafe_b64encode(sha[:6]).decode("ascii")
        # Take first 8 chars
        return b64[:8]

    def _generate_image(self, element: dict[str, Any]) -> list[str]:
        """Generate SML for an image element."""
        lines: list[str] = []

        image = element.get("image", {})
        attrs = self._element_attrs(element)

        # Image source URL - use short hash reference
        content_url = image.get("contentUrl", "")
        if content_url:
            img_hash = self._hash_url(content_url)
            self._image_registry[img_hash] = content_url
            attrs["src"] = f"img:{img_hash}"

        # Source URL (where image was loaded from)
        source_url = image.get("sourceUrl", "")
        if source_url and source_url != content_url:
            attrs["original-src"] = source_url

        # Image properties
        img_props = image.get("imageProperties", {})

        # Outline
        outline = img_props.get("outline")
        if outline:
            stroke = Stroke.from_api(outline)
            if stroke:
                stroke_classes = stroke.to_classes()
                attrs = self._merge_classes(attrs, stroke_classes)

        # Shadow
        shadow = img_props.get("shadow")
        if shadow:
            shadow_obj = Shadow.from_api(shadow)
            if shadow_obj:
                shadow_classes = shadow_obj.to_classes()
                attrs = self._merge_classes(attrs, shadow_classes)

        # Alt text / accessibility
        if "title" in element:
            attrs["title"] = element["title"]
        if "description" in element:
            attrs["alt"] = element["description"]

        # Link
        link = img_props.get("link")
        if link:
            href = link.get("url") or link.get("pageObjectId")
            if href:
                attrs["href"] = href

        lines.append(self._tag("Image", attrs, close=True))
        return lines

    def _generate_table(self, element: dict[str, Any]) -> list[str]:
        """Generate SML for a table element."""
        lines: list[str] = []

        table = element.get("table", {})
        attrs = self._element_attrs(element)

        rows = table.get("rows", 0)
        cols = table.get("columns", 0)
        attrs["rows"] = str(rows)
        attrs["cols"] = str(cols)

        lines.append(self._tag("Table", attrs, close=False))
        self._indent_level += 1

        # Table rows
        table_rows = table.get("tableRows", [])
        for row_idx, table_row in enumerate(table_rows):
            lines.extend(self._generate_table_row(element, row_idx, table_row))

        self._indent_level -= 1
        lines.append(self._indent() + "</Table>")

        return lines

    def _generate_table_row(
        self, element: dict[str, Any], row_idx: int, table_row: dict[str, Any]
    ) -> list[str]:
        """Generate SML for a table row."""
        lines: list[str] = []

        row_attrs: dict[str, str] = {"r": str(row_idx)}

        # Row height
        height = table_row.get("rowHeight", {})
        if height.get("magnitude"):
            row_attrs["class"] = f"h-{format_pt(emu_to_pt(height['magnitude']))}"

        lines.append(self._tag("Row", row_attrs, close=False))
        self._indent_level += 1

        table_id = element.get("objectId", "")

        # Cells
        cells = table_row.get("tableCells", [])
        for col_idx, cell in enumerate(cells):
            lines.extend(self._generate_table_cell(table_id, row_idx, col_idx, cell))

        self._indent_level -= 1
        lines.append(self._indent() + "</Row>")

        return lines

    def _generate_table_cell(
        self,
        table_id: str,
        row_idx: int,
        col_idx: int,
        cell: dict[str, Any],
    ) -> list[str]:
        """Generate SML for a table cell."""
        lines: list[str] = []

        # Generate cell ID
        cell_id = f"{table_id}_r{row_idx}c{col_idx}"

        attrs: dict[str, str] = {
            "id": cell_id,
            "r": str(row_idx),
            "c": str(col_idx),
        }

        # Span
        row_span = cell.get("rowSpan", 1)
        col_span = cell.get("columnSpan", 1)
        if row_span > 1:
            attrs["rowspan"] = str(row_span)
        if col_span > 1:
            attrs["colspan"] = str(col_span)

        # Cell properties
        cell_props = cell.get("tableCellProperties", {})
        cell_classes: list[str] = []

        # Cell background
        bg_fill = cell_props.get("tableCellBackgroundFill")
        if bg_fill:
            fill = Fill.from_api(bg_fill)
            if fill:
                fill_class = fill.to_class()
                if fill_class:
                    cell_classes.append(fill_class)

        # Content alignment
        content_align = cell_props.get("contentAlignment")
        if content_align:
            align_class = self._content_alignment_class(content_align)
            if align_class:
                cell_classes.append(align_class)

        if cell_classes:
            attrs["class"] = " ".join(cell_classes)

        # Cell text content
        text = cell.get("text")
        if text and text.get("textElements"):
            lines.append(self._tag("Cell", attrs, close=False))
            self._indent_level += 1
            lines.extend(self._generate_text_content(text))
            self._indent_level -= 1
            lines.append(self._indent() + "</Cell>")
        else:
            lines.append(self._tag("Cell", attrs, close=True))

        return lines

    def _generate_video(self, element: dict[str, Any]) -> list[str]:
        """Generate SML for a video element."""
        lines: list[str] = []

        video = element.get("video", {})
        attrs = self._element_attrs(element)

        # Video source
        source = video.get("source", "")
        video_id = video.get("id", "")
        if source == "YOUTUBE":
            attrs["src"] = f"youtube:{video_id}"
        elif source == "DRIVE":
            attrs["src"] = f"drive:{video_id}"

        # Video properties
        video_props = video.get("videoProperties", {})

        if video_props.get("autoPlay"):
            attrs["autoplay"] = "true"
        if video_props.get("mute"):
            attrs["muted"] = "true"
        if "start" in video_props:
            attrs["start"] = str(video_props["start"])
        if "end" in video_props:
            attrs["end"] = str(video_props["end"])

        lines.append(self._tag("Video", attrs, close=True))
        return lines

    def _generate_chart(self, element: dict[str, Any]) -> list[str]:
        """Generate SML for a Sheets chart element."""
        lines: list[str] = []

        chart = element.get("sheetsChart", {})
        attrs = self._element_attrs(element)

        attrs["spreadsheet"] = chart.get("spreadsheetId", "")
        attrs["chart-id"] = str(chart.get("chartId", ""))

        lines.append(self._tag("Chart", attrs, close=True))
        return lines

    def _generate_wordart(self, element: dict[str, Any]) -> list[str]:
        """Generate SML for a WordArt element."""
        lines: list[str] = []

        wordart = element.get("wordArt", {})
        attrs = self._element_attrs(element)

        rendered_text = wordart.get("renderedText", "")

        lines.append(self._tag("WordArt", attrs, close=False))
        self._indent_level += 1
        lines.append(self._indent() + html.escape(rendered_text))
        self._indent_level -= 1
        lines.append(self._indent() + "</WordArt>")

        return lines

    def _generate_group(self, element: dict[str, Any]) -> list[str]:
        """Generate SML for a group element."""
        lines: list[str] = []

        group = element.get("elementGroup", {})
        attrs = self._element_attrs(element)

        lines.append(self._tag("Group", attrs, close=False))
        self._indent_level += 1

        # Generate children
        for child in group.get("children", []):
            lines.extend(self._generate_page_element(child))

        self._indent_level -= 1
        lines.append(self._indent() + "</Group>")

        return lines

    def _generate_spotlight(self, element: dict[str, Any]) -> list[str]:
        """Generate SML for a speaker spotlight element."""
        lines: list[str] = []
        attrs = self._element_attrs(element)
        lines.append(self._tag("Spotlight", attrs, close=True))
        return lines

    def _generate_text_content(self, text: dict[str, Any]) -> list[str]:
        """Generate text content with explicit P and T elements.

        Spec: All text must be in <P><T>...</T></P> structure.
        Ranges are read-only coordinates for diffing.
        """
        lines: list[str] = []

        text_elements = text.get("textElements", [])

        # Group text elements into paragraphs
        paragraphs: list[dict[str, Any]] = []
        current_para: dict[str, Any] = {"style": None, "runs": [], "start": 0, "end": 0}

        for elem in text_elements:
            if "paragraphMarker" in elem:
                # Start new paragraph
                if current_para["runs"]:
                    paragraphs.append(current_para)
                current_para = {
                    "style": elem.get("paragraphMarker", {}).get("style"),
                    "bullet": elem.get("paragraphMarker", {}).get("bullet"),
                    "runs": [],
                    "start": elem.get("startIndex", 0),
                    "end": elem.get("endIndex", 0),
                }
            elif "textRun" in elem:
                run = elem["textRun"]
                content = run.get("content", "")
                style = run.get("style", {})
                start_idx = elem.get("startIndex", 0)
                end_idx = elem.get("endIndex", len(content))

                # Skip trailing newline (it's implicit in <P>)
                if content == "\n":
                    current_para["end"] = end_idx
                    continue

                # Remove trailing newline from content
                content = content.rstrip("\n")

                if content:
                    current_para["runs"].append(
                        {
                            "content": content,
                            "style": style,
                            "start": start_idx,
                            "end": end_idx,
                        }
                    )
                    current_para["end"] = end_idx
            elif "autoText" in elem:
                auto_type = elem["autoText"].get("type", "")
                start_idx = elem.get("startIndex", 0)
                end_idx = elem.get("endIndex", 0)
                current_para["runs"].append(
                    {
                        "auto": auto_type,
                        "start": start_idx,
                        "end": end_idx,
                    }
                )
                current_para["end"] = end_idx

        # Add last paragraph
        if current_para["runs"]:
            paragraphs.append(current_para)

        # Generate P elements
        for para in paragraphs:
            para_attrs: dict[str, str] = {}

            # Range attribute
            para_attrs["range"] = f"{para['start']}-{para['end']}"

            # Paragraph style classes
            para_classes: list[str] = []
            if para.get("style"):
                ps = ParagraphStyle.from_api(para["style"])
                if ps:
                    para_classes.extend(ps.to_classes())

            # Bullet
            if para.get("bullet"):
                para_classes.append("bullet")
                glyph = para["bullet"].get("glyph", "")
                if glyph:
                    # Map glyph to bullet class
                    glyph_map = {
                        "●": "bullet-disc",
                        "○": "bullet-circle",
                        "■": "bullet-square",
                    }
                    bullet_class = glyph_map.get(glyph)
                    if bullet_class:
                        para_classes.append(bullet_class)
                nesting = para["bullet"].get("nestingLevel", 0)
                if nesting > 0:
                    para_classes.append(f"indent-level-{nesting}")

            if para_classes:
                para_attrs["class"] = " ".join(para_classes)

            lines.append(self._tag("P", para_attrs, close=False))
            self._indent_level += 1

            # Generate T elements
            for run in para["runs"]:
                if "auto" in run:
                    # Auto text (slide number, etc.)
                    auto_type = run["auto"].lower().replace("_", "-")
                    lines.append(self._indent() + f'<Auto type="{auto_type}"/>')
                else:
                    run_attrs: dict[str, str] = {}
                    run_attrs["range"] = f"{run['start']}-{run['end']}"

                    # Text style classes
                    ts = TextStyle.from_api(run.get("style"))
                    if ts:
                        run_classes = ts.to_classes()
                        if run_classes:
                            run_attrs["class"] = " ".join(run_classes)

                        # Link
                        if ts.link:
                            run_attrs["href"] = ts.link

                    content = html.escape(_sanitize_xml_content(run["content"]))
                    lines.append(self._tag_with_content("T", run_attrs, content))

            self._indent_level -= 1
            lines.append(self._indent() + "</P>")

        return lines

    def _element_attrs(self, element: dict[str, Any]) -> dict[str, str]:
        """Get common element attributes (id, transform)."""
        attrs: dict[str, str] = {}

        attrs["id"] = element.get("objectId", "")

        # Transform
        transform_obj = element.get("transform")
        size_obj = element.get("size")

        transform = Transform.from_api(transform_obj, size_obj)
        transform_classes = transform.to_classes()

        if transform_classes:
            attrs["class"] = " ".join(transform_classes)

        return attrs

    def _shape_properties_classes(self, shape_props: dict[str, Any]) -> list[str]:
        """Get classes from shape properties."""
        classes: list[str] = []

        # Fill
        bg_fill = shape_props.get("shapeBackgroundFill")
        if bg_fill:
            fill = Fill.from_api(bg_fill)
            if fill:
                fill_class = fill.to_class()
                if fill_class:
                    classes.append(fill_class)

        # Outline/stroke
        outline = shape_props.get("outline")
        if outline:
            stroke = Stroke.from_api(outline)
            if stroke:
                classes.extend(stroke.to_classes())

        # Shadow
        shadow = shape_props.get("shadow")
        if shadow:
            shadow_obj = Shadow.from_api(shadow)
            if shadow_obj:
                classes.extend(shadow_obj.to_classes())

        return classes

    def _content_alignment_class(self, alignment: str) -> str:
        """Map content alignment to class."""
        mapping = {
            "TOP": "content-top",
            "MIDDLE": "content-middle",
            "BOTTOM": "content-bottom",
        }
        return mapping.get(alignment, "")

    def _autofit_class(self, autofit_type: str) -> str:
        """Map autofit type to class."""
        mapping = {
            "NONE": "autofit-none",
            "TEXT_AUTOFIT": "autofit-text",
            "SHAPE_AUTOFIT": "autofit-shape",
        }
        return mapping.get(autofit_type, "")

    def _placeholder_attrs(self, placeholder: dict[str, Any]) -> dict[str, str]:
        """Get placeholder attributes."""
        attrs: dict[str, str] = {}

        ph_type = placeholder.get("type", "")
        if ph_type:
            attrs["placeholder"] = ph_type.lower().replace("_", "-")

        idx = placeholder.get("index")
        if idx is not None:
            attrs["placeholder-index"] = str(idx)

        parent_id = placeholder.get("parentObjectId")
        if parent_id:
            attrs["placeholder-parent"] = parent_id

        return attrs

    def _merge_classes(
        self, attrs: dict[str, str], classes: list[str]
    ) -> dict[str, str]:
        """Merge additional classes into attrs."""
        if not classes:
            return attrs

        existing = attrs.get("class", "").split() if attrs.get("class") else []
        combined = existing + classes
        attrs["class"] = " ".join(combined)
        return attrs

    def _indent(self) -> str:
        """Get current indentation string."""
        if self.pretty:
            return "  " * self._indent_level
        return ""

    def _tag(self, name: str, attrs: dict[str, str], close: bool = False) -> str:
        """Build an XML/HTML tag."""
        parts = [self._indent(), f"<{name}"]

        for key, value in attrs.items():
            parts.append(f' {key}="{html.escape(str(value), quote=True)}"')

        if close:
            parts.append("/>")
        else:
            parts.append(">")

        return "".join(parts)

    def _tag_with_content(self, name: str, attrs: dict[str, str], content: str) -> str:
        """Build a tag with inline content."""
        parts = [self._indent(), f"<{name}"]

        for key, value in attrs.items():
            parts.append(f' {key}="{html.escape(str(value), quote=True)}"')

        parts.append(f">{content}</{name}>")

        return "".join(parts)


def json_to_sml(presentation: dict[str, Any], pretty: bool = True) -> str:
    """Convert presentation JSON to SML.

    Args:
        presentation: Google Slides API presentation response.
        pretty: If True, format with indentation.

    Returns:
        SML string.
    """
    generator = SMLGenerator(pretty=pretty)
    return generator.generate(presentation)
