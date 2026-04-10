"""Regression test for SUPERSCRIPT-bleed bug on a table cell containing

    Run A: "ResidentialStatus"  (17 chars, baselineOffset=NONE)
    Run B: "4"                  (1 char,  baselineOffset=SUPERSCRIPT)
    Run C: " \\n"                (2 chars, baselineOffset=NONE)

edited by the user inserting one space between "Residential" and "Status"
so that the desired paragraph becomes

    Run A: "Residential Status" (18 chars, NONE)
    Run B: "4"                  (1 char,  SUPERSCRIPT)
    Run C: " \\n"                (2 chars, NONE)

Observed on the real FORM-15G document (doc
``1FkRTeU852Mxg0OJh684MXutDxW7ubTkiA6_EXyRce54``): the reconciler emitted a
whole-paragraph ``insertText "Residential Status4 "`` plus three
``updateTextStyle`` ranges sized by the BASE run widths (17/1/2) — meaning
SUPERSCRIPT landed on the ``s`` in ``Status`` and the rendered cell showed
``Residential Statuˢ⁴`` on re-pull.

The root cause was ``content_align.align_content`` blindly pre-matching
``base[-1] ↔ desired[-1]``. When the base cell had extra trailing
bare-``\\n`` paragraphs that were removed in desired, the forced terminal
pairing coupled a bare-``\\n`` paragraph with a real-content paragraph,
leaving the real paragraph unmatched in ``base_deletes``. Downstream then
emitted a delete-whole-paragraph + insert-whole-paragraph plan instead of
the surgical one-space edit.

Fix: peel the asymmetric excess of trailing bare-``\\n`` paragraphs into
deletes / inserts BEFORE the terminal pre-match, and skip the pre-match
altogether when no common bare-``\\n`` tail exists. See
``content_align.py::align_content``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from extradoc.api_types._generated import (
    Body,
    Document,
    DocumentTab,
    NamedStyles,
    Paragraph,
    ParagraphElement,
    ParagraphStyle,
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
    TextStyleBaselineOffset,
)
from extradoc.reconcile_v3.api import reconcile_batches

BO = TextStyleBaselineOffset


# ---------------------------------------------------------------------------
# Synthetic builders
# ---------------------------------------------------------------------------


def _text_element(text: str, baseline: BO, start: int) -> tuple[ParagraphElement, int]:
    end = start + len(text)
    return (
        ParagraphElement(
            start_index=start,
            end_index=end,
            text_run=TextRun(
                content=text, text_style=TextStyle(baseline_offset=baseline)
            ),
        ),
        end,
    )


def _content_para(
    runs: list[tuple[str, BO]], start: int
) -> tuple[StructuralElement, int]:
    elements: list[ParagraphElement] = []
    pos = start
    for text, baseline in runs:
        el, pos = _text_element(text, baseline, pos)
        elements.append(el)
    return (
        StructuralElement(
            start_index=start,
            end_index=pos,
            paragraph=Paragraph(
                elements=elements,
                paragraph_style=ParagraphStyle(named_style_type="NORMAL_TEXT"),
            ),
        ),
        pos,
    )


def _bare_newline_para(start: int) -> tuple[StructuralElement, int]:
    return (
        StructuralElement(
            start_index=start,
            end_index=start + 1,
            paragraph=Paragraph(
                elements=[
                    ParagraphElement(
                        start_index=start,
                        end_index=start + 1,
                        text_run=TextRun(content="\n"),
                    )
                ],
                paragraph_style=ParagraphStyle(named_style_type="NORMAL_TEXT"),
            ),
        ),
        start + 1,
    )


def _build_cell(
    start: int,
    content_runs: list[tuple[str, BO]],
    trailing_bare_nl: int,
) -> tuple[TableCell, int]:
    """Build a table cell with one content paragraph + N bare-\\n trailing paragraphs."""
    # Cell has a 1-char overhead before its first paragraph.
    para, pos = _content_para(content_runs, start + 1)
    content: list[StructuralElement] = [para]
    for _ in range(trailing_bare_nl):
        bp, pos = _bare_newline_para(pos)
        content.append(bp)
    return TableCell(start_index=start, end_index=pos, content=content), pos


def _build_doc(
    content_runs: list[tuple[str, BO]],
    trailing_bare_nl: int,
) -> Document:
    """Build a small document whose body contains a 1-row 2-column table.

    The first cell carries the test paragraph (plus optional trailing bare
    ``\\n`` paragraphs). The second cell is a fixed filler so the table
    is confidently matchable across base/desired (``_table_sim`` needs at
    least one stable cell to score above the match threshold).

    Body layout (all indices in UTF-16 code units):

        [0..1)   SectionBreak
        [1..2)   bare-\\n paragraph (pre-table flank)
        [2..P)   Table(1x2)
        [P..P+1) bare-\\n paragraph (terminal)
    """
    sb = StructuralElement(
        start_index=0,
        end_index=1,
        section_break=SectionBreak(section_style=SectionStyle()),
    )
    pre_flank, _ = _bare_newline_para(1)
    # Table starts at 2, row at 3, cell1 at 4.
    cell1, cell1_end = _build_cell(4, content_runs, trailing_bare_nl)
    filler_cell, cell2_end = _build_cell(
        cell1_end, [("Filler text\n", BO.NONE)], trailing_bare_nl=0
    )
    row = TableRow(
        start_index=3, end_index=cell2_end, table_cells=[cell1, filler_cell]
    )
    table_el = StructuralElement(
        start_index=2,
        end_index=cell2_end,
        table=Table(rows=1, columns=2, table_rows=[row]),
    )
    term, _ = _bare_newline_para(cell2_end)
    body = Body(content=[sb, pre_flank, table_el, term])
    tab = Tab(
        tab_properties=TabProperties(tab_id="t1", title="t", index=0),
        document_tab=DocumentTab(
            body=body,
            headers={},
            footers={},
            footnotes={},
            lists={},
            named_styles=NamedStyles(styles=[]),
            document_style={},
            inline_objects={},
        ),
    )
    return Document(document_id="d", tabs=[tab])


def _collect_requests(batches) -> list[dict]:
    out: list[dict] = []
    for batch in batches:
        for req in batch.requests or []:
            out.append(req.model_dump(by_alias=True, exclude_none=True))
    return out


def _find_cell_para_start(doc: Document) -> int:
    """Return the UTF-16 start index of the first run in the test cell's first paragraph."""
    tab = (doc.tabs or [])[0]
    body = tab.document_tab.body  # type: ignore[union-attr]
    table_el = body.content[2]  # type: ignore[union-attr]
    cell = table_el.table.table_rows[0].table_cells[0]  # type: ignore[union-attr]
    para = cell.content[0].paragraph  # type: ignore[union-attr]
    first_el = para.elements[0]  # type: ignore[union-attr]
    assert first_el.start_index is not None
    return first_el.start_index


