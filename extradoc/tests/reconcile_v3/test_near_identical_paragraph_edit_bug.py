"""Regression test for near-identical paragraph reconciliation.

Bug (discovered on FORM-15G, doc 1FkRTeU852Mxg0OJh684MXutDxW7ubTkiA6_EXyRce54):

Editing ``ResidentialStatus4`` to ``Residential Status4`` (insert one space
after ``Residential``) must produce a single-character insertion and leave
the superscript on ``4`` intact. In the buggy reconciler:

1. ``align_content`` refuses to match the near-identical paragraphs (Bug 1)
   because word-level Jaccard is 0.
2. The pair flows through delete + insert which emits 7-8 ops and rewrites
   every run from scratch, leaking the superscript boundary onto the wrong
   character (the ``s`` of ``Status`` becomes superscript instead of ``4``).

With both bugs fixed, the reconciler emits a single ``insertText(" ", ...)``
at the correct offset and does not move the superscript boundary.
"""

from __future__ import annotations

from extradoc.api_types._generated import (
    Document,
    Paragraph,
    ParagraphElement,
    ParagraphStyle,
    ParagraphStyleNamedStyleType,
    SectionBreak,
    SectionStyle,
    StructuralElement,
    TextRun,
    TextStyle,
)
from extradoc.indexer import utf16_len
from extradoc.reconcile_v3.api import reconcile_batches
from tests.reconcile_v3.helpers import (
    assert_batches_within_base,
    make_indexed_doc,
    make_indexed_terminal,
)


def _section_break(start: int = 0) -> StructuralElement:
    return StructuralElement(
        start_index=start,
        end_index=start + 1,
        section_break=SectionBreak(section_style=SectionStyle()),
    )


def _multi_run_para(
    runs: list[tuple[str, TextStyle | None]],
    start: int,
) -> StructuralElement:
    """Build a paragraph with the given runs, appending a '\\n' to the last run."""
    # Ensure the last run ends with '\n' (every Google Docs paragraph does).
    if not runs:
        raise ValueError("runs must be non-empty")
    last_text, last_style = runs[-1]
    if not last_text.endswith("\n"):
        runs = [*runs[:-1], (last_text + "\n", last_style)]

    elements: list[ParagraphElement] = []
    cursor = start
    for text, style in runs:
        end = cursor + utf16_len(text)
        elements.append(
            ParagraphElement(
                start_index=cursor,
                end_index=end,
                text_run=TextRun(content=text, text_style=style or TextStyle()),
            )
        )
        cursor = end
    return StructuralElement(
        start_index=start,
        end_index=cursor,
        paragraph=Paragraph(
            elements=elements,
            paragraph_style=ParagraphStyle(
                named_style_type=ParagraphStyleNamedStyleType.NORMAL_TEXT,
            ),
        ),
    )


def _plain_para(text: str, start: int) -> StructuralElement:
    return _multi_run_para([(text, TextStyle())], start)


_CTX_BEFORE = (
    "Declaration under section 197A(1C) to be made by an individual.",
    "Claims certain receipts without deduction of tax.",
)
_CTX_AFTER = (
    "PART I",
    "Name of Assessee (Declarant).",
)


def _build_doc(
    non_sup_text: str,
    sup_text: str,
) -> Document:
    """Build a document with surrounding context + the target paragraph.

    The target paragraph is ``non_sup_text + sup_text`` where ``sup_text``
    is styled as SUPERSCRIPT. Context paragraphs are added before/after so
    the alignment DP has real matching anchors (otherwise the degenerate
    one-paragraph case takes a different code path).
    """
    body: list[StructuralElement] = [_section_break(0)]
    cursor = 1
    for text in _CTX_BEFORE:
        p = _plain_para(text, cursor)
        body.append(p)
        cursor = p.end_index or cursor
    target = _multi_run_para(
        [
            (non_sup_text, TextStyle()),
            (sup_text, TextStyle(baseline_offset="SUPERSCRIPT")),
        ],
        start=cursor,
    )
    body.append(target)
    cursor = target.end_index or cursor
    for text in _CTX_AFTER:
        p = _plain_para(text, cursor)
        body.append(p)
        cursor = p.end_index or cursor
    body.append(make_indexed_terminal(cursor))
    return make_indexed_doc(body_content=body)


def _collect_requests(batches: list) -> list:
    out: list = []
    for batch in batches:
        out.extend(batch.requests or [])
    return out


def test_insert_space_in_front_of_superscript_run_is_surgical() -> None:
    """Adding one space before a SUPERSCRIPT ``4`` must emit ≤3 ops.

    Base paragraph runs: ``"ResidentialStatus"`` NONE + ``"4\\n"`` SUPER.
    Desired runs: ``"Residential Status"`` NONE + ``"4\\n"`` SUPER.

    Ideally the reconciler emits a single ``insertText(" ")`` and nothing
    else: the superscript range is untouched in the base document and the
    inserted space inherits the adjacent normal style.
    """
    base = _build_doc("ResidentialStatus", "4")
    desired = _build_doc("Residential Status", "4")

    batches = reconcile_batches(base, desired)
    assert_batches_within_base(base, batches)
    requests = _collect_requests(batches)

    # Assert the total op count is small. Without the fix the pair flows
    # through delete+insert and emits 7+ ops.
    assert len(requests) <= 3, (
        f"expected <=3 ops, got {len(requests)}: "
        f"{[r.model_dump(exclude_none=True) for r in requests]}"
    )

    # Assert there is at most one insertText that inserts a single space.
    insert_reqs = [r for r in requests if r.insert_text is not None]
    assert len(insert_reqs) == 1, (
        f"expected exactly one insertText, got {len(insert_reqs)}: "
        f"{[r.insert_text.model_dump(exclude_none=True) for r in insert_reqs]}"
    )
    assert insert_reqs[0].insert_text is not None
    assert insert_reqs[0].insert_text.text == " ", (
        f"unexpected inserted text: {insert_reqs[0].insert_text.text!r}"
    )

    # Assert that NO updateTextStyle sets baselineOffset=SUPERSCRIPT on any
    # range — the superscript should already be at the right place in the
    # base document and just shift by one position after the insert.
    for r in requests:
        uts = r.update_text_style
        if uts is None:
            continue
        ts = uts.text_style
        if ts is None:
            continue
        offset = getattr(ts, "baseline_offset", None)
        if offset is None:
            continue
        offset_val = offset.value if hasattr(offset, "value") else str(offset)
        assert "SUPERSCRIPT" not in str(offset_val), (
            "reconciler emitted updateTextStyle baselineOffset=SUPERSCRIPT; "
            "this risks leaking the superscript to the wrong character. "
            f"request: {r.model_dump(exclude_none=True)}"
        )
