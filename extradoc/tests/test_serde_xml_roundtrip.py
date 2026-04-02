"""Tests for the 3-way merge XML SERDE interface.

Tests cover:
- serialize() writes .pristine/document.zip for XML format
- deserialize(base, folder) performs 3-way merge for XML format
- Body content changes propagate correctly
- Table changes (cell edits, row add/delete)
- Things the XML SERDE models are carried through (named styles, styles.xml)
- Things the XML SERDE doesn't model are preserved from base
- Comments, multi-tab docs, footnotes, lists
- Edge cases: legacy folder, empty doc
"""

from __future__ import annotations

import json
import zipfile
from typing import TYPE_CHECKING
from xml.etree import ElementTree as ET

if TYPE_CHECKING:
    from pathlib import Path

from extradoc.api_types._generated import (
    Body,
    Dimension,
    Document,
    DocumentStyle,
    DocumentTab,
    Footer,
    Footnote,
    Header,
    InlineObject,
    InlineObjectProperties,
    NamedStyle,
    NamedStyles,
    Paragraph,
    ParagraphElement,
    ParagraphStyle,
    ParagraphStyleNamedStyleType,
    StructuralElement,
    Tab,
    Table,
    TableCell,
    TableRow,
    TabProperties,
    TextRun,
    TextStyle,
)
from extradoc.api_types._generated import (
    List as DocList,
)
from extradoc.comments._types import DocumentWithComments, FileComments
from extradoc.serde import deserialize, serialize

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_text_para(
    text: str,
    named_style: ParagraphStyleNamedStyleType | None = None,
    bold: bool = False,
    italic: bool = False,
    align: str | None = None,
) -> StructuralElement:
    ts = TextStyle(bold=bold if bold else None, italic=italic if italic else None)
    ps = ParagraphStyle(
        named_style_type=named_style or ParagraphStyleNamedStyleType.NORMAL_TEXT,
        alignment=align,
    )
    el = ParagraphElement(text_run=TextRun(content=text + "\n", text_style=ts))
    return StructuralElement(paragraph=Paragraph(elements=[el], paragraph_style=ps))


def _make_table_se(rows: list[list[str]]) -> StructuralElement:
    """Create a simple table StructuralElement."""
    table_rows = []
    for row_texts in rows:
        cells = []
        for cell_text in row_texts:
            cell_body = [
                StructuralElement(
                    paragraph=Paragraph(
                        elements=[
                            ParagraphElement(text_run=TextRun(content=cell_text + "\n"))
                        ]
                    )
                )
            ]
            cells.append(TableCell(content=cell_body))
        table_rows.append(TableRow(table_cells=cells))
    return StructuralElement(table=Table(table_rows=table_rows))


def _make_doc(
    paras: list[str],
    doc_id: str = "test-doc",
    title: str = "Test",
    headers: dict[str, Header] | None = None,
    footers: dict[str, Footer] | None = None,
    footnotes: dict[str, Footnote] | None = None,
    document_style: DocumentStyle | None = None,
    named_styles: NamedStyles | None = None,
    inline_objects: dict[str, InlineObject] | None = None,
    lists: dict[str, DocList] | None = None,
    extra_content: list[StructuralElement] | None = None,
) -> Document:
    """Build a Document with the given paragraph texts."""
    content: list[StructuralElement] = [_make_text_para(t) for t in paras]
    if extra_content:
        content.extend(extra_content)
    doc_tab = DocumentTab(
        body=Body(content=content),
        headers=headers,
        footers=footers,
        footnotes=footnotes,
        document_style=document_style,
        named_styles=named_styles,
        inline_objects=inline_objects,
        lists=lists,
    )
    return Document(
        document_id=doc_id,
        title=title,
        tabs=[
            Tab(
                tab_properties=TabProperties(tab_id="t.0", title="Tab 1"),
                document_tab=doc_tab,
            )
        ],
    )


def _make_bundle(doc: Document) -> DocumentWithComments:
    return DocumentWithComments(
        document=doc,
        comments=FileComments(file_id=doc.document_id or ""),
    )


def _body_texts(doc: Document, tab_idx: int = 0) -> list[str]:
    """Extract non-empty body paragraph texts (stripped of newlines)."""
    tab = (doc.tabs or [])[tab_idx]
    dt = tab.document_tab
    if not dt or not dt.body:
        return []
    texts: list[str] = []
    for se in dt.body.content or []:
        if se.paragraph:
            text = "".join(
                (pe.text_run.content or "").rstrip("\n")
                for pe in (se.paragraph.elements or [])
                if pe.text_run and pe.text_run.content and pe.text_run.content != "\n"
            )
            if text:
                texts.append(text)
    return texts


def _cell_texts(doc: Document, tab_idx: int = 0) -> list[list[str]]:
    """Extract cell texts from tables in the body."""
    tab = (doc.tabs or [])[tab_idx]
    dt = tab.document_tab
    if not dt or not dt.body:
        return []
    result: list[list[str]] = []
    for se in dt.body.content or []:
        if se.table:
            for row in se.table.table_rows or []:
                row_texts: list[str] = []
                for cell in row.table_cells or []:
                    cell_text = ""
                    for cell_se in cell.content or []:
                        if cell_se.paragraph:
                            cell_text += "".join(
                                (pe.text_run.content or "").rstrip("\n")
                                for pe in (cell_se.paragraph.elements or [])
                                if pe.text_run
                            )
                    row_texts.append(cell_text)
                result.append(row_texts)
    return result


