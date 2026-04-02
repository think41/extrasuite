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


def _read_md(folder: Path, tab_name: str = "Tab_1") -> str:
    """Read a tab's markdown file."""
    return (folder / f"{tab_name}.md").read_text(encoding="utf-8")


def _write_md(folder: Path, content: str, tab_name: str = "Tab_1") -> None:
    """Overwrite a tab's markdown file."""
    (folder / f"{tab_name}.md").write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Test: serialize writes .pristine/document.zip
# ---------------------------------------------------------------------------


class TestSerializeWritesPristine:
    def test_pristine_zip_created(self, tmp_path: Path) -> None:
        """serialize() writes .pristine/document.zip for markdown format."""
        doc = _make_doc(["Hello world"])
        bundle = _make_bundle(doc)
        folder = tmp_path / "doc"
        serialize(bundle, folder, format="markdown")
        assert (folder / ".pristine" / "document.zip").exists()

    def test_pristine_contains_md_files(self, tmp_path: Path) -> None:
        """The pristine zip contains the markdown files."""
        import zipfile

        doc = _make_doc(["Hello world"])
        bundle = _make_bundle(doc)
        folder = tmp_path / "doc"
        serialize(bundle, folder, format="markdown")
        zip_path = folder / ".pristine" / "document.zip"
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
        assert any("Tab_1.md" in n for n in names)
        # Should NOT contain .pristine/ or .raw/ entries
        assert not any(".pristine" in n for n in names)

    def test_pristine_written_for_xml(self, tmp_path: Path) -> None:
        """serialize() with XML format also writes .pristine/document.zip."""
        doc = _make_doc(["Hello world"])
        bundle = _make_bundle(doc)
        folder = tmp_path / "doc"
        serialize(bundle, folder, format="xml")
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
        serialize(base, folder, format="markdown")

        # Edit the markdown
        md = _read_md(folder)
        md = md.replace("Hello world", "Hello there")
        _write_md(folder, md)

        desired = deserialize(base, folder)
        texts = _body_texts(desired.document)
        assert "Hello there" in texts
        assert "Second para" in texts

    def test_add_paragraph(self, tmp_path: Path) -> None:
        """Insert a new paragraph in markdown → appears in desired body."""
        base_doc = _make_doc(["First para", "Second para"])
        base = _make_bundle(base_doc)
        folder = tmp_path / "doc"
        serialize(base, folder, format="markdown")

        md = _read_md(folder)
        # Add a new line after "First para"
        md = md.replace("First para\n", "First para\n\nNew inserted para\n")
        _write_md(folder, md)

        desired = deserialize(base, folder)
        texts = _body_texts(desired.document)
        assert "New inserted para" in texts
        assert "First para" in texts
        assert "Second para" in texts

    def test_delete_paragraph(self, tmp_path: Path) -> None:
        """Remove a paragraph from markdown → absent in desired body."""
        base_doc = _make_doc(["Keep this", "Delete this", "Also keep"])
        base = _make_bundle(base_doc)
        folder = tmp_path / "doc"
        serialize(base, folder, format="markdown")

        md = _read_md(folder)
        lines = [line for line in md.splitlines() if "Delete this" not in line]
        _write_md(folder, "\n".join(lines) + "\n")

        desired = deserialize(base, folder)
        texts = _body_texts(desired.document)
        assert "Delete this" not in texts
        assert "Keep this" in texts

    def test_edit_bold_text(self, tmp_path: Path) -> None:
        """Edit bold text → markdown → desired has correct style."""
        base_doc = _make_doc(["Normal text"])
        base = _make_bundle(base_doc)
        folder = tmp_path / "doc"
        serialize(base, folder, format="markdown")

        # Write markdown with bold
        _write_md(folder, "**bold text**\n")
        desired = deserialize(base, folder)

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
        serialize(base, folder, format="markdown")

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
        """Edit a table cell in markdown → desired has updated cell text."""
        table_se = _make_table_se([["Header1", "Header2"], ["Value1", "Value2"]])
        base_doc = _make_doc([], extra_content=[table_se])
        base = _make_bundle(base_doc)
        folder = tmp_path / "doc"
        serialize(base, folder, format="markdown")

        md = _read_md(folder)
        md = md.replace("Value1", "Updated1")
        _write_md(folder, md)

        desired = deserialize(base, folder)
        cell_data = _cell_texts(desired.document)
        flat_cells = [cell for row in cell_data for cell in row]
        assert "Updated1" in flat_cells

    def test_table_preserved_when_not_in_markdown(self, tmp_path: Path) -> None:
        """Tables that round-trip through markdown are preserved."""
        table_se = _make_table_se([["A", "B"]])
        base_doc = _make_doc(["Para before"], extra_content=[table_se])
        base = _make_bundle(base_doc)
        folder = tmp_path / "doc"
        serialize(base, folder, format="markdown")

        # No edits
        desired = deserialize(base, folder)
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
        serialize(base, folder, format="markdown")

        # Edit body only
        md = _read_md(folder)
        md = md.replace("Body text", "Changed body")
        _write_md(folder, md)

        desired = deserialize(base, folder)
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
        serialize(base, folder, format="markdown")

        desired = deserialize(base, folder)
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
        serialize(base, folder, format="markdown")

        desired = deserialize(base, folder)
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
        serialize(base, folder, format="markdown")

        desired = deserialize(base, folder)
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
        serialize(base, folder, format="markdown")

        desired = deserialize(base, folder)
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
        serialize(base, folder, format="markdown")

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

        desired = deserialize(base, folder)
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
        serialize(base, folder, format="markdown")

        # Edit Tab 1 only
        md1 = _read_md(folder, "Tab_1")
        md1 = md1.replace("Tab1 Para1", "Tab1 Changed")
        _write_md(folder, md1, "Tab_1")

        desired = deserialize(base, folder)
        texts1 = _body_texts(desired.document, tab_idx=0)
        texts2 = _body_texts(desired.document, tab_idx=1)

        assert "Tab1 Changed" in texts1
        assert "Tab2 Para1" in texts2
        assert "Tab2 Para2" in texts2


