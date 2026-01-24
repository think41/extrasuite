"""Tests for SML parser.

Tests cover:
- Parsing presentation structure (Spec: markup-syntax-design.md)
- Text content model with P/T elements (Spec: sml-reconciliation-spec.md#text-content-model)
- Range parsing (Spec: sml-reconciliation-spec.md#range-semantics)
- Validation of SML constraints (Spec: sml-reconciliation-spec.md#editing-constraints)
"""

import pytest

from extraslide.classes import PropertyState
from extraslide.parser import (
    ParsedAutoText,
    SMLParseError,
    SMLValidationError,
    parse_element,
    parse_sml,
)


class TestParsePresentation:
    """Test parsing of presentation structure."""

    def test_parse_minimal_presentation(self) -> None:
        """Parse minimal valid presentation."""
        sml = '<Presentation id="pres1"/>'
        result = parse_sml(sml)
        assert result.id == "pres1"
        assert result.slides == []
        assert result.masters == []
        assert result.layouts == []

    def test_parse_presentation_with_attributes(self) -> None:
        """Parse presentation with all attributes."""
        sml = """<Presentation id="pres1" title="My Presentation" w="720pt" h="540pt" locale="en_US" revision="abc123"/>"""
        result = parse_sml(sml)
        assert result.id == "pres1"
        assert result.title == "My Presentation"
        assert result.width == "720pt"
        assert result.height == "540pt"
        assert result.locale == "en_US"
        assert result.revision == "abc123"

    def test_parse_presentation_with_slide(self) -> None:
        """Parse presentation with a single slide."""
        sml = """
        <Presentation id="pres1">
            <Slide id="slide1" layout="layout1" master="master1"/>
        </Presentation>
        """
        result = parse_sml(sml)
        assert len(result.slides) == 1
        assert result.slides[0].id == "slide1"
        assert result.slides[0].layout == "layout1"
        assert result.slides[0].master == "master1"

    def test_parse_presentation_with_master_and_layout(self) -> None:
        """Parse presentation with master and layout."""
        sml = """
        <Presentation id="pres1">
            <Master id="master1" name="Default">
                <Rect id="bg" class="x-0 y-0 w-720 h-540 fill-#ffffff"/>
            </Master>
            <Layout id="layout1" master="master1" name="TITLE" display-name="Title Slide">
                <TextBox id="title_ph" placeholder="title" class="x-72 y-200 w-576 h-80"/>
            </Layout>
            <Slide id="slide1" layout="layout1"/>
        </Presentation>
        """
        result = parse_sml(sml)

        assert len(result.masters) == 1
        assert result.masters[0].id == "master1"
        assert result.masters[0].name == "Default"
        assert len(result.masters[0].elements) == 1

        assert len(result.layouts) == 1
        assert result.layouts[0].id == "layout1"
        assert result.layouts[0].master == "master1"
        assert result.layouts[0].name == "TITLE"
        assert result.layouts[0].display_name == "Title Slide"

    def test_parse_skipped_slide(self) -> None:
        """Parse slide with skipped attribute."""
        sml = """
        <Presentation id="pres1">
            <Slide id="slide1" skipped="true"/>
        </Presentation>
        """
        result = parse_sml(sml)
        assert result.slides[0].skipped is True


