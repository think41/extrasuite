"""Tests for the reconcile module.

Phase 1: paragraph text in body.
Phase 2: tables (body only).
Phase 3: multi-segment (headers, footers, footnotes).
Phase 4: multi-tab.
Phase 7: edge cases + coverage.
"""

from typing import Any

import pytest

from extradoc.api_types import DeferredID
from extradoc.api_types._generated import (
    Document,
    List,
    Paragraph,
)
from extradoc.mock.api import MockGoogleDocsAPI
from extradoc.reconcile import ReconcileError, reconcile, reindex_document, verify
from extradoc.reconcile._comparators import documents_match
from extradoc.reconcile._core import resolve_deferred_ids
from extradoc.reconcile._generators import (
    _generate_text_style_updates,
    _infer_bullet_preset,
)


def _make_doc(*paragraphs: str, tab_id: str = "t.0") -> Document:
    """Helper: create a Document with paragraphs in a single tab body.

    Each string becomes a paragraph. A trailing \\n is added if not present.
    A section break is prepended automatically.
    """
    content: list[dict] = [{"sectionBreak": {}}]
    for text in paragraphs:
        if not text.endswith("\n"):
            text = text + "\n"
        content.append({"paragraph": {"elements": [{"textRun": {"content": text}}]}})

    doc = Document.model_validate(
        {
            "documentId": "test",
            "tabs": [
                {
                    "tabProperties": {"tabId": tab_id},
                    "documentTab": {"body": {"content": content}},
                }
            ],
        }
    )
    return reindex_document(doc)


class TestReindexDocument:
    def test_basic_reindex(self):
        doc = _make_doc("Hello")
        tab = doc.tabs[0]
        body = tab.document_tab.body
        assert body.content is not None
        # Section break at index 0
        sb = body.content[0]
        assert sb.section_break is not None
        # Section break startIndex is None (first element has no startIndex)
        assert sb.start_index is None
        assert sb.end_index == 1
        # Paragraph "Hello\n" at index 1-7
        para = body.content[1]
        assert para.paragraph is not None
        assert para.start_index == 1
        assert para.end_index == 7  # "Hello\n" = 6 chars

    def test_multiple_paragraphs(self):
        doc = _make_doc("Hello", "World")
        body = doc.tabs[0].document_tab.body
        assert len(body.content) == 3  # sectionBreak + 2 paragraphs
        p1 = body.content[1]
        p2 = body.content[2]
        assert p1.end_index == p2.start_index


class TestReconcileNoChange:
    def test_identical_documents(self):
        base = _make_doc("Hello", "World")
        desired = _make_doc("Hello", "World")
        result = reconcile(base, desired)
        # No changes needed
        assert len(result) == 0 or (
            len(result) == 1
            and (result[0].requests is None or len(result[0].requests) == 0)
        )
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"


class TestReconcileAddParagraph:
    def test_add_paragraph_at_end(self):
        base = _make_doc("Hello")
        desired = _make_doc("Hello", "World")
        result = reconcile(base, desired)
        assert len(result) == 1 and result[0].requests is not None
        assert len(result[0].requests) > 0
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_add_paragraph_at_beginning(self):
        base = _make_doc("World")
        desired = _make_doc("Hello", "World")
        result = reconcile(base, desired)
        assert len(result) == 1 and result[0].requests is not None
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_add_multiple_paragraphs(self):
        base = _make_doc("Hello")
        desired = _make_doc("Hello", "Beautiful", "World")
        result = reconcile(base, desired)
        assert len(result) == 1 and result[0].requests is not None
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"


class TestReconcileDeleteParagraph:
    def test_delete_paragraph_at_end(self):
        base = _make_doc("Hello", "World")
        desired = _make_doc("Hello")
        result = reconcile(base, desired)
        assert len(result) == 1 and result[0].requests is not None
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_delete_paragraph_at_beginning(self):
        base = _make_doc("Hello", "World")
        desired = _make_doc("World")
        result = reconcile(base, desired)
        assert len(result) == 1 and result[0].requests is not None
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_delete_middle_paragraph(self):
        base = _make_doc("Hello", "Beautiful", "World")
        desired = _make_doc("Hello", "World")
        result = reconcile(base, desired)
        assert len(result) == 1 and result[0].requests is not None
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"


class TestReconcileModifyParagraph:
    def test_replace_all_content(self):
        base = _make_doc("Hello")
        desired = _make_doc("Goodbye")
        result = reconcile(base, desired)
        assert len(result) == 1 and result[0].requests is not None
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"


class TestReconcileReorderParagraphs:
    def test_swap_two_paragraphs(self):
        base = _make_doc("Hello", "World")
        desired = _make_doc("World", "Hello")
        result = reconcile(base, desired)
        assert len(result) == 1 and result[0].requests is not None
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_reverse_three_paragraphs(self):
        base = _make_doc("A", "B", "C")
        desired = _make_doc("C", "B", "A")
        result = reconcile(base, desired)
        assert len(result) == 1 and result[0].requests is not None
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"


class TestReconcileEdgeCases:
    def test_empty_paragraph_to_content(self):
        """Replace empty paragraph with content."""
        base = _make_doc("")
        desired = _make_doc("Hello")
        result = reconcile(base, desired)
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_content_to_empty_paragraph(self):
        """Replace content with empty paragraph."""
        base = _make_doc("Hello")
        desired = _make_doc("")
        result = reconcile(base, desired)
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_delete_all_but_one(self):
        """Delete all paragraphs except the last one."""
        base = _make_doc("A", "B", "C", "D")
        desired = _make_doc("D")
        result = reconcile(base, desired)
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_add_many_paragraphs(self):
        """Add several paragraphs at once."""
        base = _make_doc("Start")
        desired = _make_doc("Start", "Line 1", "Line 2", "Line 3", "End")
        result = reconcile(base, desired)
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_replace_multiple_with_one(self):
        """Replace multiple paragraphs with a single one."""
        base = _make_doc("A", "B", "C", "D")
        desired = _make_doc("X")
        result = reconcile(base, desired)
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_replace_one_with_multiple(self):
        """Replace a single paragraph with multiple."""
        base = _make_doc("X")
        desired = _make_doc("A", "B", "C", "D")
        result = reconcile(base, desired)
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_complex_interleaved_changes(self):
        """Mix of adds, deletes, and unchanged paragraphs."""
        base = _make_doc("A", "B", "C", "D", "E")
        desired = _make_doc("A", "X", "C", "Y", "Z")
        result = reconcile(base, desired)
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_unicode_content(self):
        """Test with unicode/emoji content (UTF-16 correctness)."""
        base = _make_doc("Hello")
        desired = _make_doc("Hello", "World \U0001f600")
        result = reconcile(base, desired)
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_long_paragraphs(self):
        """Test with longer paragraph text."""
        base = _make_doc(
            "This is a long paragraph with many words in it.",
            "Another paragraph here.",
        )
        desired = _make_doc(
            "This is a long paragraph with many words in it.",
            "A brand new middle paragraph.",
            "Another paragraph here.",
        )
        result = reconcile(base, desired)
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_delete_first_keep_rest(self):
        """Delete only the first paragraph."""
        base = _make_doc("A", "B", "C")
        desired = _make_doc("B", "C")
        result = reconcile(base, desired)
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_delete_last_keep_rest(self):
        """Delete only the last paragraph."""
        base = _make_doc("A", "B", "C")
        desired = _make_doc("A", "B")
        result = reconcile(base, desired)
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"


# ---------------------------------------------------------------------------
# Phase 2: Tables
# ---------------------------------------------------------------------------


def _make_table(rows_data: list[list[str]]) -> dict[str, Any]:
    """Create a table dict from cell text data.

    rows_data is a list of rows, each row is a list of cell texts.
    e.g., [["A", "B"], ["C", "D"]] creates a 2x2 table.

    Cells include a dummy ``startIndex`` so that ``reindex_document()``
    uses the Full Structure path — the same path the mock's
    ``insertTable`` uses.  This ensures index arithmetic matches.
    """
    table_rows: list[dict[str, Any]] = []
    for row_data in rows_data:
        cells: list[dict[str, Any]] = []
        for text in row_data:
            if not text.endswith("\n"):
                text = text + "\n"
            cells.append(
                {
                    "startIndex": 0,  # triggers Full Structure reindex
                    "content": [
                        {"paragraph": {"elements": [{"textRun": {"content": text}}]}}
                    ],
                }
            )
        table_rows.append({"tableCells": cells})

    return {
        "table": {
            "rows": len(rows_data),
            "columns": len(rows_data[0]) if rows_data else 0,
            "tableRows": table_rows,
        }
    }


def _make_doc_with_content(
    *elements: str | dict[str, Any], tab_id: str = "t.0"
) -> Document:
    """Create a Document from a mix of paragraph strings and table dicts.

    Strings become paragraphs, dicts are used as-is (e.g., from _make_table).
    A section break is prepended automatically.
    """
    content: list[dict[str, Any]] = [{"sectionBreak": {}}]
    for elem in elements:
        if isinstance(elem, str):
            text = elem if elem.endswith("\n") else elem + "\n"
            content.append(
                {"paragraph": {"elements": [{"textRun": {"content": text}}]}}
            )
        elif isinstance(elem, dict):
            content.append(elem)
            # insertTable always creates a trailing empty paragraph by
            # splitting the paragraph at the insertion point.  Our desired
            # state must include it so the comparison matches.
            if "table" in elem:
                content.append(
                    {"paragraph": {"elements": [{"textRun": {"content": "\n"}}]}}
                )

    doc = Document.model_validate(
        {
            "documentId": "test",
            "tabs": [
                {
                    "tabProperties": {"tabId": tab_id},
                    "documentTab": {"body": {"content": content}},
                }
            ],
        }
    )
    return reindex_document(doc)


def _make_styled_para(
    text: str,
    bold: bool | None = None,
    italic: bool | None = None,
    underline: bool | None = None,
    font_size_pt: float | None = None,
    foreground_color_rgb: tuple[float, float, float] | None = None,
    named_style_type: str | None = None,
    alignment: str | None = None,
    line_spacing: float | None = None,
) -> dict[str, Any]:
    """Create a paragraph dict with text and inline styles."""
    if not text.endswith("\n"):
        text = text + "\n"

    # Build text style
    text_style: dict[str, Any] = {}
    if bold is not None:
        text_style["bold"] = bold
    if italic is not None:
        text_style["italic"] = italic
    if underline is not None:
        text_style["underline"] = underline
    if font_size_pt is not None:
        text_style["fontSize"] = {"magnitude": font_size_pt, "unit": "PT"}
    if foreground_color_rgb is not None:
        r, g, b = foreground_color_rgb
        text_style["foregroundColor"] = {
            "color": {"rgbColor": {"red": r, "green": g, "blue": b}}
        }

    # Build paragraph style
    para_style: dict[str, Any] = {}
    if named_style_type is not None:
        para_style["namedStyleType"] = named_style_type
    if alignment is not None:
        para_style["alignment"] = alignment
    if line_spacing is not None:
        para_style["lineSpacing"] = line_spacing

    # Build paragraph dict
    para_dict: dict[str, Any] = {
        "paragraph": {"elements": [{"textRun": {"content": text}}]}
    }

    if text_style:
        para_dict["paragraph"]["elements"][0]["textRun"]["textStyle"] = text_style
    if para_style:
        para_dict["paragraph"]["paragraphStyle"] = para_style

    return para_dict


def _make_doc_with_styled_content(
    *elements: str | dict[str, Any], tab_id: str = "t.0"
) -> Document:
    """Create a Document from paragraphs, styled paragraphs, and tables.

    Strings become plain paragraphs; dicts are used as-is (e.g., from
    _make_styled_para or _make_table). A section break is prepended automatically.
    """
    content: list[dict[str, Any]] = [{"sectionBreak": {}}]
    for elem in elements:
        if isinstance(elem, str):
            text = elem if elem.endswith("\n") else elem + "\n"
            content.append(
                {"paragraph": {"elements": [{"textRun": {"content": text}}]}}
            )
        elif isinstance(elem, dict):
            content.append(elem)
            if "table" in elem:
                content.append(
                    {"paragraph": {"elements": [{"textRun": {"content": "\n"}}]}}
                )

    doc = Document.model_validate(
        {
            "documentId": "test",
            "tabs": [
                {
                    "tabProperties": {"tabId": tab_id},
                    "documentTab": {"body": {"content": content}},
                }
            ],
        }
    )
    return reindex_document(doc)


