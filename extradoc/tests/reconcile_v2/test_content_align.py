"""Tests for the content alignment algorithm in content_align.py.

Tests are structured in seven parts:
  Part 1: Simple deterministic tests
  Part 2: List handling
  Part 3: Table handling
  Part 4: Mixed content sequences
  Part 5: Real document fixture tests
  Part 6: Property-based fuzz tests
  Part 7: Complex document (golden file) tests
"""

from __future__ import annotations

import copy
import json
import pathlib
import random

import pytest

from extradoc.reconcile_v2.content_align import (
    INFINITE_PENALTY,
    ContentAlignment,
    ContentNode,
    NodeKind,
    align_content,
    delete_penalty,
    edit_cost,
    insert_penalty,
    matchable,
    sequence_from_doc_json,
    text_similarity,
)

# ---------------------------------------------------------------------------
# Paths to test data
# ---------------------------------------------------------------------------

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"
GOLDEN_DIR = pathlib.Path(__file__).parent.parent / "golden"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_para(text: str, *, is_terminal: bool = False) -> ContentNode:
    """Build a paragraph ContentNode with the given text."""
    return ContentNode(
        kind=NodeKind.PARAGRAPH,
        text=text,
        is_terminal=is_terminal,
        original=None,
    )


def make_terminal_para(text: str = "\n") -> ContentNode:
    return make_para(text, is_terminal=True)


def make_table_node(cell_texts: list[str], *, is_terminal: bool = False) -> ContentNode:
    return ContentNode(
        kind=NodeKind.TABLE,
        num_cells=len(cell_texts),
        table_cell_texts=cell_texts,
        is_terminal=is_terminal,
        original=None,
    )


def make_list_node(
    text: str,
    list_kind: str = "BULLETED",
    *,
    is_terminal: bool = False,
) -> ContentNode:
    return ContentNode(
        kind=NodeKind.LIST,
        text=text,
        list_kind=list_kind,
        is_terminal=is_terminal,
        original=None,
    )


def make_section_break(*, is_terminal: bool = False) -> ContentNode:
    return ContentNode(
        kind=NodeKind.SECTION_BREAK, is_terminal=is_terminal, original=None
    )


def make_page_break(*, is_terminal: bool = False) -> ContentNode:
    return ContentNode(kind=NodeKind.PAGE_BREAK, is_terminal=is_terminal, original=None)


def make_toc(*, is_terminal: bool = False) -> ContentNode:
    return ContentNode(kind=NodeKind.TOC, is_terminal=is_terminal, original=None)


def _is_valid_alignment(
    alignment: ContentAlignment,
    base: list[ContentNode],
    desired: list[ContentNode],
) -> tuple[bool, str]:
    """Return (ok, reason) — True if the alignment is structurally valid."""
    m, n = len(base), len(desired)

    # All base indices covered exactly once
    base_covered = sorted(
        [cm.base_idx for cm in alignment.matches] + alignment.base_deletes
    )
    if base_covered != list(range(m)):
        return False, f"Base coverage mismatch: {base_covered} != {list(range(m))}"

    # All desired indices covered exactly once
    desired_covered = sorted(
        [cm.desired_idx for cm in alignment.matches] + alignment.desired_inserts
    )
    if desired_covered != list(range(n)):
        return (
            False,
            f"Desired coverage mismatch: {desired_covered} != {list(range(n))}",
        )

    # Matches are order-preserving
    for k in range(len(alignment.matches) - 1):
        a, b = alignment.matches[k], alignment.matches[k + 1]
        if not (a.base_idx < b.base_idx and a.desired_idx < b.desired_idx):
            return False, f"Matches not order-preserving at k={k}: {a}, {b}"

    return True, "ok"


def assert_valid(
    alignment: ContentAlignment, base: list[ContentNode], desired: list[ContentNode]
) -> None:
    ok, reason = _is_valid_alignment(alignment, base, desired)
    assert ok, reason


def assert_terminals_matched(
    alignment: ContentAlignment,
    base: list[ContentNode],
    desired: list[ContentNode],
) -> None:
    """Assert that the terminal elements (base[-1], desired[-1]) are matched."""
    if not base or not desired:
        return
    m, n = len(base), len(desired)
    last_match = alignment.matches[-1] if alignment.matches else None
    assert last_match is not None, "No matches at all — terminals must be matched"
    assert (
        last_match.base_idx == m - 1
    ), f"Terminal base element not matched: last match base_idx={last_match.base_idx}, m-1={m-1}"
    assert (
        last_match.desired_idx == n - 1
    ), f"Terminal desired element not matched: last match desired_idx={last_match.desired_idx}, n-1={n-1}"


def assert_identical_matched(
    alignment: ContentAlignment,
    base: list[ContentNode],
    desired: list[ContentNode],
) -> None:
    """Assert that no identical (text, kind) element is strictly better off being matched.

    When an identical element appears in both base_deletes and desired_inserts, the
    cost of deleting + inserting equals the cost of matching (both are zero edit_cost,
    while delete+insert = delete_penalty + insert_penalty > 0 only when the text is
    non-empty).  In that case matching is strictly preferable.

    Exception: when the base element has zero delete_penalty (empty text), the
    tie does not matter semantically.
    """
    base_texts = {i: (base[i].kind, base[i].text) for i in alignment.base_deletes}
    desired_texts = {
        j: (desired[j].kind, desired[j].text) for j in alignment.desired_inserts
    }

    for bi, bv in base_texts.items():
        for dj, dv in desired_texts.items():
            if bv != dv or bv[1] == "":
                continue
            # Identical non-empty element: check if matching is strictly cheaper
            # than delete+insert.  If so, the algorithm made a suboptimal choice.
            b_node = base[bi]
            d_node = desired[dj]
            match_cost = edit_cost(b_node, d_node)
            di_cost = delete_penalty(b_node) + insert_penalty(d_node)
            if match_cost < di_cost - 1e-9:
                raise AssertionError(
                    f"Identical element (kind={bv[0]!r}, text={bv[1]!r}) "
                    f"appears in both base_deletes (idx={bi}) and desired_inserts (idx={dj}). "
                    f"Matching cost ({match_cost:.2f}) < delete+insert cost ({di_cost:.2f}): "
                    "the algorithm made a suboptimal choice."
                )


