"""Integration tests for v2/engine.py.

Tests the full pipeline: pristine XML + current XML → request list.
"""

from extradoc.v2.engine import DiffEngine
from extradoc.v2.types import NodeType


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
