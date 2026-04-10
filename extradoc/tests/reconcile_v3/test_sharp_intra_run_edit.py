"""Regression tests for whole-paragraph rewrite bloat.

Bug (discovered on FORM-15G, QA fixture /tmp/qa-final3/pull1/.debug/):

A table cell (or any body story) where the base has multiple trailing empty
paragraphs and the desired has a single text paragraph used to produce a
whole-paragraph delete+reinsert (plus an updateTextStyle cascade that mis-aligned
runs with the inherited base-run widths — corrupting SUPERSCRIPT ranges).

Root cause: ``align_content`` pre-matches terminals unconditionally. When the
base terminal is an empty ``"\\n"`` and the desired terminal is the only
(non-empty) paragraph, the forced pairing left the real content paragraph
unmatched so it was deleted + reinserted.

Expected behaviour: the reconciler should detect that base[0] corresponds to
desired[0] and emit a surgical intra-run edit instead of delete+insert.
"""

from __future__ import annotations

from extradoc.api_types._generated import (
    Body,
    BatchUpdateDocumentRequest,
    Document,
    DocumentTab,
    NamedStyles,
    Paragraph,
    ParagraphElement,
    ParagraphStyle,
    ParagraphStyleNamedStyleType,
    StructuralElement,
    Tab,
    TabProperties,
    TextRun,
    TextStyle,
)
from extradoc.indexer import utf16_len
from extradoc.reconcile_v3.api import reconcile_batches


def _para(runs: list[tuple[str, TextStyle]], start: int) -> StructuralElement:
    """Build a paragraph with the given text runs; appends ``\\n`` to the last run."""
    els: list[ParagraphElement] = []
    cursor = start
    for i, (text, style) in enumerate(runs):
        content = text + "\n" if i == len(runs) - 1 else text
        end = cursor + utf16_len(content)
        els.append(
            ParagraphElement(
                start_index=cursor,
                end_index=end,
                text_run=TextRun(content=content, text_style=style),
            )
        )
        cursor = end
    return StructuralElement(
        start_index=start,
        end_index=cursor,
        paragraph=Paragraph(
            elements=els,
            paragraph_style=ParagraphStyle(
                named_style_type=ParagraphStyleNamedStyleType.NORMAL_TEXT
            ),
        ),
    )


def _make_doc(paragraphs: list[StructuralElement]) -> Document:
    """Wrap a list of paragraphs as a tab body (no section break, mirroring a cell)."""
    return Document(
        document_id="d1",
        tabs=[
            Tab(
                tab_properties=TabProperties(tab_id="t1", title="T", index=0),
                document_tab=DocumentTab(
                    body=Body(content=paragraphs),
                    named_styles=NamedStyles(styles=[]),
                ),
            )
        ],
    )


def _collect_requests(batches: list[BatchUpdateDocumentRequest]) -> list:
    out: list = []
    for batch in batches:
        out.extend(batch.requests or [])
    return out


NONE = TextStyle(baseline_offset="NONE")
SUP = TextStyle(baseline_offset="SUPERSCRIPT")


def test_space_insert_before_superscript_run_emits_single_insertText() -> None:
    """Inserting one space into a 3-run paragraph (with SUPERSCRIPT middle run)
    inside a body that also carries trailing empty paragraphs must emit ONE
    ``insertText`` of ``" "`` — not a whole-paragraph delete+reinsert.

    This mirrors the FORM-15G ``ResidentialStatus4`` → ``Residential Status4``
    edit in a table cell with two trailing empty paragraphs.
    """
    # base: "ResidentialStatus4 \n", "\n", "\n"
    p1 = _para(
        [("ResidentialStatus", NONE), ("4", SUP), (" ", NONE)],
        start=1,
    )
    p2 = _para([("", NONE)], start=p1.end_index or 0)
    p3 = _para([("", NONE)], start=p2.end_index or 0)
    base = _make_doc([p1, p2, p3])

    # desired: "Residential Status4 \n"  (the two empty trailing paragraphs removed)
    dp1 = _para(
        [("Residential Status", NONE), ("4", SUP), (" ", NONE)],
        start=1,
    )
    desired = _make_doc([dp1])

    requests = _collect_requests(reconcile_batches(base, desired))

    # We should see: one insertText " ", and up to two deleteContentRange ops
    # for the two empty trailing paragraphs. The key invariant: NO
    # updateTextStyle requests are emitted (the surrounding runs' styles are
    # unchanged) and NO insertText that rewrites the whole paragraph text.
    insert_reqs = [r for r in requests if r.insert_text is not None]
    update_reqs = [r for r in requests if r.update_text_style is not None]

    assert len(insert_reqs) == 1, (
        f"expected exactly one insertText, got {len(insert_reqs)}: "
        f"{[r.insert_text.model_dump(exclude_none=True) for r in insert_reqs]!r}"
    )
    assert insert_reqs[0].insert_text is not None
    assert insert_reqs[0].insert_text.text == " ", (
        f"expected single-space insert, got: {insert_reqs[0].insert_text.text!r}"
    )
    assert not update_reqs, (
        "bloat bug: reconciler emitted updateTextStyle for an intra-run "
        "space insert; requests: "
        f"{[r.update_text_style.model_dump(exclude_none=True) for r in update_reqs]!r}"
    )


def test_intra_run_char_replace_preserves_surrounding_style() -> None:
    """Replacing ``2020-21`` with ``2024-25`` inside a bold paragraph (with
    trailing empty paragraphs) must emit character-level delete+insert ops
    and NO updateTextStyle (the style is unchanged).
    """
    bold = TextStyle(bold=True)

    p1 = _para([("Previous year 2020-21", bold)], start=1)
    p2 = _para([("", bold)], start=p1.end_index or 0)
    p3 = _para([("", bold)], start=p2.end_index or 0)
    base = _make_doc([p1, p2, p3])

    dp1 = _para([("Previous year 2024-25", bold)], start=1)
    desired = _make_doc([dp1])

    requests = _collect_requests(reconcile_batches(base, desired))

    update_reqs = [r for r in requests if r.update_text_style is not None]
    insert_reqs = [r for r in requests if r.insert_text is not None]

    # No updateTextStyle — style didn't change.
    assert not update_reqs, (
        "bloat bug: reconciler emitted updateTextStyle despite style being "
        "unchanged; requests: "
        f"{[r.update_text_style.model_dump(exclude_none=True) for r in update_reqs]!r}"
    )
    # Inserts should be short character-level edits (not a whole-paragraph rewrite).
    for r in insert_reqs:
        assert r.insert_text is not None
        assert len(r.insert_text.text) <= 4, (
            "bloat bug: reconciler emitted whole-paragraph reinsert "
            f"{r.insert_text.text!r}"
        )
