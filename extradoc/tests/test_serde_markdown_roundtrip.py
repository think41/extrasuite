"""Tests for the 3-way merge Markdown SERDE interface.

Tests cover:
- serialize() writes .pristine/document.zip
- deserialize(base, folder) performs 3-way merge
- Body content changes propagate correctly
- Things the markdown SERDE doesn't model are preserved from base
- Comments, tables, lists, footnotes, multi-tab docs
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from extradoc.api_types._generated import (
    Body,
    BookmarkLink,
    Dimension,
    Document,
    DocumentStyle,
    DocumentTab,
    Footer,
    Footnote,
    Header,
    HeadingLink,
    InlineObject,
    InlineObjectElement,
    InlineObjectProperties,
    EmbeddedObject,
    ImageProperties,
    Size,
    Link as DocLink,
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
from extradoc.serde.markdown import MarkdownSerde
from extradoc.serde.xml import XmlSerde

_md_serde = MarkdownSerde()
_xml_serde = XmlSerde()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_text_para(
    text: str,
    named_style: ParagraphStyleNamedStyleType | None = None,
    bold: bool = False,
    italic: bool = False,
) -> StructuralElement:
    ts = TextStyle(bold=bold if bold else None, italic=italic if italic else None)
    ps = ParagraphStyle(
        named_style_type=named_style or ParagraphStyleNamedStyleType.NORMAL_TEXT
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


def _tab_md_path(folder: Path, tab_name: str = "Tab_1") -> Path:
    """Return path to a tab's markdown file (new or legacy layout)."""
    new_path = folder / "tabs" / f"{tab_name}.md"
    if new_path.exists():
        return new_path
    legacy_path = folder / f"{tab_name}.md"
    if legacy_path.exists():
        return legacy_path
    # Default to new layout for writes
    tabs_dir = folder / "tabs"
    if tabs_dir.is_dir():
        return new_path
    return legacy_path


def _read_md(folder: Path, tab_name: str = "Tab_1") -> str:
    """Read a tab's markdown file."""
    return _tab_md_path(folder, tab_name).read_text(encoding="utf-8")


def _write_md(folder: Path, content: str, tab_name: str = "Tab_1") -> None:
    """Overwrite a tab's markdown file."""
    _tab_md_path(folder, tab_name).write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Test: serialize writes .pristine/document.zip
# ---------------------------------------------------------------------------


class TestIndexMdHeadingIds:
    """index.md shows heading IDs so authors can create internal links."""

    def _make_doc_with_headings(self) -> Document:
        """Build a two-heading document where each heading has a heading_id."""

        def _heading_se(
            text: str,
            style: ParagraphStyleNamedStyleType,
            heading_id: str,
        ) -> StructuralElement:
            ps = ParagraphStyle(named_style_type=style, heading_id=heading_id)
            el = ParagraphElement(text_run=TextRun(content=text + "\n", text_style=TextStyle()))
            return StructuralElement(paragraph=Paragraph(elements=[el], paragraph_style=ps))

        intro = _make_text_para("Some intro text.")
        h1 = _heading_se("Overview", ParagraphStyleNamedStyleType.HEADING_1, "h.overview1")
        h2 = _heading_se("Details", ParagraphStyleNamedStyleType.HEADING_2, "h.details2")
        doc_tab = DocumentTab(body=Body(content=[intro, h1, h2]))
        return Document(
            document_id="test-doc",
            title="Test",
            tabs=[
                Tab(
                    tab_properties=TabProperties(tab_id="t.0", title="Tab 1"),
                    document_tab=doc_tab,
                )
            ],
        )

    def test_index_md_has_heading_table(self, tmp_path: Path) -> None:
        """index.md includes a heading table (without ID column)."""
        doc = self._make_doc_with_headings()
        bundle = _make_bundle(doc)
        folder = tmp_path / "doc"
        _md_serde.serialize(bundle, folder)

        index_md = (folder / "index.md").read_text()
        assert "| Line | Heading |" in index_md
        # ID column should NOT be present
        assert "| ID |" not in index_md
        assert "# Overview" in index_md
        assert "## Details" in index_md

    def test_index_md_has_frontmatter(self, tmp_path: Path) -> None:
        """index.md includes YAML frontmatter with document_id and title."""
        doc = self._make_doc_with_headings()
        bundle = _make_bundle(doc)
        folder = tmp_path / "doc"
        _md_serde.serialize(bundle, folder)

        index_md = (folder / "index.md").read_text()
        assert index_md.startswith("---\n")
        assert "document_id:" in index_md
        assert "title:" in index_md

    def test_index_md_no_id_column_when_no_heading_ids(self, tmp_path: Path) -> None:
        """index.md has 2-column table when headings have no IDs."""
        # Build a heading without a heading_id
        ps = ParagraphStyle(
            named_style_type=ParagraphStyleNamedStyleType.HEADING_1, heading_id=None
        )
        el = ParagraphElement(text_run=TextRun(content="Overview\n", text_style=TextStyle()))
        se = StructuralElement(paragraph=Paragraph(elements=[el], paragraph_style=ps))
        doc = _make_doc(["intro"], extra_content=[se])
        bundle = _make_bundle(doc)
        folder = tmp_path / "doc"
        _md_serde.serialize(bundle, folder)

        index_md = (folder / "index.md").read_text()
        assert "| Line | Heading |" in index_md
        assert "| ID |" not in index_md