# ===========================================================================
# PART 1: Simple deterministic tests
# ===========================================================================


class TestEmptySequences:
    def test_both_empty(self):
        result = align_content([], [])
        assert result.matches == []
        assert result.base_deletes == []
        assert result.desired_inserts == []
        assert result.total_cost == 0.0

    def test_base_empty_desired_has_elements(self):
        desired = [make_para("hello"), make_terminal_para()]
        result = align_content([], desired)
        # Nothing to match
        assert result.matches == []
        assert result.base_deletes == []
        assert_valid(result, [], desired)

    def test_desired_empty_base_has_elements(self):
        base = [make_para("hello"), make_terminal_para()]
        result = align_content(base, [])
        assert result.matches == []
        assert result.desired_inserts == []
        assert_valid(result, base, [])


class TestIdenticalSequences:
    def test_single_terminal(self):
        base = [make_terminal_para("hello\n")]
        desired = [make_terminal_para("hello\n")]
        result = align_content(base, desired)
        assert_valid(result, base, desired)
        assert_terminals_matched(result, base, desired)
        assert len(result.matches) == 1
        assert result.base_deletes == []
        assert result.desired_inserts == []

    def test_two_identical_paragraphs(self):
        base = [make_para("alpha\n"), make_terminal_para("beta\n")]
        desired = [make_para("alpha\n"), make_terminal_para("beta\n")]
        result = align_content(base, desired)
        assert_valid(result, base, desired)
        assert_terminals_matched(result, base, desired)
        assert len(result.matches) == 2
        assert result.base_deletes == []
        assert result.desired_inserts == []
        assert result.total_cost == 0.0

    def test_five_identical_paragraphs(self):
        texts = ["one\n", "two\n", "three\n", "four\n"]
        base = [make_para(t) for t in texts] + [make_terminal_para()]
        desired = [make_para(t) for t in texts] + [make_terminal_para()]
        result = align_content(base, desired)
        assert_valid(result, base, desired)
        assert len(result.matches) == 5
        assert result.base_deletes == []
        assert result.desired_inserts == []

    def test_zero_cost_for_identical(self):
        texts = ["alpha\n", "beta\n", "gamma\n"]
        base = [make_para(t) for t in texts] + [make_terminal_para()]
        desired = copy.deepcopy(base)
        result = align_content(base, desired)
        assert result.total_cost == 0.0


class TestSingleAddition:
    def test_insert_at_end(self):
        base = [make_para("existing\n"), make_terminal_para()]
        desired = [
            make_para("existing\n"),
            make_para("new paragraph\n"),
            make_terminal_para(),
        ]
        result = align_content(base, desired)
        assert_valid(result, base, desired)
        assert_terminals_matched(result, base, desired)
        assert 1 in result.desired_inserts  # "new paragraph" inserted

    def test_insert_at_start(self):
        base = [make_para("existing\n"), make_terminal_para()]
        desired = [
            make_para("new first\n"),
            make_para("existing\n"),
            make_terminal_para(),
        ]
        result = align_content(base, desired)
        assert_valid(result, base, desired)
        assert_terminals_matched(result, base, desired)
        # "existing" should be matched
        existing_matched = any(
            desired[cm.desired_idx].text == "existing\n" for cm in result.matches
        )
        assert existing_matched

    def test_insert_in_middle(self):
        base = [make_para("first\n"), make_para("third\n"), make_terminal_para()]
        desired = [
            make_para("first\n"),
            make_para("second\n"),
            make_para("third\n"),
            make_terminal_para(),
        ]
        result = align_content(base, desired)
        assert_valid(result, base, desired)
        assert_terminals_matched(result, base, desired)
        # "first" and "third" must be matched
        matched_texts = {desired[cm.desired_idx].text for cm in result.matches}
        assert "first\n" in matched_texts
        assert "third\n" in matched_texts
        assert len(result.desired_inserts) == 1


class TestSingleDeletion:
    def test_delete_at_end_before_terminal(self):
        base = [make_para("keep\n"), make_para("remove\n"), make_terminal_para()]
        desired = [make_para("keep\n"), make_terminal_para()]
        result = align_content(base, desired)
        assert_valid(result, base, desired)
        assert_terminals_matched(result, base, desired)
        assert len(result.base_deletes) == 1

    def test_delete_at_start(self):
        base = [make_para("remove\n"), make_para("keep\n"), make_terminal_para()]
        desired = [make_para("keep\n"), make_terminal_para()]
        result = align_content(base, desired)
        assert_valid(result, base, desired)
        assert_terminals_matched(result, base, desired)
        assert len(result.base_deletes) == 1

    def test_delete_in_middle(self):
        base = [
            make_para("first\n"),
            make_para("remove\n"),
            make_para("last\n"),
            make_terminal_para(),
        ]
        desired = [make_para("first\n"), make_para("last\n"), make_terminal_para()]
        result = align_content(base, desired)
        assert_valid(result, base, desired)
        assert_terminals_matched(result, base, desired)
        assert len(result.base_deletes) == 1
        # "first" and "last" must be matched
        matched_base_texts = {base[cm.base_idx].text for cm in result.matches}
        assert "first\n" in matched_base_texts
        assert "last\n" in matched_base_texts


class TestSingleEdit:
    def test_slight_text_change_is_matched_not_replaced(self):
        """A paragraph with slightly changed text should be matched, not delete+insert."""
        base = [
            make_para("The quick brown fox jumps over the lazy dog\n"),
            make_terminal_para(),
        ]
        desired = [
            make_para("The quick brown fox jumped over the lazy dog\n"),
            make_terminal_para(),
        ]
        result = align_content(base, desired)
        assert_valid(result, base, desired)
        assert_terminals_matched(result, base, desired)
        # The first paragraph should be matched (edited), not deleted+inserted
        non_terminal_matches = [
            cm for cm in result.matches if cm.base_idx != len(base) - 1
        ]
        assert len(non_terminal_matches) == 1
        assert result.base_deletes == []
        assert result.desired_inserts == []


