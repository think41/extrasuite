"""Tests for the serde module: Document ↔ XML round-trip."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from extradoc.api_types._generated import (
    Body,
    Bullet,
    Color,
    Dimension,
    DimensionUnit,
    Document,
    DocumentTab,
    Footer,
    Footnote,
    Header,
    Link,
    ListProperties,
    NestingLevel,
    NestingLevelGlyphType,
    OptionalColor,
    Paragraph,
    ParagraphElement,
    ParagraphStyle,
    ParagraphStyleAlignment,
    ParagraphStyleNamedStyleType,
    RgbColor,
    Shading,
    StructuralElement,
    Tab,
    Table,
    TableCell,
    TableCellStyle,
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
    FormattingNode,
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
                        FormattingNode(tag="b", children=[TNode(text="bold")]),
                    ],
                ),
            ],
        )
        xml = tab.to_xml_string()
        assert "<h1" in xml
        assert "headingId" in xml
        assert "<t>Hello</t>" in xml
        assert "<b>" in xml

        tab2 = TabXml.from_xml_string(xml)
        assert tab2.id == "t.0"
        assert len(tab2.body) == 2
        first = tab2.body[0]
        assert isinstance(first, ParagraphXml)
        assert first.tag == "h1"
        assert first.heading_id == "h.abc"

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
        doc2 = deserialize(output)
        _assert_text_content(doc2, ["Title", "Body text", "Bold words"])

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
        doc2 = deserialize(output)

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
