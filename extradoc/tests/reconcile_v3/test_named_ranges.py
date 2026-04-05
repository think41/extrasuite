"""Named range diffing and reconciliation tests."""

from __future__ import annotations

from typing import Any

from extradoc.api_types._generated import (
    BatchUpdateDocumentRequest,
    Body,
    Document,
    DocumentTab,
    NamedRange,
    NamedRanges,
    NamedStyles,
    Paragraph,
    ParagraphElement,
    ParagraphStyle,
    Range,
    StructuralElement,
    Tab,
    TabProperties,
    TextRun,
)
from extradoc.reconcile_v3.api import reconcile_batches

# ---------------------------------------------------------------------------
# Document builder helpers (mirror the style in test_blackbox_gaps.py)
# ---------------------------------------------------------------------------


def _para(text: str, style: str = "NORMAL_TEXT") -> StructuralElement:
    return StructuralElement(
        paragraph=Paragraph(
            elements=[ParagraphElement(text_run=TextRun(content=text))],
            paragraph_style=ParagraphStyle(named_style_type=style),
        )
    )


def _indexed_para(
    text: str, start: int, style: str = "NORMAL_TEXT"
) -> StructuralElement:
    from extradoc.indexer import utf16_len

    end = start + utf16_len(text)
    return StructuralElement(
        start_index=start,
        end_index=end,
        paragraph=Paragraph(
            elements=[ParagraphElement(text_run=TextRun(content=text))],
            paragraph_style=ParagraphStyle(named_style_type=style),
        ),
    )


def _terminal(start: int | None = None) -> StructuralElement:
    if start is not None:
        return _indexed_para("\n", start)
    return _para("\n")


def _tab(
    tab_id: str,
    body_content: list[StructuralElement],
    named_ranges: dict[str, NamedRanges] | None = None,
) -> Tab:
    return Tab(
        tab_properties=TabProperties(tab_id=tab_id, title="Tab", index=0),
        document_tab=DocumentTab(
            body=Body(content=body_content),
            headers={},
            footers={},
            footnotes={},
            lists={},
            named_styles=NamedStyles(styles=[]),
            document_style={},
            inline_objects={},
            named_ranges=named_ranges or {},
        ),
    )


def _doc(
    body_content: list[StructuralElement],
    named_ranges: dict[str, NamedRanges] | None = None,
) -> Document:
    """Build a single-tab document with optional named ranges."""
    return Document(
        document_id="test_doc",
        tabs=[_tab("t1", body_content, named_ranges=named_ranges)],
    )


def _nr(
    name: str,
    nr_id: str,
    start: int,
    end: int,
    segment_id: str = "",
) -> NamedRanges:
    """Build a NamedRanges entry with a single NamedRange containing one Range."""
    return NamedRanges(
        name=name,
        named_ranges=[
            NamedRange(
                name=name,
                named_range_id=nr_id,
                ranges=[Range(start_index=start, end_index=end, segment_id=segment_id)],
            )
        ],
    )


def _nr_multi_ranges(
    name: str,
    nr_id: str,
    spans: list[tuple[int, int]],
    segment_id: str = "",
) -> NamedRanges:
    """Build a NamedRanges entry with a single NamedRange containing multiple Ranges."""
    return NamedRanges(
        name=name,
        named_ranges=[
            NamedRange(
                name=name,
                named_range_id=nr_id,
                ranges=[
                    Range(start_index=s, end_index=e, segment_id=segment_id)
                    for s, e in spans
                ],
            )
        ],
    )


def _flat_requests(batches: list[BatchUpdateDocumentRequest]) -> list[Any]:
    """Flatten all Request objects from all batches."""
    reqs = []
    for batch in batches:
        reqs.extend(batch.requests or [])
    return reqs


def _get_create_named_range_reqs(
    batches: list[BatchUpdateDocumentRequest],
) -> list[Any]:
    return [
        r.create_named_range
        for r in _flat_requests(batches)
        if r.create_named_range is not None
    ]


def _get_delete_named_range_reqs(
    batches: list[BatchUpdateDocumentRequest],
) -> list[Any]:
    return [
        r.delete_named_range
        for r in _flat_requests(batches)
        if r.delete_named_range is not None
    ]


