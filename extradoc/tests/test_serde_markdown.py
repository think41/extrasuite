"""Tests for the markdown serde: Document ↔ markdown round-trip and diff."""

from __future__ import annotations

import textwrap
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from extradoc.api_types._generated import (
    Body,
    Bullet,
    Document,
    DocumentTab,
    InlineObjectElement,
    Link,
    ListProperties,
    NamedRange,
    NamedRanges,
    NestingLevel,
    NestingLevelGlyphType,
    Paragraph,
    ParagraphElement,
    ParagraphStyle,
    ParagraphStyleNamedStyleType,
    Range,
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
from extradoc.api_types._generated import List as DocList
from extradoc.comments._types import DocumentWithComments, FileComments
from extradoc.reconcile._core import reindex_document
from extradoc.serde.markdown import MarkdownSerde
from extradoc.serde.markdown._from_markdown import markdown_to_document
from extradoc.serde.markdown._to_markdown import document_to_markdown

_md_serde = MarkdownSerde()

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
    elements = [
        ParagraphElement(text_run=TextRun(content=text + "\n", text_style=text_style))
    ]
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

    | **Name** | **Value** |
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
        assert (
            h1.paragraph_style.named_style_type
            == ParagraphStyleNamedStyleType.HEADING_1
        )
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
                    if (
                        pe.text_run
                        and pe.text_run.text_style
                        and pe.text_run.text_style.bold
                    ):
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

    def test_md_to_document_footnote_reference_and_definition(self) -> None:
        """Markdown footnote syntax becomes a footnote ref plus footnote segment."""
        doc = markdown_to_document(
            {
                "Tab_1": (
                    "Paragraph with footnote.[^note]\n\n[^note]: Footnote body text.\n"
                )
            },
            document_id="x",
            title="T",
        )
        tab = doc.tabs[0]  # type: ignore[index]
        dt = tab.document_tab  # type: ignore[union-attr]
        body = dt.body.content  # type: ignore[union-attr]

        paragraph = next(
            se.paragraph
            for se in body
            if se.paragraph is not None and se.paragraph.elements
        )
        assert any(
            pe.footnote_reference and pe.footnote_reference.footnote_id == "note"
            for pe in (paragraph.elements or [])
        )
        assert dt.footnotes is not None
        assert "note" in dt.footnotes

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
                        TableCell(
                            content=[_make_para("A")], table_cell_style=TableCellStyle()
                        ),
                        TableCell(
                            content=[_make_para("B")], table_cell_style=TableCellStyle()
                        ),
                    ]
                ),
                TableRow(
                    table_cells=[
                        TableCell(
                            content=[_make_para("1")], table_cell_style=TableCellStyle()
                        ),
                        TableCell(
                            content=[_make_para("2")], table_cell_style=TableCellStyle()
                        ),
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
                _make_para(
                    "Overview", named_style=ParagraphStyleNamedStyleType.HEADING_1
                ),
                _make_para("Normal paragraph."),
                _make_para("Bold text", text_style=TextStyle(bold=True)),
            ]
        )

        out = tmp_path / "test-doc"
        bundle = DocumentWithComments(
            document=doc, comments=FileComments(file_id="test-doc")
        )
        _md_serde.serialize(bundle, out)

        # Check files written
        assert (out / "index.xml").exists()
        assert (out / "index.md").exists()
        assert (out / "Tab_1.md").exists()
        # styles.xml should NOT be written for markdown format
        assert not (out / "Tab_1" / "styles.xml").exists()

        # Check index.xml records format
        index_text = (out / "index.xml").read_text()
        assert 'format="markdown"' in index_text

        # Check index.md has heading with line number
        index_md = (out / "index.md").read_text()
        assert "Tab_1.md" in index_md
        assert "# Overview" in index_md

        # Deserialize
        result = _md_serde.deserialize(out)
        texts = _tab_body_text(result.desired.document)
        assert "Overview" in texts
        assert "Normal paragraph." in texts
        assert "Bold text" in texts

        # Check bold survived
        tab = result.desired.document.tabs[0]  # type: ignore[index]
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

    def test_markdown_string_roundtrip(self) -> None:
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


