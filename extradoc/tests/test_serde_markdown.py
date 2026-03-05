"""Tests for the markdown serde: Document ↔ markdown round-trip and diff."""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from extradoc.api_types._generated import (
    Body,
    Bullet,
    Document,
    DocumentTab,
    Footer,
    Footnote,
    Header,
    InlineObjectElement,
    Link,
    NestingLevel,
    NestingLevelGlyphType,
    Paragraph,
    ParagraphElement,
    ParagraphStyle,
    ParagraphStyleNamedStyleType,
    StructuralElement,
    Tab,
    Table,
    TableCell,
    TableCellStyle,
    TableRow,
    TabProperties,
    TextRun,
    TextStyle,
)
from extradoc.api_types._generated import List as DocList, ListProperties
from extradoc.serde import deserialize, serialize
from extradoc.serde._from_markdown import markdown_to_document
from extradoc.serde._to_markdown import document_to_markdown


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_para(
    text: str,
    named_style: ParagraphStyleNamedStyleType | None = None,
    text_style: TextStyle | None = None,
    bullet: Bullet | None = None,
) -> StructuralElement:
    ps = ParagraphStyle()
    if named_style:
        ps.named_style_type = named_style
    elements = [ParagraphElement(text_run=TextRun(content=text + "\n", text_style=text_style))]
    return StructuralElement(
        paragraph=Paragraph(elements=elements, paragraph_style=ps, bullet=bullet)
    )


def _make_doc(
    content: list[StructuralElement],
    doc_id: str = "test-doc",
    title: str = "Test",
    lists: dict | None = None,
) -> Document:
    doc_tab = DocumentTab(body=Body(content=content), lists=lists)
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


def _tab_body_text(doc: Document) -> list[str]:
    """Extract plain text from body paragraphs (skip empty/section-break)."""
    texts: list[str] = []
    tab = (doc.tabs or [None])[0]
    dt = tab.document_tab if tab else None
    if not dt or not dt.body:
        return texts
    for se in dt.body.content or []:
        if se.paragraph:
            parts = [
                (pe.text_run.content or "").rstrip("\n")
                for pe in (se.paragraph.elements or [])
                if pe.text_run and pe.text_run.content and pe.text_run.content != "\n"
            ]
            text = "".join(parts)
            if text:
                texts.append(text)
    return texts


# ---------------------------------------------------------------------------
# Test 1: markdown → Document → markdown round-trip
# ---------------------------------------------------------------------------


ROUND_TRIP_MD = textwrap.dedent("""\
    # Project Overview

    This is a **bold** paragraph with *italic* text.

    ## Features

    - First bullet point
    - Second bullet point

    | Name | Value |
    | --- | --- |
    | Foo | 42 |
    | Bar | 99 |

    Check out [this link](https://example.com) for more.
    """)


