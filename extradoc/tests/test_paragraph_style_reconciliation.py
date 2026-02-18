"""Tests for paragraph styling reconciliation.

Verifies that:
1. Pull side: all paragraph properties are extracted into XML attributes
2. Push side: paragraph styles don't bleed to neighboring paragraphs
3. Round-trip: paragraph properties survive pull → edit → push
4. Style classes: paragraph properties from classes are applied correctly
"""

from __future__ import annotations

from typing import Any

from extradoc.engine import DiffEngine
from extradoc.generators.content import PARA_STYLE_ATTRS, ContentGenerator
from extradoc.style_converter import PARAGRAPH_STYLE_PROPS, convert_styles
from extradoc.style_factorizer import (
    PARAGRAPH_STYLE_PROPS as PARA_EXTRACTORS,
)
from extradoc.style_factorizer import (
    FactorizedStyles,
    StyleDefinition,
)
from extradoc.types import ChangeNode, ChangeOp, NodeType, SegmentContext
from extradoc.xml_converter import (
    _PARA_PROP_TO_ATTR,
    ConversionContext,
    _build_paragraph_attrs,
)


def _body_ctx(segment_end: int = 100) -> SegmentContext:
    return SegmentContext(segment_id=None, segment_end=segment_end, tab_id="t.0")


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


def _req_types(requests: list) -> list[str]:
    return [next(iter(r.keys())) for r in requests]


# --- Pull-side extraction tests ---


class TestParagraphPropertyExtractors:
    """Tests for PARAGRAPH_STYLE_PROPS extractors in style_factorizer.py."""

    def test_alignment_extraction(self):
        ps = {"alignment": "CENTER"}
        props = _extract_props(ps)
        assert props["alignment"] == "CENTER"

    def test_line_spacing_extraction(self):
        ps = {"lineSpacing": 150}
        props = _extract_props(ps)
        assert props["lineSpacing"] == "150"

    def test_space_above_extraction(self):
        ps = {"spaceAbove": {"magnitude": 12, "unit": "PT"}}
        props = _extract_props(ps)
        assert props["spaceAbove"] == "12pt"

    def test_space_below_extraction(self):
        ps = {"spaceBelow": {"magnitude": 6, "unit": "PT"}}
        props = _extract_props(ps)
        assert props["spaceBelow"] == "6pt"

    def test_indent_left_extraction(self):
        ps = {"indentStart": {"magnitude": 36, "unit": "PT"}}
        props = _extract_props(ps)
        assert props["indentLeft"] == "36pt"

    def test_indent_right_extraction(self):
        ps = {"indentEnd": {"magnitude": 18, "unit": "PT"}}
        props = _extract_props(ps)
        assert props["indentRight"] == "18pt"

    def test_indent_first_line_extraction(self):
        ps = {"indentFirstLine": {"magnitude": 36, "unit": "PT"}}
        props = _extract_props(ps)
        assert props["indentFirstLine"] == "36pt"

    def test_keep_together_extraction(self):
        ps = {"keepLinesTogether": True}
        props = _extract_props(ps)
        assert props["keepTogether"] == "1"

    def test_keep_together_false_not_extracted(self):
        ps = {"keepLinesTogether": False}
        props = _extract_props(ps)
        assert "keepTogether" not in props

    def test_keep_next_extraction(self):
        ps = {"keepWithNext": True}
        props = _extract_props(ps)
        assert props["keepNext"] == "1"

    def test_avoid_widow_extraction(self):
        ps = {"avoidWidowAndOrphan": True}
        props = _extract_props(ps)
        assert props["avoidWidow"] == "1"

    def test_direction_rtl_extraction(self):
        ps = {"direction": "RIGHT_TO_LEFT"}
        props = _extract_props(ps)
        assert props["direction"] == "RIGHT_TO_LEFT"

    def test_direction_ltr_not_extracted(self):
        """LEFT_TO_RIGHT is the default and should not be extracted."""
        ps = {"direction": "LEFT_TO_RIGHT"}
        props = _extract_props(ps)
        assert "direction" not in props

    def test_direction_none_not_extracted(self):
        ps = {}
        props = _extract_props(ps)
        assert "direction" not in props

    def test_bg_color_extraction(self):
        ps = {
            "shading": {
                "backgroundColor": {
                    "color": {"rgbColor": {"red": 1.0, "green": 1.0, "blue": 0.0}}
                }
            }
        }
        props = _extract_props(ps)
        assert props["bgColor"] == "#FFFF00"

    def test_bg_color_no_shading(self):
        ps = {}
        props = _extract_props(ps)
        assert "bgColor" not in props

    def test_border_top_extraction(self):
        ps = {
            "borderTop": {
                "width": {"magnitude": 1, "unit": "PT"},
                "color": {
                    "color": {"rgbColor": {"red": 0.0, "green": 0.0, "blue": 0.0}}
                },
                "dashStyle": "SOLID",
            }
        }
        props = _extract_props(ps)
        # Black borders don't appear because _get_color returns None for black
        # So border string is "1,#000000,SOLID"
        assert "borderTop" in props
        assert props["borderTop"].startswith("1")

    def test_border_bottom_extraction(self):
        ps = {
            "borderBottom": {
                "width": {"magnitude": 2, "unit": "PT"},
                "color": {
                    "color": {"rgbColor": {"red": 1.0, "green": 0.0, "blue": 0.0}}
                },
                "dashStyle": "DASHED",
            }
        }
        props = _extract_props(ps)
        assert "borderBottom" in props
        assert "#FF0000" in props["borderBottom"]
        assert "DASHED" in props["borderBottom"]

    def test_no_border_when_zero_width(self):
        ps = {
            "borderTop": {
                "width": {"magnitude": 0, "unit": "PT"},
            }
        }
        props = _extract_props(ps)
        assert "borderTop" not in props

    def test_multiple_properties_extracted(self):
        """All properties should be extracted from a single paragraphStyle."""
        ps = {
            "alignment": "CENTER",
            "lineSpacing": 200,
            "spaceAbove": {"magnitude": 12, "unit": "PT"},
            "keepLinesTogether": True,
            "keepWithNext": True,
            "direction": "RIGHT_TO_LEFT",
        }
        props = _extract_props(ps)
        assert props["alignment"] == "CENTER"
        assert props["lineSpacing"] == "200"
        assert props["spaceAbove"] == "12pt"
        assert props["keepTogether"] == "1"
        assert props["keepNext"] == "1"
        assert props["direction"] == "RIGHT_TO_LEFT"


