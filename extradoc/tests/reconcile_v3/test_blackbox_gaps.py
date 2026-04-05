"""Blackbox gap tests for reconcile_v3.

These tests use ONLY the public interface:
  - reconcile_batches(base, desired) -> list[BatchUpdateDocumentRequest]
  - reconcile(base, desired) -> list[Request]

Each test constructs base and desired Document objects, runs reconcile, and
asserts on the generated requests. Tests marked xfail expose known gaps
where the reconciler is expected to fail or produce incorrect results.

Organized by gap category:
  1. Newline handling
  2. No delete+re-insert for matched paragraphs
  3. Deferred IDs — multi-structural creation
  4. UTF-16 index arithmetic
  5. Complex table scenarios
  6. Paragraph element types (footnote refs, inline objects, etc.)
  7. Multi-tab scenarios
  8. Header/footer content editing
  9. Section break preservation
"""

from __future__ import annotations

from typing import Any

import pytest

from extradoc.api_types._generated import (
    BatchUpdateDocumentRequest,
    Body,
    Bullet,
    Dimension,
    Document,
    DocumentTab,
    EmbeddedObject,
    Footer,
    Footnote,
    FootnoteReference,
    Header,
    HorizontalRule,
    InlineObject,
    InlineObjectElement,
    InlineObjectProperties,
    ListProperties,
    NamedStyles,
    NestingLevel,
    Paragraph,
    ParagraphElement,
    ParagraphStyle,
    RichLink,
    RichLinkProperties,
    SectionBreak,
    SectionStyle,
    StructuralElement,
    Tab,
    Table,
    TableCell,
    TableRow,
    TabProperties,
    TextRun,
    TextStyle,
)
from extradoc.api_types._generated import (
    List as DocList,
)
from extradoc.reconcile_v3.api import reconcile_batches

# ---------------------------------------------------------------------------
# Helpers — document builders (only use public types, no internal imports)
# ---------------------------------------------------------------------------


def _para(text: str, style: str = "NORMAL_TEXT", **kw: Any) -> StructuralElement:
    """Build a paragraph StructuralElement."""
    return StructuralElement(
        paragraph=Paragraph(
            elements=[ParagraphElement(text_run=TextRun(content=text))],
            paragraph_style=ParagraphStyle(named_style_type=style),
            **kw,
        )
    )


def _indexed_para(
    text: str, start: int, style: str = "NORMAL_TEXT", **kw: Any
) -> StructuralElement:
    """Build a paragraph with explicit start/end indices."""
    from extradoc.indexer import utf16_len

    end = start + utf16_len(text)
    return StructuralElement(
        start_index=start,
        end_index=end,
        paragraph=Paragraph(
            elements=[ParagraphElement(text_run=TextRun(content=text))],
            paragraph_style=ParagraphStyle(named_style_type=style),
            **kw,
        ),
    )


def _multi_run_para(
    runs: list[tuple[str, TextStyle | None]], start: int, style: str = "NORMAL_TEXT"
) -> StructuralElement:
    """Build a paragraph with multiple text runs and explicit indices."""
    from extradoc.indexer import utf16_len

    elements = []
    for text, ts in runs:
        elements.append(ParagraphElement(text_run=TextRun(content=text, text_style=ts)))
    total_len = sum(utf16_len(t) for t, _ in runs)
    return StructuralElement(
        start_index=start,
        end_index=start + total_len,
        paragraph=Paragraph(
            elements=elements,
            paragraph_style=ParagraphStyle(named_style_type=style),
        ),
    )


def _terminal(start: int | None = None) -> StructuralElement:
    """Build the terminal paragraph (trailing newline)."""
    if start is not None:
        return _indexed_para("\n", start)
    return _para("\n")


def _table(rows: list[list[str]]) -> StructuralElement:
    """Build a table StructuralElement (no indices)."""
    table_rows = []
    for row_texts in rows:
        cells = [TableCell(content=[_para(t), _terminal()]) for t in row_texts]
        table_rows.append(TableRow(table_cells=cells))
    return StructuralElement(
        table=Table(
            table_rows=table_rows,
            columns=len(rows[0]) if rows else 0,
            rows=len(rows),
        )
    )


def _indexed_table(rows: list[list[str]], start: int) -> StructuralElement:
    """Build a table with explicit indices (simplified — uniform cell sizes)."""
    from extradoc.indexer import utf16_len

    table_rows = []
    cursor = start + 1  # table opener
    for row_texts in rows:
        cursor += 1  # row opener
        cells = []
        for text in row_texts:
            cell_start = cursor + 1  # cell opener
            para_start = cell_start
            para_end = para_start + utf16_len(text)
            term_end = para_end + 1  # terminal \n
            cells.append(
                TableCell(
                    content=[
                        _indexed_para(text, para_start),
                        _indexed_para("\n", para_end),
                    ],
                    start_index=cursor,
                    end_index=term_end,
                )
            )
            cursor = term_end
        table_rows.append(
            TableRow(
                table_cells=cells,
                start_index=cursor
                - sum(
                    utf16_len(t) + 3
                    for t in row_texts  # approximate
                ),
            )
        )
    end = cursor
    return StructuralElement(
        start_index=start,
        end_index=end,
        table=Table(
            table_rows=table_rows,
            columns=len(rows[0]) if rows else 0,
            rows=len(rows),
        ),
    )


def _tab(
    tab_id: str,
    body_content: list[StructuralElement],
    headers: dict[str, Header] | None = None,
    footers: dict[str, Footer] | None = None,
    footnotes: dict[str, Footnote] | None = None,
    lists: dict[str, Any] | None = None,
    document_style: dict[str, Any] | None = None,
    inline_objects: dict[str, Any] | None = None,
) -> Tab:
    return Tab(
        tab_properties=TabProperties(tab_id=tab_id, title="Tab", index=0),
        document_tab=DocumentTab(
            body=Body(content=body_content),
            headers=headers or {},
            footers=footers or {},
            footnotes=footnotes or {},
            lists=lists or {},
            named_styles=NamedStyles(styles=[]),
            document_style=document_style or {},
            inline_objects=inline_objects or {},
        ),
    )


def _doc(*tabs: Tab) -> Document:
    return Document(document_id="test_doc", tabs=list(tabs))


def _single_doc(body_content: list[StructuralElement], **kwargs: Any) -> Document:
    """Convenience: single-tab document."""
    return _doc(_tab("t1", body_content, **kwargs))


def _collect_request_types(batches: list[BatchUpdateDocumentRequest]) -> list[str]:
    """Extract all request type names from batches."""
    types = []
    for batch in batches:
        for req in batch.requests or []:
            d = req.model_dump(by_alias=True, exclude_none=True)
            types.extend(d.keys())
    return types


def _get_requests_of_type(
    batches: list[BatchUpdateDocumentRequest], req_type: str
) -> list[Any]:
    """Extract all requests of a given type from batches."""
    results = []
    for batch in batches:
        for req in batch.requests or []:
            val = getattr(req, req_type, None)
            if val is not None:
                results.append(val)
    return results