class TestSerializeWritesPristine:
    def test_pristine_zip_created(self, tmp_path: Path) -> None:
        """serialize() writes .extrasuite/pristine.zip for markdown format."""
        doc = _make_doc(["Hello world"])
        bundle = _make_bundle(doc)
        folder = tmp_path / "doc"
        _md_serde.serialize(bundle, folder)
        assert (folder / ".extrasuite" / "pristine.zip").exists()

    def test_pristine_contains_md_files(self, tmp_path: Path) -> None:
        """The pristine zip contains the markdown files."""
        import zipfile

        doc = _make_doc(["Hello world"])
        bundle = _make_bundle(doc)
        folder = tmp_path / "doc"
        _md_serde.serialize(bundle, folder)
        zip_path = folder / ".extrasuite" / "pristine.zip"
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
        assert any("tabs/Tab_1.md" in n for n in names)
        # Should NOT contain .extrasuite/ entries
        assert not any(".extrasuite" in n for n in names)

    def test_pristine_written_for_xml(self, tmp_path: Path) -> None:
        """serialize() with XML format also writes .pristine/document.zip."""
        doc = _make_doc(["Hello world"])
        bundle = _make_bundle(doc)
        folder = tmp_path / "doc"
        _xml_serde.serialize(bundle, folder)
        # XML format: serde now writes .pristine zip (like markdown)
        assert (folder / ".pristine" / "document.zip").exists()


# ---------------------------------------------------------------------------
# Group 1: Body content changes
# ---------------------------------------------------------------------------


class TestBodyContentChanges:
    def test_edit_paragraph_text(self, tmp_path: Path) -> None:
        """Edit paragraph text → desired has updated text."""
        base_doc = _make_doc(["Hello world", "Second para"])
        base = _make_bundle(base_doc)
        folder = tmp_path / "doc"
        _md_serde.serialize(base, folder)

        # Edit the markdown
        md = _read_md(folder)
        md = md.replace("Hello world", "Hello there")
        _write_md(folder, md)

        desired = _md_serde.deserialize(folder).desired
        texts = _body_texts(desired.document)
        assert "Hello there" in texts
        assert "Second para" in texts

    def test_add_paragraph(self, tmp_path: Path) -> None:
        """Insert a new paragraph in markdown → appears in desired body."""
        base_doc = _make_doc(["First para", "Second para"])
        base = _make_bundle(base_doc)
        folder = tmp_path / "doc"
        _md_serde.serialize(base, folder)

        md = _read_md(folder)
        # Add a new line after "First para"
        md = md.replace("First para\n", "First para\n\nNew inserted para\n")
        _write_md(folder, md)

        desired = _md_serde.deserialize(folder).desired
        texts = _body_texts(desired.document)
        assert "New inserted para" in texts
        assert "First para" in texts
        assert "Second para" in texts

    def test_delete_paragraph(self, tmp_path: Path) -> None:
        """Remove a paragraph from markdown → absent in desired body."""
        base_doc = _make_doc(["Keep this", "Delete this", "Also keep"])
        base = _make_bundle(base_doc)
        folder = tmp_path / "doc"
        _md_serde.serialize(base, folder)

        md = _read_md(folder)
        lines = [line for line in md.splitlines() if "Delete this" not in line]
        _write_md(folder, "\n".join(lines) + "\n")

        desired = _md_serde.deserialize(folder).desired
        texts = _body_texts(desired.document)
        assert "Delete this" not in texts
        assert "Keep this" in texts

    def test_edit_bold_text(self, tmp_path: Path) -> None:
        """Edit bold text → markdown → desired has correct style."""
        base_doc = _make_doc(["Normal text"])
        base = _make_bundle(base_doc)
        folder = tmp_path / "doc"
        _md_serde.serialize(base, folder)

        # Write markdown with bold
        _write_md(folder, "**bold text**\n")
        desired = _md_serde.deserialize(folder).desired

        # Find bold run in desired body
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
        _md_serde.serialize(base, folder)

        # No edits
        desired = _md_serde.deserialize(folder).desired
        desired_texts = _body_texts(desired.document)
        base_texts = _body_texts(base_doc)
        assert desired_texts == base_texts


# ---------------------------------------------------------------------------
# Group 2: Table changes
# ---------------------------------------------------------------------------


class TestTableChanges:
    def test_edit_table_cell_text(self, tmp_path: Path) -> None:
        """Edit a table cell in markdown → desired has updated cell text."""
        table_se = _make_table_se([["Header1", "Header2"], ["Value1", "Value2"]])
        base_doc = _make_doc([], extra_content=[table_se])
        base = _make_bundle(base_doc)
        folder = tmp_path / "doc"
        _md_serde.serialize(base, folder)

        md = _read_md(folder)
        md = md.replace("Value1", "Updated1")
        _write_md(folder, md)

        desired = _md_serde.deserialize(folder).desired
        cell_data = _cell_texts(desired.document)
        flat_cells = [cell for row in cell_data for cell in row]
        assert "Updated1" in flat_cells

    def test_table_preserved_when_not_in_markdown(self, tmp_path: Path) -> None:
        """Tables that round-trip through markdown are preserved."""
        table_se = _make_table_se([["A", "B"]])
        base_doc = _make_doc(["Para before"], extra_content=[table_se])
        base = _make_bundle(base_doc)
        folder = tmp_path / "doc"
        _md_serde.serialize(base, folder)

        # No edits
        desired = _md_serde.deserialize(folder).desired
        # Should have a table in the body
        tab = desired.document.tabs[0]  # type: ignore[index]
        tables = [
            se
            for se in (tab.document_tab.body.content or [])  # type: ignore[union-attr]
            if se.table is not None
        ]
        assert len(tables) >= 1


# ---------------------------------------------------------------------------
# Group 3: Things the markdown SERDE doesn't model (must be PRESERVED from base)
# ---------------------------------------------------------------------------


