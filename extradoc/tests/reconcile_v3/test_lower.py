"""Tests for the reconcile_v3 lowering layer.

Structured in five parts:

  Part 1: Simple content ops (no complex index arithmetic)
  Part 2: Structural creation — multi-batch with deferred IDs
  Part 3: Tab creation and deletion
  Part 4: Named style update
  Part 5: End-to-end round-trip

Documents in these tests carry explicit ``startIndex``/``endIndex`` on content
elements to simulate real Google Docs API responses and enable index arithmetic.
"""

from __future__ import annotations

import copy
from typing import Any, ClassVar

import pytest

from extradoc.api_types._generated import (
    BatchUpdateDocumentRequest,
    Color,
    DeferredID,
    Dimension,
    Document,
    DocumentStyle,
    Footnote,
    FootnoteReference,
    InlineObject,
    InlineObjectElement,
    OptionalColor,
    PageBreak,
    Paragraph,
    ParagraphElement,
    ParagraphStyle,
    RgbColor,
    SectionBreak,
    SectionStyle,
    Size,
    StructuralElement,
    Table,
    TableCell,
    TableCellStyle,
    TableRow,
    TextRun,
    TextStyle,
)
from extradoc.reconcile_v3.api import diff, reconcile, reconcile_batches
from extradoc.reconcile_v3.lower import lower_batches, lower_ops
from extradoc.reconcile_v3.model import (
    DeleteFootnoteOp,
    DeleteHeaderOp,
    DeleteInlineObjectOp,
    DeleteTableColumnOp,
    DeleteTableRowOp,
    DeleteTabOp,
    InsertFootnoteOp,
    InsertInlineObjectOp,
    InsertNamedStyleOp,
    InsertTableColumnOp,
    InsertTableRowOp,
    InsertTabOp,
    UpdateBodyContentOp,
    UpdateDocumentStyleOp,
    UpdateFootnoteContentOp,
    UpdateInlineObjectOp,
    UpdateNamedStyleOp,
    UpdateTableCellStyleOp,
    UpdateTableColumnPropertiesOp,
    UpdateTableRowStyleOp,
)
from tests.reconcile_v3.helpers import (
    make_document,
    make_footer,
    make_footnote,
    make_header,
    make_indexed_doc,
    make_indexed_para,
    make_indexed_terminal,
    make_named_style,
    make_para_el,
    make_tab,
    make_table_el,
    make_terminal_para,
)

# ---------------------------------------------------------------------------
# Helper: build content elements with explicit startIndex/endIndex
# (simulating real Google Docs API responses)
# ---------------------------------------------------------------------------


def make_indexed_body(*paragraphs: tuple[str, int]) -> list[StructuralElement]:
    """Build an indexed body from (text, start_index) tuples.

    The last entry is always the terminal.
    """
    content: list[StructuralElement] = []
    for text, start in paragraphs:
        content.append(make_indexed_para(text, start))
    return content


# ===========================================================================
# Part 1: Simple content ops
# ===========================================================================


class TestSimpleContentOps:
    """Content ops with explicit index metadata in the base document."""

    def test_delete_paragraph_produces_delete_content_range(self) -> None:
        """Deleting a paragraph emits deleteContentRange with correct indices."""
        # Body: [para "Hello\n" at 1..6, terminal "\n" at 6..7]
        base = make_indexed_doc(
            body_content=[
                make_indexed_para("Hello\n", 1),
                make_indexed_terminal(7),
            ]
        )
        desired = make_indexed_doc(body_content=[make_indexed_terminal(1)])

        ops = diff(base, desired)
        assert any(isinstance(op, UpdateBodyContentOp) for op in ops)

        requests = lower_ops(ops)
        delete_reqs = [r for r in requests if r.delete_content_range is not None]
        assert len(delete_reqs) == 1

        dcr = delete_reqs[0].delete_content_range
        assert dcr is not None
        assert dcr.range is not None
        assert dcr.range.start_index == 1
        assert dcr.range.end_index == 7  # "Hello\n" is 6 chars → end=7

    def test_insert_paragraph_produces_insert_text(self) -> None:
        """Inserting a paragraph emits insertText at the correct position."""
        base = make_indexed_doc(body_content=[make_indexed_terminal(1)])
        desired = make_indexed_doc(
            body_content=[
                make_para_el("New paragraph\n"),
                make_terminal_para(),
            ]
        )

        ops = diff(base, desired)
        assert any(isinstance(op, UpdateBodyContentOp) for op in ops)

        requests = lower_ops(ops)
        insert_reqs = [r for r in requests if r.insert_text is not None]
        assert len(insert_reqs) >= 1
        # Should insert before the terminal at index 1
        it = insert_reqs[0].insert_text
        assert it is not None
        assert it.location is not None
        assert it.location.index == 1

    def test_no_requests_for_identical_documents(self) -> None:
        """Identical documents produce zero requests."""
        base = make_indexed_doc(
            body_content=[
                make_indexed_para("Hello\n", 1),
                make_indexed_terminal(7),
            ]
        )
        desired = copy.deepcopy(base)

        requests = lower_ops(diff(base, desired))
        assert requests == []

    def test_update_paragraph_text_produces_delete_then_insert(self) -> None:
        """Updating a paragraph's text emits delete+insert."""
        base = make_indexed_doc(
            body_content=[
                make_indexed_para("Old text\n", 1),
                make_indexed_terminal(10),
            ]
        )
        desired = make_indexed_doc(
            body_content=[
                make_para_el("New text\n"),
                make_terminal_para(),
            ]
        )

        ops = diff(base, desired)
        requests = lower_ops(ops)

        delete_reqs = [r for r in requests if r.delete_content_range is not None]
        insert_reqs = [r for r in requests if r.insert_text is not None]

        # Should have a delete for the old text and an insert for new text
        assert len(delete_reqs) >= 1
        assert len(insert_reqs) >= 1

    def test_delete_range_uses_tab_id(self) -> None:
        """deleteContentRange includes tabId from the op."""
        base = make_indexed_doc(
            tab_id="myTab",
            body_content=[
                make_indexed_para("To delete\n", 1),
                make_indexed_terminal(11),
            ],
        )
        desired = make_indexed_doc(
            tab_id="myTab", body_content=[make_indexed_terminal(1)]
        )

        requests = lower_ops(diff(base, desired))
        delete_reqs = [r for r in requests if r.delete_content_range is not None]
        assert len(delete_reqs) >= 1
        dcr = delete_reqs[0].delete_content_range
        assert dcr is not None
        assert dcr.range is not None
        assert dcr.range.tab_id == "myTab"

    def test_delete_in_reverse_order_for_multiple_deletes(self) -> None:
        """Multiple deletes are ordered highest-index-first to avoid index shift."""
        # Body: para1 at 1..8, para2 at 8..15, terminal at 15..16
        base = make_indexed_doc(
            body_content=[
                make_indexed_para("Para 1\n", 1),  # 1..8
                make_indexed_para("Para 2\n", 8),  # 8..15
                make_indexed_terminal(15),  # 15..16
            ]
        )
        desired = make_indexed_doc(body_content=[make_indexed_terminal(1)])

        requests = lower_ops(diff(base, desired))
        delete_reqs = [r for r in requests if r.delete_content_range is not None]
        assert len(delete_reqs) == 2

        # Deletes should be in descending startIndex order (para2 before para1)
        starts = [
            r.delete_content_range.range.start_index  # type: ignore[union-attr]
            for r in delete_reqs
        ]
        assert starts == sorted(starts, reverse=True)

    def test_elements_without_indices_are_skipped_not_crashed(self) -> None:
        """Elements without startIndex/endIndex are silently skipped (no crash)."""
        base = make_document(
            tabs=[
                make_tab(
                    "t1",
                    body_content=[make_para_el("Hello"), make_terminal_para()],
                )
            ]
        )
        desired = make_document(
            tabs=[
                make_tab(
                    "t1",
                    body_content=[make_para_el("Changed"), make_terminal_para()],
                )
            ]
        )
        ops = diff(base, desired)
        # Should not raise
        result = lower_ops(ops)
        assert isinstance(result, list)


# ===========================================================================
# Part 2: Structural creation — multi-batch with deferred IDs
# ===========================================================================


def _get_batch_requests(batch: BatchUpdateDocumentRequest) -> list[Any]:
    """Extract the requests list from a BatchUpdateDocumentRequest."""
    return batch.requests or []


class TestStructuralCreationMultiBatch:
    """Header/footer creation uses deferred IDs across batches."""

    def test_create_header_produces_two_batches(self) -> None:
        """Creating a header: Batch 0 = createHeader, Batch 1 = updateSectionStyle."""
        base = make_indexed_doc(
            document_style={},
        )
        desired = make_indexed_doc(
            document_style={"defaultHeaderId": "h1"},
            headers={"h1": make_header("h1", "My Header")},
        )

        batches = reconcile_batches(base, desired)

        assert len(batches) == 2, f"Expected 2 batches, got {len(batches)}: {batches}"

        batch0 = _get_batch_requests(batches[0])
        batch1 = _get_batch_requests(batches[1])

        # Batch 0 must contain createHeader
        create_header_reqs = [r for r in batch0 if r.create_header is not None]
        assert len(create_header_reqs) == 1
        ch = create_header_reqs[0].create_header
        assert ch is not None
        assert ch.type == "DEFAULT"

        # Batch 1 must contain updateSectionStyle with deferred ID
        section_style_reqs = [r for r in batch1 if r.update_section_style is not None]
        assert len(section_style_reqs) >= 1
        us = section_style_reqs[0].update_section_style
        assert us is not None
        assert us.section_style is not None
        # The ID is a deferred placeholder (DeferredID)
        deferred = us.section_style.default_header_id
        assert deferred is not None
        assert isinstance(deferred, DeferredID)
        assert deferred.batch_index == 0
        assert deferred.response_path is not None

    def test_create_header_deferred_placeholder_is_resolvable(self) -> None:
        """Deferred placeholder references correct batch/request index."""
        base = make_indexed_doc(document_style={})
        desired = make_indexed_doc(
            document_style={"defaultHeaderId": "h1"},
            headers={"h1": make_header("h1", "Header")},
        )

        batches = reconcile_batches(base, desired)
        assert len(batches) == 2

        # Find the deferred ID in batch 1
        batch0 = _get_batch_requests(batches[0])
        batch1 = _get_batch_requests(batches[1])
        for req in batch1:
            if req.update_section_style is not None:
                ss = req.update_section_style.section_style
                if ss is None:
                    continue
                # Check all fields that could be DeferredIDs
                for field_name in [
                    "default_header_id",
                    "default_footer_id",
                    "even_page_header_id",
                    "even_page_footer_id",
                    "first_page_header_id",
                    "first_page_footer_id",
                ]:
                    val = getattr(ss, field_name, None)
                    if isinstance(val, DeferredID):
                        # Must reference batch_index=0
                        assert val.batch_index == 0
                        # request_index must be valid in batch0
                        assert val.request_index < len(batch0)
                        # response_path must mention headerId
                        assert "headerId" in val.response_path

    def test_delete_header_emits_delete_header_request(self) -> None:
        """Deleting a header emits deleteHeader in the content batch."""
        base = make_indexed_doc(
            document_style={"defaultHeaderId": "h1"},
            headers={"h1": make_header("h1", "Old header")},
        )
        desired = make_indexed_doc(document_style={})

        ops = diff(base, desired)
        delete_ops = [op for op in ops if isinstance(op, DeleteHeaderOp)]
        assert len(delete_ops) == 1

        batches = reconcile_batches(base, desired)
        all_reqs = [req for batch in batches for req in _get_batch_requests(batch)]
        delete_header_reqs = [r for r in all_reqs if r.delete_header is not None]
        assert len(delete_header_reqs) == 1
        dh = delete_header_reqs[0].delete_header
        assert dh is not None
        assert dh.header_id == "h1"

    def test_create_footer_produces_two_batches(self) -> None:
        """Creating a footer: Batch 0 = createFooter, Batch 1 = updateSectionStyle."""
        base = make_indexed_doc(document_style={})
        desired = make_indexed_doc(
            document_style={"defaultFooterId": "f1"},
            footers={"f1": make_footer("f1", "My Footer")},
        )

        batches = reconcile_batches(base, desired)
        assert len(batches) == 2

        batch0 = _get_batch_requests(batches[0])
        batch1 = _get_batch_requests(batches[1])

        create_footer_reqs = [r for r in batch0 if r.create_footer is not None]
        assert len(create_footer_reqs) == 1
        cf = create_footer_reqs[0].create_footer
        assert cf is not None
        assert cf.type == "DEFAULT"

        section_style_reqs = [r for r in batch1 if r.update_section_style is not None]
        assert len(section_style_reqs) >= 1
        us = section_style_reqs[0].update_section_style
        assert us is not None
        assert us.section_style is not None
        deferred = us.section_style.default_footer_id
        assert isinstance(deferred, DeferredID)


# ===========================================================================
# Part 3: Tab creation and deletion
# ===========================================================================