def _flat_requests(batches: list[BatchUpdateDocumentRequest]) -> list[Any]:
    """Flatten all requests from all batches."""
    reqs = []
    for batch in batches:
        reqs.extend(batch.requests or [])
    return reqs


# ===========================================================================
# 1. Newline handling
# ===========================================================================


class TestNewlineHandling:
    """Terminal newline must never be deleted or inserted as a standalone op."""

    def test_terminal_paragraph_never_deleted(self) -> None:
        """When all content is removed, terminal paragraph must survive."""
        base = _single_doc(
            [
                _indexed_para("Hello\n", 1),
                _indexed_para("World\n", 7),
                _terminal(13),
            ]
        )
        desired = _single_doc([_terminal(1)])

        batches = reconcile_batches(base, desired)
        reqs = _flat_requests(batches)

        # Should delete "Hello\n" and "World\n" but NOT the terminal
        delete_reqs = [r for r in reqs if r.delete_content_range is not None]
        for dr in delete_reqs:
            rng = dr.delete_content_range.range
            # Terminal is at index 13 in base, after deletes at index 1
            # The delete should NOT cover the terminal paragraph
            assert rng.end_index <= 13, (
                f"Delete range {rng.start_index}-{rng.end_index} covers terminal"
            )

    def test_empty_paragraph_insertion(self) -> None:
        """Inserting an empty paragraph (just \\n) between content paragraphs."""
        base = _single_doc(
            [
                _indexed_para("First\n", 1),
                _terminal(7),
            ]
        )
        desired = _single_doc(
            [
                _para("First\n"),
                _para("\n"),
                _terminal(),
            ]
        )

        batches = reconcile_batches(base, desired)
        reqs = _flat_requests(batches)

        # Should produce an insertText for "\n"
        insert_reqs = [r for r in reqs if r.insert_text is not None]
        assert len(insert_reqs) >= 1
        # The inserted text should be just "\n"
        texts = [r.insert_text.text for r in insert_reqs]
        assert "\n" in texts

    def test_no_double_newline_insertion(self) -> None:
        """Editing paragraph text should not produce double newlines."""
        base = _single_doc(
            [
                _indexed_para("Hello\n", 1),
                _terminal(7),
            ]
        )
        desired = _single_doc(
            [
                _para("Hello World\n"),
                _terminal(),
            ]
        )

        batches = reconcile_batches(base, desired)
        reqs = _flat_requests(batches)

        # Check no insertText contains "\n\n"
        for r in reqs:
            if r.insert_text is not None:
                assert "\n\n" not in (r.insert_text.text or ""), (
                    f"Double newline found in insertText: {r.insert_text.text!r}"
                )


# ===========================================================================
# 2. No delete+re-insert for matched paragraphs
# ===========================================================================


class TestSurgicalEdits:
    """Matched paragraphs must use surgical char-level edits, not whole delete+reinsert."""

    def test_small_text_change_is_surgical(self) -> None:
        """Changing one word in a paragraph should NOT delete the whole paragraph."""
        base = _single_doc(
            [
                _indexed_para("The quick brown fox\n", 1),
                _terminal(21),
            ]
        )
        desired = _single_doc(
            [
                _para("The quick red fox\n"),
                _terminal(),
            ]
        )

        batches = reconcile_batches(base, desired)
        reqs = _flat_requests(batches)

        delete_reqs = [r for r in reqs if r.delete_content_range is not None]

        # There should be a small delete (just "brown") and a small insert ("red")
        # NOT a delete of the entire paragraph
        for dr in delete_reqs:
            rng = dr.delete_content_range.range
            delete_size = rng.end_index - rng.start_index
            assert delete_size < 15, (
                f"Delete range too large ({delete_size} chars) — "
                f"should be surgical, not whole-paragraph"
            )

    def test_style_only_change_no_delete(self) -> None:
        """Changing only paragraph style should produce zero deleteContentRange."""
        base = _single_doc(
            [
                _indexed_para("Hello\n", 1),
                _terminal(7),
            ]
        )
        desired = _single_doc(
            [
                _para("Hello\n", style="HEADING_1"),
                _terminal(),
            ]
        )

        batches = reconcile_batches(base, desired)
        reqs = _flat_requests(batches)

        delete_reqs = [r for r in reqs if r.delete_content_range is not None]
        assert len(delete_reqs) == 0, (
            f"Style-only change produced {len(delete_reqs)} deletes"
        )

        # Should have updateParagraphStyle
        style_reqs = [r for r in reqs if r.update_paragraph_style is not None]
        assert len(style_reqs) >= 1

    def test_text_style_change_no_delete(self) -> None:
        """Changing only text style (bold) should NOT delete content."""
        bold = TextStyle(bold=True)
        base = _single_doc(
            [
                _multi_run_para([("Hello\n", None)], start=1),
                _terminal(7),
            ]
        )
        desired = _single_doc(
            [
                _multi_run_para([("Hello\n", bold)], start=1),
                _terminal(7),
            ]
        )

        batches = reconcile_batches(base, desired)
        reqs = _flat_requests(batches)

        delete_reqs = [r for r in reqs if r.delete_content_range is not None]
        assert len(delete_reqs) == 0, "Text style change produced deleteContentRange"

        style_reqs = [r for r in reqs if r.update_text_style is not None]
        assert len(style_reqs) >= 1


# ===========================================================================
# 3. Deferred IDs — multi-structural creation
# ===========================================================================