class TestCompleteReplacement:
    def test_all_different_short(self):
        """When all content is completely different, delete+insert is acceptable."""
        base = [make_para("xyz\n"), make_terminal_para("terminal base\n")]
        desired = [make_para("abc\n"), make_terminal_para("terminal desired\n")]
        result = align_content(base, desired)
        assert_valid(result, base, desired)
        assert_terminals_matched(result, base, desired)


class TestTerminalConstraint:
    def test_terminal_always_matched_even_if_completely_different(self):
        base = [make_terminal_para("completely different text here\n")]
        desired = [make_terminal_para("totally unrelated content xyz\n")]
        result = align_content(base, desired)
        assert_valid(result, base, desired)
        assert_terminals_matched(result, base, desired)
        assert result.base_deletes == []
        assert result.desired_inserts == []

    def test_terminal_never_in_deletes(self):
        base = [make_para("middle\n"), make_terminal_para()]
        desired = [make_para("other\n"), make_terminal_para()]
        result = align_content(base, desired)
        assert len(base) - 1 not in result.base_deletes

    def test_terminal_never_in_inserts(self):
        base = [make_para("middle\n"), make_terminal_para()]
        desired = [make_para("other\n"), make_terminal_para()]
        result = align_content(base, desired)
        assert len(desired) - 1 not in result.desired_inserts

    def test_identical_middle_paragraph_always_matched(self):
        """An identical non-terminal paragraph must never be delete+inserted."""
        identical_text = "This is the same paragraph in both sequences\n"
        base = [
            make_para("before base\n"),
            make_para(identical_text),
            make_para("after base\n"),
            make_terminal_para(),
        ]
        desired = [
            make_para("before desired\n"),
            make_para(identical_text),
            make_para("after desired\n"),
            make_terminal_para(),
        ]
        result = align_content(base, desired)
        assert_valid(result, base, desired)
        # The identical paragraph must be in matches, not in deletes/inserts
        identical_in_matches = any(
            base[cm.base_idx].text == identical_text for cm in result.matches
        )
        assert identical_in_matches, "Identical paragraph was not matched"
        assert_identical_matched(result, base, desired)


# ===========================================================================
# PART 2: List handling
# ===========================================================================


class TestListHandling:
    def test_identical_list_matched(self):
        base = [
            make_list_node("one two three", "BULLETED"),
            make_terminal_para(),
        ]
        desired = [
            make_list_node("one two three", "BULLETED"),
            make_terminal_para(),
        ]
        result = align_content(base, desired)
        assert_valid(result, base, desired)
        assert len(result.matches) == 2
        assert result.base_deletes == []
        assert result.desired_inserts == []

    def test_list_with_added_item_matched(self):
        base = [
            make_list_node("one two", "BULLETED"),
            make_terminal_para(),
        ]
        desired = [
            make_list_node("one two three", "BULLETED"),
            make_terminal_para(),
        ]
        result = align_content(base, desired)
        assert_valid(result, base, desired)
        assert_terminals_matched(result, base, desired)
        # List should be matched (edited), not deleted+inserted
        list_matches = [
            cm for cm in result.matches if base[cm.base_idx].kind == NodeKind.LIST
        ]
        assert len(list_matches) == 1

    def test_list_item_text_edited_matched(self):
        base = [
            make_list_node("alpha beta gamma", "BULLETED"),
            make_terminal_para(),
        ]
        desired = [
            make_list_node("alpha beta delta", "BULLETED"),
            make_terminal_para(),
        ]
        result = align_content(base, desired)
        assert_valid(result, base, desired)
        assert_terminals_matched(result, base, desired)
        list_matches = [
            cm for cm in result.matches if base[cm.base_idx].kind == NodeKind.LIST
        ]
        assert len(list_matches) == 1

    def test_list_kind_changed_still_matched(self):
        """Changing list kind (bullet → numbered) should match, not delete+insert."""
        base = [
            make_list_node("item one item two item three", "BULLETED"),
            make_terminal_para(),
        ]
        desired = [
            make_list_node("item one item two item three", "NUMBERED"),
            make_terminal_para(),
        ]
        result = align_content(base, desired)
        assert_valid(result, base, desired)
        assert_terminals_matched(result, base, desired)
        list_matches = [
            cm for cm in result.matches if base[cm.base_idx].kind == NodeKind.LIST
        ]
        assert len(list_matches) == 1

    def test_list_adjacent_to_paragraphs(self):
        base = [
            make_para("intro paragraph\n"),
            make_list_node("alpha beta gamma", "BULLETED"),
            make_para("outro paragraph\n"),
            make_terminal_para(),
        ]
        desired = [
            make_para("intro paragraph\n"),
            make_list_node("alpha beta gamma delta", "BULLETED"),
            make_para("outro paragraph\n"),
            make_terminal_para(),
        ]
        result = align_content(base, desired)
        assert_valid(result, base, desired)
        assert_terminals_matched(result, base, desired)
        assert len(result.matches) == 4
        assert result.base_deletes == []
        assert result.desired_inserts == []


# ===========================================================================
# PART 3: Table handling
# ===========================================================================


class TestTableHandling:
    def test_identical_table_matched(self):
        cells = ["Header1", "Header2", "Data1", "Data2"]
        base = [make_table_node(cells), make_terminal_para()]
        desired = [make_table_node(cells), make_terminal_para()]
        result = align_content(base, desired)
        assert_valid(result, base, desired)
        assert len(result.matches) == 2
        assert result.base_deletes == []
        assert result.desired_inserts == []

    def test_table_with_one_cell_changed_matched(self):
        base_cells = ["Header1", "Header2", "Data1", "Data2"]
        desired_cells = ["Header1", "Header2", "Data1", "CHANGED"]
        base = [make_table_node(base_cells), make_terminal_para()]
        desired = [make_table_node(desired_cells), make_terminal_para()]
        result = align_content(base, desired)
        assert_valid(result, base, desired)
        assert_terminals_matched(result, base, desired)
        # Table should be matched (edited), not deleted+inserted
        table_matches = [
            cm for cm in result.matches if base[cm.base_idx].kind == NodeKind.TABLE
        ]
        assert len(table_matches) == 1

    def test_completely_different_table_may_delete_insert(self):
        """A totally different table may legitimately be delete+inserted."""
        base_cells = ["aaa", "bbb", "ccc", "ddd"]
        desired_cells = ["xxx", "yyy", "zzz", "www"]
        base = [make_table_node(base_cells), make_terminal_para()]
        desired = [make_table_node(desired_cells), make_terminal_para()]
        result = align_content(base, desired)
        assert_valid(result, base, desired)
        assert_terminals_matched(result, base, desired)
        # Either matched with high edit cost, or delete+insert — both acceptable