class TestTabOps:
    def test_insert_tab_goes_to_batch0(self) -> None:
        """InsertTabOp emits addDocumentTab in the structural creation batch."""
        base = make_document(tabs=[make_tab("t1", "Tab 1", 0)])
        desired = make_document(
            tabs=[
                make_tab("t1", "Tab 1", 0),
                make_tab("t2", "Tab 2", 1),
            ]
        )

        ops = diff(base, desired)
        insert_ops = [op for op in ops if isinstance(op, InsertTabOp)]
        assert len(insert_ops) == 1

        batches = lower_batches(ops)
        # Batch 0 should have addDocumentTab
        assert len(batches) >= 1
        batch0 = batches[0]
        add_tab_reqs = [r for r in batch0 if r.add_document_tab is not None]
        assert len(add_tab_reqs) == 1
        at = add_tab_reqs[0].add_document_tab
        assert at is not None
        assert at.tab_properties is not None
        assert at.tab_properties.title == "Tab 2"

    def test_delete_tab_emits_delete_document_tab(self) -> None:
        """DeleteTabOp emits deleteDocumentTab in the content batch."""
        base = make_document(
            tabs=[
                make_tab("t1", "Tab 1", 0),
                make_tab("t2", "Tab 2", 1),
            ]
        )
        desired = make_document(tabs=[make_tab("t1", "Tab 1", 0)])

        ops = diff(base, desired)
        delete_ops = [op for op in ops if isinstance(op, DeleteTabOp)]
        assert len(delete_ops) == 1

        batches = lower_batches(ops)
        all_reqs = [req for batch in batches for req in batch]
        delete_tab_reqs = [r for r in all_reqs if r.delete_tab is not None]
        assert len(delete_tab_reqs) == 1
        dt = delete_tab_reqs[0].delete_tab
        assert dt is not None
        assert dt.tab_id == "t2"

    def test_insert_tab_with_body_content_emits_content_in_batch1(self) -> None:
        """InsertTabOp with body content emits insertText in batch 1 with deferred tab ID."""
        base = make_document(tabs=[make_tab("t1", "Tab 1", 0)])
        desired = make_document(
            tabs=[
                make_tab("t1", "Tab 1", 0),
                make_tab(
                    "t2",
                    "Tab 2",
                    1,
                    body_content=[make_para_el("Hello\n"), make_terminal_para()],
                ),
            ]
        )

        batches = lower_batches(diff(base, desired))

        # batch 0: addDocumentTab; batch 1: body content with deferred tab ID
        assert len(batches) >= 2, f"Expected at least 2 batches, got {batches}"
        batch0 = batches[0]
        batch1 = batches[1]

        add_tab_reqs = [r for r in batch0 if r.add_document_tab is not None]
        assert len(add_tab_reqs) == 1

        insert_reqs = [r for r in batch1 if r.insert_text is not None]
        assert len(insert_reqs) >= 1, f"No insertText in batch1: {batch1}"

        # The insertText must be at index 1 with a deferred tab ID placeholder
        req = insert_reqs[0].insert_text
        assert req is not None
        loc = req.location
        assert loc is not None
        assert loc.index == 1, f"Expected index=1, got {loc.index!r}"
        tab_id = loc.tab_id
        assert isinstance(tab_id, DeferredID), (
            f"Expected deferred tab ID placeholder, got {tab_id!r}"
        )
        assert tab_id.response_path == "addDocumentTab.tabProperties.tabId"
        assert req.text == "Hello\n"

    def test_insert_tab_deferred_tab_id_resolves(self) -> None:
        """Deferred tab ID in InsertTabOp body content resolves via resolve_deferred_placeholders."""
        from extradoc.reconcile_v3.executor import resolve_deferred_placeholders

        base = make_document(tabs=[make_tab("t1", "Tab 1", 0)])
        desired = make_document(
            tabs=[
                make_tab("t1", "Tab 1", 0),
                make_tab(
                    "t2",
                    "Tab 2",
                    1,
                    body_content=[make_para_el("Hello\n"), make_terminal_para()],
                ),
            ]
        )

        batches = lower_batches(diff(base, desired))
        assert len(batches) >= 2

        # Simulate batch 0 response: addDocumentTab returned tabId "t2-real"
        fake_response = {
            "replies": [{"addDocumentTab": {"tabProperties": {"tabId": "t2-real"}}}]
        }
        # Wrap list[Request] in BatchUpdateDocumentRequest for resolver
        batch1_wrapped = BatchUpdateDocumentRequest(requests=batches[1])
        resolved = resolve_deferred_placeholders([fake_response], batch1_wrapped)

        resolved_reqs = resolved.requests or []
        insert_reqs = [r for r in resolved_reqs if r.insert_text is not None]
        assert len(insert_reqs) >= 1
        tab_id = insert_reqs[0].insert_text.location.tab_id  # type: ignore[union-attr]
        assert tab_id == "t2-real", (
            f"Expected resolved tab ID 't2-real', got {tab_id!r}"
        )

    def test_insert_tab_with_empty_body_emits_no_batch1(self) -> None:
        """InsertTabOp with only a terminal paragraph in body emits no batch 1 content."""
        base = make_document(tabs=[make_tab("t1", "Tab 1", 0)])
        desired = make_document(
            tabs=[
                make_tab("t1", "Tab 1", 0),
                make_tab("t2", "Tab 2", 1),  # default: only terminal paragraph
            ]
        )

        batches = lower_batches(diff(base, desired))

        # Only batch 0 (addDocumentTab); no batch 1 content requests
        assert len(batches) == 1, (
            f"Expected only 1 batch for empty tab body, got {len(batches)}: {batches}"
        )

    def test_insert_and_delete_tab_produce_correct_requests(self) -> None:
        """Tab insert + delete produce the right request types.

        When base has 2 tabs and desired has 3 tabs (one new), there is one
        InsertTabOp and one matched tab pair — the InsertTabOp produces
        addDocumentTab in the structural batch, and the matching pair
        produces no structural ops (only content ops if content differs).
        """
        base_with_one = make_document(tabs=[make_tab("t1", "Tab 1", 0)])
        desired_with_two = make_document(
            tabs=[
                make_tab("t1", "Tab 1", 0),
                make_tab("t2", "Tab 2", 1),
            ]
        )

        batches = lower_batches(diff(base_with_one, desired_with_two))
        assert len(batches) >= 1

        # addDocumentTab must be in the structural batch
        batch0 = batches[0]
        add_reqs = [r for r in batch0 if r.add_document_tab is not None]
        assert len(add_reqs) == 1

        # Delete case
        base_with_two = make_document(
            tabs=[
                make_tab("t1", "Tab 1", 0),
                make_tab("t2", "Tab 2", 1),
            ]
        )
        desired_with_one = make_document(tabs=[make_tab("t1", "Tab 1", 0)])

        batches2 = lower_batches(diff(base_with_two, desired_with_one))
        all_reqs = [req for batch in batches2 for req in batch]
        delete_reqs = [r for r in all_reqs if r.delete_tab is not None]
        assert len(delete_reqs) == 1


# ===========================================================================
# Part 4: Named style update
# ===========================================================================


class TestNamedStyleOps:
    def test_update_named_style_emits_update_document_style(self) -> None:
        """UpdateNamedStyleOp emits updateDocumentStyle with the changed style."""
        base_style = make_named_style("HEADING_1", bold=True)
        desired_style = make_named_style("HEADING_1", bold=False, font_size=18)

        base = make_indexed_doc(named_styles=[base_style])
        desired = make_indexed_doc(named_styles=[desired_style])

        ops = diff(base, desired)
        named_style_ops = [op for op in ops if isinstance(op, UpdateNamedStyleOp)]
        assert len(named_style_ops) == 1

        requests = lower_ops(ops)
        style_reqs = [r for r in requests if r.update_document_style is not None]
        assert len(style_reqs) >= 1

        uds = style_reqs[0].update_document_style
        assert uds is not None
        # Named style updates use the extra "namedStyles" field on the request
        # (not document_style), so check the serialized form.
        uds_dict = uds.model_dump(by_alias=True, exclude_none=True)
        assert "namedStyles" in uds_dict
        styles = uds_dict["namedStyles"]["styles"]
        assert styles[0]["namedStyleType"] == "HEADING_1"

    def test_insert_named_style_emits_update_document_style(self) -> None:
        """InsertNamedStyleOp emits updateDocumentStyle to add the new style."""
        new_style = make_named_style("HEADING_2", bold=True)

        base = make_indexed_doc(named_styles=[])
        desired = make_indexed_doc(named_styles=[new_style])

        ops = diff(base, desired)
        insert_ops = [op for op in ops if isinstance(op, InsertNamedStyleOp)]
        assert len(insert_ops) == 1

        requests = lower_ops(ops)
        style_reqs = [r for r in requests if r.update_document_style is not None]
        assert len(style_reqs) >= 1

    def test_delete_named_style_raises_not_implemented(self) -> None:
        """DeleteNamedStyleOp raises because the API doesn't support removal."""
        from extradoc.reconcile_v3.model import DeleteNamedStyleOp

        op = DeleteNamedStyleOp(
            tab_id="t1",
            named_style_type="HEADING_3",
            base_style=make_named_style("HEADING_3"),
        )
        with pytest.raises(NotImplementedError, match="DeleteNamedStyleOp"):
            lower_ops([op])

    def test_no_named_style_change_no_request(self) -> None:
        """Identical named styles produce no requests."""
        style = make_named_style("NORMAL_TEXT")
        base = make_indexed_doc(named_styles=[style])
        desired = make_indexed_doc(named_styles=[copy.deepcopy(style)])

        requests = lower_ops(diff(base, desired))
        assert requests == []


# ===========================================================================
# Part 5: End-to-end round-trip
# ===========================================================================


class TestEndToEndRoundTrip:
    """End-to-end: build a document, make a change, call reconcile()."""

    def test_identical_documents_return_empty_list(self) -> None:
        """reconcile() returns [] for identical documents."""
        base = make_indexed_doc(
            body_content=[
                make_indexed_para("Hello world\n", 1),
                make_indexed_terminal(13),
            ]
        )
        result = reconcile(base, copy.deepcopy(base))
        assert result == []

    def test_edit_paragraph_text_returns_requests(self) -> None:
        """reconcile() returns a list of requests for a text change."""
        base = make_indexed_doc(
            body_content=[
                make_indexed_para("Old text\n", 1),
                make_indexed_terminal(10),
            ]
        )
        desired = make_indexed_doc(
            body_content=[
                make_para_el("New text\n"),
                make_terminal_para(),
            ]
        )
        result = reconcile(base, desired)
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_add_paragraph_returns_insert_request(self) -> None:
        """reconcile() returns insertText for a new paragraph."""
        base = make_indexed_doc(
            body_content=[
                make_indexed_terminal(1),
            ]
        )
        desired = make_indexed_doc(
            body_content=[
                make_para_el("New paragraph\n"),
                make_terminal_para(),
            ]
        )
        result = reconcile(base, desired)
        assert isinstance(result, list)
        insert_reqs = [r for r in result if r.insert_text is not None]
        assert len(insert_reqs) >= 1

    def test_reconcile_batches_single_batch_for_content_only(self) -> None:
        """A content-only change produces a single batch."""
        base = make_indexed_doc(
            body_content=[
                make_indexed_para("Old\n", 1),
                make_indexed_terminal(5),
            ]
        )
        desired = make_indexed_doc(
            body_content=[
                make_para_el("New\n"),
                make_terminal_para(),
            ]
        )
        batches = reconcile_batches(base, desired)
        assert len(batches) == 1

    def test_reconcile_batches_two_batches_for_header_creation(self) -> None:
        """Creating a header produces two batches (structural + content)."""
        base = make_indexed_doc(document_style={})
        desired = make_indexed_doc(
            document_style={"defaultHeaderId": "new_h1"},
            headers={"new_h1": make_header("new_h1", "Page Header")},
        )
        batches = reconcile_batches(base, desired)
        assert len(batches) == 2

    def test_reconcile_legacy_document_no_tabs(self) -> None:
        """reconcile() works for legacy documents without a 'tabs' field."""

        from tests.reconcile_v3.helpers import make_legacy_document

        base = make_legacy_document(
            document_id="legacyDoc",
            body_content=[
                make_indexed_para("Hello\n", 1),
                make_indexed_terminal(7),
            ],
            named_styles=[],
        )
        desired = make_legacy_document(
            document_id="legacyDoc",
            body_content=[
                make_para_el("Hello changed\n"),
                make_terminal_para(),
            ],
            named_styles=[],
        )
        result = reconcile(base, desired)
        assert isinstance(result, list)

    def test_unsupported_ops_raise_not_implemented(self) -> None:
        """Ops that cannot be lowered raise NotImplementedError."""
        from extradoc.api_types._generated import List as DocList
        from extradoc.api_types._generated import ListProperties
        from extradoc.reconcile_v3.model import UpdateListOp

        op = UpdateListOp(
            tab_id="t1",
            list_id="list1",
            base_list_def=DocList(list_properties=ListProperties()),
            desired_list_def=DocList(list_properties=ListProperties()),
        )
        with pytest.raises(NotImplementedError, match="UpdateListOp"):
            lower_ops([op])

    def test_footnote_ops_raise_not_implemented(self) -> None:
        """Footnote ops raise NotImplementedError (not yet implemented)."""

        op = InsertFootnoteOp(
            tab_id="t1",
            footnote_id="fn1",
            desired_content=[make_para_el("footnote text\n"), make_terminal_para()],
        )
        with pytest.raises(NotImplementedError, match="InsertFootnoteOp"):
            lower_ops([op])

    def test_lower_batches_returns_empty_for_no_ops(self) -> None:
        """lower_batches([]) returns an empty list."""
        assert lower_batches([]) == []


# ===========================================================================
# Part 6: Table cell content lowering
# ===========================================================================
#
# Index arithmetic for a 2x2 table starting at body index T=1:
#
#   T=1  table opener (1 char)
#   Row 0 startIndex = 2 (row opener at 2, 1 char)
#     Cell (0,0) startIndex = 3 (cell opener, 1 char); content starts at 4
#       "A\n" occupies 4..5 (2 chars); cell endIndex = 6
#     Cell (0,1) startIndex = 6 (cell opener, 1 char); content starts at 7
#       "B\n" occupies 7..8 (2 chars); cell endIndex = 9
#   Row 0 endIndex = 9
#   Row 1 startIndex = 9 (row opener at 9, 1 char)
#     Cell (1,0) startIndex = 10 (cell opener, 1 char); content starts at 11
#       "C\n" occupies 11..12; cell endIndex = 13
#     Cell (1,1) startIndex = 13 (cell opener, 1 char); content starts at 14
#       "D\n" occupies 14..15; cell endIndex = 16
#   Table endIndex = 16
#   Body terminal "\n" at 16..17
#
# ===========================================================================


