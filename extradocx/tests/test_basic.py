"""
Basic tests for the extradocx DOCX → GFM AST converter.

Tests are organized around the public API: DocxParser, to_json, to_markdown.
"""

from __future__ import annotations

import json
import pathlib
import re
import zipfile
import xml.etree.ElementTree as ET

import pytest

from extradocx import DocxParser, to_json, to_markdown
from extradocx.ast_nodes import (
    BulletList,
    Document,
    Heading,
    OrderedList,
    Paragraph,
    Table,
    TextRun,
)

TESTDATA = pathlib.Path(__file__).parent.parent / "testdata"
REPORT_DOCX = TESTDATA / "test_report.docx"

NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def find_by_xpath(xpath_str: str, root: ET.Element) -> ET.Element | None:
    """Resolve a /w:document[1]/... XPath from the document root element."""
    parts = xpath_str.lstrip("/").split("/")
    current = root
    for part in parts[1:]:  # root IS w:document, skip first segment
        m = re.match(r"(\w+):(\w+)\[(\d+)\]", part)
        if not m:
            return None
        prefix, local, idx = m.group(1), m.group(2), int(m.group(3))
        uri = NS.get(prefix, "")
        tag = f"{{{uri}}}{local}"
        children = [c for c in current if c.tag == tag]
        if idx > len(children):
            return None
        current = children[idx - 1]
    return current


@pytest.fixture(scope="module")
def parsed_doc() -> Document:
    return DocxParser(REPORT_DOCX).parse()


@pytest.fixture(scope="module")
def docx_root() -> ET.Element:
    with zipfile.ZipFile(REPORT_DOCX) as zf:
        return ET.fromstring(zf.read("word/document.xml"))


@pytest.fixture(scope="module")
def markdown_output(parsed_doc: Document) -> str:
    return to_markdown(parsed_doc)


@pytest.fixture(scope="module")
def json_output(parsed_doc: Document) -> dict:
    return json.loads(to_json(parsed_doc))


# ---------------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------------


class TestParser:
    def test_returns_document(self, parsed_doc):
        assert isinstance(parsed_doc, Document)

    def test_has_children(self, parsed_doc):
        assert len(parsed_doc.children) > 0

    def test_detects_headings(self, parsed_doc):
        headings = [c for c in parsed_doc.children if isinstance(c, Heading)]
        assert len(headings) >= 10, "Should have at least 10 headings"

    def test_heading_levels(self, parsed_doc):
        headings = [c for c in parsed_doc.children if isinstance(c, Heading)]
        levels = {h.level for h in headings}
        assert 1 in levels
        assert 2 in levels

    def test_title_as_h1(self, parsed_doc):
        first = parsed_doc.children[0]
        assert isinstance(first, Heading)
        assert first.level == 1
        text = "".join(r.text for r in first.children if isinstance(r, TextRun))
        assert "Software Engineering" in text

    def test_detects_bullet_lists(self, parsed_doc):
        lists = [c for c in parsed_doc.children if isinstance(c, BulletList)]
        assert len(lists) >= 3

    def test_detects_ordered_lists(self, parsed_doc):
        lists = [c for c in parsed_doc.children if isinstance(c, OrderedList)]
        assert len(lists) >= 3

    def test_detects_tables(self, parsed_doc):
        tables = [c for c in parsed_doc.children if isinstance(c, Table)]
        assert len(tables) >= 5

    def test_paragraphs_have_text_runs(self, parsed_doc):
        """Most body paragraphs should contain at least one TextRun.
        (A small number may contain only structural breaks — those are skipped.)"""
        paras = [c for c in parsed_doc.children if isinstance(c, Paragraph)]
        paras_with_runs = [
            p for p in paras if any(isinstance(r, TextRun) for r in p.children)
        ]
        assert len(paras_with_runs) >= 10, "Expected at least 10 paragraphs with text runs"

    def test_bold_runs(self, parsed_doc):
        """Verify that some runs have bold=True (from the DOCX content)."""
        all_runs: list[TextRun] = []
        for node in parsed_doc.children:
            if isinstance(node, Paragraph):
                all_runs.extend(r for r in node.children if isinstance(r, TextRun))
            elif isinstance(node, Heading):
                all_runs.extend(r for r in node.children if isinstance(r, TextRun))
        bold_runs = [r for r in all_runs if r.bold]
        assert len(bold_runs) >= 1, "Expected at least one bold text run"


# ---------------------------------------------------------------------------
# XPath traceability tests
# ---------------------------------------------------------------------------