# ===========================================================================
# PART 4: Mixed content sequences
# ===========================================================================


class TestMixedContent:
    def test_para_table_para_identical(self):
        cells = ["a", "b", "c", "d"]
        base = [
            make_para("intro\n"),
            make_table_node(cells),
            make_terminal_para(),
        ]
        desired = [
            make_para("intro\n"),
            make_table_node(cells),
            make_terminal_para(),
        ]
        result = align_content(base, desired)
        assert_valid(result, base, desired)
        assert len(result.matches) == 3
        assert result.base_deletes == []
        assert result.desired_inserts == []

    def test_list_para_table_mixed(self):
        cells = ["x", "y"]
        base = [
            make_list_node("item one item two", "BULLETED"),
            make_para("middle paragraph\n"),
            make_table_node(cells),
            make_terminal_para(),
        ]
        desired = [
            make_list_node("item one item two", "BULLETED"),
            make_para("middle paragraph\n"),
            make_table_node(cells),
            make_terminal_para(),
        ]
        result = align_content(base, desired)
        assert_valid(result, base, desired)
        assert len(result.matches) == 4
        assert result.base_deletes == []
        assert result.desired_inserts == []

    def test_identical_paragraphs_are_anchors(self):
        """Shared identical paragraphs are always anchors regardless of surrounding changes."""
        anchor1 = "This is anchor paragraph one.\n"
        anchor2 = "This is anchor paragraph two.\n"
        base = [
            make_para(anchor1),
            make_para("base-only content\n"),
            make_para(anchor2),
            make_terminal_para(),
        ]
        desired = [
            make_para(anchor1),
            make_para("desired-only content\n"),
            make_para(anchor2),
            make_terminal_para(),
        ]
        result = align_content(base, desired)
        assert_valid(result, base, desired)
        assert_terminals_matched(result, base, desired)
        assert_identical_matched(result, base, desired)
        # anchor1 and anchor2 must be in matches
        matched_base_texts = {base[cm.base_idx].text for cm in result.matches}
        assert anchor1 in matched_base_texts
        assert anchor2 in matched_base_texts

    def test_section_break_matched_with_same_kind(self):
        base = [
            make_section_break(),
            make_para("content\n"),
            make_terminal_para(),
        ]
        desired = [
            make_section_break(),
            make_para("content\n"),
            make_terminal_para(),
        ]
        result = align_content(base, desired)
        assert_valid(result, base, desired)
        assert len(result.matches) == 3

    def test_paragraph_does_not_match_table(self):
        """A paragraph and a table must never be matched."""
        base = [
            make_para("some text\n"),
            make_terminal_para(),
        ]
        desired = [
            make_table_node(["cell text"]),
            make_terminal_para(),
        ]
        result = align_content(base, desired)
        assert_valid(result, base, desired)
        assert_terminals_matched(result, base, desired)
        # The paragraph and table cannot match — one will be deleted, one inserted
        non_terminal_matches = [
            cm for cm in result.matches if cm.base_idx != len(base) - 1
        ]
        assert len(non_terminal_matches) == 0


# ===========================================================================
# PART 5: Real document fixture tests
# ===========================================================================


def _load_fixture(name: str) -> tuple[dict, dict]:
    """Load base.json and desired.json from a fixture directory."""
    base_path = FIXTURES_DIR / name / "base.json"
    desired_path = FIXTURES_DIR / name / "desired.json"
    with base_path.open() as f:
        base_doc = json.load(f)
    with desired_path.open() as f:
        desired_doc = json.load(f)
    return base_doc, desired_doc


def _alignment_summary(alignment: ContentAlignment) -> str:
    return (
        f"matches={len(alignment.matches)}, "
        f"base_deletes={alignment.base_deletes}, "
        f"desired_inserts={alignment.desired_inserts}, "
        f"cost={alignment.total_cost:.1f}"
    )


class TestFixtureParagraphSplit:
    """paragraph_split: 'alpha beta\n' → 'alpha\n' + 'beta\n'"""

    def test_alignment_valid(self):
        base_doc, desired_doc = _load_fixture("paragraph_split")
        base = sequence_from_doc_json(base_doc)
        desired = sequence_from_doc_json(desired_doc)
        result = align_content(base, desired)
        assert_valid(result, base, desired)

    def test_terminals_matched(self):
        base_doc, desired_doc = _load_fixture("paragraph_split")
        base = sequence_from_doc_json(base_doc)
        desired = sequence_from_doc_json(desired_doc)
        result = align_content(base, desired)
        assert_terminals_matched(result, base, desired)

    def test_split_paragraph_handled(self):
        """base has 1 content para, desired has 2; one insertion expected."""
        base_doc, desired_doc = _load_fixture("paragraph_split")
        base = sequence_from_doc_json(base_doc)
        desired = sequence_from_doc_json(desired_doc)
        result = align_content(base, desired)
        # 1 desired insert expected (the split produced a new paragraph)
        assert len(result.desired_inserts) >= 1


class TestFixtureParagraphToHeading:
    """paragraph_to_heading: role change, same text."""

    def test_alignment_valid(self):
        base_doc, desired_doc = _load_fixture("paragraph_to_heading")
        base = sequence_from_doc_json(base_doc)
        desired = sequence_from_doc_json(desired_doc)
        result = align_content(base, desired)
        assert_valid(result, base, desired)

    def test_terminals_matched(self):
        base_doc, desired_doc = _load_fixture("paragraph_to_heading")
        base = sequence_from_doc_json(base_doc)
        desired = sequence_from_doc_json(desired_doc)
        result = align_content(base, desired)
        assert_terminals_matched(result, base, desired)

    def test_paragraph_matched_not_replaced(self):
        """The paragraph (now heading) should be matched, not delete+inserted."""
        base_doc, desired_doc = _load_fixture("paragraph_to_heading")
        base = sequence_from_doc_json(base_doc)
        desired = sequence_from_doc_json(desired_doc)
        result = align_content(base, desired)
        # Should have minimal deletions — the paragraph text is preserved
        assert_identical_matched(result, base, desired)