class TestParseElements:
    """Test parsing of page elements."""

    def test_parse_textbox(self) -> None:
        """Parse TextBox element."""
        sml = '<TextBox id="tb1" class="x-72 y-100 w-400 h-50 fill-#3b82f6"/>'
        result = parse_element(sml)
        assert result.tag == "TextBox"
        assert result.id == "tb1"
        assert "x-72" in result.classes
        assert result.position == {"x": 72, "y": 100, "w": 400, "h": 50}
        assert result.fill is not None
        assert result.fill.color is not None
        assert result.fill.color.hex == "#3b82f6"

    def test_parse_rect(self) -> None:
        """Parse Rect element."""
        sml = '<Rect id="rect1" class="x-100 y-200 w-300 h-150 fill-#ef4444 stroke-#000000 stroke-w-2"/>'
        result = parse_element(sml)
        assert result.tag == "Rect"
        assert result.id == "rect1"
        assert result.fill.color.hex == "#ef4444"
        assert result.stroke is not None
        assert result.stroke.color.hex == "#000000"
        assert result.stroke.weight_pt == 2.0

    def test_parse_line(self) -> None:
        """Parse Line element."""
        sml = '<Line id="line1" class="line-straight x-100 y-100 w-200 h-0 stroke-#6b7280 stroke-w-2 arrow-end-fill"/>'
        result = parse_element(sml)
        assert result.tag == "Line"
        assert result.id == "line1"
        assert "line-straight" in result.classes
        assert "arrow-end-fill" in result.classes

    def test_parse_image(self) -> None:
        """Parse Image element."""
        sml = '<Image id="img1" class="x-100 y-100 w-300 h-200" src="https://example.com/image.png" alt="Example"/>'
        result = parse_element(sml)
        assert result.tag == "Image"
        assert result.id == "img1"
        assert result.attrs["src"] == "https://example.com/image.png"
        assert result.attrs["alt"] == "Example"

    def test_parse_video(self) -> None:
        """Parse Video element."""
        sml = '<Video id="vid1" class="x-100 y-100 w-480 h-270" src="youtube:dQw4w9WgXcQ" autoplay="true"/>'
        result = parse_element(sml)
        assert result.tag == "Video"
        assert result.attrs["src"] == "youtube:dQw4w9WgXcQ"
        assert result.attrs["autoplay"] == "true"

    def test_parse_chart(self) -> None:
        """Parse Chart element."""
        sml = '<Chart id="chart1" class="x-100 y-100 w-400 h-300" spreadsheet="abc123" chart-id="456"/>'
        result = parse_element(sml)
        assert result.tag == "Chart"
        assert result.attrs["spreadsheet"] == "abc123"
        assert result.attrs["chart-id"] == "456"

    def test_parse_group(self) -> None:
        """Parse Group with children."""
        sml = """
        <Group id="group1" class="x-100 y-100">
            <Rect id="rect1" class="x-0 y-0 w-100 h-50"/>
            <TextBox id="tb1" class="x-0 y-60 w-100 h-30"/>
        </Group>
        """
        result = parse_element(sml)
        assert result.tag == "Group"
        assert result.id == "group1"
        assert len(result.children) == 2
        assert result.children[0].tag == "Rect"
        assert result.children[1].tag == "TextBox"

    def test_parse_placeholder(self) -> None:
        """Parse element with placeholder attributes."""
        sml = '<TextBox id="tb1" placeholder="title" placeholder-index="0" class="x-72 y-100 w-400 h-50"/>'
        result = parse_element(sml)
        assert result.attrs["placeholder"] == "title"
        assert result.attrs["placeholder-index"] == "0"