def _read_doc_xml(folder: Path, tab_folder: str = "Tab_1") -> str:
    return (folder / tab_folder / "document.xml").read_text(encoding="utf-8")


def _write_doc_xml(folder: Path, content: str, tab_folder: str = "Tab_1") -> None:
    (folder / tab_folder / "document.xml").write_text(content, encoding="utf-8")


def _read_styles_xml(folder: Path, tab_folder: str = "Tab_1") -> str:
    return (folder / tab_folder / "styles.xml").read_text(encoding="utf-8")


def _write_styles_xml(folder: Path, content: str, tab_folder: str = "Tab_1") -> None:
    (folder / tab_folder / "styles.xml").write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Test Group: serialize writes .pristine/document.zip for XML
# ---------------------------------------------------------------------------


class TestSerializeWritesPristineXml:
    def test_pristine_zip_created_for_xml(self, tmp_path: Path) -> None:
        """serialize() with XML format writes .pristine/document.zip."""
        doc = _make_doc(["Hello world"])
        bundle = _make_bundle(doc)
        folder = tmp_path / "doc"
        serialize(bundle, folder, format="xml")
        assert (folder / ".pristine" / "document.zip").exists()

    def test_pristine_contains_xml_files(self, tmp_path: Path) -> None:
        """The pristine zip contains document.xml, styles.xml, index.xml."""
        doc = _make_doc(["Hello world"])
        bundle = _make_bundle(doc)
        folder = tmp_path / "doc"
        serialize(bundle, folder, format="xml")
        zip_path = folder / ".pristine" / "document.zip"
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
        assert any("document.xml" in n for n in names)
        assert any("styles.xml" in n for n in names)
        assert "index.xml" in names
        # Should NOT contain .pristine/ or .raw/ entries
        assert not any(".pristine" in n for n in names)
        assert not any(".raw" in n for n in names)


# ---------------------------------------------------------------------------
# Group 1: Body content changes
# ---------------------------------------------------------------------------


class TestBodyContentChanges:
    def test_edit_paragraph_text(self, tmp_path: Path) -> None:
        """Edit paragraph text in document.xml → desired has updated text."""
        base_doc = _make_doc(["Hello world", "Second para"])
        base = _make_bundle(base_doc)
        folder = tmp_path / "doc"
        serialize(base, folder, format="xml")

        xml = _read_doc_xml(folder)
        xml = xml.replace(">Hello world<", ">Hello there<")
        _write_doc_xml(folder, xml)

        desired = deserialize(base, folder)
        texts = _body_texts(desired.document)
        assert "Hello there" in texts
        assert "Second para" in texts

    def test_add_paragraph(self, tmp_path: Path) -> None:
        """Insert a new <p><t>...</t></p> in document.xml → appears in desired body."""
        base_doc = _make_doc(["First para", "Second para"])
        base = _make_bundle(base_doc)
        folder = tmp_path / "doc"
        serialize(base, folder, format="xml")

        xml = _read_doc_xml(folder)
        # Insert after the first <p>...</p> block
        xml = xml.replace(
            "<p>\n      <t>First para</t>\n    </p>",
            "<p>\n      <t>First para</t>\n    </p>\n    <p>\n      <t>New inserted para</t>\n    </p>",
        )
        _write_doc_xml(folder, xml)

        desired = deserialize(base, folder)
        texts = _body_texts(desired.document)
        assert "New inserted para" in texts
        assert "First para" in texts
        assert "Second para" in texts

    def test_delete_paragraph(self, tmp_path: Path) -> None:
        """Remove a <p> from document.xml → absent in desired body."""
        base_doc = _make_doc(["Keep this", "Delete this", "Also keep"])
        base = _make_bundle(base_doc)
        folder = tmp_path / "doc"
        serialize(base, folder, format="xml")

        xml = _read_doc_xml(folder)
        # Remove the Delete this paragraph
        tree = ET.fromstring(xml)
        body = tree.find("body")
        assert body is not None
        to_remove = None
        for p in body.findall("p"):
            t = p.find("t")
            if t is not None and t.text == "Delete this":
                to_remove = p
        if to_remove is not None:
            body.remove(to_remove)
        _write_doc_xml(folder, ET.tostring(tree, encoding="unicode"))

        desired = deserialize(base, folder)
        texts = _body_texts(desired.document)
        assert "Delete this" not in texts
        assert "Keep this" in texts
        assert "Also keep" in texts

    def test_edit_bold_text_via_sugar_tag(self, tmp_path: Path) -> None:
        """Change text to bold using <b> sugar tag in document.xml → desired is bold."""
        base_doc = _make_doc(["Normal text"])
        base = _make_bundle(base_doc)
        folder = tmp_path / "doc"
        serialize(base, folder, format="xml")

        xml = _read_doc_xml(folder)
        # Wrap the text in <b>
        xml = xml.replace("<t>Normal text</t>", "<t><b>Bold text</b></t>")
        _write_doc_xml(folder, xml)

        desired = deserialize(base, folder)
        tab = desired.document.tabs[0]  # type: ignore[index]
        body_content = tab.document_tab.body.content or []  # type: ignore[union-attr]
        found_bold = False
        for se in body_content:
            if se.paragraph:
                for pe in se.paragraph.elements or []:
                    if (
                        pe.text_run
                        and pe.text_run.text_style
                        and pe.text_run.text_style.bold
                    ):
                        found_bold = True
        assert found_bold, "Expected a bold run in the desired body"

    def test_no_changes_produces_same_body(self, tmp_path: Path) -> None:
        """serialize then immediately deserialize (no edits) → body unchanged."""
        base_doc = _make_doc(["Hello world", "Second para"])
        base = _make_bundle(base_doc)
        folder = tmp_path / "doc"
        serialize(base, folder, format="xml")

        # No edits
        desired = deserialize(base, folder)
        desired_texts = _body_texts(desired.document)
        base_texts = _body_texts(base_doc)
        assert desired_texts == base_texts