# ---------------------------------------------------------------------------
# Test 4: Special elements — push path (markdown → Document)
# ---------------------------------------------------------------------------


class TestSpecialElementsPush:
    """Verify that special markdown syntax creates typed elements with named ranges."""

    def _get_tables(self, doc: Document) -> list:
        tab = (doc.tabs or [None])[0]
        dt = tab.document_tab if tab else None
        body = dt.body.content if dt and dt.body else []
        return [se for se in body if se.table is not None]

    def _get_named_ranges(self, doc: Document) -> dict:
        tab = (doc.tabs or [None])[0]
        dt = tab.document_tab if tab else None
        return dt.named_ranges or {} if dt else {}

    def test_code_fence_creates_table(self) -> None:
        """```python code``` → 1x1 table with Courier New font."""
        md = "```python\nprint('hello')\nx = 1\n```\n"
        doc = markdown_to_document({"Tab_1": md})
        tables = self._get_tables(doc)
        assert len(tables) == 1
        tbl = tables[0].table
        assert tbl.rows == 1
        assert tbl.columns == 1

        # Check Courier New font in cell content
        cell = tbl.table_rows[0].table_cells[0]
        code_runs = [
            pe.text_run
            for se in (cell.content or [])
            if se.paragraph
            for pe in (se.paragraph.elements or [])
            if pe.text_run
            and pe.text_run.text_style
            and pe.text_run.text_style.weighted_font_family
            and pe.text_run.text_style.weighted_font_family.font_family == "Courier New"
        ]
        assert len(code_runs) > 0, "Expected Courier New runs in code block"

    def test_code_fence_creates_named_range(self) -> None:
        """```python code``` → named range extradoc:codeblock:python."""
        md = "```python\nprint('hello')\n```\n"
        doc = markdown_to_document({"Tab_1": md})
        nr = self._get_named_ranges(doc)
        assert "extradoc:codeblock:python" in nr
        entries = nr["extradoc:codeblock:python"].named_ranges or []
        assert len(entries) == 1
        ranges = entries[0].ranges or []
        assert len(ranges) == 1
        assert ranges[0].start_index is not None
        assert ranges[0].end_index is not None
        assert ranges[0].end_index > ranges[0].start_index

    def test_code_fence_no_language(self) -> None:
        """``` code``` → named range extradoc:codeblock (no language suffix)."""
        md = "```\nsome code\n```\n"
        doc = markdown_to_document({"Tab_1": md})
        nr = self._get_named_ranges(doc)
        assert "extradoc:codeblock" in nr

    def test_callout_creates_table(self) -> None:
        """> [!WARNING]\\n> be careful → 1x1 table with amber background."""
        md = "> [!WARNING]\n> Be careful here.\n"
        doc = markdown_to_document({"Tab_1": md})
        tables = self._get_tables(doc)
        assert len(tables) == 1
        tbl = tables[0].table
        assert tbl.rows == 1 and tbl.columns == 1

        # Check amber background
        cell = tbl.table_rows[0].table_cells[0]
        style = cell.table_cell_style
        assert style is not None
        assert style.background_color is not None

    def test_callout_creates_named_range(self) -> None:
        """> [!WARNING] → named range extradoc:callout:warning."""
        md = "> [!WARNING]\n> Watch out!\n"
        doc = markdown_to_document({"Tab_1": md})
        nr = self._get_named_ranges(doc)
        assert "extradoc:callout:warning" in nr

    def test_blockquote_creates_table(self) -> None:
        """> quoted text → 1x1 table."""
        md = "> This is quoted text.\n"
        doc = markdown_to_document({"Tab_1": md})
        tables = self._get_tables(doc)
        assert len(tables) == 1

    def test_blockquote_creates_named_range(self) -> None:
        """> text → named range extradoc:blockquote."""
        md = "> A wise saying.\n"
        doc = markdown_to_document({"Tab_1": md})
        nr = self._get_named_ranges(doc)
        assert "extradoc:blockquote" in nr

    def test_multiple_same_type(self) -> None:
        """Two code blocks → two named ranges under the same name, different IDs."""
        md = "```python\nfirst\n```\n\n```python\nsecond\n```\n"
        doc = markdown_to_document({"Tab_1": md})
        nr = self._get_named_ranges(doc)
        assert "extradoc:codeblock:python" in nr
        entries = nr["extradoc:codeblock:python"].named_ranges or []
        assert len(entries) == 2
        # Different namedRangeIds
        ids = {e.named_range_id for e in entries}
        assert len(ids) == 2

    def test_inline_code_push(self) -> None:
        """`code` → TextRun with Courier New font."""
        md = "Use `print()` here.\n"
        doc = markdown_to_document({"Tab_1": md})
        tab = (doc.tabs or [None])[0]
        dt = tab.document_tab if tab else None
        body = dt.body.content if dt and dt.body else []
        code_runs = [
            pe.text_run
            for se in body
            if se.paragraph
            for pe in (se.paragraph.elements or [])
            if pe.text_run
            and pe.text_run.text_style
            and pe.text_run.text_style.weighted_font_family
            and pe.text_run.text_style.weighted_font_family.font_family == "Courier New"
        ]
        assert len(code_runs) == 1
        assert "print()" in (code_runs[0].content or "")