class TestDeferredIDs:
    """Creating multiple structural elements must use correct deferred IDs."""

    def test_header_and_footer_same_reconcile(self) -> None:
        """Creating both header and footer produces 2+ batches with deferred IDs."""
        base = _single_doc([_terminal(1)])
        desired = _single_doc(
            [_terminal()],
            headers={
                "h1": Header(
                    header_id="h1",
                    content=[_para("Header text"), _terminal()],
                ),
            },
            footers={
                "f1": Footer(
                    footer_id="f1",
                    content=[_para("Footer text"), _terminal()],
                ),
            },
            document_style={"default_header_id": "h1", "default_footer_id": "f1"},
        )

        batches = reconcile_batches(base, desired)

        # Must produce at least 2 batches (batch 0: creates, batch 1: content)
        assert len(batches) >= 2, (
            f"Expected >=2 batches for header+footer creation, got {len(batches)}"
        )

        # Batch 0 should have createHeader and createFooter
        batch0_types = _collect_request_types([batches[0]])
        assert "createHeader" in batch0_types, "Missing createHeader in batch 0"
        assert "createFooter" in batch0_types, "Missing createFooter in batch 0"

    def test_new_tab_with_content(self) -> None:
        """Creating a new tab with body content uses deferred tab ID."""
        base = _doc(_tab("t1", [_terminal(1)]))
        desired = _doc(
            _tab("t1", [_terminal(1)]),
            _tab("t2", [_para("New tab content\n"), _terminal()]),
        )

        batches = reconcile_batches(base, desired)

        assert len(batches) >= 2, (
            f"Expected >=2 batches for tab creation, got {len(batches)}"
        )

        batch0_types = _collect_request_types([batches[0]])
        assert "addDocumentTab" in batch0_types

    @pytest.mark.xfail(
        raises=NotImplementedError,
        reason="InsertFootnoteOp requires anchor_index from footnoteReference in body — "
        "diff layer cannot determine it when the footnote ref is in desired but has no startIndex",
    )
    def test_header_footer_and_footnote_three_deferred_ids(self) -> None:
        """Creating header + footer + footnote needs 3 deferred IDs in batch 0."""

        # Base: simple body with text and a trailing paragraph
        base = _single_doc(
            [
                _indexed_para("Some text\n", 1),
                _terminal(11),
            ]
        )

        # Desired: same body but with a footnote ref inserted, plus header + footer
        desired = _single_doc(
            [
                StructuralElement(
                    paragraph=Paragraph(
                        elements=[
                            ParagraphElement(text_run=TextRun(content="Some text")),
                            ParagraphElement(
                                footnote_reference=FootnoteReference(
                                    footnote_id="fn1",
                                )
                            ),
                            ParagraphElement(text_run=TextRun(content="\n")),
                        ],
                        paragraph_style=ParagraphStyle(named_style_type="NORMAL_TEXT"),
                    )
                ),
                _terminal(),
            ],
            headers={
                "h1": Header(
                    header_id="h1",
                    content=[_para("My Header"), _terminal()],
                ),
            },
            footers={
                "f1": Footer(
                    footer_id="f1",
                    content=[_para("My Footer"), _terminal()],
                ),
            },
            footnotes={
                "fn1": Footnote(
                    footnote_id="fn1",
                    content=[_para("Footnote body"), _terminal()],
                ),
            },
            document_style={"default_header_id": "h1", "default_footer_id": "f1"},
        )

        batches = reconcile_batches(base, desired)

        assert len(batches) >= 2, (
            f"Expected >=2 batches for header+footer+footnote, got {len(batches)}"
        )

        # Batch 0 should have 3 structural creates
        batch0_reqs = batches[0].requests or []
        create_types = []
        for req in batch0_reqs:
            d = req.model_dump(by_alias=True, exclude_none=True)
            create_types.extend(d.keys())
        assert "createHeader" in create_types
        assert "createFooter" in create_types
        assert "createFootnote" in create_types


# ===========================================================================
# 4. UTF-16 index arithmetic
# ===========================================================================


class TestUtf16Indexing:
    """Characters outside the BMP (emoji) have UTF-16 length 2, not 1."""

    def test_emoji_paragraph_insert(self) -> None:
        """Inserting a paragraph with emoji must use correct UTF-16 indices."""
        base = _single_doc([_terminal(1)])
        desired = _single_doc(
            [
                _para("\U0001f600 Hello\n"),  # 😀 is UTF-16 length 2
                _terminal(),
            ]
        )

        batches = reconcile_batches(base, desired)
        reqs = _flat_requests(batches)

        insert_reqs = [r for r in reqs if r.insert_text is not None]
        assert len(insert_reqs) >= 1
        # The insert should contain the emoji
        all_text = "".join(r.insert_text.text for r in insert_reqs)
        assert "\U0001f600" in all_text

    @pytest.mark.xfail(
        reason="Char-level diff on emoji paragraph computes wrong delete range — delete starts at 3 instead of 4 (emoji is 2 UTF-16 units)"
    )
    def test_emoji_edit_correct_indices(self) -> None:
        """Editing text after an emoji must account for UTF-16 surrogate pair."""
        from extradoc.indexer import utf16_len

        # "😀 Hello\n" — 😀 is 2 UTF-16 code units, space is 1, Hello is 5, \n is 1 = 9
        text = "\U0001f600 Hello\n"
        assert utf16_len(text) == 9

        base = _single_doc(
            [
                _indexed_para(text, 1),
                _terminal(10),  # 1 + 9 = 10
            ]
        )

        desired = _single_doc(
            [
                _para("\U0001f600 World\n"),
                _terminal(),
            ]
        )

        batches = reconcile_batches(base, desired)
        reqs = _flat_requests(batches)

        # Should have a delete of "Hello" and insert of "World"
        delete_reqs = [r for r in reqs if r.delete_content_range is not None]
        insert_reqs = [r for r in reqs if r.insert_text is not None]

        assert len(delete_reqs) >= 1
        assert len(insert_reqs) >= 1

        # The delete should be at index 4 (1 + 2 for emoji + 1 for space) through 9
        # (5 chars of "Hello")
        for dr in delete_reqs:
            rng = dr.delete_content_range.range
            assert rng.start_index >= 4, (
                f"Delete starts at {rng.start_index}, expected >= 4 (after emoji+space)"
            )


# ===========================================================================
# 5. Complex table scenarios
# ===========================================================================


