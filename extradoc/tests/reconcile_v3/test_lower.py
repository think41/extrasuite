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
from typing import Any

import pytest

from extradoc.reconcile_v3.api import diff, reconcile, reconcile_batches
from extradoc.reconcile_v3.lower import lower_batches, lower_ops
from extradoc.reconcile_v3.model import (
    DeleteHeaderOp,
    DeleteTabOp,
    InsertFootnoteOp,
    InsertNamedStyleOp,
    InsertTabOp,
    UpdateBodyContentOp,
    UpdateNamedStyleOp,
)
from tests.reconcile_v3.helpers import (
    make_document,
    make_footer,
    make_header,
    make_named_style,
    make_para_el,
    make_tab,
    make_terminal_para,
)

# ---------------------------------------------------------------------------
# Helper: build content elements with explicit startIndex/endIndex
# (simulating real Google Docs API responses)
# ---------------------------------------------------------------------------


def make_indexed_para(
    text: str,
    start: int,
    named_style: str = "NORMAL_TEXT",
) -> dict[str, Any]:
    """Return a paragraph content element with Google Docs API index fields."""
    from extradoc.indexer import utf16_len

    end = start + utf16_len(text)
    return {
        "startIndex": start,
        "endIndex": end,
        "paragraph": {
            "elements": [{"textRun": {"content": text}}],
            "paragraphStyle": {"namedStyleType": named_style},
        },
    }


def make_indexed_terminal(start: int) -> dict[str, Any]:
    """Return a terminal paragraph element (bare '\\n') with index fields."""
    return make_indexed_para("\n", start)


def make_indexed_body(*paragraphs: tuple[str, int]) -> list[dict[str, Any]]:
    """Build an indexed body from (text, start_index) tuples.

    The last entry is always the terminal.
    """
    content: list[dict[str, Any]] = []
    for text, start in paragraphs:
        content.append(make_indexed_para(text, start))
    return content