# ---------------------------------------------------------------------------
# Test 5: Special elements — pull path (Document → markdown)
# ---------------------------------------------------------------------------


def _make_doc_with_named_range_table(
    nr_name: str,
    cell_text: str = "some content",
) -> Document:
    """Build a Document with a 1x1 table and an extradoc:* named range covering it."""
    cell_para = StructuralElement(
        paragraph=Paragraph(
            elements=[
                ParagraphElement(text_run=TextRun(content=cell_text + "\n")),
            ],
            paragraph_style=ParagraphStyle(
                named_style_type=ParagraphStyleNamedStyleType.NORMAL_TEXT
            ),
        )
    )
    table = Table(
        rows=1,
        columns=1,
        table_rows=[
            TableRow(
                table_cells=[
                    TableCell(
                        content=[cell_para],
                        table_cell_style=TableCellStyle(),
                    )
                ]
            )
        ],
    )
    doc = _make_doc([StructuralElement(table=table)])
    # Reindex to get real indices
    doc = reindex_document(doc)

    # Find the table's start_index
    tab = doc.tabs[0]  # type: ignore[index]
    body = tab.document_tab.body.content  # type: ignore[union-attr]
    table_se = next(se for se in body if se.table is not None)
    si = table_se.start_index
    ei = table_se.end_index

    # Add named ranges to the DocumentTab
    nr = NamedRanges(
        name=nr_name,
        named_ranges=[
            NamedRange(
                named_range_id="kix.test_nr_1",
                name=nr_name,
                ranges=[Range(start_index=si, end_index=ei)],
            )
        ],
    )
    tab.document_tab.named_ranges = {nr_name: nr}  # type: ignore[union-attr]
    return doc