# ---------------------------------------------------------------------------
# Test 1: fully-specified synthetic case
# ---------------------------------------------------------------------------


def test_single_space_insert_surgical_ops_synthetic() -> None:
    """Inserting one space inside a ``...Status4 \\n`` paragraph (whose cell
    has two extra trailing bare-``\\n`` paragraphs that desired removes)
    must emit a SURGICAL plan:

    * exactly one ``insertText`` request with text ``" "`` at the position
      of ``S`` in ``Status``
    * exactly two ``deleteContentRange`` ops (the two trailing bare-\\n
      paragraphs being removed)
    * ZERO ``updateTextStyle`` ops — the critical anti-regression check;
      the original bug emitted updateTextStyle ranges sized by BASE run
      widths, causing SUPERSCRIPT to bleed onto the ``s`` in ``Status``.
    """
    base_runs = [
        ("ResidentialStatus", BO.NONE),
        ("4", BO.SUPERSCRIPT),
        (" \n", BO.NONE),
    ]
    desired_runs = [
        ("Residential Status", BO.NONE),
        ("4", BO.SUPERSCRIPT),
        (" \n", BO.NONE),
    ]

    # The bug only reproduces when base has extra trailing bare-newline
    # paragraphs that desired has removed — this is what drives
    # ``align_content`` to force-pair the base bare-\n terminal with the
    # desired real-content paragraph. The real FORM-15G fixture had two
    # trailing bare-\n paragraphs in the base cell; we match that shape.
    base = _build_doc(base_runs, trailing_bare_nl=2)
    desired = _build_doc(desired_runs, trailing_bare_nl=0)

    # "Status" starts 11 characters into the base paragraph (after
    # "Residential"). That is where the single inserted space belongs.
    para_start = _find_cell_para_start(base)
    expected_insert_index = para_start + len("Residential")

    batches = reconcile_batches(base, desired)
    ops = _collect_requests(batches)

    # 1. Exactly 3 ops: 2 deletes (of trailing bare-\n paragraphs) + 1 insert.
    assert len(ops) == 3, (
        f"expected exactly 3 ops, got {len(ops)}: "
        f"{[list(o.keys()) for o in ops]}\n{json.dumps(ops, indent=2)}"
    )

    # 2. Exactly one insertText op.
    insert_ops = [o for o in ops if "insertText" in o]
    assert len(insert_ops) == 1, (
        f"expected exactly 1 insertText op, got {len(insert_ops)}: {insert_ops}"
    )
    it = insert_ops[0]["insertText"]

    # 3. The inserted text is exactly one space.
    assert it["text"] == " ", f"expected text=' ', got {it['text']!r}"

    # 4. The index is the start position of ``S`` in ``Status`` in base coords.
    assert it["location"]["index"] == expected_insert_index, (
        f"expected index={expected_insert_index}, got {it['location']['index']}"
    )

    # 5. CRITICAL: no updateTextStyle anywhere. A surgical one-space insert
    #    whose style matches the surrounding NONE-baseline run must not
    #    emit any style updates — the inherited style from the left
    #    neighbour does the job. The original bug emitted updateTextStyle
    #    ranges sized by the BASE run widths (17/1/2) after a full
    #    delete+reinsert of the paragraph, causing SUPERSCRIPT to land on
    #    the ``s`` in ``Status`` on re-pull.
    update_style_ops = [o for o in ops if "updateTextStyle" in o]
    assert not update_style_ops, (
        "expected zero updateTextStyle ops; a single-space insertion whose "
        "style matches the surrounding run must not emit any style updates. "
        f"Got: {update_style_ops}"
    )

    # 6. Exactly two deleteContentRange ops, each a 1-char deletion of a
    #    trailing bare-\n paragraph. They must NOT overlap the content
    #    paragraph — only the bare-\n tails.
    delete_ops = [o for o in ops if "deleteContentRange" in o]
    assert len(delete_ops) == 2, (
        f"expected exactly 2 deleteContentRange ops (for the 2 trailing "
        f"bare-\\n paragraphs), got {len(delete_ops)}: {delete_ops}"
    )
    content_para_end = para_start + len("ResidentialStatus4 \n")
    for d in delete_ops:
        r = d["deleteContentRange"]["range"]
        assert r["endIndex"] - r["startIndex"] == 1, (
            f"expected 1-char delete, got {r}"
        )
        assert r["startIndex"] >= content_para_end, (
            f"delete at {r} overlaps the content paragraph (ends at "
            f"{content_para_end}); the content paragraph must be preserved "
            "surgically, not deleted"
        )