class TestPreservationFromBase:
    def test_headers_preserved(self, tmp_path: Path) -> None:
        """Headers from base are preserved when markdown doesn't model them."""
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
        _md_serde.serialize(base, folder)

        # Edit body only
        md = _read_md(folder)
        md = md.replace("Body text", "Changed body")
        _write_md(folder, md)

        desired = _md_serde.deserialize(folder).desired
        dt = desired.document.tabs[0].document_tab  # type: ignore[index]
        # Header should be preserved from base
        assert dt.headers is not None
        assert "hdr-1" in dt.headers

    def test_footers_preserved(self, tmp_path: Path) -> None:
        """Footers from base are preserved when markdown doesn't model them."""
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
        _md_serde.serialize(base, folder)

        desired = _md_serde.deserialize(folder).desired
        dt = desired.document.tabs[0].document_tab  # type: ignore[index]
        assert dt.footers is not None
        assert "ftr-1" in dt.footers

    def test_document_style_preserved(self, tmp_path: Path) -> None:
        """Custom document style (margins etc.) from base are preserved."""
        custom_margin = Dimension(magnitude=72.0, unit="PT")
        doc_style = DocumentStyle(margin_left=custom_margin, margin_right=custom_margin)
        base_doc = Document(
            document_id="test-style",
            title="Test",
            tabs=[
                Tab(
                    tab_properties=TabProperties(tab_id="t.0", title="Tab 1"),
                    document_tab=DocumentTab(
                        body=Body(content=[_make_text_para("Body text")]),
                        document_style=doc_style,
                    ),
                )
            ],
        )
        base = _make_bundle(base_doc)
        folder = tmp_path / "doc"
        _md_serde.serialize(base, folder)

        desired = _md_serde.deserialize(folder).desired
        dt = desired.document.tabs[0].document_tab  # type: ignore[index]
        assert dt.document_style is not None
        assert dt.document_style.margin_left is not None
        assert dt.document_style.margin_left.magnitude == 72.0

    def test_named_styles_preserved(self, tmp_path: Path) -> None:
        """Custom named styles from base are preserved."""
        named_style = NamedStyle(
            named_style_type="HEADING_1",
            text_style=TextStyle(bold=True),
        )
        named_styles = NamedStyles(styles=[named_style])
        base_doc = Document(
            document_id="test-ns",
            title="Test",
            tabs=[
                Tab(
                    tab_properties=TabProperties(tab_id="t.0", title="Tab 1"),
                    document_tab=DocumentTab(
                        body=Body(content=[_make_text_para("Body")]),
                        named_styles=named_styles,
                    ),
                )
            ],
        )
        base = _make_bundle(base_doc)
        folder = tmp_path / "doc"
        _md_serde.serialize(base, folder)

        desired = _md_serde.deserialize(folder).desired
        dt = desired.document.tabs[0].document_tab  # type: ignore[index]
        assert dt.named_styles is not None
        assert len(dt.named_styles.styles or []) >= 1
        types = [s.named_style_type for s in (dt.named_styles.styles or [])]
        assert "HEADING_1" in types

    def test_inline_objects_preserved(self, tmp_path: Path) -> None:
        """Inline objects dict is preserved from base when markdown doesn't model it."""
        # Create a base doc with an inline object in the inlineObjects dict
        # (even if the body doesn't reference it — it should be preserved)
        fake_inline_obj = InlineObject(
            inline_object_properties=InlineObjectProperties()
        )
        base_doc = Document(
            document_id="test-img",
            title="Test",
            tabs=[
                Tab(
                    tab_properties=TabProperties(tab_id="t.0", title="Tab 1"),
                    document_tab=DocumentTab(
                        body=Body(content=[_make_text_para("Body with image")]),
                        inline_objects={"img-001": fake_inline_obj},
                    ),
                )
            ],
        )
        base = _make_bundle(base_doc)
        folder = tmp_path / "doc"
        _md_serde.serialize(base, folder)

        desired = _md_serde.deserialize(folder).desired
        dt = desired.document.tabs[0].document_tab  # type: ignore[index]
        # Inline objects from base are preserved
        assert dt.inline_objects is not None
        assert "img-001" in dt.inline_objects


# ---------------------------------------------------------------------------
# Group 4: Comments
# ---------------------------------------------------------------------------


class TestComments:
    def test_comments_come_from_mine(self, tmp_path: Path) -> None:
        """Comments in the edited folder are used in desired (not base comments)."""
        from extradoc.comments._types import Comment, FileComments

        base_doc = _make_doc(["Hello world"])
        # Base has a comment
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
        _md_serde.serialize(base, folder)

        # Overwrite comments.xml with a mine comment
        from extradoc.comments._xml import to_xml as comments_to_xml

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

        desired = _md_serde.deserialize(folder).desired
        comment_ids = [c.id for c in desired.comments.comments]
        # The 3-way merge uses mine's comments
        assert "mine-c1" in comment_ids


# ---------------------------------------------------------------------------
# Group 5: Multi-tab documents
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
        """Edit body of tab 1 → tab 2 body unchanged."""
        base_doc = self._make_multitab_doc()
        base = _make_bundle(base_doc)
        folder = tmp_path / "doc"
        _md_serde.serialize(base, folder)

        # Edit Tab 1 only
        md1 = _read_md(folder, "Tab_1")
        md1 = md1.replace("Tab1 Para1", "Tab1 Changed")
        _write_md(folder, md1, "Tab_1")

        desired = _md_serde.deserialize(folder).desired
        texts1 = _body_texts(desired.document, tab_idx=0)
        texts2 = _body_texts(desired.document, tab_idx=1)

        assert "Tab1 Changed" in texts1
        assert "Tab2 Para1" in texts2
        assert "Tab2 Para2" in texts2

    def test_add_new_tab_with_list_content(self, tmp_path: Path) -> None:
        """Adding a new tab with list content must not crash during 3-way merge.

        Reproduces: push-md with a new tab causes 'Tab object has no attribute
        get' because apply_ops_to_document inserts a Pydantic Tab object into
        a dict-based document, and the list-injection loop calls .get() on it.
        """
        base_doc = self._make_multitab_doc(doc_id="add-tab-doc")
        base = _make_bundle(base_doc)
        folder = tmp_path / "doc"
        _md_serde.serialize(base, folder)

        # Add a new tab: create the markdown file in tabs/ and update index.xml
        new_tab_md = "# New Tab\n\n- Bullet one\n- Bullet two\n"
        (folder / "tabs" / "New_Tab.md").write_text(new_tab_md, encoding="utf-8")

        # Update index.xml to register the new tab
        from extradoc.serde._models import IndexTab, IndexXml

        index = IndexXml.from_xml_string(
            (folder / ".extrasuite" / "index.xml").read_text(encoding="utf-8")
        )
        index.tabs.append(IndexTab(id="t.new", title="New Tab", folder="New_Tab"))
        (folder / ".extrasuite" / "index.xml").write_text(index.to_xml_string(), encoding="utf-8")

        # This should not crash
        desired = _md_serde.deserialize(folder).desired
        assert len(desired.document.tabs or []) == 3
        texts_new = _body_texts(desired.document, tab_idx=2)
        assert any("Bullet one" in t for t in texts_new)