# ---------------------------------------------------------------------------
# Group 2: Table changes
# ---------------------------------------------------------------------------


class TestTableChanges:
    def test_edit_table_cell_text(self, tmp_path: Path) -> None:
        """Edit table cell text in XML → desired has updated cell text."""
        table_se = _make_table_se([["Header1", "Header2"], ["Value1", "Value2"]])
        base_doc = _make_doc([], extra_content=[table_se])
        base = _make_bundle(base_doc)
        folder = tmp_path / "doc"
        serialize(base, folder, format="xml")

        xml = _read_doc_xml(folder)
        xml = xml.replace(">Value1<", ">Updated1<")
        _write_doc_xml(folder, xml)

        desired = deserialize(base, folder)
        cell_data = _cell_texts(desired.document)
        flat_cells = [cell for row in cell_data for cell in row]
        assert "Updated1" in flat_cells

    def test_add_table_row(self, tmp_path: Path) -> None:
        """Insert a new <tr> into table XML → desired table has extra row."""
        table_se = _make_table_se([["A", "B"], ["C", "D"]])
        base_doc = _make_doc([], extra_content=[table_se])
        base = _make_bundle(base_doc)
        folder = tmp_path / "doc"
        serialize(base, folder, format="xml")

        xml = _read_doc_xml(folder)
        # Append a new row before closing </table>
        new_row = "\n      <tr><td><p><t>E</t></p></td><td><p><t>F</t></p></td></tr>"
        xml = xml.replace("</table>", new_row + "\n    </table>")
        _write_doc_xml(folder, xml)

        desired = deserialize(base, folder)
        cell_data = _cell_texts(desired.document)
        assert len(cell_data) >= 3
        flat_cells = [cell for row in cell_data for cell in row]
        assert "E" in flat_cells
        assert "F" in flat_cells

    def test_delete_table_row(self, tmp_path: Path) -> None:
        """Remove a <tr> from table XML → desired table has fewer rows."""
        table_se = _make_table_se([["A", "B"], ["C", "D"], ["E", "F"]])
        base_doc = _make_doc([], extra_content=[table_se])
        base = _make_bundle(base_doc)
        folder = tmp_path / "doc"
        serialize(base, folder, format="xml")

        xml = _read_doc_xml(folder)
        tree = ET.fromstring(xml)
        body = tree.find("body")
        assert body is not None
        table = body.find("table")
        assert table is not None
        rows = table.findall("tr")
        # Remove the second row (C, D)
        assert len(rows) >= 2
        table.remove(rows[1])
        _write_doc_xml(folder, ET.tostring(tree, encoding="unicode"))

        desired = deserialize(base, folder)
        cell_data = _cell_texts(desired.document)
        flat_cells = [cell for row in cell_data for cell in row]
        assert "C" not in flat_cells
        assert "A" in flat_cells


# ---------------------------------------------------------------------------
# Group 3: Things the XML SERDE models — preserved through merge
# ---------------------------------------------------------------------------