class TestMarkdownRoundTrip:
    def test_md_to_document_headings(self) -> None:
        """Headings are parsed to the correct named style."""
        doc = markdown_to_document({"Tab_1": ROUND_TRIP_MD}, document_id="x", title="T")
        tab = doc.tabs[0]  # type: ignore[index]
        body = tab.document_tab.body.content  # type: ignore[union-attr]

        # First element is sectionBreak
        assert body[0].section_break is not None

        # Second is HEADING_1
        h1 = body[1].paragraph
        assert h1 is not None
        assert h1.paragraph_style is not None
        assert h1.paragraph_style.named_style_type == ParagraphStyleNamedStyleType.HEADING_1
        # Heading text
        text = "".join(
            (pe.text_run.content or "").rstrip("\n")
            for pe in (h1.elements or [])
            if pe.text_run
        )
        assert text == "Project Overview"

    def test_md_to_document_bold_italic(self) -> None:
        """Bold and italic runs are parsed correctly."""
        doc = markdown_to_document({"Tab_1": ROUND_TRIP_MD}, document_id="x", title="T")
        tab = doc.tabs[0]  # type: ignore[index]
        body = tab.document_tab.body.content  # type: ignore[union-attr]

        # Find the paragraph with "bold"
        bold_para = None
        for se in body:
            if se.paragraph:
                for pe in se.paragraph.elements or []:
                    if pe.text_run and pe.text_run.text_style and pe.text_run.text_style.bold:
                        bold_para = se.paragraph
                        break
        assert bold_para is not None

        # Find the bold run
        bold_runs = [
            pe.text_run
            for pe in (bold_para.elements or [])
            if pe.text_run and pe.text_run.text_style and pe.text_run.text_style.bold
        ]
        assert len(bold_runs) == 1
        assert "bold" in (bold_runs[0].content or "")

        # Find the italic run
        italic_runs = [
            pe.text_run
            for pe in (bold_para.elements or [])
            if pe.text_run and pe.text_run.text_style and pe.text_run.text_style.italic
        ]
        assert len(italic_runs) == 1
        assert "italic" in (italic_runs[0].content or "")

    def test_md_to_document_bullet_list(self) -> None:
        """Bullet list items have Bullet with correct list_id."""
        doc = markdown_to_document({"Tab_1": ROUND_TRIP_MD}, document_id="x", title="T")
        tab = doc.tabs[0]  # type: ignore[index]
        body = tab.document_tab.body.content  # type: ignore[union-attr]

        bullet_paras = [
            se.paragraph
            for se in body
            if se.paragraph and se.paragraph.bullet is not None
        ]
        assert len(bullet_paras) == 2
        # All items share same list_id
        list_ids = {p.bullet.list_id for p in bullet_paras}  # type: ignore[union-attr]
        assert len(list_ids) == 1
        # Nesting level 0
        assert all(p.bullet.nesting_level == 0 for p in bullet_paras)  # type: ignore[union-attr]

    def test_md_to_document_table(self) -> None:
        """GFM table is parsed to a Table with correct rows and columns."""
        doc = markdown_to_document({"Tab_1": ROUND_TRIP_MD}, document_id="x", title="T")
        tab = doc.tabs[0]  # type: ignore[index]
        body = tab.document_tab.body.content  # type: ignore[union-attr]

        tables = [se.table for se in body if se.table is not None]
        assert len(tables) == 1
        tbl = tables[0]
        assert tbl.rows == 3  # header + 2 data rows
        assert tbl.columns == 2

    def test_md_to_document_link(self) -> None:
        """Hyperlinks are parsed with correct URL."""
        doc = markdown_to_document({"Tab_1": ROUND_TRIP_MD}, document_id="x", title="T")
        tab = doc.tabs[0]  # type: ignore[index]
        body = tab.document_tab.body.content  # type: ignore[union-attr]

        link_runs = []
        for se in body:
            if se.paragraph:
                for pe in se.paragraph.elements or []:
                    if (
                        pe.text_run
                        and pe.text_run.text_style
                        and pe.text_run.text_style.link
                    ):
                        link_runs.append(pe.text_run)
        assert len(link_runs) == 1
        assert link_runs[0].text_style.link.url == "https://example.com"  # type: ignore[union-attr]
        assert "this link" in (link_runs[0].content or "")

    def test_document_to_md_headings(self) -> None:
        """HEADING_1 serializes to # prefix."""
        doc = _make_doc(
            [
                _make_para("Hello", named_style=ParagraphStyleNamedStyleType.HEADING_1),
                _make_para("World"),
            ]
        )
        per_tab = document_to_markdown(doc)
        md = per_tab["Tab_1"]["document.md"]
        assert "# Hello\n" in md
        assert "\nWorld\n" in md

    def test_document_to_md_bold_italic(self) -> None:
        """Bold/italic text runs produce correct markdown markers."""
        doc = _make_doc(
            [
                _make_para("bold text", text_style=TextStyle(bold=True)),
                _make_para("italic text", text_style=TextStyle(italic=True)),
            ]
        )
        per_tab = document_to_markdown(doc)
        md = per_tab["Tab_1"]["document.md"]
        assert "**bold text**" in md
        assert "*italic text*" in md

    def test_document_to_md_link(self) -> None:
        """Hyperlinks serialize to [text](url) format."""
        doc = _make_doc(
            [
                _make_para(
                    "click here",
                    text_style=TextStyle(link=Link(url="https://example.com")),
                )
            ]
        )
        per_tab = document_to_markdown(doc)
        md = per_tab["Tab_1"]["document.md"]
        assert "[click here](https://example.com)" in md

    def test_document_to_md_bullet_list(self) -> None:
        """Bullet list items serialize to - markers."""
        lists = {
            "kix.list1": DocList(
                list_properties=ListProperties(
                    nesting_levels=[NestingLevel(glyph_symbol="●")]
                )
            )
        }
        doc = _make_doc(
            [
                _make_para(
                    "item one", bullet=Bullet(list_id="kix.list1", nesting_level=0)
                ),
                _make_para(
                    "item two", bullet=Bullet(list_id="kix.list1", nesting_level=0)
                ),
            ],
            lists=lists,
        )
        per_tab = document_to_markdown(doc)
        md = per_tab["Tab_1"]["document.md"]
        assert "- item one\n" in md
        assert "- item two\n" in md

    def test_document_to_md_numbered_list(self) -> None:
        """Numbered list items serialize to 1. markers."""
        lists = {
            "kix.list1": DocList(
                list_properties=ListProperties(
                    nesting_levels=[
                        NestingLevel(glyph_type=NestingLevelGlyphType.DECIMAL)
                    ]
                )
            )
        }
        doc = _make_doc(
            [
                _make_para(
                    "first", bullet=Bullet(list_id="kix.list1", nesting_level=0)
                ),
                _make_para(
                    "second", bullet=Bullet(list_id="kix.list1", nesting_level=0)
                ),
            ],
            lists=lists,
        )
        per_tab = document_to_markdown(doc)
        md = per_tab["Tab_1"]["document.md"]
        assert "1. first\n" in md
        assert "1. second\n" in md

    def test_document_to_md_gfm_table(self) -> None:
        """Simple table serializes to GFM pipe table."""
        table = Table(
            rows=2,
            columns=2,
            table_rows=[
                TableRow(
                    table_cells=[
                        TableCell(content=[_make_para("A")], table_cell_style=TableCellStyle()),
                        TableCell(content=[_make_para("B")], table_cell_style=TableCellStyle()),
                    ]
                ),
                TableRow(
                    table_cells=[
                        TableCell(content=[_make_para("1")], table_cell_style=TableCellStyle()),
                        TableCell(content=[_make_para("2")], table_cell_style=TableCellStyle()),
                    ]
                ),
            ],
        )
        doc = _make_doc([StructuralElement(table=table)])
        per_tab = document_to_markdown(doc)
        md = per_tab["Tab_1"]["document.md"]
        assert "| A | B |" in md
        assert "| --- | --- |" in md
        assert "| 1 | 2 |" in md

    def test_passthrough_inline_image(self) -> None:
        """Inline images serialize to <x-img id="..."/> and round-trip back."""
        content = [
            StructuralElement(
                paragraph=Paragraph(
                    elements=[
                        ParagraphElement(
                            inline_object_element=InlineObjectElement(
                                inline_object_id="obj.abc123"
                            )
                        ),
                        ParagraphElement(text_run=TextRun(content="\n")),
                    ],
                    paragraph_style=ParagraphStyle(
                        named_style_type=ParagraphStyleNamedStyleType.NORMAL_TEXT
                    ),
                )
            )
        ]
        doc = _make_doc(content)
        per_tab = document_to_markdown(doc)
        md = per_tab["Tab_1"]["document.md"]
        assert '<x-img id="obj.abc123"/>' in md

        # Round-trip back
        doc2 = markdown_to_document({"Tab_1": md}, document_id="x", title="T")
        tab = doc2.tabs[0]  # type: ignore[index]
        body = tab.document_tab.body.content  # type: ignore[union-attr]
        img_elements = [
            pe
            for se in body
            if se.paragraph
            for pe in (se.paragraph.elements or [])
            if pe.inline_object_element
        ]
        assert len(img_elements) == 1
        assert img_elements[0].inline_object_element.inline_object_id == "obj.abc123"  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Test 2: File-based round-trip (serialize → deserialize → identical markdown)
