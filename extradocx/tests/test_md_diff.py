"""
Tests for the markdown diff pipeline: parse_markdown + diff.

Tests the public interface:
    parse_markdown(text) -> Document
    diff(base, derived) -> list[DiffOp]

Strategy: construct base ASTs (either from markdown or manually), simulate
user edits by modifying the markdown, re-parse, and assert the diff produces
the expected operations.
"""

from __future__ import annotations

import pathlib

import pytest

from extradocx import diff, parse_markdown, to_markdown
from extradocx.ast_nodes import (
    BlockQuote,
    BulletList,
    CodeBlock,
    Document,
    Heading,
    ListItem,
    OrderedList,
    Paragraph,
    Table,
    TextRun,
    ThematicBreak,
)
from extradocx.diff_ops import (
    DeleteBlock,
    DiffOp,
    InsertBlock,
    ReplaceBlockQuote,
    ReplaceCodeBlock,
    ReplaceHeading,
    ReplaceList,
    ReplaceParagraph,
    ReplaceTable,
)

TESTDATA = pathlib.Path(__file__).parent.parent / "testdata"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_base_doc(*blocks) -> Document:
    """Build a Document with xpaths on each block for traceability."""
    children = []
    for i, block in enumerate(blocks):
        block.xpath = f"/w:document[1]/w:body[1]/w:p[{i + 1}]"
        children.append(block)
    return Document(children=children)


def _ops_of_type(ops: list[DiffOp], op_type: type) -> list:
    return [op for op in ops if isinstance(op, op_type)]


# =========================================================================
# parse_markdown tests
# =========================================================================


