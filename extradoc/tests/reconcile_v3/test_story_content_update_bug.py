"""Xfail reproductions for the story-content-update stale-index bug.

Bug summary
-----------
When ``_lower_story_content_update`` generates a batch with both deletes
and inserts to replace content in a body, some delete coordinates are
computed against BASE indices and emitted AFTER preceding inserts have
already shifted content forward. The stale deleteContentRange then
references a range that now points into newly-inserted content and
Google Docs API rejects it with HTTP 400.

Concrete example (see ``/tmp/qa_bugs/T1_baseline_replace_fails``):

    Base body:
      [  0..  1) SB
      [  1.. 40) P "Appended paragraph after the list item\\n"
      [ 40.. 93) P "Plain text reset content for testing purposes abcdef\\n"

    Desired body: h1, paragraph, 3x2 table, paragraph, 3 bullets.

    Generated batch (partial):
      [ 0] deleteContentRange [1..40)          <- deletes first base paragraph
      [ 1] deleteContentRange [0..1)           <- deletes leading SB
      [ 2..14] 13 inserts at index 0 (total +167 chars)
      [15..29] bullet / style setup
      [30] deleteContentRange [0..52)          <-- STALE. Should delete the
                                                   second base paragraph, but
                                                   after 13 inserts pushed
                                                   content forward, [0..52)
                                                   references newly-inserted
                                                   text.

These xfail tests simulate the Google Docs API's sequential request
execution by tracking the running length of the body story segment.
Any ``deleteContentRange`` whose range lies outside the current segment
bounds after preceding requests have been applied is a bug.
"""

from __future__ import annotations

from extradoc.api_types._generated import (
    Bullet,
    Paragraph,
    ParagraphElement,
    ParagraphStyle,
    SectionBreak,
    SectionStyle,
    StructuralElement,
    TextRun,
)
from extradoc.indexer import utf16_len
from extradoc.reconcile_v3.api import reconcile_batches
from tests.reconcile_v3.helpers import (
    make_indexed_doc,
    make_indexed_para,
    make_para_el,
    make_table_el,
    make_terminal_para,
)

# ---------------------------------------------------------------------------
# Small inline helpers used only by these repros
# ---------------------------------------------------------------------------


def _make_section_break(start: int = 0) -> StructuralElement:
    """Build an indexed SectionBreak structural element."""
    return StructuralElement(
        start_index=start,
        end_index=start + 1,
        section_break=SectionBreak(section_style=SectionStyle()),
    )


def _make_bullet_para(text: str, list_id: str = "list1") -> StructuralElement:
    """Build a bulleted paragraph content element (no indices)."""
    return StructuralElement(
        paragraph=Paragraph(
            elements=[ParagraphElement(text_run=TextRun(content=text))],
            paragraph_style=ParagraphStyle(named_style_type="NORMAL_TEXT"),
            bullet=Bullet(list_id=list_id),
        )
    )


# ---------------------------------------------------------------------------
# Body-length simulator
# ---------------------------------------------------------------------------


def _simulate_requests_and_find_stale_deletes(
    batches, initial_body_len: int
) -> list[str]:
    """Simulate sequential request application and flag stale deletes.

    Tracks a per-position "origin" tag for every byte currently in the
    body:

      * "B" — a byte that was present in the base document and has never
        been deleted.
      * "I" — a byte that was inserted by a request in this batch.

    A ``deleteContentRange`` is stale when any byte in its range is
    tagged "I" (it targets content that was just inserted, rather than
    original base content). This is exactly the live-API failure mode:
    the reconciler computed the delete's range at base-time, emitted it
    after preceding inserts shifted content forward, and the now-stale
    range points into fresh content.

    Returns a list of human-readable violation strings. Empty list means
    OK.
    """
    # Represent the body as a list of origin tags, one per UTF-16 unit.
    origins: list[str] = ["B"] * initial_body_len

    violations: list[str] = []
    req_idx = 0
    for batch in batches:
        if batch.requests is None:
            continue
        for req in batch.requests:
            if req.delete_content_range is not None:
                rng = req.delete_content_range.range
                assert rng is not None
                start = rng.start_index
                end = rng.end_index
                assert start is not None and end is not None
                if end > len(origins):
                    violations.append(
                        f"req[{req_idx}] deleteContentRange: endIndex={end} "
                        f"> current body_len={len(origins)} "
                        f"(startIndex={start})"
                    )
                else:
                    inserted_bytes = [
                        i for i in range(start, end) if origins[i] == "I"
                    ]
                    if inserted_bytes:
                        violations.append(
                            f"req[{req_idx}] deleteContentRange [{start}..{end}) "
                            f"targets newly-inserted content at positions "
                            f"{inserted_bytes[:5]}"
                            + ("..." if len(inserted_bytes) > 5 else "")
                        )
                    del origins[start:end]

            elif req.insert_text is not None:
                it = req.insert_text
                assert it.location is not None
                assert it.location.index is not None
                assert it.text is not None
                idx = it.location.index
                delta = utf16_len(it.text)
                if idx > len(origins):
                    violations.append(
                        f"req[{req_idx}] insertText: index={idx} > "
                        f"current body_len={len(origins)}"
                    )
                    idx = len(origins)
                origins[idx:idx] = ["I"] * delta

            elif req.insert_table is not None:
                ins = req.insert_table
                assert ins.location is not None
                assert ins.location.index is not None
                idx = ins.location.index
                rows = ins.rows or 0
                cols = ins.columns or 0
                # Table skeleton: 1 + rows * (1 + cols * 2) UTF-16 units.
                delta = 1 + rows * (1 + cols * 2)
                if idx > len(origins):
                    violations.append(
                        f"req[{req_idx}] insertTable: index={idx} > "
                        f"current body_len={len(origins)}"
                    )
                    idx = len(origins)
                origins[idx:idx] = ["I"] * delta

            # Style-only / range-only requests do not modify origins.
            req_idx += 1
    return violations