def make_indexed_cell(
    text: str,
    cell_start: int,
) -> TableCell:
    """Build an indexed table cell with a single paragraph and terminal.

    cell_start is the startIndex of the cell element itself (the cell opener).
    Content starts at cell_start + 1.
    """
    from extradoc.indexer import utf16_len

    content_start = cell_start + 1  # skip cell opener
    para_end = content_start + utf16_len(text)
    terminal_start = para_end
    terminal_end = terminal_start + 1  # "\n" is 1 char

    return TableCell(
        start_index=cell_start,
        end_index=terminal_end,
        content=[
            StructuralElement(
                start_index=content_start,
                end_index=para_end,
                paragraph=Paragraph(
                    elements=[ParagraphElement(text_run=TextRun(content=text))],
                    paragraph_style=ParagraphStyle(named_style_type="NORMAL_TEXT"),
                ),
            ),
            StructuralElement(
                start_index=terminal_start,
                end_index=terminal_end,
                paragraph=Paragraph(
                    elements=[ParagraphElement(text_run=TextRun(content="\n"))],
                    paragraph_style=ParagraphStyle(named_style_type="NORMAL_TEXT"),
                ),
            ),
        ],
    )


def make_indexed_table(
    rows: list[list[str]],
    table_start: int,
) -> StructuralElement:
    """Build a table content element with explicit startIndex/endIndex.

    Table structure (1-char openers, no closers):
      table_start = table opener (1 char)
      row[0] starts at table_start + 1 (row opener, 1 char)
      cell[0][0] starts at table_start + 2 (cell opener, 1 char)
      cell[0][0] content starts at table_start + 3
      ...
    """

    pos = table_start + 1  # skip table opener; row[0] starts here
    table_rows = []

    for row_texts in rows:
        row_start = pos
        pos += 1  # row opener (1 char)
        cells = []
        for text in row_texts:
            cell = make_indexed_cell(text, pos)
            pos = cell.end_index  # type: ignore[assignment]
            cells.append(cell)
        row_end = pos
        table_rows.append(
            TableRow(
                start_index=row_start,
                end_index=row_end,
                table_cells=cells,
            )
        )

    table_end = pos
    return StructuralElement(
        start_index=table_start,
        end_index=table_end,
        table=Table(
            rows=len(rows),
            columns=len(rows[0]) if rows else 0,
            table_rows=table_rows,
        ),
    )


class TestTableCellContentLowering:
    """Table cell content lowering: produce correct delete/insert requests."""

    def test_simple_cell_text_change_produces_correct_indices(self) -> None:
        """Changing one cell's text emits delete+insert at the cell's flat indices."""
        base_table = make_indexed_table(
            [["A\n", "B\n"], ["C\n", "D\n"]],
            table_start=1,
        )
        # terminal paragraph after the table
        base = make_indexed_doc(
            body_content=[base_table, make_indexed_terminal(base_table.end_index)]
        )

        # Desired: change cell (0,0) from "A\n" to "Hello\n"
        desired_table = make_indexed_table(
            [["Hello\n", "B\n"], ["C\n", "D\n"]],
            table_start=1,
        )
        desired = make_indexed_doc(
            body_content=[
                desired_table,
                make_indexed_terminal(desired_table.end_index),
            ]
        )

        requests = lower_ops(diff(base, desired))

        # Cell (0,0) content "A" starts at index 4 (cell_start=3, content=4)
        # "A\n" → text region is [4, 5) (we delete "A" and the para text, keeping \n)
        delete_reqs = [r for r in requests if r.delete_content_range is not None]
        insert_reqs = [r for r in requests if r.insert_text is not None]

        # Must have at least one delete and one insert for the changed cell
        assert len(delete_reqs) >= 1, f"Expected delete, got: {requests}"
        assert len(insert_reqs) >= 1, f"Expected insert, got: {requests}"

        # The delete should cover the old text at index 4
        starts = [
            r.delete_content_range.range.start_index  # type: ignore[union-attr]
            for r in delete_reqs
        ]
        assert 4 in starts, f"Expected delete at index 4, got starts={starts}"

    def test_multiple_cells_changed_in_different_rows(self) -> None:
        """Changing cells in different rows produces ops for each changed cell."""
        base_table = make_indexed_table(
            [["A\n", "B\n"], ["C\n", "D\n"]],
            table_start=1,
        )
        base = make_indexed_doc(
            body_content=[base_table, make_indexed_terminal(base_table.end_index)]
        )

        # Change cell (0,0) and cell (1,1)
        desired_table = make_indexed_table(
            [["X\n", "B\n"], ["C\n", "Y\n"]],
            table_start=1,
        )
        desired = make_indexed_doc(
            body_content=[
                desired_table,
                make_indexed_terminal(desired_table.end_index),
            ]
        )

        requests = lower_ops(diff(base, desired))

        # Both cells changed → at least 2 deletes (one per changed cell text)
        delete_reqs = [r for r in requests if r.delete_content_range is not None]
        insert_reqs = [r for r in requests if r.insert_text is not None]
        assert len(delete_reqs) >= 2, f"Expected 2+ deletes, got: {delete_reqs}"
        assert len(insert_reqs) >= 2, f"Expected 2+ inserts, got: {insert_reqs}"

    def test_no_requests_for_table_with_identical_content(self) -> None:
        """A table with identical content produces no requests."""
        base_table = make_indexed_table(
            [["A\n", "B\n"], ["C\n", "D\n"]],
            table_start=1,
        )
        base = make_indexed_doc(
            body_content=[base_table, make_indexed_terminal(base_table.end_index)]
        )
        desired = copy.deepcopy(base)
        requests = lower_ops(diff(base, desired))
        assert requests == []

    def test_cell_text_change_uses_tab_id(self) -> None:
        """Cell content delete/insert requests include the correct tabId."""
        base_table = make_indexed_table([["Old\n", "B\n"]], table_start=1)
        base = make_indexed_doc(
            tab_id="myTab",
            body_content=[base_table, make_indexed_terminal(base_table.end_index)],
        )
        desired_table = make_indexed_table([["New\n", "B\n"]], table_start=1)
        desired = make_indexed_doc(
            tab_id="myTab",
            body_content=[
                desired_table,
                make_indexed_terminal(desired_table.end_index),
            ],
        )
        requests = lower_ops(diff(base, desired))
        delete_reqs = [r for r in requests if r.delete_content_range is not None]
        assert len(delete_reqs) >= 1
        for r in delete_reqs:
            assert r.delete_content_range is not None
            assert r.delete_content_range.range is not None
            assert r.delete_content_range.range.tab_id == "myTab"

    def test_table_with_unchanged_cells_does_not_emit_spurious_ops(self) -> None:
        """Only changed cells produce ops; unchanged cells produce nothing."""
        # Change only cell (0,0); cells (0,1), (1,0), (1,1) unchanged
        base_table = make_indexed_table(
            [["A\n", "B\n"], ["C\n", "D\n"]],
            table_start=1,
        )
        base = make_indexed_doc(
            body_content=[base_table, make_indexed_terminal(base_table.end_index)]
        )
        desired_table = make_indexed_table(
            [["Changed\n", "B\n"], ["C\n", "D\n"]],
            table_start=1,
        )
        desired = make_indexed_doc(
            body_content=[
                desired_table,
                make_indexed_terminal(desired_table.end_index),
            ]
        )
        requests = lower_ops(diff(base, desired))
        insert_reqs = [r for r in requests if r.insert_text is not None]
        # Only one cell changed → exactly 1 insert (for "Changed")
        assert len(insert_reqs) == 1
        it = insert_reqs[0].insert_text
        assert it is not None
        # _lower_paragraph_update strips the trailing \n before inserting
        # (the \n is the paragraph terminator and already exists)
        assert it.text is not None
        assert it.text.rstrip("\n") == "Changed"

    def test_end_to_end_reconcile_with_table_cell_edit(self) -> None:
        """reconcile() works end-to-end for a document with a table cell edit."""
        base_table = make_indexed_table(
            [["Row1Col1\n", "Row1Col2\n"], ["Row2Col1\n", "Row2Col2\n"]],
            table_start=1,
        )
        base = make_indexed_doc(
            body_content=[base_table, make_indexed_terminal(base_table.end_index)]
        )
        desired_table = make_indexed_table(
            [["CHANGED\n", "Row1Col2\n"], ["Row2Col1\n", "Row2Col2\n"]],
            table_start=1,
        )
        desired = make_indexed_doc(
            body_content=[
                desired_table,
                make_indexed_terminal(desired_table.end_index),
            ]
        )

        # Should not raise NotImplementedError
        from extradoc.reconcile_v3.api import reconcile

        result = reconcile(base, desired)
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_reconcile_batches_table_cell_edit_is_single_batch(self) -> None:
        """A table cell content edit goes into the content batch (no structural create)."""
        base_table = make_indexed_table([["A\n"]], table_start=1)
        base = make_indexed_doc(
            body_content=[base_table, make_indexed_terminal(base_table.end_index)]
        )
        desired_table = make_indexed_table([["B\n"]], table_start=1)
        desired = make_indexed_doc(
            body_content=[
                desired_table,
                make_indexed_terminal(desired_table.end_index),
            ]
        )
        batches = reconcile_batches(base, desired)
        # Cell edit only → single content batch
        assert len(batches) == 1

    def test_cell_text_change_correct_delete_range(self) -> None:
        """Delete range starts at the cell paragraph's flat document startIndex."""
        base_table = make_indexed_table(
            [["A\n", "B\n"], ["C\n", "D\n"]],
            table_start=1,
        )
        # Cell (0,0): startIndex=3, content at 4
        cell_00_content_start = 4

        base = make_indexed_doc(
            body_content=[base_table, make_indexed_terminal(base_table.end_index)]
        )
        # Change cell (0,0) only; B, C, D unchanged → 3/4 cells match → sim=0.75 → matched
        desired_table = make_indexed_table(
            [["ZZZZ\n", "B\n"], ["C\n", "D\n"]],
            table_start=1,
        )
        desired = make_indexed_doc(
            body_content=[
                desired_table,
                make_indexed_terminal(desired_table.end_index),
            ]
        )

        requests = lower_ops(diff(base, desired))
        delete_reqs = [r for r in requests if r.delete_content_range is not None]
        assert len(delete_reqs) >= 1, f"Expected delete requests, got: {requests}"

        starts = [
            r.delete_content_range.range.start_index  # type: ignore[union-attr]
            for r in delete_reqs
        ]
        assert cell_00_content_start in starts, (
            f"Expected delete at index {cell_00_content_start}, got starts={starts}"
        )

    def test_delete_and_insert_in_same_body(self) -> None:
        """Mixed delete + insert produces correct ordered requests."""
        # Body: [A at 1..3, B at 3..5, terminal at 5..6]
        # Desired: [C, terminal]  → delete A and B, insert C
        base = make_indexed_doc(
            body_content=[
                make_indexed_para("A\n", 1),
                make_indexed_para("B\n", 3),
                make_indexed_terminal(5),
            ]
        )
        desired = make_indexed_doc(
            body_content=[
                make_para_el("C\n"),
                make_terminal_para(),
            ]
        )
        requests = lower_ops(diff(base, desired))
        delete_reqs = [r for r in requests if r.delete_content_range is not None]
        insert_reqs = [r for r in requests if r.insert_text is not None]

        assert len(delete_reqs) == 2
        assert len(insert_reqs) >= 1


# ===========================================================================
# Part 7: Multi-run paragraph style edits
# ===========================================================================


def make_indexed_para_with_runs(
    runs: list[tuple[str, dict[str, Any]]],
    start: int,
    named_style: str = "NORMAL_TEXT",
) -> StructuralElement:
    """Build an indexed paragraph with multiple text runs.

    Each run is (text, text_style_dict).  The paragraph ends with a \\n run.
    """
    from extradoc.indexer import utf16_len

    elements = []
    for text, style in runs:
        ts = TextStyle(**style) if style else None
        el = ParagraphElement(text_run=TextRun(content=text, text_style=ts))
        elements.append(el)

    full_text = "".join(t for t, _ in runs)
    end = start + utf16_len(full_text)

    return StructuralElement(
        start_index=start,
        end_index=end,
        paragraph=Paragraph(
            elements=elements,
            paragraph_style=ParagraphStyle(named_style_type=named_style),
        ),
    )


def make_para_with_runs(
    runs: list[tuple[str, dict[str, Any]]],
    named_style: str = "NORMAL_TEXT",
) -> StructuralElement:
    """Build a paragraph (no index fields) with multiple text runs."""
    elements = []
    for text, style in runs:
        ts = TextStyle(**style) if style else None
        el = ParagraphElement(text_run=TextRun(content=text, text_style=ts))
        elements.append(el)
    return StructuralElement(
        paragraph=Paragraph(
            elements=elements,
            paragraph_style=ParagraphStyle(named_style_type=named_style),
        )
    )


