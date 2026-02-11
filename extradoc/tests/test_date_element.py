"""Tests for date element support (pull, index, insert, diff)."""

from extradoc.block_indexer import BlockIndexer
from extradoc.engine import DiffEngine
from extradoc.generators.content import ContentGenerator
from extradoc.parser import BlockParser
from extradoc.style_factorizer import FactorizedStyles, StyleDefinition
from extradoc.types import (
    ChangeNode,
    ChangeOp,
    NodeType,
    ParagraphBlock,
    SegmentContext,
)
from extradoc.xml_converter import ConversionContext, _convert_paragraph_elements

# --- Pull (xml_converter) ---


def _make_ctx() -> ConversionContext:
    base = StyleDefinition(id="_base", properties={})
    styles = FactorizedStyles(base_style=base)
    return ConversionContext(
        styles=styles,
        lists={},
        footnotes={},
        inline_objects={},
    )


class TestDatePull:
    def test_date_with_all_properties(self):
        """Date element with all dateElementProperties emits all attributes."""
        elements = [
            {
                "dateElement": {
                    "dateElementProperties": {
                        "timestamp": "2026-02-09T12:00:00Z",
                        "dateFormat": "DATE_FORMAT_MONTH_DAY_YEAR_ABBREVIATED",
                        "locale": "en-GB",
                        "timeFormat": "TIME_FORMAT_DISABLED",
                        "timeZoneId": "etc/UTC",
                    }
                }
            }
        ]
        result = _convert_paragraph_elements(elements, _make_ctx())
        assert 'timestamp="2026-02-09T12:00:00Z"' in result
        assert 'dateFormat="DATE_FORMAT_MONTH_DAY_YEAR_ABBREVIATED"' in result
        assert 'locale="en-GB"' in result
        assert 'timeFormat="TIME_FORMAT_DISABLED"' in result
        assert 'timeZoneId="etc/UTC"' in result
        assert result.startswith("<date ")
        assert result.endswith("/>")

    def test_date_with_only_timestamp(self):
        """Date with only timestamp emits just that attribute."""
        elements = [
            {
                "dateElement": {
                    "dateElementProperties": {
                        "timestamp": "2026-01-01T00:00:00Z",
                    }
                }
            }
        ]
        result = _convert_paragraph_elements(elements, _make_ctx())
        assert 'timestamp="2026-01-01T00:00:00Z"' in result
        assert "dateFormat" not in result
        assert "locale" not in result

    def test_date_with_no_properties(self):
        """Date with empty or missing dateElementProperties emits bare <date/>."""
        elements = [{"dateElement": {}}]
        result = _convert_paragraph_elements(elements, _make_ctx())
        assert result == "<date/>"

    def test_date_skips_unspecified_format(self):
        """DATE_FORMAT_UNSPECIFIED and TIME_FORMAT_UNSPECIFIED are omitted."""
        elements = [
            {
                "dateElement": {
                    "dateElementProperties": {
                        "timestamp": "2026-06-15T00:00:00Z",
                        "dateFormat": "DATE_FORMAT_UNSPECIFIED",
                        "timeFormat": "TIME_FORMAT_UNSPECIFIED",
                    }
                }
            }
        ]
        result = _convert_paragraph_elements(elements, _make_ctx())
        assert 'timestamp="2026-06-15T00:00:00Z"' in result
        assert "DATE_FORMAT_UNSPECIFIED" not in result
        assert "TIME_FORMAT_UNSPECIFIED" not in result


# --- Block Indexer ---


def _parse_and_index(body_content: str) -> list:
    xml = f'<doc id="d" revision="r"><tab id="t.0" title="Tab 1"><body class="_base">{body_content}</body></tab></doc>'
    parser = BlockParser()
    doc = parser.parse(xml)
    indexer = BlockIndexer()
    indexer.compute(doc)
    return doc.tabs[0].segments[0].children


class TestDateBlockIndex:
    def test_date_counts_as_one_index(self):
        """<date/> in a paragraph adds 1 to the index count."""
        children = _parse_and_index(
            '<p>Due: <date timestamp="2026-01-01T00:00:00Z"/></p>'
        )
        assert len(children) == 1
        p = children[0]
        assert isinstance(p, ParagraphBlock)
        # "Due: " = 5 chars + 1 (date) + 1 (newline) = 7
        assert p.start_index == 1
        assert p.end_index == 8  # 1 + 5 + 1 + 1 = 8