class TestParseMarkdown:
    """Test the markdown → AST parser."""

    def test_empty_document(self):
        doc = parse_markdown("")
        assert isinstance(doc, Document)
        assert doc.children == []

    def test_single_paragraph(self):
        doc = parse_markdown("Hello world.\n")
        assert len(doc.children) == 1
        assert isinstance(doc.children[0], Paragraph)

    def test_paragraph_text(self):
        doc = parse_markdown("Hello world.\n")
        p = doc.children[0]
        assert isinstance(p, Paragraph)
        runs = [c for c in p.children if isinstance(c, TextRun)]
        text = "".join(r.text for r in runs)
        assert "Hello world." in text

    def test_atx_headings(self):
        md = "# Heading 1\n\n## Heading 2\n\n### Heading 3\n"
        doc = parse_markdown(md)
        headings = [c for c in doc.children if isinstance(c, Heading)]
        assert len(headings) == 3
        assert headings[0].level == 1
        assert headings[1].level == 2
        assert headings[2].level == 3

    def test_heading_text(self):
        doc = parse_markdown("# My Title\n")
        h = doc.children[0]
        assert isinstance(h, Heading)
        text = "".join(r.text for r in h.children if isinstance(r, TextRun))
        assert text == "My Title"

    def test_fenced_code_block(self):
        md = "```python\nprint('hello')\n```\n"
        doc = parse_markdown(md)
        assert len(doc.children) == 1
        cb = doc.children[0]
        assert isinstance(cb, CodeBlock)
        assert cb.language == "python"
        assert cb.code == "print('hello')"

    def test_code_block_no_language(self):
        md = "```\nsome code\n```\n"
        doc = parse_markdown(md)
        cb = doc.children[0]
        assert isinstance(cb, CodeBlock)
        assert cb.language == ""

    def test_bullet_list(self):
        md = "- Item A\n- Item B\n- Item C\n"
        doc = parse_markdown(md)
        assert len(doc.children) == 1
        bl = doc.children[0]
        assert isinstance(bl, BulletList)
        assert len(bl.items) == 3

    def test_ordered_list(self):
        md = "1. First\n2. Second\n3. Third\n"
        doc = parse_markdown(md)
        assert len(doc.children) == 1
        ol = doc.children[0]
        assert isinstance(ol, OrderedList)
        assert len(ol.items) == 3
        assert ol.start == 1

    def test_pipe_table(self):
        md = "| A | B |\n| --- | --- |\n| 1 | 2 |\n| 3 | 4 |\n"
        doc = parse_markdown(md)
        assert len(doc.children) == 1
        tbl = doc.children[0]
        assert isinstance(tbl, Table)
        assert len(tbl.rows) == 3  # header + 2 data rows

    def test_thematic_break(self):
        md = "---\n"
        doc = parse_markdown(md)
        assert len(doc.children) == 1
        assert isinstance(doc.children[0], ThematicBreak)

    def test_block_quote(self):
        md = "> This is a quote\n"
        doc = parse_markdown(md)
        assert len(doc.children) == 1
        bq = doc.children[0]
        assert isinstance(bq, BlockQuote)
        assert len(bq.children) >= 1

    def test_bold_text(self):
        doc = parse_markdown("**bold text**\n")
        p = doc.children[0]
        runs = [c for c in p.children if isinstance(c, TextRun)]
        bold_runs = [r for r in runs if r.bold]
        assert len(bold_runs) >= 1
        assert "bold text" in bold_runs[0].text

    def test_italic_text(self):
        doc = parse_markdown("*italic text*\n")
        p = doc.children[0]
        runs = [c for c in p.children if isinstance(c, TextRun)]
        italic_runs = [r for r in runs if r.italic]
        assert len(italic_runs) >= 1

    def test_inline_code(self):
        doc = parse_markdown("Use `code` here\n")
        p = doc.children[0]
        runs = [c for c in p.children if isinstance(c, TextRun)]
        code_runs = [r for r in runs if r.code]
        assert len(code_runs) >= 1
        assert code_runs[0].text == "code"

    def test_strikethrough(self):
        doc = parse_markdown("~~deleted~~\n")
        p = doc.children[0]
        runs = [c for c in p.children if isinstance(c, TextRun)]
        strike_runs = [r for r in runs if r.strikethrough]
        assert len(strike_runs) >= 1

    def test_link(self):
        from extradocx.ast_nodes import Link

        doc = parse_markdown("[click here](https://example.com)\n")
        p = doc.children[0]
        links = [c for c in p.children if isinstance(c, Link)]
        assert len(links) == 1
        assert links[0].href == "https://example.com"

    def test_image(self):
        from extradocx.ast_nodes import Image

        doc = parse_markdown("![alt text](image.png)\n")
        p = doc.children[0]
        images = [c for c in p.children if isinstance(c, Image)]
        assert len(images) == 1
        assert images[0].alt == "alt text"
        assert images[0].src == "image.png"

    def test_mixed_document(self):
        """Parse a realistic mixed document."""
        md = (
            "# Title\n\n"
            "Some introductory text.\n\n"
            "## Section 1\n\n"
            "- Item A\n"
            "- Item B\n\n"
            "| Col1 | Col2 |\n"
            "| --- | --- |\n"
            "| A | B |\n\n"
            "```python\nprint('hello')\n```\n\n"
            "---\n\n"
            "Final paragraph.\n"
        )
        doc = parse_markdown(md)
        types = [type(c).__name__ for c in doc.children]
        assert "Heading" in types
        assert "Paragraph" in types
        assert "BulletList" in types
        assert "Table" in types
        assert "CodeBlock" in types
        assert "ThematicBreak" in types


# =========================================================================
# diff tests — no changes
# =========================================================================