class TestMultiRunParagraphLowering:
    """Tests for surgical multi-run paragraph style and text edits."""

    # ------------------------------------------------------------------
    # Test 1: single run, text unchanged, style added
    # ------------------------------------------------------------------

    def test_single_run_style_added_no_text_change(self) -> None:
        """Same text, bold style added → only updateTextStyle, no delete/insert."""
        base = make_indexed_doc(
            body_content=[
                make_indexed_para_with_runs([("hello\n", {})], start=1),
                make_indexed_terminal(7),
            ]
        )
        desired = make_indexed_doc(
            body_content=[
                make_para_with_runs([("hello\n", {"bold": True})]),
                make_terminal_para(),
            ]
        )

        requests = lower_ops(diff(base, desired))

        delete_reqs = [r for r in requests if r.delete_content_range is not None]
        insert_reqs = [r for r in requests if r.insert_text is not None]
        style_reqs = [r for r in requests if r.update_text_style is not None]

        assert len(delete_reqs) == 0, "No delete should occur for style-only change"
        assert len(insert_reqs) == 0, "No insert should occur for style-only change"
        assert len(style_reqs) >= 1, "updateTextStyle should be emitted"

        uts = style_reqs[0].update_text_style
        assert uts is not None
        assert uts.text_style is not None
        assert uts.text_style.bold is True

    # ------------------------------------------------------------------
    # Test 2: single run, text changed, no style
    # ------------------------------------------------------------------

    def test_single_run_text_changed_no_style(self) -> None:
        """Text changes, no style → minimal delete+insert covering the change."""
        # "hello world\n" → "hello there\n" — only " world" → " there" changes
        base = make_indexed_doc(
            body_content=[
                make_indexed_para_with_runs([("hello world\n", {})], start=1),
                make_indexed_terminal(13),
            ]
        )
        desired = make_indexed_doc(
            body_content=[
                make_para_with_runs([("hello there\n", {})]),
                make_terminal_para(),
            ]
        )

        requests = lower_ops(diff(base, desired))

        delete_reqs = [r for r in requests if r.delete_content_range is not None]
        insert_reqs = [r for r in requests if r.insert_text is not None]

        # Should produce some delete+insert (the differing suffix)
        assert len(delete_reqs) >= 1
        assert len(insert_reqs) >= 1

        # No op should touch position >= 13 (the terminal \n)
        for r in delete_reqs:
            rng = r.delete_content_range.range  # type: ignore[union-attr]
            assert rng.end_index <= 12, f"Delete must not touch terminal \\n: {rng}"

    # ------------------------------------------------------------------
    # Test 3: multi-run, middle run text changed
    # ------------------------------------------------------------------

    def test_multi_run_middle_run_text_changed(self) -> None:
        """Two runs; second run's text changes → only second run's area is modified."""
        # ["Hello ", "world\n"] → ["Hello ", "there\n"]
        # "Hello world\n" at start=1 → endIndex=13
        base = make_indexed_doc(
            body_content=[
                make_indexed_para_with_runs(
                    [("Hello ", {"bold": True}), ("world\n", {})],
                    start=1,
                ),
                make_indexed_terminal(13),
            ]
        )
        desired = make_indexed_doc(
            body_content=[
                make_para_with_runs([("Hello ", {"bold": True}), ("there\n", {})]),
                make_terminal_para(),
            ]
        )

        requests = lower_ops(diff(base, desired))

        delete_reqs = [r for r in requests if r.delete_content_range is not None]
        insert_reqs = [r for r in requests if r.insert_text is not None]

        # Some ops should be produced
        assert len(delete_reqs) + len(insert_reqs) >= 1

        # No op should start before index 7 (end of "Hello ", 1+6=7)
        for r in delete_reqs:
            rng = r.delete_content_range.range  # type: ignore[union-attr]
            assert rng.start_index >= 7, f"Delete must not touch first run: {rng}"

    # ------------------------------------------------------------------
    # Test 4: multi-run, style changed on one run only
    # ------------------------------------------------------------------

    def test_multi_run_style_changed_on_second_run(self) -> None:
        """Two runs; second run gains italic → only updateTextStyle for second run."""
        # ["Hello ", "world\n"] → ["Hello ", "world\n" (italic)]
        base = make_indexed_doc(
            body_content=[
                make_indexed_para_with_runs(
                    [("Hello ", {"bold": True}), ("world\n", {})],
                    start=1,
                ),
                make_indexed_terminal(13),
            ]
        )
        desired = make_indexed_doc(
            body_content=[
                make_para_with_runs(
                    [("Hello ", {"bold": True}), ("world\n", {"italic": True})]
                ),
                make_terminal_para(),
            ]
        )

        requests = lower_ops(diff(base, desired))

        delete_reqs = [r for r in requests if r.delete_content_range is not None]
        insert_reqs = [r for r in requests if r.insert_text is not None]
        style_reqs = [r for r in requests if r.update_text_style is not None]

        assert len(delete_reqs) == 0, "No delete for style-only change"
        assert len(insert_reqs) == 0, "No insert for style-only change"
        assert len(style_reqs) >= 1

        # Style update should target the second run range [7, 13) in the paragraph
        uts = style_reqs[0].update_text_style
        assert uts is not None
        assert uts.text_style is not None
        assert uts.text_style.italic is True
        assert uts.range is not None
        assert uts.range.start_index >= 7, (
            "Style update must target second run, not first"
        )

    # ------------------------------------------------------------------
    # Test 5: run added at end
    # ------------------------------------------------------------------

    def test_run_added_at_end(self) -> None:
        """New bold run appended → insertText + updateTextStyle."""
        # ["hello\n"] → ["hello", " world\n" (bold)]
        # base: "hello\n" at 1..7; desired adds " world" before \n
        base = make_indexed_doc(
            body_content=[
                make_indexed_para_with_runs([("hello\n", {})], start=1),
                make_indexed_terminal(7),
            ]
        )
        desired = make_indexed_doc(
            body_content=[
                make_para_with_runs([("hello", {}), (" world\n", {"bold": True})]),
                make_terminal_para(),
            ]
        )

        requests = lower_ops(diff(base, desired))

        insert_reqs = [r for r in requests if r.insert_text is not None]

        assert len(insert_reqs) >= 1, "insertText should be emitted for added text"
        # The inserted text should contain " world" (or a superset)
        inserted_texts = [r.insert_text.text for r in insert_reqs]  # type: ignore[union-attr]
        assert any(
            "world" in t
            for t in inserted_texts
            if t  # type: ignore[operator]
        ), f"Expected 'world' in inserts: {inserted_texts}"

    # ------------------------------------------------------------------
    # Test 6: run deleted from end
    # ------------------------------------------------------------------

    def test_run_deleted_from_end(self) -> None:
        """Second run removed → deleteContentRange for that run's span."""
        # ["hello", " world\n"] → ["hello\n"]
        base = make_indexed_doc(
            body_content=[
                make_indexed_para_with_runs(
                    [("hello", {}), (" world\n", {"bold": True})],
                    start=1,
                ),
                make_indexed_terminal(13),
            ]
        )
        desired = make_indexed_doc(
            body_content=[
                make_para_with_runs([("hello\n", {})]),
                make_terminal_para(),
            ]
        )

        requests = lower_ops(diff(base, desired))

        delete_reqs = [r for r in requests if r.delete_content_range is not None]
        assert len(delete_reqs) >= 1

        # Should delete from position 6 (1 + len("hello")) = 6
        starts = [
            r.delete_content_range.range.start_index  # type: ignore[union-attr]
            for r in delete_reqs
        ]
        assert any(s >= 6 for s in starts), (
            f"Expected delete starting at >=6, got: {starts}"
        )

    # ------------------------------------------------------------------
    # Test 7: complete paragraph rewrite
    # ------------------------------------------------------------------

    def test_complete_paragraph_rewrite(self) -> None:
        """Completely different text produces delete+insert covering the full text."""
        base = make_indexed_doc(
            body_content=[
                make_indexed_para_with_runs([("Old text\n", {})], start=1),
                make_indexed_terminal(10),
            ]
        )
        desired = make_indexed_doc(
            body_content=[
                make_para_with_runs([("Completely different\n", {})]),
                make_terminal_para(),
            ]
        )

        requests = lower_ops(diff(base, desired))

        delete_reqs = [r for r in requests if r.delete_content_range is not None]
        insert_reqs = [r for r in requests if r.insert_text is not None]

        assert len(delete_reqs) >= 1
        assert len(insert_reqs) >= 1

        # The inserted text must contain the new content
        inserted_texts = "".join(
            r.insert_text.text
            for r in insert_reqs
            if r.insert_text and r.insert_text.text  # type: ignore[arg-type]
        )
        assert "Completely different" in inserted_texts or any(
            t in inserted_texts for t in ["Completely", "different"]
        )

    # ------------------------------------------------------------------
    # Test 8: paragraph style change only (no text change)
    # ------------------------------------------------------------------

    def test_paragraph_style_change_only(self) -> None:
        """Paragraph alignment changes → only updateParagraphStyle, no delete/insert."""
        base = make_indexed_doc(
            body_content=[
                StructuralElement(
                    start_index=1,
                    end_index=7,
                    paragraph=Paragraph(
                        elements=[
                            ParagraphElement(text_run=TextRun(content="hello\n"))
                        ],
                        paragraph_style=ParagraphStyle(
                            named_style_type="NORMAL_TEXT",
                            alignment="START",
                        ),
                    ),
                ),
                make_indexed_terminal(7),
            ]
        )
        desired = make_indexed_doc(
            body_content=[
                StructuralElement(
                    paragraph=Paragraph(
                        elements=[
                            ParagraphElement(text_run=TextRun(content="hello\n"))
                        ],
                        paragraph_style=ParagraphStyle(
                            named_style_type="NORMAL_TEXT",
                            alignment="CENTER",
                        ),
                    ),
                ),
                make_terminal_para(),
            ]
        )

        requests = lower_ops(diff(base, desired))

        delete_reqs = [r for r in requests if r.delete_content_range is not None]
        insert_reqs = [r for r in requests if r.insert_text is not None]
        para_style_reqs = [r for r in requests if r.update_paragraph_style is not None]

        assert len(delete_reqs) == 0, "No delete for paragraph-style-only change"
        assert len(insert_reqs) == 0, "No insert for paragraph-style-only change"
        assert len(para_style_reqs) >= 1, "updateParagraphStyle should be emitted"

        ups = para_style_reqs[0].update_paragraph_style
        assert ups is not None
        assert ups.paragraph_style is not None
        assert ups.paragraph_style.alignment == "CENTER"

    # ------------------------------------------------------------------
    # Test 9: combined text change + paragraph style change
    # ------------------------------------------------------------------

    def test_combined_text_and_paragraph_style_change(self) -> None:
        """Text changes AND paragraph style changes → both ops produced."""
        base = make_indexed_doc(
            body_content=[
                StructuralElement(
                    start_index=1,
                    end_index=9,
                    paragraph=Paragraph(
                        elements=[
                            ParagraphElement(text_run=TextRun(content="Old text\n"))
                        ],
                        paragraph_style=ParagraphStyle(
                            named_style_type="NORMAL_TEXT",
                            alignment="START",
                        ),
                    ),
                ),
                make_indexed_terminal(9),
            ]
        )
        desired = make_indexed_doc(
            body_content=[
                StructuralElement(
                    paragraph=Paragraph(
                        elements=[
                            ParagraphElement(text_run=TextRun(content="New text\n"))
                        ],
                        paragraph_style=ParagraphStyle(
                            named_style_type="NORMAL_TEXT",
                            alignment="CENTER",
                        ),
                    ),
                ),
                make_terminal_para(),
            ]
        )

        requests = lower_ops(diff(base, desired))

        para_style_reqs = [r for r in requests if r.update_paragraph_style is not None]
        content_reqs = [
            r
            for r in requests
            if r.delete_content_range is not None or r.insert_text is not None
        ]

        assert len(para_style_reqs) >= 1, "updateParagraphStyle should be emitted"
        assert len(content_reqs) >= 1, "Text change ops should be emitted"

    # ------------------------------------------------------------------
    # Test 10: terminal \n is never deleted
    # ------------------------------------------------------------------

    def test_terminal_paragraph_never_deleted(self) -> None:
        """The body-level terminal paragraph is never deleted by any op."""
        # "hello world\n" at 1..13; body terminal "\n" at 13..14
        base = make_indexed_doc(
            body_content=[
                make_indexed_para_with_runs([("hello world\n", {})], start=1),
                make_indexed_terminal(13),
            ]
        )
        desired = make_indexed_doc(
            body_content=[
                make_para_with_runs([("completely different text\n", {})]),
                make_terminal_para(),
            ]
        )

        requests = lower_ops(diff(base, desired))

        # The body terminal paragraph occupies [13, 14).
        # No delete should start at or after 13.
        terminal_start = 13  # body-terminal paragraph startIndex

        for r in requests:
            if r.delete_content_range is not None:
                rng = r.delete_content_range.range
                assert rng is not None
                assert rng.start_index < terminal_start, (
                    f"Delete must not touch the body-terminal paragraph: "
                    f"startIndex={rng.start_index} but terminal starts at {terminal_start}"
                )

    def test_run_level_ops_stay_within_paragraph_text(self) -> None:
        """When a run-level update occurs, ops never exceed the paragraph text range."""
        # "hello world\n" at 1..13: text is [1,12), \\n is at [12,13)
        base = make_indexed_doc(
            body_content=[
                make_indexed_para_with_runs([("hello world\n", {})], start=1),
                make_indexed_terminal(13),
            ]
        )
        desired = make_indexed_doc(
            body_content=[
                # Same prefix "hello", different suffix: " world" → " universe"
                make_para_with_runs([("hello universe\n", {})]),
                make_terminal_para(),
            ]
        )

        requests = lower_ops(diff(base, desired))

        body_terminal_start = 13
        for r in requests:
            if r.delete_content_range is not None:
                rng = r.delete_content_range.range
                assert rng is not None
                assert rng.start_index < body_terminal_start, (
                    f"Delete must not touch body-terminal paragraph: {rng}"
                )

    # ------------------------------------------------------------------
    # Test 11: end-to-end reconcile with multi-run styled paragraph
    # ------------------------------------------------------------------

    def test_end_to_end_styled_paragraph_surgical_ops(self) -> None:
        """End-to-end: reconcile produces surgical ops for styled multi-run paragraph."""
        from extradoc.reconcile_v3.api import reconcile

        # Build a full document with a paragraph that has two styled runs
        base_body = [
            make_indexed_para_with_runs(
                [("Hello ", {"bold": True}), ("world\n", {})],
                start=1,
            ),
            make_indexed_terminal(13),
        ]
        desired_body = [
            make_para_with_runs(
                [("Hello ", {"bold": True}), ("there\n", {"italic": True})]
            ),
            make_terminal_para(),
        ]

        base = make_indexed_doc(body_content=base_body)
        desired = make_indexed_doc(body_content=desired_body)

        all_reqs = reconcile(base, desired)

        # Should produce some requests
        assert isinstance(all_reqs, list)
        assert len(all_reqs) >= 1

        # Specifically, should NOT delete the first run ("Hello ") since it didn't change
        delete_reqs = [r for r in all_reqs if r.delete_content_range is not None]
        for dr in delete_reqs:
            rng = dr.delete_content_range.range  # type: ignore[union-attr]
            # "Hello " is at [1, 7), so any delete starting < 7 and ending > 1
            # would touch the first run. Allow deletes that start at 7+.
            if rng.start_index < 7:
                # Partial overlap is problematic; the delete should not cover
                # the entire "Hello " span
                assert rng.end_index <= 7, (
                    f"Delete {rng} overlaps the unchanged 'Hello ' run at [1,7)"
                )