class TestReconcileAddTable:
    def test_add_table_at_end(self):
        """Add a 1x1 table after a paragraph."""
        base = _make_doc("Hello")
        table = _make_table([["Cell"]])
        desired = _make_doc_with_content("Hello", table)
        result = reconcile(base, desired)
        assert len(result) == 1 and result[0].requests is not None
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_add_table_between_paragraphs(self):
        """Add a table between two paragraphs."""
        base = _make_doc("Hello", "World")
        table = _make_table([["Cell"]])
        desired = _make_doc_with_content("Hello", table, "World")
        result = reconcile(base, desired)
        assert len(result) == 1 and result[0].requests is not None
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_add_table_with_content(self):
        """Add a 2x2 table with cell content."""
        base = _make_doc("Hello")
        table = _make_table([["A", "B"], ["C", "D"]])
        desired = _make_doc_with_content("Hello", table)
        result = reconcile(base, desired)
        assert len(result) == 1 and result[0].requests is not None
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_add_empty_table(self):
        """Add a table with empty cells."""
        base = _make_doc("Hello")
        table = _make_table([["", ""], ["", ""]])
        desired = _make_doc_with_content("Hello", table)
        result = reconcile(base, desired)
        assert len(result) == 1 and result[0].requests is not None
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"


class TestReconcileDeleteTable:
    def test_delete_table_at_end(self):
        """Delete a table from the end of the document."""
        table = _make_table([["Cell"]])
        base = _make_doc_with_content("Hello", table)
        desired = _make_doc("Hello")
        result = reconcile(base, desired)
        assert len(result) == 1 and result[0].requests is not None
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_delete_table_between_paragraphs(self):
        """Delete a table between two paragraphs."""
        table = _make_table([["Cell"]])
        base = _make_doc_with_content("Hello", table, "World")
        desired = _make_doc("Hello", "World")
        result = reconcile(base, desired)
        assert len(result) == 1 and result[0].requests is not None
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"


class TestReconcileModifyTableCells:
    def test_modify_single_cell(self):
        """Change text in a single cell."""
        base_table = _make_table([["Old"]])
        desired_table = _make_table([["New"]])
        base = _make_doc_with_content("Hello", base_table)
        desired = _make_doc_with_content("Hello", desired_table)
        result = reconcile(base, desired)
        assert len(result) == 1 and result[0].requests is not None
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_modify_multiple_cells(self):
        """Change text in multiple cells of a 2x2 table."""
        base_table = _make_table([["A", "B"], ["C", "D"]])
        desired_table = _make_table([["X", "Y"], ["Z", "W"]])
        base = _make_doc_with_content("Hello", base_table)
        desired = _make_doc_with_content("Hello", desired_table)
        result = reconcile(base, desired)
        assert len(result) == 1 and result[0].requests is not None
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_modify_one_cell_keep_others(self):
        """Change just one cell in a 2x2 table."""
        base_table = _make_table([["A", "B"], ["C", "D"]])
        desired_table = _make_table([["A", "B"], ["C", "X"]])
        base = _make_doc_with_content("Hello", base_table)
        desired = _make_doc_with_content("Hello", desired_table)
        result = reconcile(base, desired)
        assert len(result) == 1 and result[0].requests is not None
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_clear_cell_content(self):
        """Clear a cell to empty."""
        base_table = _make_table([["Hello"]])
        desired_table = _make_table([[""]])
        base = _make_doc_with_content("Before", base_table)
        desired = _make_doc_with_content("Before", desired_table)
        result = reconcile(base, desired)
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_fill_empty_cell(self):
        """Fill an empty cell with text."""
        base_table = _make_table([[""]])
        desired_table = _make_table([["Hello"]])
        base = _make_doc_with_content("Before", base_table)
        desired = _make_doc_with_content("Before", desired_table)
        result = reconcile(base, desired)
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_identical_tables_no_change(self):
        """Identical tables produce no requests."""
        table = _make_table([["A", "B"], ["C", "D"]])
        base = _make_doc_with_content("Hello", table)
        desired = _make_doc_with_content("Hello", table)
        result = reconcile(base, desired)
        assert len(result) == 0 or (
            len(result) == 1
            and (result[0].requests is None or len(result[0].requests) == 0)
        )
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"


class TestReconcileTableRows:
    def test_add_row(self):
        """Add a row to a table."""
        base_table = _make_table([["A", "B"]])
        desired_table = _make_table([["A", "B"], ["C", "D"]])
        base = _make_doc_with_content("Hello", base_table)
        desired = _make_doc_with_content("Hello", desired_table)
        result = reconcile(base, desired)
        assert len(result) == 1 and result[0].requests is not None
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_delete_row(self):
        """Delete a row from a table."""
        base_table = _make_table([["A", "B"], ["C", "D"]])
        desired_table = _make_table([["A", "B"]])
        base = _make_doc_with_content("Hello", base_table)
        desired = _make_doc_with_content("Hello", desired_table)
        result = reconcile(base, desired)
        assert len(result) == 1 and result[0].requests is not None
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_add_multiple_rows(self):
        """Add multiple rows to a table."""
        base_table = _make_table([["A"]])
        desired_table = _make_table([["A"], ["B"], ["C"]])
        base = _make_doc_with_content("Hello", base_table)
        desired = _make_doc_with_content("Hello", desired_table)
        result = reconcile(base, desired)
        assert len(result) == 1 and result[0].requests is not None
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"


class TestReconcileTableColumns:
    def test_add_column(self):
        """Add a column to a table."""
        base_table = _make_table([["A"], ["B"]])
        desired_table = _make_table([["A", "X"], ["B", "Y"]])
        base = _make_doc_with_content("Hello", base_table)
        desired = _make_doc_with_content("Hello", desired_table)
        result = reconcile(base, desired)
        assert len(result) == 1 and result[0].requests is not None
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_delete_column(self):
        """Delete a column from a table."""
        base_table = _make_table([["A", "B"], ["C", "D"]])
        desired_table = _make_table([["A"], ["C"]])
        base = _make_doc_with_content("Hello", base_table)
        desired = _make_doc_with_content("Hello", desired_table)
        result = reconcile(base, desired)
        assert len(result) == 1 and result[0].requests is not None
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"


class TestReconcileTableMixed:
    def test_table_and_paragraph_changes(self):
        """Modify both table cells and surrounding paragraphs."""
        base_table = _make_table([["Old"]])
        desired_table = _make_table([["New"]])
        base = _make_doc_with_content("Hello", base_table, "World")
        desired = _make_doc_with_content("Goodbye", desired_table, "Earth")
        result = reconcile(base, desired)
        assert len(result) == 1 and result[0].requests is not None
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_multiple_tables(self):
        """Document with multiple tables."""
        t1 = _make_table([["T1"]])
        t2 = _make_table([["T2"]])
        t1_new = _make_table([["T1-new"]])
        t2_new = _make_table([["T2-new"]])
        base = _make_doc_with_content("Start", t1, "Mid", t2, "End")
        desired = _make_doc_with_content("Start", t1_new, "Mid", t2_new, "End")
        result = reconcile(base, desired)
        assert len(result) == 1 and result[0].requests is not None
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_replace_paragraph_with_table(self):
        """Replace a paragraph with a table."""
        base = _make_doc("Hello", "World")
        table = _make_table([["Cell"]])
        desired = _make_doc_with_content("Hello", table)
        result = reconcile(base, desired)
        assert len(result) == 1 and result[0].requests is not None
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_replace_table_with_paragraph(self):
        """Replace a table with a paragraph."""
        table = _make_table([["Cell"]])
        base = _make_doc_with_content("Hello", table)
        desired = _make_doc("Hello", "World")
        result = reconcile(base, desired)
        assert len(result) == 1 and result[0].requests is not None
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"


class TestReconcileTableStructural:
    """Tests for structural row/column operations."""

    def test_add_row_in_middle(self):
        """Add a row between two existing rows."""
        base_table = _make_table([["A", "B"], ["C", "D"]])
        desired_table = _make_table([["A", "B"], ["X", "Y"], ["C", "D"]])
        base = _make_doc_with_content("Hello", base_table)
        desired = _make_doc_with_content("Hello", desired_table)
        result = reconcile(base, desired)
        assert len(result) == 1 and result[0].requests is not None
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_add_row_and_modify_cell(self):
        """Modify a cell and add a new row."""
        base_table = _make_table([["Old"]])
        desired_table = _make_table([["New"], ["Added"]])
        base = _make_doc_with_content("Hello", base_table)
        desired = _make_doc_with_content("Hello", desired_table)
        result = reconcile(base, desired)
        assert len(result) == 1 and result[0].requests is not None
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_add_row_and_column(self):
        """Grow a 1x1 table to 2x2."""
        base_table = _make_table([["A"]])
        desired_table = _make_table([["A", "B"], ["C", "D"]])
        base = _make_doc_with_content("Hello", base_table)
        desired = _make_doc_with_content("Hello", desired_table)
        result = reconcile(base, desired)
        assert len(result) == 1 and result[0].requests is not None
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_delete_row_and_column(self):
        """Shrink a 3x3 table to 2x2."""
        base_table = _make_table([["A", "B", "C"], ["D", "E", "F"], ["G", "H", "I"]])
        desired_table = _make_table([["A", "B"], ["D", "E"]])
        base = _make_doc_with_content("Hello", base_table)
        desired = _make_doc_with_content("Hello", desired_table)
        result = reconcile(base, desired)
        assert len(result) == 1 and result[0].requests is not None
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_delete_row_and_modify_cell(self):
        """Delete a row and modify a cell in remaining rows."""
        base_table = _make_table([["A", "B"], ["C", "D"], ["E", "F"]])
        desired_table = _make_table([["X", "B"], ["E", "F"]])
        base = _make_doc_with_content("Hello", base_table)
        desired = _make_doc_with_content("Hello", desired_table)
        result = reconcile(base, desired)
        assert len(result) == 1 and result[0].requests is not None
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_add_row_at_top(self):
        """Add a row at the very top of the table."""
        base_table = _make_table([["B", "C"]])
        desired_table = _make_table([["A", "X"], ["B", "C"]])
        base = _make_doc_with_content("Hello", base_table)
        desired = _make_doc_with_content("Hello", desired_table)
        result = reconcile(base, desired)
        assert len(result) == 1 and result[0].requests is not None
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_delete_middle_row(self):
        """Delete a row from the middle of a table."""
        base_table = _make_table([["A"], ["B"], ["C"]])
        desired_table = _make_table([["A"], ["C"]])
        base = _make_doc_with_content("Hello", base_table)
        desired = _make_doc_with_content("Hello", desired_table)
        result = reconcile(base, desired)
        assert len(result) == 1 and result[0].requests is not None
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_completely_different_table(self):
        """Table with completely different content (positional fallback)."""
        base_table = _make_table([["A", "B"], ["C", "D"]])
        desired_table = _make_table([["X", "Y"], ["Z", "W"]])
        base = _make_doc_with_content("Hello", base_table)
        desired = _make_doc_with_content("Hello", desired_table)
        result = reconcile(base, desired)
        assert len(result) == 1 and result[0].requests is not None
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_swap_duplicate_rows(self):
        """Swapping two rows with identical content must trigger structural diff.

        Regression test: extract_plain_text_from_table returned the same string
        for both orderings of duplicate rows, causing _diff_table_cell_styles_only
        to be called (which produces no structural requests) instead of
        _diff_table_structural.
        """
        base_table = _make_table([["X", "Y"], ["X", "Y"], ["A", "B"]])
        desired_table = _make_table([["A", "B"], ["X", "Y"], ["X", "Y"]])
        base = _make_doc_with_content("Hello", base_table)
        desired = _make_doc_with_content("Hello", desired_table)
        result = reconcile(base, desired)
        assert len(result) == 1 and result[0].requests is not None
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_swap_columns_with_same_text(self):
        """Swapping two columns with identical cell text must trigger structural diff.

        Similar regression: if two columns share the same per-cell text, the
        flat-string comparison would not detect the column swap.
        """
        base_table = _make_table([["same", "other"], ["same", "other"]])
        desired_table = _make_table([["other", "same"], ["other", "same"]])
        base = _make_doc_with_content("Hello", base_table)
        desired = _make_doc_with_content("Hello", desired_table)
        result = reconcile(base, desired)
        assert len(result) == 1 and result[0].requests is not None
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"


def _make_doc_with_header(
    header_id: str, header_text: str, *body_paragraphs: str, tab_id: str = "t.0"
) -> Document:
    """Helper: create a Document with a header and body content."""
    body_content: list[dict] = [{"sectionBreak": {}}]
    for text in body_paragraphs:
        if not text.endswith("\n"):
            text = text + "\n"
        body_content.append(
            {"paragraph": {"elements": [{"textRun": {"content": text}}]}}
        )

    if not header_text.endswith("\n"):
        header_text = header_text + "\n"

    doc = Document.model_validate(
        {
            "documentId": "test",
            "tabs": [
                {
                    "tabProperties": {"tabId": tab_id},
                    "documentTab": {
                        "body": {"content": body_content},
                        "headers": {
                            header_id: {
                                "headerId": header_id,
                                "content": [
                                    {
                                        "paragraph": {
                                            "elements": [
                                                {"textRun": {"content": header_text}}
                                            ]
                                        }
                                    }
                                ],
                            }
                        },
                    },
                }
            ],
        }
    )
    return reindex_document(doc)