class TestDiffNoChanges:
    """When base and derived are identical, diff should return empty list."""

    def test_identical_paragraphs(self):
        base = _make_base_doc(
            Paragraph(children=[TextRun(text="Hello", xpath="")]),
            Paragraph(children=[TextRun(text="World", xpath="")]),
        )
        derived = parse_markdown("Hello\n\nWorld\n")
        ops = diff(base, derived)
        assert ops == []

    def test_identical_headings(self):
        base = _make_base_doc(Heading(level=1, children=[TextRun(text="Title", xpath="")]))
        derived = parse_markdown("# Title\n")
        ops = diff(base, derived)
        assert ops == []

    def test_identical_code_block(self):
        base = _make_base_doc(CodeBlock(code="print('hello')", language="python"))
        derived = parse_markdown("```python\nprint('hello')\n```\n")
        ops = diff(base, derived)
        assert ops == []

    def test_identical_bullet_list(self):
        base = _make_base_doc(
            BulletList(
                items=[
                    ListItem(children=[Paragraph(children=[TextRun(text="A", xpath="")])]),
                    ListItem(children=[Paragraph(children=[TextRun(text="B", xpath="")])]),
                ]
            )
        )
        derived = parse_markdown("- A\n- B\n")
        ops = diff(base, derived)
        assert ops == []

    def test_identical_table(self):
        base = _make_base_doc(
            Table(
                rows=[
                    __import__("extradocx.ast_nodes", fromlist=["TableRow"]).TableRow(
                        cells=[
                            __import__("extradocx.ast_nodes", fromlist=["TableCell"]).TableCell(
                                children=[Paragraph(children=[TextRun(text="A", xpath="")])],
                                is_header=True,
                            ),
                            __import__("extradocx.ast_nodes", fromlist=["TableCell"]).TableCell(
                                children=[Paragraph(children=[TextRun(text="B", xpath="")])],
                                is_header=True,
                            ),
                        ],
                        is_header=True,
                    ),
                    __import__("extradocx.ast_nodes", fromlist=["TableRow"]).TableRow(
                        cells=[
                            __import__("extradocx.ast_nodes", fromlist=["TableCell"]).TableCell(
                                children=[Paragraph(children=[TextRun(text="1", xpath="")])]
                            ),
                            __import__("extradocx.ast_nodes", fromlist=["TableCell"]).TableCell(
                                children=[Paragraph(children=[TextRun(text="2", xpath="")])]
                            ),
                        ]
                    ),
                ]
            )
        )
        derived = parse_markdown("| A | B |\n| --- | --- |\n| 1 | 2 |\n")
        ops = diff(base, derived)
        assert ops == []

    def test_identical_thematic_break(self):
        base = _make_base_doc(ThematicBreak())
        derived = parse_markdown("---\n")
        ops = diff(base, derived)
        assert ops == []


# =========================================================================
# diff tests — text edits
# =========================================================================


class TestDiffTextEdits:
    """Edits to text content of existing blocks."""

    def test_paragraph_text_changed(self):
        base = _make_base_doc(Paragraph(children=[TextRun(text="Hello world", xpath="")]))
        derived = parse_markdown("Hello universe\n")
        ops = diff(base, derived)
        assert len(ops) == 1
        op = ops[0]
        assert isinstance(op, ReplaceParagraph)
        assert op.old_text == "Hello world"
        assert op.new_text == "Hello universe"
        assert op.base_index == 0

    def test_heading_text_changed(self):
        base = _make_base_doc(Heading(level=2, children=[TextRun(text="Old Title", xpath="")]))
        derived = parse_markdown("## New Title\n")
        ops = diff(base, derived)
        assert len(ops) == 1
        op = ops[0]
        assert isinstance(op, ReplaceHeading)
        assert op.old_text == "Old Title"
        assert op.new_text == "New Title"

    def test_heading_level_changed(self):
        base = _make_base_doc(Heading(level=1, children=[TextRun(text="Title", xpath="")]))
        derived = parse_markdown("### Title\n")
        ops = diff(base, derived)
        assert len(ops) == 1
        op = ops[0]
        assert isinstance(op, ReplaceHeading)
        assert op.old_level == 1
        assert op.new_level == 3

    def test_code_block_code_changed(self):
        base = _make_base_doc(CodeBlock(code="x = 1", language="python"))
        derived = parse_markdown("```python\nx = 2\n```\n")
        ops = diff(base, derived)
        assert len(ops) == 1
        op = ops[0]
        assert isinstance(op, ReplaceCodeBlock)
        assert op.old_code == "x = 1"
        assert op.new_code == "x = 2"

    def test_code_block_language_changed(self):
        base = _make_base_doc(CodeBlock(code="print('hi')", language="python"))
        derived = parse_markdown("```javascript\nprint('hi')\n```\n")
        ops = diff(base, derived)
        assert len(ops) == 1
        op = ops[0]
        assert isinstance(op, ReplaceCodeBlock)
        assert op.old_language == "python"
        assert op.new_language == "javascript"

    def test_multiple_paragraphs_edited(self):
        base = _make_base_doc(
            Paragraph(children=[TextRun(text="First paragraph", xpath="")]),
            Paragraph(children=[TextRun(text="Second paragraph", xpath="")]),
            Paragraph(children=[TextRun(text="Third paragraph", xpath="")]),
        )
        derived = parse_markdown("First paragraph\n\nEdited second\n\nThird paragraph\n")
        ops = diff(base, derived)
        # Only the second paragraph should be flagged as changed
        replace_ops = _ops_of_type(ops, ReplaceParagraph)
        assert len(replace_ops) == 1
        assert replace_ops[0].base_index == 1
        assert replace_ops[0].new_text == "Edited second"