# ===========================================================================
# Part 7: Footnote lowering
# ===========================================================================


def make_footnote_ref_para(
    text_before: str,
    footnote_id: str,
    fn_ref_start: int,
    para_start: int,
) -> StructuralElement:
    """Build a paragraph element containing text followed by a footnoteReference."""
    from extradoc.indexer import utf16_len

    text_start = para_start
    text_end = text_start + utf16_len(text_before)
    ref_start = fn_ref_start
    ref_end = ref_start + 1  # footnoteReference is exactly 1 character
    newline_start = ref_end
    newline_end = newline_start + 1  # trailing \n
    para_end = newline_end

    return StructuralElement(
        start_index=para_start,
        end_index=para_end,
        paragraph=Paragraph(
            elements=[
                ParagraphElement(
                    start_index=text_start,
                    end_index=text_end,
                    text_run=TextRun(content=text_before),
                ),
                ParagraphElement(
                    start_index=ref_start,
                    end_index=ref_end,
                    footnote_reference=FootnoteReference(footnote_id=footnote_id),
                ),
                ParagraphElement(
                    start_index=newline_start,
                    end_index=newline_end,
                    text_run=TextRun(content="\n"),
                ),
            ],
            paragraph_style=ParagraphStyle(named_style_type="NORMAL_TEXT"),
        ),
    )


class TestFootnoteLowering:
    """Footnote lowering: delete, update content, and insert."""

    # -----------------------------------------------------------------------
    # 1. Delete footnote
    # -----------------------------------------------------------------------

    def test_delete_footnote_emits_delete_content_range(self) -> None:
        """Deleting a footnote emits deleteContentRange at the footnote ref offset."""
        fn_ref_para = make_footnote_ref_para(
            text_before="See",
            footnote_id="fn1",
            fn_ref_start=4,
            para_start=1,
        )
        terminal = make_indexed_terminal(6)

        base = make_indexed_doc(
            body_content=[fn_ref_para, terminal],
            footnotes={"fn1": make_footnote("fn1", "My footnote text\n")},
        )
        # Desired: same body paragraph without the footnoteReference, no footnote entry
        desired = make_indexed_doc(
            body_content=[
                make_indexed_para("See\n", 1),
                make_indexed_terminal(5),
            ],
        )

        ops = diff(base, desired)

        # Should detect a DeleteFootnoteOp with ref_index=4
        delete_fn_ops = [op for op in ops if isinstance(op, DeleteFootnoteOp)]
        assert len(delete_fn_ops) == 1
        assert delete_fn_ops[0].footnote_id == "fn1"
        assert delete_fn_ops[0].ref_index == 4

        batches = reconcile_batches(base, desired)
        all_reqs = [r for batch in batches for r in _get_batch_requests(batch)]
        delete_reqs = [r for r in all_reqs if r.delete_content_range is not None]

        # Must have a delete targeting the footnote ref at [4, 5)
        fn_deletes = [
            r
            for r in delete_reqs
            if r.delete_content_range.range.start_index == 4  # type: ignore[union-attr]
            and r.delete_content_range.range.end_index == 5  # type: ignore[union-attr]
        ]
        assert len(fn_deletes) >= 1, (
            f"Expected deleteContentRange at [4,5) for footnote ref, got: {delete_reqs}"
        )

    def test_delete_footnote_with_unknown_ref_index_raises(self) -> None:
        """DeleteFootnoteOp with ref_index=-1 raises NotImplementedError on lowering."""
        op = DeleteFootnoteOp(tab_id="t1", footnote_id="fn1", ref_index=-1)
        with pytest.raises(NotImplementedError, match="ref_index is unknown"):
            lower_ops([op])

    # -----------------------------------------------------------------------
    # 2. Update footnote content
    # -----------------------------------------------------------------------

    def test_update_footnote_content_emits_story_ops(self) -> None:
        """Updating footnote content emits ops scoped to the footnote's segmentId."""
        # Base footnote with "Old text\n" (with indices)
        base_fn_content = [
            StructuralElement(
                start_index=0,
                end_index=9,
                paragraph=Paragraph(
                    elements=[ParagraphElement(text_run=TextRun(content="Old text\n"))],
                    paragraph_style=ParagraphStyle(named_style_type="NORMAL_TEXT"),
                ),
            )
        ]
        desired_fn_content = [
            make_para_el("New text\n"),
            make_terminal_para(),
        ]

        base = make_indexed_doc(
            footnotes={"fn1": Footnote(footnote_id="fn1", content=base_fn_content)},
        )
        desired = make_indexed_doc(
            footnotes={"fn1": Footnote(footnote_id="fn1", content=desired_fn_content)},
        )

        ops = diff(base, desired)
        update_ops = [op for op in ops if isinstance(op, UpdateFootnoteContentOp)]
        assert len(update_ops) == 1
        assert update_ops[0].footnote_id == "fn1"

        all_reqs = lower_ops(ops)

        # All requests that reference a segmentId should use "fn1"
        for req in all_reqs:
            req_dict = req.model_dump(by_alias=True, exclude_none=True)
            for _key, val in req_dict.items():
                if isinstance(val, dict):
                    rng = val.get("range") or val.get("location", {})
                    seg = rng.get("segmentId") if isinstance(rng, dict) else None
                    if seg is not None:
                        assert seg == "fn1", (
                            f"Expected segmentId='fn1', got {seg!r} in {req}"
                        )

    def test_update_footnote_unchanged_content_produces_no_ops(self) -> None:
        """Unchanged footnote content produces zero ops."""
        content = [make_para_el("Footnote text\n"), make_terminal_para()]
        base = make_indexed_doc(
            footnotes={"fn1": Footnote(footnote_id="fn1", content=content)},
        )
        desired = make_indexed_doc(
            footnotes={"fn1": Footnote(footnote_id="fn1", content=content)},
        )
        assert reconcile(base, desired) == []

    # -----------------------------------------------------------------------
    # 3. Insert footnote
    # -----------------------------------------------------------------------

    def test_insert_footnote_emits_create_footnote_in_batch0(self) -> None:
        """Inserting a new footnote: batch 0 contains createFootnote."""
        desired_fn_ref_para = make_footnote_ref_para(
            text_before="See",
            footnote_id="fn1",
            fn_ref_start=4,
            para_start=1,
        )
        desired = make_indexed_doc(
            body_content=[desired_fn_ref_para, make_indexed_terminal(6)],
            footnotes={"fn1": make_footnote("fn1", "Footnote content\n")},
        )
        # Base has no footnote
        base = make_indexed_doc(
            body_content=[
                make_indexed_para("See\n", 1),
                make_indexed_terminal(5),
            ],
        )

        ops = diff(base, desired)
        insert_ops = [op for op in ops if isinstance(op, InsertFootnoteOp)]
        assert len(insert_ops) == 1
        assert insert_ops[0].footnote_id == "fn1"
        assert insert_ops[0].anchor_index == 4

        batches = reconcile_batches(base, desired)
        assert len(batches) >= 1

        # batch 0 must contain createFootnote
        batch0 = _get_batch_requests(batches[0])
        create_fn_reqs = [r for r in batch0 if r.create_footnote is not None]
        assert len(create_fn_reqs) == 1
        cf = create_fn_reqs[0].create_footnote
        assert cf is not None
        assert cf.location is not None
        assert cf.location.index == 4

    def test_insert_footnote_batch1_has_insert_text_with_deferred_id(self) -> None:
        """Inserting a footnote: batch 1 has insertText at index 1 with deferred segment ID."""
        desired_fn_ref_para = make_footnote_ref_para(
            text_before="Note",
            footnote_id="fn2",
            fn_ref_start=5,
            para_start=1,
        )
        desired = make_indexed_doc(
            body_content=[desired_fn_ref_para, make_indexed_terminal(7)],
            footnotes={"fn2": make_footnote("fn2", "Content\n")},
        )
        base = make_indexed_doc(
            body_content=[
                make_indexed_para("Note\n", 1),
                make_indexed_terminal(6),
            ],
        )

        batches = reconcile_batches(base, desired)

        # batch 0: createFootnote; batch 1 (or later): insertText with deferred segmentId
        assert len(batches) >= 2
        batch1 = _get_batch_requests(batches[1])
        insert_reqs = [r for r in batch1 if r.insert_text is not None]
        assert len(insert_reqs) >= 1

        # The insertText must use location with index=1 and a deferred placeholder segmentId.
        for req in insert_reqs:
            it = req.insert_text
            assert it is not None
            loc = it.location
            if loc is not None:
                seg_id = loc.segment_id
                if not isinstance(seg_id, DeferredID):
                    continue
                assert seg_id.response_path == "createFootnote.footnoteId"
                assert loc.index == 1, (
                    f"Expected insertText at index 1 in new footnote segment, got {loc.index!r}"
                )
                break
        else:
            pytest.fail(
                f"No insertText with deferred segmentId found in batch1: {batch1}"
            )

    def test_insert_footnote_without_anchor_raises(self) -> None:
        """InsertFootnoteOp with anchor_index=-1 raises NotImplementedError."""
        op = InsertFootnoteOp(
            tab_id="t1",
            footnote_id="fn1",
            desired_content=[make_para_el("text\n"), make_terminal_para()],
            anchor_index=-1,
        )
        with pytest.raises(NotImplementedError, match="anchor_index is unknown"):
            lower_ops([op])

    # -----------------------------------------------------------------------
    # 4. Multiple footnotes, one changed
    # -----------------------------------------------------------------------

    def test_multiple_footnotes_only_changed_one_updated(self) -> None:
        """With 3 footnotes, only the changed one produces update ops."""
        content_a = [make_para_el("Footnote A\n"), make_terminal_para()]
        content_b_old = [
            StructuralElement(
                start_index=0,
                end_index=12,
                paragraph=Paragraph(
                    elements=[
                        ParagraphElement(text_run=TextRun(content="Footnote B\n"))
                    ],
                    paragraph_style=ParagraphStyle(named_style_type="NORMAL_TEXT"),
                ),
            )
        ]
        content_b_new = [make_para_el("Footnote B updated\n"), make_terminal_para()]
        content_c = [make_para_el("Footnote C\n"), make_terminal_para()]

        base = make_indexed_doc(
            footnotes={
                "fnA": Footnote(footnote_id="fnA", content=content_a),
                "fnB": Footnote(footnote_id="fnB", content=content_b_old),
                "fnC": Footnote(footnote_id="fnC", content=content_c),
            }
        )
        desired = make_indexed_doc(
            footnotes={
                "fnA": Footnote(footnote_id="fnA", content=content_a),
                "fnB": Footnote(footnote_id="fnB", content=content_b_new),
                "fnC": Footnote(footnote_id="fnC", content=content_c),
            }
        )

        ops = diff(base, desired)
        update_ops = [op for op in ops if isinstance(op, UpdateFootnoteContentOp)]
        assert len(update_ops) == 1
        assert update_ops[0].footnote_id == "fnB"

        all_reqs = lower_ops(ops)
        # Only fnB's content is updated — any segmentId present must be "fnB"
        for req in all_reqs:
            req_dict = req.model_dump(by_alias=True, exclude_none=True)
            for _key, val in req_dict.items():
                if isinstance(val, dict):
                    rng = val.get("range") or val.get("location", {})
                    seg = rng.get("segmentId") if isinstance(rng, dict) else None
                    if seg is not None:
                        assert seg == "fnB", f"Unexpected segmentId {seg!r} in {req}"

    # -----------------------------------------------------------------------
    # 5. End-to-end: reconcile on a document with footnotes
    # -----------------------------------------------------------------------

    def test_end_to_end_update_footnote_content(self) -> None:
        """reconcile() on a document with footnotes works without raising."""
        base_content = [
            StructuralElement(
                start_index=0,
                end_index=14,
                paragraph=Paragraph(
                    elements=[
                        ParagraphElement(text_run=TextRun(content="Original text\n"))
                    ],
                    paragraph_style=ParagraphStyle(named_style_type="NORMAL_TEXT"),
                ),
            )
        ]
        desired_content = [make_para_el("Updated text\n"), make_terminal_para()]

        base = make_indexed_doc(
            footnotes={"fn1": Footnote(footnote_id="fn1", content=base_content)},
        )
        desired = make_indexed_doc(
            footnotes={"fn1": Footnote(footnote_id="fn1", content=desired_content)},
        )

        result = reconcile(base, desired)
        assert isinstance(result, list)

    def test_end_to_end_delete_footnote(self) -> None:
        """reconcile() produces correct delete request for a removed footnote."""
        fn_ref_para = make_footnote_ref_para(
            text_before="See",
            footnote_id="fnDel",
            fn_ref_start=4,
            para_start=1,
        )
        base = make_indexed_doc(
            body_content=[fn_ref_para, make_indexed_terminal(6)],
            footnotes={"fnDel": make_footnote("fnDel", "To delete\n")},
        )
        desired = make_indexed_doc(
            body_content=[make_indexed_para("See\n", 1), make_indexed_terminal(5)],
        )

        result = reconcile(base, desired)
        assert isinstance(result, list)
        assert len(result) >= 1
        # Must contain a deleteContentRange for the footnote reference
        delete_reqs = [r for r in result if r.delete_content_range is not None]
        fn_deletes = [
            r
            for r in delete_reqs
            if r.delete_content_range.range.start_index == 4  # type: ignore[union-attr]
        ]
        assert len(fn_deletes) >= 1, (
            f"Expected delete at index 4 for footnote ref, got: {result}"
        )