# Keep the old name available as an alias for callers/tests.
_validate_requests_in_bounds = _simulate_requests_and_find_stale_deletes


# ---------------------------------------------------------------------------
# Xfail reproductions
# ---------------------------------------------------------------------------


def test_xfail_replace_body_with_heading_table_and_bullets() -> None:
    """Minimal repro matching the live T1 failure.

    Base body (93 chars total):
      [  0..  1) SB
      [  1.. 40) P "Appended paragraph after the list item\\n"
      [ 40.. 93) P "Plain text reset content for testing purposes abcdef\\n"

    Desired: heading + paragraph + 3x2 table + paragraph + 3 bullets.

    Observed bug: reconciler emits two deletes at the start (OK), then
    ~13 inserts, then style/bullet requests, then a **stale**
    deleteContentRange at the end that references the pre-insert
    position of the second base paragraph. After all preceding inserts,
    that range is outside the content the reconciler intended to remove
    and instead points into newly-inserted content.
    """
    first = "Appended paragraph after the list item\n"
    second = "Plain text reset content for testing purposes abcdef\n"
    first_end = 1 + utf16_len(first)
    second_end = first_end + utf16_len(second)
    initial_body_len = second_end  # 93 — last para is the terminal

    base = make_indexed_doc(
        body_content=[
            _make_section_break(0),
            make_indexed_para(first, 1),
            make_indexed_para(second, first_end),
        ]
    )

    desired = make_indexed_doc(
        body_content=[
            make_para_el("Fruits\n", named_style="HEADING_1"),
            make_para_el("This is a short paragraph about fruits.\n"),
            make_table_el(
                [["Fruit", "Color"], ["Apple", "Red"], ["Mango", "Yellow"]]
            ),
            make_para_el("Some text after the table.\n"),
            _make_bullet_para("First bullet\n"),
            _make_bullet_para("Second bullet\n"),
            _make_bullet_para("Third bullet\n"),
            make_terminal_para(),
        ]
    )

    batches = reconcile_batches(base, desired)
    violations = _validate_requests_in_bounds(batches, initial_body_len)
    assert violations == [], (
        "Generated batch references stale indices after preceding "
        "inserts:\n  " + "\n  ".join(violations)
    )


def test_xfail_insert_before_matched_update() -> None:
    """Two whole-element inserts precede a matched-element update.

    Base body:
      [0..1) SB
      [1..9) P "keep me\\n"      <- matched and kept (terminal)
    -> initial_body_len = 9

    Desired body:
      SB, P "first new para\\n", P "second new\\n", P "keep me\\n", terminal

    The last "keep me" paragraph matches the existing base paragraph.
    But two inserts at index 1 add ~26 chars before it. If the matched
    update targets the paragraph using its stale base index (1), its
    delete/style ranges will overlap newly-inserted content.
    """
    keep = "keep me\n"
    initial_body_len = 1 + utf16_len(keep)  # 9

    base = make_indexed_doc(
        body_content=[
            _make_section_break(0),
            make_indexed_para(keep, 1),
        ]
    )

    desired = make_indexed_doc(
        body_content=[
            make_para_el("first new para\n"),
            make_para_el("second new\n"),
            make_para_el("keep me\n"),
            make_terminal_para(),
        ]
    )

    batches = reconcile_batches(base, desired)
    violations = _validate_requests_in_bounds(batches, initial_body_len)
    assert violations == [], (
        "Matched-element update used stale index after preceding "
        "inserts:\n  " + "\n  ".join(violations)
    )


