"""Regression tests: editing only a few table cells must emit a bounded number of requests.

These tests encode the invariant that a single-cell text edit in an HTML-serialized
table (one with multi-paragraph cells elsewhere) must not blow up into dozens of
``insertText`` / ``updateTextStyle`` requests on cells the user didn't touch.

BACKGROUND
----------
For HTML-formatted tables (``<table>`` blocks in markdown), the serializer flattens
each cell into a single paragraph joined by spaces. When the user edits a few cells,
the 3-way merge in ``diffmerge/apply_ops.py`` walks ALL rows/cells of the table via
``_merge_changed_table`` -> ``_merge_table_cell``. For cells whose base has N>1
paragraphs but whose desired (from the lossy markdown parse) has 1 paragraph,
``_merge_table_cell`` overwrites base's para 0 text with the flattened desired text
and keeps base's paras 1..N-1 untouched. The resulting desired cell is corrupt
(para 0 contains the full flattened text, duplicating the content in paras 1..N-1),
which makes the reconciler emit spurious ``insertText`` + ``updateTextStyle``
requests for every multi-paragraph cell in the table -- even if the user edited
just one unrelated cell.

See: extradoc/src/extradoc/diffmerge/apply_ops.py::_merge_table_cell (positional
per-paragraph merge assumes base and desired have the same number of paragraphs).

These tests are marked xfail until the merge is fixed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from extradoc.api_types._generated import (
    Body,
    Color,
    Document,
    DocumentTab,
    OptionalColor,
    Paragraph,
    ParagraphElement,
    ParagraphStyle,
    ParagraphStyleNamedStyleType,
    RgbColor,
    StructuralElement,
    Tab,
    Table,
    TableCell,
    TableCellStyle,
    TableRow,
    TabProperties,
    TextRun,
)
from extradoc.comments._types import DocumentWithComments, FileComments
from extradoc.reconcile_v3.api import reconcile_batches
from extradoc.serde.markdown import MarkdownSerde

from .helpers import reindex_document, simulate_ops_against_base

if TYPE_CHECKING:
    from pathlib import Path

_md_serde = MarkdownSerde()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _para(text: str) -> StructuralElement:
    return StructuralElement(
        paragraph=Paragraph(
            elements=[ParagraphElement(text_run=TextRun(content=text + "\n"))],
            paragraph_style=ParagraphStyle(
                named_style_type=ParagraphStyleNamedStyleType.NORMAL_TEXT,
            ),
        )
    )


def _multi_para_cell(paras: list[str]) -> TableCell:
    """A cell whose content is N paragraphs (simulates real Google Docs structure)."""
    return TableCell(
        content=[_para(t) for t in paras],
        table_cell_style=TableCellStyle(),
    )


def _single_para_cell(text: str) -> TableCell:
    return TableCell(
        content=[_para(text)],
        table_cell_style=TableCellStyle(),
    )


def _grey_header_cell(text: str) -> TableCell:
    """A header cell with a background color, which forces the serializer to emit HTML."""
    return TableCell(
        content=[_para(text)],
        table_cell_style=TableCellStyle(
            background_color=OptionalColor(
                color=Color(rgb_color=RgbColor(red=0.85, green=0.85, blue=0.85))
            )
        ),
    )


def _make_doc_with_table(rows: list[TableRow]) -> Document:
    n_cols = max((len(r.table_cells or []) for r in rows), default=0)
    table_se = StructuralElement(
        table=Table(table_rows=rows, rows=len(rows), columns=n_cols),
    )
    body = Body(content=[table_se, _para("")])
    tab = Tab(
        tab_properties=TabProperties(tab_id="t.0", title="Tab 1"),
        document_tab=DocumentTab(body=body),
    )
    return Document(document_id="test-doc", title="Test", tabs=[tab])


def _bundle(doc: Document) -> DocumentWithComments:
    return DocumentWithComments(
        document=doc,
        comments=FileComments(file_id=doc.document_id or ""),
    )


def _tab_md_path(folder: Path) -> Path:
    return folder / "tabs" / "Tab_1.md"


def _count_requests(batches: list) -> tuple[int, dict[str, int]]:
    total = 0
    by_type: dict[str, int] = {}
    for b in batches:
        for req in b.requests or []:
            total += 1
            d = (
                req.model_dump(exclude_none=True, by_alias=True)
                if hasattr(req, "model_dump")
                else req
            )
            for k in d:
                by_type[k] = by_type.get(k, 0) + 1
    return total, by_type


def _assert_no_structural_row_ops(by_type: dict[str, int]) -> None:
    assert "insertTableRow" not in by_type, f"Unexpected insertTableRow in {by_type}"
    assert "deleteTableRow" not in by_type, f"Unexpected deleteTableRow in {by_type}"
    assert "insertTableColumn" not in by_type, (
        f"Unexpected insertTableColumn in {by_type}"
    )
    assert "deleteTableColumn" not in by_type, (
        f"Unexpected deleteTableColumn in {by_type}"
    )


# ---------------------------------------------------------------------------
# Test 1: minimal repro — 1-cell edit in a 3-row table with one multi-paragraph cell
# ---------------------------------------------------------------------------


def test_single_cell_edit_does_not_corrupt_multiparagraph_cells(tmp_path: Path) -> None:
    """Edit ONE cell in row 2 col 0; row 1 col 1 (multi-para cell) must stay untouched
    in the merged ``desired`` document (structural invariant, no API indices needed)."""
    header = TableRow(
        table_cells=[
            _grey_header_cell("Sr"),
            _grey_header_cell("Question"),
        ]
    )
    row1 = TableRow(
        table_cells=[
            _single_para_cell("1"),
            _multi_para_cell(
                [
                    "First sentence of the long question.",
                    "Second sentence continuing the question.",
                    "Third sentence with more context.",
                ]
            ),
        ]
    )
    row2 = TableRow(
        table_cells=[
            _single_para_cell("2"),
            _single_para_cell("Short question"),
        ]
    )
    doc = reindex_document(_make_doc_with_table([header, row1, row2]))

    folder = tmp_path / "doc"
    _md_serde.serialize(_bundle(doc), folder)

    # User edit: change "2" -> "2." in the Sr cell of row 2.
    md_path = _tab_md_path(folder)
    md = md_path.read_text()
    # Make sure the HTML table was emitted (required for the bug to reproduce).
    assert "<table>" in md, "test precondition: serializer must emit an HTML table"
    edited = md.replace("<td>2</td>", "<td>2.</td>", 1)
    assert edited != md, "edit did not match"
    md_path.write_text(edited)

    result = _md_serde.deserialize(folder)

    # The unrelated multi-paragraph cell at row 1 col 1 must survive the merge
    # byte-for-byte identical to base (it was not touched in markdown).
    def _cell(doc: Document, r: int, c: int) -> TableCell:
        body_content = doc.tabs[0].document_tab.body.content  # type: ignore[union-attr,index]
        for se in body_content or []:
            if se.table is not None:
                return se.table.table_rows[r].table_cells[c]  # type: ignore[index]
        raise AssertionError("no table in doc")

    base_cell = _cell(result.base.document, 1, 1)
    desired_cell = _cell(result.desired.document, 1, 1)

    def _cell_para_texts(cell: TableCell) -> list[str]:
        out: list[str] = []
        for cse in cell.content or []:
            if cse.paragraph is None:
                continue
            t = "".join(
                (pe.text_run.content or "")
                for pe in (cse.paragraph.elements or [])
                if pe.text_run
            )
            out.append(t)
        return out

    base_texts = _cell_para_texts(base_cell)
    desired_texts = _cell_para_texts(desired_cell)
    assert desired_texts == base_texts, (
        "Unrelated multi-paragraph cell was corrupted by _merge_table_cell. "
        f"base paragraphs={base_texts!r}, desired paragraphs={desired_texts!r}"
    )

    # Bonus: the reconciler must not emit structural row/column ops for this edit.
    batches = reconcile_batches(result.base.document, result.desired.document)
    _total, by_type = _count_requests(batches)
    _assert_no_structural_row_ops(by_type)

    # Range-validity oracle: every emitted op must lie within the base tree.
    base_dict = result.base.document.model_dump(by_alias=True, exclude_none=True)
    all_reqs: list = []
    for b in batches:
        for req in b.requests or []:
            all_reqs.append(req.model_dump(by_alias=True, exclude_none=True))
    assert simulate_ops_against_base(base_dict, all_reqs) == []


# ---------------------------------------------------------------------------
# Test 2: Tab_1.md-like scenario — edit all Sr cells in a 25-row table
# ---------------------------------------------------------------------------


def test_sr_column_edit_is_bounded(tmp_path: Path) -> None:
    """Edit only the Sr column; request count must scale with edits, not total cells."""
    header = TableRow(
        table_cells=[
            _grey_header_cell("Sr"),
            _grey_header_cell("Section"),
            _grey_header_cell("Question"),
            _grey_header_cell("Answer"),
            _grey_header_cell("Filter"),
        ]
    )
    rows = [header]
    n_data_rows = 24
    for i in range(1, n_data_rows + 1):
        rows.append(
            TableRow(
                table_cells=[
                    _single_para_cell(str(i)),
                    _single_para_cell(f"Section {i}"),
                    # Every 3rd row has a multi-paragraph Question cell.
                    _multi_para_cell(
                        [
                            f"Question {i} sentence one.",
                            f"Question {i} sentence two.",
                            f"Question {i} sentence three.",
                        ]
                    )
                    if i % 3 == 0
                    else _single_para_cell(f"Question {i}"),
                    _multi_para_cell(
                        [
                            f"Answer {i} part A.",
                            f"Answer {i} part B.",
                        ]
                    )
                    if i % 4 == 0
                    else _single_para_cell(f"Answer {i}"),
                    _single_para_cell(f"Filter {i}"),
                ]
            )
        )
    doc = reindex_document(_make_doc_with_table(rows))

    folder = tmp_path / "doc"
    _md_serde.serialize(_bundle(doc), folder)

    md_path = _tab_md_path(folder)
    md = md_path.read_text()
    assert "<table>" in md, "test precondition: serializer must emit an HTML table"

    # Edit every Sr cell: "<td>N</td>" -> "<td>N.</td>" for N = 1..24.
    import re as _re

    first_tds: list[str] = []

    def _edit(m: _re.Match[str]) -> str:
        val = m.group(1)
        first_tds.append(val)
        return f"<td>{val}.</td>"

    # Replace the FIRST numeric <td>N</td> within each <tr>...</tr> (the Sr column).
    def _per_row(row_m: _re.Match[str]) -> str:
        body = row_m.group(0)
        new_body, _ = _re.subn(r"<td>(\d+)</td>", _edit, body, count=1)
        return new_body

    edited = _re.sub(r"<tr>.*?</tr>", _per_row, md, flags=_re.DOTALL)
    assert len(first_tds) == n_data_rows, (
        f"expected {n_data_rows} Sr cells, matched {len(first_tds)}"
    )
    md_path.write_text(edited)

    result = _md_serde.deserialize(folder)
    batches = reconcile_batches(result.base.document, result.desired.document)

    total, by_type = _count_requests(batches)
    _assert_no_structural_row_ops(by_type)
    # 24 cell-text edits; allow ~2x headroom for insertText+updateTextStyle pairs.
    assert total < 60, (
        f"expected <60 requests for {n_data_rows} cell edits, got {total}: {by_type}"
    )

    # Range-validity oracle.
    base_dict = result.base.document.model_dump(by_alias=True, exclude_none=True)
    all_reqs: list = []
    for b in batches:
        for req in b.requests or []:
            all_reqs.append(req.model_dump(by_alias=True, exclude_none=True))
    assert simulate_ops_against_base(base_dict, all_reqs) == []