def _extract_props(para_style: dict[str, Any]) -> dict[str, str]:
    """Helper to extract paragraph properties using the factorizer extractors."""
    props: dict[str, str] = {}
    for prop_name, extractor in PARA_EXTRACTORS:
        value = extractor(para_style)
        if value:
            props[prop_name] = value
    return props


# --- Pull-side XML conversion tests ---


class TestBuildParagraphAttrs:
    """Tests for _build_paragraph_attrs in xml_converter.py."""

    def _make_ctx(
        self, named_style_defaults: dict[str, dict[str, str]] | None = None
    ) -> ConversionContext:
        styles = FactorizedStyles(base_style=StyleDefinition(id="_base", properties={}))
        ctx = ConversionContext(styles=styles)
        if named_style_defaults:
            ctx.named_style_para_defaults = named_style_defaults
        return ctx

    def test_alignment_becomes_align_attr(self):
        style = {"alignment": "CENTER"}
        ctx = self._make_ctx()
        attrs = _build_paragraph_attrs(style, "NORMAL_TEXT", ctx)
        assert 'align="CENTER"' in attrs

    def test_indent_first_line_becomes_indent_first(self):
        style = {"indentFirstLine": {"magnitude": 36, "unit": "PT"}}
        ctx = self._make_ctx()
        attrs = _build_paragraph_attrs(style, "NORMAL_TEXT", ctx)
        assert 'indentFirst="36pt"' in attrs

    def test_keep_together_emitted(self):
        style = {"keepLinesTogether": True}
        ctx = self._make_ctx()
        attrs = _build_paragraph_attrs(style, "NORMAL_TEXT", ctx)
        assert 'keepTogether="1"' in attrs

    def test_keep_next_emitted(self):
        style = {"keepWithNext": True}
        ctx = self._make_ctx()
        attrs = _build_paragraph_attrs(style, "NORMAL_TEXT", ctx)
        assert 'keepNext="1"' in attrs

    def test_avoid_widow_emitted(self):
        style = {"avoidWidowAndOrphan": True}
        ctx = self._make_ctx()
        attrs = _build_paragraph_attrs(style, "NORMAL_TEXT", ctx)
        assert 'avoidWidow="1"' in attrs

    def test_direction_rtl_emitted(self):
        style = {"direction": "RIGHT_TO_LEFT"}
        ctx = self._make_ctx()
        attrs = _build_paragraph_attrs(style, "NORMAL_TEXT", ctx)
        assert 'direction="RIGHT_TO_LEFT"' in attrs

    def test_direction_ltr_not_emitted(self):
        style = {"direction": "LEFT_TO_RIGHT"}
        ctx = self._make_ctx()
        attrs = _build_paragraph_attrs(style, "NORMAL_TEXT", ctx)
        assert "direction" not in attrs

    def test_bg_color_emitted(self):
        style = {
            "shading": {
                "backgroundColor": {
                    "color": {"rgbColor": {"red": 1.0, "green": 1.0, "blue": 0.0}}
                }
            }
        }
        ctx = self._make_ctx()
        attrs = _build_paragraph_attrs(style, "NORMAL_TEXT", ctx)
        assert 'bgColor="#FFFF00"' in attrs

    def test_border_emitted(self):
        style = {
            "borderBottom": {
                "width": {"magnitude": 2, "unit": "PT"},
                "color": {
                    "color": {"rgbColor": {"red": 1.0, "green": 0.0, "blue": 0.0}}
                },
                "dashStyle": "SOLID",
            }
        }
        ctx = self._make_ctx()
        attrs = _build_paragraph_attrs(style, "NORMAL_TEXT", ctx)
        assert "borderBottom" in attrs

    def test_no_attrs_for_default_style(self):
        """No attributes emitted when style matches named style defaults."""
        style = {"alignment": "CENTER"}
        ctx = self._make_ctx(
            named_style_defaults={
                "HEADING_1": {"alignment": "CENTER"},
            }
        )
        attrs = _build_paragraph_attrs(style, "HEADING_1", ctx)
        assert attrs == ""

    def test_override_when_differs_from_default(self):
        """Attributes emitted when they differ from named style defaults."""
        style = {"alignment": "END"}
        ctx = self._make_ctx(
            named_style_defaults={
                "HEADING_1": {"alignment": "CENTER"},
            }
        )
        attrs = _build_paragraph_attrs(style, "HEADING_1", ctx)
        assert 'align="END"' in attrs

    def test_empty_style_returns_empty(self):
        ctx = self._make_ctx()
        attrs = _build_paragraph_attrs({}, "NORMAL_TEXT", ctx)
        assert attrs == ""