def _make_doc_with_footer(
    footer_id: str, footer_text: str, *body_paragraphs: str, tab_id: str = "t.0"
) -> Document:
    """Helper: create a Document with a footer and body content."""
    body_content: list[dict] = [{"sectionBreak": {}}]
    for text in body_paragraphs:
        if not text.endswith("\n"):
            text = text + "\n"
        body_content.append(
            {"paragraph": {"elements": [{"textRun": {"content": text}}]}}
        )

    if not footer_text.endswith("\n"):
        footer_text = footer_text + "\n"

    doc = Document.model_validate(
        {
            "documentId": "test",
            "tabs": [
                {
                    "tabProperties": {"tabId": tab_id},
                    "documentTab": {
                        "body": {"content": body_content},
                        "footers": {
                            footer_id: {
                                "footerId": footer_id,
                                "content": [
                                    {
                                        "paragraph": {
                                            "elements": [
                                                {"textRun": {"content": footer_text}}
                                            ]
                                        }
                                    }
                                ],
                            }
                        },
                    },
                }
            ],
        }
    )
    return reindex_document(doc)


class TestReconcileMultiSegment:
    """Phase 3: Headers, footers, and footnotes."""

    def test_delete_header(self):
        """Delete a header from the document."""
        base = _make_doc_with_header("hdr1", "Header Text", "Body")
        desired = _make_doc("Body")
        result = reconcile(base, desired)
        assert len(result) == 1 and result[0].requests is not None
        # Check that we have a deleteHeader request
        request_types = [
            next(iter(req.model_dump(by_alias=True, exclude_none=True).keys()))
            for req in result[0].requests
        ]
        assert "deleteHeader" in request_types
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_delete_footer(self):
        """Delete a footer from the document."""
        base = _make_doc_with_footer("ftr1", "Footer Text", "Body")
        desired = _make_doc("Body")
        result = reconcile(base, desired)
        assert len(result) == 1 and result[0].requests is not None
        # Check that we have a deleteFooter request
        request_types = [
            next(iter(req.model_dump(by_alias=True, exclude_none=True).keys()))
            for req in result[0].requests
        ]
        assert "deleteFooter" in request_types
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_modify_header_content(self):
        """Modify the content of an existing header."""
        base = _make_doc_with_header("hdr1", "Old Header", "Body")
        desired = _make_doc_with_header("hdr1", "New Header", "Body")
        result = reconcile(base, desired)
        assert len(result) == 1 and result[0].requests is not None
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_modify_footer_content(self):
        """Modify the content of an existing footer."""
        base = _make_doc_with_footer("ftr1", "Old Footer", "Body")
        desired = _make_doc_with_footer("ftr1", "New Footer", "Body")
        result = reconcile(base, desired)
        assert len(result) == 1 and result[0].requests is not None
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_create_header(self):
        """Create a new header with content population (multi-batch).

        Batch 0: createHeader (creates empty header)
        Batch 1: insertText with DeferredID (populates header content)
        """
        base = _make_doc("Body")
        desired = _make_doc_with_header("hdr1", "New Header", "Body")
        result = reconcile(base, desired)

        # Should have 2 batches
        assert len(result) == 2

        # Batch 0: createHeader
        assert result[0].requests is not None
        request_types_0 = [
            next(iter(req.model_dump(by_alias=True, exclude_none=True).keys()))
            for req in result[0].requests
        ]
        assert "createHeader" in request_types_0

        # Batch 1: insertText with DeferredID
        assert result[1].requests is not None
        request_types_1 = [
            next(iter(req.model_dump(by_alias=True, exclude_none=True).keys()))
            for req in result[1].requests
        ]
        assert "insertText" in request_types_1

        # Verify the insertText uses DeferredID
        insert_req = next(
            req for req in result[1].requests if req.insert_text is not None
        )
        assert insert_req.insert_text is not None
        assert isinstance(insert_req.insert_text.location.segment_id, DeferredID)
        assert insert_req.insert_text.text == "New Header"

        # Verify end-to-end by executing batches
        # (Note: Can't use strict verify() because header IDs are assigned by API)

        base_dict = base.model_dump(by_alias=True, exclude_none=True)
        mock = MockGoogleDocsAPI(base_dict)

        # Execute batch 0
        batch_0_reqs = [
            req.model_dump(by_alias=True, exclude_none=True)
            for req in result[0].requests
        ]
        response_0 = mock.batch_update(batch_0_reqs)

        # Execute batch 1 with resolved IDs
        batch_1_resolved = resolve_deferred_ids([response_0], result[1])
        batch_1_reqs = [
            req.model_dump(by_alias=True, exclude_none=True)
            for req in batch_1_resolved.requests
        ]
        mock.batch_update(batch_1_reqs)

        # Check result
        actual = mock.get()
        headers = actual["tabs"][0]["documentTab"]["headers"]
        assert len(headers) == 1, "Should have exactly one header"
        header = next(iter(headers.values()))
        header_text = header["content"][0]["paragraph"]["elements"][0]["textRun"][
            "content"
        ]
        assert header_text == "New Header\n"

    def test_create_footer(self):
        """Create a new footer with content population (multi-batch).

        Batch 0: createFooter (creates empty footer)
        Batch 1: insertText with DeferredID (populates footer content)
        """
        base = _make_doc("Body")
        desired = _make_doc_with_footer("ftr1", "New Footer", "Body")
        result = reconcile(base, desired)

        # Should have 2 batches
        assert len(result) == 2

        # Batch 0: createFooter
        assert result[0].requests is not None
        request_types_0 = [
            next(iter(req.model_dump(by_alias=True, exclude_none=True).keys()))
            for req in result[0].requests
        ]
        assert "createFooter" in request_types_0

        # Batch 1: insertText with DeferredID
        assert result[1].requests is not None
        request_types_1 = [
            next(iter(req.model_dump(by_alias=True, exclude_none=True).keys()))
            for req in result[1].requests
        ]
        assert "insertText" in request_types_1

        # Verify the insertText uses DeferredID
        insert_req = next(
            req for req in result[1].requests if req.insert_text is not None
        )
        assert insert_req.insert_text is not None
        assert isinstance(insert_req.insert_text.location.segment_id, DeferredID)
        assert insert_req.insert_text.text == "New Footer"

        # Verify end-to-end by executing batches
        # (Note: Can't use strict verify() because footer IDs are assigned by API)

        base_dict = base.model_dump(by_alias=True, exclude_none=True)
        mock = MockGoogleDocsAPI(base_dict)

        # Execute batch 0
        batch_0_reqs = [
            req.model_dump(by_alias=True, exclude_none=True)
            for req in result[0].requests
        ]
        response_0 = mock.batch_update(batch_0_reqs)

        # Execute batch 1 with resolved IDs
        batch_1_resolved = resolve_deferred_ids([response_0], result[1])
        batch_1_reqs = [
            req.model_dump(by_alias=True, exclude_none=True)
            for req in batch_1_resolved.requests
        ]
        mock.batch_update(batch_1_reqs)

        # Check result
        actual = mock.get()
        footers = actual["tabs"][0]["documentTab"]["footers"]
        assert len(footers) == 1, "Should have exactly one footer"
        footer = next(iter(footers.values()))
        footer_text = footer["content"][0]["paragraph"]["elements"][0]["textRun"][
            "content"
        ]
        assert footer_text == "New Footer\n"


def _make_multi_tab_doc(tabs: list[tuple[str, str, list[str]]]) -> Document:
    """Helper: create a Document with multiple tabs.

    Args:
        tabs: List of (tab_id, title, [paragraphs]) tuples

    Returns:
        Document with multiple tabs
    """
    doc_tabs: list[dict[str, Any]] = []
    for idx, (tab_id, title, paragraphs) in enumerate(tabs):
        content: list[dict] = [{"sectionBreak": {}}]
        for text in paragraphs:
            if not text.endswith("\n"):
                text = text + "\n"
            content.append(
                {"paragraph": {"elements": [{"textRun": {"content": text}}]}}
            )

        doc_tabs.append(
            {
                "tabProperties": {"tabId": tab_id, "title": title, "index": idx},
                "documentTab": {"body": {"content": content}},
            }
        )

    doc = Document.model_validate({"documentId": "test", "tabs": doc_tabs})
    return reindex_document(doc)


class TestReconcileMultiTab:
    """Phase 4: Tests for multi-tab reconciliation."""

    def test_delete_tab(self):
        """Delete a tab from a multi-tab document."""
        base = _make_multi_tab_doc(
            [
                ("t.0", "Tab 1", ["First tab content"]),
                ("t.1", "Tab 2", ["Second tab content"]),
            ]
        )
        desired = _make_multi_tab_doc([("t.0", "Tab 1", ["First tab content"])])

        result = reconcile(base, desired)
        assert len(result) == 1 and result[0].requests is not None
        request_types = [
            next(iter(req.model_dump(by_alias=True, exclude_none=True).keys()))
            for req in result[0].requests
        ]
        assert "deleteTab" in request_types
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_create_tab(self):
        """Create a new tab and populate its body content (multi-batch).

        Batch 0: addDocumentTab
        Batch 1: insertText with DeferredID (populates body content)
        """
        base = _make_multi_tab_doc([("t.0", "Tab 1", ["First tab content"])])
        desired = _make_multi_tab_doc(
            [
                ("t.0", "Tab 1", ["First tab content"]),
                ("t.1", "Tab 2", ["Second tab content"]),
            ]
        )

        result = reconcile(base, desired)
        assert len(result) == 2, "Should have 2 batches: creation + body population"

        request_types_0 = [
            next(iter(req.model_dump(by_alias=True, exclude_none=True).keys()))
            for req in (result[0].requests or [])
        ]
        assert "addDocumentTab" in request_types_0

        request_types_1 = [
            next(iter(req.model_dump(by_alias=True, exclude_none=True).keys()))
            for req in (result[1].requests or [])
        ]
        assert "insertText" in request_types_1

        # Execute batches and verify body content
        base_dict = base.model_dump(by_alias=True, exclude_none=True)
        mock = MockGoogleDocsAPI(base_dict)

        batch_0_reqs = [
            req.model_dump(by_alias=True, exclude_none=True)
            for req in result[0].requests
        ]
        response_0 = mock.batch_update(batch_0_reqs)

        batch_1_resolved = resolve_deferred_ids([response_0], result[1])
        batch_1_reqs = [
            req.model_dump(by_alias=True, exclude_none=True)
            for req in batch_1_resolved.requests
        ]
        mock.batch_update(batch_1_reqs)

        actual = mock.get()
        tabs = actual["tabs"]
        assert len(tabs) == 2, "Should have 2 tabs"
        new_tab = tabs[1]
        assert new_tab["tabProperties"]["title"] == "Tab 2"

        body_text = "".join(
            elem["paragraph"]["elements"][0]["textRun"]["content"]
            for elem in new_tab["documentTab"]["body"]["content"]
            if "paragraph" in elem
        )
        assert "Second tab content" in body_text

    def test_rename_tab(self):
        """Change the title of an existing tab."""
        base = _make_multi_tab_doc(
            [
                ("t.0", "Old Title", ["First tab content"]),
                ("t.1", "Tab 2", ["Second tab content"]),
            ]
        )
        desired = _make_multi_tab_doc(
            [
                ("t.0", "New Title", ["First tab content"]),
                ("t.1", "Tab 2", ["Second tab content"]),
            ]
        )

        result = reconcile(base, desired)
        assert len(result) == 1 and result[0].requests is not None
        request_types = [
            next(iter(req.model_dump(by_alias=True, exclude_none=True).keys()))
            for req in result[0].requests
        ]
        assert "updateDocumentTabProperties" in request_types
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_modify_content_across_tabs(self):
        """Modify content in multiple tabs simultaneously."""
        base = _make_multi_tab_doc(
            [
                ("t.0", "Tab 1", ["Old content"]),
                ("t.1", "Tab 2", ["Old content"]),
            ]
        )
        desired = _make_multi_tab_doc(
            [
                ("t.0", "Tab 1", ["New content"]),
                ("t.1", "Tab 2", ["New content"]),
            ]
        )

        result = reconcile(base, desired)
        assert len(result) == 1 and result[0].requests is not None
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"


class TestReconcileParagraphStyles:
    """Tests for paragraph-level style changes."""

    def test_change_named_style_type(self):
        """Change paragraph from NORMAL_TEXT to HEADING_1."""
        base_para = _make_styled_para("Heading", named_style_type="NORMAL_TEXT")
        desired_para = _make_styled_para("Heading", named_style_type="HEADING_1")
        base = _make_doc_with_styled_content(base_para)
        desired = _make_doc_with_styled_content(desired_para)

        result = reconcile(base, desired)
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_change_alignment(self):
        """Change paragraph alignment from START to CENTER."""
        base_para = _make_styled_para("Text", alignment="START")
        desired_para = _make_styled_para("Text", alignment="CENTER")
        base = _make_doc_with_styled_content(base_para)
        desired = _make_doc_with_styled_content(desired_para)

        result = reconcile(base, desired)
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_identical_paragraph_styles_no_change(self):
        """Identical paragraph styles produce no requests."""
        para = _make_styled_para("Text", alignment="CENTER", line_spacing=115.0)
        base = _make_doc_with_styled_content(para)
        desired = _make_doc_with_styled_content(para)

        result = reconcile(base, desired)
        assert len(result) == 0 or (
            len(result) == 1
            and (result[0].requests is None or len(result[0].requests) == 0)
        )


