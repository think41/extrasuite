"""Tests for block-level diff detection."""

import pytest

from extradoc.block_diff import (
    Block,
    BlockChange,
    BlockDiffDetector,
    BlockType,
    ChangeType,
    diff_documents_block_level,
    format_changes,
)


class TestBlockParsing:
    """Tests for parsing XML into block tree."""

    def test_parse_simple_body(self):
        """Parse a document with simple paragraphs."""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<doc id="test-doc" revision="r1">
  <meta><title>Test</title></meta>
  <body class="_base">
    <p>First paragraph</p>
    <p>Second paragraph</p>
  </body>
</doc>"""

        detector = BlockDiffDetector()
        tree = detector._parse_to_block_tree(xml)

        assert tree.block_type == BlockType.DOCUMENT
        assert tree.block_id == "test-doc"
        assert len(tree.children) == 1  # body

        body = tree.children[0]
        assert body.block_type == BlockType.BODY
        assert len(body.children) == 1  # one ContentBlock for consecutive paragraphs

        content_block = body.children[0]
        assert content_block.block_type == BlockType.CONTENT_BLOCK
        assert content_block.attributes["paragraph_count"] == 2

    def test_parse_mixed_content(self):
        """Parse a document with paragraphs and tables."""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<doc id="test-doc" revision="r1">
  <meta><title>Test</title></meta>
  <body class="_base">
    <p>Before table</p>
    <table rows="2" cols="2">
      <tr><td><p>A1</p></td><td><p>B1</p></td></tr>
      <tr><td><p>A2</p></td><td><p>B2</p></td></tr>
    </table>
    <p>After table</p>
  </body>
</doc>"""

        detector = BlockDiffDetector()
        tree = detector._parse_to_block_tree(xml)

        body = tree.children[0]
        assert len(body.children) == 3  # ContentBlock, Table, ContentBlock

        assert body.children[0].block_type == BlockType.CONTENT_BLOCK
        assert body.children[1].block_type == BlockType.TABLE
        assert body.children[2].block_type == BlockType.CONTENT_BLOCK

    def test_parse_table_with_cells(self):
        """Parse table cells as recursive containers."""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<doc id="test-doc" revision="r1">
  <meta><title>Test</title></meta>
  <body class="_base">
    <table rows="2" cols="2">
      <tr><td><p>Cell content</p></td><td><p>More content</p></td></tr>
      <tr><td><p>Row 2</p></td><td><p>Data</p></td></tr>
    </table>
  </body>
</doc>"""

        detector = BlockDiffDetector()
        tree = detector._parse_to_block_tree(xml)

        body = tree.children[0]
        table = body.children[0]

        assert table.block_type == BlockType.TABLE
        assert table.attributes["rows"] == 2
        assert table.attributes["cols"] == 2
        assert len(table.children) == 4  # 4 cells

        # Check cell structure
        cell_00 = table.children[0]
        assert cell_00.block_type == BlockType.TABLE_CELL
        assert cell_00.block_id == "0,0"
        assert len(cell_00.children) == 1  # ContentBlock
        assert cell_00.children[0].block_type == BlockType.CONTENT_BLOCK

    def test_parse_headings(self):
        """Parse headings as paragraphs in content blocks."""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<doc id="test-doc" revision="r1">
  <meta><title>Test</title></meta>
  <body class="_base">
    <h1>Heading 1</h1>
    <p>Paragraph</p>
    <h2>Heading 2</h2>
  </body>
</doc>"""

        detector = BlockDiffDetector()
        tree = detector._parse_to_block_tree(xml)

        body = tree.children[0]
        # All consecutive paragraph-like elements grouped into one ContentBlock
        assert len(body.children) == 1
        assert body.children[0].block_type == BlockType.CONTENT_BLOCK
        assert body.children[0].attributes["paragraph_count"] == 3

    def test_parse_headers_footers_footnotes(self):
        """Parse headers, footers, and footnotes."""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<doc id="test-doc" revision="r1">
  <meta><title>Test</title></meta>
  <body class="_base">
    <p>Body content</p>
  </body>
  <header id="kix.hdr1" class="_base">
    <p>Header text</p>
  </header>
  <footer id="kix.ftr1" class="_base">
    <p>Footer text</p>
  </footer>
  <footnote id="kix.fn1">
    <p>Footnote content</p>
  </footnote>