class TestParaPropToAttrMapping:
    """Verify _PARA_PROP_TO_ATTR covers all extractors."""

    def test_all_extractors_have_mapping(self):
        """Every extractor in PARAGRAPH_STYLE_PROPS should have a mapping."""
        extractor_names = {name for name, _ in PARA_EXTRACTORS}
        mapped_names = set(_PARA_PROP_TO_ATTR.keys())
        assert extractor_names == mapped_names, (
            f"Extractor names not in mapping: {extractor_names - mapped_names}; "
            f"Mapping names not in extractors: {mapped_names - extractor_names}"
        )


# --- Push-side reconciliation tests ---


class TestParagraphStyleReset:
    """Tests that paragraph styles are properly reset during insert to prevent bleed."""

    def test_insert_resets_paragraph_style(self):
        """Inserted paragraphs should reset paragraph styles to prevent bleed."""
        gen = ContentGenerator()
        node = _make_content_node(
            ChangeOp.ADDED,
            after_xml="<p>Hello</p>",
            pristine_start=5,
            pristine_end=5,
        )
        reqs, _ = gen.emit(node, _body_ctx())
        # Find the paragraph style reset request
        para_style_reqs = [r for r in reqs if "updateParagraphStyle" in r]
        assert len(para_style_reqs) >= 1
        fields = para_style_reqs[0]["updateParagraphStyle"]["fields"]
        # The reset should include all critical paragraph properties
        assert "namedStyleType" in fields
        assert "alignment" in fields
        assert "lineSpacing" in fields
        assert "spaceAbove" in fields
        assert "spaceBelow" in fields
        assert "indentStart" in fields
        assert "indentEnd" in fields
        assert "indentFirstLine" in fields
        assert "keepLinesTogether" in fields
        assert "keepWithNext" in fields
        assert "avoidWidowAndOrphan" in fields
        assert "direction" in fields
        assert "shading" in fields
        assert "borderTop" in fields
        assert "borderBottom" in fields
        assert "borderLeft" in fields
        assert "borderRight" in fields

    def test_heading_insert_sets_named_style(self):
        """Heading insertion should set the correct namedStyleType."""
        gen = ContentGenerator()
        node = _make_content_node(
            ChangeOp.ADDED,
            after_xml="<h2>Section Title</h2>",
            pristine_start=1,
            pristine_end=1,
        )
        reqs, _ = gen.emit(node, _body_ctx())
        para_reqs = [r for r in reqs if "updateParagraphStyle" in r]
        heading_req = next(
            r
            for r in para_reqs
            if r["updateParagraphStyle"]["paragraphStyle"].get("namedStyleType")
            == "HEADING_2"
        )
        assert heading_req is not None

    def test_insert_with_alignment_applies_override(self):
        """Inserting a paragraph with alignment should apply the override after reset."""
        gen = ContentGenerator()
        node = _make_content_node(
            ChangeOp.ADDED,
            after_xml='<p align="CENTER">Centered text</p>',
            pristine_start=1,
            pristine_end=1,
        )
        reqs, _ = gen.emit(node, _body_ctx())
        para_reqs = [r for r in reqs if "updateParagraphStyle" in r]
        # Should have at least 2: one reset + one override
        assert len(para_reqs) >= 2
        # The override should set alignment
        override_req = next(
            r
            for r in para_reqs
            if "alignment" in r["updateParagraphStyle"].get("paragraphStyle", {})
        )
        assert (
            override_req["updateParagraphStyle"]["paragraphStyle"]["alignment"]
            == "CENTER"
        )

    def test_insert_with_spacing_applies_override(self):
        """Inserting a paragraph with spacing should apply the override."""
        gen = ContentGenerator()
        node = _make_content_node(
            ChangeOp.ADDED,
            after_xml='<h1 spaceAbove="20pt" spaceBelow="10pt">Heading</h1>',
            pristine_start=1,
            pristine_end=1,
        )
        reqs, _ = gen.emit(node, _body_ctx())
        para_reqs = [r for r in reqs if "updateParagraphStyle" in r]
        override_reqs = [
            r
            for r in para_reqs
            if "spaceAbove" in r["updateParagraphStyle"].get("paragraphStyle", {})
        ]
        assert len(override_reqs) >= 1
        ps = override_reqs[0]["updateParagraphStyle"]["paragraphStyle"]
        assert ps["spaceAbove"]["magnitude"] == 20.0
        assert ps["spaceBelow"]["magnitude"] == 10.0

    def test_insert_with_keep_together_applies_override(self):
        """Inserting with keepTogether should apply the boolean property."""
        gen = ContentGenerator()
        node = _make_content_node(
            ChangeOp.ADDED,
            after_xml='<p keepTogether="1">Keep together paragraph</p>',
            pristine_start=1,
            pristine_end=1,
        )
        reqs, _ = gen.emit(node, _body_ctx())
        para_reqs = [r for r in reqs if "updateParagraphStyle" in r]
        override_reqs = [
            r
            for r in para_reqs
            if "keepLinesTogether"
            in r["updateParagraphStyle"].get("paragraphStyle", {})
        ]
        assert len(override_reqs) >= 1
        assert override_reqs[0]["updateParagraphStyle"]["paragraphStyle"][
            "keepLinesTogether"
        ]

    def test_insert_with_direction_applies_override(self):
        """Inserting with direction should apply the direction property."""
        gen = ContentGenerator()
        node = _make_content_node(
            ChangeOp.ADDED,
            after_xml='<p direction="RIGHT_TO_LEFT">RTL text</p>',
            pristine_start=1,
            pristine_end=1,
        )
        reqs, _ = gen.emit(node, _body_ctx())
        para_reqs = [r for r in reqs if "updateParagraphStyle" in r]
        override_reqs = [
            r
            for r in para_reqs
            if "direction" in r["updateParagraphStyle"].get("paragraphStyle", {})
        ]
        assert len(override_reqs) >= 1
        assert (
            override_reqs[0]["updateParagraphStyle"]["paragraphStyle"]["direction"]
            == "RIGHT_TO_LEFT"
        )

    def test_insert_with_bg_color_applies_override(self):
        """Inserting with bgColor should apply the shading property."""
        gen = ContentGenerator()
        node = _make_content_node(
            ChangeOp.ADDED,
            after_xml='<p bgColor="#FFFF00">Highlighted paragraph</p>',
            pristine_start=1,
            pristine_end=1,
        )
        reqs, _ = gen.emit(node, _body_ctx())
        para_reqs = [r for r in reqs if "updateParagraphStyle" in r]
        override_reqs = [
            r
            for r in para_reqs
            if "shading" in r["updateParagraphStyle"].get("paragraphStyle", {})
        ]
        assert len(override_reqs) >= 1

    def test_insert_with_border_applies_override(self):
        """Inserting with border should apply the border property."""
        gen = ContentGenerator()
        node = _make_content_node(
            ChangeOp.ADDED,
            after_xml='<p borderBottom="2,#FF0000,SOLID">Bordered</p>',
            pristine_start=1,
            pristine_end=1,
        )
        reqs, _ = gen.emit(node, _body_ctx())
        para_reqs = [r for r in reqs if "updateParagraphStyle" in r]
        override_reqs = [
            r
            for r in para_reqs
            if "borderBottom" in r["updateParagraphStyle"].get("paragraphStyle", {})
        ]
        assert len(override_reqs) >= 1

    def test_modify_resets_and_applies_styles(self):
        """MODIFIED content block should reset and apply paragraph styles."""
        gen = ContentGenerator()
        node = _make_content_node(
            ChangeOp.MODIFIED,
            before_xml='<p align="CENTER">Old centered</p>',
            after_xml='<p align="END">New right-aligned</p>',
            pristine_start=5,
            pristine_end=20,
        )
        reqs, _ = gen.emit(node, _body_ctx())
        # Should have delete, insert, style reset, and style override
        rt = _req_types(reqs)
        assert "deleteContentRange" in rt
        assert "insertText" in rt
        assert "updateParagraphStyle" in rt
        # Should have the alignment override
        para_reqs = [r for r in reqs if "updateParagraphStyle" in r]
        override_reqs = [
            r
            for r in para_reqs
            if "alignment" in r["updateParagraphStyle"].get("paragraphStyle", {})
        ]
        assert any(
            r["updateParagraphStyle"]["paragraphStyle"]["alignment"] == "END"
            for r in override_reqs
        )


