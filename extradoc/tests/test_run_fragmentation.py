"""Tests for text-run fragmentation bugs in the push workflow.

Two mechanisms can cause the reconciler to emit multiple consecutive
``updateTextStyle`` requests for contiguous sub-ranges that share the same
style.  The Google Docs API splits runs at every ``updateTextStyle`` boundary,
so each push cycle increases run fragmentation.

Mechanism 1 — ``_emit_insert_with_style`` (reconcile_v3/lower.py)
  When text is inserted or replaced, ``_emit_insert_with_style`` iterates over
  ``desired_spans`` and emits one ``updateTextStyle`` per span when the span's
  style differs from the inherited style.  If the desired document has two
  consecutive runs with IDENTICAL styles (e.g. both bold), two requests are
  emitted for contiguous sub-ranges — fragmenting the run on the real API.

Mechanism 2 — ``_merge_changed_paragraph`` (diffmerge/apply_ops.py)
  When a changed paragraph has a single desired run that spans multiple base
  runs with equal merged styles, the function splits the desired run at each
  base run boundary.  These unnecessary sub-runs then reach ``_emit_insert_with_style``
  as multiple consecutive same-style spans, triggering Mechanism 1.

Both tests are marked ``xfail(strict=True)`` — they document the current
broken behaviour and will be promoted to passing tests once the bugs are fixed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from extradoc.api_types._generated import (
    Document,
    Paragraph,
    ParagraphElement,
    ParagraphStyle,
    StructuralElement,
    TextRun,
    TextStyle,
)
from extradoc.comments._types import DocumentWithComments, FileComments
from extradoc.reconcile_v3.api import reconcile_batches
from extradoc.serde.markdown import MarkdownSerde


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_doc(content: list[dict[str, Any]]) -> Document:
    """Wrap body ``content`` in a minimal multi-tab Document."""
    return Document.model_validate(
        {
            "documentId": "testdoc",
            "title": "Test",
            "tabs": [
                {
                    "tabProperties": {"tabId": "t.0", "title": "Tab 1", "index": 0},
                    "documentTab": {
                        "body": {
                            "content": [{"sectionBreak": {"sectionStyle": {}}}]
                            + content
                        }
                    },
                }
            ],
        }
    )


def _make_doc_with_indices(content: list[dict[str, Any]]) -> Document:
    """Like ``_make_doc`` but assigns concrete ``startIndex``/``endIndex`` fields
    via the mock's reindex pass so the lowering layer can do index arithmetic.
    """
    from tests.reconcile_v3.helpers import reindex_document

    raw = _make_doc(content)
    return reindex_document(raw)


def _make_run(text: str, **style_kwargs: Any) -> dict[str, Any]:
    """Build a paragraph element dict for a single text run."""
    ts = style_kwargs if style_kwargs else {}
    return {"textRun": {"content": text, "textStyle": ts}}


def _make_para(runs: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a paragraph dict from a list of textRun element dicts."""
    return {
        "paragraph": {
            "elements": runs + [_make_run("\n")],
            "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
        }
    }


def _all_requests(batches: list) -> list[Any]:
    """Flatten all requests from a list of BatchUpdateDocumentRequest."""
    return [req for batch in batches for req in (batch.requests or [])]


def _update_text_style_requests(reqs: list[Any]) -> list[Any]:
    """Filter to only ``updateTextStyle`` requests."""
    return [r for r in reqs if r.update_text_style is not None]


# ---------------------------------------------------------------------------
# Mechanism 1: consecutive same-style spans produce ONE updateTextStyle
# ---------------------------------------------------------------------------


def test_consecutive_same_style_spans_produce_one_update_text_style() -> None:
    """Two consecutive bold desired spans should produce ONE updateTextStyle.

    Scenario
    --------
    Base document: one paragraph containing plain text "ZZZZZZZZZZ\\n" (no bold,
    no characters in common with the desired text so the diff produces a single
    ``replace`` opcode with no LCS-preserving equal chunks).
    Desired document: the paragraph is replaced with "Hello World\\n" where BOTH
    "Hello " and "World" come from separate paragraph elements (runs) that are
    both bold.

    This simulates what happens after a round-trip through the markdown serde:
    the serializer writes ``**Hello World**`` but the parser creates two runs
    (due to pre-existing fragmentation in the base that was serialized as
    ``**Hello ****World**``), both with ``bold=True``.

    Expected (correct) behaviour
    ----------------------------
    The reconciler should emit exactly ONE ``updateTextStyle`` request covering
    the entire "Hello World" replacement, not two separate requests — one for
    "Hello " and one for "World".

    Current (buggy) behaviour
    -------------------------
    ``_emit_insert_with_style`` iterates desired_spans one span at a time and
    emits a separate ``updateTextStyle`` for each span whose style differs from
    the inherited style.  It has no look-ahead to merge adjacent equal-style
    spans, so two requests are emitted.
    """
    # Base: plain text paragraph — no bold, no chars in common with desired so
    # the diff produces a single replace opcode (no equal-chunk style updates).
    base = _make_doc_with_indices(
        [
            _make_para([_make_run("ZZZZZZZZZZ\n")]),
        ]
    )

    # Desired: two separate bold runs (same style) simulating pre-existing
    # fragmentation that survived the markdown round-trip.
    desired_content = [
        _make_para(
            [
                _make_run("Hello ", bold=True),
                _make_run("World\n", bold=True),
            ]
        )
    ]
    desired = _make_doc(desired_content)

    batches = reconcile_batches(base, desired)
    all_reqs = _all_requests(batches)
    style_reqs = _update_text_style_requests(all_reqs)

    # The replacement is one logical bold span — should map to ONE updateTextStyle.
    assert len(style_reqs) == 1, (
        f"Expected exactly 1 updateTextStyle for the bold region, got {len(style_reqs)}. "
        f"Consecutive same-style spans are being emitted as separate requests, "
        f"which fragments runs on the Google Docs API.\n"
        f"Requests: {style_reqs}"
    )


