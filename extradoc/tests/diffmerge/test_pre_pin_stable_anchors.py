"""Tests for the pre-pinning pass in content alignment.

Pre-pinning runs BEFORE the DP to establish anchors from two sources:
1. Exact-text-match paragraphs (unambiguous — appear exactly once each side).
2. API-uncreatable elements (TOC, OPAQUE).

Pre-pinned anchors constrain the DP to smaller sub-problems and work
synergistically with _positional_fallback.
"""

from __future__ import annotations

from extradoc.api_types._generated import (
    StructuralElement,
    TableOfContents,
)
from extradoc.diffmerge.content_align import (
    ContentNode,
    align_content,
    content_node_from_element,
)
from tests.diffmerge.helpers import (
    make_para_el,
    make_table_el,
    make_terminal_para,
)

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _nodes(elements: list, terminal_at_end: bool = True) -> list[ContentNode]:
    nodes: list[ContentNode] = []
    last = len(elements) - 1
    for i, el in enumerate(elements):
        nodes.append(
            content_node_from_element(el, is_terminal=(terminal_at_end and i == last))
        )
    return nodes


def _match_map(alignment) -> dict[int, int]:
    return {m.base_idx: m.desired_idx for m in alignment.matches}


def _assert_matched(alignment, bi: int, di: int) -> None:
    mm = _match_map(alignment)
    assert bi in mm, f"base index {bi} expected to be matched but was deleted/unmatched"
    assert mm[bi] == di, f"base index {bi} matched desired {mm[bi]}, expected {di}"


def make_toc_el() -> StructuralElement:
    """Return a Table of Contents element."""
    return StructuralElement(table_of_contents=TableOfContents(content=[]))


# ---------------------------------------------------------------------------
# Tests: Exact-text pre-pinning
# ---------------------------------------------------------------------------


def test_exact_match_anchor_allows_complete_rewrite_between() -> None:
    """An exact-match anchor created by pre-pinning should make the positional
    fallback promote the completely-rewritten paragraph between two stable
    paragraphs.

    Scenario
    --------
    base:    [STABLE_A, REWRITE_ME, STABLE_B, TERMINAL]
    desired: [STABLE_A, NEW_TEXT,   STABLE_B, TERMINAL]

    Without pre-pinning, the DP might match STABLE_A/STABLE_B correctly, but
    with pre-pinning STABLE_A and STABLE_B are anchored first, forcing the DP
    to run only on the [REWRITE_ME] / [NEW_TEXT] gap. The positional fallback
    then promotes that 1:1 gap.

    Assert: REWRITE_ME (base[1]) is matched to NEW_TEXT (desired[1]).
    """
    base_els = [
        make_para_el("Stable intro paragraph used as anchor A"),
        make_para_el("This paragraph will be completely rewritten xyzzy"),
        make_para_el("Stable closing paragraph used as anchor B"),
        make_terminal_para(),
    ]
    desired_els = [
        make_para_el("Stable intro paragraph used as anchor A"),
        make_para_el("Brand new completely different content abcde"),
        make_para_el("Stable closing paragraph used as anchor B"),
        make_terminal_para(),
    ]

    base = _nodes(base_els)
    desired = _nodes(desired_els)
    alignment = align_content(base, desired)

    # STABLE_A and STABLE_B must be matched at the same positions.
    _assert_matched(alignment, 0, 0)
    _assert_matched(alignment, 2, 2)
    # The completely-rewritten paragraph must be matched (not delete+insert).
    _assert_matched(alignment, 1, 1)


def test_ambiguous_exact_match_not_pre_pinned() -> None:
    """When an exact text appears more than once, it must NOT be pre-pinned.

    Scenario
    --------
    base:    [DUP, DUP, TERMINAL]
    desired: [DUP, DUP, TERMINAL]

    "DUP" appears twice in base and twice in desired — ambiguous.
    The result is still correct (DP matches them positionally), but the
    important thing is that we don't confuse the DP by pre-pinning.
    We just verify correctness: both DUPs are matched.
    """
    dup_text = "Duplicate paragraph text appears twice"
    base_els = [
        make_para_el(dup_text),
        make_para_el(dup_text),
        make_terminal_para(),
    ]
    desired_els = [
        make_para_el(dup_text),
        make_para_el(dup_text),
        make_terminal_para(),
    ]
    base = _nodes(base_els)
    desired = _nodes(desired_els)
    alignment = align_content(base, desired)

    # Both should be matched — not deleted+inserted.
    mm = _match_map(alignment)
    assert 0 in mm and 1 in mm, "Both duplicate paragraphs should be matched"
    assert not alignment.base_deletes
    assert not alignment.desired_inserts