def _make_doc_with_adjacent_codeblock_ranges() -> Document:
    doc = _make_doc(
        [
            StructuralElement(
                table=Table(
                    rows=1,
                    columns=1,
                    table_rows=[
                        TableRow(
                            table_cells=[
                                TableCell(
                                    content=[
                                        StructuralElement(
                                            paragraph=Paragraph(
                                                elements=[
                                                    ParagraphElement(
                                                        text_run=TextRun(
                                                            content="print('hello')\n"
                                                        )
                                                    )
                                                ],
                                                paragraph_style=ParagraphStyle(
                                                    named_style_type=ParagraphStyleNamedStyleType.NORMAL_TEXT
                                                ),
                                            )
                                        )
                                    ],
                                    table_cell_style=TableCellStyle(),
                                )
                            ]
                        )
                    ],
                )
            ),
            StructuralElement(
                table=Table(
                    rows=1,
                    columns=1,
                    table_rows=[
                        TableRow(
                            table_cells=[
                                TableCell(
                                    content=[
                                        StructuralElement(
                                            paragraph=Paragraph(
                                                elements=[
                                                    ParagraphElement(
                                                        text_run=TextRun(
                                                            content='{"stage": "edited"}\n'
                                                        )
                                                    )
                                                ],
                                                paragraph_style=ParagraphStyle(
                                                    named_style_type=ParagraphStyleNamedStyleType.NORMAL_TEXT
                                                ),
                                            )
                                        )
                                    ],
                                    table_cell_style=TableCellStyle(),
                                )
                            ]
                        )
                    ],
                )
            ),
        ]
    )
    doc = reindex_document(doc)
    tab = doc.tabs[0]  # type: ignore[index]
    body = tab.document_tab.body.content  # type: ignore[union-attr]
    tables = [se for se in body if se.table is not None]
    first_table = tables[0]
    second_table = tables[1]
    tab.document_tab.named_ranges = {  # type: ignore[union-attr]
        "extradoc:codeblock:python": NamedRanges(
            name="extradoc:codeblock:python",
            named_ranges=[
                NamedRange(
                    named_range_id="kix.python",
                    name="extradoc:codeblock:python",
                    ranges=[
                        Range(
                            start_index=first_table.start_index + 1,
                            end_index=second_table.start_index + 1,
                        )
                    ],
                )
            ],
        ),
        "extradoc:codeblock:json": NamedRanges(
            name="extradoc:codeblock:json",
            named_ranges=[
                NamedRange(
                    named_range_id="kix.json",
                    name="extradoc:codeblock:json",
                    ranges=[
                        Range(
                            start_index=second_table.start_index + 1,
                            end_index=second_table.end_index + 2,
                        )
                    ],
                )
            ],
        ),
    }
    return doc