# ---------------------------------------------------------------------------
# 1. Basic CRUD
# ---------------------------------------------------------------------------


class TestBasicCrud:
    """Create and delete named ranges."""

    def test_add_single_named_range(self) -> None:
        """Base has no named ranges; desired adds one → createNamedRange."""
        # "Hello\n" occupies indices 1-7 (6 chars); terminal \n at 7.
        base = _doc(
            [_indexed_para("Hello\n", 1), _terminal(7)],
            named_ranges=None,
        )
        desired = _doc(
            [_para("Hello\n"), _terminal()],
            named_ranges={"my_range": _nr("my_range", "nr_1", 1, 6)},
        )

        batches = reconcile_batches(base, desired)
        creates = _get_create_named_range_reqs(batches)

        assert len(creates) == 1, f"Expected 1 createNamedRange, got {len(creates)}"
        assert creates[0].name == "my_range"
        assert creates[0].range is not None
        assert creates[0].range.start_index == 1
        assert creates[0].range.end_index == 6

    def test_delete_single_named_range(self) -> None:
        """Base has one named range; desired has none → deleteNamedRange."""
        base = _doc(
            [_indexed_para("Hello\n", 1), _terminal(7)],
            named_ranges={"my_range": _nr("my_range", "nr_1", 1, 6)},
        )
        desired = _doc(
            [_para("Hello\n"), _terminal()],
            named_ranges=None,
        )

        batches = reconcile_batches(base, desired)
        deletes = _get_delete_named_range_reqs(batches)

        assert len(deletes) == 1, f"Expected 1 deleteNamedRange, got {len(deletes)}"
        assert deletes[0].named_range_id == "nr_1"

    def test_add_multiple_named_ranges(self) -> None:
        """Adding 3 named ranges at once → 3 createNamedRange requests."""
        base = _doc(
            [
                _indexed_para("Alpha\n", 1),
                _indexed_para("Beta\n", 7),
                _indexed_para("Gamma\n", 12),
                _terminal(18),
            ],
            named_ranges=None,
        )
        desired = _doc(
            [
                _para("Alpha\n"),
                _para("Beta\n"),
                _para("Gamma\n"),
                _terminal(),
            ],
            named_ranges={
                "range_a": _nr("range_a", "nr_a", 1, 6),
                "range_b": _nr("range_b", "nr_b", 7, 11),
                "range_c": _nr("range_c", "nr_c", 12, 17),
            },
        )

        batches = reconcile_batches(base, desired)
        creates = _get_create_named_range_reqs(batches)

        assert len(creates) == 3, f"Expected 3 createNamedRange, got {len(creates)}"
        names = {c.name for c in creates}
        assert names == {"range_a", "range_b", "range_c"}

    def test_delete_multiple_named_ranges(self) -> None:
        """Deleting all named ranges → one deleteNamedRange per namedRangeId."""
        base = _doc(
            [_indexed_para("Alpha\n", 1), _indexed_para("Beta\n", 7), _terminal(12)],
            named_ranges={
                "range_a": _nr("range_a", "nr_a", 1, 6),
                "range_b": _nr("range_b", "nr_b", 7, 11),
            },
        )
        desired = _doc(
            [_para("Alpha\n"), _para("Beta\n"), _terminal()],
            named_ranges=None,
        )

        batches = reconcile_batches(base, desired)
        deletes = _get_delete_named_range_reqs(batches)

        assert len(deletes) == 2, f"Expected 2 deleteNamedRange, got {len(deletes)}"
        ids = {d.named_range_id for d in deletes}
        assert ids == {"nr_a", "nr_b"}

    def test_rename_named_range(self) -> None:
        """Same span, different name → delete old + create new."""
        base = _doc(
            [_indexed_para("Hello\n", 1), _terminal(7)],
            named_ranges={"old_name": _nr("old_name", "nr_1", 1, 6)},
        )
        desired = _doc(
            [_para("Hello\n"), _terminal()],
            named_ranges={"new_name": _nr("new_name", "nr_2", 1, 6)},
        )

        batches = reconcile_batches(base, desired)
        creates = _get_create_named_range_reqs(batches)
        deletes = _get_delete_named_range_reqs(batches)

        assert len(creates) == 1, f"Expected 1 createNamedRange, got {len(creates)}"
        assert len(deletes) == 1, f"Expected 1 deleteNamedRange, got {len(deletes)}"
        assert creates[0].name == "new_name"
        assert deletes[0].named_range_id == "nr_1"

    def test_move_named_range(self) -> None:
        """Same name and ID, different span → delete old + create new."""
        base = _doc(
            [_indexed_para("Hello\n", 1), _terminal(7)],
            named_ranges={"my_range": _nr("my_range", "nr_1", 1, 4)},
        )
        desired = _doc(
            [_para("Hello\n"), _terminal()],
            # span moved: was 1-4, now 3-6
            named_ranges={"my_range": _nr("my_range", "nr_1", 3, 6)},
        )

        batches = reconcile_batches(base, desired)
        creates = _get_create_named_range_reqs(batches)
        deletes = _get_delete_named_range_reqs(batches)

        assert len(creates) == 1, f"Expected 1 createNamedRange, got {len(creates)}"
        assert len(deletes) == 1, f"Expected 1 deleteNamedRange, got {len(deletes)}"
        assert creates[0].name == "my_range"
        assert creates[0].range is not None
        assert creates[0].range.start_index == 3
        assert creates[0].range.end_index == 6
        assert deletes[0].named_range_id == "nr_1"