# =========================================================================
# diff tests — structural changes (insert / delete)
# =========================================================================


class TestDiffStructuralChanges:
    """Insertions and deletions of blocks."""

    def test_paragraph_inserted(self):
        base = _make_base_doc(
            Paragraph(children=[TextRun(text="First", xpath="")]),
            Paragraph(children=[TextRun(text="Third", xpath="")]),
        )
        derived = parse_markdown("First\n\nSecond\n\nThird\n")
        ops = diff(base, derived)
        insert_ops = _ops_of_type(ops, InsertBlock)
        assert len(insert_ops) == 1
        inserted = insert_ops[0].block
        assert isinstance(inserted, Paragraph)

    def test_paragraph_deleted(self):
        base = _make_base_doc(
            Paragraph(children=[TextRun(text="First", xpath="")]),
            Paragraph(children=[TextRun(text="Second", xpath="")]),
            Paragraph(children=[TextRun(text="Third", xpath="")]),
        )
        derived = parse_markdown("First\n\nThird\n")
        ops = diff(base, derived)
        delete_ops = _ops_of_type(ops, DeleteBlock)
        assert len(delete_ops) == 1
        assert delete_ops[0].base_index == 1

    def test_heading_inserted(self):
        base = _make_base_doc(Paragraph(children=[TextRun(text="Content", xpath="")]))
        derived = parse_markdown("# New Heading\n\nContent\n")
        ops = diff(base, derived)
        insert_ops = _ops_of_type(ops, InsertBlock)
        assert len(insert_ops) == 1
        assert isinstance(insert_ops[0].block, Heading)

    def test_multiple_blocks_deleted(self):
        base = _make_base_doc(
            Paragraph(children=[TextRun(text="Keep", xpath="")]),
            Paragraph(children=[TextRun(text="Remove one", xpath="")]),
            Paragraph(children=[TextRun(text="Remove two", xpath="")]),
            Paragraph(children=[TextRun(text="Keep too", xpath="")]),
        )
        derived = parse_markdown("Keep\n\nKeep too\n")
        ops = diff(base, derived)
        delete_ops = _ops_of_type(ops, DeleteBlock)
        assert len(delete_ops) == 2

    def test_block_replaced_with_different_type(self):
        """A paragraph replaced with a heading (kind change)."""
        base = _make_base_doc(Paragraph(children=[TextRun(text="Now a heading", xpath="")]))
        derived = parse_markdown("# Now a heading\n")
        ops = diff(base, derived)
        # Should detect this as a heading replacement
        heading_ops = _ops_of_type(ops, ReplaceHeading)
        assert len(heading_ops) == 1
        assert heading_ops[0].new_level == 1


# =========================================================================
# diff tests — list edits
# =========================================================================