class TestSpecialElementsPull:
    """Verify that named ranges drive serialization on the pull path."""

    def test_codeblock_pull(self) -> None:
        """extradoc:codeblock:python named range → ```python\\ncode\\n```."""
        doc = _make_doc_with_named_range_table(
            "extradoc:codeblock:python", "print('hello')"
        )
        per_tab = document_to_markdown(doc)
        md = per_tab["Tab_1"]["document.md"]
        assert "```python" in md
        assert "print('hello')" in md
        assert "```" in md

    def test_codeblock_pull_tolerates_table_start_one_before_named_range(self) -> None:
        """Live Docs can report table start one code point before the named range."""
        doc = _make_doc_with_named_range_table(
            "extradoc:codeblock:python", "print('hello')"
        )
        tab = doc.tabs[0]  # type: ignore[index]
        named_ranges = tab.document_tab.named_ranges  # type: ignore[union-attr]
        entry = named_ranges["extradoc:codeblock:python"].named_ranges[0]
        entry.ranges[0].start_index += 1

        per_tab = document_to_markdown(doc)
        md = per_tab["Tab_1"]["document.md"]
        assert "```python" in md
        assert "print('hello')" in md
        assert "| --- |" not in md

    def test_codeblock_pull_prefers_nearest_overlapping_named_range(self) -> None:
        """Adjacent codeblock ranges must not make the later table inherit the earlier language."""
        doc = _make_doc_with_adjacent_codeblock_ranges()

        per_tab = document_to_markdown(doc)
        md = per_tab["Tab_1"]["document.md"]

        assert "```python" in md
        assert "```json" in md
        assert md.count("```python") == 1
        assert md.count("```json") == 1

    def test_callout_warning_pull(self) -> None:
        """extradoc:callout:warning → > [!WARNING]\\n> text."""
        doc = _make_doc_with_named_range_table("extradoc:callout:warning", "Watch out!")
        per_tab = document_to_markdown(doc)
        md = per_tab["Tab_1"]["document.md"]
        assert "> [!WARNING]" in md
        assert "> Watch out!" in md

    def test_blockquote_pull(self) -> None:
        """extradoc:blockquote → > text."""
        doc = _make_doc_with_named_range_table("extradoc:blockquote", "Wise words")
        per_tab = document_to_markdown(doc)
        md = per_tab["Tab_1"]["document.md"]
        assert "> Wise words" in md

    def test_no_named_range_is_regular_table(self) -> None:
        """A 1x1 table WITHOUT a named range serializes as a regular GFM table."""
        cell_para = StructuralElement(
            paragraph=Paragraph(
                elements=[ParagraphElement(text_run=TextRun(content="data\n"))],
                paragraph_style=ParagraphStyle(
                    named_style_type=ParagraphStyleNamedStyleType.NORMAL_TEXT
                ),
            )
        )
        table = Table(
            rows=1,
            columns=1,
            table_rows=[
                TableRow(
                    table_cells=[
                        TableCell(
                            content=[cell_para],
                            table_cell_style=TableCellStyle(),
                        )
                    ]
                )
            ],
        )
        doc = _make_doc([StructuralElement(table=table)])
        per_tab = document_to_markdown(doc)
        md = per_tab["Tab_1"]["document.md"]
        # Should be GFM table, not code fence
        assert "```" not in md
        assert "> " not in md
        assert "| data |" in md

    def test_multiple_same_type_pull(self) -> None:
        """Two extradoc:callout:warning named ranges → both pulled as > [!WARNING]."""
        cell_para1 = StructuralElement(
            paragraph=Paragraph(
                elements=[
                    ParagraphElement(text_run=TextRun(content="First warning\n"))
                ],
                paragraph_style=ParagraphStyle(
                    named_style_type=ParagraphStyleNamedStyleType.NORMAL_TEXT
                ),
            )
        )
        cell_para2 = StructuralElement(
            paragraph=Paragraph(
                elements=[
                    ParagraphElement(text_run=TextRun(content="Second warning\n"))
                ],
                paragraph_style=ParagraphStyle(
                    named_style_type=ParagraphStyleNamedStyleType.NORMAL_TEXT
                ),
            )
        )
        t1 = Table(
            rows=1,
            columns=1,
            table_rows=[
                TableRow(
                    table_cells=[
                        TableCell(
                            content=[cell_para1], table_cell_style=TableCellStyle()
                        )
                    ]
                )
            ],
        )
        t2 = Table(
            rows=1,
            columns=1,
            table_rows=[
                TableRow(
                    table_cells=[
                        TableCell(
                            content=[cell_para2], table_cell_style=TableCellStyle()
                        )
                    ]
                )
            ],
        )
        doc = _make_doc([StructuralElement(table=t1), StructuralElement(table=t2)])
        doc = reindex_document(doc)

        tab = doc.tabs[0]  # type: ignore[index]
        body = tab.document_tab.body.content  # type: ignore[union-attr]
        table_ses = [se for se in body if se.table is not None]
        assert len(table_ses) == 2

        nr1 = NamedRange(
            named_range_id="kix.nr1",
            name="extradoc:callout:warning",
            ranges=[
                Range(
                    start_index=table_ses[0].start_index,
                    end_index=table_ses[0].end_index,
                )
            ],
        )
        nr2 = NamedRange(
            named_range_id="kix.nr2",
            name="extradoc:callout:warning",
            ranges=[
                Range(
                    start_index=table_ses[1].start_index,
                    end_index=table_ses[1].end_index,
                )
            ],
        )
        tab.document_tab.named_ranges = {  # type: ignore[union-attr]
            "extradoc:callout:warning": NamedRanges(
                name="extradoc:callout:warning",
                named_ranges=[nr1, nr2],
            )
        }

        per_tab = document_to_markdown(doc)
        md = per_tab["Tab_1"]["document.md"]
        assert md.count("> [!WARNING]") == 2
        assert "First warning" in md
        assert "Second warning" in md

    def test_inline_code_pull(self) -> None:
        """Courier New text run → `code` in markdown."""
        ts = TextStyle.model_validate(
            {
                "weightedFontFamily": {"fontFamily": "Courier New"},
                "fontSize": {"magnitude": 10, "unit": "PT"},
            }
        )
        doc = _make_doc(
            [
                StructuralElement(
                    paragraph=Paragraph(
                        elements=[
                            ParagraphElement(text_run=TextRun(content="Use ")),
                            ParagraphElement(
                                text_run=TextRun(content="print()", text_style=ts)
                            ),
                            ParagraphElement(text_run=TextRun(content=" here.\n")),
                        ],
                        paragraph_style=ParagraphStyle(
                            named_style_type=ParagraphStyleNamedStyleType.NORMAL_TEXT
                        ),
                    )
                )
            ]
        )
        per_tab = document_to_markdown(doc)
        md = per_tab["Tab_1"]["document.md"]
        assert "`print()`" in md

    def test_relative_url_fix(self) -> None:
        """http://LICENSE (API-mangled relative URL) → LICENSE on pull."""
        doc = _make_doc(
            [
                _make_para(
                    "read the license",
                    text_style=TextStyle(link=Link(url="http://LICENSE")),
                )
            ]
        )
        per_tab = document_to_markdown(doc)
        md = per_tab["Tab_1"]["document.md"]
        assert "[read the license](LICENSE)" in md
        assert "http://LICENSE" not in md

    def test_list_pull_derives_nesting_from_indent_when_bullet_level_missing(
        self,
    ) -> None:
        doc = reindex_document(
            markdown_to_document(
                {"Tab_1": "- parent\n  - child\n"},
                document_id="nested-list-pull",
                title="Nested List Pull",
                tab_ids={"Tab_1": "t.0"},
            )
        )

        body = doc.tabs[0].document_tab.body.content
        child_paragraph = body[1].paragraph
        assert child_paragraph is not None
        assert child_paragraph.bullet is not None
        child_paragraph.bullet.nesting_level = None

        per_tab = document_to_markdown(doc)
        md = per_tab["Tab_1"]["document.md"]

        assert "- parent" in md
        assert "  - child" in md


