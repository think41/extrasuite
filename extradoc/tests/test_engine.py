"""Integration tests for v2/engine.py.

Tests the full pipeline: pristine XML + current XML → request list.
"""

import pytest

from extradoc.engine import DiffEngine, _validate_no_embedded_newlines
from extradoc.types import NodeType


def _make_doc(body_content: str, headers: str = "", footers: str = "") -> str:
    return f'<doc id="d" revision="r"><tab id="t.0" title="Tab 1"><body class="_base">{body_content}</body>{headers}{footers}</tab></doc>'


def _req_types(requests: list) -> list[str]:
    return [next(iter(r.keys())) for r in requests]


class TestDiffEngine:
    def test_no_changes(self):
        engine = DiffEngine()
        xml = _make_doc("<p>Hello</p>")
        requests, _tree = engine.diff(xml, xml)
        assert requests == []

    def test_paragraph_added(self):
        engine = DiffEngine()
        pristine = _make_doc("<p>A</p>")
        current = _make_doc("<p>A</p><p>B</p>")
        requests, _tree = engine.diff(pristine, current)
        assert len(requests) > 0
        assert "insertText" in _req_types(requests)

    def test_paragraph_deleted(self):
        engine = DiffEngine()
        pristine = _make_doc("<p>A</p><p>B</p>")
        current = _make_doc("<p>A</p>")
        requests, _tree = engine.diff(pristine, current)
        assert "deleteContentRange" in _req_types(requests)

    def test_paragraph_modified(self):
        engine = DiffEngine()
        pristine = _make_doc("<p>Hello</p>")
        current = _make_doc("<p>World</p>")
        requests, _tree = engine.diff(pristine, current)
        rt = _req_types(requests)
        assert "deleteContentRange" in rt
        assert "insertText" in rt

    def test_heading_style_applied(self):
        engine = DiffEngine()
        pristine = _make_doc("<p>Text</p>")
        current = _make_doc("<h1>Title</h1>")
        requests, _tree = engine.diff(pristine, current)
        rt = _req_types(requests)
        assert "updateParagraphStyle" in rt
        para_style_reqs = [r for r in requests if "updateParagraphStyle" in r]
        found_heading = any(
            r["updateParagraphStyle"].get("paragraphStyle", {}).get("namedStyleType")
            == "HEADING_1"
            for r in para_style_reqs
        )
        assert found_heading

    def test_bold_text_applied(self):
        engine = DiffEngine()
        pristine = _make_doc("<p>Text</p>")
        current = _make_doc("<p><b>Bold</b></p>")
        requests, _tree = engine.diff(pristine, current)
        assert "updateTextStyle" in _req_types(requests)

    def test_table_added(self):
        engine = DiffEngine()
        pristine = _make_doc("<p>A</p>")
        current = _make_doc(
            '<p>A</p><table id="t1"><tr id="r1"><td id="0,0"><p>Cell</p></td></tr></table>'
        )
        requests, _tree = engine.diff(pristine, current)
        assert "insertTable" in _req_types(requests)

    def test_table_deleted(self):
        engine = DiffEngine()
        pristine = _make_doc(
            '<p>A</p><table id="t1"><tr id="r1"><td id="0,0"><p>Cell</p></td></tr></table>'
        )
        current = _make_doc("<p>A</p>")
        requests, _tree = engine.diff(pristine, current)
        assert "deleteContentRange" in _req_types(requests)

    def test_header_added(self):
        engine = DiffEngine()
        pristine = _make_doc("<p>A</p>")
        current = _make_doc(
            "<p>A</p>",
            headers='<header id="hdr1" class="_base"><p>Header</p></header>',
        )
        requests, _tree = engine.diff(pristine, current)
        assert "createHeader" in _req_types(requests)

    def test_header_deleted(self):
        engine = DiffEngine()
        pristine = _make_doc(
            "<p>A</p>",
            headers='<header id="hdr1" class="_base"><p>Header</p></header>',
        )
        current = _make_doc("<p>A</p>")
        requests, _tree = engine.diff(pristine, current)
        assert "deleteHeader" in _req_types(requests)

    def test_footer_added(self):
        engine = DiffEngine()
        pristine = _make_doc("<p>A</p>")
        current = _make_doc(
            "<p>A</p>",
            footers='<footer id="ftr1" class="_base"><p>Footer</p></footer>',
        )
        requests, _tree = engine.diff(pristine, current)
        assert "createFooter" in _req_types(requests)

    def test_multiple_changes_backwards_order(self):
        """Changes should be emitted in backwards order (highest index first)."""
        engine = DiffEngine()
        pristine = _make_doc("<p>A</p><p>B</p><p>C</p>")
        current = _make_doc("<p>X</p><p>B</p><p>Z</p>")
        requests, _tree = engine.diff(pristine, current)
        delete_reqs = [
            r["deleteContentRange"]["range"]["startIndex"]
            for r in requests
            if "deleteContentRange" in r
        ]
        if len(delete_reqs) >= 2:
            assert delete_reqs[0] > delete_reqs[1]

    def test_change_tree_returned(self):
        """Engine should return both requests and the change tree."""
        engine = DiffEngine()
        pristine = _make_doc("<p>A</p>")
        current = _make_doc("<p>B</p>")
        _requests, tree = engine.diff(pristine, current)
        assert tree is not None
        assert tree.node_type == NodeType.DOCUMENT

    def test_bullet_list_added(self):
        engine = DiffEngine()
        pristine = _make_doc("<p>A</p>")
        current = _make_doc('<p>A</p><li type="bullet" level="0">Item 1</li>')
        requests, _tree = engine.diff(pristine, current)
        assert "createParagraphBullets" in _req_types(requests)

    def test_styles_xml_parsed(self):
        """Passing styles_xml shouldn't crash (even if not used)."""
        engine = DiffEngine()
        pristine = _make_doc("<p>A</p>")
        current = _make_doc("<p>B</p>")
        styles = '<styles><style id="bold-style" bold="1"/></styles>'
        requests, _tree = engine.diff(pristine, current, current_styles=styles)
        assert len(requests) > 0

    def test_table_row_delete_with_cell_mod(self):
        """End-to-end: delete a row and modify a cell in a surviving row.

        This is the core bug scenario: cell mods must be emitted before
        deleteTableRow, otherwise the pristine body indices used by cell
        mods become stale after the row delete shrinks the body.
        """
        engine = DiffEngine()
        pristine = _make_doc(
            "<p>Before</p>"
            '<table id="t1">'
            '<tr id="r0"><td id="c00"><p>Header</p></td><td id="c01"><p>H2</p></td></tr>'
            '<tr id="r1"><td id="c10"><p>Delete</p></td><td id="c11"><p>Me</p></td></tr>'
            '<tr id="r2"><td id="c20"><p>Alpha</p></td><td id="c21"><p>Keep</p></td></tr>'
            "</table>"
            "<p>After</p>"
        )
        current = _make_doc(
            "<p>Before</p>"
            '<table id="t1">'
            '<tr id="r0"><td id="c00"><p>Header</p></td><td id="c01"><p>H2</p></td></tr>'
            '<tr id="r2"><td id="c20"><p>Beta</p></td><td id="c21"><p>Keep</p></td></tr>'
            "</table>"
            "<p>After</p>"
        )
        requests, _tree = engine.diff(pristine, current)
        rt = _req_types(requests)

        assert "deleteTableRow" in rt, "Should have deleteTableRow for row r1"

        # Cell mod requests (deleteContentRange/insertText for Alpha→Beta)
        # must appear BEFORE deleteTableRow
        cell_mod_types = {"deleteContentRange", "insertText"}
        delete_row_idx = rt.index("deleteTableRow")

        cell_mods_before = [
            i for i, t in enumerate(rt) if t in cell_mod_types and i < delete_row_idx
        ]
        assert (
            len(cell_mods_before) >= 2
        ), f"Expected cell mod requests before deleteTableRow, got request order: {rt}"

    def test_toc_no_spurious_diff(self):
        """Document with TOC should produce no spurious diffs when unchanged."""
        engine = DiffEngine()
        xml = _make_doc(
            "<p>Before</p>" "<toc><p>Chapter 1</p><p>Chapter 2</p></toc>" "<p>After</p>"
        )
        requests, _tree = engine.diff(xml, xml)
        assert requests == []

    def test_toc_with_content_change_after(self):
        """Content change after TOC should use correct indexes."""
        engine = DiffEngine()
        pristine = _make_doc(
            "<p>Before</p>" "<toc><p>Chapter 1</p></toc>" "<p>After</p>"
        )
        current = _make_doc(
            "<p>Before</p>" "<toc><p>Chapter 1</p></toc>" "<p>Changed</p>"
        )
        requests, _tree = engine.diff(pristine, current)
        assert len(requests) > 0
        rt = _req_types(requests)
        assert "deleteContentRange" in rt
        assert "insertText" in rt

    def test_equation_no_spurious_diff(self):
        """Document with equation should produce no spurious diffs when unchanged."""
        engine = DiffEngine()
        xml = _make_doc(
            '<p><equation length="23"/> This is an equation</p>' "<p>After equation</p>"
        )
        requests, _tree = engine.diff(xml, xml)
        assert requests == []

    def test_equation_content_change_after(self):
        """Content change after equation paragraph should use correct indexes."""
        engine = DiffEngine()
        pristine = _make_doc('<p><equation length="23"/> eq</p>' "<p>Original</p>")
        current = _make_doc('<p><equation length="23"/> eq</p>' "<p>Changed</p>")
        requests, _tree = engine.diff(pristine, current)
        assert len(requests) > 0
        rt = _req_types(requests)
        assert "deleteContentRange" in rt
        assert "insertText" in rt

    def test_richlink_no_spurious_diff(self):
        """Document with richlink should produce no spurious diffs when unchanged."""
        engine = DiffEngine()
        xml = _make_doc(
            '<p>See <richlink url="https://example.com" title="Example"/> for details.</p>'
        )
        requests, _tree = engine.diff(xml, xml)
        assert requests == []