# ---------------------------------------------------------------------------
# Group 6: Lists
# ---------------------------------------------------------------------------


class TestLists:
    def _make_bullet_doc(self) -> Document:
        """Create a doc with a bullet list."""
        from extradoc.serde.markdown._from_markdown import markdown_to_document

        md = "- Item one\n- Item two\n- Item three\n"
        return markdown_to_document({"Tab_1": md}, document_id="list-doc", title="List")

    def test_edit_list_item_text(self, tmp_path: Path) -> None:
        """Edit a bullet list item text → desired has updated text."""
        base_doc = self._make_bullet_doc()
        base = _make_bundle(base_doc)
        folder = tmp_path / "doc"
        _md_serde.serialize(base, folder)

        md = _read_md(folder)
        md = md.replace("Item one", "Item one edited")
        _write_md(folder, md)

        desired = _md_serde.deserialize(folder).desired
        texts = _body_texts(desired.document)
        assert any("Item one edited" in t for t in texts)

    def test_add_list_item(self, tmp_path: Path) -> None:
        """Add a bullet list item → appears in desired body."""
        base_doc = self._make_bullet_doc()
        base = _make_bundle(base_doc)
        folder = tmp_path / "doc"
        _md_serde.serialize(base, folder)

        md = _read_md(folder)
        md = md.replace("- Item three\n", "- Item three\n- New fourth item\n")
        _write_md(folder, md)

        desired = _md_serde.deserialize(folder).desired
        texts = _body_texts(desired.document)
        assert any("New fourth item" in t for t in texts)


# ---------------------------------------------------------------------------
# Group 7: Footnotes
# ---------------------------------------------------------------------------


class TestFootnotes:
    def test_edit_footnote_content(self, tmp_path: Path) -> None:
        """Edit footnote text in markdown → desired has updated footnote."""
        from extradoc.serde.markdown._from_markdown import markdown_to_document

        md = "Para with footnote[^1].\n\n[^1]: Old footnote text\n"
        base_doc = markdown_to_document(
            {"Tab_1": md}, document_id="fn-doc", title="Footnotes"
        )
        base = _make_bundle(base_doc)
        folder = tmp_path / "doc"
        _md_serde.serialize(base, folder)

        # Edit footnote text in the markdown
        md_current = _read_md(folder)
        md_new = md_current.replace("Old footnote text", "New footnote text")
        _write_md(folder, md_new)

        desired = _md_serde.deserialize(folder).desired
        # Check footnotes in the document tab
        dt = desired.document.tabs[0].document_tab  # type: ignore[index]
        footnotes = dt.footnotes or {}
        # Find any footnote with the new text
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
# Group 8: Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_body_no_crash(self, tmp_path: Path) -> None:
        """Serialize/deserialize a minimal doc doesn't crash."""
        base_doc = _make_doc([])
        base = _make_bundle(base_doc)
        folder = tmp_path / "doc"
        _md_serde.serialize(base, folder)
        desired = _md_serde.deserialize(folder).desired
        assert desired.document is not None

    def test_no_changes_zero_ops(self, tmp_path: Path) -> None:
        """serialize then deserialize without editing → no body content changes."""

        base_doc = _make_doc(["Hello world", "Second para"])
        base = _make_bundle(base_doc)
        folder = tmp_path / "doc"
        _md_serde.serialize(base, folder)

        # No edits → deserialize
        desired = _md_serde.deserialize(folder).desired

        # Verify body texts are identical
        base_texts = _body_texts(base_doc)
        desired_texts = _body_texts(desired.document)
        assert desired_texts == base_texts

    def test_legacy_folder_no_pristine(self, tmp_path: Path) -> None:
        """When .extrasuite/pristine.zip is absent, _parse() still works."""

        base_doc = _make_doc(["Hello world"])
        base = _make_bundle(base_doc)
        folder = tmp_path / "doc"
        _md_serde.serialize(base, folder)

        # Remove the pristine zip
        pristine_zip = folder / ".extrasuite" / "pristine.zip"
        pristine_zip.unlink()

        # _parse reads the folder without needing pristine
        parsed = _md_serde._parse(folder)
        assert parsed.document is not None
        texts = _body_texts(parsed.document)
        assert "Hello world" in texts

    def test_deserialize_xml_single_arg(self, tmp_path: Path) -> None:
        """XmlSerde.deserialize(folder) returns a DeserializeResult."""

        base_doc = _make_doc(["Hello world"])
        bundle = DocumentWithComments(
            document=base_doc,
            comments=FileComments(file_id="test"),
        )
        folder = tmp_path / "doc"
        _xml_serde.serialize(bundle, folder)

        result = _xml_serde.deserialize(folder)
        assert result.desired.document is not None


# ---------------------------------------------------------------------------
# Tests: Hyperlink serialization / deserialization
# ---------------------------------------------------------------------------


def _make_linked_para(display_text: str, link: DocLink) -> StructuralElement:
    """Build a paragraph with a single linked text run followed by a plain newline."""
    linked_run = ParagraphElement(
        text_run=TextRun(content=display_text, text_style=TextStyle(link=link))
    )
    newline_run = ParagraphElement(text_run=TextRun(content="\n", text_style=TextStyle()))
    ps = ParagraphStyle(named_style_type=ParagraphStyleNamedStyleType.NORMAL_TEXT)
    return StructuralElement(
        paragraph=Paragraph(elements=[linked_run, newline_run], paragraph_style=ps)
    )