</doc>"""

        detector = BlockDiffDetector()
        tree = detector._parse_to_block_tree(xml)

        assert len(tree.children) == 4  # body, header, footer, footnote

        body = tree.children[0]
        assert body.block_type == BlockType.BODY

        header = tree.children[1]
        assert header.block_type == BlockType.HEADER
        assert header.block_id == "kix.hdr1"

        footer = tree.children[2]
        assert footer.block_type == BlockType.FOOTER
        assert footer.block_id == "kix.ftr1"

        footnote = tree.children[3]
        assert footnote.block_type == BlockType.FOOTNOTE
        assert footnote.block_id == "kix.fn1"

    def test_parse_toc(self):
        """Parse table of contents as single block."""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<doc id="test-doc" revision="r1">
  <meta><title>Test</title></meta>
  <body class="_base">
    <p>Before TOC</p>
    <toc>
      <p>TOC Entry 1</p>
      <p>TOC Entry 2</p>
    </toc>
    <p>After TOC</p>
  </body>
</doc>"""

        detector = BlockDiffDetector()
        tree = detector._parse_to_block_tree(xml)

        body = tree.children[0]
        assert len(body.children) == 3  # ContentBlock, TOC, ContentBlock

        toc = body.children[1]
        assert toc.block_type == BlockType.TABLE_OF_CONTENTS


class TestBlockDiff:
    """Tests for diffing block trees."""

    def test_no_changes(self):
        """No changes when documents are identical."""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<doc id="test-doc" revision="r1">
  <meta><title>Test</title></meta>
  <body class="_base">
    <p>Hello world</p>
  </body>
</doc>"""

        changes = diff_documents_block_level(xml, xml)
        assert len(changes) == 0

    def test_content_block_modified(self):
        """Detect modified content block."""
        pristine = """<?xml version="1.0" encoding="UTF-8"?>
<doc id="test-doc" revision="r1">
  <meta><title>Test</title></meta>
  <body class="_base">
    <p>Original text</p>
  </body>
</doc>"""

        current = """<?xml version="1.0" encoding="UTF-8"?>
<doc id="test-doc" revision="r1">
  <meta><title>Test</title></meta>
  <body class="_base">
    <p>Modified text</p>
  </body>
</doc>"""

        changes = diff_documents_block_level(pristine, current)

        assert len(changes) == 1
        assert changes[0].change_type == ChangeType.MODIFIED
        assert changes[0].block_type == BlockType.CONTENT_BLOCK
        assert "Original text" in changes[0].before_xml
        assert "Modified text" in changes[0].after_xml

    def test_content_block_added(self):
        """Detect added content block."""
        pristine = """<?xml version="1.0" encoding="UTF-8"?>
<doc id="test-doc" revision="r1">
  <meta><title>Test</title></meta>
  <body class="_base">
    <p>First paragraph</p>
    <table rows="1" cols="1"><tr><td><p>Cell</p></td></tr></table>
  </body>
</doc>"""

        current = """<?xml version="1.0" encoding="UTF-8"?>
<doc id="test-doc" revision="r1">
  <meta><title>Test</title></meta>
  <body class="_base">
    <p>First paragraph</p>
    <table rows="1" cols="1"><tr><td><p>Cell</p></td></tr></table>
    <p>New paragraph after table</p>
  </body>
</doc>"""

        changes = diff_documents_block_level(pristine, current)

        assert len(changes) == 1
        assert changes[0].change_type == ChangeType.ADDED
        assert changes[0].block_type == BlockType.CONTENT_BLOCK
        assert "New paragraph" in changes[0].after_xml

    def test_content_block_deleted(self):
        """Detect deleted content block."""
        pristine = """<?xml version="1.0" encoding="UTF-8"?>
