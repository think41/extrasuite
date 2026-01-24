"""SML Parser.

Parses SML (Slide Markup Language) into data structures for diffing.

Spec reference: sml-reconciliation-spec.md
"""

from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from extraslide.classes import (
    Fill,
    ParagraphStyle,
    Stroke,
    TextStyle,
    parse_class_string,
    parse_fill_class,
    parse_position_classes,
    parse_stroke_classes,
    parse_text_style_classes,
)


class SMLParseError(Exception):
    """Error during SML parsing."""

    pass


class SMLValidationError(SMLParseError):
    """SML validation error (e.g., bare text, newlines in content)."""

    pass


# ============================================================================
# Data Structures for Parsed SML
# ============================================================================


@dataclass
class ParsedTextRun:
    """A parsed <T> element.

    Spec: sml-reconciliation-spec.md#text-content-model
    """

    content: str
    range_start: int | None = None
    range_end: int | None = None
    classes: list[str] = field(default_factory=list)
    href: str | None = None
    style: TextStyle | None = None


@dataclass
class ParsedAutoText:
    """A parsed <Auto> element."""

    type: str
    range_start: int | None = None
    range_end: int | None = None


@dataclass
class ParsedParagraph:
    """A parsed <P> element.

    Spec: sml-reconciliation-spec.md#text-content-model
    """

    range_start: int | None = None
    range_end: int | None = None
    classes: list[str] = field(default_factory=list)
    runs: list[ParsedTextRun | ParsedAutoText] = field(default_factory=list)
    style: ParagraphStyle | None = None


@dataclass
class ParsedTableCell:
    """A parsed <Cell> element."""

    id: str
    row: int
    col: int
    rowspan: int = 1
    colspan: int = 1
    classes: list[str] = field(default_factory=list)
    paragraphs: list[ParsedParagraph] = field(default_factory=list)


@dataclass
class ParsedTableRow:
    """A parsed <Row> element."""

    row_index: int
    classes: list[str] = field(default_factory=list)
    cells: list[ParsedTableCell] = field(default_factory=list)


@dataclass
class ParsedElement:
    """A parsed SML element (shape, line, image, etc.).

    This is the common structure for all page elements.
    """

    tag: str  # Element type (TextBox, Rect, Line, Image, etc.)
    id: str
    classes: list[str] = field(default_factory=list)
    attrs: dict[str, str] = field(default_factory=dict)
    # Text content (for shapes with text)
    paragraphs: list[ParsedParagraph] = field(default_factory=list)
    # Children (for groups)
    children: list[ParsedElement] = field(default_factory=list)
    # Table content
    rows: int | None = None
    cols: int | None = None
    table_rows: list[ParsedTableRow] = field(default_factory=list)
    # Computed properties
    fill: Fill | None = None
    stroke: Stroke | None = None
    position: dict[str, float] = field(default_factory=dict)


@dataclass
class ParsedSlide:
    """A parsed <Slide> element."""

    id: str
    classes: list[str] = field(default_factory=list)
    layout: str | None = None
    master: str | None = None
    skipped: bool = False
    elements: list[ParsedElement] = field(default_factory=list)


@dataclass
class ParsedMaster:
    """A parsed <Master> element."""

    id: str
    name: str | None = None
    classes: list[str] = field(default_factory=list)
    elements: list[ParsedElement] = field(default_factory=list)


@dataclass
class ParsedLayout:
    """A parsed <Layout> element."""

    id: str
    master: str | None = None
    name: str | None = None
    display_name: str | None = None
    classes: list[str] = field(default_factory=list)
    elements: list[ParsedElement] = field(default_factory=list)


@dataclass
class ParsedPresentation:
    """A parsed SML presentation."""

    id: str
    title: str | None = None
    width: str | None = None
    height: str | None = None
    locale: str | None = None
    revision: str | None = None
    images: dict[str, str] = field(default_factory=dict)  # hash -> url mapping
    masters: list[ParsedMaster] = field(default_factory=list)
    layouts: list[ParsedLayout] = field(default_factory=list)
    slides: list[ParsedSlide] = field(default_factory=list)


# ============================================================================
# Parser Implementation
# ============================================================================