# ---------------------------------------------------------------------------
# 2. Named ranges with content changes
# ---------------------------------------------------------------------------


class TestNamedRangesWithContentChanges:
    """Named range changes alongside body content changes."""

    def test_add_named_range_and_edit_text(self) -> None:
        """Edit paragraph text AND add a named range in the same reconcile."""
        base = _doc(
            [_indexed_para("Old text\n", 1), _terminal(10)],
            named_ranges=None,
        )
        desired = _doc(
            [_para("New text\n"), _terminal()],
            named_ranges={"highlight": _nr("highlight", "nr_1", 1, 8)},
        )

        batches = reconcile_batches(base, desired)
        reqs = _flat_requests(batches)

        # Should produce a text insert/delete AND a createNamedRange
        creates = _get_create_named_range_reqs(batches)
        assert len(creates) == 1, f"Expected 1 createNamedRange, got {len(creates)}"
        assert creates[0].name == "highlight"

        # Some text modification must also be present
        has_text_op = any(
            r.insert_text is not None or r.delete_content_range is not None
            for r in reqs
        )
        assert has_text_op, "Expected at least one text modification request"

    def test_named_range_survives_unrelated_text_edit(self) -> None:
        """Named range unchanged; unrelated text elsewhere changes → no named range ops.

        This is NOT marked xfail: even without named range implementation, the
        reconciler must not emit spurious creates/deletes for unchanged named
        ranges. This test is a correctness guard both before and after
        implementation.
        """
        # "Hello\n" at 1-7, "World\n" at 7-13, terminal at 13.
        # Named range covers "Hello" (1-6). Only "World" changes to "Earth".
        base = _doc(
            [
                _indexed_para("Hello\n", 1),
                _indexed_para("World\n", 7),
                _terminal(13),
            ],
            named_ranges={"greeting": _nr("greeting", "nr_1", 1, 6)},
        )
        desired = _doc(
            [
                _para("Hello\n"),
                _para("Earth\n"),
                _terminal(),
            ],
            named_ranges={"greeting": _nr("greeting", "nr_1", 1, 6)},
        )

        batches = reconcile_batches(base, desired)
        creates = _get_create_named_range_reqs(batches)
        deletes = _get_delete_named_range_reqs(batches)

        assert len(creates) == 0, f"Expected 0 createNamedRange, got {creates}"
        assert len(deletes) == 0, f"Expected 0 deleteNamedRange, got {deletes}"

    def test_named_range_deleted_when_spanning_text_deleted(self) -> None:
        """Named range covers text that is deleted → named range must also be deleted."""
        # "Hello\n" at 1-7 (covered by named range), "World\n" at 7-13, terminal at 13.
        # Desired: only "World\n" remains.
        base = _doc(
            [
                _indexed_para("Hello\n", 1),
                _indexed_para("World\n", 7),
                _terminal(13),
            ],
            named_ranges={"deleted_text": _nr("deleted_text", "nr_1", 1, 6)},
        )
        desired = _doc(
            [
                _para("World\n"),
                _terminal(),
            ],
            named_ranges=None,
        )

        batches = reconcile_batches(base, desired)
        deletes = _get_delete_named_range_reqs(batches)

        assert len(deletes) == 1, f"Expected 1 deleteNamedRange, got {len(deletes)}"
        assert deletes[0].named_range_id == "nr_1"