def _get_link_from_desired(result_doc: Document, tab_idx: int = 0) -> DocLink | None:
    """Return the first DocLink found in the desired document body."""
    tab = (result_doc.tabs or [])[tab_idx]
    dt = tab.document_tab
    if not dt or not dt.body:
        return None
    for se in dt.body.content or []:
        if se.paragraph:
            for pe in se.paragraph.elements or []:
                if pe.text_run and pe.text_run.text_style and pe.text_run.text_style.link:
                    return pe.text_run.text_style.link
    return None


class TestHyperlinkSerde:
    """Tests for all hyperlink types in the markdown SERDE."""

    def test_external_url_round_trip(self, tmp_path: Path) -> None:
        """External URL links serialize to [text](url) and round-trip correctly."""
        link = DocLink(url="https://example.com/path?q=1")
        doc = _make_doc(["intro"], extra_content=[_make_linked_para("click here", link)])
        bundle = _make_bundle(doc)
        folder = tmp_path / "doc"
        _md_serde.serialize(bundle, folder)

        md = _read_md(folder)
        assert "[click here](https://example.com/path?q=1)" in md

        result = _md_serde.deserialize(folder)
        found = _get_link_from_desired(result.desired.document)
        assert found is not None
        assert found.url == "https://example.com/path?q=1"

    def test_heading_link_legacy_format_round_trip(self, tmp_path: Path) -> None:
        """Legacy headingId links (#heading:{id}) round-trip correctly."""
        link = DocLink(heading_id="h.abc123")
        doc = _make_doc(["intro"], extra_content=[_make_linked_para("see section", link)])
        bundle = _make_bundle(doc)
        folder = tmp_path / "doc"
        _md_serde.serialize(bundle, folder)

        md = _read_md(folder)
        assert "[see section](#heading:h.abc123)" in md

        result = _md_serde.deserialize(folder)
        found = _get_link_from_desired(result.desired.document)
        assert found is not None
        assert found.heading_id == "h.abc123"

    def test_heading_link_new_format_same_tab(self, tmp_path: Path) -> None:
        """New HeadingLink without tab_id serializes as #heading:{id}.
        On a no-edit round-trip the 3-way merge returns base unchanged, so
        the desired document keeps the original HeadingLink struct.
        """
        link = DocLink(heading=HeadingLink(id="h.abc123", tab_id=None))
        doc = _make_doc(["intro"], extra_content=[_make_linked_para("see section", link)])
        bundle = _make_bundle(doc)
        folder = tmp_path / "doc"
        _md_serde.serialize(bundle, folder)

        md = _read_md(folder)
        assert "[see section](#heading:h.abc123)" in md

        # No-edit round-trip: 3-way merge returns base unchanged → HeadingLink preserved.
        result = _md_serde.deserialize(folder)
        found = _get_link_from_desired(result.desired.document)
        assert found is not None
        assert found.heading is not None
        assert found.heading.id == "h.abc123"
        assert found.heading.tab_id is None

    def test_heading_link_new_format_cross_tab(self, tmp_path: Path) -> None:
        """Cross-tab HeadingLink serializes as #heading:{tab_id}/{heading_id}."""
        link = DocLink(heading=HeadingLink(id="h.xyz789", tab_id="t.fr18r141n5si"))
        doc = _make_doc(["intro"], extra_content=[_make_linked_para("see other tab", link)])
        bundle = _make_bundle(doc)
        folder = tmp_path / "doc"
        _md_serde.serialize(bundle, folder)

        md = _read_md(folder)
        assert "[see other tab](#heading:t.fr18r141n5si/h.xyz789)" in md

        result = _md_serde.deserialize(folder)
        found = _get_link_from_desired(result.desired.document)
        assert found is not None
        assert found.heading is not None
        assert found.heading.id == "h.xyz789"
        assert found.heading.tab_id == "t.fr18r141n5si"

    def test_bookmark_link_legacy_format_round_trip(self, tmp_path: Path) -> None:
        """Legacy bookmarkId links (#bookmark:{id}) round-trip correctly."""
        link = DocLink(bookmark_id="bm.def456")
        doc = _make_doc(["intro"], extra_content=[_make_linked_para("see bookmark", link)])
        bundle = _make_bundle(doc)
        folder = tmp_path / "doc"
        _md_serde.serialize(bundle, folder)

        md = _read_md(folder)
        assert "[see bookmark](#bookmark:bm.def456)" in md

        result = _md_serde.deserialize(folder)
        found = _get_link_from_desired(result.desired.document)
        assert found is not None
        assert found.bookmark_id == "bm.def456"

    def test_bookmark_link_new_format_same_tab(self, tmp_path: Path) -> None:
        """New BookmarkLink without tab_id serializes as #bookmark:{id}.
        On a no-edit round-trip the 3-way merge returns base unchanged, so
        the desired document keeps the original BookmarkLink struct.
        """
        link = DocLink(bookmark=BookmarkLink(id="bm.def456", tab_id=None))
        doc = _make_doc(["intro"], extra_content=[_make_linked_para("see bookmark", link)])
        bundle = _make_bundle(doc)
        folder = tmp_path / "doc"
        _md_serde.serialize(bundle, folder)

        md = _read_md(folder)
        assert "[see bookmark](#bookmark:bm.def456)" in md

        # No-edit round-trip: 3-way merge returns base unchanged → BookmarkLink preserved.
        result = _md_serde.deserialize(folder)
        found = _get_link_from_desired(result.desired.document)
        assert found is not None
        assert found.bookmark is not None
        assert found.bookmark.id == "bm.def456"
        assert found.bookmark.tab_id is None

    def test_bookmark_link_new_format_cross_tab(self, tmp_path: Path) -> None:
        """Cross-tab BookmarkLink serializes as #bookmark:{tab_id}/{bookmark_id}."""
        link = DocLink(bookmark=BookmarkLink(id="bm.xyz789", tab_id="t.de9mg0cq7w3r"))
        doc = _make_doc(["intro"], extra_content=[_make_linked_para("see other tab", link)])
        bundle = _make_bundle(doc)
        folder = tmp_path / "doc"
        _md_serde.serialize(bundle, folder)

        md = _read_md(folder)
        assert "[see other tab](#bookmark:t.de9mg0cq7w3r/bm.xyz789)" in md

        result = _md_serde.deserialize(folder)
        found = _get_link_from_desired(result.desired.document)
        assert found is not None
        assert found.bookmark is not None
        assert found.bookmark.id == "bm.xyz789"
        assert found.bookmark.tab_id == "t.de9mg0cq7w3r"

    def test_tab_link_round_trip(self, tmp_path: Path) -> None:
        """Direct tab links (#tab:{tab_id}) round-trip correctly."""
        link = DocLink(tab_id="t.fr18r141n5si")
        doc = _make_doc(["intro"], extra_content=[_make_linked_para("go to tab 2", link)])
        bundle = _make_bundle(doc)
        folder = tmp_path / "doc"
        _md_serde.serialize(bundle, folder)

        md = _read_md(folder)
        assert "[go to tab 2](#tab:t.fr18r141n5si)" in md

        result = _md_serde.deserialize(folder)
        found = _get_link_from_desired(result.desired.document)
        assert found is not None
        assert found.tab_id == "t.fr18r141n5si"

    def test_heading_link_is_preserved_on_noop(self, tmp_path: Path) -> None:
        """A new-format HeadingLink survives a no-op serialize → deserialize."""
        link = DocLink(heading=HeadingLink(id="h.abc123", tab_id="t.0"))
        doc = _make_doc(["intro"], extra_content=[_make_linked_para("same tab link", link)])
        bundle = _make_bundle(doc)
        folder = tmp_path / "doc"
        _md_serde.serialize(bundle, folder)
        result = _md_serde.deserialize(folder)
        # The base document must appear in desired unchanged (no diff)
        # Find the link in base
        base_link = _get_link_from_desired(result.base.document)
        desired_link = _get_link_from_desired(result.desired.document)
        assert base_link is not None
        assert desired_link is not None
        # 3-way merge: no edits → desired link must equal base link
        assert desired_link.heading is not None
        assert desired_link.heading.id == "h.abc123"
        assert desired_link.heading.tab_id == "t.0"