class TestFixtureTextReplace:
    """text_replace: one paragraph text edited."""

    def test_alignment_valid(self):
        base_doc, desired_doc = _load_fixture("text_replace")
        base = sequence_from_doc_json(base_doc)
        desired = sequence_from_doc_json(desired_doc)
        result = align_content(base, desired)
        assert_valid(result, base, desired)

    def test_terminals_matched(self):
        base_doc, desired_doc = _load_fixture("text_replace")
        base = sequence_from_doc_json(base_doc)
        desired = sequence_from_doc_json(desired_doc)
        result = align_content(base, desired)
        assert_terminals_matched(result, base, desired)

    def test_edited_paragraph_matched(self):
        """The edited paragraph should be matched (not delete+insert)."""
        base_doc, desired_doc = _load_fixture("text_replace")
        base = sequence_from_doc_json(base_doc)
        desired = sequence_from_doc_json(desired_doc)
        result = align_content(base, desired)
        # text_replace: only 1 paragraph changes text slightly
        # All non-structural elements should be matched
        non_terminal_para_matches = [
            cm
            for cm in result.matches
            if base[cm.base_idx].kind == NodeKind.PARAGRAPH
            and not base[cm.base_idx].is_terminal
        ]
        assert len(non_terminal_para_matches) >= 1


class TestFixtureListAppend:
    """list_append: one list item added at end."""

    def test_alignment_valid(self):
        base_doc, desired_doc = _load_fixture("list_append")
        base = sequence_from_doc_json(base_doc)
        desired = sequence_from_doc_json(desired_doc)
        result = align_content(base, desired)
        assert_valid(result, base, desired)

    def test_terminals_matched(self):
        base_doc, desired_doc = _load_fixture("list_append")
        base = sequence_from_doc_json(base_doc)
        desired = sequence_from_doc_json(desired_doc)
        result = align_content(base, desired)
        assert_terminals_matched(result, base, desired)

    def test_no_spurious_deletes(self):
        base_doc, desired_doc = _load_fixture("list_append")
        base = sequence_from_doc_json(base_doc)
        desired = sequence_from_doc_json(desired_doc)
        result = align_content(base, desired)
        # Appending items should produce only inserts, not deletes of existing content
        # (existing bullet paras should be matched or at least not all deleted)
        assert len(result.base_deletes) <= 1  # at most the modified list block


class TestFixtureListKindChange:
    """list_kind_change: list type changes."""

    def test_alignment_valid(self):
        base_doc, desired_doc = _load_fixture("list_kind_change")
        base = sequence_from_doc_json(base_doc)
        desired = sequence_from_doc_json(desired_doc)
        result = align_content(base, desired)
        assert_valid(result, base, desired)

    def test_terminals_matched(self):
        base_doc, desired_doc = _load_fixture("list_kind_change")
        base = sequence_from_doc_json(base_doc)
        desired = sequence_from_doc_json(desired_doc)
        result = align_content(base, desired)
        assert_terminals_matched(result, base, desired)


class TestFixtureTableCellTextReplace:
    """table_cell_text_replace: one cell text edited."""

    def test_alignment_valid(self):
        base_doc, desired_doc = _load_fixture("table_cell_text_replace")
        base = sequence_from_doc_json(base_doc)
        desired = sequence_from_doc_json(desired_doc)
        result = align_content(base, desired)
        assert_valid(result, base, desired)

    def test_terminals_matched(self):
        base_doc, desired_doc = _load_fixture("table_cell_text_replace")
        base = sequence_from_doc_json(base_doc)
        desired = sequence_from_doc_json(desired_doc)
        result = align_content(base, desired)
        assert_terminals_matched(result, base, desired)

    def test_table_matched_not_replaced(self):
        """The table with one cell changed should be matched, not delete+inserted."""
        base_doc, desired_doc = _load_fixture("table_cell_text_replace")
        base = sequence_from_doc_json(base_doc)
        desired = sequence_from_doc_json(desired_doc)
        result = align_content(base, desired)
        # Table should be in matches
        table_matches = [
            cm for cm in result.matches if base[cm.base_idx].kind == NodeKind.TABLE
        ]
        assert len(table_matches) >= 1


class TestFixtureTableRowInsert:
    """table_row_insert: one row added to a table."""

    def test_alignment_valid(self):
        base_doc, desired_doc = _load_fixture("table_row_insert")
        base = sequence_from_doc_json(base_doc)
        desired = sequence_from_doc_json(desired_doc)
        result = align_content(base, desired)
        assert_valid(result, base, desired)

    def test_terminals_matched(self):
        base_doc, desired_doc = _load_fixture("table_row_insert")
        base = sequence_from_doc_json(base_doc)
        desired = sequence_from_doc_json(desired_doc)
        result = align_content(base, desired)
        assert_terminals_matched(result, base, desired)

    def test_table_matched_after_row_insert(self):
        """Table with an extra row still has significant cell overlap → matched."""
        base_doc, desired_doc = _load_fixture("table_row_insert")
        base = sequence_from_doc_json(base_doc)
        desired = sequence_from_doc_json(desired_doc)
        result = align_content(base, desired)
        table_matches = [
            cm for cm in result.matches if base[cm.base_idx].kind == NodeKind.TABLE
        ]
        assert len(table_matches) >= 1


