"""Dataclass models representing the XML structure for document.xml and index.xml.

These models are the intermediate representation between Google Docs API
Document objects and the on-disk XML files.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from xml.etree.ElementTree import Element, SubElement, fromstring

from ._utils import element_to_string

if TYPE_CHECKING:
    from ._styles import StylesXml
    from ._tab_extras import (
        DocStyleXml,
        InlineObjectsXml,
        NamedRangesXml,
        NamedStylesXml,
        PositionedObjectsXml,
    )

# ---------------------------------------------------------------------------
# Index models (index.xml)
# ---------------------------------------------------------------------------


@dataclass
class IndexHeading:
    """A heading in the document outline."""

    tag: str  # title, subtitle, h1, h2, h3
    text: str


@dataclass
class IndexTab:
    """A tab entry in the index."""

    id: str
    title: str
    folder: str
    headings: list[IndexHeading] = field(default_factory=list)
    parent_tab_id: str | None = None
    nesting_level: int | None = None
    icon_emoji: str | None = None
    child_tabs: list[IndexTab] = field(default_factory=list)


@dataclass
class IndexXml:
    """Root model for index.xml."""

    id: str
    title: str
    revision: str | None = None
    tabs: list[IndexTab] = field(default_factory=list)

    def to_element(self) -> Element:
        root = Element("doc")
        root.set("id", self.id)
        root.set("title", self.title)
        if self.revision:
            root.set("revision", self.revision)
        for tab in self.tabs:
            _index_tab_to_element(tab, root)
        return root

    def to_xml_string(self) -> str:
        return element_to_string(self.to_element())

    @classmethod
    def from_element(cls, root: Element) -> IndexXml:
        tabs: list[IndexTab] = []
        for tab_elem in root.findall("tab"):
            tabs.append(_index_tab_from_element(tab_elem))
        return cls(
            id=root.get("id", ""),
            title=root.get("title", ""),
            revision=root.get("revision"),
            tabs=tabs,
        )

    @classmethod
    def from_xml_string(cls, xml: str) -> IndexXml:
        return cls.from_element(fromstring(xml))

    def all_tabs_flat(self) -> list[IndexTab]:
        """Return all tabs flattened (top-level + nested children)."""
        result: list[IndexTab] = []
        for tab in self.tabs:
            _collect_tabs(tab, result)
        return result


def _index_tab_to_element(tab: IndexTab, parent: Element) -> None:
    """Serialize an IndexTab (and its children) to XML."""
    tab_elem = SubElement(parent, "tab")
    tab_elem.set("id", tab.id)
    tab_elem.set("title", tab.title)
    tab_elem.set("folder", tab.folder)
    if tab.parent_tab_id:
        tab_elem.set("parentTabId", tab.parent_tab_id)
    if tab.nesting_level is not None:
        tab_elem.set("nestingLevel", str(tab.nesting_level))
    if tab.icon_emoji:
        tab_elem.set("iconEmoji", tab.icon_emoji)
    for h in tab.headings:
        h_elem = SubElement(tab_elem, h.tag)
        h_elem.text = h.text
    for child_tab in tab.child_tabs:
        _index_tab_to_element(child_tab, tab_elem)


def _index_tab_from_element(tab_elem: Element) -> IndexTab:
    """Parse an IndexTab (and its children) from XML."""
    headings: list[IndexHeading] = []
    child_tabs: list[IndexTab] = []
    for child in tab_elem:
        if child.tag in ("title", "subtitle", "h1", "h2", "h3"):
            headings.append(IndexHeading(tag=child.tag, text=child.text or ""))
        elif child.tag == "tab":
            child_tabs.append(_index_tab_from_element(child))
    nl_str = tab_elem.get("nestingLevel")
    return IndexTab(
        id=tab_elem.get("id", ""),
        title=tab_elem.get("title", ""),
        folder=tab_elem.get("folder", ""),
        headings=headings,
        parent_tab_id=tab_elem.get("parentTabId"),
        nesting_level=int(nl_str) if nl_str is not None else None,
        icon_emoji=tab_elem.get("iconEmoji"),
        child_tabs=child_tabs,
    )


def _collect_tabs(tab: IndexTab, result: list[IndexTab]) -> None:
    """Collect all tabs recursively into a flat list."""
    result.append(tab)
    for child in tab.child_tabs:
        _collect_tabs(child, result)


# ---------------------------------------------------------------------------
# Inline models (content within paragraphs)
# ---------------------------------------------------------------------------


@dataclass
class TNode:
    """<t> — a text run, optionally with a class and/or sugar tag.

    Examples:
        <t>plain text</t>
        <t class="s1">styled text</t>
        <t><b>bold text</b></t>
        <t class="s1"><i>italic + styled text</i></t>
    """

    text: str
    class_name: str | None = None
    sugar_tag: str | None = None  # b, i, u, s, sup, sub


@dataclass
class LinkNode:
    """<a href="..."> — a hyperlink."""

    href: str
    children: list[TNode] = field(default_factory=list)
    class_name: str | None = None
    link_type: str | None = None  # "link", "linkBookmark", "linkHeading", "linkTab"


@dataclass
class ImageNode:
    """<image objectId="..."/> — an inline image."""

    object_id: str


@dataclass
class FootnoteRefNode:
    """<footnoteref id="..."/> — a footnote reference."""

    id: str


@dataclass
class PersonNode:
    """<person email="..."/> — a person mention."""

    email: str
    name: str | None = None
    person_id: str | None = None


@dataclass
class DateNode:
    """<date/> — a date element."""

    date_id: str | None = None
    timestamp: str | None = None
    date_format: str | None = None
    time_format: str | None = None
    locale: str | None = None
    time_zone_id: str | None = None
    display_text: str | None = None


@dataclass
class RichLinkNode:
    """<richlink url="..."/> — a rich link (chip)."""

    url: str
    title: str | None = None
    mime_type: str | None = None


@dataclass
class AutoTextNode:
    """<autotext/> — auto text (page number, etc.)."""

    type: str | None = None


@dataclass
class EquationNode:
    """<equation/> — an equation."""

    pass


@dataclass
class ColumnBreakNode:
    """<columnbreak/> — a column break."""

    pass


@dataclass
class SoftBreakNode:
    """<br/> — a soft line break (\\x0b / Shift+Enter in Google Docs)."""

    pass


InlineNode = (
    TNode
    | LinkNode
    | ImageNode
    | FootnoteRefNode
    | PersonNode
    | DateNode
    | RichLinkNode
    | AutoTextNode
    | EquationNode
    | ColumnBreakNode
    | SoftBreakNode
)


# ---------------------------------------------------------------------------
# Block models (structural elements)
# ---------------------------------------------------------------------------


@dataclass
class ParagraphXml:
    """<p>, <h1>-<h6>, <title>, <subtitle>, or <li>."""

    tag: str  # p, h1..h6, title, subtitle, li
    inlines: list[InlineNode] = field(default_factory=list)
    class_name: str | None = None
    heading_id: str | None = None
    # For <li> elements:
    parent: str | None = None
    level: int | None = None


@dataclass
class ColXml:
    """<col/> — table column definition."""

    class_name: str | None = None


@dataclass
class CellXml:
    """<td> — table cell."""

    blocks: list[BlockNode] = field(default_factory=list)
    class_name: str | None = None
    colspan: int | None = None
    rowspan: int | None = None


@dataclass
class RowXml:
    """<tr> — table row."""

    cells: list[CellXml] = field(default_factory=list)
    class_name: str | None = None


@dataclass
class TableXml:
    """<table> — a table."""

    cols: list[ColXml] = field(default_factory=list)
    rows: list[RowXml] = field(default_factory=list)
    class_name: str | None = None


@dataclass
class HrXml:
    """<hr/> — horizontal rule."""

    pass


@dataclass
class PageBreakXml:
    """<pagebreak/> — page break."""

    pass


@dataclass
class SectionBreakXml:
    """<sectionbreak/> — section break."""

    # SectionStyle fields (stored as JSON string for complex types)
    section_type: str | None = None
    content_direction: str | None = None
    default_header_id: str | None = None
    default_footer_id: str | None = None
    first_page_header_id: str | None = None
    first_page_footer_id: str | None = None
    even_page_header_id: str | None = None
    even_page_footer_id: str | None = None
    use_first_page_header_footer: bool | None = None
    flip_page_orientation: bool | None = None
    page_number_start: int | None = None
    margin_top: str | None = None
    margin_bottom: str | None = None
    margin_left: str | None = None
    margin_right: str | None = None
    margin_header: str | None = None
    margin_footer: str | None = None
    column_properties: str | None = None  # JSON-encoded list
    column_separator_style: str | None = None


@dataclass
class TocXml:
    """<toc> — table of contents."""

    blocks: list[BlockNode] = field(default_factory=list)


BlockNode = ParagraphXml | TableXml | HrXml | PageBreakXml | SectionBreakXml | TocXml


# ---------------------------------------------------------------------------
# Document models (document.xml)
# ---------------------------------------------------------------------------


@dataclass
class TabFiles:
    """All files for a single tab folder."""

    tab: TabXml
    styles: StylesXml
    doc_style: DocStyleXml | None = None
    named_styles: NamedStylesXml | None = None
    inline_objects: InlineObjectsXml | None = None
    positioned_objects: PositionedObjectsXml | None = None
    named_ranges: NamedRangesXml | None = None


@dataclass
class LevelDefXml:
    """<level> within a <list> definition."""

    index: int
    glyph_type: str | None = None
    glyph_format: str | None = None
    glyph_symbol: str | None = None
    bullet_alignment: str | None = None
    start_number: int | None = None
    class_name: str | None = None


@dataclass
class ListDefXml:
    """<list id="..."> — a list definition."""

    id: str
    levels: list[LevelDefXml] = field(default_factory=list)


@dataclass
class SegmentXml:
    """A header, footer, or footnote segment."""

    id: str
    segment_type: str  # "header", "footer", "footnote"
    blocks: list[BlockNode] = field(default_factory=list)


@dataclass
class TabXml:
    """Root model for a per-tab document.xml."""

    id: str
    title: str
    index: int | None = None
    lists: list[ListDefXml] = field(default_factory=list)
    body: list[BlockNode] = field(default_factory=list)
    headers: list[SegmentXml] = field(default_factory=list)
    footers: list[SegmentXml] = field(default_factory=list)
    footnotes: list[SegmentXml] = field(default_factory=list)

    def to_element(self) -> Element:
        root = Element("tab")
        root.set("id", self.id)
        root.set("title", self.title)
        if self.index is not None:
            root.set("index", str(self.index))
        if self.lists:
            lists_elem = SubElement(root, "lists")
            for lst in self.lists:
                _list_def_to_element(lst, lists_elem)
        body_elem = SubElement(root, "body")
        for block in self.body:
            _block_to_element(block, body_elem)
        for seg in self.headers:
            _segment_to_element(seg, root)
        for seg in self.footers:
            _segment_to_element(seg, root)
        for seg in self.footnotes:
            _segment_to_element(seg, root)
        return root

    def to_xml_string(self) -> str:
        return element_to_string(self.to_element())

    @classmethod
    def from_element(cls, root: Element) -> TabXml:
        index_str = root.get("index")
        tab = cls(
            id=root.get("id", ""),
            title=root.get("title", ""),
            index=int(index_str) if index_str is not None else None,
        )
        lists_elem = root.find("lists")
        if lists_elem is not None:
            for list_elem in lists_elem.findall("list"):
                tab.lists.append(_list_def_from_element(list_elem))
        body_elem = root.find("body")
        if body_elem is not None:
            tab.body = _blocks_from_element(body_elem)
        for seg_elem in root.findall("header"):
            tab.headers.append(_segment_from_element(seg_elem, "header"))
        for seg_elem in root.findall("footer"):
            tab.footers.append(_segment_from_element(seg_elem, "footer"))
        for seg_elem in root.findall("footnote"):
            tab.footnotes.append(_segment_from_element(seg_elem, "footnote"))
        return tab

    @classmethod
    def from_xml_string(cls, xml: str) -> TabXml:
        return cls.from_element(fromstring(xml))


# ---------------------------------------------------------------------------
# Element serialization helpers
# ---------------------------------------------------------------------------

_SUGAR_TAGS = frozenset({"b", "i", "u", "s", "sup", "sub"})
_HEADING_TAGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6", "title", "subtitle"})
_BLOCK_TAGS = frozenset(
    {"p", "h1", "h2", "h3", "h4", "h5", "h6", "title", "subtitle", "li"}
)


def _inline_to_element(node: InlineNode, parent: Element) -> None:
    """Append an inline node as a child Element."""
    if isinstance(node, TNode):
        t = SubElement(parent, "t")
        if node.class_name:
            t.set("class", node.class_name)
        if node.sugar_tag:
            sugar = SubElement(t, node.sugar_tag)
            sugar.text = node.text
        else:
            t.text = node.text
    elif isinstance(node, LinkNode):
        elem = SubElement(parent, "a")
        elem.set("href", node.href)
        if node.class_name:
            elem.set("class", node.class_name)
        if node.link_type and node.link_type != "link":
            elem.set("linkType", node.link_type)
        for child in node.children:
            t = SubElement(elem, "t")
            t.text = child.text
    elif isinstance(node, ImageNode):
        elem = SubElement(parent, "image")
        elem.set("objectId", node.object_id)
    elif isinstance(node, FootnoteRefNode):
        elem = SubElement(parent, "footnoteref")
        elem.set("id", node.id)
    elif isinstance(node, PersonNode):
        elem = SubElement(parent, "person")
        elem.set("email", node.email)
        if node.name:
            elem.set("name", node.name)
        if node.person_id:
            elem.set("personId", node.person_id)
    elif isinstance(node, DateNode):
        elem = SubElement(parent, "date")
        if node.date_id:
            elem.set("dateId", node.date_id)
        if node.timestamp:
            elem.set("timestamp", node.timestamp)
        if node.date_format:
            elem.set("dateFormat", node.date_format)
        if node.time_format:
            elem.set("timeFormat", node.time_format)
        if node.locale:
            elem.set("locale", node.locale)
        if node.time_zone_id:
            elem.set("timeZoneId", node.time_zone_id)
        if node.display_text:
            elem.set("displayText", node.display_text)
    elif isinstance(node, RichLinkNode):
        elem = SubElement(parent, "richlink")
        elem.set("url", node.url)
        if node.title:
            elem.set("title", node.title)
        if node.mime_type:
            elem.set("mimeType", node.mime_type)
    elif isinstance(node, AutoTextNode):
        elem = SubElement(parent, "autotext")
        if node.type:
            elem.set("type", node.type)
    elif isinstance(node, EquationNode):
        SubElement(parent, "equation")
    elif isinstance(node, ColumnBreakNode):
        SubElement(parent, "columnbreak")
    elif isinstance(node, SoftBreakNode):
        SubElement(parent, "br")


def _block_to_element(block: BlockNode, parent: Element) -> None:
    """Append a block node as a child Element."""
    if isinstance(block, ParagraphXml):
        elem = SubElement(parent, block.tag)
        if block.class_name:
            elem.set("class", block.class_name)
        if block.heading_id and block.tag in _HEADING_TAGS:
            elem.set("headingId", block.heading_id)
        if block.tag == "li":
            if block.parent:
                elem.set("parent", block.parent)
            if block.level is not None:
                elem.set("level", str(block.level))
        for inline in block.inlines:
            _inline_to_element(inline, elem)
    elif isinstance(block, TableXml):
        elem = SubElement(parent, "table")
        if block.class_name:
            elem.set("class", block.class_name)
        for col in block.cols:
            col_elem = SubElement(elem, "col")
            if col.class_name:
                col_elem.set("class", col.class_name)
        for row in block.rows:
            tr = SubElement(elem, "tr")
            if row.class_name:
                tr.set("class", row.class_name)
            for cell in row.cells:
                td = SubElement(tr, "td")
                if cell.class_name:
                    td.set("class", cell.class_name)
                if cell.colspan is not None and cell.colspan > 1:
                    td.set("colspan", str(cell.colspan))
                if cell.rowspan is not None and cell.rowspan > 1:
                    td.set("rowspan", str(cell.rowspan))
                for child_block in cell.blocks:
                    _block_to_element(child_block, td)
    elif isinstance(block, HrXml):
        SubElement(parent, "hr")
    elif isinstance(block, PageBreakXml):
        SubElement(parent, "pagebreak")
    elif isinstance(block, SectionBreakXml):
        elem = SubElement(parent, "sectionbreak")
        _section_break_attrs = {
            "sectionType": block.section_type,
            "contentDirection": block.content_direction,
            "defaultHeaderId": block.default_header_id,
            "defaultFooterId": block.default_footer_id,
            "firstPageHeaderId": block.first_page_header_id,
            "firstPageFooterId": block.first_page_footer_id,
            "evenPageHeaderId": block.even_page_header_id,
            "evenPageFooterId": block.even_page_footer_id,
            "marginTop": block.margin_top,
            "marginBottom": block.margin_bottom,
            "marginLeft": block.margin_left,
            "marginRight": block.margin_right,
            "marginHeader": block.margin_header,
            "marginFooter": block.margin_footer,
            "columnProperties": block.column_properties,
            "columnSeparatorStyle": block.column_separator_style,
        }
        for k, v in _section_break_attrs.items():
            if v is not None:
                elem.set(k, v)
        if block.use_first_page_header_footer is not None:
            elem.set(
                "useFirstPageHeaderFooter",
                str(block.use_first_page_header_footer).lower(),
            )
        if block.flip_page_orientation is not None:
            elem.set(
                "flipPageOrientation",
                str(block.flip_page_orientation).lower(),
            )
        if block.page_number_start is not None:
            elem.set("pageNumberStart", str(block.page_number_start))
    elif isinstance(block, TocXml):
        elem = SubElement(parent, "toc")
        for child_block in block.blocks:
            _block_to_element(child_block, elem)


def _list_def_to_element(lst: ListDefXml, parent: Element) -> None:
    """Append a list definition as a child Element."""
    elem = SubElement(parent, "list")
    elem.set("id", lst.id)
    for level in lst.levels:
        lv = SubElement(elem, "level")
        lv.set("index", str(level.index))
        if level.glyph_type:
            lv.set("glyphType", level.glyph_type)
        if level.glyph_format:
            lv.set("glyphFormat", level.glyph_format)
        if level.glyph_symbol:
            lv.set("glyphSymbol", level.glyph_symbol)
        if level.bullet_alignment:
            lv.set("bulletAlignment", level.bullet_alignment)
        if level.start_number is not None:
            lv.set("startNumber", str(level.start_number))
        if level.class_name:
            lv.set("class", level.class_name)


def _segment_to_element(seg: SegmentXml, parent: Element) -> None:
    """Append a segment (header/footer/footnote) as a child Element."""
    elem = SubElement(parent, seg.segment_type)
    elem.set("id", seg.id)
    for block in seg.blocks:
        _block_to_element(block, elem)


# ---------------------------------------------------------------------------
# Element deserialization helpers
# ---------------------------------------------------------------------------


def _inlines_from_element(parent: Element) -> list[InlineNode]:
    """Parse inline nodes from a paragraph-like element's children."""
    inlines: list[InlineNode] = []
    for child in parent:
        tag = child.tag
        if tag == "t":
            class_name = child.get("class")
            # Check for sugar tag child (e.g. <t><b>text</b></t>)
            sugar_tag = None
            text = child.text or ""
            for sub in child:
                if sub.tag in _SUGAR_TAGS:
                    sugar_tag = sub.tag
                    text = sub.text or ""
                    break
            inlines.append(TNode(text=text, class_name=class_name, sugar_tag=sugar_tag))
        elif tag == "br":
            inlines.append(SoftBreakNode())
        elif tag == "a":
            t_nodes = [TNode(text=t.text or "") for t in child.findall("t")]
            inlines.append(
                LinkNode(
                    href=child.get("href", ""),
                    children=t_nodes,
                    class_name=child.get("class"),
                    link_type=child.get("linkType"),
                )
            )
        elif tag == "image":
            inlines.append(ImageNode(object_id=child.get("objectId", "")))
        elif tag == "footnoteref":
            inlines.append(FootnoteRefNode(id=child.get("id", "")))
        elif tag == "person":
            inlines.append(
                PersonNode(
                    email=child.get("email", ""),
                    name=child.get("name"),
                    person_id=child.get("personId"),
                )
            )
        elif tag == "date":
            inlines.append(
                DateNode(
                    date_id=child.get("dateId"),
                    timestamp=child.get("timestamp"),
                    date_format=child.get("dateFormat"),
                    time_format=child.get("timeFormat"),
                    locale=child.get("locale"),
                    time_zone_id=child.get("timeZoneId"),
                    display_text=child.get("displayText"),
                )
            )
        elif tag == "richlink":
            inlines.append(
                RichLinkNode(
                    url=child.get("url", ""),
                    title=child.get("title"),
                    mime_type=child.get("mimeType"),
                )
            )
        elif tag == "autotext":
            inlines.append(AutoTextNode(type=child.get("type")))
        elif tag == "equation":
            inlines.append(EquationNode())
        elif tag == "columnbreak":
            inlines.append(ColumnBreakNode())
    return inlines