class TestXPathPointers:
    def test_body_xpath(self, parsed_doc):
        assert parsed_doc.xpath == "/w:document[1]/w:body[1]"

    def test_paragraph_xpaths_are_unique(self, parsed_doc):
        paras = [c for c in parsed_doc.children if isinstance(c, Paragraph)]
        xpaths = [p.xpath for p in paras]
        assert len(xpaths) == len(set(xpaths)), "Paragraph XPaths must be unique"

    def test_heading_xpaths_are_unique(self, parsed_doc):
        headings = [c for c in parsed_doc.children if isinstance(c, Heading)]
        xpaths = [h.xpath for h in headings]
        assert len(xpaths) == len(set(xpaths))

    def test_text_run_xpath_resolves_to_correct_text(self, parsed_doc, docx_root):
        """XPaths in TextRun nodes must point to elements with matching text."""
        # Check title
        first = parsed_doc.children[0]
        assert isinstance(first, Heading)
        for run in first.children:
            if isinstance(run, TextRun):
                el = find_by_xpath(run.xpath, docx_root)
                assert el is not None, f"XPath not found: {run.xpath}"
                assert el.text == run.text, f"Text mismatch at {run.xpath}"

    def test_table_cell_xpath_resolves(self, parsed_doc, docx_root):
        """Table cell XPaths must resolve to w:tc elements."""
        tables = [c for c in parsed_doc.children if isinstance(c, Table)]
        assert tables
        tbl = tables[0]
        for row in tbl.rows:
            for cell in row.cells:
                el = find_by_xpath(cell.xpath, docx_root)
                assert el is not None, f"Cell XPath not found: {cell.xpath}"
                # The element should be w:tc
                assert el.tag.endswith("}tc"), f"Expected w:tc at {cell.xpath}"

    def test_list_item_xpath_resolves(self, parsed_doc, docx_root):
        """List item XPaths must resolve to paragraph elements."""
        blists = [c for c in parsed_doc.children if isinstance(c, BulletList)]
        assert blists
        for item in blists[0].items[:3]:
            el = find_by_xpath(item.xpath, docx_root)
            assert el is not None, f"List item XPath not found: {item.xpath}"
            assert el.tag.endswith("}p"), f"Expected w:p at {item.xpath}"


# ---------------------------------------------------------------------------
# Markdown serializer tests
# ---------------------------------------------------------------------------


class TestMarkdownSerializer:
    def test_produces_non_empty_string(self, markdown_output):
        assert len(markdown_output) > 1000

    def test_headings_use_atx_syntax(self, markdown_output):
        assert "# Chapter 1" in markdown_output
        assert "## 1.1" in markdown_output

    def test_bullet_list_items(self, markdown_output):
        assert "- 1960s:" in markdown_output

    def test_ordered_list_items(self, markdown_output):
        assert re.search(r"^\d+\. ", markdown_output, re.MULTILINE)

    def test_table_pipe_syntax(self, markdown_output):
        assert "|" in markdown_output
        # Check for separator row
        assert re.search(r"\| -+", markdown_output)

    def test_italic_runs(self, markdown_output):
        # The subtitle is italic
        assert "*A Practical Guide" in markdown_output

    def test_ends_with_newline(self, markdown_output):
        assert markdown_output.endswith("\n")


# ---------------------------------------------------------------------------
# JSON serializer tests
# ---------------------------------------------------------------------------


class TestJsonSerializer:
    def test_root_type(self, json_output):
        assert json_output["type"] == "document"

    def test_root_has_xpath(self, json_output):
        assert json_output["xpath"] == "/w:document[1]/w:body[1]"

    def test_nodes_have_type_and_xpath(self, json_output):
        for child in json_output["children"]:
            assert "type" in child, f"Missing type: {child}"
            assert "xpath" in child, f"Missing xpath: {child}"

    def test_text_runs_have_text_field(self, json_output):
        def walk(node):
            if node.get("type") == "text_run":
                assert "text" in node
                assert "xpath" in node
            for child in node.get("children", []):
                walk(child)
            for item in node.get("items", []):
                walk(item)
            for row in node.get("rows", []):
                walk(row)
            for cell in row.get("cells", []) if isinstance(node.get("rows"), list) else []:
                walk(cell)

        for child in json_output["children"]:
            walk(child)

    def test_heading_has_level(self, json_output):
        headings = [c for c in json_output["children"] if c["type"] == "heading"]
        assert headings
        for h in headings:
            assert "level" in h
            assert 1 <= h["level"] <= 6

    def test_table_structure(self, json_output):
        tables = [c for c in json_output["children"] if c["type"] == "table"]
        assert tables
        tbl = tables[0]
        assert "rows" in tbl
        assert tbl["rows"]
        for row in tbl["rows"]:
            assert "cells" in row
            for cell in row["cells"]:
                assert "children" in cell