class SMLParser:
    """Parser for SML documents."""

    def __init__(self, strict: bool = True) -> None:
        """Initialize parser.

        Args:
            strict: If True, validate SML constraints strictly.
        """
        self.strict = strict

    def parse(self, sml: str) -> ParsedPresentation:
        """Parse SML string into a ParsedPresentation.

        Args:
            sml: SML string.

        Returns:
            ParsedPresentation object.

        Raises:
            SMLParseError: If parsing fails.
            SMLValidationError: If SML violates constraints.
        """
        try:
            root = ET.fromstring(sml)
        except ET.ParseError as e:
            raise SMLParseError(f"Invalid XML: {e}") from e

        if root.tag != "Presentation":
            raise SMLParseError(
                f"Root element must be <Presentation>, got <{root.tag}>"
            )

        return self._parse_presentation(root)

    def _parse_presentation(self, elem: ET.Element) -> ParsedPresentation:
        """Parse <Presentation> element."""
        pres = ParsedPresentation(
            id=elem.get("id", ""),
            title=elem.get("title"),
            width=elem.get("w"),
            height=elem.get("h"),
            locale=elem.get("locale"),
            revision=elem.get("revision"),
        )

        for child in elem:
            if child.tag == "Images":
                # Parse image registry
                for img in child:
                    if img.tag == "Img":
                        img_id = img.get("id", "")
                        img_url = img.get("url", "")
                        if img_id and img_url:
                            pres.images[img_id] = img_url
            elif child.tag == "Masters":
                # Container for masters
                for master in child:
                    if master.tag == "Master":
                        pres.masters.append(self._parse_master(master))
            elif child.tag == "Layouts":
                # Container for layouts
                for layout in child:
                    if layout.tag == "Layout":
                        pres.layouts.append(self._parse_layout(layout))
            elif child.tag == "Slides":
                # Container for slides
                for slide in child:
                    if slide.tag == "Slide":
                        pres.slides.append(self._parse_slide(slide))
            elif child.tag == "Master":
                # Support legacy format without containers
                pres.masters.append(self._parse_master(child))
            elif child.tag == "Layout":
                # Support legacy format without containers
                pres.layouts.append(self._parse_layout(child))
            elif child.tag == "Slide":
                # Support legacy format without containers
                pres.slides.append(self._parse_slide(child))

        return pres

    def _parse_master(self, elem: ET.Element) -> ParsedMaster:
        """Parse <Master> element."""
        master = ParsedMaster(
            id=elem.get("id", ""),
            name=elem.get("name"),
            classes=parse_class_string(elem.get("class", "")),
        )

        for child in elem:
            if child.tag not in ("ColorScheme",):
                master.elements.append(self._parse_element(child))

        return master

    def _parse_layout(self, elem: ET.Element) -> ParsedLayout:
        """Parse <Layout> element."""
        layout = ParsedLayout(
            id=elem.get("id", ""),
            master=elem.get("master"),
            name=elem.get("name"),
            display_name=elem.get("display-name"),
            classes=parse_class_string(elem.get("class", "")),
        )

        for child in elem:
            layout.elements.append(self._parse_element(child))

        return layout

    def _parse_slide(self, elem: ET.Element) -> ParsedSlide:
        """Parse <Slide> element."""
        slide = ParsedSlide(
            id=elem.get("id", ""),
            layout=elem.get("layout"),
            master=elem.get("master"),
            skipped=elem.get("skipped") == "true",
            classes=parse_class_string(elem.get("class", "")),
        )

        for child in elem:
            if child.tag == "Actions":
                # Actions are parsed separately for reconciliation
                continue
            slide.elements.append(self._parse_element(child))

        return slide

    def _parse_element(self, elem: ET.Element) -> ParsedElement:
        """Parse a page element (shape, line, image, etc.)."""
        tag = elem.tag
        element_id = elem.get("id", "")
        classes = parse_class_string(elem.get("class", ""))

        # Collect all other attributes
        attrs = {
            k: v
            for k, v in elem.attrib.items()
            if k not in ("id", "class", "rows", "cols")
        }

        parsed = ParsedElement(
            tag=tag,
            id=element_id,
            classes=classes,
            attrs=attrs,
        )

        # Parse styling from classes
        parsed.position = parse_position_classes(classes)

        # Parse fill from classes
        for cls in classes:
            if cls.startswith("fill-") or cls.startswith("bg-"):
                prefix = "fill" if cls.startswith("fill-") else "bg"
                fill = parse_fill_class(cls if prefix == "fill" else f"fill-{cls[3:]}")
                if fill:
                    parsed.fill = fill
                    break

        # Parse stroke from classes
        parsed.stroke = parse_stroke_classes(classes)

        # Handle specific element types
        if tag == "Table":
            parsed.rows = int(elem.get("rows", 0))
            parsed.cols = int(elem.get("cols", 0))
            for child in elem:
                if child.tag == "Row":
                    parsed.table_rows.append(self._parse_table_row(child))
        elif tag == "Group":
            for child in elem:
                parsed.children.append(self._parse_element(child))
        elif tag == "WordArt":
            # WordArt has text content directly
            text = "".join(elem.itertext()).strip()
            if text:
                # Create a pseudo-paragraph for the content
                para = ParsedParagraph()
                para.runs.append(ParsedTextRun(content=text))
                parsed.paragraphs.append(para)
        else:
            # Parse text content for shapes
            self._parse_text_content(elem, parsed)

        return parsed

    def _parse_text_content(self, elem: ET.Element, parsed: ParsedElement) -> None:
        """Parse text content (<P> and <T> elements) from a shape."""
        # Check for bare text (validation)
        if self.strict and elem.text and elem.text.strip():
            raise SMLValidationError(
                f"Bare text in <{elem.tag}> is not allowed. "
                f"Text must be wrapped in <P><T>...</T></P>. "
                f"Found: '{elem.text.strip()[:50]}...'"
            )

        for child in elem:
            if child.tag == "P":
                parsed.paragraphs.append(self._parse_paragraph(child))
            # Ignore other children (already handled by specific types)

    def _parse_paragraph(self, elem: ET.Element) -> ParsedParagraph:
        """Parse a <P> element."""
        para = ParsedParagraph(
            classes=parse_class_string(elem.get("class", "")),
        )

        # Parse range attribute
        range_attr = elem.get("range")
        if range_attr:
            para.range_start, para.range_end = self._parse_range(range_attr)

        # Parse paragraph style from classes
        # Note: We don't fully reconstruct ParagraphStyle here since
        # the diff engine primarily compares class strings.

        # Validate no bare text
        if self.strict and elem.text and elem.text.strip():
            raise SMLValidationError(
                f"Bare text in <P> is not allowed. "
                f"Text must be wrapped in <T>...</T>. "
                f"Found: '{elem.text.strip()[:50]}...'"
            )

        # Parse text runs
        for child in elem:
            if child.tag == "T":
                para.runs.append(self._parse_text_run(child))
            elif child.tag == "Auto":
                para.runs.append(self._parse_auto_text(child))

            # Check tail text (text after closing tag)
            if self.strict and child.tail and child.tail.strip():
                raise SMLValidationError(
                    f"Bare text after <{child.tag}> is not allowed. "
                    f"Found: '{child.tail.strip()[:50]}...'"
                )

        return para

    def _parse_text_run(self, elem: ET.Element) -> ParsedTextRun:
        """Parse a <T> element."""
        content = elem.text or ""

        # Validate no newlines in content
        if self.strict and "\n" in content:
            raise SMLValidationError(
                f"Newlines in <T> content are not allowed. "
                f"Use separate <P> elements instead. "
                f"Found newline in: '{content[:50]}...'"
            )

        run = ParsedTextRun(
            content=html.unescape(content),
            classes=parse_class_string(elem.get("class", "")),
            href=elem.get("href"),
        )

        # Parse range attribute
        range_attr = elem.get("range")
        if range_attr:
            run.range_start, run.range_end = self._parse_range(range_attr)

        # Parse text style from classes
        run.style = parse_text_style_classes(run.classes)

        return run

    def _parse_auto_text(self, elem: ET.Element) -> ParsedAutoText:
        """Parse an <Auto> element."""
        auto = ParsedAutoText(type=elem.get("type", ""))

        # Parse range if present
        range_attr = elem.get("range")
        if range_attr:
            auto.range_start, auto.range_end = self._parse_range(range_attr)

        return auto

    def _parse_table_row(self, elem: ET.Element) -> ParsedTableRow:
        """Parse a <Row> element."""
        row = ParsedTableRow(
            row_index=int(elem.get("r", 0)),
            classes=parse_class_string(elem.get("class", "")),
        )

        for child in elem:
            if child.tag == "Cell":
                row.cells.append(self._parse_table_cell(child))

        return row

    def _parse_table_cell(self, elem: ET.Element) -> ParsedTableCell:
        """Parse a <Cell> element."""
        cell = ParsedTableCell(
            id=elem.get("id", ""),
            row=int(elem.get("r", 0)),
            col=int(elem.get("c", 0)),
            rowspan=int(elem.get("rowspan", 1)),
            colspan=int(elem.get("colspan", 1)),
            classes=parse_class_string(elem.get("class", "")),
        )

        # Parse text content in cell
        for child in elem:
            if child.tag == "P":
                cell.paragraphs.append(self._parse_paragraph(child))

        return cell

    def _parse_range(self, range_str: str) -> tuple[int, int]:
        """Parse a range string like '0-12' into (start, end) tuple."""
        if match := re.match(r"^(\d+)-(\d+)$", range_str):
            return int(match.group(1)), int(match.group(2))
        raise SMLParseError(f"Invalid range format: '{range_str}'")


# ============================================================================
# Public API
# ============================================================================


def parse_sml(sml: str, strict: bool = True) -> ParsedPresentation:
    """Parse SML string into a ParsedPresentation.

    Args:
        sml: SML string.
        strict: If True, validate SML constraints strictly.

    Returns:
        ParsedPresentation object.

    Raises:
        SMLParseError: If parsing fails.
        SMLValidationError: If SML violates constraints.
    """
    parser = SMLParser(strict=strict)
    return parser.parse(sml)


def parse_element(sml: str, strict: bool = True) -> ParsedElement:
    """Parse a single SML element.

    Useful for parsing individual elements outside a full presentation.

    Args:
        sml: SML element string (e.g., '<TextBox>...</TextBox>').
        strict: If True, validate SML constraints strictly.

    Returns:
        ParsedElement object.

    Raises:
        SMLParseError: If parsing fails.
    """
    try:
        elem = ET.fromstring(sml)
    except ET.ParseError as e:
        raise SMLParseError(f"Invalid XML: {e}") from e

    parser = SMLParser(strict=strict)
    return parser._parse_element(elem)