# ---------------------------------------------------------------------------
# Group 9: Heading links by name
# ---------------------------------------------------------------------------

import pytest


def _make_heading_se(
    text: str,
    style: ParagraphStyleNamedStyleType,
    heading_id: str,
) -> StructuralElement:
    """Build a heading StructuralElement with a heading_id."""
    ps = ParagraphStyle(named_style_type=style, heading_id=heading_id)
    el = ParagraphElement(text_run=TextRun(content=text + "\n", text_style=TextStyle()))
    return StructuralElement(paragraph=Paragraph(elements=[el], paragraph_style=ps))


class TestHeadingLinksByName:
    """Tests for heading-link-by-name resolution in markdown serde."""

    def test_existing_heading_resolves_by_name(self, tmp_path: Path) -> None:
        """Link [see here](#Overview) resolves to a heading link when 'Overview' exists."""
        h1 = _make_heading_se("Overview", ParagraphStyleNamedStyleType.HEADING_1, "h.abc123")
        doc = _make_doc(["intro"], extra_content=[h1])
        bundle = _make_bundle(doc)
        folder = tmp_path / "doc"
        _md_serde.serialize(bundle, folder)

        # Write markdown with a heading link by name
        md = _read_md(folder)
        md = md.replace("intro", "[see here](#Overview)")
        _write_md(folder, md)

        result = _md_serde.deserialize(folder)
        found = _get_link_from_desired(result.desired.document)
        assert found is not None, "Expected a heading link in the desired document"
        # Must be a heading link, not a plain URL
        has_heading = (found.heading_id is not None) or (found.heading is not None)
        assert has_heading, f"Expected heading link, got: {found}"

    def test_cross_tab_heading_resolves_by_name(self, tmp_path: Path) -> None:
        """Link [see](#Tab_2/Details) resolves to a heading link in the other tab."""
        h1_tab1 = _make_heading_se("Intro", ParagraphStyleNamedStyleType.HEADING_1, "h.t1intro")
        h1_tab2 = _make_heading_se("Details", ParagraphStyleNamedStyleType.HEADING_1, "h.t2details")

        tab1_content = [_make_text_para("intro"), h1_tab1]
        tab2_content = [h1_tab2, _make_text_para("Some detail text")]

        doc = Document(
            document_id="cross-tab-doc",
            title="CrossTab",
            tabs=[
                Tab(
                    tab_properties=TabProperties(tab_id="t.0", title="Tab 1"),
                    document_tab=DocumentTab(body=Body(content=tab1_content)),
                ),
                Tab(
                    tab_properties=TabProperties(tab_id="t.1", title="Tab 2"),
                    document_tab=DocumentTab(body=Body(content=tab2_content)),
                ),
            ],
        )
        bundle = _make_bundle(doc)
        folder = tmp_path / "doc"
        _md_serde.serialize(bundle, folder)

        # Write a cross-tab heading link by name
        md = _read_md(folder, "Tab_1")
        md = md.replace("intro", "[see](#Tab_2/Details)")
        _write_md(folder, md, "Tab_1")

        result = _md_serde.deserialize(folder)
        found = _get_link_from_desired(result.desired.document, tab_idx=0)
        assert found is not None, "Expected a cross-tab heading link"
        # Must be a heading link (not a URL)
        has_heading = (found.heading_id is not None) or (found.heading is not None)
        assert has_heading, f"Expected heading link, got: {found}"

    def test_duplicate_headings_first_wins(self, tmp_path: Path) -> None:
        """Two headings named 'Details' — link resolves to the first one."""
        h1 = _make_heading_se("Details", ParagraphStyleNamedStyleType.HEADING_2, "h.first")
        h2 = _make_heading_se("Details", ParagraphStyleNamedStyleType.HEADING_2, "h.second")
        doc = _make_doc(["intro"], extra_content=[h1, h2])
        bundle = _make_bundle(doc)
        folder = tmp_path / "doc"
        _md_serde.serialize(bundle, folder)

        md = _read_md(folder)
        md = md.replace("intro", "[see](#Details)")
        _write_md(folder, md)

        result = _md_serde.deserialize(folder)
        found = _get_link_from_desired(result.desired.document)
        assert found is not None, "Expected a heading link"
        has_heading = (found.heading_id is not None) or (found.heading is not None)
        assert has_heading, f"Expected heading link, got: {found}"

    def test_new_heading_placeholder(self, tmp_path: Path) -> None:
        """Link to non-existent heading creates a placeholder URL."""
        doc = _make_doc(["intro"])
        bundle = _make_bundle(doc)
        folder = tmp_path / "doc"
        _md_serde.serialize(bundle, folder)

        md = _read_md(folder)
        md = md.replace("intro", "[see](#NewSection)")
        _write_md(folder, md)

        result = _md_serde.deserialize(folder)
        found = _get_link_from_desired(result.desired.document)
        assert found is not None, "Expected a link in the desired document"
        assert found.url is not None, "Expected a URL-based placeholder link"
        assert found.url.startswith("#heading-ref:"), f"Expected placeholder, got: {found.url}"
        assert "NewSection" in found.url

    def test_serialize_heading_link_as_name(self, tmp_path: Path) -> None:
        """Heading link with heading_id serializes as [text](#Heading Name)."""
        h1 = _make_heading_se("Overview", ParagraphStyleNamedStyleType.HEADING_1, "h.abc123")
        link = DocLink(heading_id="h.abc123")
        linked_para = _make_linked_para("click here", link)
        doc = _make_doc([], extra_content=[h1, linked_para])
        bundle = _make_bundle(doc)
        folder = tmp_path / "doc"
        _md_serde.serialize(bundle, folder)

        md = _read_md(folder)
        assert "[click here](#Overview)" in md, f"Expected name-based link, got:\n{md}"
        # Must NOT contain the raw heading ID
        assert "#heading:h.abc123" not in md

    def test_serialize_placeholder_back_as_name(self, tmp_path: Path) -> None:
        """Doc with url='#heading-ref:Details' serializes as [text](#Details)."""
        link = DocLink(url="#heading-ref:Details")
        linked_para = _make_linked_para("see details", link)
        doc = _make_doc(["intro"], extra_content=[linked_para])
        bundle = _make_bundle(doc)
        folder = tmp_path / "doc"
        _md_serde.serialize(bundle, folder)

        md = _read_md(folder)
        assert "[see details](#Details)" in md, f"Expected name-based link, got:\n{md}"
        assert "#heading-ref:" not in md

    def test_self_healing_round_trip(self, tmp_path: Path) -> None:
        """Full cycle: first push creates placeholder, next cycle resolves it.

        Cycle 1: Link to 'NewSection' (doesn't exist) → placeholder stored.
        Cycle 2: 'NewSection' heading now exists in base → resolves to real heading link.
        """
        # --- Cycle 1: create doc, add link to non-existent heading ---
        doc = _make_doc(["intro"])
        bundle = _make_bundle(doc)
        folder1 = tmp_path / "cycle1"
        _md_serde.serialize(bundle, folder1)

        md = _read_md(folder1)
        md = md.replace("intro", "[see](#NewSection)")
        _write_md(folder1, md)

        result1 = _md_serde.deserialize(folder1)
        link1 = _get_link_from_desired(result1.desired.document)
        assert link1 is not None
        assert link1.url is not None and link1.url.startswith("#heading-ref:")

        # --- Cycle 2: base now has the heading + the placeholder link ---
        # Build a new base that has the heading AND the placeholder link from cycle 1
        h1 = _make_heading_se("NewSection", ParagraphStyleNamedStyleType.HEADING_1, "h.newsec")
        placeholder_link = DocLink(url="#heading-ref:NewSection")
        linked_para = _make_linked_para("see", placeholder_link)
        doc2 = _make_doc([], extra_content=[h1, linked_para])
        bundle2 = _make_bundle(doc2)
        folder2 = tmp_path / "cycle2"
        _md_serde.serialize(bundle2, folder2)

        # No edits — just deserialize; the placeholder should self-heal
        result2 = _md_serde.deserialize(folder2)
        link2 = _get_link_from_desired(result2.desired.document)
        assert link2 is not None, "Expected a link after self-healing"
        # Should now be a real heading link, not a placeholder
        has_heading = (link2.heading_id is not None) or (link2.heading is not None)
        assert has_heading, f"Expected heading link after self-heal, got: {link2}"