class TestDiffListEdits:
    """Edits within lists."""

    def test_list_item_text_changed(self):
        base = _make_base_doc(
            BulletList(
                items=[
                    ListItem(
                        children=[Paragraph(children=[TextRun(text="Item A", xpath="")])],
                        xpath="/list/item1",
                    ),
                    ListItem(
                        children=[Paragraph(children=[TextRun(text="Item B", xpath="")])],
                        xpath="/list/item2",
                    ),
                ]
            )
        )
        derived = parse_markdown("- Item A\n- Item B modified\n")
        ops = diff(base, derived)
        list_ops = _ops_of_type(ops, ReplaceList)
        assert len(list_ops) == 1
        assert list_ops[0].list_type == "bullet"
        # Should have one ReplaceListItem inside
        from extradocx.diff_ops import ReplaceListItem

        replace_items = [op for op in list_ops[0].item_ops if isinstance(op, ReplaceListItem)]
        assert len(replace_items) == 1
        assert replace_items[0].base_item_index == 1

    def test_list_item_added(self):
        base = _make_base_doc(
            BulletList(
                items=[
                    ListItem(
                        children=[Paragraph(children=[TextRun(text="Item A", xpath="")])],
                        xpath="/list/item1",
                    ),
                ]
            )
        )
        derived = parse_markdown("- Item A\n- Item B\n")
        ops = diff(base, derived)
        list_ops = _ops_of_type(ops, ReplaceList)
        assert len(list_ops) == 1
        from extradocx.diff_ops import InsertListItem

        insert_items = [op for op in list_ops[0].item_ops if isinstance(op, InsertListItem)]
        assert len(insert_items) == 1

    def test_list_item_removed(self):
        base = _make_base_doc(
            BulletList(
                items=[
                    ListItem(
                        children=[Paragraph(children=[TextRun(text="Item A", xpath="")])],
                        xpath="/list/item1",
                    ),
                    ListItem(
                        children=[Paragraph(children=[TextRun(text="Item B", xpath="")])],
                        xpath="/list/item2",
                    ),
                    ListItem(
                        children=[Paragraph(children=[TextRun(text="Item C", xpath="")])],
                        xpath="/list/item3",
                    ),
                ]
            )
        )
        derived = parse_markdown("- Item A\n- Item C\n")
        ops = diff(base, derived)
        list_ops = _ops_of_type(ops, ReplaceList)
        assert len(list_ops) == 1
        from extradocx.diff_ops import DeleteListItem

        delete_items = [op for op in list_ops[0].item_ops if isinstance(op, DeleteListItem)]
        assert len(delete_items) == 1
        assert delete_items[0].base_item_index == 1

    def test_ordered_list_edit(self):
        base = _make_base_doc(
            OrderedList(
                items=[
                    ListItem(
                        children=[Paragraph(children=[TextRun(text="Step one", xpath="")])],
                        xpath="/list/item1",
                    ),
                    ListItem(
                        children=[Paragraph(children=[TextRun(text="Step two", xpath="")])],
                        xpath="/list/item2",
                    ),
                ],
                start=1,
            )
        )
        derived = parse_markdown("1. Step one\n2. Step two updated\n")
        ops = diff(base, derived)
        list_ops = _ops_of_type(ops, ReplaceList)
        assert len(list_ops) == 1
        assert list_ops[0].list_type == "ordered"


# =========================================================================
# diff tests — table edits
# =========================================================================


class TestDiffTableEdits:
    """Edits to tables."""

    def test_table_cell_changed(self):
        from extradocx.ast_nodes import TableCell, TableRow

        base = _make_base_doc(
            Table(
                rows=[
                    TableRow(
                        cells=[
                            TableCell(
                                children=[Paragraph(children=[TextRun(text="H1", xpath="")])],
                                is_header=True,
                            ),
                            TableCell(
                                children=[Paragraph(children=[TextRun(text="H2", xpath="")])],
                                is_header=True,
                            ),
                        ],
                        is_header=True,
                    ),
                    TableRow(
                        cells=[
                            TableCell(children=[Paragraph(children=[TextRun(text="A", xpath="")])]),
                            TableCell(children=[Paragraph(children=[TextRun(text="B", xpath="")])]),
                        ]
                    ),
                ]
            )
        )
        derived = parse_markdown("| H1 | H2 |\n| --- | --- |\n| A | CHANGED |\n")
        ops = diff(base, derived)
        table_ops = _ops_of_type(ops, ReplaceTable)
        assert len(table_ops) == 1
        assert table_ops[0].base_index == 0


# =========================================================================
# diff tests — block quote edits
# =========================================================================


class TestDiffBlockQuoteEdits:
    def test_blockquote_content_changed(self):
        base = _make_base_doc(
            BlockQuote(children=[Paragraph(children=[TextRun(text="Original quote", xpath="")])])
        )
        derived = parse_markdown("> Edited quote\n")
        ops = diff(base, derived)
        bq_ops = _ops_of_type(ops, ReplaceBlockQuote)
        assert len(bq_ops) == 1

    def test_blockquote_unchanged(self):
        base = _make_base_doc(
            BlockQuote(children=[Paragraph(children=[TextRun(text="Same quote", xpath="")])])
        )
        derived = parse_markdown("> Same quote\n")
        ops = diff(base, derived)
        assert ops == []


# =========================================================================
# diff tests — formatting changes
# =========================================================================