def test_exact_match_anchor_separates_two_independent_rewrites() -> None:
    """A stable anchor between two rewritten paragraphs should allow both to be
    promoted by the positional fallback.

    Scenario
    --------
    base:    [REWRITE_LEFT, STABLE, REWRITE_RIGHT, TERMINAL]
    desired: [NEW_LEFT,     STABLE, NEW_RIGHT,     TERMINAL]

    STABLE anchors the gap on both sides, leaving 1:1 gaps on each side.
    """
    base_els = [
        make_para_el("Old left paragraph with completely different content xyzzy"),
        make_para_el("Stable unchanged middle paragraph serves as anchor"),
        make_para_el("Old right paragraph with completely different content abcde"),
        make_terminal_para(),
    ]
    desired_els = [
        make_para_el("New left paragraph completely rewritten foobarbaz"),
        make_para_el("Stable unchanged middle paragraph serves as anchor"),
        make_para_el("New right paragraph completely rewritten quxquux"),
        make_terminal_para(),
    ]
    base = _nodes(base_els)
    desired = _nodes(desired_els)
    alignment = align_content(base, desired)

    _assert_matched(alignment, 1, 1)  # stable anchor
    _assert_matched(alignment, 0, 0)  # left rewrite promoted
    _assert_matched(alignment, 2, 2)  # right rewrite promoted


# ---------------------------------------------------------------------------
# Tests: API-uncreatable elements (TOC)
# ---------------------------------------------------------------------------


def test_toc_always_matched_regardless_of_surrounding_text() -> None:
    """A TOC in base is API-uncreatable; it must be matched to the TOC in
    desired even when the surrounding paragraphs are completely different.

    Scenario
    --------
    base:    [INTRO_OLD, TOC, CLOSING_OLD, TERMINAL]
    desired: [INTRO_NEW, TOC, CLOSING_NEW, TERMINAL]
    """
    base_els = [
        make_para_el("Old introduction text that is completely different xyzzy"),
        make_toc_el(),
        make_para_el("Old closing paragraph that is completely different abcde"),
        make_terminal_para(),
    ]
    desired_els = [
        make_para_el("New introduction text that is completely different foobarbaz"),
        make_toc_el(),
        make_para_el("New closing paragraph that is completely different quxquux"),
        make_terminal_para(),
    ]
    base = _nodes(base_els)
    desired = _nodes(desired_els)
    alignment = align_content(base, desired)

    # TOC must be matched.
    _assert_matched(alignment, 1, 1)
    # Surrounding paragraphs must also be matched (1:1 gaps).
    _assert_matched(alignment, 0, 0)
    _assert_matched(alignment, 2, 2)


def test_toc_in_base_not_in_desired_is_not_deleted() -> None:
    """A TOC in base with no corresponding TOC in desired must NOT generate a
    base_delete for it. (It will become a forced carry-through elsewhere, but
    the aligner must not mark it for deletion.)

    Scenario
    --------
    base:    [PARA_A, TOC, PARA_B, TERMINAL]
    desired: [PARA_A,      PARA_B, TERMINAL]

    We assert that the TOC (base[1]) is NOT in base_deletes.
    """
    base_els = [
        make_para_el("Paragraph A matches on both sides"),
        make_toc_el(),
        make_para_el("Paragraph B matches on both sides"),
        make_terminal_para(),
    ]
    desired_els = [
        make_para_el("Paragraph A matches on both sides"),
        make_para_el("Paragraph B matches on both sides"),
        make_terminal_para(),
    ]
    base = _nodes(base_els)
    desired = _nodes(desired_els)
    alignment = align_content(base, desired)

    assert 1 not in set(alignment.base_deletes), (
        "TOC (base[1]) must not be in base_deletes — it is API-uncreatable"
    )


# ---------------------------------------------------------------------------
# Tests: Interaction with existing machinery
# ---------------------------------------------------------------------------


def test_pre_pin_does_not_break_table_flank_pinning() -> None:
    """Pre-pinning must coexist with table-flank pinning without conflict.

    Scenario
    --------
    base:    [STABLE_ANCHOR, PRE_TABLE, TABLE, POST_TABLE, TERMINAL]
    desired: [STABLE_ANCHOR, NEW_PRE,   TABLE, NEW_POST,   TERMINAL]

    STABLE_ANCHOR is exact-matched by pre-pinning.
    PRE_TABLE / POST_TABLE are pinned by table-flank pinning.
    """
    base_els = [
        make_para_el("Stable anchor paragraph that appears exactly once"),
        make_para_el("Pre-table paragraph old text completely different xyzzy"),
        make_table_el([["Cell A", "Cell B"]]),
        make_para_el("Post-table paragraph old text completely different abcde"),
        make_terminal_para(),
    ]
    desired_els = [
        make_para_el("Stable anchor paragraph that appears exactly once"),
        make_para_el("Pre-table paragraph new text completely different foobarbaz"),
        make_table_el([["Cell A", "Cell B"]]),
        make_para_el("Post-table paragraph new text completely different quxquux"),
        make_terminal_para(),
    ]
    base = _nodes(base_els)
    desired = _nodes(desired_els)
    alignment = align_content(base, desired)

    _assert_matched(alignment, 0, 0)  # stable anchor
    _assert_matched(alignment, 1, 1)  # pre-table (table-flank pinned)
    _assert_matched(alignment, 2, 2)  # table
    _assert_matched(alignment, 3, 3)  # post-table (table-flank pinned)