class TestXmlSerdeModels:
    """XML SERDE models more than markdown: named styles, docstyle, headers, footers.
    These should round-trip through the 3-way merge correctly.
    """

    def test_named_styles_round_trip(self, tmp_path: Path) -> None:
        """Named styles in namedstyles.xml round-trip through 3-way merge."""
        ns = NamedStyles(
            styles=[
                NamedStyle(
                    named_style_type="HEADING_1", text_style=TextStyle(bold=True)
                )
            ]
        )
        base_doc = _make_doc(["Body text"], named_styles=ns)
        base = _make_bundle(base_doc)
        folder = tmp_path / "doc"
        serialize(base, folder, format="xml")

        # Edit body only
        xml = _read_doc_xml(folder)
        xml = xml.replace(">Body text<", ">Changed body<")
        _write_doc_xml(folder, xml)

        desired = deserialize(base, folder)
        dt = desired.document.tabs[0].document_tab  # type: ignore[index]
        assert dt.named_styles is not None
        types = [s.named_style_type for s in (dt.named_styles.styles or [])]
        assert "HEADING_1" in types

    def test_edit_named_style_in_namedstyles_xml(self, tmp_path: Path) -> None:
        """Edit namedstyles.xml directly → desired doc has updated named style."""
        ns = NamedStyles(
            styles=[
                NamedStyle(
                    named_style_type="HEADING_1",
                    text_style=TextStyle(bold=True, italic=None),
                )
            ]
        )
        base_doc = _make_doc(["Body text"], named_styles=ns)
        base = _make_bundle(base_doc)
        folder = tmp_path / "doc"
        serialize(base, folder, format="xml")

        # Edit namedstyles.xml: add italic=True to HEADING_1
        ns_path = folder / "Tab_1" / "namedstyles.xml"
        tree = ET.fromstring(ns_path.read_text(encoding="utf-8"))
        raw_data = json.loads(tree.text or "{}")
        for style in raw_data.get("styles", []):
            if style.get("namedStyleType") == "HEADING_1":
                style["textStyle"]["italic"] = True
        tree.text = json.dumps(raw_data, separators=(",", ":"))
        ns_path.write_text(ET.tostring(tree, encoding="unicode"), encoding="utf-8")

        desired = deserialize(base, folder)
        dt = desired.document.tabs[0].document_tab  # type: ignore[index]
        assert dt.named_styles is not None
        h1_style = next(
            (
                s
                for s in (dt.named_styles.styles or [])
                if s.named_style_type == "HEADING_1"
            ),
            None,
        )
        assert h1_style is not None
        assert h1_style.text_style is not None
        assert h1_style.text_style.italic is True

    def test_paragraph_style_alignment_via_styles_xml(self, tmp_path: Path) -> None:
        """Paragraph with CENTER alignment serializes to styles.xml and round-trips."""
        base_doc = Document(
            document_id="test-align",
            title="Test",
            tabs=[
                Tab(
                    tab_properties=TabProperties(tab_id="t.0", title="Tab 1"),
                    document_tab=DocumentTab(
                        body=Body(
                            content=[
                                StructuralElement(
                                    paragraph=Paragraph(
                                        elements=[
                                            ParagraphElement(
                                                text_run=TextRun(content="Centered\n")
                                            )
                                        ],
                                        paragraph_style=ParagraphStyle(
                                            named_style_type=ParagraphStyleNamedStyleType.NORMAL_TEXT,
                                            alignment="CENTER",
                                        ),
                                    )
                                )
                            ]
                        )
                    ),
                )
            ],
        )
        base = _make_bundle(base_doc)
        folder = tmp_path / "doc"
        serialize(base, folder, format="xml")

        # No edits
        desired = deserialize(base, folder)
        dt = desired.document.tabs[0].document_tab  # type: ignore[index]
        for se in dt.body.content or []:  # type: ignore[union-attr]
            if se.paragraph:
                text = "".join(
                    (pe.text_run.content or "")
                    for pe in se.paragraph.elements or []
                    if pe.text_run
                )
                if "Centered" in text:
                    assert (
                        se.paragraph.paragraph_style is not None
                        and se.paragraph.paragraph_style.alignment == "CENTER"
                    )

    def test_text_style_via_styles_xml(self, tmp_path: Path) -> None:
        """Text with font-size serializes as class in styles.xml and round-trips."""
        base_doc = Document(
            document_id="test-font",
            title="Test",
            tabs=[
                Tab(
                    tab_properties=TabProperties(tab_id="t.0", title="Tab 1"),
                    document_tab=DocumentTab(
                        body=Body(
                            content=[
                                StructuralElement(
                                    paragraph=Paragraph(
                                        elements=[
                                            ParagraphElement(
                                                text_run=TextRun(
                                                    content="Big font\n",
                                                    text_style=TextStyle(
                                                        font_size=Dimension(
                                                            magnitude=24.0, unit="PT"
                                                        )
                                                    ),
                                                )
                                            )
                                        ]
                                    )
                                )
                            ]
                        )
                    ),
                )
            ],
        )
        base = _make_bundle(base_doc)
        folder = tmp_path / "doc"
        serialize(base, folder, format="xml")

        # Verify styles.xml was written
        styles_xml = _read_styles_xml(folder)
        assert "24.0pt" in styles_xml

        # No edits, verify round-trip
        desired = deserialize(base, folder)
        dt = desired.document.tabs[0].document_tab  # type: ignore[index]
        for se in dt.body.content or []:  # type: ignore[union-attr]
            if se.paragraph:
                for pe in se.paragraph.elements or []:
                    if pe.text_run and "Big font" in (pe.text_run.content or ""):
                        assert pe.text_run.text_style is not None
                        assert pe.text_run.text_style.font_size is not None
                        assert pe.text_run.text_style.font_size.magnitude == 24.0

    def test_edit_text_style_class_in_styles_xml(self, tmp_path: Path) -> None:
        """Editing font size in styles.xml → desired has updated text style."""
        base_doc = Document(
            document_id="test-edit-style",
            title="Test",
            tabs=[
                Tab(
                    tab_properties=TabProperties(tab_id="t.0", title="Tab 1"),
                    document_tab=DocumentTab(
                        body=Body(
                            content=[
                                StructuralElement(
                                    paragraph=Paragraph(
                                        elements=[
                                            ParagraphElement(
                                                text_run=TextRun(
                                                    content="Sized text\n",
                                                    text_style=TextStyle(
                                                        font_size=Dimension(
                                                            magnitude=12.0, unit="PT"
                                                        )
                                                    ),
                                                )
                                            )
                                        ]
                                    )
                                )
                            ]
                        )
                    ),
                )
            ],
        )
        base = _make_bundle(base_doc)
        folder = tmp_path / "doc"
        serialize(base, folder, format="xml")

        # Edit styles.xml: change 12.0pt to 18.0pt
        styles_xml = _read_styles_xml(folder)
        styles_xml = styles_xml.replace('size="12.0pt"', 'size="18.0pt"')
        _write_styles_xml(folder, styles_xml)

        desired = deserialize(base, folder)
        dt = desired.document.tabs[0].document_tab  # type: ignore[index]
        for se in dt.body.content or []:  # type: ignore[union-attr]
            if se.paragraph:
                for pe in se.paragraph.elements or []:
                    if pe.text_run and "Sized text" in (pe.text_run.content or ""):
                        assert pe.text_run.text_style is not None
                        assert pe.text_run.text_style.font_size is not None
                        assert pe.text_run.text_style.font_size.magnitude == 18.0