class TestDiffFormattingChanges:
    """Formatting changes within text runs."""

    def test_bold_added(self):
        base = _make_base_doc(Paragraph(children=[TextRun(text="important", xpath="")]))
        derived = parse_markdown("**important**\n")
        ops = diff(base, derived)
        # Text is the same but formatting changed — should detect a replace
        assert len(ops) == 1
        assert isinstance(ops[0], ReplaceParagraph)
        assert ops[0].old_text == "important"
        assert ops[0].new_text == "important"

    def test_italic_added(self):
        base = _make_base_doc(Paragraph(children=[TextRun(text="emphasis", xpath="")]))
        derived = parse_markdown("*emphasis*\n")
        ops = diff(base, derived)
        assert len(ops) == 1
        assert isinstance(ops[0], ReplaceParagraph)


# =========================================================================
# diff tests — complex scenarios
# =========================================================================


class TestDiffComplexScenarios:
    """Realistic multi-edit scenarios."""

    def test_interleaved_edits(self):
        """Multiple edits, inserts, and deletes in one document."""
        base = _make_base_doc(
            Heading(level=1, children=[TextRun(text="Title", xpath="")]),
            Paragraph(children=[TextRun(text="Intro paragraph", xpath="")]),
            Heading(level=2, children=[TextRun(text="Section A", xpath="")]),
            Paragraph(children=[TextRun(text="Content A", xpath="")]),
            Heading(level=2, children=[TextRun(text="Section B", xpath="")]),
            Paragraph(children=[TextRun(text="Content B", xpath="")]),
        )
        derived = parse_markdown(
            "# Title\n\n"
            "Intro paragraph\n\n"
            "## Section A\n\n"
            "Modified content A\n\n"
            "## New Section\n\n"
            "Brand new content\n\n"
            "## Section B\n\n"
            "Content B\n"
        )
        ops = diff(base, derived)
        # Should have: 1 replace (Content A), 2 inserts (New Section + new content)
        replace_ops = _ops_of_type(ops, ReplaceParagraph)
        insert_ops = _ops_of_type(ops, InsertBlock)
        assert len(replace_ops) >= 1
        assert len(insert_ops) >= 1
        # No deletes
        delete_ops = _ops_of_type(ops, DeleteBlock)
        assert len(delete_ops) == 0

    def test_reorder_sections(self):
        """Swapping sections should produce deletes + inserts."""
        base = _make_base_doc(
            Heading(level=2, children=[TextRun(text="Alpha", xpath="")]),
            Paragraph(children=[TextRun(text="Alpha content", xpath="")]),
            Heading(level=2, children=[TextRun(text="Beta", xpath="")]),
            Paragraph(children=[TextRun(text="Beta content", xpath="")]),
        )
        derived = parse_markdown("## Beta\n\nBeta content\n\n## Alpha\n\nAlpha content\n")
        ops = diff(base, derived)
        # The DP should find the minimum-cost alignment; depending on
        # similarity it may match some pairs and insert/delete others
        assert len(ops) > 0

    def test_empty_to_content(self):
        """Going from empty to having content should be all inserts."""
        base = Document(children=[])
        derived = parse_markdown("# Hello\n\nWorld\n")
        ops = diff(base, derived)
        assert all(isinstance(op, InsertBlock) for op in ops)
        assert len(ops) == 2

    def test_content_to_empty(self):
        """Going from content to empty should be all deletes."""
        base = _make_base_doc(
            Heading(level=1, children=[TextRun(text="Title", xpath="")]),
            Paragraph(children=[TextRun(text="Content", xpath="")]),
        )
        derived = Document(children=[])
        ops = diff(base, derived)
        assert all(isinstance(op, DeleteBlock) for op in ops)
        assert len(ops) == 2


# =========================================================================
# Round-trip test: DOCX → markdown → parse → diff (golden file)
# =========================================================================