class TestParagraphStylesFromClass:
    """Tests that paragraph properties from style classes are applied correctly."""

    def test_class_alignment_applied(self):
        """Style class with alignment should be applied as paragraph property."""
        style_defs = {"rmHiM": {"alignment": "CENTER"}}
        gen = ContentGenerator(style_defs=style_defs)
        node = _make_content_node(
            ChangeOp.ADDED,
            after_xml='<p class="rmHiM">Centered via class</p>',
            pristine_start=1,
            pristine_end=1,
        )
        reqs, _ = gen.emit(node, _body_ctx())
        para_reqs = [r for r in reqs if "updateParagraphStyle" in r]
        override_reqs = [
            r
            for r in para_reqs
            if "alignment" in r["updateParagraphStyle"].get("paragraphStyle", {})
        ]
        assert len(override_reqs) >= 1

    def test_class_indent_first_line_applied(self):
        """Style class with indentFirstLine should be mapped to indentFirst attr."""
        style_defs = {"xK9mR": {"indentFirstLine": "36pt"}}
        gen = ContentGenerator(style_defs=style_defs)
        node = _make_content_node(
            ChangeOp.ADDED,
            after_xml='<p class="xK9mR">Indented first line</p>',
            pristine_start=1,
            pristine_end=1,
        )
        reqs, _ = gen.emit(node, _body_ctx())
        para_reqs = [r for r in reqs if "updateParagraphStyle" in r]
        override_reqs = [
            r
            for r in para_reqs
            if "indentFirstLine" in r["updateParagraphStyle"].get("paragraphStyle", {})
        ]
        assert len(override_reqs) >= 1

    def test_class_mixed_text_and_para_props(self):
        """Style class with both text and paragraph props should split correctly."""
        style_defs = {
            "mixed": {
                "bold": "1",
                "color": "#FF0000",
                "alignment": "CENTER",
                "spaceAbove": "12pt",
            }
        }
        gen = ContentGenerator(style_defs=style_defs)
        node = _make_content_node(
            ChangeOp.ADDED,
            after_xml='<p class="mixed">Mixed style</p>',
            pristine_start=1,
            pristine_end=1,
        )
        reqs, _ = gen.emit(node, _body_ctx())
        # Should have paragraph style override for alignment + spaceAbove
        para_reqs = [r for r in reqs if "updateParagraphStyle" in r]
        override_reqs = [
            r
            for r in para_reqs
            if "alignment" in r["updateParagraphStyle"].get("paragraphStyle", {})
        ]
        assert len(override_reqs) >= 1
        # Should have text style for bold + color
        text_reqs = [r for r in reqs if "updateTextStyle" in r]
        bold_reqs = [
            r
            for r in text_reqs
            if r["updateTextStyle"].get("textStyle", {}).get("bold")
        ]
        assert len(bold_reqs) >= 1

    def test_direct_attrs_override_class(self):
        """Direct paragraph attributes should override class properties."""
        style_defs = {"rmHiM": {"alignment": "CENTER"}}
        gen = ContentGenerator(style_defs=style_defs)
        node = _make_content_node(
            ChangeOp.ADDED,
            after_xml='<p class="rmHiM" align="END">Right-aligned despite class</p>',
            pristine_start=1,
            pristine_end=1,
        )
        reqs, _ = gen.emit(node, _body_ctx())
        para_reqs = [r for r in reqs if "updateParagraphStyle" in r]
        # Should have END alignment (direct attr wins over class)
        override_reqs = [
            r
            for r in para_reqs
            if "alignment" in r["updateParagraphStyle"].get("paragraphStyle", {})
        ]
        assert any(
            r["updateParagraphStyle"]["paragraphStyle"]["alignment"] == "END"
            for r in override_reqs
        )