# ---------------------------------------------------------------------------
# Group 6: Lists
# ---------------------------------------------------------------------------


class TestLists:
    def _make_bullet_doc(self) -> Document:
        """Create a doc with a bullet list."""
        from extradoc.serde._from_markdown import markdown_to_document

        md = "- Item one\n- Item two\n- Item three\n"
        return markdown_to_document({"Tab_1": md}, document_id="list-doc", title="List")

    def test_edit_list_item_text(self, tmp_path: Path) -> None:
        """Edit a bullet list item text → desired has updated text."""
        base_doc = self._make_bullet_doc()
        base = _make_bundle(base_doc)
        folder = tmp_path / "doc"
        serialize(base, folder, format="markdown")

        md = _read_md(folder)
        md = md.replace("Item one", "Item one edited")
        _write_md(folder, md)

        desired = deserialize(base, folder)
        texts = _body_texts(desired.document)
        assert any("Item one edited" in t for t in texts)

    def test_add_list_item(self, tmp_path: Path) -> None:
        """Add a bullet list item → appears in desired body."""
        base_doc = self._make_bullet_doc()
        base = _make_bundle(base_doc)
        folder = tmp_path / "doc"
        serialize(base, folder, format="markdown")

        md = _read_md(folder)
        md = md.replace("- Item three\n", "- Item three\n- New fourth item\n")
        _write_md(folder, md)

        desired = deserialize(base, folder)
        texts = _body_texts(desired.document)
        assert any("New fourth item" in t for t in texts)


# ---------------------------------------------------------------------------
# Group 7: Footnotes
# ---------------------------------------------------------------------------


class TestFootnotes:
    def test_edit_footnote_content(self, tmp_path: Path) -> None:
        """Edit footnote text in markdown → desired has updated footnote."""
        from extradoc.serde._from_markdown import markdown_to_document

        md = "Para with footnote[^1].\n\n[^1]: Old footnote text\n"
        base_doc = markdown_to_document(
            {"Tab_1": md}, document_id="fn-doc", title="Footnotes"
        )
        base = _make_bundle(base_doc)
        folder = tmp_path / "doc"
        serialize(base, folder, format="markdown")

        # Edit footnote text in the markdown
        md_current = _read_md(folder)
        md_new = md_current.replace("Old footnote text", "New footnote text")
        _write_md(folder, md_new)

        desired = deserialize(base, folder)
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
        serialize(base, folder, format="markdown")
        desired = deserialize(base, folder)
        assert desired.document is not None

    def test_no_changes_zero_ops(self, tmp_path: Path) -> None:
        """serialize then deserialize without editing → no body content changes."""

        base_doc = _make_doc(["Hello world", "Second para"])
        base = _make_bundle(base_doc)
        folder = tmp_path / "doc"
        serialize(base, folder, format="markdown")

        # No edits → deserialize
        desired = deserialize(base, folder)

        # Verify body texts are identical
        base_texts = _body_texts(base_doc)
        desired_texts = _body_texts(desired.document)
        assert desired_texts == base_texts

    def test_legacy_folder_no_pristine(self, tmp_path: Path) -> None:
        """When .pristine/document.zip is absent, falls back to direct parse."""

        base_doc = _make_doc(["Hello world"])
        base = _make_bundle(base_doc)
        folder = tmp_path / "doc"
        serialize(base, folder, format="markdown")

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
        bundle = DocumentWithComments(
            document=base_doc,
            comments=FileComments(file_id="test"),
        )
        folder = tmp_path / "doc"
        serialize(bundle, folder, format="xml")

        # Legacy call: deserialize(folder)
        result = deserialize(folder)
        assert result.document is not None