def _blocks_from_element(parent: Element) -> list[BlockNode]:
    """Parse block nodes from a container element's children."""
    blocks: list[BlockNode] = []
    for child in parent:
        tag = child.tag
        if tag in _BLOCK_TAGS:
            para = ParagraphXml(tag=tag, inlines=_inlines_from_element(child))
            para.class_name = child.get("class")
            if tag in _HEADING_TAGS:
                para.heading_id = child.get("headingId")
            if tag == "li":
                para.parent = child.get("parent")
                level_str = child.get("level")
                para.level = int(level_str) if level_str is not None else None
            blocks.append(para)
        elif tag == "table":
            table = TableXml()
            table.class_name = child.get("class")
            for col_elem in child.findall("col"):
                table.cols.append(ColXml(class_name=col_elem.get("class")))
            for tr_elem in child.findall("tr"):
                row = RowXml(class_name=tr_elem.get("class"))
                for td_elem in tr_elem.findall("td"):
                    colspan_str = td_elem.get("colspan")
                    rowspan_str = td_elem.get("rowspan")
                    cell = CellXml(
                        blocks=_blocks_from_element(td_elem),
                        class_name=td_elem.get("class"),
                        colspan=int(colspan_str) if colspan_str else None,
                        rowspan=int(rowspan_str) if rowspan_str else None,
                    )
                    row.cells.append(cell)
                table.rows.append(row)
            blocks.append(table)
        elif tag == "hr":
            blocks.append(HrXml())
        elif tag == "pagebreak":
            blocks.append(PageBreakXml())
        elif tag == "sectionbreak":
            _pns = child.get("pageNumberStart")
            _ufp = child.get("useFirstPageHeaderFooter")
            _fpo = child.get("flipPageOrientation")
            blocks.append(
                SectionBreakXml(
                    section_type=child.get("sectionType"),
                    content_direction=child.get("contentDirection"),
                    default_header_id=child.get("defaultHeaderId"),
                    default_footer_id=child.get("defaultFooterId"),
                    first_page_header_id=child.get("firstPageHeaderId"),
                    first_page_footer_id=child.get("firstPageFooterId"),
                    even_page_header_id=child.get("evenPageHeaderId"),
                    even_page_footer_id=child.get("evenPageFooterId"),
                    use_first_page_header_footer=(
                        _ufp == "true" if _ufp is not None else None
                    ),
                    flip_page_orientation=(
                        _fpo == "true" if _fpo is not None else None
                    ),
                    page_number_start=(int(_pns) if _pns is not None else None),
                    margin_top=child.get("marginTop"),
                    margin_bottom=child.get("marginBottom"),
                    margin_left=child.get("marginLeft"),
                    margin_right=child.get("marginRight"),
                    margin_header=child.get("marginHeader"),
                    margin_footer=child.get("marginFooter"),
                    column_properties=child.get("columnProperties"),
                    column_separator_style=child.get("columnSeparatorStyle"),
                )
            )
        elif tag == "toc":
            blocks.append(TocXml(blocks=_blocks_from_element(child)))
    return blocks


def _list_def_from_element(elem: Element) -> ListDefXml:
    """Parse a <list> element into ListDefXml."""
    levels: list[LevelDefXml] = []
    for lv in elem.findall("level"):
        idx_str = lv.get("index", "0")
        start_str = lv.get("startNumber")
        levels.append(
            LevelDefXml(
                index=int(idx_str),
                glyph_type=lv.get("glyphType"),
                glyph_format=lv.get("glyphFormat"),
                glyph_symbol=lv.get("glyphSymbol"),
                bullet_alignment=lv.get("bulletAlignment"),
                start_number=int(start_str) if start_str is not None else None,
                class_name=lv.get("class"),
            )
        )
    return ListDefXml(id=elem.get("id", ""), levels=levels)


def _segment_from_element(elem: Element, segment_type: str) -> SegmentXml:
    """Parse a header/footer/footnote element into SegmentXml."""
    return SegmentXml(
        id=elem.get("id", ""),
        segment_type=segment_type,
        blocks=_blocks_from_element(elem),
    )