class TestComplexTables:
    """Edge cases around table handling."""

    def test_table_cell_with_multiple_paragraphs(self) -> None:
        """Table cell with multiple paragraphs should be supported."""
        base_cell = TableCell(
            content=[
                _indexed_para("Line 1\n", 3),
                _indexed_para("Line 2\n", 10),
                _indexed_para("\n", 17),
            ]
        )
        base = _single_doc(
            [
                StructuralElement(
                    start_index=1,
                    end_index=18,
                    table=Table(
                        table_rows=[TableRow(table_cells=[base_cell])],
                        columns=1,
                        rows=1,
                    ),
                ),
                _terminal(18),
            ]
        )

        desired_cell = TableCell(
            content=[
                _para("Line 1\n"),
                _para("Line 2 modified\n"),
                _terminal(),
            ]
        )
        desired = _single_doc(
            [
                StructuralElement(
                    table=Table(
                        table_rows=[TableRow(table_cells=[desired_cell])],
                        columns=1,
                        rows=1,
                    ),
                ),
                _terminal(),
            ]
        )

        batches = reconcile_batches(base, desired)
        reqs = _flat_requests(batches)
        # Should produce some kind of content update, not crash
        assert len(reqs) >= 1

    def test_add_table_to_empty_doc(self) -> None:
        """Inserting a table into an empty document."""
        base = _single_doc([_terminal(1)])
        desired = _single_doc(
            [
                _table([["A", "B"], ["C", "D"]]),
                _terminal(),
            ]
        )

        batches = reconcile_batches(base, desired)
        reqs = _flat_requests(batches)

        # Should have insertTable
        insert_table_reqs = [r for r in reqs if r.insert_table is not None]
        assert len(insert_table_reqs) == 1
        it = insert_table_reqs[0].insert_table
        assert it.rows == 2
        assert it.columns == 2

    def test_delete_table(self) -> None:
        """Deleting a table from a document."""
        base = _single_doc(
            [
                _indexed_para("Before\n", 1),
                StructuralElement(
                    start_index=8,
                    end_index=20,
                    table=Table(
                        table_rows=[
                            TableRow(
                                table_cells=[
                                    TableCell(
                                        content=[
                                            _indexed_para("Cell\n", 10),
                                            _indexed_para("\n", 15),
                                        ]
                                    )
                                ]
                            )
                        ],
                        columns=1,
                        rows=1,
                    ),
                ),
                _terminal(20),
            ]
        )
        desired = _single_doc(
            [
                _para("Before\n"),
                _terminal(),
            ]
        )

        batches = reconcile_batches(base, desired)
        reqs = _flat_requests(batches)

        delete_reqs = [r for r in reqs if r.delete_content_range is not None]
        assert len(delete_reqs) >= 1

    @pytest.mark.xfail(
        reason="Simultaneous row+column changes not supported — table_diff only does one axis"
    )
    def test_table_add_row_and_column_simultaneously(self) -> None:
        """Adding both a row and column in the same reconcile."""
        base = _single_doc(
            [
                StructuralElement(
                    start_index=1,
                    end_index=20,
                    table=Table(
                        table_rows=[
                            TableRow(
                                table_cells=[
                                    TableCell(
                                        content=[
                                            _indexed_para("A\n", 4),
                                            _indexed_para("\n", 6),
                                        ]
                                    ),
                                    TableCell(
                                        content=[
                                            _indexed_para("B\n", 8),
                                            _indexed_para("\n", 10),
                                        ]
                                    ),
                                ]
                            ),
                        ],
                        columns=2,
                        rows=1,
                    ),
                ),
                _terminal(20),
            ]
        )

        desired = _single_doc(
            [
                StructuralElement(
                    table=Table(
                        table_rows=[
                            TableRow(
                                table_cells=[
                                    TableCell(content=[_para("A\n"), _terminal()]),
                                    TableCell(content=[_para("B\n"), _terminal()]),
                                    TableCell(content=[_para("C\n"), _terminal()]),
                                ]
                            ),
                            TableRow(
                                table_cells=[
                                    TableCell(content=[_para("D\n"), _terminal()]),
                                    TableCell(content=[_para("E\n"), _terminal()]),
                                    TableCell(content=[_para("F\n"), _terminal()]),
                                ]
                            ),
                        ],
                        columns=3,
                        rows=2,
                    ),
                ),
                _terminal(),
            ]
        )

        batches = reconcile_batches(base, desired)
        req_types = _collect_request_types(batches)
        # Should have both insertTableRow and insertTableColumn
        assert "insertTableRow" in req_types
        assert "insertTableColumn" in req_types

    def test_two_adjacent_tables(self) -> None:
        """Two tables next to each other — edits in second should not affect first."""
        base = _single_doc(
            [
                StructuralElement(
                    start_index=1,
                    end_index=15,
                    table=Table(
                        table_rows=[
                            TableRow(
                                table_cells=[
                                    TableCell(
                                        content=[
                                            _indexed_para("T1\n", 4),
                                            _indexed_para("\n", 7),
                                        ]
                                    )
                                ]
                            )
                        ],
                        columns=1,
                        rows=1,
                    ),
                ),
                StructuralElement(
                    start_index=15,
                    end_index=29,
                    table=Table(
                        table_rows=[
                            TableRow(
                                table_cells=[
                                    TableCell(
                                        content=[
                                            _indexed_para("T2\n", 18),
                                            _indexed_para("\n", 21),
                                        ]
                                    )
                                ]
                            )
                        ],
                        columns=1,
                        rows=1,
                    ),
                ),
                _terminal(29),
            ]
        )

        # Only change content in second table
        desired = _single_doc(
            [
                StructuralElement(
                    table=Table(
                        table_rows=[
                            TableRow(
                                table_cells=[
                                    TableCell(content=[_para("T1\n"), _terminal()])
                                ]
                            )
                        ],
                        columns=1,
                        rows=1,
                    ),
                ),
                StructuralElement(
                    table=Table(
                        table_rows=[
                            TableRow(
                                table_cells=[
                                    TableCell(
                                        content=[_para("T2 modified\n"), _terminal()]
                                    )
                                ]
                            )
                        ],
                        columns=1,
                        rows=1,
                    ),
                ),
                _terminal(),
            ]
        )

        batches = reconcile_batches(base, desired)
        reqs = _flat_requests(batches)

        # Should only affect second table — no requests touching indices < 15
        for r in reqs:
            if r.delete_content_range is not None:
                rng = r.delete_content_range.range
                assert rng.start_index >= 15, (
                    f"Delete at {rng.start_index} touches first table"
                )
            if r.insert_text is not None:
                loc = r.insert_text.location
                if loc is not None:
                    assert loc.index >= 15, f"Insert at {loc.index} touches first table"


# ===========================================================================
# 6. Paragraph element types
# ===========================================================================