# --- Content Generator (insertDate) ---


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
    return SegmentContext(segment_id=None, segment_end=segment_end, tab_id="t.0")


def _req_types(requests: list) -> list[str]:
    return [next(iter(r.keys())) for r in requests]


class TestDateInsert:
    def test_insert_date_element(self):
        """Adding a paragraph with a <date/> should generate insertDate request."""
        gen = ContentGenerator()
        node = _make_content_node(
            ChangeOp.ADDED,
            after_xml='<p>Due: <date timestamp="2026-02-09T12:00:00Z" dateFormat="DATE_FORMAT_MONTH_DAY_YEAR_ABBREVIATED"/></p>',
            pristine_start=1,
            pristine_end=1,
        )
        reqs, _consumed = gen.emit(node, _body_ctx())
        types = _req_types(reqs)
        assert "insertDate" in types

        date_req = next(r for r in reqs if "insertDate" in r)
        insert_date = date_req["insertDate"]
        assert (
            insert_date["dateElementProperties"]["timestamp"] == "2026-02-09T12:00:00Z"
        )
        assert (
            insert_date["dateElementProperties"]["dateFormat"]
            == "DATE_FORMAT_MONTH_DAY_YEAR_ABBREVIATED"
        )
        assert insert_date["location"]["tabId"] == "t.0"

    def test_insert_date_with_all_properties(self):
        """insertDate includes all provided date properties."""
        gen = ContentGenerator()
        node = _make_content_node(
            ChangeOp.ADDED,
            after_xml='<p><date timestamp="2026-06-15T10:30:00Z" dateFormat="DATE_FORMAT_MONTH_DAY_YEAR_ABBREVIATED" locale="en-GB" timeFormat="TIME_FORMAT_HOUR_MINUTE" timeZoneId="America/New_York"/></p>',
            pristine_start=1,
            pristine_end=1,
        )
        reqs, _consumed = gen.emit(node, _body_ctx())
        date_req = next(r for r in reqs if "insertDate" in r)
        props = date_req["insertDate"]["dateElementProperties"]
        assert props["timestamp"] == "2026-06-15T10:30:00Z"
        assert props["locale"] == "en-GB"
        assert props["timeFormat"] == "TIME_FORMAT_HOUR_MINUTE"
        assert props["timeZoneId"] == "America/New_York"

    def test_insert_date_bare(self):
        """A bare <date/> with no attributes generates insertDate with empty properties."""
        gen = ContentGenerator()
        node = _make_content_node(
            ChangeOp.ADDED,
            after_xml="<p>Today: <date/></p>",
            pristine_start=1,
            pristine_end=1,
        )
        reqs, _consumed = gen.emit(node, _body_ctx())
        types = _req_types(reqs)
        assert "insertDate" in types
        date_req = next(r for r in reqs if "insertDate" in r)
        assert date_req["insertDate"]["dateElementProperties"] == {}


# --- Engine Integration ---


def _make_doc(body_content: str) -> str:
    return f'<doc id="d" revision="r"><tab id="t.0" title="Tab 1"><body class="_base">{body_content}</body></tab></doc>'


class TestDateDiffEngine:
    def test_no_change_with_date(self):
        """Identical date elements produce no diff."""
        engine = DiffEngine()
        xml = _make_doc(
            '<p>Due: <date timestamp="2026-02-09T12:00:00Z" dateFormat="DATE_FORMAT_MONTH_DAY_YEAR_ABBREVIATED"/></p>'
        )
        requests, _tree = engine.diff(xml, xml)
        assert requests == []

    def test_add_date_element(self):
        """Adding a date generates insertDate request."""
        engine = DiffEngine()
        pristine = _make_doc("<p>Hello</p>")
        current = _make_doc(
            '<p>Hello</p><p>Due: <date timestamp="2026-02-09T12:00:00Z"/></p>'
        )
        requests, _tree = engine.diff(pristine, current)
        types = _req_types(requests)
        assert "insertText" in types
        assert "insertDate" in types

    def test_delete_date_element(self):
        """Deleting a paragraph with date generates deleteContentRange."""
        engine = DiffEngine()
        pristine = _make_doc(
            '<p>Hello</p><p>Due: <date timestamp="2026-02-09T12:00:00Z"/></p>'
        )
        current = _make_doc("<p>Hello</p>")
        requests, _tree = engine.diff(pristine, current)
        types = _req_types(requests)
        assert "deleteContentRange" in types
