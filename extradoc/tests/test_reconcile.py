"""Tests for the reconcile module.

Phase 1: paragraph text in body.
Phase 2: tables (body only).
Phase 3: multi-segment (headers, footers, footnotes).
Phase 4: multi-tab.
"""

from typing import Any

from extradoc.api_types import DeferredID
from extradoc.api_types._generated import Document
from extradoc.reconcile import reconcile, reindex_document, verify


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
        from extradoc.mock.api import MockGoogleDocsAPI
        from extradoc.reconcile._core import resolve_deferred_ids

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
        from extradoc.mock.api import MockGoogleDocsAPI
        from extradoc.reconcile._core import resolve_deferred_ids

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
        """Create a new tab.

        NOTE: Phase 4 implementation creates an empty tab (not populated).
        This test verifies that the addDocumentTab request is generated.
        Full content population will be implemented in Phase 5+.
        """
        base = _make_multi_tab_doc([("t.0", "Tab 1", ["First tab content"])])
        desired = _make_multi_tab_doc(
            [
                ("t.0", "Tab 1", ["First tab content"]),
                ("t.1", "Tab 2", ["Second tab content"]),
            ]
        )

        result = reconcile(base, desired)
        assert len(result) == 1 and result[0].requests is not None
        # Check that we have an addDocumentTab request
        request_types = [
            next(iter(req.model_dump(by_alias=True, exclude_none=True).keys()))
            for req in result[0].requests
        ]
        assert "addDocumentTab" in request_types
        # Note: verify() will fail because content isn't populated
        # This is expected for Phase 4 partial implementation

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