def make_indexed_doc(
    tab_id: str = "t1",
    body_content: list[dict[str, Any]] | None = None,
    headers: dict[str, Any] | None = None,
    footers: dict[str, Any] | None = None,
    footnotes: dict[str, Any] | None = None,
    document_style: dict[str, Any] | None = None,
    named_styles: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a minimal indexed document for lowering tests."""
    if body_content is None:
        body_content = [make_indexed_terminal(1)]
    return make_document(
        tabs=[
            make_tab(
                tab_id,
                body_content=body_content,
                headers=headers,
                footers=footers,
                footnotes=footnotes,
                document_style=document_style,
                named_styles=named_styles,
            )
        ]
    )


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
        delete_reqs = [r for r in requests if "deleteContentRange" in r]
        assert len(delete_reqs) == 1

        dcr = delete_reqs[0]["deleteContentRange"]["range"]
        assert dcr["startIndex"] == 1
        assert dcr["endIndex"] == 7  # "Hello\n" is 6 chars → end=7

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
        insert_reqs = [r for r in requests if "insertText" in r]
        assert len(insert_reqs) >= 1
        # Should insert before the terminal at index 1
        it = insert_reqs[0]["insertText"]
        assert "location" in it
        assert it["location"]["index"] == 1

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

        delete_reqs = [r for r in requests if "deleteContentRange" in r]
        insert_reqs = [r for r in requests if "insertText" in r]

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
        delete_reqs = [r for r in requests if "deleteContentRange" in r]
        assert len(delete_reqs) >= 1
        dcr = delete_reqs[0]["deleteContentRange"]["range"]
        assert dcr.get("tabId") == "myTab"

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
        delete_reqs = [r for r in requests if "deleteContentRange" in r]
        assert len(delete_reqs) == 2

        # Deletes should be in descending startIndex order (para2 before para1)
        starts = [r["deleteContentRange"]["range"]["startIndex"] for r in delete_reqs]
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

        batch0 = batches[0]
        batch1 = batches[1]

        # Batch 0 must contain createHeader
        create_header_reqs = [r for r in batch0 if "createHeader" in r]
        assert len(create_header_reqs) == 1
        ch = create_header_reqs[0]["createHeader"]
        assert ch["type"] == "DEFAULT"

        # Batch 1 must contain updateSectionStyle with deferred ID
        section_style_reqs = [r for r in batch1 if "updateSectionStyle" in r]
        assert len(section_style_reqs) >= 1
        us = section_style_reqs[0]["updateSectionStyle"]
        assert "sectionStyle" in us
        # The ID is a deferred placeholder dict (not yet resolved)
        deferred = us["sectionStyle"].get("defaultHeaderId")
        assert deferred is not None
        assert isinstance(deferred, dict)
        assert deferred.get("placeholder") is True
        assert deferred.get("batch_index") == 0
        assert "response_path" in deferred

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
        batch1 = batches[1]
        for req in batch1:
            if "updateSectionStyle" in req:
                ss = req["updateSectionStyle"]["sectionStyle"]
                for _field, val in ss.items():
                    if isinstance(val, dict) and val.get("placeholder"):
                        # Must reference batch_index=0
                        assert val["batch_index"] == 0
                        # request_index must be valid in batch0
                        assert val["request_index"] < len(batches[0])
                        # response_path must mention headerId
                        assert "headerId" in val["response_path"]

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
        # Only content batch (no structural creation)
        all_reqs = [req for batch in batches for req in batch]
        delete_header_reqs = [r for r in all_reqs if "deleteHeader" in r]
        assert len(delete_header_reqs) == 1
        dh = delete_header_reqs[0]["deleteHeader"]
        assert dh["headerId"] == "h1"

    def test_create_footer_produces_two_batches(self) -> None:
        """Creating a footer: Batch 0 = createFooter, Batch 1 = updateSectionStyle."""
        base = make_indexed_doc(document_style={})
        desired = make_indexed_doc(
            document_style={"defaultFooterId": "f1"},
            footers={"f1": make_footer("f1", "My Footer")},
        )

        batches = reconcile_batches(base, desired)
        assert len(batches) == 2

        batch0 = batches[0]
        batch1 = batches[1]

        create_footer_reqs = [r for r in batch0 if "createFooter" in r]
        assert len(create_footer_reqs) == 1
        cf = create_footer_reqs[0]["createFooter"]
        assert cf["type"] == "DEFAULT"

        section_style_reqs = [r for r in batch1 if "updateSectionStyle" in r]
        assert len(section_style_reqs) >= 1
        us = section_style_reqs[0]["updateSectionStyle"]
        deferred = us["sectionStyle"].get("defaultFooterId")
        assert isinstance(deferred, dict)
        assert deferred.get("placeholder") is True


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
        add_tab_reqs = [r for r in batch0 if "addDocumentTab" in r]
        assert len(add_tab_reqs) == 1
        at = add_tab_reqs[0]["addDocumentTab"]
        assert at["tabProperties"]["title"] == "Tab 2"

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
        delete_tab_reqs = [r for r in all_reqs if "deleteDocumentTab" in r]
        assert len(delete_tab_reqs) == 1
        dt = delete_tab_reqs[0]["deleteDocumentTab"]
        assert dt["tabId"] == "t2"

    def test_insert_and_delete_tab_produce_correct_requests(self) -> None:
        """Tab insert + delete produce the right request types.

        When base has 2 tabs and desired has 3 tabs (one new), there is one
        InsertTabOp and one matched tab pair — the InsertTabOp produces
        addDocumentTab in the structural batch, and the matching pair
        produces no structural ops (only content ops if content differs).
        """
        # Base: t1 (matched), t2 (no match in desired → DeleteTabOp via _match_tabs
        # only if desired has strictly fewer unmatched tabs; here desired has t1 +
        # one extra t3 → t2 pairs positionally with t3 via positional fallback,
        # so no DeleteTabOp/InsertTabOp unless base has *more* or *fewer* tabs).
        #
        # The cleanest way to test insert+delete independently: use explicit IDs.
        # Delete: base has t1+t2, desired has only t1.
        # Insert: base has t1, desired has t1+t2.
        # Here we test the insert case (1 existing + 1 new).

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
        add_reqs = [r for r in batch0 if "addDocumentTab" in r]
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
        delete_reqs = [r for r in all_reqs if "deleteDocumentTab" in r]
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
        style_reqs = [r for r in requests if "updateDocumentStyle" in r]
        assert len(style_reqs) >= 1

        uds = style_reqs[0]["updateDocumentStyle"]
        assert "namedStyles" in uds
        assert "styles" in uds["namedStyles"]
        style_in_req = uds["namedStyles"]["styles"][0]
        assert style_in_req["namedStyleType"] == "HEADING_1"

    def test_insert_named_style_emits_update_document_style(self) -> None:
        """InsertNamedStyleOp emits updateDocumentStyle to add the new style."""
        new_style = make_named_style("HEADING_2", bold=True)

        base = make_indexed_doc(named_styles=[])
        desired = make_indexed_doc(named_styles=[new_style])

        ops = diff(base, desired)
        insert_ops = [op for op in ops if isinstance(op, InsertNamedStyleOp)]
        assert len(insert_ops) == 1

        requests = lower_ops(ops)
        style_reqs = [r for r in requests if "updateDocumentStyle" in r]
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
        insert_reqs = [r for r in result if "insertText" in r]
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
        base: dict[str, Any] = {
            "documentId": "legacyDoc",
            "body": {
                "content": [
                    make_indexed_para("Hello\n", 1),
                    make_indexed_terminal(7),
                ]
            },
            "headers": {},
            "footers": {},
            "footnotes": {},
            "lists": {},
            "namedStyles": {"styles": []},
            "documentStyle": {},
        }
        desired: dict[str, Any] = {
            "documentId": "legacyDoc",
            "body": {
                "content": [
                    make_para_el("Hello changed\n"),
                    make_terminal_para(),
                ]
            },
            "headers": {},
            "footers": {},
            "footnotes": {},
            "lists": {},
            "namedStyles": {"styles": []},
            "documentStyle": {},
        }
        result = reconcile(base, desired)
        assert isinstance(result, list)

    def test_unsupported_ops_raise_not_implemented(self) -> None:
        """Ops that cannot be lowered raise NotImplementedError."""
        from extradoc.reconcile_v3.model import UpdateListOp

        op = UpdateListOp(
            tab_id="t1",
            list_id="list1",
            base_list_def={"listProperties": {}},
            desired_list_def={"listProperties": {"changed": True}},
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
        delete_reqs = [r for r in requests if "deleteContentRange" in r]
        insert_reqs = [r for r in requests if "insertText" in r]

        assert len(delete_reqs) == 2
        assert len(insert_reqs) >= 1