# ---------------------------------------------------------------------------
# Test 6: Round-trip — markdown → Document → markdown for special elements
# ---------------------------------------------------------------------------


class TestSpecialElementsRoundTrip:
    def test_code_fence_round_trip(self) -> None:
        """Code fence survives markdown → Document → markdown."""
        source = textwrap.dedent("""\
            # Title

            ```python
            def hello():
                print("hi")
            ```

            After the block.
            """)
        doc = markdown_to_document({"Tab_1": source})
        per_tab = document_to_markdown(doc)
        result = per_tab["Tab_1"]["document.md"]
        assert "```python" in result
        assert "def hello():" in result
        assert '    print("hi")' in result
        assert "After the block." in result

    def test_callout_round_trip(self) -> None:
        """> [!WARNING] survives markdown → Document → markdown."""
        source = textwrap.dedent("""\
            # Guide

            > [!WARNING]
            > Do not delete this file.

            Continue here.
            """)
        doc = markdown_to_document({"Tab_1": source})
        per_tab = document_to_markdown(doc)
        result = per_tab["Tab_1"]["document.md"]
        assert "> [!WARNING]" in result
        assert "Do not delete this file." in result

    def test_blockquote_round_trip(self) -> None:
        """> text survives markdown → Document → markdown."""
        source = textwrap.dedent("""\
            Intro paragraph.

            > The greatest glory in living lies not in never falling.

            End paragraph.
            """)
        doc = markdown_to_document({"Tab_1": source})
        per_tab = document_to_markdown(doc)
        result = per_tab["Tab_1"]["document.md"]
        assert "> The greatest glory" in result

    def test_inline_code_round_trip(self) -> None:
        """`code` survives markdown → Document → markdown."""
        source = "Use `print()` to display output.\n"
        doc = markdown_to_document({"Tab_1": source})
        per_tab = document_to_markdown(doc)
        result = per_tab["Tab_1"]["document.md"]
        assert "`print()`" in result

    def test_mixed_content_round_trip(self) -> None:
        """Mixed special and normal content round-trips correctly."""
        source = textwrap.dedent("""\
            # API Reference

            Use the `get()` method.

            ```bash
            curl https://api.example.com/data
            ```

            > [!INFO]
            > Requires authentication.

            > See also the [docs](https://docs.example.com).

            Normal paragraph after.
            """)
        doc = markdown_to_document({"Tab_1": source})
        per_tab = document_to_markdown(doc)
        result = per_tab["Tab_1"]["document.md"]
        assert "`get()`" in result
        assert "```bash" in result
        assert "curl https://api.example.com/data" in result
        assert "> [!INFO]" in result
        assert "> See also the" in result
        assert "Normal paragraph after." in result