# ---------------------------------------------------------------------------
# Test 2: fixture-based simulation
# ---------------------------------------------------------------------------

_DEBUG_DIR = Path("/tmp/qa-v4/pull1/.debug")


def _apply_ops_to_cell(
    runs: list[tuple[str, str, BO]],
    ops: list[dict],
    cell_start: int,
    cell_end: int,
) -> list[tuple[str, BO]]:
    """Tiny simulator for the subset of batchUpdate ops we care about.

    ``runs`` is the initial per-character state of the entire DOCUMENT
    encoded as (char, kind, baseline) triples where kind is ``"text"`` for
    editable text characters. Only the characters within the cell's range
    are compared afterwards. The simulator processes ops in the ORDER they
    appear in the batch — which matches the Google Docs batchUpdate
    execution model (sequential, each subsequent op sees the effects of
    the previous ops). The reconciler is responsible for emitting ops in
    an index-safe order.

    Returns the resulting list of (text, baseline) runs for the cell's
    FIRST paragraph only (up to and including the first ``\\n``).
    """
    # ``chars`` is a list of (char, baseline_offset) pairs; index == doc
    # position (approximately — we pad out of-range with None to keep the
    # arithmetic simple).
    chars: list[tuple[str, BO | None]] = [("?", None)] * (cell_end + 1)
    pos = 0
    for text, _kind, baseline in runs:
        for ch in text:
            if pos < len(chars):
                chars[pos] = (ch, baseline)
            else:
                chars.append((ch, baseline))
            pos += 1

    for op in ops:
        if "insertText" in op:
            it = op["insertText"]
            idx = it["location"]["index"]
            text = it["text"]
            # Inherited style = left neighbour (or right if at start).
            if idx > 0 and idx - 1 < len(chars):
                inherited = chars[idx - 1][1]
            elif idx < len(chars):
                inherited = chars[idx][1]
            else:
                inherited = None
            for ch in text:
                chars.insert(idx, (ch, inherited))
                idx += 1
        elif "deleteContentRange" in op:
            r = op["deleteContentRange"]["range"]
            s = r["startIndex"]
            e = r["endIndex"]
            del chars[s:e]
        elif "updateTextStyle" in op:
            uts = op["updateTextStyle"]
            r = uts["range"]
            s = r["startIndex"]
            e = r["endIndex"]
            fields = uts.get("fields", "").split(",")
            new_baseline = uts.get("textStyle", {}).get("baselineOffset")
            if "baselineOffset" in fields and new_baseline is not None:
                for k in range(s, min(e, len(chars))):
                    ch, _ = chars[k]
                    chars[k] = (ch, BO(new_baseline))
        # Ignore other request types for simulation purposes.

    # Extract the cell's first-paragraph characters. After the ops, the
    # paragraph is bounded by ``cell_start`` up to and including the first
    # ``\n`` character at-or-after ``cell_start``.
    result_runs: list[tuple[str, BO]] = []
    current_text = ""
    current_style: BO | None = None
    k = cell_start
    while k < len(chars):
        ch, style = chars[k]
        if current_style is None:
            current_style = style if style is not None else BO.NONE
            current_text = ch
        elif style == current_style:
            current_text += ch
        else:
            result_runs.append((current_text, current_style))
            current_style = style if style is not None else BO.NONE
            current_text = ch
        k += 1
        if ch == "\n":
            break
    if current_text:
        assert current_style is not None
        result_runs.append((current_text, current_style))
    return result_runs


