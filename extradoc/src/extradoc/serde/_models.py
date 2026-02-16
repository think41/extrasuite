"""Dataclass models representing the XML structure for document.xml and index.xml.

These models are the intermediate representation between Google Docs API
Document objects and the on-disk XML files.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from xml.etree.ElementTree import Element, SubElement, fromstring

from ._utils import element_to_string

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
            tab_elem = SubElement(root, "tab")
            tab_elem.set("id", tab.id)
            tab_elem.set("title", tab.title)
            tab_elem.set("folder", tab.folder)
            for h in tab.headings:
                h_elem = SubElement(tab_elem, h.tag)
                h_elem.text = h.text
        return root

    def to_xml_string(self) -> str:
        return element_to_string(self.to_element())

    @classmethod
    def from_element(cls, root: Element) -> IndexXml:
        tabs: list[IndexTab] = []
        for tab_elem in root.findall("tab"):
            headings: list[IndexHeading] = []
            for child in tab_elem:
                if child.tag in ("title", "subtitle", "h1", "h2", "h3"):
                    headings.append(IndexHeading(tag=child.tag, text=child.text or ""))
            tabs.append(
                IndexTab(
                    id=tab_elem.get("id", ""),
                    title=tab_elem.get("title", ""),
                    folder=tab_elem.get("folder", ""),
                    headings=headings,
                )
            )
        return cls(
            id=root.get("id", ""),
            title=root.get("title", ""),
            revision=root.get("revision"),
            tabs=tabs,
        )

    @classmethod
    def from_xml_string(cls, xml: str) -> IndexXml:
        return cls.from_element(fromstring(xml))


# ---------------------------------------------------------------------------
# Inline models (content within paragraphs)
# ---------------------------------------------------------------------------


@dataclass
class TNode:
    """<t>text</t> — a plain text node."""

    text: str


@dataclass
class FormattingNode:
    """<b>, <i>, <u>, <s>, <sup>, <sub> — sugar formatting tag."""

    tag: str  # b, i, u, s, sup, sub
    children: list[TNode] = field(default_factory=list)
    class_name: str | None = None


@dataclass
class SpanNode:
    """<span class="..."> — styled text without a sugar tag."""

    class_name: str
    children: list[TNode] = field(default_factory=list)


@dataclass
class LinkNode:
    """<a href="..."> — a hyperlink."""

    href: str
    children: list[TNode] = field(default_factory=list)
    class_name: str | None = None


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


@dataclass
class DateNode:
    """<date/> — a date element."""

    pass


@dataclass
class RichLinkNode:
    """<richlink url="..."/> — a rich link (chip)."""

    url: str


@dataclass
class AutoTextNode:
    """<autotext/> — auto text (page number, etc.)."""

    pass


@dataclass
class EquationNode:
    """<equation/> — an equation."""

    pass


@dataclass
class ColumnBreakNode:
    """<columnbreak/> — a column break."""

    pass


InlineNode = (
    TNode
    | FormattingNode
    | SpanNode
    | LinkNode
    | ImageNode
    | FootnoteRefNode
    | PersonNode
    | DateNode
    | RichLinkNode
    | AutoTextNode
    | EquationNode
    | ColumnBreakNode
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

    pass


@dataclass
class TocXml:
    """<toc> — table of contents."""

    blocks: list[BlockNode] = field(default_factory=list)


BlockNode = ParagraphXml | TableXml | HrXml | PageBreakXml | SectionBreakXml | TocXml


# ---------------------------------------------------------------------------
# Document models (document.xml)
# ---------------------------------------------------------------------------


@dataclass
class LevelDefXml:
    """<level> within a <list> definition."""

    index: int
    glyph_type: str | None = None
    glyph_format: str | None = None
    glyph_symbol: str | None = None
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
    lists: list[ListDefXml] = field(default_factory=list)
    body: list[BlockNode] = field(default_factory=list)
    headers: list[SegmentXml] = field(default_factory=list)
    footers: list[SegmentXml] = field(default_factory=list)
    footnotes: list[SegmentXml] = field(default_factory=list)

    def to_element(self) -> Element:
        root = Element("tab")
        root.set("id", self.id)
        root.set("title", self.title)
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
        tab = cls(id=root.get("id", ""), title=root.get("title", ""))
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
        t.text = node.text
    elif isinstance(node, FormattingNode):
        elem = SubElement(parent, node.tag)
        if node.class_name:
            elem.set("class", node.class_name)
        for child in node.children:
            t = SubElement(elem, "t")
            t.text = child.text
    elif isinstance(node, SpanNode):
        elem = SubElement(parent, "span")
        elem.set("class", node.class_name)
        for child in node.children:
            t = SubElement(elem, "t")
            t.text = child.text
    elif isinstance(node, LinkNode):
        elem = SubElement(parent, "a")
        elem.set("href", node.href)
        if node.class_name:
            elem.set("class", node.class_name)
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
    elif isinstance(node, DateNode):
        SubElement(parent, "date")
    elif isinstance(node, RichLinkNode):
        elem = SubElement(parent, "richlink")
        elem.set("url", node.url)
    elif isinstance(node, AutoTextNode):
        SubElement(parent, "autotext")
    elif isinstance(node, EquationNode):
        SubElement(parent, "equation")
    elif isinstance(node, ColumnBreakNode):
        SubElement(parent, "columnbreak")


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
        SubElement(parent, "sectionbreak")
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
            inlines.append(TNode(text=child.text or ""))
        elif tag in _SUGAR_TAGS:
            t_nodes = [TNode(text=t.text or "") for t in child.findall("t")]
            inlines.append(
                FormattingNode(
                    tag=tag,
                    children=t_nodes,
                    class_name=child.get("class"),
                )
            )
        elif tag == "span":
            t_nodes = [TNode(text=t.text or "") for t in child.findall("t")]
            inlines.append(
                SpanNode(class_name=child.get("class", ""), children=t_nodes)
            )
        elif tag == "a":
            t_nodes = [TNode(text=t.text or "") for t in child.findall("t")]
            inlines.append(
                LinkNode(
                    href=child.get("href", ""),
                    children=t_nodes,
                    class_name=child.get("class"),
                )
            )
        elif tag == "image":
            inlines.append(ImageNode(object_id=child.get("objectId", "")))
        elif tag == "footnoteref":
            inlines.append(FootnoteRefNode(id=child.get("id", "")))
        elif tag == "person":
            inlines.append(PersonNode(email=child.get("email", "")))
        elif tag == "date":
            inlines.append(DateNode())
        elif tag == "richlink":
            inlines.append(RichLinkNode(url=child.get("url", "")))
        elif tag == "autotext":
            inlines.append(AutoTextNode())
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
            blocks.append(SectionBreakXml())
        elif tag == "toc":
            blocks.append(TocXml(blocks=_blocks_from_element(child)))
    return blocks


def _list_def_from_element(elem: Element) -> ListDefXml:
    """Parse a <list> element into ListDefXml."""
    levels: list[LevelDefXml] = []
    for lv in elem.findall("level"):
        idx_str = lv.get("index", "0")
        levels.append(
            LevelDefXml(
                index=int(idx_str),
                glyph_type=lv.get("glyphType"),
                glyph_format=lv.get("glyphFormat"),
                glyph_symbol=lv.get("glyphSymbol"),
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