class TestMultiParagraphStyleIsolation:
    """Tests that styles from one paragraph don't bleed into the next."""

    def test_heading_followed_by_paragraph_has_separate_styles(self):
        """Heading and paragraph inserted together should have separate styles."""
        gen = ContentGenerator()
        node = _make_content_node(
            ChangeOp.ADDED,
            after_xml="<h1>Title</h1>\n<p>Body text</p>",
            pristine_start=1,
            pristine_end=1,
        )
        reqs, _ = gen.emit(node, _body_ctx())
        para_reqs = [r for r in reqs if "updateParagraphStyle" in r]
        # Should have at least 2 paragraph style requests (one per paragraph)
        named_styles = [
            r["updateParagraphStyle"]["paragraphStyle"].get("namedStyleType")
            for r in para_reqs
            if "namedStyleType" in r["updateParagraphStyle"].get("paragraphStyle", {})
        ]
        assert "HEADING_1" in named_styles
        assert "NORMAL_TEXT" in named_styles

    def test_centered_then_normal_paragraph_styles_isolated(self):
        """Centered paragraph followed by normal should have different styles."""
        gen = ContentGenerator()
        node = _make_content_node(
            ChangeOp.ADDED,
            after_xml=('<p align="CENTER">Centered</p>\n<p>Normal</p>'),
            pristine_start=1,
            pristine_end=1,
        )
        reqs, _ = gen.emit(node, _body_ctx())
        para_reqs = [r for r in reqs if "updateParagraphStyle" in r]
        # The first paragraph should have an alignment override
        # The second should only have the reset (NORMAL_TEXT)
        alignment_reqs = [
            r
            for r in para_reqs
            if "alignment" in r["updateParagraphStyle"].get("paragraphStyle", {})
        ]
        assert len(alignment_reqs) >= 1
        assert any(
            r["updateParagraphStyle"]["paragraphStyle"]["alignment"] == "CENTER"
            for r in alignment_reqs
        )