class TestReconcileTextStyles:
    """Tests for text run style changes."""

    def test_make_text_bold(self):
        """Add bold to plain text."""
        base_para = _make_styled_para("Hello")
        desired_para = _make_styled_para("Hello", bold=True)
        base = _make_doc_with_styled_content(base_para)
        desired = _make_doc_with_styled_content(desired_para)

        result = reconcile(base, desired)
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_remove_bold(self):
        """Remove bold from text."""
        base_para = _make_styled_para("Hello", bold=True)
        desired_para = _make_styled_para("Hello")
        base = _make_doc_with_styled_content(base_para)
        desired = _make_doc_with_styled_content(desired_para)

        result = reconcile(base, desired)
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_multiple_text_style_fields(self):
        """Change multiple text style fields simultaneously."""
        base_para = _make_styled_para("Hello")
        desired_para = _make_styled_para(
            "Hello", bold=True, italic=True, underline=True, font_size_pt=14.0
        )
        base = _make_doc_with_styled_content(base_para)
        desired = _make_doc_with_styled_content(desired_para)

        result = reconcile(base, desired)
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_change_font_size(self):
        """Change font size."""
        base_para = _make_styled_para("Hello", font_size_pt=12.0)
        desired_para = _make_styled_para("Hello", font_size_pt=18.0)
        base = _make_doc_with_styled_content(base_para)
        desired = _make_doc_with_styled_content(desired_para)

        result = reconcile(base, desired)
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_identical_text_styles_no_change(self):
        """Identical text styles produce no requests."""
        para = _make_styled_para("Hello", bold=True, italic=True)
        base = _make_doc_with_styled_content(para)
        desired = _make_doc_with_styled_content(para)

        result = reconcile(base, desired)
        assert len(result) == 0 or (
            len(result) == 1
            and (result[0].requests is None or len(result[0].requests) == 0)
        )

    def test_mid_run_style_change(self):
        """Apply bold to only part of a paragraph text (run-count mismatch).

        base: single run "Hello World\\n"
        desired: two runs — "Hello" (bold) + " World\\n" (plain)
        LCS matches (same text), but run counts differ → positional fallback.
        """
        base = _make_doc_with_styled_content(
            {"paragraph": {"elements": [{"textRun": {"content": "Hello World\n"}}]}}
        )
        desired = _make_doc_with_styled_content(
            {
                "paragraph": {
                    "elements": [
                        {
                            "textRun": {
                                "content": "Hello",
                                "textStyle": {"bold": True},
                            }
                        },
                        {"textRun": {"content": " World\n"}},
                    ]
                }
            }
        )

        result = reconcile(base, desired)
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"


class TestReconcileCombinedStyles:
    """Tests for combined style scenarios."""

    def test_text_and_paragraph_style_change(self):
        """Change both text and paragraph styles."""
        base_para = _make_styled_para("Hello", bold=True, alignment="START")
        desired_para = _make_styled_para("Hello", bold=True, alignment="CENTER")
        base = _make_doc_with_styled_content(base_para)
        desired = _make_doc_with_styled_content(desired_para)

        result = reconcile(base, desired)
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_heading_with_bold(self):
        """Create a bold heading."""
        base_para = _make_styled_para("Title", named_style_type="NORMAL_TEXT")
        desired_para = _make_styled_para(
            "Title", named_style_type="HEADING_1", bold=True
        )
        base = _make_doc_with_styled_content(base_para)
        desired = _make_doc_with_styled_content(desired_para)

        result = reconcile(base, desired)
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_style_multiple_paragraphs(self):
        """Apply different styles to multiple paragraphs."""
        base_para1 = _make_styled_para("Paragraph 1")
        base_para2 = _make_styled_para("Paragraph 2")
        desired_para1 = _make_styled_para("Paragraph 1", bold=True, alignment="CENTER")
        desired_para2 = _make_styled_para("Paragraph 2", italic=True)
        base = _make_doc_with_styled_content(base_para1, base_para2)
        desired = _make_doc_with_styled_content(desired_para1, desired_para2)

        result = reconcile(base, desired)
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"


# ---------------------------------------------------------------------------
# Helpers for Phase 7 tests
# ---------------------------------------------------------------------------

# Nesting-level indentation formula used by createParagraphBullets:
#   indentStart = 36 + level * 36 PT
#   indentFirstLine = 18 + level * 36 PT
_BULLET_NESTING_LEVELS = [
    {
        "indentStart": {"magnitude": 36 + i * 36, "unit": "PT"},
        "indentFirstLine": {"magnitude": 18 + i * 36, "unit": "PT"},
    }
    for i in range(9)
]

_LINK_BLUE = {
    "color": {"rgbColor": {"red": 0.06666667, "green": 0.33333334, "blue": 0.8}}
}


def _make_doc_with_bullet(
    text: str,
    nesting_level: int = 0,
    *,
    tab_id: str = "t.0",
) -> Document:
    """Create a Document with a single bulleted paragraph at the given nesting level.

    Includes the list definition so mock can compute nestingLevel from indentation.
    """
    il = 18 + nesting_level * 36
    is_ = 36 + nesting_level * 36
    if not text.endswith("\n"):
        text = text + "\n"
    bullet: dict[str, Any] = {"listId": "list1"}
    if nesting_level > 0:
        bullet["nestingLevel"] = nesting_level

    doc = Document.model_validate(
        {
            "documentId": "test",
            "tabs": [
                {
                    "tabProperties": {"tabId": tab_id},
                    "documentTab": {
                        "body": {
                            "content": [
                                {"sectionBreak": {}},
                                {
                                    "paragraph": {
                                        "elements": [{"textRun": {"content": text}}],
                                        "bullet": bullet,
                                        "paragraphStyle": {
                                            "indentFirstLine": {
                                                "magnitude": il,
                                                "unit": "PT",
                                            },
                                            "indentStart": {
                                                "magnitude": is_,
                                                "unit": "PT",
                                            },
                                        },
                                    }
                                },
                            ]
                        },
                        "lists": {
                            "list1": {
                                "listProperties": {
                                    "nestingLevels": _BULLET_NESTING_LEVELS
                                }
                            }
                        },
                    },
                }
            ],
        }
    )
    return reindex_document(doc)


class TestReconcileBulletNesting:
    """Tests for bullet nesting level changes."""

    def test_nesting_level_increase(self):
        """Change bullet nesting level from 0 to 1."""
        base = _make_doc_with_bullet("Hello", nesting_level=0)
        desired = _make_doc_with_bullet("Hello", nesting_level=1)

        result = reconcile(base, desired)
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_nesting_level_decrease(self):
        """Change bullet nesting level from 2 to 0."""
        base = _make_doc_with_bullet("Hello", nesting_level=2)
        desired = _make_doc_with_bullet("Hello", nesting_level=0)

        result = reconcile(base, desired)
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_add_bullet_at_nesting_level_1(self):
        """Add a bullet at nesting level 1 to a plain paragraph."""
        base = _make_doc_with_styled_content("Hello")
        desired = _make_doc_with_bullet("Hello", nesting_level=1)

        result = reconcile(base, desired)
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_same_nesting_level_no_change(self):
        """Same nesting level produces no unnecessary requests."""
        base = _make_doc_with_bullet("Hello", nesting_level=1)
        desired = _make_doc_with_bullet("Hello", nesting_level=1)

        result = reconcile(base, desired)
        assert len(result) == 0 or (
            len(result) == 1
            and (result[0].requests is None or len(result[0].requests) == 0)
        )


class TestReconcileTableCellStyles:
    """Tests for paragraph/text style changes within table cells."""

    def _make_table_cell_doc(
        self,
        cell_text: str,
        bold: bool | None = None,
        italic: bool | None = None,
        alignment: str | None = None,
    ) -> Document:
        """Create a Document with a 1x1 table with a styled cell."""
        text_style: dict[str, Any] = {}
        if bold is not None:
            text_style["bold"] = bold
        if italic is not None:
            text_style["italic"] = italic

        para_style: dict[str, Any] = {}
        if alignment is not None:
            para_style["alignment"] = alignment

        el: dict[str, Any] = {"textRun": {"content": cell_text + "\n"}}
        if text_style:
            el["textRun"]["textStyle"] = text_style

        para: dict[str, Any] = {"paragraph": {"elements": [el]}}
        if para_style:
            para["paragraph"]["paragraphStyle"] = para_style

        return _make_doc_with_styled_content(
            {
                "table": {
                    "rows": 1,
                    "columns": 1,
                    "tableRows": [{"tableCells": [{"content": [para]}]}],
                }
            }
        )

    def test_make_cell_text_bold(self):
        """Apply bold to text in a table cell."""
        base = self._make_table_cell_doc("Cell content", bold=False)
        desired = self._make_table_cell_doc("Cell content", bold=True)

        result = reconcile(base, desired)
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_change_cell_paragraph_alignment(self):
        """Change alignment in a table cell paragraph."""
        base = self._make_table_cell_doc("Cell", alignment="START")
        desired = self._make_table_cell_doc("Cell", alignment="CENTER")

        result = reconcile(base, desired)
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_multiple_cell_style_changes(self):
        """Change bold and italic in a table cell."""
        base = self._make_table_cell_doc("Cell content")
        desired = self._make_table_cell_doc("Cell content", bold=True, italic=True)

        result = reconcile(base, desired)
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_identical_cell_styles_no_change(self):
        """Identical cell styles produce no requests."""
        base = self._make_table_cell_doc("Cell", bold=True)
        desired = self._make_table_cell_doc("Cell", bold=True)

        result = reconcile(base, desired)
        assert len(result) == 0 or (
            len(result) == 1
            and (result[0].requests is None or len(result[0].requests) == 0)
        )


class TestReconcileLinkStyle:
    """Tests for link addition and removal in text runs."""

    def test_add_link(self):
        """Add a hyperlink to text.

        After applying updateTextStyle with link, the mock splits the trailing \\n
        into a separate run and auto-adds underline and foregroundColor. The desired
        document reflects this final state.
        """
        base = _make_doc_with_styled_content(
            {"paragraph": {"elements": [{"textRun": {"content": "Click here\n"}}]}}
        )
        # Desired: two runs — linked text + separate \\n (as the mock produces)
        desired = _make_doc_with_styled_content(
            {
                "paragraph": {
                    "elements": [
                        {
                            "textRun": {
                                "content": "Click here",
                                "textStyle": {
                                    "link": {"url": "http://example.com"},
                                    "underline": True,
                                    "foregroundColor": _LINK_BLUE,
                                },
                            }
                        },
                        {"textRun": {"content": "\n"}},
                    ]
                }
            }
        )

        result = reconcile(base, desired)
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_remove_link(self):
        """Remove a hyperlink from text.

        Base has two runs (linked text + separate \\n). Desired has two runs
        without link styles. The mock keeps runs separate after updateTextStyle.
        """
        base = _make_doc_with_styled_content(
            {
                "paragraph": {
                    "elements": [
                        {
                            "textRun": {
                                "content": "Click here",
                                "textStyle": {
                                    "link": {"url": "http://example.com"},
                                    "underline": True,
                                    "foregroundColor": _LINK_BLUE,
                                },
                            }
                        },
                        {"textRun": {"content": "\n"}},
                    ]
                }
            }
        )
        # Desired: same two runs but without link/underline/foregroundColor
        desired = _make_doc_with_styled_content(
            {
                "paragraph": {
                    "elements": [
                        {"textRun": {"content": "Click here"}},
                        {"textRun": {"content": "\n"}},
                    ]
                }
            }
        )

        result = reconcile(base, desired)
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"


# ---------------------------------------------------------------------------
# Phase 7: Edge Cases + Coverage
# ---------------------------------------------------------------------------


def _make_doc_with_raw_content(
    *elements: dict[str, Any], tab_id: str = "t.0"
) -> Document:
    """Create a Document from raw element dicts (no automatic paragraph wrapping).

    A section break is prepended automatically.
    """
    content: list[dict[str, Any]] = [{"sectionBreak": {}}]
    for elem in elements:
        content.append(elem)

    doc = Document.model_validate(
        {
            "documentId": "test",
            "tabs": [
                {
                    "tabProperties": {"tabId": tab_id},
                    "documentTab": {"body": {"content": content}},
                }
            ],
        }
    )
    return reindex_document(doc)