def test_xfail_insert_after_matched_update_no_overshift() -> None:
    """Matched update comes BEFORE any inserts — must not be shifted.

    Base body:
      [0..1) SB
      [1..31) P "early para with modified text\\n"  (30 chars)
      [31..41) P "late para\\n"                      (10 chars)
    -> initial_body_len = 41

    Desired body:
      SB,
      P "early para with different text\\n"  (early is EDITED),
      P "late para\\n"                       (kept as terminal-ish),
      P "inserted after\\n"                  (new insert),
      terminal

    The update to the early paragraph must NOT be shifted by the
    trailing insert. This guards against a fix that over-corrects by
    adding a post_insert_shift that applies even to updates whose match
    position is before the insertion point.
    """
    early = "early para with modified text\n"
    late = "late para\n"
    early_end = 1 + utf16_len(early)
    initial_body_len = early_end + utf16_len(late)

    base = make_indexed_doc(
        body_content=[
            _make_section_break(0),
            make_indexed_para(early, 1),
            make_indexed_para(late, early_end),
        ]
    )

    desired = make_indexed_doc(
        body_content=[
            make_para_el("early para with different text\n"),
            make_para_el("late para\n"),
            make_para_el("inserted after\n"),
            make_terminal_para(),
        ]
    )

    batches = reconcile_batches(base, desired)
    violations = _validate_requests_in_bounds(batches, initial_body_len)
    assert violations == [], (
        "Update indices were incorrectly shifted by a later insert:\n  "
        + "\n  ".join(violations)
    )


def test_xfail_mixed_delete_insert_update() -> None:
    """Simultaneously exercise pre_delete_shift and post_insert_shift.

    Base body:
      [0..1) SB
      [1..11) P "to delete\\n"                   (10 chars)
      [11..29) P "to keep but edit\\n"           (18 chars)
    -> initial_body_len = 29

    Desired body:
      SB,
      P "new insert\\n",                 (whole-element insert at top)
      P "to keep but edit EDITED\\n",    (matched update)
      terminal

    The matched update for "to keep but edit" needs BOTH: the delete of
    the first base paragraph pushing indices back, AND the whole-element
    insert of "new insert" pushing indices forward. Net shift may be
    non-zero and requires post_insert_shift to be correct.
    """
    para_del = "to delete\n"
    para_keep = "to keep but edit\n"
    del_end = 1 + utf16_len(para_del)
    initial_body_len = del_end + utf16_len(para_keep)

    base = make_indexed_doc(
        body_content=[
            _make_section_break(0),
            make_indexed_para(para_del, 1),
            make_indexed_para(para_keep, del_end),
        ]
    )

    desired = make_indexed_doc(
        body_content=[
            make_para_el("new insert\n"),
            make_para_el("to keep but edit EDITED\n"),
            make_terminal_para(),
        ]
    )

    batches = reconcile_batches(base, desired)
    violations = _validate_requests_in_bounds(batches, initial_body_len)
    assert violations == [], (
        "Mixed delete+insert+update emitted stale indices:\n  "
        + "\n  ".join(violations)
    )


def test_xfail_multiple_inserts_before_match() -> None:
    """Three whole-element inserts precede the matched update.

    Base body:
      [0..1) SB
      [1..13) P "target para\\n"   (12 chars)
    -> initial_body_len = 13

    Desired body:
      SB, P "a\\n", P "b\\n", P "c\\n",
      P "target para MODIFIED\\n", terminal

    Three inserts contribute +6 chars before the matched paragraph.
    Its matched-element update must account for all three shifts.
    """
    target = "target para\n"
    initial_body_len = 1 + utf16_len(target)  # 13

    base = make_indexed_doc(
        body_content=[
            _make_section_break(0),
            make_indexed_para(target, 1),
        ]
    )

    desired = make_indexed_doc(
        body_content=[
            make_para_el("a\n"),
            make_para_el("b\n"),
            make_para_el("c\n"),
            make_para_el("target para MODIFIED\n"),
            make_terminal_para(),
        ]
    )

    batches = reconcile_batches(base, desired)
    violations = _validate_requests_in_bounds(batches, initial_body_len)
    assert violations == [], (
        "Multiple-insert shift was not applied to matched update:\n  "
        + "\n  ".join(violations)
    )


def test_xfail_replace_single_paragraph_with_longer_text() -> None:
    """Simpler repro: replace a body paragraph with longer text.

    Base: [SB at 0..1, P "original text with twenty+ chars here\\n" at 1..40]
          -> body_len = 40

    Desired: [SB, P "much longer replacement text that is fifty plus chars
              long here\\n", terminal]

    This test is kept narrow on purpose — it is the minimal shape that
    exercises the same lowering path as the T1 repro (body-story update
    with both deletes and inserts where the desired content is longer
    than base).
    """
    original = "original text with twenty+ chars here\n"
    original_end = 1 + utf16_len(original)
    initial_body_len = original_end  # last P is the terminal

    base = make_indexed_doc(
        body_content=[
            _make_section_break(0),
            make_indexed_para(original, 1),
        ]
    )

    replacement = (
        "much longer replacement text that is fifty plus chars long here\n"
    )
    desired = make_indexed_doc(
        body_content=[
            make_para_el(replacement),
            make_terminal_para(),
        ]
    )

    batches = reconcile_batches(base, desired)
    violations = _validate_requests_in_bounds(batches, initial_body_len)
    assert violations == [], (
        "Generated batch references stale indices after preceding "
        "inserts:\n  " + "\n  ".join(violations)
    )