class TestParagraphElements:
    """Tests for non-textRun paragraph elements (footnote refs, images, etc.)."""

    def test_footnote_ref_survives_text_edit(self) -> None:
        """Editing text before a footnote reference should preserve the reference."""
        # Paragraph: "Hello[fn_ref] World\n"
        base = _single_doc(
            [
                StructuralElement(
                    start_index=1,
                    end_index=18,
                    paragraph=Paragraph(
                        elements=[
                            ParagraphElement(
                                start_index=1,
                                end_index=6,
                                text_run=TextRun(content="Hello"),
                            ),
                            ParagraphElement(
                                start_index=6,
                                end_index=7,
                                footnote_reference=FootnoteReference(
                                    footnote_id="fn1",
                                ),
                            ),
                            ParagraphElement(
                                start_index=7,
                                end_index=18,
                                text_run=TextRun(content=" World\n"),
                            ),
                        ],
                        paragraph_style=ParagraphStyle(named_style_type="NORMAL_TEXT"),
                    ),
                ),
                _terminal(18),
            ],
            footnotes={
                "fn1": Footnote(
                    footnote_id="fn1",
                    content=[_para("A footnote"), _terminal()],
                ),
            },
        )

        # Change "Hello" to "Hi" — footnote ref must survive
        desired = _single_doc(
            [
                StructuralElement(
                    paragraph=Paragraph(
                        elements=[
                            ParagraphElement(text_run=TextRun(content="Hi")),
                            ParagraphElement(
                                footnote_reference=FootnoteReference(
                                    footnote_id="fn1",
                                ),
                            ),
                            ParagraphElement(text_run=TextRun(content=" World\n")),
                        ],
                        paragraph_style=ParagraphStyle(named_style_type="NORMAL_TEXT"),
                    ),
                ),
                _terminal(),
            ],
            footnotes={
                "fn1": Footnote(
                    footnote_id="fn1",
                    content=[_para("A footnote"), _terminal()],
                ),
            },
        )

        batches = reconcile_batches(base, desired)
        reqs = _flat_requests(batches)

        # Should NOT delete the footnote reference character at index 6
        for r in reqs:
            if r.delete_content_range is not None:
                rng = r.delete_content_range.range
                assert not (rng.start_index <= 6 < rng.end_index), (
                    f"Delete range [{rng.start_index}, {rng.end_index}) "
                    f"covers footnote reference at index 6"
                )

    def test_horizontal_rule_preservation(self) -> None:
        """Editing text around a HorizontalRule should preserve it."""
        base = _single_doc(
            [
                _indexed_para("Before\n", 1),
                StructuralElement(
                    start_index=8,
                    end_index=10,
                    paragraph=Paragraph(
                        elements=[
                            ParagraphElement(
                                start_index=8,
                                end_index=9,
                                horizontal_rule=HorizontalRule(),
                            ),
                            ParagraphElement(
                                start_index=9,
                                end_index=10,
                                text_run=TextRun(content="\n"),
                            ),
                        ],
                        paragraph_style=ParagraphStyle(named_style_type="NORMAL_TEXT"),
                    ),
                ),
                _indexed_para("After\n", 10),
                _terminal(16),
            ]
        )

        desired = _single_doc(
            [
                _para("Before modified\n"),
                StructuralElement(
                    paragraph=Paragraph(
                        elements=[
                            ParagraphElement(horizontal_rule=HorizontalRule()),
                            ParagraphElement(text_run=TextRun(content="\n")),
                        ],
                        paragraph_style=ParagraphStyle(named_style_type="NORMAL_TEXT"),
                    ),
                ),
                _para("After\n"),
                _terminal(),
            ]
        )

        batches = reconcile_batches(base, desired)
        reqs = _flat_requests(batches)

        # The horizontal rule paragraph should not be deleted
        for r in reqs:
            if r.delete_content_range is not None:
                rng = r.delete_content_range.range
                assert not (rng.start_index <= 8 and rng.end_index >= 10), (
                    "Horizontal rule paragraph was deleted"
                )

    @pytest.mark.xfail(
        reason="RichLink and Person elements not tracked by diff — will be dropped on round-trip"
    )
    def test_rich_link_preservation(self) -> None:
        """Paragraph containing a RichLink should survive text edits."""
        base = _single_doc(
            [
                StructuralElement(
                    start_index=1,
                    end_index=12,
                    paragraph=Paragraph(
                        elements=[
                            ParagraphElement(
                                start_index=1,
                                end_index=5,
                                text_run=TextRun(content="See "),
                            ),
                            ParagraphElement(
                                start_index=5,
                                end_index=11,
                                rich_link=RichLink(
                                    rich_link_properties=RichLinkProperties(
                                        uri="https://docs.google.com/doc/123",
                                        title="My Doc",
                                    ),
                                ),
                            ),
                            ParagraphElement(
                                start_index=11,
                                end_index=12,
                                text_run=TextRun(content="\n"),
                            ),
                        ],
                        paragraph_style=ParagraphStyle(named_style_type="NORMAL_TEXT"),
                    ),
                ),
                _terminal(12),
            ]
        )

        desired = _single_doc(
            [
                StructuralElement(
                    paragraph=Paragraph(
                        elements=[
                            ParagraphElement(text_run=TextRun(content="Check ")),
                            ParagraphElement(
                                rich_link=RichLink(
                                    rich_link_properties=RichLinkProperties(
                                        uri="https://docs.google.com/doc/123",
                                        title="My Doc",
                                    ),
                                ),
                            ),
                            ParagraphElement(text_run=TextRun(content="\n")),
                        ],
                        paragraph_style=ParagraphStyle(named_style_type="NORMAL_TEXT"),
                    ),
                ),
                _terminal(),
            ]
        )

        batches = reconcile_batches(base, desired)
        reqs = _flat_requests(batches)

        # Should edit "See " to "Check " without touching the rich_link at index 5
        for r in reqs:
            if r.delete_content_range is not None:
                rng = r.delete_content_range.range
                assert not (rng.start_index <= 5 < rng.end_index), (
                    f"Delete [{rng.start_index}, {rng.end_index}) covers rich link"
                )


# ===========================================================================
# 7. Multi-tab scenarios
# ===========================================================================


class TestMultiTab:
    """Changes across multiple tabs in a single reconcile."""

    def test_edits_in_two_tabs(self) -> None:
        """Editing content in both tabs produces requests for each tab."""
        base = _doc(
            Tab(
                tab_properties=TabProperties(tab_id="t1", title="Tab1", index=0),
                document_tab=DocumentTab(
                    body=Body(
                        content=[
                            _indexed_para("Tab1 text\n", 1),
                            _terminal(11),
                        ]
                    ),
                    headers={},
                    footers={},
                    footnotes={},
                    lists={},
                    named_styles=NamedStyles(styles=[]),
                    document_style={},
                    inline_objects={},
                ),
            ),
            Tab(
                tab_properties=TabProperties(tab_id="t2", title="Tab2", index=1),
                document_tab=DocumentTab(
                    body=Body(
                        content=[
                            _indexed_para("Tab2 text\n", 1),
                            _terminal(11),
                        ]
                    ),
                    headers={},
                    footers={},
                    footnotes={},
                    lists={},
                    named_styles=NamedStyles(styles=[]),
                    document_style={},
                    inline_objects={},
                ),
            ),
        )

        desired = _doc(
            Tab(
                tab_properties=TabProperties(tab_id="t1", title="Tab1", index=0),
                document_tab=DocumentTab(
                    body=Body(
                        content=[
                            _para("Tab1 modified\n"),
                            _terminal(),
                        ]
                    ),
                    headers={},
                    footers={},
                    footnotes={},
                    lists={},
                    named_styles=NamedStyles(styles=[]),
                    document_style={},
                    inline_objects={},
                ),
            ),
            Tab(
                tab_properties=TabProperties(tab_id="t2", title="Tab2", index=1),
                document_tab=DocumentTab(
                    body=Body(
                        content=[
                            _para("Tab2 modified\n"),
                            _terminal(),
                        ]
                    ),
                    headers={},
                    footers={},
                    footnotes={},
                    lists={},
                    named_styles=NamedStyles(styles=[]),
                    document_style={},
                    inline_objects={},
                ),
            ),
        )

        batches = reconcile_batches(base, desired)
        reqs = _flat_requests(batches)

        # Should have requests targeting both t1 and t2
        tab_ids = set()
        for r in reqs:
            if r.insert_text is not None and r.insert_text.location:
                tab_ids.add(r.insert_text.location.tab_id)
            if r.delete_content_range is not None and r.delete_content_range.range:
                tab_ids.add(r.delete_content_range.range.tab_id)
        assert "t1" in tab_ids, "No requests for tab t1"
        assert "t2" in tab_ids, "No requests for tab t2"


# ===========================================================================
# 8. Header/footer content editing
# ===========================================================================