class TestReconcileTableOfContents:
    """Tests for tableOfContents read-only validation."""

    def test_toc_delete_raises_error(self):
        """Removing a TOC raises ReconcileError."""
        base = _make_doc_with_raw_content(
            {"tableOfContents": {}},
            {"paragraph": {"elements": [{"textRun": {"content": "Body\n"}}]}},
        )
        desired = _make_doc("Body")

        with pytest.raises(ReconcileError, match="tableOfContents"):
            reconcile(base, desired)

    def test_toc_add_raises_error(self):
        """Adding a TOC raises ReconcileError."""
        base = _make_doc("Body")
        desired = _make_doc_with_raw_content(
            {"tableOfContents": {}},
            {"paragraph": {"elements": [{"textRun": {"content": "Body\n"}}]}},
        )

        with pytest.raises(ReconcileError, match="tableOfContents"):
            reconcile(base, desired)

    def test_matched_toc_no_error(self):
        """Same TOC in base and desired produces no error and no requests."""
        base = _make_doc_with_raw_content(
            {"tableOfContents": {}},
            {"paragraph": {"elements": [{"textRun": {"content": "Body\n"}}]}},
        )
        desired = _make_doc_with_raw_content(
            {"tableOfContents": {}},
            {"paragraph": {"elements": [{"textRun": {"content": "Body\n"}}]}},
        )

        result = reconcile(base, desired)
        # No error and no requests (TOC is skipped, body is identical)
        assert len(result) == 0 or (
            len(result) == 1
            and (result[0].requests is None or len(result[0].requests) == 0)
        )


class TestReconcileSectionBreaks:
    """Tests for section break change handling."""

    def test_delete_section_break_raises_error(self):
        """Removing a section break raises ReconcileError."""
        # Build a document with two section breaks manually
        doc_dict: dict[str, Any] = {
            "documentId": "test",
            "tabs": [
                {
                    "tabProperties": {"tabId": "t.0"},
                    "documentTab": {
                        "body": {
                            "content": [
                                {"sectionBreak": {}},
                                {
                                    "paragraph": {
                                        "elements": [
                                            {"textRun": {"content": "Para 1\n"}}
                                        ]
                                    }
                                },
                                {
                                    "sectionBreak": {
                                        "sectionStyle": {"sectionType": "NEXT_PAGE"}
                                    }
                                },
                                {
                                    "paragraph": {
                                        "elements": [
                                            {"textRun": {"content": "Para 2\n"}}
                                        ]
                                    }
                                },
                            ]
                        }
                    },
                }
            ],
        }
        base = reindex_document(Document.model_validate(doc_dict))
        # desired has only one section break (the initial one)
        desired = _make_doc("Para 1", "Para 2")

        with pytest.raises(ReconcileError, match=r"[Ss]ection break"):
            reconcile(base, desired)

    def test_add_section_break_raises_error(self):
        """Adding a section break raises ReconcileError."""
        base = _make_doc("Para 1", "Para 2")
        # desired has an extra section break in the middle
        doc_dict: dict[str, Any] = {
            "documentId": "test",
            "tabs": [
                {
                    "tabProperties": {"tabId": "t.0"},
                    "documentTab": {
                        "body": {
                            "content": [
                                {"sectionBreak": {}},
                                {
                                    "paragraph": {
                                        "elements": [
                                            {"textRun": {"content": "Para 1\n"}}
                                        ]
                                    }
                                },
                                {
                                    "sectionBreak": {
                                        "sectionStyle": {"sectionType": "NEXT_PAGE"}
                                    }
                                },
                                {
                                    "paragraph": {
                                        "elements": [
                                            {"textRun": {"content": "Para 2\n"}}
                                        ]
                                    }
                                },
                            ]
                        }
                    },
                }
            ],
        }
        desired = reindex_document(Document.model_validate(doc_dict))

        with pytest.raises(ReconcileError, match=r"[Ss]ection break"):
            reconcile(base, desired)

    def test_normal_document_no_section_break_error(self):
        """Normal documents (with initial section break matched) have no error."""
        base = _make_doc("Hello", "World")
        desired = _make_doc("Hello", "World", "New paragraph")

        # Should not raise — the initial section break is MATCHED
        result = reconcile(base, desired)
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"


class TestReconcileSpecialElements:
    """Tests for paragraphs containing non-text elements."""

    def test_delete_paragraph_with_page_break(self):
        """Deleting a paragraph containing a page break works fine."""
        base = _make_doc_with_raw_content(
            {
                "paragraph": {
                    "elements": [{"pageBreak": {}}, {"textRun": {"content": "\n"}}]
                }
            },
            {"paragraph": {"elements": [{"textRun": {"content": "After\n"}}]}},
        )
        desired = _make_doc("After")

        # Deletion should succeed
        result = reconcile(base, desired)
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_add_paragraph_with_page_break_raises_error(self):
        """Adding a paragraph with a page break raises ReconcileError."""
        base = _make_doc("Before")
        desired = _make_doc_with_raw_content(
            {"paragraph": {"elements": [{"textRun": {"content": "Before\n"}}]}},
            {
                "paragraph": {
                    "elements": [{"pageBreak": {}}, {"textRun": {"content": "\n"}}]
                }
            },
        )

        with pytest.raises(ReconcileError, match="non-text elements"):
            reconcile(base, desired)

    def test_matched_paragraph_with_horizontal_rule(self):
        """Matched paragraph with horizontal rule produces no error."""
        para = {
            "paragraph": {
                "elements": [{"horizontalRule": {}}, {"textRun": {"content": "\n"}}]
            }
        }
        base = _make_doc_with_raw_content(para)
        desired = _make_doc_with_raw_content(para)

        # No error and no requests (identical)
        result = reconcile(base, desired)
        assert len(result) == 0 or (
            len(result) == 1
            and (result[0].requests is None or len(result[0].requests) == 0)
        )

    def test_add_page_break_paragraph_in_middle_raises_error(self):
        """Adding a page break paragraph between existing paragraphs raises ReconcileError.

        This triggers the inner gap (right anchor present) code path.
        """
        base = _make_doc("Before", "After")
        desired = _make_doc_with_raw_content(
            {"paragraph": {"elements": [{"textRun": {"content": "Before\n"}}]}},
            {
                "paragraph": {
                    "elements": [{"pageBreak": {}}, {"textRun": {"content": "\n"}}]
                }
            },
            {"paragraph": {"elements": [{"textRun": {"content": "After\n"}}]}},
        )

        with pytest.raises(ReconcileError, match="non-text elements"):
            reconcile(base, desired)


class TestReconcileUTF16:
    """Tests verifying UTF-16 index correctness with emoji and multi-unit characters."""

    def test_add_emoji_paragraph(self):
        """Add a paragraph containing emoji (emoji = 2 UTF-16 code units)."""
        base = _make_doc("Hello")
        desired = _make_doc("Hello", "Party \U0001f389")  # 🎉 = U+1F389

        result = reconcile(base, desired)
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_delete_emoji_paragraph(self):
        """Delete a paragraph containing emoji."""
        base = _make_doc("Hello", "Party \U0001f389")
        desired = _make_doc("Hello")

        result = reconcile(base, desired)
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_modify_emoji_paragraph(self):
        """Change a paragraph with one emoji to another."""
        base = _make_doc("Hello", "Hello \U0001f600")  # 😀
        desired = _make_doc("Hello", "Hello \U0001f680")  # 🚀

        result = reconcile(base, desired)
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_emoji_bold(self):
        """Apply bold style to a paragraph containing emoji."""
        base_para = {
            "paragraph": {"elements": [{"textRun": {"content": "Rocket \U0001f680\n"}}]}
        }
        desired_para = {
            "paragraph": {
                "elements": [
                    {
                        "textRun": {
                            "content": "Rocket \U0001f680\n",
                            "textStyle": {"bold": True},
                        }
                    }
                ]
            }
        }
        base = _make_doc_with_styled_content(base_para)
        desired = _make_doc_with_styled_content(desired_para)

        result = reconcile(base, desired)
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"


# ---------------------------------------------------------------------------
# DeferredID request_index correctness (multi-batch scenarios)
# ---------------------------------------------------------------------------


def _make_doc_with_header_and_footer(
    header_text: str,
    footer_text: str,
    *body_paragraphs: str,
    header_id: str = "hdr1",
    footer_id: str = "ftr1",
    tab_id: str = "t.0",
) -> Document:
    """Helper: create a Document with both a header and a footer."""
    body_content: list[dict] = [{"sectionBreak": {}}]
    for text in body_paragraphs:
        if not text.endswith("\n"):
            text = text + "\n"
        body_content.append(
            {"paragraph": {"elements": [{"textRun": {"content": text}}]}}
        )

    doc = Document.model_validate(
        {
            "documentId": "test",
            "tabs": [
                {
                    "tabProperties": {"tabId": tab_id},
                    "documentTab": {
                        "body": {"content": body_content},
                        "headers": {
                            header_id: {
                                "headerId": header_id,
                                "content": [
                                    {
                                        "paragraph": {
                                            "elements": [
                                                {
                                                    "textRun": {
                                                        "content": header_text + "\n"
                                                    }
                                                }
                                            ]
                                        }
                                    }
                                ],
                            }
                        },
                        "footers": {
                            footer_id: {
                                "footerId": footer_id,
                                "content": [
                                    {
                                        "paragraph": {
                                            "elements": [
                                                {
                                                    "textRun": {
                                                        "content": footer_text + "\n"
                                                    }
                                                }
                                            ]
                                        }
                                    }
                                ],
                            }
                        },
                    },
                }
            ],
        }
    )
    return reindex_document(doc)