# ===========================================================================
# Part 6: Table structural op lowering
# ===========================================================================


class TestTableStructuralLowering:
    """Tests for InsertTableRowOp, DeleteTableRowOp, InsertTableColumnOp, DeleteTableColumnOp."""

    TAB_ID = "t1"
    TABLE_START = 5

    def test_insert_table_row_request_shape(self) -> None:
        """InsertTableRowOp → correct insertTableRow request shape."""
        op = InsertTableRowOp(
            tab_id=self.TAB_ID,
            table_start_index=self.TABLE_START,
            row_index=1,
            insert_below=True,
            column_count=2,
        )
        batches = lower_batches([op])
        assert len(batches) == 1
        reqs = batches[0]
        assert len(reqs) == 1
        req = reqs[0]
        assert req.insert_table_row is not None
        itr = req.insert_table_row
        assert itr.table_cell_location is not None
        loc = itr.table_cell_location
        assert loc.table_start_location is not None
        assert loc.table_start_location.index == self.TABLE_START
        assert loc.table_start_location.tab_id == self.TAB_ID
        assert loc.row_index == 1
        assert loc.column_index == 0
        assert itr.insert_below is True

    def test_delete_table_row_request_shape(self) -> None:
        """DeleteTableRowOp → correct deleteTableRow request shape."""
        op = DeleteTableRowOp(
            tab_id=self.TAB_ID,
            table_start_index=self.TABLE_START,
            row_index=2,
        )
        batches = lower_batches([op])
        assert len(batches) == 1
        reqs = batches[0]
        assert len(reqs) == 1
        req = reqs[0]
        assert req.delete_table_row is not None
        dtr = req.delete_table_row
        assert dtr.table_cell_location is not None
        loc = dtr.table_cell_location
        assert loc.table_start_location is not None
        assert loc.table_start_location.index == self.TABLE_START
        assert loc.table_start_location.tab_id == self.TAB_ID
        assert loc.row_index == 2
        assert loc.column_index == 0

    def test_insert_table_column_request_shape(self) -> None:
        """InsertTableColumnOp → correct insertTableColumn request shape."""
        op = InsertTableColumnOp(
            tab_id=self.TAB_ID,
            table_start_index=self.TABLE_START,
            column_index=1,
            insert_right=True,
        )
        batches = lower_batches([op])
        assert len(batches) == 1
        reqs = batches[0]
        assert len(reqs) == 1
        req = reqs[0]
        assert req.insert_table_column is not None
        itc = req.insert_table_column
        assert itc.table_cell_location is not None
        loc = itc.table_cell_location
        assert loc.table_start_location is not None
        assert loc.table_start_location.index == self.TABLE_START
        assert loc.table_start_location.tab_id == self.TAB_ID
        assert loc.row_index == 0
        assert loc.column_index == 1
        assert itc.insert_right is True

    def test_delete_table_column_request_shape(self) -> None:
        """DeleteTableColumnOp → correct deleteTableColumn request shape."""
        op = DeleteTableColumnOp(
            tab_id=self.TAB_ID,
            table_start_index=self.TABLE_START,
            column_index=0,
        )
        batches = lower_batches([op])
        assert len(batches) == 1
        reqs = batches[0]
        assert len(reqs) == 1
        req = reqs[0]
        assert req.delete_table_column is not None
        dtc = req.delete_table_column
        assert dtc.table_cell_location is not None
        loc = dtc.table_cell_location
        assert loc.table_start_location is not None
        assert loc.table_start_location.index == self.TABLE_START
        assert loc.table_start_location.tab_id == self.TAB_ID
        assert loc.row_index == 0
        assert loc.column_index == 0

    def test_table_ops_go_into_content_batch_not_batch_0(self) -> None:
        """Table structural ops go into batch 1 (content batch), not batch 0."""
        from extradoc.reconcile_v3.model import CreateHeaderOp

        ops: list[Any] = [
            CreateHeaderOp(
                tab_id=self.TAB_ID,
                section_slot="DEFAULT",
                desired_header_id="h1",
                desired_content=[make_para_el("Header"), make_terminal_para()],
            ),
            InsertTableRowOp(
                tab_id=self.TAB_ID,
                table_start_index=self.TABLE_START,
                row_index=0,
                insert_below=False,
                column_count=2,
            ),
        ]
        batches = lower_batches(ops)
        # Batch 0 should have createHeader; batch 1 should have insertTableRow
        assert len(batches) >= 2
        batch0_types = {_get_request_type(r) for r in batches[0]}
        assert "create_header" in batch0_types
        batch1_types = {_get_request_type(r) for r in batches[1]}
        assert "insert_table_row" in batch1_types

    def test_end_to_end_table_gains_row(self) -> None:
        """reconcile(base, desired) on a doc where a table gains a row."""
        table_el = StructuralElement(
            start_index=1,
            end_index=20,
            table=Table(
                table_rows=[
                    TableRow(
                        table_cells=[
                            TableCell(
                                content=[make_para_el("A\n")],
                            )
                        ],
                    )
                ],
                columns=1,
                rows=1,
            ),
        )
        terminal = make_indexed_terminal(21)
        base = make_indexed_doc(body_content=[table_el, terminal])

        # Desired: two rows
        table_el_desired = StructuralElement(
            start_index=1,
            end_index=30,
            table=Table(
                table_rows=[
                    TableRow(
                        table_cells=[
                            TableCell(
                                content=[make_para_el("A\n")],
                            )
                        ],
                    ),
                    TableRow(
                        table_cells=[
                            TableCell(
                                content=[make_para_el("B\n")],
                            )
                        ],
                    ),
                ],
                columns=1,
                rows=2,
            ),
        )
        terminal_desired = make_indexed_terminal(31)
        desired = make_indexed_doc(body_content=[table_el_desired, terminal_desired])

        result = reconcile(base, desired)
        assert isinstance(result, list)
        insert_row_reqs = [r for r in result if r.insert_table_row is not None]
        assert len(insert_row_reqs) >= 1, (
            f"Expected insertTableRow request, got: {result}"
        )


def _get_request_type(req: Any) -> str:
    """Return the field name of the set request type."""
    for field_name in [
        "add_document_tab",
        "create_footer",
        "create_footnote",
        "create_header",
        "create_named_range",
        "create_paragraph_bullets",
        "delete_content_range",
        "delete_footer",
        "delete_header",
        "delete_named_range",
        "delete_paragraph_bullets",
        "delete_positioned_object",
        "delete_tab",
        "delete_table_column",
        "delete_table_row",
        "insert_date",
        "insert_inline_image",
        "insert_page_break",
        "insert_person",
        "insert_section_break",
        "insert_table",
        "insert_table_column",
        "insert_table_row",
        "insert_text",
        "merge_table_cells",
        "pin_table_header_rows",
        "replace_all_text",
        "replace_image",
        "replace_named_range_content",
        "unmerge_table_cells",
        "update_document_style",
        "update_document_tab_properties",
        "update_paragraph_style",
        "update_section_style",
        "update_table_cell_style",
        "update_table_column_properties",
        "update_table_row_style",
        "update_text_style",
    ]:
        if getattr(req, field_name, None) is not None:
            return field_name
    return "unknown"


# ===========================================================================
# Part 6: Table style lowering
# ===========================================================================


class TestTableStyleLowering:
    """Tests for lowering of UpdateTableCellStyleOp, UpdateTableRowStyleOp,
    and UpdateTableColumnPropertiesOp."""

    def test_update_table_cell_style_request_shape(self) -> None:
        """UpdateTableCellStyleOp lowers to a correctly-shaped updateTableCellStyle request."""
        op = UpdateTableCellStyleOp(
            tab_id="t1",
            table_start_index=5,
            row_index=1,
            column_index=2,
            desired_style=TableCellStyle(
                background_color=OptionalColor(color=Color(rgb_color=RgbColor(red=1.0)))
            ),
            fields_mask="backgroundColor",
        )
        batches = lower_batches([op])
        assert len(batches) == 1
        reqs = batches[0]
        assert len(reqs) == 1
        req = reqs[0]
        assert req.update_table_cell_style is not None
        ucs = req.update_table_cell_style
        assert ucs.fields == "backgroundColor"
        # Check via dict for nested structure
        ucs_dict = ucs.model_dump(by_alias=True, exclude_none=True)
        assert ucs_dict["tableCellStyle"] == {
            "backgroundColor": {"color": {"rgbColor": {"red": 1.0}}}
        }
        assert ucs.table_range is not None
        assert ucs.table_range.table_cell_location is not None
        assert ucs.table_range.table_cell_location.row_index == 1
        assert ucs.table_range.table_cell_location.column_index == 2
        assert ucs.table_range.row_span == 1
        assert ucs.table_range.column_span == 1
        assert ucs.table_start_location is not None
        assert ucs.table_start_location.index == 5
        assert ucs.table_start_location.tab_id == "t1"

    def test_update_table_row_style_request_shape(self) -> None:
        """UpdateTableRowStyleOp lowers to a correctly-shaped updateTableRowStyle request."""
        op = UpdateTableRowStyleOp(
            tab_id="t1",
            table_start_index=5,
            row_index=2,
            min_row_height=Dimension(magnitude=30.0, unit="PT"),
        )
        batches = lower_batches([op])
        assert len(batches) == 1
        reqs = batches[0]
        assert len(reqs) == 1
        req = reqs[0]
        assert req.update_table_row_style is not None
        urs = req.update_table_row_style
        assert urs.row_indices == [2]
        assert urs.fields == "minRowHeight"
        assert urs.table_row_style is not None
        assert urs.table_row_style.min_row_height is not None
        assert urs.table_row_style.min_row_height.magnitude == 30.0
        assert urs.table_start_location is not None
        assert urs.table_start_location.index == 5

    def test_update_table_column_properties_request_shape(self) -> None:
        """UpdateTableColumnPropertiesOp lowers to a correctly-shaped request."""
        op = UpdateTableColumnPropertiesOp(
            tab_id="t1",
            table_start_index=5,
            column_index=1,
            width=Dimension(magnitude=150.0, unit="PT"),
            width_type="FIXED_WIDTH",
        )
        batches = lower_batches([op])
        assert len(batches) == 1
        reqs = batches[0]
        assert len(reqs) == 1
        req = reqs[0]
        assert req.update_table_column_properties is not None
        ucp = req.update_table_column_properties
        assert ucp.column_indices == [1]
        assert ucp.table_column_properties is not None
        assert ucp.table_column_properties.width is not None
        assert ucp.table_column_properties.width.magnitude == 150.0
        assert ucp.table_column_properties.width_type == "FIXED_WIDTH"
        assert ucp.table_start_location is not None
        assert ucp.table_start_location.index == 5

    def test_all_table_style_ops_go_into_batch_1(self) -> None:
        """All three table style op types end up in the content batch (batch 1)."""
        ops: list[
            UpdateTableCellStyleOp
            | UpdateTableRowStyleOp
            | UpdateTableColumnPropertiesOp
        ] = [
            UpdateTableCellStyleOp(
                tab_id="",
                table_start_index=1,
                row_index=0,
                column_index=0,
                desired_style=TableCellStyle(content_alignment="TOP"),
                fields_mask="contentAlignment",
            ),
            UpdateTableRowStyleOp(
                tab_id="",
                table_start_index=1,
                row_index=0,
                min_row_height=None,
            ),
            UpdateTableColumnPropertiesOp(
                tab_id="",
                table_start_index=1,
                column_index=0,
                width=None,
                width_type="EVENLY_DISTRIBUTED",
            ),
        ]
        batches = lower_batches(ops)  # type: ignore[arg-type]
        # No structural-create ops → only batch 1 is emitted
        assert len(batches) == 1
        assert len(batches[0]) == 3

    def test_end_to_end_reconcile_table_cell_style(self) -> None:
        """End-to-end reconcile on a table with changed cell style produces no error."""
        bg_red = {"backgroundColor": {"color": {"rgbColor": {"red": 1.0}}}}
        bg_blue = {"backgroundColor": {"color": {"rgbColor": {"blue": 1.0}}}}

        def _make_doc(cell_style: dict[str, Any]) -> Document:
            table_el = StructuralElement(
                start_index=1,
                end_index=10,
                table=Table(
                    table_rows=[
                        TableRow(
                            table_cells=[
                                TableCell(
                                    content=[
                                        make_para_el("A\n"),
                                        make_terminal_para(),
                                    ],
                                    table_cell_style=cell_style,
                                )
                            ],
                        )
                    ],
                    columns=1,
                    rows=1,
                ),
            )
            return make_document(
                tabs=[
                    make_tab("t1", body_content=[table_el, make_indexed_terminal(11)])
                ]
            )

        base = _make_doc(bg_red)
        desired = _make_doc(bg_blue)

        from extradoc.reconcile_v3.api import reconcile

        result = reconcile(base, desired)
        assert isinstance(result, list)
        style_reqs = [r for r in result if r.update_table_cell_style is not None]
        assert len(style_reqs) == 1