class TestHeaderFooterContent:
    """Editing content inside existing headers/footers."""

    def test_edit_existing_header_content(self) -> None:
        """Changing text inside an existing header should produce content update."""
        base = _single_doc(
            [_terminal(1)],
            headers={
                "h1": Header(
                    header_id="h1",
                    content=[
                        _indexed_para("Old header\n", 0),
                        _indexed_para("\n", 11),
                    ],
                ),
            },
            document_style={"default_header_id": "h1"},
        )
        desired = _single_doc(
            [_terminal()],
            headers={
                "h1": Header(
                    header_id="h1",
                    content=[
                        _para("New header\n"),
                        _terminal(),
                    ],
                ),
            },
            document_style={"default_header_id": "h1"},
        )

        batches = reconcile_batches(base, desired)
        reqs = _flat_requests(batches)

        # Should produce requests with segment_id = "h1"
        assert len(reqs) >= 1, "No requests for header content update"

        # Verify segment_id is set to h1 on the content requests
        found_header_segment = any(
            (
                r.insert_text is not None
                and r.insert_text.location
                and r.insert_text.location.segment_id == "h1"
            )
            or (
                r.delete_content_range is not None
                and r.delete_content_range.range
                and r.delete_content_range.range.segment_id == "h1"
            )
            for r in reqs
        )
        assert found_header_segment, "No request targets header segment h1"

    def test_edit_existing_footer_content(self) -> None:
        """Changing text inside an existing footer."""
        base = _single_doc(
            [_terminal(1)],
            footers={
                "f1": Footer(
                    footer_id="f1",
                    content=[
                        _indexed_para("Old footer\n", 0),
                        _indexed_para("\n", 11),
                    ],
                ),
            },
            document_style={"default_footer_id": "f1"},
        )
        desired = _single_doc(
            [_terminal()],
            footers={
                "f1": Footer(
                    footer_id="f1",
                    content=[
                        _para("New footer\n"),
                        _terminal(),
                    ],
                ),
            },
            document_style={"default_footer_id": "f1"},
        )

        batches = reconcile_batches(base, desired)
        reqs = _flat_requests(batches)
        assert len(reqs) >= 1

        found = any(
            (
                r.delete_content_range is not None
                and r.delete_content_range.range
                and r.delete_content_range.range.segment_id == "f1"
            )
            or (
                r.insert_text is not None
                and r.insert_text.location
                and r.insert_text.location.segment_id == "f1"
            )
            for r in reqs
        )
        assert found, "No request targets footer segment f1"


# ===========================================================================
# 9. Section break preservation
# ===========================================================================


class TestSectionBreaks:
    """Section breaks between paragraphs should survive edits."""

    def test_section_break_preserved_when_surrounding_text_changes(self) -> None:
        """Editing paragraphs around a section break should not delete it."""
        base = _single_doc(
            [
                _indexed_para("Section 1\n", 1),
                StructuralElement(
                    start_index=11,
                    end_index=13,
                    section_break=SectionBreak(
                        section_style=SectionStyle(
                            section_type="NEXT_PAGE",
                        )
                    ),
                ),
                _indexed_para("Section 2\n", 13),
                _terminal(23),
            ]
        )

        desired = _single_doc(
            [
                _para("Section 1 modified\n"),
                StructuralElement(
                    section_break=SectionBreak(
                        section_style=SectionStyle(
                            section_type="NEXT_PAGE",
                        )
                    ),
                ),
                _para("Section 2\n"),
                _terminal(),
            ]
        )

        batches = reconcile_batches(base, desired)
        reqs = _flat_requests(batches)

        # Should NOT delete the section break
        for r in reqs:
            if r.delete_content_range is not None:
                rng = r.delete_content_range.range
                assert not (rng.start_index <= 11 and rng.end_index >= 13), (
                    f"Section break at [11, 13) was deleted by range "
                    f"[{rng.start_index}, {rng.end_index})"
                )


# ===========================================================================
# 10. endOfSegmentPosition — must not appear
# ===========================================================================


class TestNoEndOfSegmentPosition:
    """The reconciler must never use endOfSegmentPosition in requests."""

    def test_no_end_of_segment_position_in_any_request(self) -> None:
        """All requests use explicit indices, never endOfSegmentPosition."""
        base = _single_doc([_terminal(1)])
        desired = _single_doc(
            [
                _para("New content\n"),
                _terminal(),
            ]
        )

        batches = reconcile_batches(base, desired)

        for batch in batches:
            batch_json = batch.model_dump(by_alias=True, exclude_none=True)
            json_str = str(batch_json)
            assert "endOfSegmentPosition" not in json_str, (
                "Found endOfSegmentPosition in request"
            )


# ===========================================================================
# 11. Inline images mixed with text
# ===========================================================================


class TestInlineImages:
    """Inline images mixed with text in paragraphs."""

    def test_text_edit_with_inline_image_in_paragraph(self) -> None:
        """Editing text in a paragraph that also contains an inline image."""
        base = _single_doc(
            [
                StructuralElement(
                    start_index=1,
                    end_index=15,
                    paragraph=Paragraph(
                        elements=[
                            ParagraphElement(
                                start_index=1,
                                end_index=6,
                                text_run=TextRun(content="Hello"),
                            ),
                            ParagraphElement(
                                start_index=6,
                                end_index=7,
                                inline_object_element=InlineObjectElement(
                                    inline_object_id="img1",
                                ),
                            ),
                            ParagraphElement(
                                start_index=7,
                                end_index=15,
                                text_run=TextRun(content=" World\n"),
                            ),
                        ],
                        paragraph_style=ParagraphStyle(named_style_type="NORMAL_TEXT"),
                    ),
                ),
                _terminal(15),
            ],
            inline_objects={
                "img1": InlineObject(
                    inline_object_id="img1",
                    inline_object_properties=InlineObjectProperties(
                        embedded_object=EmbeddedObject(
                            title="test image",
                        )
                    ),
                ),
            },
        )

        desired = _single_doc(
            [
                StructuralElement(
                    paragraph=Paragraph(
                        elements=[
                            ParagraphElement(text_run=TextRun(content="Hi")),
                            ParagraphElement(
                                inline_object_element=InlineObjectElement(
                                    inline_object_id="img1",
                                ),
                            ),
                            ParagraphElement(text_run=TextRun(content=" World\n")),
                        ],
                        paragraph_style=ParagraphStyle(named_style_type="NORMAL_TEXT"),
                    ),
                ),
                _terminal(),
            ],
            inline_objects={
                "img1": InlineObject(
                    inline_object_id="img1",
                    inline_object_properties=InlineObjectProperties(
                        embedded_object=EmbeddedObject(
                            title="test image",
                        )
                    ),
                ),
            },
        )

        batches = reconcile_batches(base, desired)
        reqs = _flat_requests(batches)

        # The image at index 6 should NOT be deleted
        for r in reqs:
            if r.delete_content_range is not None:
                rng = r.delete_content_range.range
                assert not (rng.start_index <= 6 < rng.end_index), (
                    f"Delete [{rng.start_index}, {rng.end_index}) covers inline image"
                )