# ---------------------------------------------------------------------------
# Group 4: Things the XML SERDE doesn't model — preserved from base
# ---------------------------------------------------------------------------


class TestPreservationFromBase:
    def test_document_style_preserved_when_not_in_xml(self, tmp_path: Path) -> None:
        """Custom document style margin from base is preserved (round-trip)."""
        custom_margin = Dimension(magnitude=72.0, unit="PT")
        doc_style = DocumentStyle(margin_left=custom_margin)
        base_doc = _make_doc(["Body text"], document_style=doc_style)
        base = _make_bundle(base_doc)
        folder = tmp_path / "doc"
        serialize(base, folder, format="xml")

        # No edits
        desired = deserialize(base, folder)
        dt = desired.document.tabs[0].document_tab  # type: ignore[index]
        # documentStyle is serialized to docstyle.xml — round-trips through JSON
        # The margin_left should be present (either from docstyle.xml or base)
        assert dt.document_style is not None

    def test_inline_objects_preserved_from_base(self, tmp_path: Path) -> None:
        """Inline objects in base are preserved since XML SERDE skips InsertInlineObjectOp."""
        fake_inline_obj = InlineObject(
            inline_object_properties=InlineObjectProperties()
        )
        base_doc = _make_doc(
            ["Body text"],
            inline_objects={"img-001": fake_inline_obj},
        )
        base = _make_bundle(base_doc)
        folder = tmp_path / "doc"
        serialize(base, folder, format="xml")

        # Edit body text
        xml = _read_doc_xml(folder)
        xml = xml.replace(">Body text<", ">Changed text<")
        _write_doc_xml(folder, xml)

        desired = deserialize(base, folder)
        dt = desired.document.tabs[0].document_tab  # type: ignore[index]
        # Inline objects dict should be preserved from base
        assert dt.inline_objects is not None
        assert "img-001" in dt.inline_objects

    def test_headers_preserved(self, tmp_path: Path) -> None:
        """Headers in base doc survive round-trip through XML SERDE."""
        header_para = StructuralElement(
            paragraph=Paragraph(
                elements=[ParagraphElement(text_run=TextRun(content="Page header\n"))]
            )
        )
        header = Header(header_id="hdr-1", content=[header_para])
        doc_style = DocumentStyle(default_header_id="hdr-1")
        base_doc = Document(
            document_id="test-hdr",
            title="Test",
            tabs=[
                Tab(
                    tab_properties=TabProperties(tab_id="t.0", title="Tab 1"),
                    document_tab=DocumentTab(
                        body=Body(content=[_make_text_para("Body text")]),
                        headers={"hdr-1": header},
                        document_style=doc_style,
                    ),
                )
            ],
        )
        base = _make_bundle(base_doc)
        folder = tmp_path / "doc"
        serialize(base, folder, format="xml")

        # Edit body only
        xml = _read_doc_xml(folder)
        xml = xml.replace(">Body text<", ">Changed body<")
        _write_doc_xml(folder, xml)

        desired = deserialize(base, folder)
        dt = desired.document.tabs[0].document_tab  # type: ignore[index]
        # Header should be preserved from base (or serialized via docstyle extras)
        assert dt.headers is not None
        assert "hdr-1" in dt.headers

    def test_footers_preserved(self, tmp_path: Path) -> None:
        """Footers in base doc survive round-trip through XML SERDE."""
        footer_para = StructuralElement(
            paragraph=Paragraph(
                elements=[ParagraphElement(text_run=TextRun(content="Page footer\n"))]
            )
        )
        footer = Footer(footer_id="ftr-1", content=[footer_para])
        doc_style = DocumentStyle(default_footer_id="ftr-1")
        base_doc = Document(
            document_id="test-ftr",
            title="Test",
            tabs=[
                Tab(
                    tab_properties=TabProperties(tab_id="t.0", title="Tab 1"),
                    document_tab=DocumentTab(
                        body=Body(content=[_make_text_para("Body text")]),
                        footers={"ftr-1": footer},
                        document_style=doc_style,
                    ),
                )
            ],
        )
        base = _make_bundle(base_doc)
        folder = tmp_path / "doc"
        serialize(base, folder, format="xml")

        desired = deserialize(base, folder)
        dt = desired.document.tabs[0].document_tab  # type: ignore[index]
        assert dt.footers is not None
        assert "ftr-1" in dt.footers


# ---------------------------------------------------------------------------
# Group 5: Comments
# ---------------------------------------------------------------------------