class TestDeferredIDRequestIndex:
    """Tests for the request_index bug in multi-batch scenarios.

    The bug: request_index was computed as len(_requests) (flat global list),
    but it should be the count of entries in the *same* batch, because
    replies[] only contains entries for that batch.
    """

    def test_create_header_and_footer_simultaneously(self):
        """Adding both a header and footer to a tab generates correct DeferredIDs.

        Scenario triggering the bug in _reconcile_new_segment:
        - batch 0: createHeader, createFooter
        - batch 1: insertText (header content), insertText (footer content)

        Without the fix, the second _reconcile_new_segment call sees
        len(_requests) = 2 (createHeader + insertText_header) and records
        request_index=2 for createFooter, but createFooter is at replies[1].
        """
        base = _make_doc("Body")
        desired = _make_doc_with_header_and_footer("My Header", "My Footer", "Body")

        result = reconcile(base, desired)

        # Should have 2 batches: creation + population
        assert len(result) == 2

        # Batch 0: createHeader + createFooter (2 creation requests)
        assert result[0].requests is not None
        request_types_0 = [
            next(iter(req.model_dump(by_alias=True, exclude_none=True).keys()))
            for req in result[0].requests
        ]
        assert "createHeader" in request_types_0
        assert "createFooter" in request_types_0

        # Batch 1: insertText for header + insertText for footer
        assert result[1].requests is not None

        # Verify DeferredIDs in batch 1 have correct request_index (0 or 1 only)
        for req in result[1].requests:
            if req.insert_text is not None:
                seg_id = req.insert_text.location.segment_id
                assert isinstance(seg_id, DeferredID)
                assert seg_id.batch_index == 0
                assert seg_id.request_index < 2, (
                    f"request_index={seg_id.request_index} is out of range for "
                    f"batch 0 which has only 2 replies"
                )

        # End-to-end: execute batches and verify final content

        base_dict = base.model_dump(by_alias=True, exclude_none=True)
        mock = MockGoogleDocsAPI(base_dict)

        batch_0_reqs = [
            req.model_dump(by_alias=True, exclude_none=True)
            for req in result[0].requests
        ]
        response_0 = mock.batch_update(batch_0_reqs)

        batch_1_resolved = resolve_deferred_ids([response_0], result[1])
        batch_1_reqs = [
            req.model_dump(by_alias=True, exclude_none=True)
            for req in batch_1_resolved.requests
        ]
        mock.batch_update(batch_1_reqs)

        actual = mock.get()
        tab = actual["tabs"][0]["documentTab"]

        headers = tab.get("headers", {})
        assert len(headers) == 1
        header_text = next(iter(headers.values()))["content"][0]["paragraph"][
            "elements"
        ][0]["textRun"]["content"]
        assert header_text == "My Header\n"

        footers = tab.get("footers", {})
        assert len(footers) == 1
        footer_text = next(iter(footers.values()))["content"][0]["paragraph"][
            "elements"
        ][0]["textRun"]["content"]
        assert footer_text == "My Footer\n"

    def test_new_tab_deferred_id_request_index_is_batch_local(self):
        """The DeferredID for addDocumentTab uses the per-batch position, not flat list index.

        Scenario:
        - Matched tab t.0 gains a new footer →
            batch 0: createFooter_t0       (batch-0 index 0)
            batch 1: insertText_footer_t0  (batch-1 index 0)
        - New tab t.1 added →
            batch 0: addDocumentTab_t1     (batch-0 index 1)  ← DeferredID(batch=0, req=1)

        Without the fix, len(_requests)=2 (includes the batch-1 insertText) when
        addDocumentTab_t1 is appended, so the DeferredID records request_index=2.
        But batch 0 only has 2 replies ([0]=createFooterReply, [1]=addDocumentTabReply),
        so resolve_deferred_ids raises ReconcileError("only 2 replies").
        With the fix, request_index=1 → resolves correctly.
        """
        base = _make_multi_tab_doc([("t.0", "Tab 1", ["Content"])])

        # t.0 gains a footer; t.1 is a brand-new empty tab
        desired_tabs: list[dict] = [
            {
                "tabProperties": {"tabId": "t.0", "title": "Tab 1", "index": 0},
                "documentTab": {
                    "body": {
                        "content": [
                            {"sectionBreak": {}},
                            {
                                "paragraph": {
                                    "elements": [{"textRun": {"content": "Content\n"}}]
                                }
                            },
                        ]
                    },
                    "footers": {
                        "ftr1": {
                            "footerId": "ftr1",
                            "content": [
                                {
                                    "paragraph": {
                                        "elements": [
                                            {"textRun": {"content": "Tab1 Footer\n"}}
                                        ]
                                    }
                                }
                            ],
                        }
                    },
                },
            },
            {
                "tabProperties": {"tabId": "t.1", "title": "Tab 2", "index": 1},
                "documentTab": {
                    "body": {
                        "content": [
                            {"sectionBreak": {}},
                        ]
                    },
                },
            },
        ]
        desired = reindex_document(
            Document.model_validate({"documentId": "test", "tabs": desired_tabs})
        )

        result = reconcile(base, desired)

        # Must have at least 2 batches
        assert len(result) >= 2

        # Batch 0 must contain createFooter_t0 and addDocumentTab_t1
        assert result[0].requests is not None
        types_0 = [
            next(iter(req.model_dump(by_alias=True, exclude_none=True).keys()))
            for req in result[0].requests
        ]
        assert "createFooter" in types_0
        assert "addDocumentTab" in types_0
        # createFooter must come before addDocumentTab (matched tab processed first)
        assert types_0.index("createFooter") < types_0.index("addDocumentTab")

        # Find the DeferredID embedded in batch 1 that references addDocumentTab.
        # Without the fix, this DeferredID has request_index=2 (out of range for
        # batch 0 which has only 2 replies).
        batch_0_size = len(types_0)  # should be 2
        assert batch_0_size == 2

        # Collect all DeferredIDs in batches 1+
        def _collect_deferred_ids(obj: Any) -> list[DeferredID]:
            """Recursively collect DeferredID objects from a nested structure."""
            ids: list[DeferredID] = []
            if isinstance(obj, DeferredID):
                ids.append(obj)
            elif hasattr(obj, "__dict__"):
                for v in vars(obj).values():
                    ids.extend(_collect_deferred_ids(v))
            elif isinstance(obj, dict):
                for v in obj.values():
                    ids.extend(_collect_deferred_ids(v))
            elif isinstance(obj, list | tuple):
                for item in obj:
                    ids.extend(_collect_deferred_ids(item))
            return ids

        for batch_i, batch in enumerate(result[1:], start=1):
            for deferred in _collect_deferred_ids(batch):
                if deferred.batch_index == 0:
                    assert deferred.request_index < batch_0_size, (
                        f"DeferredID in batch {batch_i} references "
                        f"batch-0 reply[{deferred.request_index}] but batch 0 "
                        f"only has {batch_0_size} replies"
                    )

        # End-to-end: execute batch 0 and batch 1.
        # resolve_deferred_ids raises ReconcileError without the fix.

        base_dict = base.model_dump(by_alias=True, exclude_none=True)
        mock = MockGoogleDocsAPI(base_dict)

        batch_0_reqs = [
            req.model_dump(by_alias=True, exclude_none=True)
            for req in result[0].requests
        ]
        response_0 = mock.batch_update(batch_0_reqs)
        assert len(response_0["replies"]) == batch_0_size

        # This call raises ReconcileError without the fix
        batch_1_resolved = resolve_deferred_ids([response_0], result[1])
        batch_1_reqs = [
            req.model_dump(by_alias=True, exclude_none=True)
            for req in batch_1_resolved.requests
        ]
        mock.batch_update(batch_1_reqs)

        # Verify the footer was correctly populated (the createFooter path works)
        actual = mock.get()
        tab0_doc = actual["tabs"][0]["documentTab"]
        footers = tab0_doc.get("footers", {})
        assert len(footers) == 1
        footer_text = next(iter(footers.values()))["content"][0]["paragraph"][
            "elements"
        ][0]["textRun"]["content"]
        assert footer_text == "Tab1 Footer\n"

        # Tab 2 was created
        assert len(actual["tabs"]) == 2


# ---------------------------------------------------------------------------
# Issue 12: text mismatch in matched paragraph run raises ReconcileError
# ---------------------------------------------------------------------------


def _make_paragraph(text: str, bold: bool | None = None) -> Paragraph:
    """Build a minimal Paragraph with a single text run."""
    text_style: dict[str, Any] = {}
    if bold is not None:
        text_style["bold"] = bold
    el: dict[str, Any] = {"textRun": {"content": text}}
    if text_style:
        el["textRun"]["textStyle"] = text_style
    return Paragraph.model_validate({"elements": [el]})


class TestTextRunMismatchRaisesError:
    """Verify that _generate_text_style_updates raises ReconcileError on text mismatch.

    This guard should never fire in normal operation (matched paragraphs always
    have the same text), but raising instead of silently returning [] surfaces
    upstream alignment bugs immediately.
    """

    def test_different_text_same_run_count_raises(self):
        """Mismatched run text in a matched paragraph raises ReconcileError."""
        base = _make_paragraph("Hello\n", bold=False)
        desired = _make_paragraph("World\n", bold=True)

        with pytest.raises(ReconcileError, match="mismatch"):
            _generate_text_style_updates(base, desired, 1, None, None)

    def test_matching_text_does_not_raise(self):
        """Same text, different style — no error, returns style requests."""
        base = _make_paragraph("Hello\n", bold=False)
        desired = _make_paragraph("Hello\n", bold=True)

        reqs = _generate_text_style_updates(base, desired, 1, None, None)
        assert len(reqs) == 1
        assert "updateTextStyle" in reqs[0]


# ---------------------------------------------------------------------------
# Issue 13: _strip_cell_para_styles is too aggressive
# ---------------------------------------------------------------------------