# ===========================================================================
# 12. Document style changes
# ===========================================================================


class TestDocumentStyle:
    """Document-level style changes (margins, page size, etc.)."""

    def test_margin_change(self) -> None:
        """Changing document margins produces updateDocumentStyle."""
        base = _single_doc(
            [_terminal(1)],
            document_style={
                "margin_top": {"magnitude": 72, "unit": "PT"},
                "margin_bottom": {"magnitude": 72, "unit": "PT"},
            },
        )
        desired = _single_doc(
            [_terminal()],
            document_style={
                "margin_top": {"magnitude": 36, "unit": "PT"},
                "margin_bottom": {"magnitude": 72, "unit": "PT"},
            },
        )

        batches = reconcile_batches(base, desired)
        req_types = _collect_request_types(batches)

        assert "updateDocumentStyle" in req_types


# ===========================================================================
# 13. Paragraph with only whitespace
# ===========================================================================


class TestWhitespace:
    """Edge cases with whitespace-only content."""

    def test_whitespace_only_paragraph(self) -> None:
        """A paragraph with only spaces should be handled correctly."""
        base = _single_doc(
            [
                _indexed_para("   \n", 1),
                _terminal(5),
            ]
        )
        desired = _single_doc(
            [
                _para("Text\n"),
                _terminal(),
            ]
        )

        batches = reconcile_batches(base, desired)
        reqs = _flat_requests(batches)
        assert len(reqs) >= 1

    def test_tab_characters_in_paragraph(self) -> None:
        """Tab characters (used for bullet nesting) in non-bullet paragraphs."""
        base = _single_doc(
            [
                _indexed_para("\tIndented\n", 1),
                _terminal(11),
            ]
        )
        desired = _single_doc(
            [
                _para("Not indented\n"),
                _terminal(),
            ]
        )

        batches = reconcile_batches(base, desired)
        reqs = _flat_requests(batches)
        assert len(reqs) >= 1


# ===========================================================================
# 14. Large document — many paragraphs
# ===========================================================================


class TestLargeDocument:
    """Performance-adjacent: reconciling docs with many paragraphs."""

    def test_single_edit_in_large_doc(self) -> None:
        """Editing one paragraph in a 50-paragraph doc should be efficient."""
        n = 50
        base_content: list[StructuralElement] = []
        cursor = 1
        for i in range(n):
            text = f"Paragraph {i}\n"
            base_content.append(_indexed_para(text, cursor))
            from extradoc.indexer import utf16_len

            cursor += utf16_len(text)
        base_content.append(_terminal(cursor))
        base = _single_doc(base_content)

        # Only change paragraph 25
        desired_content: list[StructuralElement] = []
        for i in range(n):
            if i == 25:
                desired_content.append(_para(f"Modified paragraph {i}\n"))
            else:
                desired_content.append(_para(f"Paragraph {i}\n"))
        desired_content.append(_terminal())
        desired = _single_doc(desired_content)

        batches = reconcile_batches(base, desired)
        reqs = _flat_requests(batches)

        # Should produce a small number of requests (not O(n))
        assert len(reqs) <= 5, (
            f"Too many requests ({len(reqs)}) for single paragraph edit"
        )


# ===========================================================================
# 15. Named ranges (not supported)
# ===========================================================================


class TestNamedRanges:
    """Named ranges are a document feature the reconciler doesn't handle."""

    @pytest.mark.xfail(
        reason="Named ranges (createNamedRange/deleteNamedRange) not supported by reconciler"
    )
    def test_named_range_not_silently_dropped(self) -> None:
        """Adding a named range should either work or raise explicitly."""
        base = _doc(
            Tab(
                tab_properties=TabProperties(tab_id="t1", title="Tab", index=0),
                document_tab=DocumentTab(
                    body=Body(
                        content=[
                            _indexed_para("Hello World\n", 1),
                            _terminal(13),
                        ]
                    ),
                    headers={},
                    footers={},
                    footnotes={},
                    lists={},
                    named_styles=NamedStyles(styles=[]),
                    document_style={},
                    inline_objects={},
                    named_ranges={},
                ),
            )
        )

        desired = _doc(
            Tab(
                tab_properties=TabProperties(tab_id="t1", title="Tab", index=0),
                document_tab=DocumentTab(
                    body=Body(
                        content=[
                            _indexed_para("Hello World\n", 1),
                            _terminal(13),
                        ]
                    ),
                    headers={},
                    footers={},
                    footnotes={},
                    lists={},
                    named_styles=NamedStyles(styles=[]),
                    document_style={},
                    inline_objects={},
                    named_ranges={
                        "nr1": {
                            "named_range_id": "nr1",
                            "name": "my_range",
                            "ranges": [
                                {"start_index": 1, "end_index": 6, "segment_id": ""},
                            ],
                        },
                    },
                ),
            )
        )

        batches = reconcile_batches(base, desired)
        req_types = _collect_request_types(batches)
        assert "createNamedRange" in req_types


# ===========================================================================
# 16. Bullet paragraphs with text style
# ===========================================================================