# --- Style converter push-side tests ---


class TestStyleConverterParagraphProps:
    """Tests for convert_styles with PARAGRAPH_STYLE_PROPS."""

    def test_keep_together_converts_to_bool(self):
        result, fields = convert_styles({"keepTogether": "1"}, PARAGRAPH_STYLE_PROPS)
        assert result["keepLinesTogether"] is True
        assert "keepLinesTogether" in fields

    def test_keep_next_converts_to_bool(self):
        result, fields = convert_styles({"keepNext": "1"}, PARAGRAPH_STYLE_PROPS)
        assert result["keepWithNext"] is True
        assert "keepWithNext" in fields

    def test_avoid_widow_converts_to_bool(self):
        result, fields = convert_styles({"avoidWidow": "1"}, PARAGRAPH_STYLE_PROPS)
        assert result["avoidWidowAndOrphan"] is True
        assert "avoidWidowAndOrphan" in fields

    def test_direction_rtl_converts(self):
        result, fields = convert_styles(
            {"direction": "RIGHT_TO_LEFT"}, PARAGRAPH_STYLE_PROPS
        )
        assert result["direction"] == "RIGHT_TO_LEFT"
        assert "direction" in fields

    def test_bg_color_converts(self):
        result, fields = convert_styles({"bgColor": "#FFFF00"}, PARAGRAPH_STYLE_PROPS)
        assert "shading" in result
        assert "backgroundColor" in result["shading"]
        assert "shading" in fields

    def test_border_converts(self):
        result, fields = convert_styles(
            {"borderBottom": "2,#FF0000,SOLID"}, PARAGRAPH_STYLE_PROPS
        )
        assert "borderBottom" in result
        assert result["borderBottom"]["width"]["magnitude"] == 2.0
        assert "borderBottom" in fields

    def test_alignment_converts(self):
        result, fields = convert_styles({"align": "CENTER"}, PARAGRAPH_STYLE_PROPS)
        assert result["alignment"] == "CENTER"
        assert "alignment" in fields

    def test_indent_first_converts(self):
        result, fields = convert_styles({"indentFirst": "36pt"}, PARAGRAPH_STYLE_PROPS)
        assert result["indentFirstLine"]["magnitude"] == 36.0
        assert "indentFirstLine" in fields


