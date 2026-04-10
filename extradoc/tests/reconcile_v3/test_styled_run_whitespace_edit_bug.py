"""Regression test for run fragmentation on whitespace-only edits into a styled run.

Bug (discovered on FORM-15G, doc 1FkRTeU852Mxg0OJh684MXutDxW7ubTkiA6_EXyRce54):

When the user inserts spaces into an existing styled run (e.g. edits
``**PARTI**`` -> ``**PART I**`` or ``*column16ofPartI*`` -> ``*column 16 of
Part I*``) the reconciler emits one ``insertText`` per inserted space plus an
``updateTextStyle`` carrying the FULL desired ``TextStyle`` (``italic``,
``fontSize``, ``foregroundColor``...) onto each inserted character. The base
run's ``TextStyle`` only has ``italic=True`` — the other fields are inherited
from the named style. After the API applies these requests it stores each
space as a separate run with an explicit ``fontSize`` and
``foregroundColor``. On re-pull, consolidation fails and the single run
fragments into per-word runs: ``*column* *16* *of* *Part* *I*``.

The fix lives in ``extradoc/reconcile_v3/lower.py::_insert_ops_for_span``:
when the desired style at an inserted character equals the adjacent base
run's style (i.e. the style is inherited through ``insertText``'s normal
behaviour), no ``updateTextStyle`` should be emitted at all — and where it
must be emitted, only the fields that actually differ from the adjacent base
style should be listed.
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


def _make_section_break(start: int = 0) -> StructuralElement:
    return StructuralElement(
        start_index=start,
        end_index=start + 1,
        section_break=SectionBreak(section_style=SectionStyle()),
    )


def _styled_para(text: str, start: int, style: TextStyle) -> StructuralElement:
    # `text` must NOT include the trailing \n; it is added here.
    content = text + "\n"
    end = start + utf16_len(content)
    return StructuralElement(
        start_index=start,
        end_index=end,
        paragraph=Paragraph(
            elements=[
                ParagraphElement(
                    start_index=start,
                    end_index=end,
                    text_run=TextRun(content=content, text_style=style),
                ),
            ],
            paragraph_style=ParagraphStyle(
                named_style_type=ParagraphStyleNamedStyleType.NORMAL_TEXT,
            ),
        ),
    )


def _make_doc(text: str, style: TextStyle) -> Document:
    sb = _make_section_break(0)
    para = _styled_para(text, start=1, style=style)
    term_start = para.end_index or 0
    term = make_indexed_terminal(term_start)
    return make_indexed_doc(body_content=[sb, para, term])


def _collect_requests(
    batches: list,
) -> list:
    out: list = []
    for batch in batches:
        out.extend(batch.requests or [])
    return out


def test_inserting_spaces_into_italic_run_does_not_fragment() -> None:
    """Inserting spaces into an italic run must not emit updateTextStyle with extra fields.

    Without the fix:
      - Each inserted space becomes its own run with explicit fontSize /
        foregroundColor copied from the desired style, OR at minimum an
        ``updateTextStyle`` is emitted explicitly setting ``italic=True`` on
        the inserted char — which in the real API prevents run consolidation
        and fragments the single italic run into one run per word.

    With the fix:
      - The inserted chars inherit the surrounding italic style via
        ``insertText``'s normal behaviour, so no ``updateTextStyle`` is
        emitted at all for inserts whose style equals the adjacent base run.
    """
    base = _make_doc("column16ofPartI", TextStyle(italic=True))
    desired = _make_doc("column 16 of Part I", TextStyle(italic=True))

    batches = reconcile_batches(base, desired)
    assert_batches_within_base(base, batches)
    requests = _collect_requests(batches)

    insert_reqs = [r for r in requests if r.insert_text is not None]
    update_reqs = [r for r in requests if r.update_text_style is not None]

    # Sanity: we did emit insert ops for the added spaces.
    assert insert_reqs, (
        f"expected insertText requests for the added spaces, got: {requests!r}"
    )
    # And every inserted text must be a single space.
    for r in insert_reqs:
        assert r.insert_text is not None
        assert r.insert_text.text == " ", (
            f"unexpected inserted text: {r.insert_text.text!r}"
        )

    # Core invariant: no updateTextStyle is emitted for the inserted chars.
    # The italic style of the surrounding run is inherited automatically.
    # If fragmentation ever comes back, update_reqs will contain requests
    # covering the inserted spaces.
    assert not update_reqs, (
        "fragmentation bug: reconciler emitted updateTextStyle for whitespace "
        f"inserts into an already-styled run; requests: "
        f"{[r.update_text_style.model_dump(exclude_none=True) for r in update_reqs]!r}"
    )


def test_inserting_space_into_bold_run_does_not_fragment() -> None:
    """PART I variant: single space inserted inside a bold run.

    Base: ``PARTI`` (single bold run). Desired: ``PART I``. The inserted
    space must not carry an explicit updateTextStyle — otherwise on re-pull
    the bold run fragments into ``**PART** **I**``.
    """

    base2 = _make_doc("PARTI", TextStyle(bold=True))
    batches = reconcile_batches(
        base2,
        _make_doc("PART I", TextStyle(bold=True)),
    )
    assert_batches_within_base(base2, batches)
    requests = _collect_requests(batches)

    update_reqs = [r for r in requests if r.update_text_style is not None]
    assert not update_reqs, (
        "fragmentation bug: reconciler emitted updateTextStyle for a space "
        "inserted inside a bold run; requests: "
        f"{[r.update_text_style.model_dump(exclude_none=True) for r in update_reqs]!r}"
    )