# ---------------------------------------------------------------------------
# 3. Multi-range named ranges
# ---------------------------------------------------------------------------


class TestMultiRangeNamedRanges:
    """Named ranges spanning multiple discontinuous regions."""

    def test_named_range_with_multiple_ranges(self) -> None:
        """A single namedRangeId spans 2 discontinuous regions."""
        # "Alpha\n" at 1-7, "Beta\n" at 7-12, "Gamma\n" at 12-18, terminal at 18.
        # Named range "bookends" covers "Alpha" (1-6) and "Gamma" (12-17).
        base = _doc(
            [
                _indexed_para("Alpha\n", 1),
                _indexed_para("Beta\n", 7),
                _indexed_para("Gamma\n", 12),
                _terminal(18),
            ],
            named_ranges=None,
        )
        desired = _doc(
            [
                _para("Alpha\n"),
                _para("Beta\n"),
                _para("Gamma\n"),
                _terminal(),
            ],
            named_ranges={
                "bookends": NamedRanges(
                    name="bookends",
                    named_ranges=[
                        NamedRange(
                            name="bookends",
                            named_range_id="nr_1",
                            ranges=[
                                Range(start_index=1, end_index=6, segment_id=""),
                                Range(start_index=12, end_index=17, segment_id=""),
                            ],
                        )
                    ],
                )
            },
        )

        batches = reconcile_batches(base, desired)
        creates = _get_create_named_range_reqs(batches)

        # The API creates one named range per Range object.
        # So 2 Range entries → 2 createNamedRange requests (each with same name).
        assert len(creates) == 2, (
            f"Expected 2 createNamedRange requests, got {len(creates)}"
        )
        names = {c.name for c in creates}
        assert names == {"bookends"}

    def test_add_range_to_existing_named_range(self) -> None:
        """Base has 1-span named range; desired has same name/ID with 2 spans.

        The API has no updateNamedRange. Options:
          a) delete the old single-span NR and create two new NRs with the same name,
          b) keep old NR and add a second createNamedRange with same name.
        Either way, the result should include a createNamedRange for the new span.
        """
        base = _doc(
            [
                _indexed_para("Alpha\n", 1),
                _indexed_para("Beta\n", 7),
                _terminal(12),
            ],
            named_ranges={"label": _nr("label", "nr_1", 1, 6)},
        )
        desired = _doc(
            [
                _para("Alpha\n"),
                _para("Beta\n"),
                _terminal(),
            ],
            named_ranges={
                "label": NamedRanges(
                    name="label",
                    named_ranges=[
                        NamedRange(
                            name="label",
                            named_range_id="nr_1",
                            ranges=[
                                Range(start_index=1, end_index=6, segment_id=""),
                                Range(start_index=7, end_index=11, segment_id=""),
                            ],
                        )
                    ],
                )
            },
        )

        batches = reconcile_batches(base, desired)
        creates = _get_create_named_range_reqs(batches)

        # At minimum, a createNamedRange for the new span (7-11) must appear.
        assert len(creates) >= 1, (
            f"Expected at least 1 createNamedRange, got {len(creates)}"
        )
        ranges = [c.range for c in creates if c.range is not None]
        new_span_created = any(r.start_index == 7 and r.end_index == 11 for r in ranges)
        assert new_span_created, f"New span (7-11) not found in creates: {ranges}"