class TestFixtureOperationalNotesRepair:
    """operational_notes_repair: complex real-world document."""

    def test_alignment_valid(self):
        base_doc, desired_doc = _load_fixture("operational_notes_repair")
        base = sequence_from_doc_json(base_doc)
        desired = sequence_from_doc_json(desired_doc)
        result = align_content(base, desired)
        assert_valid(result, base, desired)

    def test_terminals_matched(self):
        base_doc, desired_doc = _load_fixture("operational_notes_repair")
        base = sequence_from_doc_json(base_doc)
        desired = sequence_from_doc_json(desired_doc)
        result = align_content(base, desired)
        assert_terminals_matched(result, base, desired)

    def test_no_identical_content_deleted_and_inserted(self):
        base_doc, desired_doc = _load_fixture("operational_notes_repair")
        base = sequence_from_doc_json(base_doc)
        desired = sequence_from_doc_json(desired_doc)
        result = align_content(base, desired)
        assert_identical_matched(result, base, desired)


# ===========================================================================
# PART 6: Property-based fuzz tests
# ===========================================================================


def _random_para(rng: random.Random, vocab: list[str]) -> ContentNode:
    n_words = rng.randint(1, 8)
    text = " ".join(rng.choice(vocab) for _ in range(n_words)) + "\n"
    return make_para(text)


def _random_sequence(
    rng: random.Random,
    length: int,
    vocab: list[str],
    *,
    include_tables: bool = False,
) -> list[ContentNode]:
    nodes = []
    for _ in range(length):
        if include_tables and rng.random() < 0.2:
            n_cells = rng.randint(2, 6)
            cells = [rng.choice(vocab) for _ in range(n_cells)]
            nodes.append(make_table_node(cells))
        else:
            nodes.append(_random_para(rng, vocab))
    # Add terminal
    nodes.append(make_terminal_para())
    return nodes


def _mutate_sequence(
    rng: random.Random,
    seq: list[ContentNode],
    vocab: list[str],
    n_mutations: int = 1,
) -> list[ContentNode]:
    """Return a mutated copy of seq (does not modify terminal)."""
    import copy as _copy

    new_seq = _copy.deepcopy(seq)
    # We never mutate the terminal (last element)
    content = new_seq[:-1]
    terminal = new_seq[-1]

    for _ in range(n_mutations):
        if not content:
            content.append(_random_para(rng, vocab))
            continue
        op = rng.choice(["insert", "delete", "edit"])
        if op == "insert":
            pos = rng.randint(0, len(content))
            content.insert(pos, _random_para(rng, vocab))
        elif op == "delete" and len(content) > 1:
            pos = rng.randint(0, len(content) - 1)
            content.pop(pos)
        elif op == "edit" and content:
            pos = rng.randint(0, len(content) - 1)
            content[pos] = _random_para(rng, vocab)

    return [*content, terminal]


class TestFuzz:
    """Property-based fuzz tests verifying alignment invariants."""

    def test_fuzz_200_correctness(self):
        """Run 200 random mutation scenarios and verify all invariants."""
        rng = random.Random(42)
        vocab = [f"word{i}" for i in range(15)]
        failures: list[str] = []

        for case_idx in range(200):
            length = rng.randint(1, 8)
            base = _random_sequence(
                rng, length, vocab, include_tables=(case_idx % 5 == 0)
            )
            n_mut = rng.randint(1, 3)
            desired = _mutate_sequence(rng, base, vocab, n_mutations=n_mut)

            result = align_content(base, desired)
            ok, reason = _is_valid_alignment(result, base, desired)
            if not ok:
                failures.append(f"Case {case_idx}: {reason}")
                continue

            # Terminal constraint
            if base and desired:
                m, n = len(base), len(desired)
                if result.matches:
                    last = result.matches[-1]
                    if last.base_idx != m - 1 or last.desired_idx != n - 1:
                        failures.append(
                            f"Case {case_idx}: Terminal not last match: {last}, m={m}, n={n}"
                        )

        if failures:
            summary = "\n".join(failures[:5])
            if len(failures) > 5:
                summary += f"\n... and {len(failures) - 5} more"
            pytest.fail(f"{len(failures)}/200 fuzz cases failed:\n{summary}")

    def test_fuzz_identical_sequences_zero_cost(self):
        """Identical sequences always produce zero cost and full match."""
        rng = random.Random(99)
        vocab = [f"w{i}" for i in range(12)]

        for _ in range(200):
            length = rng.randint(1, 6)
            base = _random_sequence(rng, length, vocab)
            result = align_content(base, base)
            ok, reason = _is_valid_alignment(result, base, base)
            assert ok, reason
            assert (
                result.total_cost == 0.0
            ), f"Expected zero cost for identical sequences, got {result.total_cost}"
            assert (
                result.base_deletes == []
            ), f"Unexpected deletes for identical: {result.base_deletes}"
            assert (
                result.desired_inserts == []
            ), f"Unexpected inserts for identical: {result.desired_inserts}"

    def test_fuzz_order_preserving(self):
        """Matches are always strictly order-preserving."""
        rng = random.Random(77)
        vocab = [f"v{i}" for i in range(10)]

        for case_idx in range(200):
            length = rng.randint(1, 7)
            base = _random_sequence(rng, length, vocab)
            desired = _mutate_sequence(rng, base, vocab, n_mutations=rng.randint(1, 2))
            result = align_content(base, desired)
            for k in range(len(result.matches) - 1):
                a, b = result.matches[k], result.matches[k + 1]
                assert (
                    a.base_idx < b.base_idx
                ), f"Case {case_idx}: base_idx not strictly increasing at k={k}: {a}, {b}"
                assert (
                    a.desired_idx < b.desired_idx
                ), f"Case {case_idx}: desired_idx not strictly increasing at k={k}: {a}, {b}"

    def test_fuzz_cost_never_worse_than_delete_all_insert_all(self):
        """The DP cost must be ≤ cost of deleting all base and inserting all desired."""
        rng = random.Random(55)
        vocab = [f"x{i}" for i in range(10)]

        for case_idx in range(200):
            length = rng.randint(1, 6)
            base = _random_sequence(rng, length, vocab)
            desired = _mutate_sequence(rng, base, vocab, n_mutations=rng.randint(1, 2))
            result = align_content(base, desired)

            # Upper bound: delete non-terminal base + insert non-terminal desired
            upper = sum(delete_penalty(b) for b in base if not b.is_terminal) + sum(
                insert_penalty(d) for d in desired if not d.is_terminal
            )
            assert (
                result.total_cost <= upper + 1e-6
            ), f"Case {case_idx}: cost {result.total_cost} > upper bound {upper}"

    def test_fuzz_terminals_always_matched(self):
        """Terminal elements are always matched, never in deletes/inserts."""
        rng = random.Random(33)
        vocab = [f"t{i}" for i in range(8)]

        for case_idx in range(200):
            length = rng.randint(1, 7)
            base = _random_sequence(rng, length, vocab)
            desired = _mutate_sequence(rng, base, vocab, n_mutations=rng.randint(1, 3))
            result = align_content(base, desired)

            m, n = len(base), len(desired)
            assert (
                m - 1 not in result.base_deletes
            ), f"Case {case_idx}: terminal base[{m-1}] in base_deletes"
            assert (
                n - 1 not in result.desired_inserts
            ), f"Case {case_idx}: terminal desired[{n-1}] in desired_inserts"
            if result.matches:
                last = result.matches[-1]
                assert (
                    last.base_idx == m - 1
                ), f"Case {case_idx}: last match base_idx={last.base_idx} != {m-1}"
                assert (
                    last.desired_idx == n - 1
                ), f"Case {case_idx}: last match desired_idx={last.desired_idx} != {n-1}"

    def test_fuzz_identical_elements_at_same_position_matched(self):
        """When a single element differs, all others (identical) should be matched.

        This tests the specific case: one mutation (delete or insert) from base
        to desired.  With only one mutation, every element that exists in both
        sequences at the right relative position must be matched.

        Note: The global DP may legitimately delete+insert an identical element
        if doing so avoids deleting a *more expensive* element elsewhere.  This
        test focuses on the simpler one-mutation scenario where no such trade-off
        exists.
        """
        rng = random.Random(11)

        failures: list[str] = []
        for case_idx in range(200):
            length = rng.randint(2, 5)
            # Create base with distinct texts so there's no ambiguity
            base_texts = [
                " ".join(f"unique{case_idx}_{i}_{k}" for k in range(3)) + "\n"
                for i in range(length)
            ]
            base = [make_para(t) for t in base_texts] + [make_terminal_para()]

            # Single delete mutation: remove element at random position
            if length > 1:
                del_pos = rng.randint(0, length - 1)
                desired_texts = base_texts[:del_pos] + base_texts[del_pos + 1 :]
                desired = [make_para(t) for t in desired_texts] + [make_terminal_para()]

                result = align_content(base, desired)
                ok, reason = _is_valid_alignment(result, base, desired)
                if not ok:
                    failures.append(f"Case {case_idx} delete: {reason}")
                    continue

                # All preserved texts should be matched
                for i, _t in enumerate(base_texts):
                    if i == del_pos:
                        # This one was deleted
                        if i not in result.base_deletes:
                            failures.append(
                                f"Case {case_idx}: deleted element at base[{i}] not in base_deletes"
                            )
                    else:
                        # Should be matched
                        matched_base = {cm.base_idx for cm in result.matches}
                        if i not in matched_base and i < len(base) - 1:
                            failures.append(
                                f"Case {case_idx}: preserved element at base[{i}] not in matches"
                            )

        if failures:
            summary = "\n".join(failures[:5])
            if len(failures) > 5:
                summary += f"\n... and {len(failures) - 5} more"
            pytest.fail(f"{len(failures)}/200 fuzz cases failed:\n{summary}")