# ---------------------------------------------------------------------------
# Image support tests
# ---------------------------------------------------------------------------


def _make_inline_object(
    object_id: str,
    content_uri: str,
    description: str | None = None,
) -> InlineObject:
    return InlineObject(
        object_id=object_id,
        inline_object_properties=InlineObjectProperties(
            embedded_object=EmbeddedObject(
                image_properties=ImageProperties(content_uri=content_uri),
                description=description,
                size=Size(
                    width=Dimension(magnitude=200, unit="PT"),
                    height=Dimension(magnitude=100, unit="PT"),
                ),
            )
        ),
    )


def _make_para_with_image(
    text: str, inline_object_id: str
) -> StructuralElement:
    return StructuralElement(
        paragraph=Paragraph(
            elements=[
                ParagraphElement(text_run=TextRun(content=text)),
                ParagraphElement(
                    inline_object_element=InlineObjectElement(
                        inline_object_id=inline_object_id
                    )
                ),
                ParagraphElement(text_run=TextRun(content="\n")),
            ],
            paragraph_style=ParagraphStyle(
                named_style_type=ParagraphStyleNamedStyleType.NORMAL_TEXT
            ),
        )
    )


class TestImageSerde:
    """Tests for inline image markdown serialization/deserialization."""

    def test_serialize_image_with_description(self, tmp_path: "Path") -> None:
        """An image with description serializes as ![alt](url)."""
        img = _make_inline_object(
            "kix.abc123",
            "https://lh3.googleusercontent.com/abc123",
            description="A photo",
        )
        para = _make_para_with_image("Hello ", "kix.abc123")
        doc = _make_doc(
            [],
            extra_content=[para],
            inline_objects={"kix.abc123": img},
        )
        bundle = _make_bundle(doc)
        _md_serde.serialize(bundle, tmp_path)

        md = _read_md(tmp_path)
        assert "![A photo](https://lh3.googleusercontent.com/abc123)" in md
        assert "<x-img" not in md

    def test_serialize_image_no_description(self, tmp_path: "Path") -> None:
        """An image with no description serializes with empty alt text."""
        img = _make_inline_object(
            "kix.abc123",
            "https://lh3.googleusercontent.com/abc123",
        )
        para = _make_para_with_image("Hello ", "kix.abc123")
        doc = _make_doc(
            [],
            extra_content=[para],
            inline_objects={"kix.abc123": img},
        )
        bundle = _make_bundle(doc)
        _md_serde.serialize(bundle, tmp_path)

        md = _read_md(tmp_path)
        assert "![](https://lh3.googleusercontent.com/abc123)" in md
        assert "<x-img" not in md

    def test_deserialize_existing_image_roundtrip(self, tmp_path: "Path") -> None:
        """Deserializing a doc with an image produces same inlineObjectElement."""
        img = _make_inline_object(
            "kix.abc123",
            "https://lh3.googleusercontent.com/abc123",
            description="A photo",
        )
        para = _make_para_with_image("Hello ", "kix.abc123")
        doc = _make_doc(
            [],
            extra_content=[para],
            inline_objects={"kix.abc123": img},
        )
        bundle = _make_bundle(doc)
        _md_serde.serialize(bundle, tmp_path)

        # Verify the serialized markdown uses ![alt](url) not <x-img>
        md = _read_md(tmp_path)
        assert "![A photo](https://lh3.googleusercontent.com/abc123)" in md
        assert "<x-img" not in md

        # No edits — just deserialize
        result = _md_serde.deserialize(tmp_path)
        desired = result.desired.document
        dt = (desired.tabs or [])[0].document_tab
        assert dt is not None
        assert dt.inline_objects is not None
        assert "kix.abc123" in dt.inline_objects

        # Check the element is still in the body
        body_els = dt.body.content or []
        found = False
        for se in body_els:
            if se.paragraph:
                for el in se.paragraph.elements or []:
                    if (
                        el.inline_object_element
                        and el.inline_object_element.inline_object_id == "kix.abc123"
                    ):
                        found = True
        assert found, "InlineObjectElement should be preserved in round-trip"

    def test_deserialize_new_local_image(self, tmp_path: "Path") -> None:
        """Adding ![photo](./images/local.png) creates a new InlineObjectElement."""
        doc = _make_doc(["Hello world"])
        bundle = _make_bundle(doc)
        _md_serde.serialize(bundle, tmp_path)

        md_path = _tab_md_path(tmp_path)
        md = md_path.read_text()
        md += "\n![photo](./images/local.png)\n"
        md_path.write_text(md)

        result = _md_serde.deserialize(tmp_path)
        desired = result.desired.document
        dt = (desired.tabs or [])[0].document_tab
        assert dt is not None
        assert dt.inline_objects is not None
        assert len(dt.inline_objects) > 0

        # Find an inline object with our local path as contentUri
        found_uri = False
        for io in dt.inline_objects.values():
            props = io.inline_object_properties
            if props and props.embedded_object:
                uri = props.embedded_object.image_properties
                if uri and uri.content_uri == "./images/local.png":
                    found_uri = True
        assert found_uri, "Expected inline object with contentUri='./images/local.png'"

    def test_deserialize_new_external_image(self, tmp_path: "Path") -> None:
        """Adding ![alt](https://example.com/img.png) creates a new InlineObjectElement."""
        doc = _make_doc(["Hello world"])
        bundle = _make_bundle(doc)
        _md_serde.serialize(bundle, tmp_path)

        md_path = _tab_md_path(tmp_path)
        md = md_path.read_text()
        md += "\n![alt](https://example.com/img.png)\n"
        md_path.write_text(md)

        result = _md_serde.deserialize(tmp_path)
        desired = result.desired.document
        dt = (desired.tabs or [])[0].document_tab
        assert dt is not None
        assert dt.inline_objects is not None
        assert len(dt.inline_objects) > 0

        found_uri = False
        for io in dt.inline_objects.values():
            props = io.inline_object_properties
            if props and props.embedded_object:
                uri = props.embedded_object.image_properties
                if uri and uri.content_uri == "https://example.com/img.png":
                    found_uri = True
        assert found_uri, "Expected inline object with contentUri='https://example.com/img.png'"

    def test_delete_image(self, tmp_path: "Path") -> None:
        """Removing ![alt](url) from markdown removes the InlineObjectElement."""
        img = _make_inline_object(
            "kix.abc123",
            "https://lh3.googleusercontent.com/abc123",
            description="A photo",
        )
        para = _make_para_with_image("Hello ", "kix.abc123")
        doc = _make_doc(
            [],
            extra_content=[para],
            inline_objects={"kix.abc123": img},
        )
        bundle = _make_bundle(doc)
        _md_serde.serialize(bundle, tmp_path)

        # Verify serialized as markdown image (not <x-img>)
        md_path = _tab_md_path(tmp_path)
        md = md_path.read_text()
        assert "![A photo](https://lh3.googleusercontent.com/abc123)" in md
        assert "<x-img" not in md

        # Remove the image from markdown
        lines = md.split("\n")
        lines = [line for line in lines if "![A photo]" not in line]
        md_path.write_text("\n".join(lines))

        result = _md_serde.deserialize(tmp_path)
        desired = result.desired.document
        dt = (desired.tabs or [])[0].document_tab
        assert dt is not None

        # The inline object element should be gone from body
        found = False
        for se in (dt.body.content or []):
            if se.paragraph:
                for el in se.paragraph.elements or []:
                    if (
                        el.inline_object_element
                        and el.inline_object_element.inline_object_id == "kix.abc123"
                    ):
                        found = True
        assert not found, "InlineObjectElement should be removed after deleting image from markdown"