<doc id="test-doc" revision="r1">
  <meta><title>Test</title></meta>
  <body class="_base">
    <p>First paragraph</p>
    <table rows="1" cols="1"><tr><td><p>Cell</p></td></tr></table>
    <p>Paragraph to delete</p>
  </body>
</doc>"""

        current = """<?xml version="1.0" encoding="UTF-8"?>
<doc id="test-doc" revision="r1">
  <meta><title>Test</title></meta>
  <body class="_base">
    <p>First paragraph</p>
    <table rows="1" cols="1"><tr><td><p>Cell</p></td></tr></table>
  </body>
</doc>"""

        changes = diff_documents_block_level(pristine, current)

        assert len(changes) == 1
        assert changes[0].change_type == ChangeType.DELETED
        assert changes[0].block_type == BlockType.CONTENT_BLOCK
        assert "Paragraph to delete" in changes[0].before_xml

    def test_table_added(self):
        """Detect added table."""
        pristine = """<?xml version="1.0" encoding="UTF-8"?>
<doc id="test-doc" revision="r1">
  <meta><title>Test</title></meta>
  <body class="_base">
    <p>Before</p>
    <p>After</p>
  </body>
</doc>"""

        current = """<?xml version="1.0" encoding="UTF-8"?>
<doc id="test-doc" revision="r1">
  <meta><title>Test</title></meta>
  <body class="_base">
    <p>Before</p>
    <table rows="2" cols="2">
      <tr><td><p>A</p></td><td><p>B</p></td></tr>
      <tr><td><p>C</p></td><td><p>D</p></td></tr>
    </table>
    <p>After</p>
  </body>
</doc>"""

        changes = diff_documents_block_level(pristine, current)

        # Should show: original content block modified (split), table added
        table_changes = [c for c in changes if c.block_type == BlockType.TABLE]
        assert len(table_changes) == 1
        assert table_changes[0].change_type == ChangeType.ADDED

    def test_table_deleted(self):
        """Detect deleted table."""
        pristine = """<?xml version="1.0" encoding="UTF-8"?>
<doc id="test-doc" revision="r1">
  <meta><title>Test</title></meta>
  <body class="_base">
    <p>Before</p>
    <table rows="2" cols="2">
      <tr><td><p>A</p></td><td><p>B</p></td></tr>
      <tr><td><p>C</p></td><td><p>D</p></td></tr>
    </table>
    <p>After</p>
  </body>
</doc>"""

        current = """<?xml version="1.0" encoding="UTF-8"?>
<doc id="test-doc" revision="r1">
  <meta><title>Test</title></meta>
  <body class="_base">
    <p>Before</p>
    <p>After</p>
  </body>
</doc>"""

        changes = diff_documents_block_level(pristine, current)

        table_changes = [c for c in changes if c.block_type == BlockType.TABLE]
        assert len(table_changes) == 1
        assert table_changes[0].change_type == ChangeType.DELETED

    def test_table_cell_modified(self):
        """Detect modified table cell content."""
        pristine = """<?xml version="1.0" encoding="UTF-8"?>
<doc id="test-doc" revision="r1">
  <meta><title>Test</title></meta>
  <body class="_base">
    <table rows="2" cols="2">
      <tr><td><p>Original A1</p></td><td><p>B1</p></td></tr>
      <tr><td><p>A2</p></td><td><p>B2</p></td></tr>
    </table>
  </body>
</doc>"""

        current = """<?xml version="1.0" encoding="UTF-8"?>
<doc id="test-doc" revision="r1">
  <meta><title>Test</title></meta>
  <body class="_base">
    <table rows="2" cols="2">
      <tr><td><p>Modified A1</p></td><td><p>B1</p></td></tr>
      <tr><td><p>A2</p></td><td><p>B2</p></td></tr>
    </table>
  </body>