# ===========================================================================
# PART 7: Complex document (golden file) tests
# ===========================================================================


def _load_golden(file_id: str) -> dict:
    path = GOLDEN_DIR / f"{file_id}.json"
    with path.open() as f:
        return json.load(f)


def _modify_one_paragraph(
    nodes: list[ContentNode],
    idx: int,
    new_text: str,
) -> list[ContentNode]:
    """Return a copy of nodes with nodes[idx].text replaced."""
    result = list(nodes)
    original = nodes[idx]
    result[idx] = ContentNode(
        kind=original.kind,
        text=new_text,
        inline_element_count=original.inline_element_count,
        list_kind=original.list_kind,
        table_cell_texts=original.table_cell_texts,
        num_cells=original.num_cells,
        is_terminal=original.is_terminal,
        original=original.original,
    )
    return result


GOLDEN_IDS = [
    "14nMj7vggV3XR3WQtYcgrABRABjKk-fqw0UQUCP25rhQ",
    "1YicNYwId9u4okuK4uNfWdTEuKyS1QWb1RcnZl9eVyTc",
]


@pytest.mark.parametrize("doc_id", GOLDEN_IDS)
class TestGoldenDocument:
    def test_self_alignment_perfect(self, doc_id: str):
        """Aligning a document against itself: zero cost, all matched."""
        doc = _load_golden(doc_id)
        nodes = sequence_from_doc_json(doc)
        result = align_content(nodes, nodes)
        assert_valid(result, nodes, nodes)
        assert result.total_cost == 0.0, f"Expected zero cost, got {result.total_cost}"
        assert result.base_deletes == [], f"Expected no deletes: {result.base_deletes}"
        assert (
            result.desired_inserts == []
        ), f"Expected no inserts: {result.desired_inserts}"
        assert len(result.matches) == len(nodes)

    def test_one_paragraph_slightly_modified_matched(self, doc_id: str):
        """Slightly modifying one paragraph: it should be matched, not delete+inserted."""
        doc = _load_golden(doc_id)
        nodes = sequence_from_doc_json(doc)

        # Find a non-terminal paragraph with substantive text
        target_idx = None
        for i, node in enumerate(nodes[:-1]):
            if node.kind == NodeKind.PARAGRAPH and len(node.text.strip()) > 20:
                target_idx = i
                break

        if target_idx is None:
            pytest.skip(f"No substantive paragraph found in {doc_id}")

        original_text = nodes[target_idx].text
        # Slight modification: append a word
        modified_text = original_text.rstrip("\n") + " (slightly modified)\n"
        desired = _modify_one_paragraph(nodes, target_idx, modified_text)

        result = align_content(nodes, desired)
        assert_valid(result, nodes, desired)
        assert_terminals_matched(result, nodes, desired)

        # The modified paragraph should be matched
        matched_base_indices = {cm.base_idx for cm in result.matches}
        assert (
            target_idx in matched_base_indices
        ), f"Modified paragraph at index {target_idx} was not matched"

    def test_paragraph_removed_from_middle(self, doc_id: str):
        """Removing a paragraph: all others should remain matched."""
        doc = _load_golden(doc_id)
        nodes = sequence_from_doc_json(doc)

        if len(nodes) < 4:
            pytest.skip(f"Document {doc_id} too short for this test")

        # Remove the element at index 2 (skip sectionBreak at 0, terminal at -1)
        remove_idx = min(2, len(nodes) - 2)
        desired = nodes[:remove_idx] + nodes[remove_idx + 1 :]
        # Re-mark terminal
        desired[-1] = ContentNode(
            kind=desired[-1].kind,
            text=desired[-1].text,
            inline_element_count=desired[-1].inline_element_count,
            list_kind=desired[-1].list_kind,
            table_cell_texts=desired[-1].table_cell_texts,
            num_cells=desired[-1].num_cells,
            is_terminal=True,
            original=desired[-1].original,
        )

        result = align_content(nodes, desired)
        assert_valid(result, nodes, desired)
        assert_terminals_matched(result, nodes, desired)

        # Exactly one base element should be in base_deletes
        assert len(result.base_deletes) == 1
        assert result.base_deletes[0] == remove_idx

    def test_new_paragraph_inserted(self, doc_id: str):
        """Adding a new paragraph: all originals should remain matched."""
        doc = _load_golden(doc_id)
        nodes = sequence_from_doc_json(doc)

        if len(nodes) < 3:
            pytest.skip(f"Document {doc_id} too short for this test")

        # Insert a unique new paragraph at position 2
        new_node = make_para("This is a completely new paragraph that was inserted.\n")
        insert_pos = min(2, len(nodes) - 1)
        desired = [*nodes[:insert_pos], new_node, *nodes[insert_pos:]]
        # Re-mark terminal (last element)
        desired[-1] = ContentNode(
            kind=desired[-1].kind,
            text=desired[-1].text,
            inline_element_count=desired[-1].inline_element_count,
            list_kind=desired[-1].list_kind,
            table_cell_texts=desired[-1].table_cell_texts,
            num_cells=desired[-1].num_cells,
            is_terminal=True,
            original=desired[-1].original,
        )

        result = align_content(nodes, desired)
        assert_valid(result, nodes, desired)
        assert_terminals_matched(result, nodes, desired)

        # Exactly one desired element should be in desired_inserts
        assert len(result.desired_inserts) == 1
        assert result.desired_inserts[0] == insert_pos

    def test_performance_reasonable(self, doc_id: str):
        """The DP should complete in reasonable time for large documents."""
        import time

        doc = _load_golden(doc_id)
        nodes = sequence_from_doc_json(doc)

        start = time.perf_counter()
        result = align_content(nodes, nodes)
        elapsed = time.perf_counter() - start

        assert (
            elapsed < 10.0
        ), f"Alignment took {elapsed:.2f}s for {len(nodes)}-element document"
        # Self-alignment sanity check
        assert result.total_cost == 0.0