# ---------------------------------------------------------------------------
# 4. Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge cases for named range handling."""

    def test_named_range_single_character(self) -> None:
        """Named range spanning exactly 1 character."""
        base = _doc(
            [_indexed_para("Hello\n", 1), _terminal(7)],
            named_ranges=None,
        )
        # Range covers only 'H' (index 1 to 2)
        desired = _doc(
            [_para("Hello\n"), _terminal()],
            named_ranges={"first_char": _nr("first_char", "nr_1", 1, 2)},
        )

        batches = reconcile_batches(base, desired)
        creates = _get_create_named_range_reqs(batches)

        assert len(creates) == 1, f"Expected 1 createNamedRange, got {len(creates)}"
        assert creates[0].name == "first_char"
        assert creates[0].range is not None
        assert creates[0].range.start_index == 1
        assert creates[0].range.end_index == 2

    def test_named_range_entire_body(self) -> None:
        """Named range spanning the entire document body content."""
        # Body: "Hello World\n" at 1-13, terminal at 13-14.
        # Span covers all content chars (1-12), excluding terminal \n at 13.
        base = _doc(
            [_indexed_para("Hello World\n", 1), _terminal(13)],
            named_ranges=None,
        )
        desired = _doc(
            [_para("Hello World\n"), _terminal()],
            named_ranges={"everything": _nr("everything", "nr_1", 1, 12)},
        )

        batches = reconcile_batches(base, desired)
        creates = _get_create_named_range_reqs(batches)

        assert len(creates) == 1, f"Expected 1 createNamedRange, got {len(creates)}"
        assert creates[0].name == "everything"
        assert creates[0].range is not None
        assert creates[0].range.start_index == 1
        assert creates[0].range.end_index == 12

    def test_two_named_ranges_overlapping(self) -> None:
        """Two different named range names spanning overlapping text."""
        # "Hello\n" at 1-7; range_a covers 1-4 ("Hel"), range_b covers 3-6 ("lo\n" without \n).
        base = _doc(
            [_indexed_para("Hello\n", 1), _terminal(7)],
            named_ranges=None,
        )
        desired = _doc(
            [_para("Hello\n"), _terminal()],
            named_ranges={
                "range_a": _nr("range_a", "nr_a", 1, 4),
                "range_b": _nr("range_b", "nr_b", 3, 6),
            },
        )

        batches = reconcile_batches(base, desired)
        creates = _get_create_named_range_reqs(batches)

        assert len(creates) == 2, f"Expected 2 createNamedRange, got {len(creates)}"
        names = {c.name for c in creates}
        assert names == {"range_a", "range_b"}

    def test_named_range_at_document_end(self) -> None:
        """Named range just before the terminal paragraph's newline."""
        # "Hello\n" at 1-7, terminal at 7-8.
        # Range covers 'o\n' → indices 5-6 (last char before terminal).
        base = _doc(
            [_indexed_para("Hello\n", 1), _terminal(7)],
            named_ranges=None,
        )
        desired = _doc(
            [_para("Hello\n"), _terminal()],
            named_ranges={"end_range": _nr("end_range", "nr_1", 5, 6)},
        )

        batches = reconcile_batches(base, desired)
        creates = _get_create_named_range_reqs(batches)

        assert len(creates) == 1, f"Expected 1 createNamedRange, got {len(creates)}"
        assert creates[0].name == "end_range"
        assert creates[0].range is not None
        assert creates[0].range.start_index == 5
        assert creates[0].range.end_index == 6

    def test_no_named_ranges_in_either(self) -> None:
        """Both base and desired have no named ranges → no named range requests (sanity check).

        This test is NOT xfail — it should pass even without implementation
        because the reconciler simply emits no named range ops when there is nothing to do.
        """
        base = _doc(
            [_indexed_para("Hello\n", 1), _terminal(7)],
            named_ranges=None,
        )
        desired = _doc(
            [_para("Hello\n"), _terminal()],
            named_ranges=None,
        )

        batches = reconcile_batches(base, desired)
        creates = _get_create_named_range_reqs(batches)
        deletes = _get_delete_named_range_reqs(batches)

        assert len(creates) == 0, f"Expected no createNamedRange, got {creates}"
        assert len(deletes) == 0, f"Expected no deleteNamedRange, got {deletes}"