# ---------------------------------------------------------------------------
# Mechanism 2: _merge_changed_paragraph splits equal-style sub-runs
# ---------------------------------------------------------------------------


def test_merge_changed_paragraph_does_not_split_equal_style_sub_runs(
    tmp_path: Path,
) -> None:
    """A single bold desired run spanning two same-bold base runs → ONE updateTextStyle.

    Scenario
    --------
    Base document: one paragraph with three runs:
      - "ASHA " bold (run 1)
      - "FOUNDATION" bold (run 2, same style but separate run — pre-existing fragmentation)
      - "\\n" (trailing newline)

    LLM edit: the markdown serializes ``**ASHA FOUNDATION**`` (one span), and
    the LLM appends " Inc" so the paragraph becomes ``**ASHA FOUNDATION Inc**``.

    Expected (correct) behaviour
    ----------------------------
    The desired document should have ONE bold run "ASHA FOUNDATION Inc\\n".
    The reconciler should emit:
      - one ``insertText`` for " Inc" at the end
      - at most ONE ``updateTextStyle`` covering the newly inserted text (if needed)
    It must NOT emit multiple ``updateTextStyle`` calls for the unchanged
    "ASHA FOUNDATION" region.

    Current (buggy) behaviour
    -------------------------
    ``_merge_changed_paragraph`` finds two base runs in the [0, len("ASHA FOUNDATION"))
    range and splits the single desired bold run at the base run boundary (after
    "ASHA ").  The two resulting sub-runs both have bold=True but are separate
    spans in the desired document.  This triggers Mechanism 1: two
    ``updateTextStyle`` requests are emitted for "ASHA " and "FOUNDATION"
    respectively even though neither changed.
    """
    # Base document: two same-bold runs (pre-existing fragmentation).
    base_content = [
        _make_para(
            [
                _make_run("ASHA ", bold=True),
                _make_run("FOUNDATION", bold=True),
                _make_run("\n"),
            ]
        )
    ]
    base = _make_doc_with_indices(base_content)

    # Simulate pull → LLM edit → push using the markdown serde round-trip.
    # The serde will serialize both bold runs as one ``**ASHA FOUNDATION**``
    # span.  The LLM appends " Inc".
    bundle = DocumentWithComments(
        document=base,
        comments=FileComments(file_id="testdoc"),
    )
    serde = MarkdownSerde()
    folder = tmp_path / "doc"
    serde.serialize(bundle, folder)

    # Find the tab file and apply the LLM edit.
    tab_file = folder / "tabs" / "Tab_1.md"
    if not tab_file.exists():
        tab_file = folder / "Tab_1.md"
    md = tab_file.read_text(encoding="utf-8")

    # The serializer should have produced a single **ASHA FOUNDATION** span.
    assert "ASHA FOUNDATION" in md, (
        f"Serialized markdown did not contain 'ASHA FOUNDATION':\n{md}"
    )

    # LLM appends " Inc" inside the bold span.
    md = md.replace("**ASHA FOUNDATION**", "**ASHA FOUNDATION Inc**")
    tab_file.write_text(md, encoding="utf-8")

    result = serde.deserialize(folder)
    base_doc = result.base.document
    desired_doc = result.desired.document

    batches = reconcile_batches(base_doc, desired_doc)
    all_reqs = _all_requests(batches)
    style_reqs = _update_text_style_requests(all_reqs)

    # The only updateTextStyle request(s) should be for the newly inserted
    # " Inc" text (if its style differs from the inherited run style).
    # There must be NO updateTextStyle for the unchanged "ASHA FOUNDATION"
    # region — i.e. at most 1 updateTextStyle total (for " Inc"), not 2 or 3.
    assert len(style_reqs) <= 1, (
        f"Expected at most 1 updateTextStyle (for newly inserted ' Inc'), "
        f"got {len(style_reqs)}. The unchanged 'ASHA FOUNDATION' region is "
        f"generating spurious updateTextStyle requests due to run splitting in "
        f"_merge_changed_paragraph.\n"
        f"Requests: {style_reqs}"
    )