# ===========================================================================
# Helpers for text_similarity unit tests
# ===========================================================================


class TestTextSimilarity:
    def test_identical(self):
        assert text_similarity("hello world", "hello world") == 1.0

    def test_both_empty(self):
        assert text_similarity("", "") == 1.0

    def test_one_empty(self):
        assert text_similarity("hello", "") == 0.0
        assert text_similarity("", "hello") == 0.0

    def test_disjoint(self):
        assert text_similarity("alpha beta", "gamma delta") == 0.0

    def test_partial_overlap(self):
        # "hello world" ∩ "hello there" = {"hello"}, union = {"hello", "world", "there"}
        sim = text_similarity("hello world", "hello there")
        assert abs(sim - 1 / 3) < 1e-9

    def test_case_insensitive(self):
        assert text_similarity("Hello World", "hello world") == 1.0

    def test_subset(self):
        # "hello" is subset of "hello world" — jaccard = 1/2
        sim = text_similarity("hello", "hello world")
        assert abs(sim - 0.5) < 1e-9


class TestDeleteInsertPenalty:
    def test_terminal_paragraph_infinite_penalty(self):
        node = make_terminal_para("some text\n")
        assert delete_penalty(node) == INFINITE_PENALTY
        assert insert_penalty(node) == INFINITE_PENALTY

    def test_empty_paragraph_low_penalty(self):
        node = make_para("")
        assert delete_penalty(node) == 0.0

    def test_longer_text_higher_penalty(self):
        short = make_para("hi\n")
        long = make_para("this is a much longer paragraph with many words\n")
        assert delete_penalty(long) > delete_penalty(short)

    def test_table_penalty_scales_with_cells(self):
        small = make_table_node(["a", "b"])
        large = make_table_node(["a", "b", "c", "d", "e", "f"])
        assert delete_penalty(large) > delete_penalty(small)


class TestMatchable:
    def test_identical_paras_matchable(self):
        a = make_para("hello world\n")
        b = make_para("hello world\n")
        assert matchable(a, b)

    def test_para_and_table_not_matchable(self):
        a = make_para("hello world\n")
        b = make_table_node(["hello", "world"])
        assert not matchable(a, b)

    def test_completely_different_paras_not_matchable(self):
        a = make_para("alpha beta gamma delta\n")
        b = make_para("epsilon zeta eta theta\n")
        assert not matchable(a, b)

    def test_slightly_similar_paras_matchable(self):
        a = make_para("the quick brown fox\n")
        b = make_para("the quick brown dog\n")
        assert matchable(a, b)

    def test_section_breaks_always_matchable(self):
        a = make_section_break()
        b = make_section_break()
        assert matchable(a, b)

    def test_page_breaks_always_matchable(self):
        a = make_page_break()
        b = make_page_break()
        assert matchable(a, b)

    def test_table_with_shared_cells_matchable(self):
        a = make_table_node(["x", "y", "z"])
        b = make_table_node(["x", "y", "w"])
        assert matchable(a, b)

    def test_completely_different_tables_not_matchable(self):
        a = make_table_node(["aaa", "bbb"])
        b = make_table_node(["xxx", "yyy"])
        assert not matchable(a, b)