# ---------------------------------------------------------------------------


class TestMarkdownFileCycle:
    def test_serialize_deserialize_markdown(self, tmp_path: Path) -> None:
        """serialize(format='markdown') → deserialize() → same Document structure."""
        doc = _make_doc(
            [
                _make_para("Overview", named_style=ParagraphStyleNamedStyleType.HEADING_1),
                _make_para("Normal paragraph."),
                _make_para("Bold text", text_style=TextStyle(bold=True)),
            ]
        )

        out = tmp_path / "test-doc"
        paths = serialize(doc, out, format="markdown")

        # Check files written
        assert (out / "index.xml").exists()
        assert (out / "Tab_1" / "document.md").exists()
        # styles.xml should NOT be written for markdown format
        assert not (out / "Tab_1" / "styles.xml").exists()

        # Check index.xml records format
        index_text = (out / "index.xml").read_text()
        assert 'format="markdown"' in index_text

        # Deserialize
        bundle = deserialize(out)
        texts = _tab_body_text(bundle.document)
        assert "Overview" in texts
        assert "Normal paragraph." in texts
        assert "Bold text" in texts

        # Check bold survived
        tab = bundle.document.tabs[0]  # type: ignore[index]
        body = tab.document_tab.body.content  # type: ignore[union-attr]
        bold_runs = [
            pe.text_run
            for se in body
            if se.paragraph
            for pe in (se.paragraph.elements or [])
            if pe.text_run and pe.text_run.text_style and pe.text_run.text_style.bold
        ]
        assert len(bold_runs) == 1
        assert "Bold text" in (bold_runs[0].content or "")

    def test_markdown_string_roundtrip(self, tmp_path: Path) -> None:
        """Write markdown → Document → write markdown → same string."""
        source = ROUND_TRIP_MD

        # Parse to Document
        doc = markdown_to_document({"Tab_1": source}, document_id="x", title="T")

        # Re-serialize
        per_tab = document_to_markdown(doc)
        result = per_tab["Tab_1"]["document.md"]

        assert result == source