# ===========================================================================
# Part 6: DocumentStyle lowering
# ===========================================================================


class TestDocumentStyleLowering:
    """Tests for UpdateDocumentStyleOp → updateDocumentStyle request."""

    def test_lower_op_produces_correct_request(self) -> None:
        """UpdateDocumentStyleOp lowers to a correct updateDocumentStyle request."""
        op = UpdateDocumentStyleOp(
            tab_id="t1",
            desired_style=DocumentStyle(margin_top=Dimension(magnitude=36, unit="PT")),
            fields_mask="marginTop",
        )
        reqs = lower_ops([op])
        assert len(reqs) == 1
        req = reqs[0]
        assert req.update_document_style is not None
        body = req.update_document_style
        body_dict = body.model_dump(by_alias=True, exclude_none=True)
        assert body_dict["documentStyle"] == {
            "marginTop": {"magnitude": 36, "unit": "PT"}
        }
        assert body.fields == "marginTop"
        assert body.tab_id == "t1"

    def test_lower_op_fields_mask_is_correct(self) -> None:
        """fields_mask is passed through verbatim."""
        op = UpdateDocumentStyleOp(
            tab_id="t1",
            desired_style=DocumentStyle(
                margin_top=Dimension(magnitude=72, unit="PT"),
                page_number_start=2,
            ),
            fields_mask="marginTop,pageNumberStart",
        )
        reqs = lower_ops([op])
        assert len(reqs) == 1
        body = reqs[0].update_document_style
        assert body is not None
        assert body.fields == "marginTop,pageNumberStart"

    def test_lower_op_legacy_tab_no_tab_id_in_request(self) -> None:
        """Legacy pseudo-tabs (empty tab_id) omit tabId from the request."""
        op = UpdateDocumentStyleOp(
            tab_id="",
            desired_style=DocumentStyle(page_number_start=3),
            fields_mask="pageNumberStart",
        )
        reqs = lower_ops([op])
        assert len(reqs) == 1
        body = reqs[0].update_document_style
        assert body is not None
        # tab_id should be None or empty for legacy docs
        assert not body.tab_id  # empty string or None

    def test_end_to_end_changed_margins(self) -> None:
        """End-to-end: document with changed margins reconciles without error."""
        base_style: dict[str, Any] = {
            "marginTop": {"magnitude": 72, "unit": "PT"},
            "marginBottom": {"magnitude": 72, "unit": "PT"},
        }
        desired_style: dict[str, Any] = {
            "marginTop": {"magnitude": 36, "unit": "PT"},
            "marginBottom": {"magnitude": 36, "unit": "PT"},
        }
        base = make_document(
            tabs=[
                make_tab(
                    "t1",
                    body_content=[make_indexed_para("Hello\n", 1)],
                    document_style=base_style,
                )
            ]
        )
        desired = make_document(
            tabs=[
                make_tab(
                    "t1",
                    body_content=[make_indexed_para("Hello\n", 1)],
                    document_style=desired_style,
                )
            ]
        )
        result = reconcile(base, desired)
        assert isinstance(result, list)
        style_reqs = [r for r in result if r.update_document_style is not None]
        assert len(style_reqs) == 1
        body = style_reqs[0].update_document_style
        assert body is not None
        body_dict = body.model_dump(by_alias=True, exclude_none=True)
        assert body_dict["documentStyle"]["marginTop"] == {
            "magnitude": 36,
            "unit": "PT",
        }
        assert body_dict["documentStyle"]["marginBottom"] == {
            "magnitude": 36,
            "unit": "PT",
        }
        assert body.fields is not None
        assert set(body.fields.split(",")) == {"marginTop", "marginBottom"}


# ===========================================================================
# Part 6: Inline image insert/delete lowering
# ===========================================================================


class TestInlineImageLowering:
    """Tests for lowering InsertInlineObjectOp and DeleteInlineObjectOp."""

    _content_uri = "https://lh3.googleusercontent.com/img123"
    _object_size: ClassVar[Size] = Size(
        width=Dimension(magnitude=200, unit="PT"),
        height=Dimension(magnitude=150, unit="PT"),
    )

    def test_insert_inline_object_request_shape(self) -> None:
        """InsertInlineObjectOp → insertInlineImage with correct fields."""
        op = InsertInlineObjectOp(
            tab_id="t1",
            inline_object_id="kix.abc",
            content_uri=self._content_uri,
            insert_index=5,
            object_size=self._object_size,
        )
        batches = lower_batches([op])
        # Should appear in batch 1 (content ops)
        assert len(batches) == 1
        reqs = batches[0]
        assert len(reqs) == 1
        req = reqs[0]
        assert req.insert_inline_image is not None
        body = req.insert_inline_image
        assert body.uri == self._content_uri
        assert body.location is not None
        assert body.location.index == 5
        # segment_id holds tab_id for inline image requests
        assert body.location.segment_id == "t1"
        assert body.object_size is not None

    def test_insert_inline_object_without_size(self) -> None:
        """InsertInlineObjectOp without object_size → no objectSize field."""
        op = InsertInlineObjectOp(
            tab_id="t1",
            inline_object_id="kix.abc",
            content_uri=self._content_uri,
            insert_index=3,
            object_size=None,
        )
        batches = lower_batches([op])
        assert len(batches) == 1
        req = batches[0][0]
        assert req.insert_inline_image is not None
        assert req.insert_inline_image.object_size is None

    def test_delete_inline_object_request_shape(self) -> None:
        """DeleteInlineObjectOp → deleteContentRange of 1 character."""
        op = DeleteInlineObjectOp(
            tab_id="t1",
            inline_object_id="kix.old",
            delete_index=7,
        )
        batches = lower_batches([op])
        assert len(batches) == 1
        reqs = batches[0]
        assert len(reqs) == 1
        req = reqs[0]
        assert req.delete_content_range is not None
        rng = req.delete_content_range.range
        assert rng is not None
        assert rng.start_index == 7
        assert rng.end_index == 8  # exactly 1 character
        assert rng.tab_id == "t1"

    def test_insert_and_delete_both_go_to_batch_1(self) -> None:
        """Both insert and delete ops land in the same batch (batch 1)."""
        insert_op = InsertInlineObjectOp(
            tab_id="t1",
            inline_object_id="kix.new",
            content_uri=self._content_uri,
            insert_index=2,
        )
        delete_op = DeleteInlineObjectOp(
            tab_id="t1",
            inline_object_id="kix.old",
            delete_index=10,
        )
        batches = lower_batches([insert_op, delete_op])
        assert len(batches) == 1  # only batch 1, no batch 0
        reqs = batches[0]
        assert len(reqs) == 2
        assert reqs[0].insert_inline_image is not None
        assert reqs[1].delete_content_range is not None

    def test_update_inline_object_raises(self) -> None:
        """UpdateInlineObjectOp raises NotImplementedError (API limitation)."""
        import pytest

        op = UpdateInlineObjectOp(
            tab_id="t1",
            inline_object_id="kix.existing",
            base_obj=InlineObject(),
            desired_obj=InlineObject(),
        )
        with pytest.raises(NotImplementedError, match="batchUpdate"):
            lower_batches([op])

    def test_end_to_end_reconcile_with_image_added(self) -> None:
        """End-to-end: reconcile() on a document where a matched paragraph gains an image."""
        from tests.reconcile_v3.test_diff import _make_inline_object

        obj_id = "kix.e2e"
        content_uri = "https://lh3.googleusercontent.com/e2e"
        obj = _make_inline_object(obj_id, content_uri)

        # Base: paragraph "Hello\n" + terminal
        base = make_document(
            tabs=[
                make_tab(
                    "t1",
                    body_content=[
                        make_indexed_para("Hello\n", 1),
                        make_indexed_terminal(7),
                    ],
                    inline_objects={},
                )
            ]
        )

        # Desired: same paragraph but now with an image element prepended
        desired_para = StructuralElement(
            start_index=1,
            end_index=8,
            paragraph=Paragraph(
                elements=[
                    ParagraphElement(
                        start_index=1,
                        end_index=2,
                        inline_object_element=InlineObjectElement(
                            inline_object_id=obj_id,
                        ),
                    ),
                    ParagraphElement(
                        start_index=2,
                        end_index=8,
                        text_run=TextRun(content="Hello\n", text_style=TextStyle()),
                    ),
                ],
                paragraph_style=ParagraphStyle(named_style_type="NORMAL_TEXT"),
            ),
        )
        desired = make_document(
            tabs=[
                make_tab(
                    "t1",
                    body_content=[desired_para, make_indexed_terminal(8)],
                    inline_objects={obj_id: obj},
                )
            ]
        )

        result = reconcile(base, desired)
        assert isinstance(result, list)
        insert_reqs = [r for r in result if r.insert_inline_image is not None]
        assert len(insert_reqs) == 1
        assert insert_reqs[0].insert_inline_image.uri == content_uri  # type: ignore[union-attr]


# ===========================================================================
# Part 7: Page break and section break insertion
# ===========================================================================


def make_indexed_page_break(start: int) -> StructuralElement:
    """Return a page break paragraph element with index fields."""
    return StructuralElement(
        start_index=start,
        end_index=start + 2,
        paragraph=Paragraph(
            elements=[
                ParagraphElement(page_break=PageBreak()),
                ParagraphElement(text_run=TextRun(content="\n")),
            ],
            paragraph_style=ParagraphStyle(named_style_type="NORMAL_TEXT"),
        ),
    )


def make_indexed_section_break(
    start: int,
    section_style: dict[str, Any] | None = None,
) -> StructuralElement:
    """Return a section break structural element with index fields."""
    ss = SectionStyle(**(section_style or {"section_type": "NEXT_PAGE"}))
    return StructuralElement(
        start_index=start,
        end_index=start + 1,
        section_break=SectionBreak(section_style=ss),
    )