class TestParseTextContent:
    """Test parsing of text content (P and T elements).

    Spec: sml-reconciliation-spec.md#text-content-model
    """

    def test_parse_simple_text(self) -> None:
        """Parse shape with simple text content."""
        sml = """
        <TextBox id="tb1" class="x-72 y-100 w-400 h-50">
            <P range="0-12">
                <T range="0-11">Hello World</T>
            </P>
        </TextBox>
        """
        result = parse_element(sml)
        assert len(result.paragraphs) == 1
        para = result.paragraphs[0]
        assert para.range_start == 0
        assert para.range_end == 12
        assert len(para.runs) == 1
        assert para.runs[0].content == "Hello World"
        assert para.runs[0].range_start == 0
        assert para.runs[0].range_end == 11

    def test_parse_multiple_text_runs(self) -> None:
        """Parse paragraph with multiple text runs."""
        sml = """
        <TextBox id="tb1">
            <P range="0-18">
                <T range="0-6">Hello </T>
                <T range="6-11" class="bold">world</T>
                <T range="11-17"> today</T>
            </P>
        </TextBox>
        """
        result = parse_element(sml)
        para = result.paragraphs[0]
        assert len(para.runs) == 3
        assert para.runs[0].content == "Hello "
        assert para.runs[1].content == "world"
        assert para.runs[1].style.bold is True
        assert para.runs[2].content == " today"

    def test_parse_multiple_paragraphs(self) -> None:
        """Parse shape with multiple paragraphs."""
        sml = """
        <TextBox id="tb1">
            <P range="0-12">
                <T range="0-11">First line.</T>
            </P>
            <P range="12-25">
                <T range="12-24">Second line.</T>
            </P>
        </TextBox>
        """
        result = parse_element(sml)
        assert len(result.paragraphs) == 2
        assert result.paragraphs[0].runs[0].content == "First line."
        assert result.paragraphs[1].runs[0].content == "Second line."

    def test_parse_styled_text(self) -> None:
        """Parse text with various styles."""
        sml = """
        <TextBox id="tb1">
            <P range="0-50">
                <T range="0-5" class="bold italic underline">Hello</T>
                <T range="5-11" class="text-size-24 text-color-#ef4444"> World</T>
                <T range="11-20" class="font-family-arial line-through"> Striked</T>
            </P>
        </TextBox>
        """
        result = parse_element(sml)
        runs = result.paragraphs[0].runs

        assert runs[0].style.bold is True
        assert runs[0].style.italic is True
        assert runs[0].style.underline is True

        assert runs[1].style.font_size_pt == 24.0
        assert runs[1].style.foreground_color.hex == "#ef4444"

        assert runs[2].style.font_family == "Arial"
        assert runs[2].style.strikethrough is True

    def test_parse_text_with_link(self) -> None:
        """Parse text run with href attribute."""
        sml = """
        <TextBox id="tb1">
            <P range="0-10">
                <T range="0-9" href="https://example.com">Click me</T>
            </P>
        </TextBox>
        """
        result = parse_element(sml)
        assert result.paragraphs[0].runs[0].href == "https://example.com"

    def test_parse_paragraph_with_bullet(self) -> None:
        """Parse paragraph with bullet classes."""
        sml = """
        <TextBox id="tb1">
            <P range="0-10" class="bullet bullet-disc">
                <T range="0-9">Item one</T>
            </P>
        </TextBox>
        """
        result = parse_element(sml)
        para = result.paragraphs[0]
        assert "bullet" in para.classes
        assert "bullet-disc" in para.classes

    def test_parse_auto_text(self) -> None:
        """Parse auto text elements (slide numbers, etc.)."""
        sml = """
        <TextBox id="tb1">
            <P range="0-5">
                <Auto type="slide-number"/>
            </P>
        </TextBox>
        """
        result = parse_element(sml)

        assert len(result.paragraphs[0].runs) == 1
        auto = result.paragraphs[0].runs[0]
        assert isinstance(auto, ParsedAutoText)
        assert auto.type == "slide-number"