</doc>"""

        changes = diff_documents_block_level(pristine, current)

        assert len(changes) == 1
        assert changes[0].change_type == ChangeType.MODIFIED
        assert changes[0].block_type == BlockType.TABLE

        # Check child changes
        assert len(changes[0].child_changes) >= 1
        cell_change = changes[0].child_changes[0]
        assert cell_change.block_type == BlockType.TABLE_CELL
        assert cell_change.block_id == "0,0"

    def test_multiple_changes(self):
        """Detect multiple different changes."""
        pristine = """<?xml version="1.0" encoding="UTF-8"?>
<doc id="test-doc" revision="r1">
  <meta><title>Test</title></meta>
  <body class="_base">
    <p>Paragraph 1</p>
    <table rows="1" cols="1"><tr><td><p>Table 1</p></td></tr></table>
    <p>Paragraph 2</p>
  </body>
</doc>"""

        current = """<?xml version="1.0" encoding="UTF-8"?>
<doc id="test-doc" revision="r1">
  <meta><title>Test</title></meta>
  <body class="_base">
    <p>Modified Paragraph 1</p>
    <p>Paragraph 2</p>
    <table rows="2" cols="2">
      <tr><td><p>New</p></td><td><p>Table</p></td></tr>
      <tr><td><p>With</p></td><td><p>Data</p></td></tr>
    </table>
  </body>
</doc>"""

        changes = diff_documents_block_level(pristine, current)

        # Should have changes for:
        # - First content block modified
        # - Original table deleted
        # - New table added (different dimensions)
        # - Second content block may move

        assert len(changes) >= 2

    def test_header_modified(self):
        """Detect modified header content."""
        pristine = """<?xml version="1.0" encoding="UTF-8"?>
<doc id="test-doc" revision="r1">
  <meta><title>Test</title></meta>
  <body class="_base"><p>Body</p></body>
  <header id="kix.hdr1" class="_base">
    <p>Original header</p>
  </header>
</doc>"""

        current = """<?xml version="1.0" encoding="UTF-8"?>
<doc id="test-doc" revision="r1">
  <meta><title>Test</title></meta>
  <body class="_base"><p>Body</p></body>
  <header id="kix.hdr1" class="_base">
    <p>Modified header</p>
  </header>
</doc>"""

        changes = diff_documents_block_level(pristine, current)

        assert len(changes) == 1
        assert changes[0].change_type == ChangeType.MODIFIED
        assert changes[0].block_type == BlockType.CONTENT_BLOCK
        assert "header:kix.hdr1" in changes[0].container_path[0]

    def test_footnote_added(self):
        """Detect added footnote."""
        pristine = """<?xml version="1.0" encoding="UTF-8"?>
<doc id="test-doc" revision="r1">
  <meta><title>Test</title></meta>
  <body class="_base"><p>Body</p></body>
</doc>"""

        current = """<?xml version="1.0" encoding="UTF-8"?>
<doc id="test-doc" revision="r1">
  <meta><title>Test</title></meta>
  <body class="_base"><p>Body</p></body>
  <footnote id="kix.fn1">
    <p>New footnote</p>
  </footnote>