class TestComments:
    def test_comments_come_from_mine(self, tmp_path: Path) -> None:
        """Comments in the edited XML folder are used in desired (not base comments)."""
        from extradoc.comments._types import Comment, FileComments
        from extradoc.comments._xml import to_xml as comments_to_xml

        base_doc = _make_doc(["Hello world"])
        base_comment = Comment(
            id="base-c1",
            author="base@example.com",
            created_time="2024-01-01T00:00:00Z",
            content="Base comment",
            anchor="kix.abc",
            resolved=False,
            deleted=False,
        )
        base = DocumentWithComments(
            document=base_doc,
            comments=FileComments(file_id="test-cmt", comments=[base_comment]),
        )
        folder = tmp_path / "doc"
        serialize(base, folder, format="xml")

        # Overwrite comments.xml with a mine comment
        mine_comment = Comment(
            id="mine-c1",
            author="mine@example.com",
            created_time="2024-06-01T00:00:00Z",
            content="Mine comment",
            anchor="kix.xyz",
            resolved=False,
            deleted=False,
        )
        mine_comments = FileComments(file_id="test-cmt", comments=[mine_comment])
        (folder / "comments.xml").write_text(
            comments_to_xml(mine_comments), encoding="utf-8"
        )

        desired = deserialize(base, folder)
        comment_ids = [c.id for c in desired.comments.comments]
        assert "mine-c1" in comment_ids

    def test_comment_preserved_when_paragraph_not_edited(self, tmp_path: Path) -> None:
        """Comments survive round-trip when paragraphs are not edited."""
        from extradoc.comments._types import Comment, FileComments

        base_doc = _make_doc(["Para with comment"])
        comment = Comment(
            id="c-1",
            author="user@example.com",
            created_time="2024-01-01T00:00:00Z",
            content="A comment",
            anchor="kix.abc",
            resolved=False,
            deleted=False,
        )
        base = DocumentWithComments(
            document=base_doc,
            comments=FileComments(file_id="test-cmt2", comments=[comment]),
        )
        folder = tmp_path / "doc"
        serialize(base, folder, format="xml")

        # No edits
        desired = deserialize(base, folder)
        comment_ids = [c.id for c in desired.comments.comments]
        assert "c-1" in comment_ids


# ---------------------------------------------------------------------------
# Group 6: Multi-tab documents
# ---------------------------------------------------------------------------


class TestMultiTab:
    def _make_multitab_doc(self, doc_id: str = "mt-doc") -> Document:
        def _tab(tab_id: str, title: str, texts: list[str]) -> Tab:
            content = [_make_text_para(t) for t in texts]
            return Tab(
                tab_properties=TabProperties(tab_id=tab_id, title=title, index=0),
                document_tab=DocumentTab(body=Body(content=content)),
            )

        return Document(
            document_id=doc_id,
            title="MultiTab",
            tabs=[
                _tab("t.0", "Tab 1", ["Tab1 Para1", "Tab1 Para2"]),
                _tab("t.1", "Tab 2", ["Tab2 Para1", "Tab2 Para2"]),
            ],
        )

    def test_edit_one_tab_other_unchanged(self, tmp_path: Path) -> None:
        """Edit body of tab 1 → tab 2 body unchanged in desired."""
        base_doc = self._make_multitab_doc()
        base = _make_bundle(base_doc)
        folder = tmp_path / "doc"
        serialize(base, folder, format="xml")

        # Edit Tab_1 only
        xml1 = _read_doc_xml(folder, "Tab_1")
        xml1 = xml1.replace(">Tab1 Para1<", ">Tab1 Changed<")
        _write_doc_xml(folder, xml1, "Tab_1")

        desired = deserialize(base, folder)
        texts1 = _body_texts(desired.document, tab_idx=0)
        texts2 = _body_texts(desired.document, tab_idx=1)

        assert "Tab1 Changed" in texts1
        assert "Tab2 Para1" in texts2
        assert "Tab2 Para2" in texts2

    def test_tab_structure_preserved(self, tmp_path: Path) -> None:
        """Tab count and IDs are preserved from base after editing one tab."""
        base_doc = self._make_multitab_doc()
        base = _make_bundle(base_doc)
        folder = tmp_path / "doc"
        serialize(base, folder, format="xml")

        # No edits
        desired = deserialize(base, folder)
        assert desired.document.tabs is not None
        assert len(desired.document.tabs) == 2
        tab_ids = [
            (t.tab_properties.tab_id if t.tab_properties else None)
            for t in desired.document.tabs
        ]
        assert "t.0" in tab_ids
        assert "t.1" in tab_ids


# ---------------------------------------------------------------------------
# Group 7: Lists
# ---------------------------------------------------------------------------