class TestPageBreakSectionBreak:
    """Tests for page break and section break insertion / update lowering."""

    # ------------------------------------------------------------------
    # Page break insertion
    # ------------------------------------------------------------------

    def test_insert_page_break_emits_insert_page_break_request(self) -> None:
        """Desired has a page break paragraph, base doesn't → insertPageBreak."""
        base = make_indexed_doc(body_content=[make_indexed_terminal(1)])
        desired = make_indexed_doc(
            body_content=[
                # Page break paragraph (no index — desired docs may lack indices)
                StructuralElement(
                    paragraph=Paragraph(
                        elements=[
                            ParagraphElement(page_break=PageBreak()),
                            ParagraphElement(text_run=TextRun(content="\n")),
                        ],
                        paragraph_style=ParagraphStyle(named_style_type="NORMAL_TEXT"),
                    ),
                ),
                make_terminal_para(),
            ]
        )

        requests = lower_ops(diff(base, desired))
        pb_reqs = [r for r in requests if r.insert_page_break is not None]
        assert len(pb_reqs) == 1
        assert pb_reqs[0].insert_page_break.location is not None  # type: ignore[union-attr]
        assert pb_reqs[0].insert_page_break.location.index == 1  # type: ignore[union-attr]

    def test_insert_page_break_uses_tab_id(self) -> None:
        """insertPageBreak request carries the correct tabId."""
        base = make_indexed_doc(tab_id="myTab", body_content=[make_indexed_terminal(1)])
        desired = make_indexed_doc(
            tab_id="myTab",
            body_content=[
                StructuralElement(
                    paragraph=Paragraph(
                        elements=[
                            ParagraphElement(page_break=PageBreak()),
                            ParagraphElement(text_run=TextRun(content="\n")),
                        ],
                        paragraph_style=ParagraphStyle(named_style_type="NORMAL_TEXT"),
                    ),
                ),
                make_terminal_para(),
            ],
        )

        requests = lower_ops(diff(base, desired))
        pb_reqs = [r for r in requests if r.insert_page_break is not None]
        assert len(pb_reqs) == 1
        assert pb_reqs[0].insert_page_break.location.tab_id == "myTab"  # type: ignore[union-attr]

    def test_page_break_delete_uses_delete_content_range(self) -> None:
        """Base has a page break, desired doesn't → deleteContentRange."""
        base = make_indexed_doc(
            body_content=[
                make_indexed_page_break(1),  # page break para at 1..3
                make_indexed_terminal(3),
            ]
        )
        desired = make_indexed_doc(body_content=[make_indexed_terminal(1)])

        requests = lower_ops(diff(base, desired))
        delete_reqs = [r for r in requests if r.delete_content_range is not None]
        assert len(delete_reqs) == 1
        dcr = delete_reqs[0].delete_content_range
        assert dcr is not None
        assert dcr.range is not None
        assert dcr.range.start_index == 1
        assert dcr.range.end_index == 3

    # ------------------------------------------------------------------
    # Section break insertion
    # ------------------------------------------------------------------

    def test_insert_section_break_emits_insert_section_break_request(self) -> None:
        """Desired has a section break, base doesn't → insertSectionBreak."""
        base = make_indexed_doc(body_content=[make_indexed_terminal(1)])
        desired = make_indexed_doc(
            body_content=[
                StructuralElement(
                    section_break=SectionBreak(
                        section_style=SectionStyle(section_type="NEXT_PAGE"),
                    ),
                ),
                make_terminal_para(),
            ]
        )

        requests = lower_ops(diff(base, desired))
        sb_reqs = [r for r in requests if r.insert_section_break is not None]
        assert len(sb_reqs) == 1
        req = sb_reqs[0].insert_section_break
        assert req is not None
        assert req.section_type == "NEXT_PAGE"
        assert req.location is not None
        assert req.location.index == 1

    def test_insert_section_break_custom_section_type(self) -> None:
        """sectionType from sectionStyle is preserved in the request."""
        base = make_indexed_doc(body_content=[make_indexed_terminal(1)])
        desired = make_indexed_doc(
            body_content=[
                StructuralElement(
                    section_break=SectionBreak(
                        section_style=SectionStyle(section_type="CONTINUOUS"),
                    ),
                ),
                make_terminal_para(),
            ]
        )

        requests = lower_ops(diff(base, desired))
        sb_reqs = [r for r in requests if r.insert_section_break is not None]
        assert len(sb_reqs) == 1
        assert sb_reqs[0].insert_section_break.section_type == "CONTINUOUS"  # type: ignore[union-attr]

    def test_insert_section_break_missing_section_type_defaults_to_next_page(
        self,
    ) -> None:
        """Missing sectionType defaults to NEXT_PAGE."""
        base = make_indexed_doc(body_content=[make_indexed_terminal(1)])
        desired = make_indexed_doc(
            body_content=[
                StructuralElement(
                    section_break=SectionBreak(
                        section_style=SectionStyle(),
                    ),
                ),
                make_terminal_para(),
            ]
        )

        requests = lower_ops(diff(base, desired))
        sb_reqs = [r for r in requests if r.insert_section_break is not None]
        assert len(sb_reqs) == 1
        assert sb_reqs[0].insert_section_break.section_type == "NEXT_PAGE"  # type: ignore[union-attr]

    def test_insert_section_break_with_extra_style_emits_update_section_style(
        self,
    ) -> None:
        """Section break with custom sectionStyle fields also emits updateSectionStyle."""
        base = make_indexed_doc(body_content=[make_indexed_terminal(1)])
        desired = make_indexed_doc(
            body_content=[
                StructuralElement(
                    section_break=SectionBreak(
                        section_style=SectionStyle(
                            section_type="NEXT_PAGE",
                            column_count=2,
                        ),
                    ),
                ),
                make_terminal_para(),
            ]
        )

        requests = lower_ops(diff(base, desired))
        sb_reqs = [r for r in requests if r.insert_section_break is not None]
        uss_reqs = [r for r in requests if r.update_section_style is not None]
        assert len(sb_reqs) == 1
        assert len(uss_reqs) >= 1
        uss = uss_reqs[-1].update_section_style
        assert uss is not None
        assert uss.section_style is not None
        assert uss.section_style.column_count is not None

    # ------------------------------------------------------------------
    # Section break style update (matched section breaks, style changed)
    # ------------------------------------------------------------------

    def test_matched_section_breaks_with_changed_style_emits_update_section_style(
        self,
    ) -> None:
        """Matched section breaks with a sectionStyle change → updateSectionStyle."""
        base = make_indexed_doc(
            body_content=[
                make_indexed_section_break(
                    1, {"sectionType": "NEXT_PAGE", "columnCount": 1}
                ),
                make_indexed_terminal(2),
            ]
        )
        desired = make_indexed_doc(
            body_content=[
                StructuralElement(
                    section_break=SectionBreak(
                        section_style=SectionStyle(
                            section_type="NEXT_PAGE",
                            column_count=2,
                        ),
                    ),
                ),
                make_terminal_para(),
            ]
        )

        requests = lower_ops(diff(base, desired))
        uss_reqs = [r for r in requests if r.update_section_style is not None]
        assert len(uss_reqs) >= 1
        uss = uss_reqs[0].update_section_style
        assert uss is not None
        assert uss.section_style is not None
        assert uss.section_style.column_count == 2
        assert uss.fields is not None
        assert "columnCount" in uss.fields

    def test_matched_section_breaks_identical_style_produces_no_request(self) -> None:
        """Identical section break styles produce no updateSectionStyle request."""
        base = make_indexed_doc(
            body_content=[
                make_indexed_section_break(1, {"sectionType": "NEXT_PAGE"}),
                make_indexed_terminal(2),
            ]
        )
        desired = make_indexed_doc(
            body_content=[
                StructuralElement(
                    section_break=SectionBreak(
                        section_style=SectionStyle(section_type="NEXT_PAGE"),
                    ),
                ),
                make_indexed_terminal(2),
            ]
        )

        requests = lower_ops(diff(base, desired))
        uss_reqs = [r for r in requests if r.update_section_style is not None]
        # No header/footer created → no deferred updateSectionStyle
        content_uss = [
            r
            for r in uss_reqs
            if r.update_section_style is not None
            and r.update_section_style.range is not None
            and r.update_section_style.range.start_index is not None
            and r.update_section_style.range.start_index > 0
        ]
        assert content_uss == []

    # ------------------------------------------------------------------
    # End-to-end: reconcile() on document gaining a page break
    # ------------------------------------------------------------------

    def test_reconcile_document_gaining_page_break_no_error(self) -> None:
        """End-to-end reconcile on a document that gains a page break."""
        from extradoc.reconcile_v3.api import reconcile

        base = make_indexed_doc(
            body_content=[
                make_indexed_para("First paragraph\n", 1),
                make_indexed_terminal(17),
            ]
        )
        desired = make_indexed_doc(
            body_content=[
                make_para_el("First paragraph\n"),
                StructuralElement(
                    paragraph=Paragraph(
                        elements=[
                            ParagraphElement(page_break=PageBreak()),
                            ParagraphElement(text_run=TextRun(content="\n")),
                        ],
                        paragraph_style=ParagraphStyle(named_style_type="NORMAL_TEXT"),
                    ),
                ),
                make_terminal_para(),
            ]
        )

        result = reconcile(base, desired)
        assert isinstance(result, list)
        pb_reqs = [r for r in result if r.insert_page_break is not None]
        assert len(pb_reqs) == 1


# ===========================================================================
# Part 8: Table cell content insertion (_lower_table_insert)
# ===========================================================================


class TestTableInsertCellContent:
    """Tests for cell content requests emitted by _lower_table_insert."""

    from extradoc.indexer import utf16_len

    def _make_cell(self, text: str) -> TableCell:
        """Cell with one text paragraph + terminal."""
        return TableCell(
            content=[make_para_el(text), make_terminal_para()],
        )

    def _make_table_el(self, cells_by_row: list[list[str]]) -> StructuralElement:
        """Table element where each cell text is provided as a string."""
        return StructuralElement(
            table=Table(
                rows=len(cells_by_row),
                columns=len(cells_by_row[0]) if cells_by_row else 0,
                table_rows=[
                    TableRow(
                        table_cells=[self._make_cell(t) for t in row],
                    )
                    for row in cells_by_row
                ],
            )
        )

    def test_insert_table_emits_insertTable_request(self) -> None:
        """_lower_table_insert always emits insertTable as the first request."""
        from extradoc.reconcile_v3.lower import _lower_table_insert

        el = self._make_table_el([["Hello\n", "World\n"]])
        reqs = _lower_table_insert(el=el, index=5, tab_id="t1", segment_id=None)
        assert reqs[0].insert_table is not None
        it = reqs[0].insert_table
        assert it.rows == 1
        assert it.columns == 2
        assert it.location is not None
        assert it.location.index == 5

    def test_insert_table_1x1_cell_content_index(self) -> None:
        """1x1 table: cell content inserts at index+3 (table+row+cell openers = 3 chars)."""
        from extradoc.reconcile_v3.lower import _lower_table_insert

        el = self._make_table_el([["Hello\n"]])
        reqs = _lower_table_insert(el=el, index=5, tab_id="t1", segment_id=None)

        insert_reqs = [r for r in reqs if r.insert_text is not None]
        assert len(insert_reqs) == 1
        loc = insert_reqs[0].insert_text.location  # type: ignore[union-attr]
        assert loc is not None
        assert loc.index == 8, (
            "1x1 table at 5: table opener(5) + row opener(6) + cell opener(7) "
            f"→ content at 8, got {loc.index}"
        )
        assert insert_reqs[0].insert_text.text == "Hello\n"  # type: ignore[union-attr]

    def test_insert_table_1x2_second_cell_index_accounts_for_first_insertion(
        self,
    ) -> None:
        """1x2 table: second cell content starts after first cell's inserted chars shift it."""
        from extradoc.indexer import utf16_len
        from extradoc.reconcile_v3.lower import _lower_table_insert

        el = self._make_table_el([["Hello\n", "World\n"]])
        reqs = _lower_table_insert(el=el, index=5, tab_id="t1", segment_id=None)

        insert_reqs = [r for r in reqs if r.insert_text is not None]
        assert len(insert_reqs) == 2

        # First cell: table(5) + row(6) + cell(7) → content at 8
        assert insert_reqs[0].insert_text.location.index == 8  # type: ignore[union-attr]
        assert insert_reqs[0].insert_text.text == "Hello\n"  # type: ignore[union-attr]

        first_text_size = utf16_len("Hello\n")  # 6
        expected_second_index = 8 + first_text_size + 2  # 8 + 6 + 2 = 16
        assert (
            insert_reqs[1].insert_text.location.index == expected_second_index  # type: ignore[union-attr]
        ), (
            f"Expected second cell content at {expected_second_index}, "
            f"got {insert_reqs[1].insert_text.location.index}"  # type: ignore[union-attr]
        )
        assert insert_reqs[1].insert_text.text == "World\n"  # type: ignore[union-attr]

    def test_insert_table_2x1_second_row_index(self) -> None:
        """2x1 table: second row cell starts after first row's entire size."""
        from extradoc.reconcile_v3.lower import _lower_table_insert

        el = self._make_table_el([["A\n"], ["B\n"]])
        reqs = _lower_table_insert(el=el, index=1, tab_id="t1", segment_id=None)

        insert_reqs = [r for r in reqs if r.insert_text is not None]
        assert len(insert_reqs) == 2

        # Row 0, Cell 0:
        # table at 1 → row0 at 2 → cell at 3 → content at 4
        assert insert_reqs[0].insert_text.location.index == 4  # type: ignore[union-attr]
        assert insert_reqs[0].insert_text.text == "A\n"  # type: ignore[union-attr]

        assert (
            insert_reqs[1].insert_text.location.index == 9  # type: ignore[union-attr]
        ), f"Expected row-1 cell at 9, got {insert_reqs[1].insert_text.location.index}"  # type: ignore[union-attr]
        assert insert_reqs[1].insert_text.text == "B\n"  # type: ignore[union-attr]

    def test_insert_table_empty_cells_emit_no_insertText(self) -> None:
        """Empty cells (no text content) produce no insertText requests."""
        from extradoc.reconcile_v3.lower import _lower_table_insert

        el = make_table_el([["", ""], ["", ""]])
        reqs = _lower_table_insert(el=el, index=1, tab_id="t1", segment_id=None)

        assert len(reqs) == 1, (
            f"Expected only insertTable for empty cells, got {len(reqs)} requests: {reqs}"
        )

    def _make_cell_no_terminal(self, text: str) -> TableCell:
        """Cell with a single paragraph (no separate terminal)."""
        return TableCell(
            content=[make_para_el(text)],
        )

    def _make_table_no_terminal(
        self, cells_by_row: list[list[str]]
    ) -> StructuralElement:
        """Table whose cells have no separate terminal paragraph."""
        return StructuralElement(
            table=Table(
                rows=len(cells_by_row),
                columns=len(cells_by_row[0]) if cells_by_row else 0,
                table_rows=[
                    TableRow(
                        table_cells=[self._make_cell_no_terminal(t) for t in row],
                    )
                    for row in cells_by_row
                ],
            )
        )

    def test_cell_with_no_terminal_paragraph_still_inserts_content(self) -> None:
        """Cells from markdown serde have one paragraph (no separate terminal) — must still insert."""
        from extradoc.reconcile_v3.lower import _lower_table_insert

        el = self._make_table_no_terminal([["Hello\n"]])
        reqs = _lower_table_insert(el=el, index=5, tab_id="t1", segment_id=None)

        insert_reqs = [r for r in reqs if r.insert_text is not None]
        assert len(insert_reqs) == 1, (
            f"Expected insertText for cell content, got {len(insert_reqs)}: {reqs}"
        )
        assert insert_reqs[0].insert_text.text == "Hello\n"  # type: ignore[union-attr]
        assert insert_reqs[0].insert_text.location.index == 8  # type: ignore[union-attr]

    def test_cell_with_explicit_terminal_paragraph_is_not_double_inserted(self) -> None:
        """Cells from a real API pull have [content, terminal_para] — terminal must not be inserted."""
        from extradoc.reconcile_v3.lower import _lower_table_insert

        # Real API format: cell = [para("Hello\n"), para("\n")]
        el = self._make_table_el([["Hello\n"]])  # _make_table_el adds terminal
        reqs = _lower_table_insert(el=el, index=5, tab_id="t1", segment_id=None)

        insert_reqs = [r for r in reqs if r.insert_text is not None]
        assert len(insert_reqs) == 1, (
            f"Expected exactly one insertText (not double), got: {[r.insert_text.text for r in insert_reqs]}"
        )  # type: ignore[union-attr]
        assert insert_reqs[0].insert_text.text == "Hello\n"  # type: ignore[union-attr]
