"""Regression tests for updateParagraphStyle with pageBreakBefore inside a table.

Bug: when a cell's trailing paragraph is matched to a shorter desired paragraph,
the lowering emits updateParagraphStyle for the matched range with a fields
mask that includes ``pageBreakBefore``.  Google Docs rejects this with HTTP
400 because pageBreakBefore cannot be updated for paragraphs inside tables,
headers, footers, or footnotes.

See https://developers.google.com/docs/api/reference/rest/v1/documents#paragraphstyle

These tests assert directly on the lowered requests (not via the mock).
"""

from __future__ import annotations

from extradoc.api_types._generated import (
    Paragraph,
    ParagraphElement,
    ParagraphStyle,
    StructuralElement,
    Table,
    TableCell,
    TableRow,
    TextRun,
)
from extradoc.indexer import utf16_len
from extradoc.reconcile_v3.api import reconcile_batches

from .helpers import assert_batches_within_base, make_indexed_terminal
from .test_lower import make_indexed_doc


def _rich_trailing_style() -> ParagraphStyle:
    """ParagraphStyle that Google Docs puts on trailing cell paragraphs.

    Includes ``pageBreakBefore=False`` plus border fields, matching what the
    live API returns for an empty trailing paragraph inside a table cell.
    """
    return ParagraphStyle.model_validate(
        {
            "direction": "LEFT_TO_RIGHT",
            "lineSpacing": 100.0,
            "namedStyleType": "NORMAL_TEXT",
            "pageBreakBefore": False,
            "keepLinesTogether": False,
            "keepWithNext": False,
            "avoidWidowAndOrphan": False,
        }
    )


def _plain_style() -> ParagraphStyle:
    return ParagraphStyle.model_validate(
        {
            "direction": "LEFT_TO_RIGHT",
            "lineSpacing": 100.0,
            "namedStyleType": "NORMAL_TEXT",
        }
    )


def _indexed_para_with_style(
    text: str, start: int, style: ParagraphStyle
) -> StructuralElement:
    return StructuralElement(
        start_index=start,
        end_index=start + utf16_len(text),
        paragraph=Paragraph(
            elements=[ParagraphElement(text_run=TextRun(content=text))],
            paragraph_style=style,
        ),
    )


def _make_cell(
    cell_start: int,
    text: str,
    *,
    with_trailing_rich: bool,
) -> TableCell:
    """Build a cell containing a content paragraph plus (optionally) a trailing
    paragraph carrying the rich pageBreakBefore-bearing style.
    """
    content_start = cell_start + 1
    para = _indexed_para_with_style(text, content_start, _plain_style())
    assert para.end_index is not None
    content: list[StructuralElement] = [para]
    if with_trailing_rich:
        trailing = _indexed_para_with_style(
            "\n", para.end_index, _rich_trailing_style()
        )
        content.append(trailing)
        assert trailing.end_index is not None
        end = trailing.end_index
    else:
        end = para.end_index
    return TableCell(start_index=cell_start, end_index=end, content=content)


def _build_1x1_table_doc(
    *,
    cell_text: str,
    with_trailing_rich: bool,
) -> object:
    table_start = 1
    row_start = table_start + 1  # skip table opener
    cell_start = row_start + 1  # skip row opener
    cell = _make_cell(cell_start, cell_text, with_trailing_rich=with_trailing_rich)
    assert cell.end_index is not None
    row_end = cell.end_index
    table_end = row_end
    table_el = StructuralElement(
        start_index=table_start,
        end_index=table_end,
        table=Table(
            rows=1,
            columns=1,
            table_rows=[
                TableRow(
                    start_index=row_start,
                    end_index=row_end,
                    table_cells=[cell],
                )
            ],
        ),
    )
    return make_indexed_doc(
        body_content=[table_el, make_indexed_terminal(table_end)],
    )


def _update_para_style_fields(batches: list[object]) -> list[tuple[int, int, str]]:
    """Extract (start_index, end_index, fields_mask) for every updateParagraphStyle."""
    out: list[tuple[int, int, str]] = []
    for batch in batches:
        reqs = getattr(batch, "requests", None) or []
        for req in reqs:
            ups = getattr(req, "update_paragraph_style", None)
            if ups is None:
                continue
            rng = ups.range
            assert rng is not None
            fields = ups.fields or ""
            out.append((rng.start_index or 0, rng.end_index or 0, fields))
    return out


def _table_span(doc: object) -> tuple[int, int]:
    """Return (table_start, table_end) for the first table in doc.tabs[0]."""
    tabs = doc.tabs  # type: ignore[attr-defined]
    body = tabs[0].document_tab.body
    for c in body.content or []:
        if c.table is not None:
            assert c.start_index is not None and c.end_index is not None
            return c.start_index, c.end_index
    raise AssertionError("no table found in doc")