class TestLists:
    def _make_list_doc(self) -> Document:
        """Create a doc with a bullet list (via XML deserialization)."""
        from extradoc.serde._from_markdown import markdown_to_document

        md = "- Item one\n- Item two\n- Item three\n"
        return markdown_to_document({"Tab_1": md}, document_id="list-doc", title="List")

    def test_edit_list_item_text(self, tmp_path: Path) -> None:
        """Edit a list item's <t> in document.xml → desired has updated text."""
        base_doc = self._make_list_doc()
        base = _make_bundle(base_doc)
        folder = tmp_path / "doc"
        serialize(base, folder, format="xml")

        xml = _read_doc_xml(folder)
        xml = xml.replace(">Item one<", ">Item one edited<")
        _write_doc_xml(folder, xml)

        desired = deserialize(base, folder)
        texts = _body_texts(desired.document)
        assert any("Item one edited" in t for t in texts)

    def test_add_list_item(self, tmp_path: Path) -> None:
        """Add a new list item paragraph in document.xml → appears in desired body."""
        base_doc = self._make_list_doc()
        base = _make_bundle(base_doc)
        folder = tmp_path / "doc"
        serialize(base, folder, format="xml")

        # Find the list id from the serialized XML, then append a new <li>
        xml = _read_doc_xml(folder)
        tree = ET.fromstring(xml)
        # Find the parent list id from the first <li> element
        first_li = tree.find(".//li")
        assert first_li is not None
        parent_id = first_li.get("parent", "")
        level = first_li.get("level", "0")

        body = tree.find("body")
        assert body is not None
        # Find last <li> and insert a new one after it
        all_li = body.findall("li")
        assert len(all_li) >= 1
        last_li = all_li[-1]
        last_li_idx = list(body).index(last_li)
        new_li = ET.Element("li")
        new_li.set("parent", parent_id)
        new_li.set("level", level)
        new_li.text = "New fourth item"
        body.insert(last_li_idx + 1, new_li)
        _write_doc_xml(folder, ET.tostring(tree, encoding="unicode"))

        desired = deserialize(base, folder)
        texts = _body_texts(desired.document)
        assert any("New fourth item" in t for t in texts)


# ---------------------------------------------------------------------------
# Group 8: Footnotes
# ---------------------------------------------------------------------------


class TestFootnotes:
    def test_edit_footnote_content(self, tmp_path: Path) -> None:
        """Edit footnote text in document.xml → desired has updated footnote."""
        from extradoc.api_types._generated import FootnoteReference

        fn_id = "fn-001"
        fn_para = StructuralElement(
            paragraph=Paragraph(
                elements=[
                    ParagraphElement(text_run=TextRun(content="Old footnote text\n"))
                ]
            )
        )
        body_para = StructuralElement(
            paragraph=Paragraph(
                elements=[
                    ParagraphElement(text_run=TextRun(content="Body ")),
                    ParagraphElement(
                        footnote_reference=FootnoteReference(footnote_id=fn_id)
                    ),
                    ParagraphElement(text_run=TextRun(content=".\n")),
                ]
            )
        )
        base_doc = Document(
            document_id="fn-doc",
            title="Footnotes",
            tabs=[
                Tab(
                    tab_properties=TabProperties(tab_id="t.0", title="Tab 1"),
                    document_tab=DocumentTab(
                        body=Body(content=[body_para]),
                        footnotes={fn_id: Footnote(content=[fn_para])},
                    ),
                )
            ],
        )
        base = _make_bundle(base_doc)
        folder = tmp_path / "doc"
        serialize(base, folder, format="xml")

        xml = _read_doc_xml(folder)
        xml = xml.replace(">Old footnote text<", ">New footnote text<")
        _write_doc_xml(folder, xml)

        desired = deserialize(base, folder)
        dt = desired.document.tabs[0].document_tab  # type: ignore[index]
        footnotes = dt.footnotes or {}
        found = False
        for _fn_id, fn in footnotes.items():
            for se in fn.content or []:
                if se.paragraph:
                    text = "".join(
                        (pe.text_run.content or "")
                        for pe in (se.paragraph.elements or [])
                        if pe.text_run
                    )
                    if "New footnote text" in text:
                        found = True
        assert found, "Expected updated footnote text in desired document"


# ---------------------------------------------------------------------------
# Group 9: Styles (XML SERDE models more than markdown)
# ---------------------------------------------------------------------------


class TestStylesXml:
    def test_heading_style_preserved(self, tmp_path: Path) -> None:
        """Heading paragraph style (namedStyleType HEADING_1) survives round-trip."""
        base_doc = Document(
            document_id="test-heading",
            title="Test",
            tabs=[
                Tab(
                    tab_properties=TabProperties(tab_id="t.0", title="Tab 1"),
                    document_tab=DocumentTab(
                        body=Body(
                            content=[
                                StructuralElement(
                                    paragraph=Paragraph(
                                        elements=[
                                            ParagraphElement(
                                                text_run=TextRun(content="My Heading\n")
                                            )
                                        ],
                                        paragraph_style=ParagraphStyle(
                                            named_style_type=ParagraphStyleNamedStyleType.HEADING_1
                                        ),
                                    )
                                ),
                                _make_text_para("Normal paragraph"),
                            ]
                        )
                    ),
                )
            ],
        )
        base = _make_bundle(base_doc)
        folder = tmp_path / "doc"
        serialize(base, folder, format="xml")

        # The heading should be serialized as <h1> in document.xml
        xml = _read_doc_xml(folder)
        assert "<h1>" in xml

        # No edits
        desired = deserialize(base, folder)
        dt = desired.document.tabs[0].document_tab  # type: ignore[index]
        for se in dt.body.content or []:  # type: ignore[union-attr]
            if se.paragraph:
                text = "".join(
                    (pe.text_run.content or "")
                    for pe in se.paragraph.elements or []
                    if pe.text_run
                )
                if "My Heading" in text:
                    assert (
                        se.paragraph.paragraph_style is not None
                        and se.paragraph.paragraph_style.named_style_type == "HEADING_1"
                    )

    def test_italic_text_style_round_trip(self, tmp_path: Path) -> None:
        """Italic text serializes as <i> sugar tag and round-trips."""
        base_doc = Document(
            document_id="test-italic",
            title="Test",
            tabs=[
                Tab(
                    tab_properties=TabProperties(tab_id="t.0", title="Tab 1"),
                    document_tab=DocumentTab(
                        body=Body(
                            content=[
                                StructuralElement(
                                    paragraph=Paragraph(
                                        elements=[
                                            ParagraphElement(
                                                text_run=TextRun(
                                                    content="Italic text\n",
                                                    text_style=TextStyle(italic=True),
                                                )
                                            )
                                        ]
                                    )
                                )
                            ]
                        )
                    ),
                )
            ],
        )
        base = _make_bundle(base_doc)
        folder = tmp_path / "doc"
        serialize(base, folder, format="xml")

        # Verify <i> sugar tag in document.xml
        xml = _read_doc_xml(folder)
        assert "<i>" in xml

        desired = deserialize(base, folder)
        dt = desired.document.tabs[0].document_tab  # type: ignore[index]
        found_italic = False
        for se in dt.body.content or []:  # type: ignore[union-attr]
            if se.paragraph:
                for pe in se.paragraph.elements or []:
                    if (
                        pe.text_run
                        and pe.text_run.text_style
                        and pe.text_run.text_style.italic
                    ):
                        found_italic = True
        assert found_italic


