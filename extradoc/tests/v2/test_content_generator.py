"""Tests for v2/generators/content.py."""

from extradoc.v2.generators.content import ContentGenerator, _bullet_type_to_preset
from extradoc.v2.types import ChangeNode, ChangeOp, NodeType, SegmentContext


def _make_content_node(
    op: ChangeOp,
    before_xml: str | None = None,
    after_xml: str | None = None,
    pristine_start: int = 1,
    pristine_end: int = 10,
) -> ChangeNode:
    return ChangeNode(
        node_type=NodeType.CONTENT_BLOCK,
        op=op,
        before_xml=before_xml,
        after_xml=after_xml,
        pristine_start=pristine_start,
        pristine_end=pristine_end,
    )


def _body_ctx(segment_end: int = 100) -> SegmentContext:
    return SegmentContext(segment_id=None, segment_end=segment_end)


def _req_types(requests: list) -> list[str]:
    return [next(iter(r.keys())) for r in requests]


class TestContentGeneratorDelete:
    def test_basic_delete(self):
        gen = ContentGenerator()
        node = _make_content_node(
            ChangeOp.DELETED,
            before_xml="<p>Hello</p>",
            pristine_start=5,
            pristine_end=12,
        )
        reqs, consumed = gen.emit(node, _body_ctx())
        assert not consumed
        assert len(reqs) == 1
        assert "deleteContentRange" in reqs[0]
        rng = reqs[0]["deleteContentRange"]["range"]
        assert rng["startIndex"] == 5
        assert rng["endIndex"] == 12

    def test_delete_at_segment_end(self):
        """Delete at segment end should not delete the final newline."""
        gen = ContentGenerator()
        node = _make_content_node(
            ChangeOp.DELETED,
            before_xml="<p>Hello</p>",
            pristine_start=5,
            pristine_end=20,
        )
        ctx = _body_ctx(segment_end=20)
        reqs, _consumed = gen.emit(node, ctx)
        assert len(reqs) == 1
        rng = reqs[0]["deleteContentRange"]["range"]
        # Should not delete past segment_end - 1
        assert rng["endIndex"] == 19

    def test_delete_empty_range(self):
        gen = ContentGenerator()
        node = _make_content_node(
            ChangeOp.DELETED,
            before_xml="<p>X</p>",
            pristine_start=5,
            pristine_end=5,
        )
        reqs, _consumed = gen.emit(node, _body_ctx())
        assert reqs == []

    def test_delete_with_segment_id(self):
        gen = ContentGenerator()
        node = _make_content_node(
            ChangeOp.DELETED,
            before_xml="<p>Hi</p>",
            pristine_start=0,
            pristine_end=3,
        )
        ctx = SegmentContext(segment_id="kix.hdr1", segment_end=10)
        reqs, _consumed = gen.emit(node, ctx)
        assert len(reqs) == 1
        rng = reqs[0]["deleteContentRange"]["range"]
        assert rng["segmentId"] == "kix.hdr1"


class TestContentGeneratorAdd:
    def test_basic_insert(self):
        gen = ContentGenerator()
        node = _make_content_node(
            ChangeOp.ADDED,
            after_xml="<p>Hello</p>",
            pristine_start=5,
            pristine_end=5,
        )
        reqs, consumed = gen.emit(node, _body_ctx())
        assert not consumed
        assert len(reqs) > 0
        # First request should be insertText
        assert "insertText" in reqs[0]
        text = reqs[0]["insertText"]["text"]
        assert "Hello" in text

    def test_insert_with_heading(self):
        gen = ContentGenerator()
        node = _make_content_node(
            ChangeOp.ADDED,
            after_xml="<h1>Title</h1>",
            pristine_start=1,
            pristine_end=1,
        )
        reqs, _consumed = gen.emit(node, _body_ctx())
        rt = _req_types(reqs)
        assert "insertText" in rt
        assert "updateParagraphStyle" in rt
        # Find the heading style
        para_style_reqs = [r for r in reqs if "updateParagraphStyle" in r]
        found_heading = any(
            r["updateParagraphStyle"].get("paragraphStyle", {}).get("namedStyleType")
            == "HEADING_1"
            for r in para_style_reqs
        )
        assert found_heading

    def test_insert_with_bullet(self):
        gen = ContentGenerator()
        node = _make_content_node(
            ChangeOp.ADDED,
            after_xml='<li type="bullet" level="0">Item</li>',
            pristine_start=1,
            pristine_end=1,
        )
        reqs, _consumed = gen.emit(node, _body_ctx())
        assert "createParagraphBullets" in _req_types(reqs)

    def test_insert_with_bold(self):
        gen = ContentGenerator()
        node = _make_content_node(
            ChangeOp.ADDED,
            after_xml="<p><b>Bold text</b></p>",
            pristine_start=1,
            pristine_end=1,
        )
        reqs, _consumed = gen.emit(node, _body_ctx())
        assert "updateTextStyle" in _req_types(reqs)

    def test_insert_at_segment_end(self):
        """Insert at segment end should strip trailing newline."""
        gen = ContentGenerator()
        node = _make_content_node(
            ChangeOp.ADDED,
            after_xml="<p>New</p>",
            pristine_start=99,
            pristine_end=99,
        )
        ctx = _body_ctx(segment_end=100)
        _reqs, consumed = gen.emit(node, ctx)
        assert consumed  # segment_end_consumed should be True


class TestContentGeneratorModify:
    def test_modify_produces_delete_then_insert(self):
        """MODIFIED falls back to delete + insert."""
        gen = ContentGenerator()
        node = _make_content_node(
            ChangeOp.MODIFIED,
            before_xml="<p>Old</p>",
            after_xml="<p>New</p>",
            pristine_start=5,
            pristine_end=10,
        )
        reqs, _consumed = gen.emit(node, _body_ctx())
        rt = _req_types(reqs)
        # Should have delete first, then insert
        assert "deleteContentRange" in rt
        assert "insertText" in rt


class TestBulletTypeToPreset:
    def test_known_types(self):
        assert _bullet_type_to_preset("bullet") == "BULLET_DISC_CIRCLE_SQUARE"
        assert _bullet_type_to_preset("decimal") == "NUMBERED_DECIMAL_NESTED"
        assert _bullet_type_to_preset("alpha") == "NUMBERED_UPPERALPHA_ALPHA_ROMAN"
        assert (
            _bullet_type_to_preset("roman") == "NUMBERED_UPPERROMAN_UPPERALPHA_DECIMAL"
        )
        assert _bullet_type_to_preset("checkbox") == "BULLET_CHECKBOX"

    def test_unknown_type_defaults_to_disc(self):
        assert _bullet_type_to_preset("unknown") == "BULLET_DISC_CIRCLE_SQUARE"