class TestNewTabWithTable:
    """Creating a new tab whose body contains a table with cell content."""

    @pytest.mark.xfail(
        raises=NotImplementedError,
        reason="_element_size cannot compute table size without startIndex/endIndex — "
        "new tab content is synthetic (no API indices), so inserting a table into a new tab fails",
    )
    def test_new_tab_with_table(self) -> None:
        """New tab with a 2x2 table should produce addDocumentTab + insertTable + insertText for cells."""
        base = _doc(_tab("t1", [_terminal(1)]))

        desired = _doc(
            _tab("t1", [_terminal(1)]),
            _tab(
                "t2",
                [
                    _para("Title\n"),
                    _table([["A1", "B1"], ["A2", "B2"]]),
                    _terminal(),
                ],
            ),
        )

        batches = reconcile_batches(base, desired)
        req_types = _collect_request_types(batches)

        # Must have at least 2 batches (batch 0: addDocumentTab, batch 1: content)
        assert len(batches) >= 2, f"Expected >=2 batches, got {len(batches)}"
        assert "addDocumentTab" in req_types

        # Batch 1 should contain insertTable for the 2x2 table
        assert "insertTable" in req_types, "Missing insertTable in requests"

        # Should have insertText for "Title\n" and cell contents
        insert_texts = _get_requests_of_type(batches, "insert_text")
        all_text = "".join(r.text or "" for r in insert_texts)
        assert "Title" in all_text, f"Title not found in inserted text: {all_text!r}"
        # Cell contents should be inserted
        for cell_text in ["A1", "B1", "A2", "B2"]:
            assert cell_text in all_text, (
                f"Cell text {cell_text!r} not found in inserted text: {all_text!r}"
            )

    @pytest.mark.xfail(
        raises=NotImplementedError,
        reason="_element_size cannot compute table size without startIndex/endIndex",
    )
    def test_new_tab_with_table_only(self) -> None:
        """New tab whose only content is a table (no leading paragraph)."""
        base = _doc(_tab("t1", [_terminal(1)]))

        desired = _doc(
            _tab("t1", [_terminal(1)]),
            _tab(
                "t2",
                [
                    _table([["X", "Y"]]),
                    _terminal(),
                ],
            ),
        )

        batches = reconcile_batches(base, desired)
        req_types = _collect_request_types(batches)

        assert len(batches) >= 2
        assert "addDocumentTab" in req_types
        assert "insertTable" in req_types

        insert_texts = _get_requests_of_type(batches, "insert_text")
        all_text = "".join(r.text or "" for r in insert_texts)
        for cell_text in ["X", "Y"]:
            assert cell_text in all_text, (
                f"Cell text {cell_text!r} not found: {all_text!r}"
            )

    @pytest.mark.xfail(
        raises=NotImplementedError,
        reason="_element_size cannot compute table size without startIndex/endIndex",
    )
    def test_new_tab_with_multi_paragraph_table_cell(self) -> None:
        """New tab with a table cell containing multiple paragraphs."""
        base = _doc(_tab("t1", [_terminal(1)]))

        multi_para_cell = TableCell(
            content=[_para("Line 1\n"), _para("Line 2\n"), _terminal()]
        )
        simple_cell = TableCell(content=[_para("Simple\n"), _terminal()])

        desired = _doc(
            _tab("t1", [_terminal(1)]),
            _tab(
                "t2",
                [
                    StructuralElement(
                        table=Table(
                            table_rows=[
                                TableRow(table_cells=[multi_para_cell, simple_cell])
                            ],
                            columns=2,
                            rows=1,
                        )
                    ),
                    _terminal(),
                ],
            ),
        )

        batches = reconcile_batches(base, desired)
        req_types = _collect_request_types(batches)

        assert "insertTable" in req_types

        insert_texts = _get_requests_of_type(batches, "insert_text")
        all_text = "".join(r.text or "" for r in insert_texts)
        assert "Line 1" in all_text
        assert "Line 2" in all_text
        assert "Simple" in all_text


class TestBulletEdgeCases:
    """Edge cases for bullet/list handling."""

    def test_bullet_paragraph_text_and_style_change(self) -> None:
        """Changing both text and bullet style simultaneously."""
        bullet_list = DocList(
            list_properties=ListProperties(
                nesting_levels=[
                    NestingLevel(
                        bullet_alignment="START",
                        glyph_symbol="\u25cf",
                        glyph_format="%0",
                        indent_first_line=Dimension(magnitude=18, unit="PT"),
                        indent_start=Dimension(magnitude=36, unit="PT"),
                        start_number=1,
                        text_style=TextStyle(underline=False),
                    )
                ]
            )
        )

        base = _single_doc(
            [
                StructuralElement(
                    start_index=1,
                    end_index=8,
                    paragraph=Paragraph(
                        elements=[
                            ParagraphElement(text_run=TextRun(content="Item 1\n")),
                        ],
                        bullet=Bullet(list_id="list1"),
                        paragraph_style=ParagraphStyle(
                            named_style_type="NORMAL_TEXT",
                            indent_first_line=Dimension(magnitude=18, unit="PT"),
                            indent_start=Dimension(magnitude=36, unit="PT"),
                        ),
                    ),
                ),
                _terminal(8),
            ],
            lists={"list1": bullet_list},
        )

        desired = _single_doc(
            [
                StructuralElement(
                    paragraph=Paragraph(
                        elements=[
                            ParagraphElement(
                                text_run=TextRun(
                                    content="Modified item\n",
                                    text_style=TextStyle(bold=True),
                                )
                            ),
                        ],
                        bullet=Bullet(list_id="list1"),
                        paragraph_style=ParagraphStyle(
                            named_style_type="NORMAL_TEXT",
                            indent_first_line=Dimension(magnitude=18, unit="PT"),
                            indent_start=Dimension(magnitude=36, unit="PT"),
                        ),
                    ),
                ),
                _terminal(),
            ],
            lists={"list1": bullet_list},
        )

        batches = reconcile_batches(base, desired)
        reqs = _flat_requests(batches)

        # Should have text edit requests
        assert len(reqs) >= 1
        # Should NOT recreate bullets (bullet unchanged)
        create_bullet_reqs = [r for r in reqs if r.create_paragraph_bullets is not None]
        assert len(create_bullet_reqs) == 0, (
            "Bullet was unnecessarily recreated when only text changed"
        )


# ===========================================================================
# 17. Footnote content editing
# ===========================================================================


class TestFootnoteContent:
    """Editing content inside an existing footnote."""

    def test_edit_footnote_body(self) -> None:
        """Changing text inside a footnote should produce content update."""
        base = _single_doc(
            [
                StructuralElement(
                    start_index=1,
                    end_index=12,
                    paragraph=Paragraph(
                        elements=[
                            ParagraphElement(
                                start_index=1,
                                end_index=11,
                                text_run=TextRun(content="Some text"),
                            ),
                            ParagraphElement(
                                start_index=11,
                                end_index=12,
                                footnote_reference=FootnoteReference(
                                    footnote_id="fn1",
                                ),
                            ),
                        ],
                        paragraph_style=ParagraphStyle(named_style_type="NORMAL_TEXT"),
                    ),
                ),
                _terminal(12),
            ],
            footnotes={
                "fn1": Footnote(
                    footnote_id="fn1",
                    content=[
                        _indexed_para("Old footnote text\n", 0),
                        _indexed_para("\n", 18),
                    ],
                ),
            },
        )

        desired = _single_doc(
            [
                StructuralElement(
                    paragraph=Paragraph(
                        elements=[
                            ParagraphElement(text_run=TextRun(content="Some text")),
                            ParagraphElement(
                                footnote_reference=FootnoteReference(
                                    footnote_id="fn1",
                                ),
                            ),
                        ],
                        paragraph_style=ParagraphStyle(named_style_type="NORMAL_TEXT"),
                    ),
                ),
                _terminal(),
            ],
            footnotes={
                "fn1": Footnote(
                    footnote_id="fn1",
                    content=[
                        _para("New footnote text\n"),
                        _terminal(),
                    ],
                ),
            },
        )

        batches = reconcile_batches(base, desired)
        reqs = _flat_requests(batches)

        # Should have requests targeting footnote segment
        found_fn = any(
            (
                r.insert_text is not None
                and r.insert_text.location
                and r.insert_text.location.segment_id == "fn1"
            )
            or (
                r.delete_content_range is not None
                and r.delete_content_range.range
                and r.delete_content_range.range.segment_id == "fn1"
            )
            for r in reqs
        )
        assert found_fn, "No request targets footnote segment fn1"