# ---------------------------------------------------------------------------
# Test 7: Reconciler named-range diff
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Test 8: diff() uses raw JSON as base when .raw/document.json is present
# ---------------------------------------------------------------------------


class TestDiffRawJsonBase:
    """Verify that diff() uses .raw/document.json as the base document for
    markdown-format folders, giving accurate real-API startIndex values for
    deleteContentRange requests instead of mock-computed approximations.
    """

    def _setup_markdown_folder(
        self,
        tmp_path: Path,
        md_content: str,
        doc_id: str = "test-doc-id",
    ) -> Path:
        """Create a markdown folder structure (as pull-md would produce)."""
        folder = tmp_path / doc_id
        folder.mkdir()

        doc = markdown_to_document(
            {"Tab_1": md_content},
            document_id=doc_id,
            title="Test",
            tab_ids={"Tab_1": "t.0"},
        )
        bundle = DocumentWithComments(
            document=doc,
            comments=FileComments(file_id=doc_id),
        )
        _md_serde.serialize(bundle, folder)

        return folder

    def test_uses_raw_json_base_for_deleteContentRange(self, tmp_path: Path) -> None:
        """deleteContentRange.startIndex must come from raw JSON, not mock reindex.

        We inflate the raw JSON's table startIndex by 100 positions to make the
        test deterministic: if diff() uses the raw JSON, deleteContentRange will
        start at (inflated_cell_si); if it falls back to the mock, it will start
        at the mock-computed (lower) cell_si.
        """
        import json

        from extradoc.client import DocsClient
        from extradoc.reconcile._core import reindex_document

        INFLATE = 100  # Simulated real-API offset

        # Base markdown: callout with old text
        base_md = textwrap.dedent("""\
            # Heading

            Some paragraph.

            > [!WARNING]
            > Original callout text here.

            After callout.
            """)

        # Set up folder
        folder = self._setup_markdown_folder(tmp_path, base_md, "test-raw-base")

        # Build the "raw" API JSON: same doc but with all indices inflated by INFLATE.
        # This simulates the real API placing the table 100 positions higher than mock.
        raw_doc = markdown_to_document(
            {"Tab_1": base_md},
            document_id="test-raw-base",
            title="Test",
            tab_ids={"Tab_1": "t.0"},
        )
        raw_doc_reindexed = reindex_document(raw_doc)

        # Serialize to JSON dict, then inflate all numeric index fields
        raw_dict = raw_doc_reindexed.model_dump(by_alias=True, exclude_none=True)

        def _inflate(obj: object) -> object:
            if isinstance(obj, dict):
                return {
                    k: (
                        _inflate(v) + INFLATE
                        if k in ("startIndex", "endIndex") and isinstance(v, int)
                        else _inflate(v)
                    )
                    for k, v in obj.items()
                }
            if isinstance(obj, list):
                return [_inflate(item) for item in obj]
            return obj

        inflated_dict = _inflate(raw_dict)

        raw_dir = folder / ".raw"
        raw_dir.mkdir(exist_ok=True)
        (raw_dir / "document.json").write_text(
            json.dumps(inflated_dict), encoding="utf-8"
        )

        # Edited markdown: change the callout text
        edited_md = textwrap.dedent("""\
            # Heading

            Some paragraph.

            > [!WARNING]
            > New callout text, completely different.

            After callout.
            """)
        (folder / "Tab_1.md").write_text(edited_md, encoding="utf-8")

        # Run diff
        client = DocsClient.__new__(DocsClient)
        result = client.diff(str(folder))

        all_reqs = [r for batch in result.batches for r in (batch.requests or [])]
        delete_ranges = [
            r.delete_content_range
            for r in all_reqs
            if r.delete_content_range is not None
        ]

        # Find the deleteContentRange that targets callout cell content.
        # With raw JSON as base, all startIndex values should be >= INFLATE
        # (since the raw JSON has every index inflated by INFLATE).
        # With mock as base, the callout cell startIndex would be much smaller.
        cell_deletes = [
            d
            for d in delete_ranges
            if d.range and (d.range.start_index or 0) >= INFLATE
        ]
        assert len(cell_deletes) >= 1, (
            f"Expected deleteContentRange with startIndex >= {INFLATE} "
            f"(from raw JSON), but got: {delete_ranges}"
        )

    def test_falls_back_to_mock_when_no_raw_json(self, tmp_path: Path) -> None:
        """Without .raw/document.json, diff() uses mock-reindexed pristine."""
        from extradoc.client import DocsClient

        base_md = "# Heading\n\n> [!INFO]\n> Some info here.\n"
        edited_md = "# Heading\n\n> [!INFO]\n> Updated info text.\n"

        folder = self._setup_markdown_folder(tmp_path, base_md, "test-no-raw")
        (folder / "Tab_1.md").write_text(edited_md, encoding="utf-8")

        # No .raw/ directory — should use mock reindex fallback
        client = DocsClient.__new__(DocsClient)
        result = client.diff(str(folder))

        # Should succeed without error
        assert result.document_id == "test-no-raw"
        # Should produce at least one batch with change requests
        all_reqs = [r for batch in result.batches for r in (batch.requests or [])]
        assert len(all_reqs) > 0, (
            "Expected diff to produce requests for changed callout"
        )

    def test_heading_edit_with_consecutive_callouts_avoids_separator_insert(
        self, tmp_path: Path
    ) -> None:
        """Editing an unrelated heading must not reinsert callout separators.

        The raw Docs API stores a bare '\\n' paragraph between consecutive
        callout tables. Markdown preserves that separator visually, so the raw
        base normalizer must keep it. If it strips the separator, diff() later
        emits an insertText '\\n' at the preceding table boundary, which the
        real Google Docs API rejects with a 400 INVALID_ARGUMENT error.
        """
        import json

        from extradoc.client import DocsClient

        base_md = textwrap.dedent("""\
            # Title

            > [!WARNING]
            > Warn 1.

            > [!INFO]
            > Info 2.

            ## Tail

            Tail paragraph.
            """)
        edited_md = textwrap.dedent("""\
            # Title Updated

            > [!WARNING]
            > Warn 1.

            > [!INFO]
            > Info 2.

            ## Tail

            Tail paragraph.
            """)

        folder = self._setup_markdown_folder(
            tmp_path, base_md, "test-callout-separators"
        )

        raw_doc = markdown_to_document(
            {"Tab_1": base_md},
            document_id="test-callout-separators",
            title="Test",
            tab_ids={"Tab_1": "t.0"},
        )
        raw_dir = folder / ".raw"
        raw_dir.mkdir(exist_ok=True)
        (raw_dir / "document.json").write_text(
            json.dumps(
                reindex_document(raw_doc).model_dump(by_alias=True, exclude_none=True)
            ),
            encoding="utf-8",
        )

        (folder / "Tab_1.md").write_text(edited_md, encoding="utf-8")

        client = DocsClient.__new__(DocsClient)
        result = client.diff(str(folder))

        all_reqs = [r for batch in result.batches for r in (batch.requests or [])]
        newline_inserts = [
            r.insert_text
            for r in all_reqs
            if r.insert_text is not None and r.insert_text.text == "\n"
        ]
        assert not newline_inserts, (
            "Diff should not emit bare separator insertText requests for "
            f"consecutive callouts: {newline_inserts}"
        )
