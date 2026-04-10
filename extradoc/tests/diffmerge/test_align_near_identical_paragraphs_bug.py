"""Regression test for align_content rejecting near-identical paragraphs.

Bug (discovered on FORM-15G QA):

``align_content`` uses word-level Jaccard similarity with a threshold of 0.3.
Two paragraphs that are clearly the same after a minor edit can fall below
this threshold when the words differ in tokenisation, e.g.:

- ``"ResidentialStatus4"`` vs ``"Residential Status4 "`` — zero shared
  tokens, Jaccard = 0.0.
- ``"Previous year (P.Y.)3             2020-21"`` vs
  ``"Previous year (P.Y.)3             2024-25 (for which declaration is
  being made)"`` — Jaccard ≈ 0.27.

When alignment refuses the pair, the paragraphs flow through delete+insert
instead of a surgical text-run diff, which inflates the push op count 3x and
(in combination with a separate run-boundary bug) leaks styles like
superscript onto the wrong characters.

Fix: ``matchable()`` must accept paragraph pairs whose shared prefix+suffix
covers a large fraction of the longer text, even when the word-level Jaccard
score is low.
"""

from __future__ import annotations

from extradoc.api_types._generated import (
    Paragraph,
    ParagraphElement,
    ParagraphStyle,
    ParagraphStyleNamedStyleType,
    StructuralElement,
    TextRun,
)
from extradoc.diffmerge.content_align import (
    align_content,
    content_node_from_element,
    matchable,
)


def _para(text: str) -> StructuralElement:
    return StructuralElement(
        paragraph=Paragraph(
            elements=[ParagraphElement(text_run=TextRun(content=text + "\n"))],
            paragraph_style=ParagraphStyle(
                named_style_type=ParagraphStyleNamedStyleType.NORMAL_TEXT,
            ),
        )
    )


def _terminal() -> StructuralElement:
    return _para("")


def _nodes(*texts: str) -> list:
    elements = [_para(t) for t in texts] + [_terminal()]
    nodes = [content_node_from_element(e) for e in elements]
    nodes[-1].is_terminal = True
    return nodes


# Realistic surrounding context: several unambiguous matchable paragraphs so
# the positional fallback can't paper over a `matchable()` rejection of the
# near-identical pair (it only promotes elements in 1:1 gaps created by the DP,
# which requires matching nodes on either side).
_CTX_BEFORE = (
    "Declaration under section 197A(1C) to be made by an individual",
    "who is of the age of sixty years or more claiming certain receipts",
    "without deduction of tax.",
)
_CTX_AFTER = (
    "PART I",
    "1. Name of Assessee (Declarant)",
    "2. PAN of the Assessee",
)


def test_matchable_accepts_residentialstatus_space_insert() -> None:
    """``matchable()`` must return True for the near-identical pair.

    Without the fix: word-level Jaccard is 0.0 (zero shared tokens), below
    the 0.3 threshold, so ``matchable()`` returns False. The DP aligner then
    assigns the pair the max delete+insert cost instead of a cheap edit.
    """
    base_node = content_node_from_element(_para("ResidentialStatus4"))
    desired_node = content_node_from_element(_para("Residential Status4 "))
    assert matchable(base_node, desired_node), (
        "near-identical paragraphs should be matchable even when word-level "
        "Jaccard is low"
    )


def test_matchable_accepts_previous_year_long_tail() -> None:
    """``matchable()`` must return True for a shared-prefix paragraph pair."""
    base_node = content_node_from_element(
        _para("Previous year (P.Y.)3             2020-21")
    )
    desired_node = content_node_from_element(
        _para(
            "Previous year (P.Y.)3             2024-25 "
            "(for which declaration is being made)"
        )
    )
    assert matchable(base_node, desired_node)


def test_align_matches_residentialstatus_space_insert() -> None:
    """End-to-end: near-identical paragraphs must come through as a MATCH.

    Surrounded by unambiguous context paragraphs so the positional fallback
    does not paper over the real alignment decision.
    """
    base = _nodes(*_CTX_BEFORE, "ResidentialStatus4", *_CTX_AFTER)
    desired = _nodes(*_CTX_BEFORE, "Residential Status4 ", *_CTX_AFTER)

    alignment = align_content(base, desired)

    # The near-identical paragraph is at index len(_CTX_BEFORE).
    target = len(_CTX_BEFORE)
    pairs = {(m.base_idx, m.desired_idx) for m in alignment.matches}
    assert (target, target) in pairs, (
        f"near-identical paragraph pair was not matched; "
        f"deletes={alignment.base_deletes}, inserts={alignment.desired_inserts}, "
        f"matches={sorted(pairs)}"
    )
    assert target not in alignment.base_deletes
    assert target not in alignment.desired_inserts


def test_align_matches_previous_year_with_long_tail() -> None:
    """Paragraph with a long appended tail should still be matched.

    The base and desired share a 44-char prefix (``Previous year ... 2020-``
    / ``... 2024-``). Word-level Jaccard is ~0.27, below the 0.3 threshold,
    so the pair is rejected without the fix.
    """
    base_text = "Previous year (P.Y.)3             2020-21"
    desired_text = (
        "Previous year (P.Y.)3             2024-25 "
        "(for which declaration is being made)"
    )
    base = _nodes(*_CTX_BEFORE, base_text, *_CTX_AFTER)
    desired = _nodes(*_CTX_BEFORE, desired_text, *_CTX_AFTER)

    alignment = align_content(base, desired)

    target = len(_CTX_BEFORE)
    pairs = {(m.base_idx, m.desired_idx) for m in alignment.matches}
    assert (target, target) in pairs, (
        f"long-tail paragraph pair was not matched; "
        f"deletes={alignment.base_deletes}, inserts={alignment.desired_inserts}"
    )


def test_align_still_rejects_completely_unrelated_paragraphs() -> None:
    """Sanity: unrelated text should NOT be matched.

    The fix must not over-match. Two unrelated paragraphs with no shared
    prefix or suffix should still flow through delete+insert.
    """
    # Place unrelated base and desired paragraphs between unambiguous anchors
    # so the positional fallback (which promotes same-kind elements in 1:1
    # DP gaps) can still fire — but the `matchable()` similarity check must
    # still be the gatekeeper for cost computation; an unrelated pair should
    # not get a low edit_cost.
    #
    # We assert via the public similarity helper that the heuristic does not
    # collapse to a near-identical match on unrelated text.
    from extradoc.diffmerge.content_align import matchable

    base_el = content_node_from_element(
        _para("The quick brown fox jumps over the lazy dog.")
    )
    desired_el = content_node_from_element(
        _para("Lorem ipsum dolor sit amet, consectetur adipiscing.")
    )
    assert not matchable(base_el, desired_el), (
        "over-matching: completely unrelated paragraphs should not be matchable"
    )