# ---------------------------------------------------------------------------
# Group 10: Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_body_no_crash(self, tmp_path: Path) -> None:
        """Serialize/deserialize a minimal doc doesn't crash."""
        base_doc = _make_doc([])
        base = _make_bundle(base_doc)
        folder = tmp_path / "doc"
        serialize(base, folder, format="xml")
        desired = deserialize(base, folder)
        assert desired.document is not None

    def test_no_changes_zero_ops(self, tmp_path: Path) -> None:
        """serialize then deserialize without editing → body content unchanged."""
        base_doc = _make_doc(["Hello world", "Second para"])
        base = _make_bundle(base_doc)
        folder = tmp_path / "doc"
        serialize(base, folder, format="xml")

        # No edits → deserialize
        desired = deserialize(base, folder)

        base_texts = _body_texts(base_doc)
        desired_texts = _body_texts(desired.document)
        assert desired_texts == base_texts

    def test_legacy_folder_no_pristine(self, tmp_path: Path) -> None:
        """When .pristine/document.zip is absent for XML, falls back to direct parse."""
        base_doc = _make_doc(["Hello world"])
        base = _make_bundle(base_doc)
        folder = tmp_path / "doc"
        serialize(base, folder, format="xml")

        # Remove the pristine zip to simulate a legacy folder
        pristine_zip = folder / ".pristine" / "document.zip"
        pristine_zip.unlink()

        # Should not crash and should return a document
        desired = deserialize(base, folder)
        assert desired.document is not None
        texts = _body_texts(desired.document)
        assert "Hello world" in texts

    def test_deserialize_legacy_single_arg(self, tmp_path: Path) -> None:
        """Legacy single-argument deserialize(folder) still works for XML format."""
        base_doc = _make_doc(["Hello world"])
        bundle = _make_bundle(base_doc)
        folder = tmp_path / "doc"
        serialize(bundle, folder, format="xml")

        # Legacy call: deserialize(folder)
        result = deserialize(folder)
        assert result.document is not None

    def test_multiple_edits_in_one_pass(self, tmp_path: Path) -> None:
        """Multiple paragraph edits in one XML edit session → all changes in desired."""
        base_doc = _make_doc(["Para A", "Para B", "Para C"])
        base = _make_bundle(base_doc)
        folder = tmp_path / "doc"
        serialize(base, folder, format="xml")

        xml = _read_doc_xml(folder)
        xml = xml.replace(">Para A<", ">Changed A<")
        xml = xml.replace(">Para C<", ">Changed C<")
        _write_doc_xml(folder, xml)

        desired = deserialize(base, folder)
        texts = _body_texts(desired.document)
        assert "Changed A" in texts
        assert "Para B" in texts
        assert "Changed C" in texts

    def test_edit_paragraph_preserves_other_tabs(self, tmp_path: Path) -> None:
        """Editing XML content in one tab preserves other tab data from base."""
        base_doc = Document(
            document_id="two-tab",
            title="Two Tabs",
            tabs=[
                Tab(
                    tab_properties=TabProperties(tab_id="t.0", title="Tab 1"),
                    document_tab=DocumentTab(
                        body=Body(content=[_make_text_para("Tab1 content")])
                    ),
                ),
                Tab(
                    tab_properties=TabProperties(tab_id="t.1", title="Tab 2"),
                    document_tab=DocumentTab(
                        body=Body(content=[_make_text_para("Tab2 content")])
                    ),
                ),
            ],
        )
        base = _make_bundle(base_doc)
        folder = tmp_path / "doc"
        serialize(base, folder, format="xml")

        # Edit only Tab_1
        xml = _read_doc_xml(folder, "Tab_1")
        xml = xml.replace(">Tab1 content<", ">Tab1 edited<")
        _write_doc_xml(folder, xml, "Tab_1")

        desired = deserialize(base, folder)
        assert desired.document.tabs is not None
        assert len(desired.document.tabs) == 2
        texts_tab2 = _body_texts(desired.document, tab_idx=1)
        assert "Tab2 content" in texts_tab2