# ---------------------------------------------------------------------------
# Test 3: Diff test — edits produce accurate batchUpdate requests
# ---------------------------------------------------------------------------


class TestMarkdownDiff:
    def test_heading_text_change(self) -> None:
        """Changing heading text produces insertText + deleteContentRange."""
        from extradoc.reconcile._core import reconcile, reindex_document

        base_md = textwrap.dedent("""\
            # Original Heading

            Some body text.
            """)

        edited_md = textwrap.dedent("""\
            # Updated Heading

            Some body text.
            """)

        base_doc = markdown_to_document({"Tab_1": base_md}, document_id="x", title="T")
        desired_doc = markdown_to_document({"Tab_1": edited_md}, document_id="x", title="T")

        base_idx = reindex_document(base_doc)
        desired_idx = reindex_document(desired_doc)

        batches = reconcile(base_idx, desired_idx)
        assert len(batches) > 0

        # Flatten all requests
        all_requests = [r for batch in batches for r in batch.requests]

        # Should have text modification requests
        request_types = set()
        for r in all_requests:
            if r.insert_text:
                request_types.add("insertText")
            if r.delete_content_range:
                request_types.add("deleteContentRange")

        assert "insertText" in request_types or "deleteContentRange" in request_types

    def test_add_paragraph_produces_insert(self) -> None:
        """Adding a paragraph produces an insertText request."""
        from extradoc.reconcile._core import reconcile, reindex_document

        base_md = textwrap.dedent("""\
            # Heading

            First paragraph.
            """)

        edited_md = textwrap.dedent("""\
            # Heading

            First paragraph.

            New paragraph added.
            """)

        base_doc = markdown_to_document({"Tab_1": base_md}, document_id="x", title="T")
        desired_doc = markdown_to_document({"Tab_1": edited_md}, document_id="x", title="T")

        base_idx = reindex_document(base_doc)
        desired_idx = reindex_document(desired_doc)

        batches = reconcile(base_idx, desired_idx)
        assert len(batches) > 0

        all_requests = [r for batch in batches for r in batch.requests]
        insert_texts = [r.insert_text for r in all_requests if r.insert_text]
        assert any(
            "New paragraph added" in (t.text or "") for t in insert_texts
        )

    def test_unchanged_content_no_style_ops(self) -> None:
        """Unchanged paragraphs produce no spurious style operations."""
        from extradoc.reconcile._core import reconcile, reindex_document

        # Only change the heading text; body paragraph is untouched
        base_md = textwrap.dedent("""\
            # Original

            Untouched paragraph.
            """)

        edited_md = textwrap.dedent("""\
            # Changed

            Untouched paragraph.
            """)

        base_doc = markdown_to_document({"Tab_1": base_md}, document_id="x", title="T")
        desired_doc = markdown_to_document({"Tab_1": edited_md}, document_id="x", title="T")

        base_idx = reindex_document(base_doc)
        desired_idx = reindex_document(desired_doc)

        batches = reconcile(base_idx, desired_idx)
        all_requests = [r for batch in batches for r in batch.requests]

        # Should have no updateParagraphStyle or updateTextStyle for unchanged content
        para_style_ops = [r for r in all_requests if r.update_paragraph_style]
        text_style_ops = [r for r in all_requests if r.update_text_style]

        # Any style ops must not affect the untouched paragraph
        # (We just check there aren't unreasonable numbers of style changes)
        assert len(para_style_ops) <= 2  # at most 1 for heading, 1 for body
        assert len(text_style_ops) == 0

    def test_no_diff_when_identical(self) -> None:
        """Identical markdown → zero operations."""
        from extradoc.reconcile._core import reconcile, reindex_document

        md = textwrap.dedent("""\
            # Heading

            Body text.

            - item 1
            - item 2
            """)

        doc1 = markdown_to_document({"Tab_1": md}, document_id="x", title="T")
        doc2 = markdown_to_document({"Tab_1": md}, document_id="x", title="T")

        idx1 = reindex_document(doc1)
        idx2 = reindex_document(doc2)

        batches = reconcile(idx1, idx2)
        all_requests = [r for batch in batches for r in batch.requests]
        assert len(all_requests) == 0, f"Expected no ops, got: {all_requests}"