class TestParseTable:
    """Test parsing of table elements."""

    def test_parse_simple_table(self) -> None:
        """Parse simple table structure."""
        sml = """
        <Table id="table1" class="x-72 y-200 w-576 h-200" rows="2" cols="2">
            <Row r="0">
                <Cell id="table1_r0c0" r="0" c="0">
                    <P range="0-7"><T range="0-6">Header</T></P>
                </Cell>
                <Cell id="table1_r0c1" r="0" c="1">
                    <P range="0-7"><T range="0-6">Value</T></P>
                </Cell>
            </Row>
            <Row r="1">
                <Cell id="table1_r1c0" r="1" c="0">
                    <P range="0-5"><T range="0-4">Data</T></P>
                </Cell>
                <Cell id="table1_r1c1" r="1" c="1">
                    <P range="0-5"><T range="0-4">123</T></P>
                </Cell>
            </Row>
        </Table>
        """
        result = parse_element(sml)
        assert result.tag == "Table"
        assert result.rows == 2
        assert result.cols == 2
        assert len(result.table_rows) == 2

        row0 = result.table_rows[0]
        assert row0.row_index == 0
        assert len(row0.cells) == 2
        assert row0.cells[0].row == 0
        assert row0.cells[0].col == 0
        assert row0.cells[1].col == 1

    def test_parse_table_with_spans(self) -> None:
        """Parse table with merged cells."""
        sml = """
        <Table id="table1" rows="2" cols="3">
            <Row r="0">
                <Cell id="table1_r0c0" r="0" c="0" colspan="2">
                    <P range="0-7"><T range="0-6">Merged</T></P>
                </Cell>
                <Cell id="table1_r0c2" r="0" c="2"/>
            </Row>
        </Table>
        """
        result = parse_element(sml)
        cell = result.table_rows[0].cells[0]
        assert cell.colspan == 2
        assert cell.rowspan == 1

    def test_parse_table_cell_with_fill(self) -> None:
        """Parse table cell with background fill."""
        sml = """
        <Table id="table1" rows="1" cols="1">
            <Row r="0">
                <Cell id="table1_r0c0" r="0" c="0" class="fill-#fef3c7"/>
            </Row>
        </Table>
        """
        result = parse_element(sml)
        cell = result.table_rows[0].cells[0]
        assert "fill-#fef3c7" in cell.classes


class TestParseRanges:
    """Test range attribute parsing.

    Spec: sml-reconciliation-spec.md#range-semantics
    """

    def test_parse_valid_range(self) -> None:
        """Parse valid range format."""
        sml = """
        <TextBox id="tb1">
            <P range="0-12">
                <T range="0-5">Hello</T>
            </P>
        </TextBox>
        """
        result = parse_element(sml)
        para = result.paragraphs[0]
        assert para.range_start == 0
        assert para.range_end == 12
        run = para.runs[0]
        assert run.range_start == 0
        assert run.range_end == 5

    def test_parse_missing_range(self) -> None:
        """Missing range is allowed (for new elements)."""
        sml = """
        <TextBox id="tb1">
            <P>
                <T>New text</T>
            </P>
        </TextBox>
        """
        result = parse_element(sml)
        para = result.paragraphs[0]
        assert para.range_start is None
        assert para.range_end is None
        assert para.runs[0].range_start is None

    def test_parse_invalid_range_format(self) -> None:
        """Invalid range format should raise error."""
        sml = """
        <TextBox id="tb1">
            <P range="invalid">
                <T>Text</T>
            </P>
        </TextBox>
        """
        with pytest.raises(SMLParseError, match="Invalid range format"):
            parse_element(sml)


class TestValidation:
    """Test SML validation constraints.

    Spec: sml-reconciliation-spec.md#editing-constraints
    """

    def test_reject_bare_text_in_shape(self) -> None:
        """Bare text in shape should be rejected."""
        sml = '<TextBox id="tb1">Hello world</TextBox>'
        with pytest.raises(SMLValidationError, match="Bare text"):
            parse_element(sml, strict=True)

    def test_reject_bare_text_in_paragraph(self) -> None:
        """Bare text in paragraph should be rejected."""
        sml = """
        <TextBox id="tb1">
            <P>Bare text here</P>
        </TextBox>
        """
        with pytest.raises(SMLValidationError, match="Bare text"):
            parse_element(sml, strict=True)

    def test_reject_newline_in_text_run(self) -> None:
        """Newline in text content should be rejected."""
        sml = """
        <TextBox id="tb1">
            <P range="0-20">
                <T range="0-19">Line1
Line2</T>
            </P>
        </TextBox>
        """
        with pytest.raises(SMLValidationError, match="Newlines"):
            parse_element(sml, strict=True)

    def test_allow_violations_in_non_strict_mode(self) -> None:
        """Non-strict mode should allow violations."""
        sml = '<TextBox id="tb1">Bare text</TextBox>'
        result = parse_element(sml, strict=False)
        assert result.id == "tb1"