def _build_2x1_table_doc(
    *,
    cell_texts: tuple[str, str],
    with_trailing_rich: bool,
) -> object:
    """Build a doc with a 2-row 1-column table."""
    table_start = 1
    row0_start = table_start + 1
    cell0 = _make_cell(
        row0_start + 1, cell_texts[0], with_trailing_rich=with_trailing_rich
    )
    assert cell0.end_index is not None
    row0_end = cell0.end_index
    row1_start = row0_end
    cell1 = _make_cell(
        row1_start + 1, cell_texts[1], with_trailing_rich=with_trailing_rich
    )
    assert cell1.end_index is not None
    row1_end = cell1.end_index
    table_end = row1_end
    table_el = StructuralElement(
        start_index=table_start,
        end_index=table_end,
        table=Table(
            rows=2,
            columns=1,
            table_rows=[
                TableRow(
                    start_index=row0_start, end_index=row0_end, table_cells=[cell0]
                ),
                TableRow(
                    start_index=row1_start, end_index=row1_end, table_cells=[cell1]
                ),
            ],
        ),
    )
    return make_indexed_doc(
        body_content=[table_el, make_indexed_terminal(table_end)],
    )


def test_cell_text_edit_does_not_emit_pagebreakbefore_in_mask() -> None:
    """Editing a cell's text must not emit updateParagraphStyle with
    ``pageBreakBefore`` in the fields mask for any range that sits inside
    the table — Google Docs returns HTTP 400 for that combination.
    """
    # 2-row table; edit only the second cell's text.  First cell identical →
    # the table matches at structural level and the per-cell UpdateBodyContentOp
    # path is exercised (which is where the bug lives).
    base = _build_2x1_table_doc(
        cell_texts=("A1-longish-stable-content\n", "B1\n"),
        with_trailing_rich=True,
    )
    desired = _build_2x1_table_doc(
        cell_texts=("A1-longish-stable-content\n", "B1-edited\n"),
        with_trailing_rich=False,
    )

    batches = reconcile_batches(base, desired)  # type: ignore[arg-type]
    assert_batches_within_base(base, batches)
    table_start, table_end = _table_span(base)

    offenders: list[tuple[int, int, str]] = []
    for start, end, fields in _update_para_style_fields(batches):
        mask_fields = {f.strip() for f in fields.split(",") if f.strip()}
        # Range overlaps the table (inclusive of the trailing cell paragraph)
        overlaps_table = start < table_end and end > table_start
        if overlaps_table and "pageBreakBefore" in mask_fields:
            offenders.append((start, end, fields))

    assert not offenders, (
        "updateParagraphStyle emitted with pageBreakBefore in mask for a "
        f"range inside the table (would 400 from real API): {offenders}"
    )


def test_cell_row_append_does_not_emit_pagebreakbefore_in_mask() -> None:
    """Appending a row to an existing table must not emit updateParagraphStyle
    with ``pageBreakBefore`` in the fields mask for any range inside the table.
    """
    # Base: 1x1 table with "A1\n" + rich trailing
    base = _build_1x1_table_doc(cell_text="A1\n", with_trailing_rich=True)

    # Desired: 2x1 table.  Build manually using same pattern as _build_1x1_table_doc.
    table_start = 1
    row0_start = table_start + 1
    cell0 = _make_cell(row0_start + 1, "A1\n", with_trailing_rich=False)
    assert cell0.end_index is not None
    row0_end = cell0.end_index
    row1_start = row0_end
    cell1 = _make_cell(row1_start + 1, "A2\n", with_trailing_rich=False)
    assert cell1.end_index is not None
    row1_end = cell1.end_index
    table_end = row1_end
    table_el = StructuralElement(
        start_index=table_start,
        end_index=table_end,
        table=Table(
            rows=2,
            columns=1,
            table_rows=[
                TableRow(
                    start_index=row0_start, end_index=row0_end, table_cells=[cell0]
                ),
                TableRow(
                    start_index=row1_start, end_index=row1_end, table_cells=[cell1]
                ),
            ],
        ),
    )
    desired = make_indexed_doc(
        body_content=[table_el, make_indexed_terminal(table_end)],
    )

    batches = reconcile_batches(base, desired)  # type: ignore[arg-type]
    assert_batches_within_base(base, batches)
    # The base table span is what matters — requests run against base indices.
    base_table_start, base_table_end = _table_span(base)

    offenders: list[tuple[int, int, str]] = []
    for start, end, fields in _update_para_style_fields(batches):
        mask_fields = {f.strip() for f in fields.split(",") if f.strip()}
        overlaps_table = start < base_table_end and end > base_table_start
        if overlaps_table and "pageBreakBefore" in mask_fields:
            offenders.append((start, end, fields))

    assert not offenders, (
        "updateParagraphStyle emitted with pageBreakBefore in mask for a "
        f"range inside the table (would 400 from real API): {offenders}"
    )
