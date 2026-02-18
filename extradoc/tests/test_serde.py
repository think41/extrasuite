"""Tests for the serde module: Document ↔ XML round-trip."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from extradoc.api_types._generated import (
    AutoText,
    Body,
    Bullet,
    Color,
    ColumnBreak,
    DateElement,
    Dimension,
    DimensionUnit,
    Document,
    DocumentTab,
    Equation,
    Footer,
    Footnote,
    FootnoteReference,
    Header,
    HorizontalRule,
    InlineObjectElement,
    Link,
    ListProperties,
    NestingLevel,
    NestingLevelGlyphType,
    OptionalColor,
    PageBreak,
    Paragraph,
    ParagraphElement,
    ParagraphStyle,
    ParagraphStyleAlignment,
    ParagraphStyleNamedStyleType,
    Person,
    PersonProperties,
    RgbColor,
    RichLink,
    RichLinkProperties,
    SectionBreak,
    Shading,
    StructuralElement,
    Tab,
    Table,
    TableCell,
    TableCellStyle,
    TableOfContents,
    TableRow,
    TabProperties,
    TextRun,
    TextStyle,
    WeightedFontFamily,
)
from extradoc.api_types._generated import (
    List as DocList,
)
from extradoc.serde import (
    deserialize,
    from_document,
    serialize,
    to_document,
)
from extradoc.serde._models import (
    IndexHeading,
    IndexTab,
    IndexXml,
    ParagraphXml,
    TabXml,
    TNode,
)
from extradoc.serde._styles import (
    StyleCollector,
    StyleDef,
    StylesXml,
    extract_para_style,
    extract_text_style,
    resolve_para_style,
    resolve_text_style,
)
from extradoc.serde._utils import (
    dim_to_str,
    hex_to_optional_color,
    optional_color_to_hex,
    sanitize_tab_name,
    str_to_dim,
)

# ---------------------------------------------------------------------------
# Helper: build a minimal Document with paragraphs
# ---------------------------------------------------------------------------


def _make_para(
    text: str,
    named_style: ParagraphStyleNamedStyleType | None = None,
    text_style: TextStyle | None = None,
    heading_id: str | None = None,
    bullet: Bullet | None = None,
) -> StructuralElement:
    """Create a StructuralElement containing a paragraph."""
    ps = ParagraphStyle()
    if named_style:
        ps.named_style_type = named_style
    if heading_id:
        ps.heading_id = heading_id
    elements = [
        ParagraphElement(text_run=TextRun(content=text + "\n", text_style=text_style))
    ]
    return StructuralElement(
        paragraph=Paragraph(
            elements=elements,
            paragraph_style=ps,
            bullet=bullet,
        )
    )


def _make_doc(
    content: list[StructuralElement],
    doc_id: str = "test-doc",
    title: str = "Test Document",
    tab_id: str = "t.0",
    tab_title: str = "Tab 1",
    lists: dict[str, DocList] | None = None,
    headers: dict[str, Header] | None = None,
    footers: dict[str, Footer] | None = None,
    footnotes: dict[str, Footnote] | None = None,
) -> Document:
    """Create a minimal Document with a single tab."""
    doc_tab = DocumentTab(
        body=Body(content=content),
        lists=lists,
        headers=headers,
        footers=footers,
        footnotes=footnotes,
    )
    return Document(
        document_id=doc_id,
        title=title,
        tabs=[
            Tab(
                tab_properties=TabProperties(tab_id=tab_id, title=tab_title),
                document_tab=doc_tab,
            )
        ],
    )


# ===========================================================================
# Utility tests
# ===========================================================================


class TestUtils:
    def test_sanitize_tab_name(self) -> None:
        assert sanitize_tab_name("Tab 1") == "Tab_1"
        assert sanitize_tab_name("Appendix / References") == "Appendix_References"
        assert sanitize_tab_name("hello-world") == "hello-world"
        assert sanitize_tab_name("  ") == "untitled"

    def test_color_roundtrip(self) -> None:
        oc = OptionalColor(
            color=Color(rgb_color=RgbColor(red=1.0, green=0.0, blue=0.0))
        )
        hex_str = optional_color_to_hex(oc)
        assert hex_str == "#FF0000"
        oc2 = hex_to_optional_color(hex_str)
        assert oc2.color is not None
        assert oc2.color.rgb_color is not None
        assert abs((oc2.color.rgb_color.red or 0) - 1.0) < 0.01

    def test_dim_roundtrip(self) -> None:
        d = Dimension(magnitude=12.0, unit=DimensionUnit.PT)
        s = dim_to_str(d)
        assert s == "12.0pt"
        d2 = str_to_dim(s)
        assert d2 is not None
        assert d2.magnitude == 12.0


# ===========================================================================
# Style extraction and resolution tests
# ===========================================================================


class TestStyles:
    def test_text_style_roundtrip(self) -> None:
        ts = TextStyle(
            bold=True,
            italic=True,
            font_size=Dimension(magnitude=14.0, unit=DimensionUnit.PT),
            foreground_color=OptionalColor(
                color=Color(rgb_color=RgbColor(red=1.0, green=0.0, blue=0.0))
            ),
            weighted_font_family=WeightedFontFamily(font_family="Arial"),
        )
        attrs = extract_text_style(ts)
        assert attrs["bold"] == "true"
        assert attrs["italic"] == "true"
        assert attrs["size"] == "14.0pt"
        assert attrs["font"] == "Arial"
        assert attrs["color"] == "#FF0000"

        ts2 = resolve_text_style(attrs)
        assert ts2.bold is True
        assert ts2.italic is True
        assert ts2.font_size is not None
        assert ts2.font_size.magnitude == 14.0
        assert ts2.weighted_font_family is not None
        assert ts2.weighted_font_family.font_family == "Arial"

    def test_para_style_roundtrip(self) -> None:
        ps = ParagraphStyle(
            alignment=ParagraphStyleAlignment.CENTER,
            line_spacing=150.0,
            space_above=Dimension(magnitude=12.0, unit=DimensionUnit.PT),
            keep_with_next=True,
            shading=Shading(
                background_color=OptionalColor(
                    color=Color(rgb_color=RgbColor(red=0.0, green=1.0, blue=0.0))
                )
            ),
        )
        attrs = extract_para_style(ps)
        assert attrs["align"] == "CENTER"
        assert attrs["lineSpacing"] == "150.0"
        assert attrs["spaceAbove"] == "12.0pt"
        assert attrs["keepNext"] == "true"
        assert "bgColor" in attrs

        ps2 = resolve_para_style(attrs)
        assert ps2.alignment == ParagraphStyleAlignment.CENTER
        assert ps2.line_spacing == 150.0
        assert ps2.keep_with_next is True

    def test_style_collector(self) -> None:
        c = StyleCollector()
        name1 = c.add_text_style({"bold": "true"})
        name2 = c.add_text_style({"bold": "true"})
        name3 = c.add_text_style({"italic": "true"})
        assert name1 == name2  # Same style → same class
        assert name1 != name3  # Different style → different class
        assert name1 == "s1"
        assert name3 == "s2"

        styles = c.build()
        assert len(styles.text_styles) == 2

    def test_styles_xml_roundtrip(self) -> None:
        styles = StylesXml(
            text_styles=[
                StyleDef(class_name="s1", attrs={"bold": "true", "size": "12pt"})
            ],
            para_styles=[StyleDef(class_name="p1", attrs={"align": "CENTER"})],
        )
        xml = styles.to_xml_string()
        assert "<text" in xml
        assert "<para" in xml

        styles2 = StylesXml.from_xml_string(xml)
        assert len(styles2.text_styles) == 1
        assert styles2.text_styles[0].class_name == "s1"
        assert styles2.text_styles[0].attrs["bold"] == "true"


# ===========================================================================
# Model XML roundtrip tests
# ===========================================================================


class TestModels:
    def test_tab_xml_roundtrip(self) -> None:
        tab = TabXml(
            id="t.0",
            title="Tab 1",
            body=[
                ParagraphXml(
                    tag="h1", inlines=[TNode(text="Hello")], heading_id="h.abc"
                ),
                ParagraphXml(
                    tag="p",
                    inlines=[
                        TNode(text="Plain "),
                        TNode(text="bold", sugar_tag="b"),
                    ],
                ),
            ],
        )
        xml = tab.to_xml_string()
        assert "<h1" in xml
        assert "headingId" in xml
        assert "<t>Hello</t>" in xml
        assert "<b>bold</b>" in xml

        tab2 = TabXml.from_xml_string(xml)
        assert tab2.id == "t.0"
        assert len(tab2.body) == 2
        first = tab2.body[0]
        assert isinstance(first, ParagraphXml)
        assert first.tag == "h1"
        assert first.heading_id == "h.abc"

        # Verify sugar tag round-trip
        second = tab2.body[1]
        assert isinstance(second, ParagraphXml)
        assert len(second.inlines) == 2
        bold_node = second.inlines[1]
        assert isinstance(bold_node, TNode)
        assert bold_node.sugar_tag == "b"
        assert bold_node.text == "bold"

    def test_index_xml_roundtrip(self) -> None:
        index = IndexXml(
            id="doc-1",
            title="My Doc",
            revision="rev1",
            tabs=[
                IndexTab(
                    id="t.0",
                    title="Tab 1",
                    folder="Tab_1",
                    headings=[
                        IndexHeading(tag="title", text="Document Title"),
                        IndexHeading(tag="h1", text="Introduction"),
                    ],
                )
            ],
        )
        xml = index.to_xml_string()
        assert 'id="doc-1"' in xml

        index2 = IndexXml.from_xml_string(xml)
        assert index2.id == "doc-1"
        assert len(index2.tabs) == 1
        assert len(index2.tabs[0].headings) == 2
        assert index2.tabs[0].headings[0].text == "Document Title"


# ===========================================================================
# Document → XML → Document round-trip tests
# ===========================================================================


class TestRoundTrip:
    def test_simple_paragraphs(self) -> None:
        """Plain text paragraphs survive round-trip."""
        doc = _make_doc(
            [
                _make_para("Hello world"),
                _make_para("Second paragraph"),
            ]
        )
        _index, tabs = from_document(doc)
        doc2 = to_document(tabs, document_id="test-doc", title="Test Document")
        _assert_text_content(doc2, ["Hello world", "Second paragraph"])

    def test_heading_roundtrip(self) -> None:
        """Headings preserve tag and heading ID."""
        doc = _make_doc(
            [
                _make_para(
                    "My Title",
                    named_style=ParagraphStyleNamedStyleType.HEADING_1,
                    heading_id="h.123",
                ),
                _make_para("Body text"),
            ]
        )
        _index, tabs = from_document(doc)
        doc2 = to_document(tabs)

        tab = doc2.tabs[0]  # type: ignore
        dt = tab.document_tab
        assert dt and dt.body and dt.body.content
        first_para = dt.body.content[0].paragraph
        assert first_para is not None
        assert first_para.paragraph_style is not None
        assert (
            first_para.paragraph_style.named_style_type
            == ParagraphStyleNamedStyleType.HEADING_1
        )
        assert first_para.paragraph_style.heading_id == "h.123"

    def test_styled_text_roundtrip(self) -> None:
        """Bold/italic text survives round-trip."""
        ts = TextStyle(bold=True)
        doc = _make_doc(
            [
                _make_para("Bold text", text_style=ts),
            ]
        )
        _index, tabs = from_document(doc)
        doc2 = to_document(tabs)

        tab = doc2.tabs[0]  # type: ignore
        dt = tab.document_tab
        assert dt and dt.body and dt.body.content
        first_para = dt.body.content[0].paragraph
        assert first_para is not None
        elements = first_para.elements or []
        # First element should be the text run (not the trailing \n)
        text_run = elements[0].text_run
        assert text_run is not None
        assert text_run.text_style is not None
        assert text_run.text_style.bold is True

    def test_list_roundtrip(self) -> None:
        """List items with bullets survive round-trip."""
        lists = {
            "kix.list1": DocList(
                list_properties=ListProperties(
                    nesting_levels=[
                        NestingLevel(
                            glyph_type=NestingLevelGlyphType.DECIMAL,
                            glyph_format="%0.",
                        ),
                    ]
                )
            )
        }
        doc = _make_doc(
            [
                _make_para(
                    "First item",
                    bullet=Bullet(list_id="kix.list1", nesting_level=0),
                ),
                _make_para(
                    "Second item",
                    bullet=Bullet(list_id="kix.list1", nesting_level=0),
                ),
            ],
            lists=lists,
        )
        _index, tabs = from_document(doc)
        doc2 = to_document(tabs)

        tab = doc2.tabs[0]  # type: ignore
        dt = tab.document_tab
        assert dt is not None

        # Check lists were preserved
        assert dt.lists is not None
        assert "kix.list1" in dt.lists
        nl = dt.lists["kix.list1"].list_properties
        assert nl is not None and nl.nesting_levels
        assert nl.nesting_levels[0].glyph_type == NestingLevelGlyphType.DECIMAL

        # Check bullets on paragraphs
        assert dt.body and dt.body.content
        first = dt.body.content[0].paragraph
        assert first is not None and first.bullet is not None
        assert first.bullet.list_id == "kix.list1"
        assert first.bullet.nesting_level == 0

    def test_table_roundtrip(self) -> None:
        """Simple table survives round-trip."""
        table = Table(
            rows=2,
            columns=2,
            table_rows=[
                TableRow(
                    table_cells=[
                        TableCell(
                            content=[_make_para("A")],
                            table_cell_style=TableCellStyle(),
                        ),
                        TableCell(
                            content=[_make_para("B")],
                            table_cell_style=TableCellStyle(),
                        ),
                    ]
                ),
                TableRow(
                    table_cells=[
                        TableCell(
                            content=[_make_para("C")],
                            table_cell_style=TableCellStyle(),
                        ),
                        TableCell(
                            content=[_make_para("D")],
                            table_cell_style=TableCellStyle(),
                        ),
                    ]
                ),
            ],
        )
        doc = _make_doc([StructuralElement(table=table)])
        _index, tabs = from_document(doc)
        doc2 = to_document(tabs)

        tab = doc2.tabs[0]  # type: ignore
        dt = tab.document_tab
        assert dt and dt.body and dt.body.content
        se = dt.body.content[0]
        assert se.table is not None
        assert se.table.rows == 2
        assert se.table.columns == 2

    def test_header_footer_roundtrip(self) -> None:
        """Headers and footers survive round-trip."""
        doc = _make_doc(
            [_make_para("Body text")],
            headers={
                "kix.h1": Header(
                    header_id="kix.h1",
                    content=[_make_para("Header text")],
                )
            },
            footers={
                "kix.f1": Footer(
                    footer_id="kix.f1",
                    content=[_make_para("Footer text")],
                )
            },
        )
        _index, tabs = from_document(doc)
        doc2 = to_document(tabs)

        tab = doc2.tabs[0]  # type: ignore
        dt = tab.document_tab
        assert dt is not None
        assert dt.headers and "kix.h1" in dt.headers
        assert dt.footers and "kix.f1" in dt.footers

    def test_index_generation(self) -> None:
        """Index includes heading outline."""
        doc = _make_doc(
            [
                _make_para("My Title", named_style=ParagraphStyleNamedStyleType.TITLE),
                _make_para(
                    "Introduction", named_style=ParagraphStyleNamedStyleType.HEADING_1
                ),
                _make_para("Body text"),
                _make_para(
                    "Methods", named_style=ParagraphStyleNamedStyleType.HEADING_1
                ),
            ]
        )
        index, _tabs = from_document(doc)
        assert index.id == "test-doc"
        assert len(index.tabs) == 1
        headings = index.tabs[0].headings
        assert len(headings) == 3
        assert headings[0].tag == "title"
        assert headings[0].text == "My Title"
        assert headings[1].tag == "h1"
        assert headings[1].text == "Introduction"

    def test_link_roundtrip(self) -> None:
        """Links survive round-trip."""

        ts = TextStyle(link=Link(url="https://example.com"))
        doc = _make_doc([_make_para("Click here", text_style=ts)])
        _index, tabs = from_document(doc)
        doc2 = to_document(tabs)

        tab = doc2.tabs[0]  # type: ignore
        dt = tab.document_tab
        assert dt and dt.body and dt.body.content
        para = dt.body.content[0].paragraph
        assert para and para.elements
        tr = para.elements[0].text_run
        assert tr and tr.text_style and tr.text_style.link
        assert tr.text_style.link.url == "https://example.com"

    def test_footnote_roundtrip(self) -> None:
        """Footnotes survive round-trip."""
        doc = _make_doc(
            [_make_para("Body with footnote")],
            footnotes={
                "kix.fn1": Footnote(
                    footnote_id="kix.fn1",
                    content=[_make_para("Footnote text")],
                )
            },
        )
        _index, tabs = from_document(doc)
        doc2 = to_document(tabs)

        tab = doc2.tabs[0]  # type: ignore
        dt = tab.document_tab
        assert dt is not None
        assert dt.footnotes and "kix.fn1" in dt.footnotes

    def test_section_break_roundtrip(self) -> None:
        """Section breaks survive round-trip."""
        content = [
            StructuralElement(section_break=SectionBreak()),
            _make_para("After section break"),
        ]
        doc = _make_doc(content)
        _index, tabs = from_document(doc)
        doc2 = to_document(tabs)

        tab = doc2.tabs[0]  # type: ignore
        dt = tab.document_tab
        assert dt and dt.body and dt.body.content
        assert dt.body.content[0].section_break is not None

    def test_nested_list_roundtrip(self) -> None:
        """Multi-level nested lists survive round-trip."""
        lists = {
            "kix.list1": DocList(
                list_properties=ListProperties(
                    nesting_levels=[
                        NestingLevel(
                            glyph_type=NestingLevelGlyphType.DECIMAL,
                            glyph_format="%0.",
                        ),
                        NestingLevel(
                            glyph_type=NestingLevelGlyphType.ALPHA,
                            glyph_format="%1.",
                        ),
                    ]
                )
            )
        }
        doc = _make_doc(
            [
                _make_para(
                    "Top level",
                    bullet=Bullet(list_id="kix.list1", nesting_level=0),
                ),
                _make_para(
                    "Nested item",
                    bullet=Bullet(list_id="kix.list1", nesting_level=1),
                ),
            ],
            lists=lists,
        )
        _index, tabs = from_document(doc)
        doc2 = to_document(tabs)

        tab = doc2.tabs[0]  # type: ignore
        dt = tab.document_tab
        assert dt and dt.lists and "kix.list1" in dt.lists
        nl = dt.lists["kix.list1"].list_properties
        assert nl and nl.nesting_levels and len(nl.nesting_levels) == 2
        assert nl.nesting_levels[0].glyph_type == NestingLevelGlyphType.DECIMAL
        assert nl.nesting_levels[1].glyph_type == NestingLevelGlyphType.ALPHA

        assert dt.body and dt.body.content
        nested = dt.body.content[1].paragraph
        assert nested and nested.bullet
        assert nested.bullet.nesting_level == 1

    def test_mixed_inline_roundtrip(self) -> None:
        """Paragraph with bold, italic, and link runs survives round-trip."""
        content = [
            StructuralElement(
                paragraph=Paragraph(
                    elements=[
                        ParagraphElement(
                            text_run=TextRun(
                                content="bold ",
                                text_style=TextStyle(bold=True),
                            )
                        ),
                        ParagraphElement(
                            text_run=TextRun(
                                content="italic ",
                                text_style=TextStyle(italic=True),
                            )
                        ),
                        ParagraphElement(
                            text_run=TextRun(
                                content="link",
                                text_style=TextStyle(
                                    link=Link(url="https://example.com")
                                ),
                            )
                        ),
                        ParagraphElement(
                            text_run=TextRun(content="\n"),
                        ),
                    ],
                    paragraph_style=ParagraphStyle(
                        named_style_type=ParagraphStyleNamedStyleType.NORMAL_TEXT,
                    ),
                )
            )
        ]
        doc = _make_doc(content)
        _index, tabs = from_document(doc)
        doc2 = to_document(tabs)

        tab = doc2.tabs[0]  # type: ignore
        dt = tab.document_tab
        assert dt and dt.body and dt.body.content
        para = dt.body.content[0].paragraph
        assert para and para.elements

        # Find the text runs (skip trailing \n)
        runs = [
            pe.text_run
            for pe in para.elements
            if pe.text_run and pe.text_run.content and pe.text_run.content != "\n"
        ]
        assert len(runs) == 3
        assert runs[0].text_style and runs[0].text_style.bold is True
        assert runs[1].text_style and runs[1].text_style.italic is True
        assert runs[2].text_style and runs[2].text_style.link
        assert runs[2].text_style.link.url == "https://example.com"

    def test_toc_roundtrip(self) -> None:
        """Table of contents survives round-trip."""
        toc = TableOfContents(
            content=[_make_para("Chapter 1"), _make_para("Chapter 2")]
        )
        doc = _make_doc(
            [
                StructuralElement(table_of_contents=toc),
                _make_para("Body text"),
            ]
        )
        _index, tabs = from_document(doc)
        doc2 = to_document(tabs)

        tab = doc2.tabs[0]  # type: ignore
        dt = tab.document_tab
        assert dt and dt.body and dt.body.content
        assert dt.body.content[0].table_of_contents is not None

    def test_inline_objects_roundtrip(self) -> None:
        """Inline objects (image, person, footnoteref, etc.) survive round-trip."""
        content = [
            StructuralElement(
                paragraph=Paragraph(
                    elements=[
                        ParagraphElement(
                            inline_object_element=InlineObjectElement(
                                inline_object_id="obj.123"
                            )
                        ),
                        ParagraphElement(
                            footnote_reference=FootnoteReference(footnote_id="fn.1")
                        ),
                        ParagraphElement(
                            person=Person(
                                person_properties=PersonProperties(
                                    email="test@example.com"
                                )
                            )
                        ),
                        ParagraphElement(date_element=DateElement()),
                        ParagraphElement(
                            rich_link=RichLink(
                                rich_link_properties=RichLinkProperties(
                                    uri="https://example.com"
                                )
                            )
                        ),
                        ParagraphElement(auto_text=AutoText()),
                        ParagraphElement(equation=Equation()),
                        ParagraphElement(column_break=ColumnBreak()),
                        ParagraphElement(
                            text_run=TextRun(content="\n"),
                        ),
                    ],
                    paragraph_style=ParagraphStyle(),
                )
            )
        ]
        doc = _make_doc(content)
        _index, tabs = from_document(doc)
        doc2 = to_document(tabs)

        tab = doc2.tabs[0]  # type: ignore
        dt = tab.document_tab
        assert dt and dt.body and dt.body.content
        para = dt.body.content[0].paragraph
        assert para and para.elements

        # Check each inline type was preserved
        elems = para.elements
        assert elems[0].inline_object_element is not None
        assert elems[0].inline_object_element.inline_object_id == "obj.123"
        assert elems[1].footnote_reference is not None
        assert elems[1].footnote_reference.footnote_id == "fn.1"
        assert elems[2].person is not None
        assert elems[2].person.person_properties is not None
        assert elems[2].person.person_properties.email == "test@example.com"
        assert elems[3].date_element is not None
        assert elems[4].rich_link is not None
        assert elems[5].auto_text is not None
        assert elems[6].equation is not None
        assert elems[7].column_break is not None

    def test_cell_styles_roundtrip(self) -> None:
        """Table cell styles (colspan, rowspan, background) survive round-trip."""
        table = Table(
            rows=2,
            columns=3,
            table_rows=[
                TableRow(
                    table_cells=[
                        TableCell(
                            content=[_make_para("Merged")],
                            table_cell_style=TableCellStyle(
                                column_span=2,
                                background_color=OptionalColor(
                                    color=Color(
                                        rgb_color=RgbColor(red=1.0, green=0.9, blue=0.8)
                                    )
                                ),
                            ),
                        ),
                        TableCell(
                            content=[_make_para("C")],
                            table_cell_style=TableCellStyle(),
                        ),
                    ]
                ),
                TableRow(
                    table_cells=[
                        TableCell(
                            content=[_make_para("D")],
                            table_cell_style=TableCellStyle(),
                        ),
                        TableCell(
                            content=[_make_para("E")],
                            table_cell_style=TableCellStyle(),
                        ),
                        TableCell(
                            content=[_make_para("F")],
                            table_cell_style=TableCellStyle(),
                        ),
                    ]
                ),
            ],
        )
        doc = _make_doc([StructuralElement(table=table)])
        _index, tabs = from_document(doc)
        doc2 = to_document(tabs)

        tab = doc2.tabs[0]  # type: ignore
        dt = tab.document_tab
        assert dt and dt.body and dt.body.content
        t = dt.body.content[0].table
        assert t is not None
        assert t.table_rows
        first_cell = t.table_rows[0].table_cells[0]
        assert first_cell.table_cell_style is not None
        assert first_cell.table_cell_style.column_span == 2
        assert first_cell.table_cell_style.background_color is not None

    def test_hr_and_pagebreak_roundtrip(self) -> None:
        """Horizontal rules and page breaks survive round-trip."""
        content = [
            _make_para("Before hr"),
            StructuralElement(
                paragraph=Paragraph(
                    elements=[
                        ParagraphElement(horizontal_rule=HorizontalRule()),
                        ParagraphElement(text_run=TextRun(content="\n")),
                    ]
                )
            ),
            _make_para("Between"),
            StructuralElement(
                paragraph=Paragraph(
                    elements=[
                        ParagraphElement(page_break=PageBreak()),
                        ParagraphElement(text_run=TextRun(content="\n")),
                    ]
                )
            ),
            _make_para("After"),
        ]
        doc = _make_doc(content)
        _index, tabs = from_document(doc)
        doc2 = to_document(tabs)

        tab = doc2.tabs[0]  # type: ignore
        dt = tab.document_tab
        assert dt and dt.body and dt.body.content
        # HR becomes a paragraph with horizontalRule
        hr_para = dt.body.content[1].paragraph
        assert hr_para and hr_para.elements
        assert hr_para.elements[0].horizontal_rule is not None
        # PageBreak becomes a paragraph with pageBreak
        pb_para = dt.body.content[3].paragraph
        assert pb_para and pb_para.elements
        assert pb_para.elements[0].page_break is not None

    def test_sugar_tag_with_class_roundtrip(self) -> None:
        """Bold+italic text: sugar tag (b) + class with italic survives round-trip."""
        ts = TextStyle(bold=True, italic=True)
        doc = _make_doc([_make_para("Bold italic", text_style=ts)])
        _index, tabs = from_document(doc)

        # Verify intermediate XML model: should be TNode with sugar_tag="b"
        folder = next(iter(tabs.keys()))
        tab_xml = tabs[folder].tab
        para = tab_xml.body[0]
        assert isinstance(para, ParagraphXml)
        node = para.inlines[0]
        assert isinstance(node, TNode)
        assert node.sugar_tag == "b"
        assert node.class_name is not None  # italic goes into class

        # Verify round-trip back to Document
        doc2 = to_document(tabs)
        tab = doc2.tabs[0]  # type: ignore
        dt = tab.document_tab
        assert dt and dt.body and dt.body.content
        para2 = dt.body.content[0].paragraph
        assert para2 and para2.elements
        tr = para2.elements[0].text_run
        assert tr and tr.text_style
        assert tr.text_style.bold is True
        assert tr.text_style.italic is True

    def test_empty_body_roundtrip(self) -> None:
        """Document with empty body survives round-trip."""
        doc = _make_doc([])
        _index, tabs = from_document(doc)
        doc2 = to_document(tabs)
        assert doc2.tabs is not None
        assert len(doc2.tabs) == 1

    def test_multiple_tabs(self) -> None:
        """Document with multiple tabs survives round-trip."""
        doc = Document(
            document_id="multi-tab",
            title="Multi Tab Doc",
            tabs=[
                Tab(
                    tab_properties=TabProperties(tab_id="t.0", title="Introduction"),
                    document_tab=DocumentTab(
                        body=Body(content=[_make_para("Intro text")])
                    ),
                ),
                Tab(
                    tab_properties=TabProperties(tab_id="t.1", title="Appendix"),
                    document_tab=DocumentTab(
                        body=Body(content=[_make_para("Appendix text")])
                    ),
                ),
            ],
        )
        index, tabs = from_document(doc)
        assert len(tabs) == 2
        assert len(index.tabs) == 2

        doc2 = to_document(tabs)
        assert doc2.tabs is not None
        assert len(doc2.tabs) == 2


# ===========================================================================
# File round-trip tests
# ===========================================================================


class TestFileRoundTrip:
    def test_serialize_deserialize(self, tmp_path: Path) -> None:
        """serialize() → deserialize() produces equivalent Document."""
        doc = _make_doc(
            [
                _make_para(
                    "Title",
                    named_style=ParagraphStyleNamedStyleType.TITLE,
                    heading_id="h.title",
                ),
                _make_para("Body text"),
                _make_para(
                    "Bold words",
                    text_style=TextStyle(bold=True),
                ),
            ]
        )

        output = tmp_path / "test-doc"
        paths = serialize(doc, output)
        assert len(paths) >= 3  # index.xml + document.xml + styles.xml

        # Check files exist
        assert (output / "index.xml").exists()
        assert (output / "Tab_1" / "document.xml").exists()
        assert (output / "Tab_1" / "styles.xml").exists()

        # Deserialize and verify
        bundle2 = deserialize(output)
        _assert_text_content(bundle2.document, ["Title", "Body text", "Bold words"])

    def test_styled_file_roundtrip(self, tmp_path: Path) -> None:
        """Styled text survives file round-trip."""

        doc = _make_doc(
            [
                _make_para(
                    "Red bold",
                    text_style=TextStyle(
                        bold=True,
                        foreground_color=OptionalColor(
                            color=Color(
                                rgb_color=RgbColor(red=1.0, green=0.0, blue=0.0)
                            )
                        ),
                    ),
                ),
                _make_para(
                    "Link text",
                    text_style=TextStyle(link=Link(url="https://example.com")),
                ),
            ]
        )

        output = tmp_path / "styled-doc"
        serialize(doc, output)
        doc2 = deserialize(output).document

        tab = doc2.tabs[0]  # type: ignore
        dt = tab.document_tab
        assert dt and dt.body and dt.body.content

        # First paragraph: bold + red
        p1 = dt.body.content[0].paragraph
        assert p1 and p1.elements
        tr = p1.elements[0].text_run
        assert tr and tr.text_style
        assert tr.text_style.bold is True
        assert tr.text_style.foreground_color is not None

        # Second paragraph: link
        p2 = dt.body.content[1].paragraph
        assert p2 and p2.elements
        tr2 = p2.elements[0].text_run
        assert tr2 and tr2.text_style and tr2.text_style.link
        assert tr2.text_style.link.url == "https://example.com"


# ===========================================================================
# Helpers
# ===========================================================================


def _assert_text_content(doc: Document, expected_texts: list[str]) -> None:
    """Assert that a Document's body paragraphs contain the expected texts."""
    assert doc.tabs is not None
    tab = doc.tabs[0]
    dt = tab.document_tab
    assert dt and dt.body and dt.body.content

    actual_texts: list[str] = []
    for se in dt.body.content:
        if se.paragraph and se.paragraph.elements:
            parts: list[str] = []
            for pe in se.paragraph.elements:
                if pe.text_run and pe.text_run.content:
                    parts.append(pe.text_run.content.rstrip("\n"))
            text = "".join(parts)
            if text:
                actual_texts.append(text)

    assert actual_texts == expected_texts