def _table_doc_dict(cell_para_style: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a raw document dict with a 1x1 table; optional cell paragraphStyle."""
    para: dict[str, Any] = {"elements": [{"textRun": {"content": "Cell\n"}}]}
    if cell_para_style is not None:
        para["paragraphStyle"] = cell_para_style
    return {
        "documentId": "test",
        "tabs": [
            {
                "tabProperties": {"tabId": "t.0"},
                "documentTab": {
                    "body": {
                        "content": [
                            {"sectionBreak": {}},
                            {
                                "table": {
                                    "rows": 1,
                                    "columns": 1,
                                    "tableRows": [
                                        {
                                            "tableCells": [
                                                {"content": [{"paragraph": para}]}
                                            ]
                                        }
                                    ],
                                }
                            },
                        ]
                    }
                },
            }
        ],
    }


class TestDocumentsMatchCellParaStyle:
    """documents_match should detect meaningful cell paragraphStyle differences
    while tolerating mock-generated structural defaults.
    """

    def test_mock_default_para_style_matches_absent(self):
        """Full mock-generated default paragraphStyle compares equal to absent."""
        # Mock generates this for every insertTable cell
        mock_defaults = {
            "namedStyleType": "NORMAL_TEXT",
            "direction": "LEFT_TO_RIGHT",
            "alignment": "START",
            "lineSpacing": 100,
            "spacingMode": "COLLAPSE_LISTS",
            "spaceAbove": {"unit": "PT"},
            "spaceBelow": {"unit": "PT"},
            "keepLinesTogether": False,
            "keepWithNext": False,
            "avoidWidowAndOrphan": False,
            "pageBreakBefore": False,
        }
        actual = _table_doc_dict(mock_defaults)
        desired = _table_doc_dict(None)

        ok, diffs = documents_match(actual, desired)
        assert ok, f"Default paragraphStyle should match absent: {diffs}"

    def test_heading_style_detected(self):
        """Heading paragraphStyle in a cell is detected as different from absent."""
        actual = _table_doc_dict(None)
        desired = _table_doc_dict({"namedStyleType": "HEADING_1"})

        ok, diffs = documents_match(actual, desired)
        assert not ok, "Missing heading in cell should be detected"

    def test_center_alignment_detected(self):
        """Non-default alignment in a cell paragraph is detected as different."""
        actual = _table_doc_dict(None)
        desired = _table_doc_dict({"alignment": "CENTER"})

        ok, diffs = documents_match(actual, desired)
        assert not ok, "Missing CENTER alignment in cell should be detected"

    def test_matching_heading_style_passes(self):
        """Both sides with heading style in a cell compare equal."""
        both = _table_doc_dict({"namedStyleType": "HEADING_2"})

        ok, diffs = documents_match(both, both)
        assert ok, f"Identical heading style should match: {diffs}"

    def test_reconcile_heading_in_cell(self):
        """reconcile() + verify() correctly apply heading style inside a table cell."""
        base_table = {
            "table": {
                "rows": 1,
                "columns": 1,
                "tableRows": [
                    {
                        "tableCells": [
                            {
                                "startIndex": 0,
                                "content": [
                                    {
                                        "paragraph": {
                                            "elements": [
                                                {"textRun": {"content": "Title\n"}}
                                            ]
                                        }
                                    }
                                ],
                            }
                        ]
                    }
                ],
            }
        }
        desired_table = {
            "table": {
                "rows": 1,
                "columns": 1,
                "tableRows": [
                    {
                        "tableCells": [
                            {
                                "startIndex": 0,
                                "content": [
                                    {
                                        "paragraph": {
                                            "paragraphStyle": {
                                                "namedStyleType": "HEADING_1"
                                            },
                                            "elements": [
                                                {"textRun": {"content": "Title\n"}}
                                            ],
                                        }
                                    }
                                ],
                            }
                        ]
                    }
                ],
            }
        }
        base = _make_doc_with_content(base_table)
        desired = _make_doc_with_content(desired_table)

        result = reconcile(base, desired)
        ok, diffs = verify(base, result, desired)
        assert ok, f"Heading style in table cell should be applied: {diffs}"


# ---------------------------------------------------------------------------
# Issue 14: documents_match must not be in the public API
# ---------------------------------------------------------------------------


class TestIssue14DocumentsMatchNotPublic:
    """Issue 14: documents_match is an internal utility and must not be exported."""

    def test_not_in_all(self):
        """documents_match is not in reconcile.__all__."""
        import extradoc.reconcile as reconcile_module

        assert "documents_match" not in reconcile_module.__all__

    def test_not_directly_importable_from_reconcile(self):
        """documents_match cannot be imported directly from extradoc.reconcile."""
        import importlib

        m = importlib.import_module("extradoc.reconcile")
        assert not hasattr(m, "documents_match")

    def test_still_importable_from_comparators(self):
        """documents_match remains usable from _comparators for internal use."""
        from extradoc.reconcile._comparators import documents_match

        assert callable(documents_match)


# ---------------------------------------------------------------------------
# Issue 15: Multi-paragraph cells lose structure (silent failure)
# ---------------------------------------------------------------------------


def _make_multi_para_cell_table(
    paras: list[dict[str, Any]], start_index: bool = True
) -> dict[str, Any]:
    """Build a table with one row and one cell containing multiple paragraphs."""
    cell: dict[str, Any] = {"content": paras}
    if start_index:
        cell["startIndex"] = 0
    return {
        "table": {
            "rows": 1,
            "columns": 1,
            "tableRows": [{"tableCells": [cell]}],
        }
    }


class TestIssue15MultiParagraphCells:
    """Issue 15: Multi-paragraph cells with non-default styles raise ReconcileError."""

    def test_plain_two_para_cell_populate_works(self):
        """Populating a cell with two plain-text paragraphs preserves structure.

        insertText with embedded \\n correctly creates paragraph breaks.
        No ReconcileError should be raised for plain-text multi-paragraph cells.
        """
        base = _make_doc_with_content("Intro", _make_table([["Old"]]))
        desired_table = _make_multi_para_cell_table(
            [
                {"paragraph": {"elements": [{"textRun": {"content": "Line 1\n"}}]}},
                {"paragraph": {"elements": [{"textRun": {"content": "Line 2\n"}}]}},
            ]
        )
        desired = _make_doc_with_content("Intro", desired_table)
        result = reconcile(base, desired)
        ok, diffs = verify(base, result, desired)
        assert ok, f"Plain multi-paragraph cell should be reconciled correctly: {diffs}"

    def test_multi_para_cell_with_heading_style_raises_error(self):
        """A desired cell with multiple paragraphs and a heading style raises ReconcileError.

        The reconciler inserts combined text via insertText, which loses per-paragraph
        styles. This must raise an error instead of silently producing wrong output.
        """
        base = _make_doc_with_content("Intro", _make_table([["Old"]]))
        desired_table = _make_multi_para_cell_table(
            [
                {
                    "paragraph": {
                        "paragraphStyle": {"namedStyleType": "HEADING_1"},
                        "elements": [{"textRun": {"content": "Heading\n"}}],
                    }
                },
                {"paragraph": {"elements": [{"textRun": {"content": "Body\n"}}]}},
            ]
        )
        desired = _make_doc_with_content("Intro", desired_table)

        with pytest.raises(ReconcileError, match="[Mm]ulti-paragraph"):
            reconcile(base, desired)

    def test_diff_cell_with_heading_style_in_second_para_raises_error(self):
        """Diffing a matched cell where desired has two paras and a heading raises error."""
        # Build a 1x2 table: base col 0 and desired col 0 have same column fingerprint
        # (same per-column text when stripped), but desired cell has non-default para style.
        # The easiest way to trigger _diff_single_cell_at with multi-para desired is
        # to have the tables differ structurally but ensure _populate_cell_at is invoked.
        base_table = _make_table([["A", "B"]])
        # desired: same col 1 ("B") but col 0 has two paragraphs with heading style
        desired_table = _make_multi_para_cell_table(
            [
                {
                    "paragraph": {
                        "paragraphStyle": {"namedStyleType": "HEADING_2"},
                        "elements": [{"textRun": {"content": "A\n"}}],
                    }
                },
                {"paragraph": {"elements": [{"textRun": {"content": "Extra\n"}}]}},
            ]
        )
        # Use single-column desired so we stay in the 1-col path
        base = _make_doc_with_content("Start", base_table)
        desired = _make_doc_with_content("Start", desired_table)

        with pytest.raises(ReconcileError, match="[Mm]ulti-paragraph"):
            reconcile(base, desired)


# ---------------------------------------------------------------------------
# Issue 16: Nested tables invisible — content_fingerprint always "T:table"
# ---------------------------------------------------------------------------


class TestIssue16TableFingerprint:
    """Issue 16: content_fingerprint must distinguish tables by content."""

    def test_different_tables_have_different_fingerprints(self):
        """Two tables with different cell content must have different fingerprints."""
        from extradoc.api_types._generated import StructuralElement
        from extradoc.reconcile._extractors import content_fingerprint

        t1 = StructuralElement.model_validate(
            {
                "table": {
                    "rows": 1,
                    "columns": 1,
                    "tableRows": [
                        {
                            "tableCells": [
                                {
                                    "content": [
                                        {
                                            "paragraph": {
                                                "elements": [
                                                    {"textRun": {"content": "Alpha\n"}}
                                                ]
                                            }
                                        }
                                    ]
                                }
                            ]
                        }
                    ],
                }
            }
        )
        t2 = StructuralElement.model_validate(
            {
                "table": {
                    "rows": 1,
                    "columns": 1,
                    "tableRows": [
                        {
                            "tableCells": [
                                {
                                    "content": [
                                        {
                                            "paragraph": {
                                                "elements": [
                                                    {"textRun": {"content": "Beta\n"}}
                                                ]
                                            }
                                        }
                                    ]
                                }
                            ]
                        }
                    ],
                }
            }
        )
        fp1 = content_fingerprint(t1)
        fp2 = content_fingerprint(t2)
        assert fp1 != fp2, (
            "Tables with different content must have different fingerprints, "
            f"but both got: {fp1!r}"
        )
        assert fp1.startswith("T:")
        assert fp2.startswith("T:")

    def test_same_tables_have_same_fingerprint(self):
        """Two tables with identical content have the same fingerprint."""
        from extradoc.api_types._generated import StructuralElement
        from extradoc.reconcile._extractors import content_fingerprint

        table_dict = {
            "table": {
                "rows": 1,
                "columns": 1,
                "tableRows": [
                    {
                        "tableCells": [
                            {
                                "content": [
                                    {
                                        "paragraph": {
                                            "elements": [
                                                {"textRun": {"content": "Same\n"}}
                                            ]
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                ],
            }
        }
        t = StructuralElement.model_validate(table_dict)
        assert content_fingerprint(t) == content_fingerprint(t)

    def test_two_tables_aligned_correctly(self):
        """Two distinct tables are aligned with their correct counterparts."""
        t1 = _make_table([["First"]])
        t2 = _make_table([["Second"]])
        t1_new = _make_table([["First Modified"]])
        t2_new = _make_table([["Second Modified"]])

        base = _make_doc_with_content("Start", t1, "Mid", t2, "End")
        desired = _make_doc_with_content("Start", t1_new, "Mid", t2_new, "End")
        result = reconcile(base, desired)
        ok, diffs = verify(base, result, desired)
        assert ok, f"Two tables should be modified independently: {diffs}"


# ---------------------------------------------------------------------------
# Issue 17: tableCellStyle changes silently ignored
# ---------------------------------------------------------------------------


def _make_table_with_cell_style(
    cell_text: str,
    cell_style: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a 1x1 table with optional tableCellStyle on the single cell."""
    cell: dict[str, Any] = {
        "startIndex": 0,
        "content": [
            {"paragraph": {"elements": [{"textRun": {"content": cell_text + "\n"}}]}}
        ],
    }
    if cell_style is not None:
        cell["tableCellStyle"] = cell_style
    return {
        "table": {
            "rows": 1,
            "columns": 1,
            "tableRows": [{"tableCells": [cell]}],
        }
    }


class TestIssue17TableCellStyleSilentFailure:
    """Issue 17: tableCellStyle changes must raise ReconcileError, not be silently ignored."""

    def test_table_cell_style_change_raises_error(self):
        """Changing tableCellStyle must raise ReconcileError."""
        base_table = _make_table_with_cell_style(
            "Cell",
            {"backgroundColor": {"color": {"rgbColor": {"red": 1.0}}}},
        )
        desired_table = _make_table_with_cell_style(
            "Cell",
            {"backgroundColor": {"color": {"rgbColor": {"green": 1.0}}}},
        )
        base = _make_doc_with_content("Hello", base_table)
        desired = _make_doc_with_content("Hello", desired_table)

        with pytest.raises(ReconcileError, match="[Tt]able[Cc]ell[Ss]tyle"):
            reconcile(base, desired)

    def test_table_cell_style_added_raises_error(self):
        """Adding tableCellStyle to a cell that previously had none raises ReconcileError."""
        base_table = _make_table_with_cell_style("Cell", None)
        desired_table = _make_table_with_cell_style(
            "Cell",
            {"backgroundColor": {"color": {"rgbColor": {"blue": 1.0}}}},
        )
        base = _make_doc_with_content("Hello", base_table)
        desired = _make_doc_with_content("Hello", desired_table)

        with pytest.raises(ReconcileError, match="[Tt]able[Cc]ell[Ss]tyle"):
            reconcile(base, desired)

    def test_identical_table_cell_style_no_error(self):
        """Identical tableCellStyle in both base and desired does not raise."""
        style = {"backgroundColor": {"color": {"rgbColor": {"red": 0.5}}}}
        table = _make_table_with_cell_style("Cell", style)
        base = _make_doc_with_content("Hello", table)
        desired = _make_doc_with_content("Hello", table)

        # Must not raise
        result = reconcile(base, desired)
        assert result is not None

    def test_no_cell_style_no_error(self):
        """Cells without tableCellStyle work normally."""
        base = _make_doc_with_content("Hello", _make_table([["Cell"]]))
        desired = _make_doc_with_content("Hello", _make_table([["New Cell"]]))
        result = reconcile(base, desired)
        ok, diffs = verify(base, result, desired)
        assert ok, f"Tables without tableCellStyle should reconcile: {diffs}"


# ---------------------------------------------------------------------------
# Issue 18: Section-specific headers/footers silently wrong
# ---------------------------------------------------------------------------


def _make_two_section_doc_with_new_header(
    header_text: str,
) -> Document:
    """Build a two-section document with a header that needs sectionBreakLocation."""
    body_content: list[dict] = [
        {"sectionBreak": {}},  # initial section break
        {"paragraph": {"elements": [{"textRun": {"content": "Section 1\n"}}]}},
        {"sectionBreak": {"sectionStyle": {"sectionType": "NEXT_PAGE"}}},
        {"paragraph": {"elements": [{"textRun": {"content": "Section 2\n"}}]}},
    ]
    if not header_text.endswith("\n"):
        header_text = header_text + "\n"
    doc = Document.model_validate(
        {
            "documentId": "test",
            "tabs": [
                {
                    "tabProperties": {"tabId": "t.0"},
                    "documentTab": {
                        "body": {"content": body_content},
                        "headers": {
                            "hdr_new": {
                                "headerId": "hdr_new",
                                "content": [
                                    {
                                        "paragraph": {
                                            "elements": [
                                                {"textRun": {"content": header_text}}
                                            ]
                                        }
                                    }
                                ],
                            }
                        },
                    },
                }
            ],
        }
    )
    return reindex_document(doc)


class TestIssue18SectionSpecificHeaders:
    """Issue 18: Creating headers/footers in multi-section documents raises ReconcileError."""

    def test_create_header_in_single_section_doc_works(self):
        """Creating a new header in a single-section document works normally."""
        base = _make_doc("Body")
        desired = _make_doc_with_header("hdr1", "My Header", "Body")

        # Must not raise for single-section documents
        result = reconcile(base, desired)
        assert len(result) == 2  # batch 0: createHeader, batch 1: insertText

    def test_create_header_in_multi_section_doc_raises_error(self):
        """Creating a new header in a multi-section document raises ReconcileError.

        The createHeader request always omits sectionBreakLocation, which applies
        the header to all sections. In a multi-section document, this may produce
        incorrect results, so reconcile() rejects it loudly.
        """
        base = reindex_document(
            Document.model_validate(
                {
                    "documentId": "test",
                    "tabs": [
                        {
                            "tabProperties": {"tabId": "t.0"},
                            "documentTab": {
                                "body": {
                                    "content": [
                                        {"sectionBreak": {}},
                                        {
                                            "paragraph": {
                                                "elements": [
                                                    {
                                                        "textRun": {
                                                            "content": "Section 1\n"
                                                        }
                                                    }
                                                ]
                                            }
                                        },
                                        {
                                            "sectionBreak": {
                                                "sectionStyle": {
                                                    "sectionType": "NEXT_PAGE"
                                                }
                                            }
                                        },
                                        {
                                            "paragraph": {
                                                "elements": [
                                                    {
                                                        "textRun": {
                                                            "content": "Section 2\n"
                                                        }
                                                    }
                                                ]
                                            }
                                        },
                                    ]
                                }
                            },
                        }
                    ],
                }
            )
        )
        desired = _make_two_section_doc_with_new_header("New Header")

        with pytest.raises(ReconcileError, match="[Ss]ection"):
            reconcile(base, desired)

    def test_modify_existing_header_in_multi_section_doc_works(self):
        """Modifying an existing header in a multi-section document is allowed.

        The header already exists (same ID in base and desired), so no
        createHeader request is needed — only content diffing.
        """
        two_section_body: list[dict] = [
            {"sectionBreak": {}},
            {"paragraph": {"elements": [{"textRun": {"content": "Section 1\n"}}]}},
            {"sectionBreak": {"sectionStyle": {"sectionType": "NEXT_PAGE"}}},
            {"paragraph": {"elements": [{"textRun": {"content": "Section 2\n"}}]}},
        ]
        base = reindex_document(
            Document.model_validate(
                {
                    "documentId": "test",
                    "tabs": [
                        {
                            "tabProperties": {"tabId": "t.0"},
                            "documentTab": {
                                "body": {"content": two_section_body},
                                "headers": {
                                    "hdr1": {
                                        "headerId": "hdr1",
                                        "content": [
                                            {
                                                "paragraph": {
                                                    "elements": [
                                                        {
                                                            "textRun": {
                                                                "content": "Old Header\n"
                                                            }
                                                        }
                                                    ]
                                                }
                                            }
                                        ],
                                    }
                                },
                            },
                        }
                    ],
                }
            )
        )
        desired = reindex_document(
            Document.model_validate(
                {
                    "documentId": "test",
                    "tabs": [
                        {
                            "tabProperties": {"tabId": "t.0"},
                            "documentTab": {
                                "body": {"content": two_section_body},
                                "headers": {
                                    "hdr1": {
                                        "headerId": "hdr1",
                                        "content": [
                                            {
                                                "paragraph": {
                                                    "elements": [
                                                        {
                                                            "textRun": {
                                                                "content": "New Header\n"
                                                            }
                                                        }
                                                    ]
                                                }
                                            }
                                        ],
                                    }
                                },
                            },
                        }
                    ],
                }
            )
        )

        # Modifying existing header (same ID) must NOT raise
        result = reconcile(base, desired)
        assert result is not None


# ---------------------------------------------------------------------------
# Helpers for Issue 8 bullet preset tests
# ---------------------------------------------------------------------------

# Glyph symbols for each unordered preset (matching mock/bullet_ops.py)
_PRESET_GLYPH_SYMBOLS: dict[str, list[str]] = {
    "BULLET_DISC_CIRCLE_SQUARE": ["●", "○", "■"],
    "BULLET_DIAMONDX_ARROW3D_SQUARE": ["❖", "➢", "■"],
    "BULLET_CHECKBOX": ["☐", "☐", "☐"],
    "BULLET_ARROW_DIAMOND_DISC": ["➔", "◆", "●"],
    "BULLET_STAR_CIRCLE_SQUARE": ["★", "○", "■"],
}


def _make_nesting_levels_for_preset(preset: str) -> list[dict[str, Any]]:
    """Build nesting level dicts that match the real API output for a given preset.

    Unordered presets get glyphSymbol; numbered presets get the appropriate
    glyphType per level; BULLET_CHECKBOX gets GLYPH_TYPE_UNSPECIFIED.
    """
    is_numbered = preset.startswith("NUMBERED_")
    is_checkbox = preset == "BULLET_CHECKBOX"
    glyphs = _PRESET_GLYPH_SYMBOLS.get(preset, ["●", "○", "■"])

    # Numbered glyph types: level-0 glyph type per preset (real API, not mock simplified)
    _NUMBERED_LEVEL0_GLYPH: dict[str, str] = {
        "NUMBERED_DECIMAL_NESTED": "DECIMAL",
        "NUMBERED_DECIMAL_ALPHA_ROMAN": "DECIMAL",
        "NUMBERED_DECIMAL_ALPHA_ROMAN_PARENS": "DECIMAL",
        "NUMBERED_UPPERALPHA_ALPHA_ROMAN": "UPPER_ALPHA",
        "NUMBERED_UPPERROMAN_UPPERALPHA_DECIMAL": "UPPER_ROMAN",
        "NUMBERED_ZERODECIMAL_ALPHA_ROMAN": "ZERO_DECIMAL",
    }

    levels = []
    for i in range(9):
        lvl: dict[str, Any] = {
            "bulletAlignment": "START",
            "indentFirstLine": {"magnitude": 18 + i * 36, "unit": "PT"},
            "indentStart": {"magnitude": 36 + i * 36, "unit": "PT"},
            "textStyle": {"underline": False},
            "startNumber": 1,
            "glyphFormat": f"%{i}.",
        }
        if is_numbered:
            level0_type = _NUMBERED_LEVEL0_GLYPH.get(preset, "DECIMAL")
            lvl["glyphType"] = level0_type if i == 0 else "DECIMAL"
        elif is_checkbox:
            lvl["glyphType"] = "GLYPH_TYPE_UNSPECIFIED"
        else:
            lvl["glyphSymbol"] = glyphs[i % len(glyphs)]
        levels.append(lvl)
    return levels


def _make_doc_with_preset_bullet(
    text: str,
    preset: str,
    *,
    tab_id: str = "t.0",
) -> Document:
    """Create a Document with a bulleted paragraph using the given preset's nesting structure.

    The nesting levels are built to match the real API's list structure for the preset,
    so _infer_bullet_preset can correctly identify the preset from the desired document.
    """
    if not text.endswith("\n"):
        text = text + "\n"
    nesting_levels = _make_nesting_levels_for_preset(preset)
    doc = Document.model_validate(
        {
            "documentId": "test",
            "tabs": [
                {
                    "tabProperties": {"tabId": tab_id},
                    "documentTab": {
                        "body": {
                            "content": [
                                {"sectionBreak": {}},
                                {
                                    "paragraph": {
                                        "elements": [{"textRun": {"content": text}}],
                                        "bullet": {"listId": "list1"},
                                        "paragraphStyle": {
                                            "indentFirstLine": {
                                                "magnitude": 18,
                                                "unit": "PT",
                                            },
                                            "indentStart": {
                                                "magnitude": 36,
                                                "unit": "PT",
                                            },
                                        },
                                    }
                                },
                            ]
                        },
                        "lists": {
                            "list1": {
                                "listProperties": {"nestingLevels": nesting_levels}
                            }
                        },
                    },
                }
            ],
        }
    )
    return reindex_document(doc)


def _get_bullet_preset_from_result(result: Any) -> str | None:
    """Extract the bulletPreset from the first createParagraphBullets request."""
    for batch in result:
        for req in batch.requests or []:
            d = req.model_dump(by_alias=True, exclude_none=True)
            if "createParagraphBullets" in d:
                return d["createParagraphBullets"].get("bulletPreset")
    return None


def _make_list(glyph_type: str | None = None, glyph_symbol: str | None = None) -> List:
    """Build a List object with one nesting level for unit-testing _infer_bullet_preset."""
    lvl_data: dict[str, Any] = {}
    if glyph_type is not None:
        lvl_data["glyphType"] = glyph_type
    if glyph_symbol is not None:
        lvl_data["glyphSymbol"] = glyph_symbol
    return List.model_validate({"listProperties": {"nestingLevels": [lvl_data]}})


# ---------------------------------------------------------------------------
# Issue 8: Bullet preset is hardcoded
# ---------------------------------------------------------------------------


class TestInferBulletPreset:
    """Unit tests for _infer_bullet_preset — tests the mapping logic directly."""

    def test_none_list_id_returns_default(self):
        lists = {"list1": _make_list(glyph_symbol="●")}
        assert _infer_bullet_preset(None, lists) == "BULLET_DISC_CIRCLE_SQUARE"

    def test_none_lists_returns_default(self):
        assert _infer_bullet_preset("list1", None) == "BULLET_DISC_CIRCLE_SQUARE"

    def test_missing_list_id_returns_default(self):
        lists = {"list1": _make_list(glyph_symbol="●")}
        assert (
            _infer_bullet_preset("list_MISSING", lists) == "BULLET_DISC_CIRCLE_SQUARE"
        )

    def test_no_nesting_levels_returns_default(self):
        lst = List.model_validate({"listProperties": {"nestingLevels": []}})
        assert (
            _infer_bullet_preset("list1", {"list1": lst}) == "BULLET_DISC_CIRCLE_SQUARE"
        )

    def test_no_list_properties_returns_default(self):
        lst = List.model_validate({})
        assert (
            _infer_bullet_preset("list1", {"list1": lst}) == "BULLET_DISC_CIRCLE_SQUARE"
        )

    def test_disc_symbol_returns_disc_preset(self):
        lists = {"list1": _make_list(glyph_symbol="●")}
        assert _infer_bullet_preset("list1", lists) == "BULLET_DISC_CIRCLE_SQUARE"

    def test_diamond_symbol_returns_diamond_preset(self):
        lists = {"list1": _make_list(glyph_symbol="❖")}
        assert _infer_bullet_preset("list1", lists) == "BULLET_DIAMONDX_ARROW3D_SQUARE"

    def test_arrow_symbol_returns_arrow_preset(self):
        lists = {"list1": _make_list(glyph_symbol="➔")}
        assert _infer_bullet_preset("list1", lists) == "BULLET_ARROW_DIAMOND_DISC"

    def test_star_symbol_returns_star_preset(self):
        lists = {"list1": _make_list(glyph_symbol="★")}
        assert _infer_bullet_preset("list1", lists) == "BULLET_STAR_CIRCLE_SQUARE"

    def test_decimal_glyph_type_returns_decimal_preset(self):
        lists = {"list1": _make_list(glyph_type="DECIMAL")}
        assert _infer_bullet_preset("list1", lists) == "NUMBERED_DECIMAL_NESTED"

    def test_upper_alpha_glyph_type_returns_upper_alpha_preset(self):
        lists = {"list1": _make_list(glyph_type="UPPER_ALPHA")}
        assert _infer_bullet_preset("list1", lists) == "NUMBERED_UPPERALPHA_ALPHA_ROMAN"

    def test_upper_roman_glyph_type_returns_upper_roman_preset(self):
        lists = {"list1": _make_list(glyph_type="UPPER_ROMAN")}
        assert (
            _infer_bullet_preset("list1", lists)
            == "NUMBERED_UPPERROMAN_UPPERALPHA_DECIMAL"
        )

    def test_alpha_glyph_type_returns_alpha_preset(self):
        lists = {"list1": _make_list(glyph_type="ALPHA")}
        assert _infer_bullet_preset("list1", lists) == "NUMBERED_DECIMAL_ALPHA_ROMAN"

    def test_zero_decimal_glyph_type_returns_zero_decimal_preset(self):
        lists = {"list1": _make_list(glyph_type="ZERO_DECIMAL")}
        assert (
            _infer_bullet_preset("list1", lists) == "NUMBERED_ZERODECIMAL_ALPHA_ROMAN"
        )

    def test_glyph_type_unspecified_returns_checkbox_preset(self):
        lists = {"list1": _make_list(glyph_type="GLYPH_TYPE_UNSPECIFIED")}
        assert _infer_bullet_preset("list1", lists) == "BULLET_CHECKBOX"

    def test_none_glyph_type_with_no_symbol_returns_default(self):
        """No glyphType, no glyphSymbol → fall back to default."""
        lst = List.model_validate({"listProperties": {"nestingLevels": [{}]}})
        assert (
            _infer_bullet_preset("list1", {"list1": lst}) == "BULLET_DISC_CIRCLE_SQUARE"
        )


class TestReconcileBulletPreset:
    """Integration tests: reconcile picks the correct bulletPreset from the desired document."""

    def test_disc_bullet_uses_disc_preset(self):
        """Adding a disc bullet → preset BULLET_DISC_CIRCLE_SQUARE."""
        base = _make_doc("Hello")
        desired = _make_doc_with_preset_bullet("Hello", "BULLET_DISC_CIRCLE_SQUARE")
        result = reconcile(base, desired)
        preset = _get_bullet_preset_from_result(result)
        assert preset == "BULLET_DISC_CIRCLE_SQUARE"
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_diamond_bullet_uses_diamond_preset(self):
        """Adding a diamond bullet → preset BULLET_DIAMONDX_ARROW3D_SQUARE."""
        base = _make_doc("Hello")
        desired = _make_doc_with_preset_bullet(
            "Hello", "BULLET_DIAMONDX_ARROW3D_SQUARE"
        )
        result = reconcile(base, desired)
        preset = _get_bullet_preset_from_result(result)
        assert preset == "BULLET_DIAMONDX_ARROW3D_SQUARE"
        ok, diffs = verify(base, result, desired)
        assert ok, f"Diffs: {diffs}"

    def test_numbered_decimal_uses_decimal_preset(self):
        """Adding a numbered decimal list → preset NUMBERED_DECIMAL_NESTED."""
        base = _make_doc("Hello")
        desired = _make_doc_with_preset_bullet("Hello", "NUMBERED_DECIMAL_NESTED")
        result = reconcile(base, desired)
        preset = _get_bullet_preset_from_result(result)
        assert preset == "NUMBERED_DECIMAL_NESTED"
        # Note: verify() skipped — mock simplifies numbered glyphType to DECIMAL
        # for all presets, so round-trip comparison would diverge on glyphType fields.

    def test_upper_alpha_uses_upper_alpha_preset(self):
        """Adding an upper-alpha list → preset NUMBERED_UPPERALPHA_ALPHA_ROMAN."""
        base = _make_doc("Hello")
        desired = _make_doc_with_preset_bullet(
            "Hello", "NUMBERED_UPPERALPHA_ALPHA_ROMAN"
        )
        result = reconcile(base, desired)
        preset = _get_bullet_preset_from_result(result)
        assert preset == "NUMBERED_UPPERALPHA_ALPHA_ROMAN"

    def test_no_lists_dict_falls_back_to_disc(self):
        """Desired bullet references a list_id not in the lists dict → disc fallback."""
        base = _make_doc("Hello")
        # Build desired without a matching lists entry
        desired = Document.model_validate(
            {
                "documentId": "test",
                "tabs": [
                    {
                        "tabProperties": {"tabId": "t.0"},
                        "documentTab": {
                            "body": {
                                "content": [
                                    {"sectionBreak": {}},
                                    {
                                        "paragraph": {
                                            "elements": [
                                                {"textRun": {"content": "Hello\n"}}
                                            ],
                                            "bullet": {"listId": "orphan_list"},
                                            "paragraphStyle": {
                                                "indentFirstLine": {
                                                    "magnitude": 18,
                                                    "unit": "PT",
                                                },
                                                "indentStart": {
                                                    "magnitude": 36,
                                                    "unit": "PT",
                                                },
                                            },
                                        }
                                    },
                                ]
                            },
                            # No "lists" key — or lists missing "orphan_list"
                        },
                    }
                ],
            }
        )
        desired = reindex_document(desired)
        result = reconcile(base, desired)
        preset = _get_bullet_preset_from_result(result)
        assert preset == "BULLET_DISC_CIRCLE_SQUARE"