# --- End-to-end reconciliation tests ---


class TestEndToEndParagraphReconciliation:
    """End-to-end tests using DiffEngine to verify paragraph style round-trip."""

    def test_add_centered_paragraph(self):
        """Adding a centered paragraph should generate proper reconciliation requests."""
        pristine = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<doc id="test" revision="1">'
            '  <tab id="t.0" class="_base">'
            "    <body>"
            "      <p>Normal text</p>"
            "    </body>"
            "  </tab>"
            "</doc>"
        )
        current = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<doc id="test" revision="1">'
            '  <tab id="t.0" class="_base">'
            "    <body>"
            "      <p>Normal text</p>"
            '      <p align="CENTER">Centered text</p>'
            "    </body>"
            "  </tab>"
            "</doc>"
        )
        engine = DiffEngine()
        reqs, _ = engine.diff(pristine, current)
        assert len(reqs) > 0
        # Should have insertText for the new paragraph
        insert_reqs = [r for r in reqs if "insertText" in r]
        assert len(insert_reqs) >= 1
        # Should have updateParagraphStyle with alignment
        para_reqs = [r for r in reqs if "updateParagraphStyle" in r]
        assert len(para_reqs) >= 1
        # One of them should set alignment to CENTER
        alignment_reqs = [
            r
            for r in para_reqs
            if "alignment" in r["updateParagraphStyle"].get("paragraphStyle", {})
        ]
        assert any(
            r["updateParagraphStyle"]["paragraphStyle"]["alignment"] == "CENTER"
            for r in alignment_reqs
        )

    def test_add_paragraph_with_spacing(self):
        """Adding a paragraph with spacing overrides should generate proper requests."""
        pristine = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<doc id="test" revision="1">'
            '  <tab id="t.0" class="_base">'
            "    <body>"
            "      <p>Existing</p>"
            "    </body>"
            "  </tab>"
            "</doc>"
        )
        current = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<doc id="test" revision="1">'
            '  <tab id="t.0" class="_base">'
            "    <body>"
            "      <p>Existing</p>"
            '      <p spaceAbove="20pt" spaceBelow="10pt">Spaced paragraph</p>'
            "    </body>"
            "  </tab>"
            "</doc>"
        )
        engine = DiffEngine()
        reqs, _ = engine.diff(pristine, current)
        para_reqs = [r for r in reqs if "updateParagraphStyle" in r]
        # Should have style requests that include spaceAbove
        override_reqs = [
            r
            for r in para_reqs
            if "spaceAbove" in r["updateParagraphStyle"].get("paragraphStyle", {})
        ]
        assert len(override_reqs) >= 1

    def test_heading_to_paragraph_style_change(self):
        """Changing a heading to a paragraph should reset the named style."""
        pristine = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<doc id="test" revision="1">'
            '  <tab id="t.0" class="_base">'
            "    <body>"
            "      <h1>Old Heading</h1>"
            "    </body>"
            "  </tab>"
            "</doc>"
        )
        current = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<doc id="test" revision="1">'
            '  <tab id="t.0" class="_base">'
            "    <body>"
            "      <p>Now just text</p>"
            "    </body>"
            "  </tab>"
            "</doc>"
        )
        engine = DiffEngine()
        reqs, _ = engine.diff(pristine, current)
        para_reqs = [r for r in reqs if "updateParagraphStyle" in r]
        # Should set NORMAL_TEXT
        normal_reqs = [
            r
            for r in para_reqs
            if r["updateParagraphStyle"]["paragraphStyle"].get("namedStyleType")
            == "NORMAL_TEXT"
        ]
        assert len(normal_reqs) >= 1

    def test_add_paragraph_with_keep_together(self):
        """Adding a paragraph with keepTogether should generate proper requests."""
        pristine = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<doc id="test" revision="1">'
            '  <tab id="t.0" class="_base">'
            "    <body>"
            "      <p>Existing</p>"
            "    </body>"
            "  </tab>"
            "</doc>"
        )
        current = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<doc id="test" revision="1">'
            '  <tab id="t.0" class="_base">'
            "    <body>"
            "      <p>Existing</p>"
            '      <p keepTogether="1">Keep together</p>'
            "    </body>"
            "  </tab>"
            "</doc>"
        )
        engine = DiffEngine()
        reqs, _ = engine.diff(pristine, current)
        para_reqs = [r for r in reqs if "updateParagraphStyle" in r]
        override_reqs = [
            r
            for r in para_reqs
            if "keepLinesTogether"
            in r["updateParagraphStyle"].get("paragraphStyle", {})
        ]
        assert len(override_reqs) >= 1
        assert override_reqs[0]["updateParagraphStyle"]["paragraphStyle"][
            "keepLinesTogether"
        ]


# --- PARA_STYLE_ATTRS completeness test ---


class TestParaStyleAttrsCompleteness:
    """Ensure PARA_STYLE_ATTRS covers all properties that can appear in XML."""

    def test_all_xml_attrs_in_para_style_attrs(self):
        """All XML attribute names from _PARA_PROP_TO_ATTR values should be in PARA_STYLE_ATTRS."""
        for attr_name in _PARA_PROP_TO_ATTR.values():
            assert attr_name in PARA_STYLE_ATTRS, (
                f"XML attribute '{attr_name}' from _PARA_PROP_TO_ATTR "
                f"is not in PARA_STYLE_ATTRS"
            )

    def test_all_para_style_attrs_have_converter(self):
        """All PARA_STYLE_ATTRS should have a corresponding converter in PARAGRAPH_STYLE_PROPS."""
        converter_xml_attrs = {prop.xml_attr for prop in PARAGRAPH_STYLE_PROPS}
        for attr in PARA_STYLE_ATTRS:
            assert attr in converter_xml_attrs, (
                f"PARA_STYLE_ATTRS attribute '{attr}' has no converter "
                f"in PARAGRAPH_STYLE_PROPS"
            )