class TestSpecialCases:
    """Test special parsing cases."""

    def test_parse_html_entities(self) -> None:
        """HTML entities should be unescaped."""
        sml = """
        <TextBox id="tb1">
            <P range="0-10">
                <T range="0-9">A &amp; B &lt; C</T>
            </P>
        </TextBox>
        """
        result = parse_element(sml)
        assert result.paragraphs[0].runs[0].content == "A & B < C"

    def test_parse_empty_shape(self) -> None:
        """Parse shape with no text content."""
        sml = '<Rect id="rect1" class="x-100 y-100 w-200 h-100"/>'
        result = parse_element(sml)
        assert result.paragraphs == []

    def test_parse_theme_color(self) -> None:
        """Parse theme color fill."""
        sml = '<Rect id="rect1" class="fill-theme-accent1"/>'
        result = parse_element(sml)
        assert result.fill.color.theme == "accent1"

    def test_parse_fill_with_opacity(self) -> None:
        """Parse fill with opacity modifier."""
        sml = '<Rect id="rect1" class="fill-#3b82f6/50"/>'
        result = parse_element(sml)
        assert result.fill.color.hex == "#3b82f6"
        assert result.fill.color.alpha == 0.5

    def test_parse_property_state_none(self) -> None:
        """Parse fill-none property state."""
        sml = '<Rect id="rect1" class="fill-none"/>'
        result = parse_element(sml)

        assert result.fill.state == PropertyState.NOT_RENDERED

    def test_parse_property_state_inherit(self) -> None:
        """Parse fill-inherit property state."""
        sml = '<Rect id="rect1" class="fill-inherit"/>'
        result = parse_element(sml)

        assert result.fill.state == PropertyState.INHERIT

    def test_parse_invalid_xml(self) -> None:
        """Invalid XML should raise parse error."""
        sml = "<Presentation><broken"
        with pytest.raises(SMLParseError, match="Invalid XML"):
            parse_sml(sml)

    def test_parse_wrong_root_element(self) -> None:
        """Wrong root element should raise error."""
        sml = "<Slide id='s1'/>"
        with pytest.raises(SMLParseError, match="Root element must be"):
            parse_sml(sml)

    def test_parse_wordart(self) -> None:
        """Parse WordArt element with text content."""
        sml = '<WordArt id="wa1" class="x-100 y-100">Hello World</WordArt>'
        result = parse_element(sml, strict=False)
        assert result.tag == "WordArt"
        assert len(result.paragraphs) == 1
        assert result.paragraphs[0].runs[0].content == "Hello World"


class TestRoundTrip:
    """Test that parsed SML contains all info needed for diffing."""

    def test_preserve_all_classes(self) -> None:
        """All classes should be preserved for diffing."""
        sml = '<Rect id="rect1" class="x-100 y-200 w-300 h-150 fill-#ef4444 stroke-#000000 stroke-w-2 shadow-md"/>'
        result = parse_element(sml)
        assert "x-100" in result.classes
        assert "fill-#ef4444" in result.classes
        assert "stroke-#000000" in result.classes
        assert "shadow-md" in result.classes

    def test_preserve_all_attrs(self) -> None:
        """All attributes should be preserved."""
        sml = '<Image id="img1" src="https://example.com/img.png" alt="Example" title="Image Title" class="x-100 y-100"/>'
        result = parse_element(sml)
        assert result.attrs["src"] == "https://example.com/img.png"
        assert result.attrs["alt"] == "Example"
        assert result.attrs["title"] == "Image Title"