</doc>"""

        detector = BlockDiffDetector()
        pristine_tree = detector._parse_to_block_tree(pristine)
        current_tree = detector._parse_to_block_tree(current)

        # Check tree structure
        assert len(pristine_tree.children) == 1  # body only
        assert len(current_tree.children) == 2  # body + footnote


class TestBlockAlignment:
    """Tests for the block alignment algorithm."""

    def test_exact_match_alignment(self):
        """Align blocks with identical content."""
        detector = BlockDiffDetector()

        pristine = [
            Block(BlockType.CONTENT_BLOCK, xml_content="<p>A</p>"),
            Block(
                BlockType.TABLE,
                xml_content="<table/>",
                attributes={"rows": 1, "cols": 1},
            ),
            Block(BlockType.CONTENT_BLOCK, xml_content="<p>B</p>"),
        ]

        current = [
            Block(BlockType.CONTENT_BLOCK, xml_content="<p>A</p>"),
            Block(
                BlockType.TABLE,
                xml_content="<table/>",
                attributes={"rows": 1, "cols": 1},
            ),
            Block(BlockType.CONTENT_BLOCK, xml_content="<p>B</p>"),
        ]

        alignment = detector._align_blocks(pristine, current)

        # All should be matched
        assert len(alignment) == 3
        for p_idx, c_idx in alignment:
            assert p_idx is not None
            assert c_idx is not None
            assert p_idx == c_idx

    def test_structural_match_alignment(self):
        """Align blocks by structural key when content differs."""
        detector = BlockDiffDetector()

        pristine = [
            Block(BlockType.CONTENT_BLOCK, xml_content="<p>Original</p>"),
            Block(
                BlockType.TABLE,
                xml_content="<table rows='2' cols='2'/>",
                attributes={"rows": 2, "cols": 2},
            ),
        ]

        current = [
            Block(BlockType.CONTENT_BLOCK, xml_content="<p>Modified</p>"),
            Block(
                BlockType.TABLE,
                xml_content="<table rows='2' cols='2'/>",
                attributes={"rows": 2, "cols": 2},
            ),
        ]

        alignment = detector._align_blocks(pristine, current)

        # Should match by structural key
        matched_pairs = [
            (p, c) for p, c in alignment if p is not None and c is not None
        ]
        assert len(matched_pairs) == 2

    def test_addition_detection(self):
        """Detect additions in alignment."""
        detector = BlockDiffDetector()

        pristine = [
            Block(BlockType.CONTENT_BLOCK, xml_content="<p>A</p>"),
        ]

        current = [
            Block(BlockType.CONTENT_BLOCK, xml_content="<p>A</p>"),
            Block(
                BlockType.TABLE,
                xml_content="<table/>",
                attributes={"rows": 1, "cols": 1},
            ),
        ]

        alignment = detector._align_blocks(pristine, current)

        additions = [(p, c) for p, c in alignment if p is None]
        assert len(additions) == 1
        assert additions[0][1] == 1  # Table at index 1 in current

    def test_deletion_detection(self):
        """Detect deletions in alignment."""
        detector = BlockDiffDetector()

        pristine = [
            Block(BlockType.CONTENT_BLOCK, xml_content="<p>A</p>"),
            Block(
                BlockType.TABLE,
                xml_content="<table/>",
                attributes={"rows": 1, "cols": 1},
            ),
        ]

        current = [
            Block(BlockType.CONTENT_BLOCK, xml_content="<p>A</p>"),
        ]

        alignment = detector._align_blocks(pristine, current)

        deletions = [(p, c) for p, c in alignment if c is None]
        assert len(deletions) == 1
        assert deletions[0][0] == 1  # Table at index 1 in pristine


class TestFormatChanges:
    """Tests for the format_changes helper."""

    def test_format_simple_change(self):
        """Format a simple change."""
        changes = [
            BlockChange(
                change_type=ChangeType.MODIFIED,
                block_type=BlockType.CONTENT_BLOCK,
                before_xml="<p>Old</p>",
                after_xml="<p>New</p>",
                container_path=["body:"],
            )
        ]

        output = format_changes(changes)

        assert "MODIFIED" in output
        assert "content_block" in output
        assert "Old" in output
        assert "New" in output

    def test_format_nested_changes(self):
        """Format changes with child changes."""
        changes = [
            BlockChange(
                change_type=ChangeType.MODIFIED,
                block_type=BlockType.TABLE,
                before_xml="<table>...</table>",
                after_xml="<table>...</table>",
                container_path=["body:"],
                child_changes=[
                    BlockChange(
                        change_type=ChangeType.MODIFIED,
                        block_type=BlockType.TABLE_CELL,
                        block_id="0,0",
                        before_xml="<td><p>Old</p></td>",
                        after_xml="<td><p>New</p></td>",
                        container_path=["body:", "table_cell:0,0"],
                    )
                ],
            )
        ]

        output = format_changes(changes)

        assert "table" in output
        assert "table_cell" in output
        assert "child changes" in output