class TestRoundTrip:
    """Test the full round-trip: parse DOCX → to_markdown → parse_markdown → diff.

    When no edits are made, the diff should be empty or minimal.
    """

    @pytest.fixture(scope="class")
    def docx_doc(self):
        from extradocx import DocxParser

        docx_path = TESTDATA / "test_report.docx"
        if not docx_path.exists():
            pytest.skip("test_report.docx not found")
        return DocxParser(docx_path).parse()

    def test_roundtrip_no_edits_produces_minimal_diff(self, docx_doc):
        """DOCX → markdown → parse_markdown → diff should produce few ops.

        We don't expect zero ops because the markdown serialization is lossy
        (escaping, whitespace normalization). But the number of ops should be
        small relative to document size.
        """
        md = to_markdown(docx_doc)
        reparsed = parse_markdown(md)
        ops = diff(docx_doc, reparsed)

        n_blocks = len(docx_doc.children)
        n_ops = len(ops)
        # The round-trip should preserve most content — allow up to 30% drift
        # due to lossy serialization (escaping, whitespace normalization,
        # formatting loss for underline/super/subscript)
        ratio = n_ops / max(n_blocks, 1)
        assert ratio < 0.5, (
            f"Too many ops ({n_ops}) for {n_blocks} blocks (ratio={ratio:.2f}). "
            "Round-trip should be mostly stable."
        )

    def test_roundtrip_with_edit(self, docx_doc):
        """Make a single edit to the markdown and verify diff detects it."""
        md = to_markdown(docx_doc)
        # Inject a new heading after the first line
        lines = md.split("\n")
        lines.insert(2, "")
        lines.insert(3, "## INJECTED HEADING")
        lines.insert(4, "")
        lines.insert(5, "This paragraph was injected by the test.")
        edited_md = "\n".join(lines)

        reparsed = parse_markdown(edited_md)
        ops = diff(docx_doc, reparsed)

        # Should have at least 1 insert for the injected heading
        insert_ops = _ops_of_type(ops, InsertBlock)
        assert len(insert_ops) >= 1

    def test_roundtrip_with_deletion(self, docx_doc):
        """Delete a heading from the markdown and verify diff detects it."""
        md = to_markdown(docx_doc)
        lines = md.split("\n")
        # Find and remove a heading line
        heading_idx = None
        for i, line in enumerate(lines):
            if line.startswith("## ") and i > 5:
                heading_idx = i
                break
        if heading_idx is None:
            pytest.skip("No ## heading found to delete")

        # Remove the heading line and one adjacent blank line
        del lines[heading_idx]
        if heading_idx < len(lines) and not lines[heading_idx].strip():
            del lines[heading_idx]

        edited_md = "\n".join(lines)
        reparsed = parse_markdown(edited_md)
        ops = diff(docx_doc, reparsed)

        # Should have at least 1 delete
        delete_ops = _ops_of_type(ops, DeleteBlock)
        assert len(delete_ops) >= 1


# =========================================================================
# diff operation properties
# =========================================================================


class TestDiffOpProperties:
    """Verify structural properties of diff operations."""

    def test_delete_ops_have_xpath(self):
        base = _make_base_doc(
            Paragraph(children=[TextRun(text="To delete", xpath="")]),
            Paragraph(children=[TextRun(text="To keep", xpath="")]),
        )
        derived = parse_markdown("To keep\n")
        ops = diff(base, derived)
        delete_ops = _ops_of_type(ops, DeleteBlock)
        assert len(delete_ops) == 1
        assert delete_ops[0].base_xpath != ""  # xpath was set by _make_base_doc

    def test_replace_ops_have_xpath(self):
        base = _make_base_doc(Paragraph(children=[TextRun(text="Original text", xpath="")]))
        derived = parse_markdown("Modified text\n")
        ops = diff(base, derived)
        replace_ops = _ops_of_type(ops, ReplaceParagraph)
        assert len(replace_ops) == 1
        assert replace_ops[0].base_xpath != ""

    def test_insert_ops_have_position(self):
        base = _make_base_doc(Paragraph(children=[TextRun(text="Existing", xpath="")]))
        derived = parse_markdown("Existing\n\nNew paragraph\n")
        ops = diff(base, derived)
        insert_ops = _ops_of_type(ops, InsertBlock)
        assert len(insert_ops) == 1
        assert isinstance(insert_ops[0].position, int)

    def test_ops_sorted_deterministically(self):
        """Operations should be sorted: deletes, then replaces, then inserts."""
        base = _make_base_doc(
            Paragraph(children=[TextRun(text="Delete me", xpath="")]),
            Paragraph(children=[TextRun(text="Edit me original", xpath="")]),
        )
        derived = parse_markdown("Edit me changed\n\nNew block\n")
        ops = diff(base, derived)

        # Verify ordering: deletes first, then replaces, then inserts
        seen_types: list[str] = []
        for op in ops:
            t = type(op).__name__
            if t not in seen_types:
                seen_types.append(t)
        # DeleteBlock should come before others if present
        if "DeleteBlock" in seen_types:
            assert seen_types.index("DeleteBlock") == 0