class TestValidateNoEmbeddedNewlines:
    """Tests for _validate_no_embedded_newlines."""

    # -- Should pass (no error) --

    def test_clean_document(self):
        """Normal document with no embedded newlines passes."""
        xml = _make_doc("<p>Hello world</p><p>Second paragraph</p>")
        _validate_no_embedded_newlines(xml)

    def test_container_tags_allow_whitespace(self):
        """Container tags (doc, tab, body, table, tr, td, etc.) allow newlines
        between child elements — this is normal XML indentation."""
        xml = (
            '<doc id="d" revision="r">\n'
            '  <tab id="t.0" title="Tab 1">\n'
            "    <body>\n"
            "      <p>Hello</p>\n"
            '      <table id="t1">\n'
            '        <tr id="r1">\n'
            '          <td id="c1">\n'
            "            <p>Cell</p>\n"
            "          </td>\n"
            "        </tr>\n"
            "      </table>\n"
            "    </body>\n"
            "  </tab>\n"
            "</doc>"
        )
        _validate_no_embedded_newlines(xml)

    def test_header_footer_allow_whitespace(self):
        """Header and footer are containers — whitespace between children is fine."""
        xml = _make_doc(
            "<p>Body</p>",
            headers='<header id="h1" class="_base">\n  <p>Header text</p>\n</header>',
            footers='<footer id="f1" class="_base">\n  <p>Footer text</p>\n</footer>',
        )
        _validate_no_embedded_newlines(xml)

    def test_footnote_allows_whitespace(self):
        """Footnote is a container — whitespace between children is fine."""
        xml = _make_doc(
            '<p>Text<footnote id="fn1">\n  <p>Footnote content</p>\n</footnote></p>'
        )
        _validate_no_embedded_newlines(xml)

    def test_toc_allows_whitespace(self):
        """Table of contents is a container."""
        xml = _make_doc("<toc>\n  <p>Chapter 1</p>\n</toc>")
        _validate_no_embedded_newlines(xml)

    def test_style_wrapper_allows_whitespace(self):
        """<style> wrapper is a container."""
        xml = _make_doc(
            '<style class="warn">\n  <p>Warning 1</p>\n  <p>Warning 2</p>\n</style>'
        )
        _validate_no_embedded_newlines(xml)

    def test_empty_elements(self):
        """Empty elements are fine."""
        xml = _make_doc("<p></p><h1></h1>")
        _validate_no_embedded_newlines(xml)

    def test_malformed_xml_passes(self):
        """Malformed XML is not our problem — let the parser handle it."""
        _validate_no_embedded_newlines("<not valid xml <<<")

    # -- Should fail (ValueError) --

    def test_newline_in_paragraph(self):
        xml = _make_doc("<p>Line one\nLine two</p>")
        with pytest.raises(ValueError, match=r"<p>"):
            _validate_no_embedded_newlines(xml)

    def test_newline_in_heading(self):
        xml = _make_doc("<h1>Title\nsubtitle</h1>")
        with pytest.raises(ValueError, match=r"<h1>"):
            _validate_no_embedded_newlines(xml)

    def test_newline_in_h2(self):
        xml = _make_doc("<h2>First\nsecond</h2>")
        with pytest.raises(ValueError, match=r"<h2>"):
            _validate_no_embedded_newlines(xml)

    def test_newline_in_list_item(self):
        xml = _make_doc('<li type="bullet" level="0">Item\ncontinued</li>')
        with pytest.raises(ValueError, match=r"<li>"):
            _validate_no_embedded_newlines(xml)

    def test_newline_in_title(self):
        xml = _make_doc("<title>Doc\ntitle</title>")
        with pytest.raises(ValueError, match=r"<title>"):
            _validate_no_embedded_newlines(xml)

    def test_newline_in_subtitle(self):
        xml = _make_doc("<subtitle>Sub\ntitle</subtitle>")
        with pytest.raises(ValueError, match=r"<subtitle>"):
            _validate_no_embedded_newlines(xml)

    def test_newline_in_bold(self):
        xml = _make_doc("<p><b>Bold\ntext</b></p>")
        with pytest.raises(ValueError, match=r"<b>"):
            _validate_no_embedded_newlines(xml)

    def test_newline_in_italic(self):
        xml = _make_doc("<p><i>Italic\ntext</i></p>")
        with pytest.raises(ValueError, match=r"<i>"):
            _validate_no_embedded_newlines(xml)

    def test_newline_in_span(self):
        xml = _make_doc('<p><span class="x">Styled\ntext</span></p>')
        with pytest.raises(ValueError, match=r"<span>"):
            _validate_no_embedded_newlines(xml)

    def test_newline_in_link(self):
        xml = _make_doc('<p><a href="url">Link\ntext</a></p>')
        with pytest.raises(ValueError, match=r"<a>"):
            _validate_no_embedded_newlines(xml)

    def test_newline_in_tail_text(self):
        """Tail text after inline element but inside content parent."""
        xml = _make_doc("<p><b>bold</b>then\nnewline</p>")
        with pytest.raises(ValueError, match=r"newline"):
            _validate_no_embedded_newlines(xml)

    def test_newline_in_underline(self):
        xml = _make_doc("<p><u>Under\nline</u></p>")
        with pytest.raises(ValueError, match=r"<u>"):
            _validate_no_embedded_newlines(xml)

    def test_newline_in_strikethrough(self):
        xml = _make_doc("<p><s>Strike\nthrough</s></p>")
        with pytest.raises(ValueError, match=r"<s>"):
            _validate_no_embedded_newlines(xml)

    def test_newline_in_superscript(self):
        xml = _make_doc("<p><sup>Super\nscript</sup></p>")
        with pytest.raises(ValueError, match=r"<sup>"):
            _validate_no_embedded_newlines(xml)

    def test_newline_in_subscript(self):
        xml = _make_doc("<p><sub>Sub\nscript</sub></p>")
        with pytest.raises(ValueError, match=r"<sub>"):
            _validate_no_embedded_newlines(xml)

    # -- Integration: DiffEngine.diff rejects embedded newlines --

    def test_diff_rejects_newline_in_current(self):
        """DiffEngine.diff should reject current XML with embedded newlines."""
        engine = DiffEngine()
        pristine = _make_doc("<p>A</p>")
        current = _make_doc("<p>Line one\nLine two</p>")
        with pytest.raises(ValueError, match=r"<p>"):
            engine.diff(pristine, current)