@pytest.mark.skipif(
    not (_DEBUG_DIR / "base_document.json").exists(),
    reason=f"debug fixture {_DEBUG_DIR} missing; run the reverted /tmp/qa-v4 scenario first",
)
def test_single_space_insert_surgical_ops_real_fixture() -> None:
    """Load the real FORM-15G fixture; assert the cell's first paragraph

    ends up with the desired 3-run shape (18/1/2, SUPERSCRIPT on the ``4``)
    and no other ``SUPERSCRIPT`` escapes into adjacent characters.
    """
    with (_DEBUG_DIR / "base_document.json").open() as f:
        base = Document.model_validate(json.load(f))

    # Build an IDEAL desired: same base, but with the user's one-space
    # edit applied correctly (Residential Status4 \n, SUPERSCRIPT on "4").
    # We modify a deep copy of the base at tab t.0, body content[8]
    # (table), row 1, cell 9 — the ResidentialStatus cell identified in
    # the task description.
    base_dict = base.model_dump(by_alias=True, exclude_none=True)
    tab_doc: dict = next(
        t for t in base_dict["tabs"] if t["tabProperties"]["tabId"] == "t.0"
    )
    body = tab_doc["documentTab"]["body"]
    table = body["content"][8]["table"]
    cell = table["tableRows"][1]["tableCells"][9]
    # Replace the cell with the *ideal* desired content: a single
    # paragraph with three runs, and NO trailing bare-\n paragraphs
    # (matches the serde output shape).
    first_para = cell["content"][0]
    first_para_elements = first_para["paragraph"]["elements"]
    # Reuse the existing run metadata so we inherit styling fields
    # (fontSize, fontFamily, ...). Only change content + baselineOffset.
    template_none = first_para_elements[0]["textRun"]["textStyle"]
    template_super = first_para_elements[1]["textRun"]["textStyle"]
    new_elements = [
        {
            "textRun": {
                "content": "Residential Status",
                "textStyle": {**template_none, "baselineOffset": "NONE"},
            }
        },
        {
            "textRun": {
                "content": "4",
                "textStyle": {**template_super, "baselineOffset": "SUPERSCRIPT"},
            }
        },
        {
            "textRun": {
                "content": " \n",
                "textStyle": {**template_none, "baselineOffset": "NONE"},
            }
        },
    ]
    first_para["paragraph"]["elements"] = new_elements
    # Remove bullet so desired mirrors the serde output shape.
    first_para["paragraph"].pop("bullet", None)
    # Drop the trailing bare-\n paragraphs (the other two in base).
    cell["content"] = [first_para]

    desired = Document.model_validate(base_dict)

    batches = reconcile_batches(base, desired)
    ops = _collect_requests(batches)

    # Collect ops that touch the Residential cell range (509..531).
    cell_ops: list[dict] = []
    for op in ops:
        body_str = json.dumps(op)
        # Any request whose indices fall within the cell range.
        import re

        matched = False
        for m in re.finditer(r'"(startIndex|endIndex|index)":\s*(\d+)', body_str):
            v = int(m.group(2))
            if 505 <= v <= 540:
                matched = True
                break
        if matched:
            cell_ops.append(op)

    # There must be at least one insertText " " at a position inside the
    # paragraph (not at the trailing \n). Exact count is tolerant because
    # the bare-\n paragraphs and the bullet require a few cleanup ops.
    space_inserts = [
        o
        for o in cell_ops
        if "insertText" in o and o["insertText"]["text"] == " "
    ]
    assert space_inserts, (
        "expected at least one insertText ' ' in the Residential cell ops; "
        f"got: {cell_ops}"
    )

    # CRITICAL: no updateTextStyle may set SUPERSCRIPT on a range whose
    # *first* character in the final document text is anything other than
    # the literal ``4``. We verify this via simulation.
    #
    # Build a simplified "runs" list for the entire base document's first
    # 540 characters and simulate the cell_ops.
    # Only the cell in question matters; we fabricate a flat list of
    # (char, style) using base[0].startIndex = 509.
    base_tab = next(
        t for t in base.tabs or [] if t.tab_properties.tab_id == "t.0"  # type: ignore[union-attr]
    )
    cell_obj = base_tab.document_tab.body.content[8].table.table_rows[1].table_cells[9]  # type: ignore[union-attr]
    base_runs_triples: list[tuple[str, str, BO]] = []
    for content_el in cell_obj.content or []:
        para = content_el.paragraph
        if para is None:
            continue
        for pe in para.elements or []:
            if pe.text_run is not None:
                tr = pe.text_run
                bo = (tr.text_style.baseline_offset if tr.text_style else None) or BO.NONE
                base_runs_triples.append((tr.content or "", "text", bo))
    # Prepend filler to align absolute indices with the cell's first para
    # starting at 509.
    pad = ("?" * 509, "text", BO.NONE)
    cell_start = 509
    cell_end = 532

    result = _apply_ops_to_cell(
        [pad, *base_runs_triples], cell_ops, cell_start, cell_end
    )

    # Expect exactly 3 runs, lengths 18/1/2, SUPERSCRIPT only on the "4".
    result_text = "".join(text for text, _ in result)
    assert result_text == "Residential Status4 \n", (
        f"expected paragraph text 'Residential Status4 \\n', got {result_text!r}; "
        f"runs={result}"
    )
    assert len(result) == 3, f"expected 3 runs, got {len(result)}: {result}"
    assert [len(t) for t, _ in result] == [18, 1, 2], (
        f"expected run lengths [18,1,2], got {[len(t) for t, _ in result]}: {result}"
    )
    assert result[0][1] == BO.NONE, (
        f"expected run[0] NONE, got {result[0][1]}"
    )
    assert result[1][0] == "4" and result[1][1] == BO.SUPERSCRIPT, (
        f"expected run[1]=('4', SUPERSCRIPT), got {result[1]}"
    )
    assert result[2][1] == BO.NONE, (
        f"expected run[2] NONE, got {result[2][1]}"
    )
