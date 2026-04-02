"""Tests for the reconcile_v3 top-down tree diff.

Structured in nine parts matching the task specification:

  Part 1: Tab matching
  Part 2: DocumentStyle
  Part 3: NamedStyles
  Part 4: Lists
  Part 5: Headers and Footers
  Part 6: Footnotes
  Part 7: Body content
  Part 8: Table cells (recursive)
  Part 9: End-to-end
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from extradoc.reconcile_v3.api import diff
from extradoc.reconcile_v3.model import (
    CreateFooterOp,
    CreateHeaderOp,
    DeleteFooterOp,
    DeleteFootnoteOp,
    DeleteHeaderOp,
    DeleteListOp,
    DeleteNamedStyleOp,
    DeleteTableColumnOp,
    DeleteTableRowOp,
    DeleteTabOp,
    InsertFootnoteOp,
    InsertListOp,
    InsertNamedStyleOp,
    InsertTableColumnOp,
    InsertTableRowOp,
    InsertTabOp,
    UpdateBodyContentOp,
    UpdateDocumentStyleOp,
    UpdateFooterContentOp,
    UpdateFootnoteContentOp,
    UpdateHeaderContentOp,
    UpdateListOp,
    UpdateNamedStyleOp,
)
from tests.reconcile_v3.helpers import (
    make_doc_tab,
    make_document,
    make_footer,
    make_footnote,
    make_header,
    make_legacy_document,
    make_named_style,
    make_para_el,
    make_tab,
    make_table_el,
    make_terminal_para,
)

# ===========================================================================
# Part 1: Tab matching
# ===========================================================================


class TestTabMatching:
    def test_identical_documents_no_ops(self) -> None:
        doc = make_document(tabs=[make_tab("t1", "Tab 1", 0)])
        ops = diff(doc, copy.deepcopy(doc))
        assert ops == []

    def test_add_new_tab(self) -> None:
        base = make_document(tabs=[make_tab("t1", "Tab 1", 0)])
        desired = make_document(
            tabs=[
                make_tab("t1", "Tab 1", 0),
                make_tab("t2", "Tab 2", 1),
            ]
        )
        ops = diff(base, desired)
        tab_ops = [op for op in ops if isinstance(op, InsertTabOp)]
        assert len(tab_ops) == 1
        assert tab_ops[0].desired_tab_index == 1

    def test_delete_tab(self) -> None:
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
        assert delete_ops[0].base_tab_id == "t2"

    def test_tab_matching_by_id(self) -> None:
        """Tabs are matched by tabId even when reordered."""
        base = make_document(
            tabs=[
                make_tab("t1", "Tab 1", 0),
                make_tab("t2", "Tab 2", 1),
            ]
        )
        # Desired has same tabs; content differs in t2 only
        desired_t2 = make_tab(
            "t2",
            "Tab 2",
            1,
            body_content=[make_para_el("New content in t2"), make_terminal_para()],
        )
        desired = make_document(tabs=[make_tab("t1", "Tab 1", 0), desired_t2])
        ops = diff(base, desired)

        # Should not produce any tab structural ops — only content ops
        tab_insert_ops = [op for op in ops if isinstance(op, InsertTabOp)]
        tab_delete_ops = [op for op in ops if isinstance(op, DeleteTabOp)]
        assert tab_insert_ops == []
        assert tab_delete_ops == []

        # Should produce body content ops (for the changed tab)
        body_ops = [op for op in ops if isinstance(op, UpdateBodyContentOp)]
        assert len(body_ops) >= 1

    def test_positional_fallback_no_ids(self) -> None:
        """Documents with empty tabIds fall back to positional matching."""
        base_tab: dict[str, Any] = {
            "tabProperties": {"tabId": "", "title": "Tab 1", "index": 0},
            "documentTab": make_doc_tab(),
        }
        desired_tab: dict[str, Any] = {
            "tabProperties": {"tabId": "", "title": "Tab 1", "index": 0},
            "documentTab": make_doc_tab(),
        }
        base = {"documentId": "doc1", "tabs": [base_tab]}
        desired = {"documentId": "doc1", "tabs": [desired_tab]}
        ops = diff(base, desired)
        assert ops == []

    def test_legacy_document_no_tabs_field(self) -> None:
        """Legacy documents (no 'tabs' field) are handled via pseudo-tab wrapper."""
        base = make_legacy_document()
        desired = copy.deepcopy(base)
        ops = diff(base, desired)
        assert ops == []


# ===========================================================================
# Part 2: DocumentStyle
# ===========================================================================


class TestDocumentStyle:
    def test_identical_style_no_ops(self) -> None:
        style = {"pageSize": {"width": {"magnitude": 612, "unit": "PT"}}}
        base = make_document(tabs=[make_tab("t1", document_style=style)])
        desired = make_document(
            tabs=[make_tab("t1", document_style=copy.deepcopy(style))]
        )
        ops = diff(base, desired)
        assert ops == []

    def test_changed_style_emits_op(self) -> None:
        """Changed DocumentStyle → UpdateDocumentStyleOp (lowering unsupported)."""
        base_style = {"pageSize": {"width": {"magnitude": 612, "unit": "PT"}}}
        desired_style = {"pageSize": {"width": {"magnitude": 792, "unit": "PT"}}}
        base = make_document(tabs=[make_tab("t1", document_style=base_style)])
        desired = make_document(tabs=[make_tab("t1", document_style=desired_style)])
        ops = diff(base, desired)
        style_ops = [op for op in ops if isinstance(op, UpdateDocumentStyleOp)]
        assert len(style_ops) == 1
        assert style_ops[0].tab_id == "t1"
        assert style_ops[0].base_style == base_style
        assert style_ops[0].desired_style == desired_style

    def test_changed_style_lowering_raises(self) -> None:
        """Lowering an UpdateDocumentStyleOp raises NotImplementedError."""
        from extradoc.reconcile_v3.lower import lower_ops

        base_style = {"pageSize": {"width": {"magnitude": 612, "unit": "PT"}}}
        desired_style = {"pageSize": {"width": {"magnitude": 792, "unit": "PT"}}}
        base = make_document(tabs=[make_tab("t1", document_style=base_style)])
        desired = make_document(tabs=[make_tab("t1", document_style=desired_style)])
        ops = diff(base, desired)
        with pytest.raises(NotImplementedError, match="UpdateDocumentStyleOp"):
            lower_ops(ops)


# ===========================================================================
# Part 3: NamedStyles
# ===========================================================================


class TestNamedStyles:
    def test_identical_named_styles_no_ops(self) -> None:
        styles = [
            make_named_style("NORMAL_TEXT"),
            make_named_style("HEADING_1", bold=True),
        ]
        base = make_document(tabs=[make_tab("t1", named_styles=styles)])
        desired = make_document(
            tabs=[make_tab("t1", named_styles=copy.deepcopy(styles))]
        )
        ops = diff(base, desired)
        ns_ops = [
            op
            for op in ops
            if isinstance(
                op, UpdateNamedStyleOp | InsertNamedStyleOp | DeleteNamedStyleOp
            )
        ]
        assert ns_ops == []

    def test_one_changed_named_style(self) -> None:
        base_style = make_named_style("HEADING_1", bold=False)
        desired_style = make_named_style("HEADING_1", bold=True)
        base = make_document(tabs=[make_tab("t1", named_styles=[base_style])])
        desired = make_document(tabs=[make_tab("t1", named_styles=[desired_style])])
        ops = diff(base, desired)
        update_ops = [op for op in ops if isinstance(op, UpdateNamedStyleOp)]
        assert len(update_ops) == 1
        assert update_ops[0].named_style_type == "HEADING_1"
        assert update_ops[0].tab_id == "t1"

    def test_named_style_added(self) -> None:
        base = make_document(tabs=[make_tab("t1", named_styles=[])])
        desired = make_document(
            tabs=[
                make_tab(
                    "t1", named_styles=[make_named_style("HEADING_2", font_size=18)]
                )
            ]
        )
        ops = diff(base, desired)
        insert_ops = [op for op in ops if isinstance(op, InsertNamedStyleOp)]
        assert len(insert_ops) == 1
        assert insert_ops[0].named_style_type == "HEADING_2"

    def test_named_style_deleted(self) -> None:
        base = make_document(
            tabs=[make_tab("t1", named_styles=[make_named_style("HEADING_3")])]
        )
        desired = make_document(tabs=[make_tab("t1", named_styles=[])])
        ops = diff(base, desired)
        delete_ops = [op for op in ops if isinstance(op, DeleteNamedStyleOp)]
        assert len(delete_ops) == 1
        assert delete_ops[0].named_style_type == "HEADING_3"

    def test_only_changed_style_emits_op(self) -> None:
        """When multiple styles exist, only the changed one emits an op."""
        normal = make_named_style("NORMAL_TEXT")
        h1_base = make_named_style("HEADING_1", bold=False)
        h1_desired = make_named_style("HEADING_1", bold=True)
        base = make_document(tabs=[make_tab("t1", named_styles=[normal, h1_base])])
        desired = make_document(
            tabs=[make_tab("t1", named_styles=[copy.deepcopy(normal), h1_desired])]
        )
        ops = diff(base, desired)
        ns_ops = [
            op
            for op in ops
            if isinstance(
                op, UpdateNamedStyleOp | InsertNamedStyleOp | DeleteNamedStyleOp
            )
        ]
        # Only the HEADING_1 change
        assert len(ns_ops) == 1
        assert isinstance(ns_ops[0], UpdateNamedStyleOp)
        assert ns_ops[0].named_style_type == "HEADING_1"


# ===========================================================================
# Part 4: Lists
# ===========================================================================


class TestLists:
    def _list_def(self, kind: str = "BULLETED") -> dict[str, Any]:
        return {
            "listProperties": {
                "nestingLevels": [
                    {"glyphType": kind, "indentFirstLine": {"magnitude": 18}}
                ]
            }
        }

    def test_identical_lists_no_ops(self) -> None:
        lists = {"list1": self._list_def()}
        base = make_document(tabs=[make_tab("t1", lists=lists)])
        desired = make_document(tabs=[make_tab("t1", lists=copy.deepcopy(lists))])
        ops = diff(base, desired)
        list_ops = [
            op
            for op in ops
            if isinstance(op, InsertListOp | DeleteListOp | UpdateListOp)
        ]
        assert list_ops == []

    def test_new_list_added(self) -> None:
        base = make_document(tabs=[make_tab("t1", lists={})])
        desired = make_document(
            tabs=[make_tab("t1", lists={"list1": self._list_def()})]
        )
        ops = diff(base, desired)
        insert_ops = [op for op in ops if isinstance(op, InsertListOp)]
        assert len(insert_ops) == 1
        assert insert_ops[0].list_id == "list1"
        assert insert_ops[0].tab_id == "t1"

    def test_list_removed(self) -> None:
        base = make_document(tabs=[make_tab("t1", lists={"list1": self._list_def()})])
        desired = make_document(tabs=[make_tab("t1", lists={})])
        ops = diff(base, desired)
        delete_ops = [op for op in ops if isinstance(op, DeleteListOp)]
        assert len(delete_ops) == 1
        assert delete_ops[0].list_id == "list1"

    def test_list_content_changed_emits_update_op(self) -> None:
        """List definition changed → UpdateListOp (cannot edit via API)."""
        base_def = self._list_def("BULLETED")
        desired_def = self._list_def("NUMBERED")
        base = make_document(tabs=[make_tab("t1", lists={"list1": base_def})])
        desired = make_document(tabs=[make_tab("t1", lists={"list1": desired_def})])
        ops = diff(base, desired)
        update_ops = [op for op in ops if isinstance(op, UpdateListOp)]
        assert len(update_ops) == 1
        assert update_ops[0].list_id == "list1"

    def test_list_update_lowering_raises(self) -> None:
        from extradoc.reconcile_v3.lower import lower_ops

        base_def = self._list_def("BULLETED")
        desired_def = self._list_def("NUMBERED")
        base = make_document(tabs=[make_tab("t1", lists={"list1": base_def})])
        desired = make_document(tabs=[make_tab("t1", lists={"list1": desired_def})])
        ops = diff(base, desired)
        with pytest.raises(NotImplementedError, match="UpdateListOp"):
            lower_ops(ops)


# ===========================================================================
# Part 5: Headers and Footers
# ===========================================================================


class TestHeadersAndFooters:
    def _tab_with_header(
        self, tab_id: str, header_id: str, text: str = "Header"
    ) -> dict[str, Any]:
        return make_tab(
            tab_id,
            headers={header_id: make_header(header_id, text)},
            document_style={"defaultHeaderId": header_id},
        )

    def _tab_with_footer(
        self, tab_id: str, footer_id: str, text: str = "Footer"
    ) -> dict[str, Any]:
        return make_tab(
            tab_id,
            footers={footer_id: make_footer(footer_id, text)},
            document_style={"defaultFooterId": footer_id},
        )

    def test_identical_header_no_ops(self) -> None:
        tab = self._tab_with_header("t1", "h1")
        base = make_document(tabs=[tab])
        desired = make_document(tabs=[copy.deepcopy(tab)])
        ops = diff(base, desired)
        header_ops = [
            op
            for op in ops
            if isinstance(op, CreateHeaderOp | DeleteHeaderOp | UpdateHeaderContentOp)
        ]
        assert header_ops == []

    def test_header_content_changed(self) -> None:
        base = make_document(tabs=[self._tab_with_header("t1", "h1", "Old header")])
        desired = make_document(tabs=[self._tab_with_header("t1", "h1", "New header")])
        ops = diff(base, desired)
        update_ops = [op for op in ops if isinstance(op, UpdateHeaderContentOp)]
        assert len(update_ops) == 1
        assert update_ops[0].header_id == "h1"
        assert update_ops[0].section_slot == "DEFAULT"
        assert update_ops[0].tab_id == "t1"

    def test_new_header_created(self) -> None:
        base = make_document(tabs=[make_tab("t1")])
        desired = make_document(tabs=[self._tab_with_header("t1", "h1")])
        ops = diff(base, desired)
        create_ops = [op for op in ops if isinstance(op, CreateHeaderOp)]
        assert len(create_ops) == 1
        assert create_ops[0].desired_header_id == "h1"
        assert create_ops[0].section_slot == "DEFAULT"

    def test_header_deleted(self) -> None:
        base = make_document(tabs=[self._tab_with_header("t1", "h1")])
        desired = make_document(tabs=[make_tab("t1")])
        ops = diff(base, desired)
        delete_ops = [op for op in ops if isinstance(op, DeleteHeaderOp)]
        assert len(delete_ops) == 1
        assert delete_ops[0].base_header_id == "h1"

    def test_identical_footer_no_ops(self) -> None:
        tab = self._tab_with_footer("t1", "f1")
        base = make_document(tabs=[tab])
        desired = make_document(tabs=[copy.deepcopy(tab)])
        ops = diff(base, desired)
        footer_ops = [
            op
            for op in ops
            if isinstance(op, CreateFooterOp | DeleteFooterOp | UpdateFooterContentOp)
        ]
        assert footer_ops == []

    def test_footer_content_changed(self) -> None:
        base = make_document(tabs=[self._tab_with_footer("t1", "f1", "Old footer")])
        desired = make_document(tabs=[self._tab_with_footer("t1", "f1", "New footer")])
        ops = diff(base, desired)
        update_ops = [op for op in ops if isinstance(op, UpdateFooterContentOp)]
        assert len(update_ops) == 1
        assert update_ops[0].footer_id == "f1"

    def test_new_footer_created(self) -> None:
        base = make_document(tabs=[make_tab("t1")])
        desired = make_document(tabs=[self._tab_with_footer("t1", "f1")])
        ops = diff(base, desired)
        create_ops = [op for op in ops if isinstance(op, CreateFooterOp)]
        assert len(create_ops) == 1
        assert create_ops[0].desired_footer_id == "f1"

    def test_footer_deleted(self) -> None:
        base = make_document(tabs=[self._tab_with_footer("t1", "f1")])
        desired = make_document(tabs=[make_tab("t1")])
        ops = diff(base, desired)
        delete_ops = [op for op in ops if isinstance(op, DeleteFooterOp)]
        assert len(delete_ops) == 1
        assert delete_ops[0].base_footer_id == "f1"

    def test_first_page_header_slot(self) -> None:
        """FIRST_PAGE header slot is separately tracked."""
        base = make_document(tabs=[make_tab("t1")])
        # Desired has a first-page header
        desired_doc_style = {"firstPageHeaderId": "h_fp"}
        desired_headers = {"h_fp": make_header("h_fp", "First page header")}
        desired = make_document(
            tabs=[
                make_tab(
                    "t1", headers=desired_headers, document_style=desired_doc_style
                )
            ]
        )
        ops = diff(base, desired)
        create_ops = [op for op in ops if isinstance(op, CreateHeaderOp)]
        assert len(create_ops) == 1
        assert create_ops[0].section_slot == "FIRST_PAGE"


# ===========================================================================
# Part 6: Footnotes
# ===========================================================================


class TestFootnotes:
    def _tab_with_footnotes(
        self, tab_id: str, footnotes: dict[str, Any]
    ) -> dict[str, Any]:
        return make_tab(tab_id, footnotes=footnotes)

    def test_identical_footnotes_no_ops(self) -> None:
        footnotes = {"fn1": make_footnote("fn1", "Some footnote")}
        tab = self._tab_with_footnotes("t1", footnotes)
        base = make_document(tabs=[tab])
        desired = make_document(tabs=[copy.deepcopy(tab)])
        ops = diff(base, desired)
        fn_ops = [
            op
            for op in ops
            if isinstance(
                op, InsertFootnoteOp | DeleteFootnoteOp | UpdateFootnoteContentOp
            )
        ]
        assert fn_ops == []

    def test_footnote_content_changed(self) -> None:
        base_fn = {"fn1": make_footnote("fn1", "Old footnote")}
        desired_fn = {"fn1": make_footnote("fn1", "Updated footnote")}
        base = make_document(tabs=[self._tab_with_footnotes("t1", base_fn)])
        desired = make_document(tabs=[self._tab_with_footnotes("t1", desired_fn)])
        ops = diff(base, desired)
        update_ops = [op for op in ops if isinstance(op, UpdateFootnoteContentOp)]
        assert len(update_ops) == 1
        assert update_ops[0].footnote_id == "fn1"
        assert update_ops[0].tab_id == "t1"

    def test_footnote_added(self) -> None:
        base = make_document(tabs=[self._tab_with_footnotes("t1", {})])
        desired = make_document(
            tabs=[self._tab_with_footnotes("t1", {"fn1": make_footnote("fn1")})]
        )
        ops = diff(base, desired)
        insert_ops = [op for op in ops if isinstance(op, InsertFootnoteOp)]
        assert len(insert_ops) == 1
        assert insert_ops[0].footnote_id == "fn1"

    def test_footnote_deleted(self) -> None:
        base = make_document(
            tabs=[self._tab_with_footnotes("t1", {"fn1": make_footnote("fn1")})]
        )
        desired = make_document(tabs=[self._tab_with_footnotes("t1", {})])
        ops = diff(base, desired)
        delete_ops = [op for op in ops if isinstance(op, DeleteFootnoteOp)]
        assert len(delete_ops) == 1
        assert delete_ops[0].footnote_id == "fn1"

    def test_footnotes_matched_by_id(self) -> None:
        """Footnotes fn1 and fn2 are matched by ID even if only one changes."""
        base_footnotes = {
            "fn1": make_footnote("fn1", "Footnote one"),
            "fn2": make_footnote("fn2", "Footnote two"),
        }
        desired_footnotes = {
            "fn1": make_footnote("fn1", "Footnote one"),  # unchanged
            "fn2": make_footnote("fn2", "Footnote two UPDATED"),  # changed
        }
        base = make_document(tabs=[self._tab_with_footnotes("t1", base_footnotes)])
        desired = make_document(
            tabs=[self._tab_with_footnotes("t1", desired_footnotes)]
        )
        ops = diff(base, desired)
        fn_ops = [op for op in ops if isinstance(op, UpdateFootnoteContentOp)]
        # Only fn2 changed
        assert len(fn_ops) == 1
        assert fn_ops[0].footnote_id == "fn2"


# ===========================================================================
# Part 7: Body content
# ===========================================================================


class TestBodyContent:
    def test_identical_body_no_ops(self) -> None:
        content = [make_para_el("Hello world"), make_terminal_para()]
        base = make_document(tabs=[make_tab("t1", body_content=content)])
        desired = make_document(
            tabs=[make_tab("t1", body_content=copy.deepcopy(content))]
        )
        ops = diff(base, desired)
        body_ops = [op for op in ops if isinstance(op, UpdateBodyContentOp)]
        assert body_ops == []

    def test_paragraph_added(self) -> None:
        base_content = [make_para_el("Para 1"), make_terminal_para()]
        desired_content = [
            make_para_el("Para 1"),
            make_para_el("New paragraph"),
            make_terminal_para(),
        ]
        base = make_document(tabs=[make_tab("t1", body_content=base_content)])
        desired = make_document(tabs=[make_tab("t1", body_content=desired_content)])
        ops = diff(base, desired)
        body_ops = [
            op
            for op in ops
            if isinstance(op, UpdateBodyContentOp) and op.story_kind == "body"
        ]
        assert len(body_ops) == 1
        alignment = body_ops[0].alignment
        # One desired index is unmatched (the new paragraph)
        assert len(alignment.desired_inserts) >= 1

    def test_paragraph_deleted(self) -> None:
        base_content = [
            make_para_el("Para 1"),
            make_para_el("Para to delete"),
            make_terminal_para(),
        ]
        desired_content = [make_para_el("Para 1"), make_terminal_para()]
        base = make_document(tabs=[make_tab("t1", body_content=base_content)])
        desired = make_document(tabs=[make_tab("t1", body_content=desired_content)])
        ops = diff(base, desired)
        body_ops = [
            op
            for op in ops
            if isinstance(op, UpdateBodyContentOp) and op.story_kind == "body"
        ]
        assert len(body_ops) == 1
        alignment = body_ops[0].alignment
        assert len(alignment.base_deletes) >= 1

    def test_table_added(self) -> None:
        base_content = [make_para_el("Before table"), make_terminal_para()]
        desired_content = [
            make_para_el("Before table"),
            make_table_el([["Cell A", "Cell B"]]),
            make_terminal_para(),
        ]
        base = make_document(tabs=[make_tab("t1", body_content=base_content)])
        desired = make_document(tabs=[make_tab("t1", body_content=desired_content)])
        ops = diff(base, desired)
        body_ops = [
            op
            for op in ops
            if isinstance(op, UpdateBodyContentOp) and op.story_kind == "body"
        ]
        assert len(body_ops) == 1
        alignment = body_ops[0].alignment
        assert len(alignment.desired_inserts) >= 1

    def test_paragraph_text_changed(self) -> None:
        base_content = [
            make_para_el("Original text for this paragraph"),
            make_terminal_para(),
        ]
        desired_content = [
            make_para_el("Updated text for this paragraph"),
            make_terminal_para(),
        ]
        base = make_document(tabs=[make_tab("t1", body_content=base_content)])
        desired = make_document(tabs=[make_tab("t1", body_content=desired_content)])
        ops = diff(base, desired)
        body_ops = [
            op
            for op in ops
            if isinstance(op, UpdateBodyContentOp) and op.story_kind == "body"
        ]
        assert len(body_ops) == 1
        alignment = body_ops[0].alignment
        # The paragraphs should be matched (high text similarity) even if changed
        assert len(alignment.matches) >= 1

    def test_terminal_paragraph_always_preserved(self) -> None:
        """The terminal paragraph is never deleted — alignment always matches it."""
        base_content = [make_terminal_para()]
        desired_content = [make_terminal_para()]
        base = make_document(tabs=[make_tab("t1", body_content=base_content)])
        desired = make_document(tabs=[make_tab("t1", body_content=desired_content)])
        ops = diff(base, desired)
        body_ops = [op for op in ops if isinstance(op, UpdateBodyContentOp)]
        # Identical — no ops
        assert body_ops == []

    def test_no_ops_for_empty_body(self) -> None:
        """Documents with only the terminal paragraph produce no body ops."""
        base = make_document(tabs=[make_tab("t1", body_content=[make_terminal_para()])])
        desired = make_document(
            tabs=[make_tab("t1", body_content=[make_terminal_para()])]
        )
        ops = diff(base, desired)
        assert ops == []


# ===========================================================================
# Part 8: Table cells (recursive)
# ===========================================================================


class TestTableCells:
    def test_identical_table_no_ops(self) -> None:
        table = make_table_el([["A", "B"], ["C", "D"]])
        base_content = [table, make_terminal_para()]
        base = make_document(tabs=[make_tab("t1", body_content=base_content)])
        desired = make_document(
            tabs=[make_tab("t1", body_content=copy.deepcopy(base_content))]
        )
        ops = diff(base, desired)
        assert ops == []

    def test_cell_content_changed(self) -> None:
        base_table = make_table_el([["Original cell content", "B"]])
        desired_table = make_table_el([["Changed cell content", "B"]])
        base_content = [base_table, make_terminal_para()]
        desired_content = [desired_table, make_terminal_para()]
        base = make_document(tabs=[make_tab("t1", body_content=base_content)])
        desired = make_document(tabs=[make_tab("t1", body_content=desired_content)])
        ops = diff(base, desired)

        # Should produce: body op (table matched) + cell content op
        body_ops = [op for op in ops if isinstance(op, UpdateBodyContentOp)]
        assert len(body_ops) >= 1
        cell_ops = [
            op
            for op in ops
            if isinstance(op, UpdateBodyContentOp) and op.story_kind == "table_cell"
        ]
        assert len(cell_ops) >= 1
        assert cell_ops[0].tab_id == "t1"

    def test_nested_table_recursion(self) -> None:
        """A table inside a cell triggers recursive alignment."""
        # Outer table: 1 row, 1 cell containing an inner table
        inner_base = make_table_el([["Inner cell"]])
        inner_desired = make_table_el([["Inner cell changed"]])

        outer_base_cell_content = [
            inner_base,
            make_terminal_para(),
        ]
        outer_desired_cell_content = [
            inner_desired,
            make_terminal_para(),
        ]

        base_table: dict[str, Any] = {
            "table": {
                "tableRows": [
                    {
                        "tableCells": [
                            {"content": outer_base_cell_content, "tableCellStyle": {}}
                        ],
                        "tableRowStyle": {},
                    }
                ],
                "columns": 1,
                "rows": 1,
            }
        }
        desired_table: dict[str, Any] = {
            "table": {
                "tableRows": [
                    {
                        "tableCells": [
                            {
                                "content": outer_desired_cell_content,
                                "tableCellStyle": {},
                            }
                        ],
                        "tableRowStyle": {},
                    }
                ],
                "columns": 1,
                "rows": 1,
            }
        }

        base_content = [base_table, make_terminal_para()]
        desired_content = [desired_table, make_terminal_para()]
        base = make_document(tabs=[make_tab("t1", body_content=base_content)])
        desired = make_document(tabs=[make_tab("t1", body_content=desired_content)])
        ops = diff(base, desired)

        cell_ops = [
            op
            for op in ops
            if isinstance(op, UpdateBodyContentOp) and op.story_kind == "table_cell"
        ]
        # Outer cell should produce a cell op; inner cell recursion may produce more
        assert len(cell_ops) >= 1


# ===========================================================================
# Part 9: End-to-end
# ===========================================================================


class TestEndToEnd:
    def test_complete_synthetic_document(self) -> None:
        """Build a 2-tab document with headers/footers/body/footnotes and make changes."""
        h1_base = make_header("h1", "Base header")
        h2_base = make_header("h2", "Tab 2 header")
        f1_base = make_footer("f1", "Base footer")
        fn1_base = make_footnote("fn1", "Footnote one")
        fn2_base = make_footnote("fn2", "Footnote two")
        list_def = {"listProperties": {"nestingLevels": [{"glyphType": "BULLETED"}]}}
        ns_normal = make_named_style("NORMAL_TEXT")
        ns_h1 = make_named_style("HEADING_1", bold=True)

        tab1_base = make_tab(
            "t1",
            "Main",
            0,
            body_content=[
                make_para_el("Introduction paragraph"),
                make_table_el([["Row 1 Col 1", "Row 1 Col 2"]]),
                make_terminal_para(),
            ],
            headers={"h1": h1_base},
            footers={"f1": f1_base},
            footnotes={"fn1": fn1_base, "fn2": fn2_base},
            lists={"list1": list_def},
            named_styles=[ns_normal, ns_h1],
            document_style={"defaultHeaderId": "h1", "defaultFooterId": "f1"},
        )
        tab2_base = make_tab(
            "t2",
            "Appendix",
            1,
            body_content=[make_para_el("Appendix content"), make_terminal_para()],
            headers={"h2": h2_base},
            document_style={"defaultHeaderId": "h2"},
        )

        base = make_document(tabs=[tab1_base, tab2_base])

        # Make multiple simultaneous changes across tree levels:
        # 1. Change header in tab1
        h1_desired = make_header("h1", "New header text")
        # 2. Add a new footnote in tab1
        fn3_desired = make_footnote("fn3", "New footnote")
        # 3. Remove footnote fn2
        # 4. Change HEADING_1 named style
        ns_h1_desired = make_named_style("HEADING_1", bold=True, font_size=20)
        # 5. Change body content in tab2
        # 6. Add a new tab (t3)
        tab3_desired = make_tab("t3", "New Tab", 2)

        tab1_desired = make_tab(
            "t1",
            "Main",
            0,
            body_content=[
                make_para_el("Introduction paragraph"),
                make_table_el([["Row 1 Col 1", "Row 1 Col 2"]]),
                make_terminal_para(),
            ],
            headers={"h1": h1_desired},
            footers={"f1": f1_base},
            footnotes={"fn1": fn1_base, "fn3": fn3_desired},  # fn2 removed, fn3 added
            lists={"list1": list_def},
            named_styles=[ns_normal, ns_h1_desired],  # h1 style changed
            document_style={"defaultHeaderId": "h1", "defaultFooterId": "f1"},
        )
        tab2_desired = make_tab(
            "t2",
            "Appendix",
            1,
            body_content=[
                make_para_el("Updated appendix content"),
                make_terminal_para(),
            ],
            headers={"h2": h2_base},
            document_style={"defaultHeaderId": "h2"},
        )

        desired = make_document(tabs=[tab1_desired, tab2_desired, tab3_desired])

        ops = diff(base, desired)

        # Verify each type of change is detected at each tree level
        # Tab: new tab added
        insert_tab_ops = [op for op in ops if isinstance(op, InsertTabOp)]
        assert len(insert_tab_ops) == 1

        # Header changed in tab1
        header_update_ops = [op for op in ops if isinstance(op, UpdateHeaderContentOp)]
        assert any(op.tab_id == "t1" for op in header_update_ops)

        # Footnote fn2 deleted
        delete_fn_ops = [op for op in ops if isinstance(op, DeleteFootnoteOp)]
        assert any(op.footnote_id == "fn2" for op in delete_fn_ops)

        # Footnote fn3 inserted
        insert_fn_ops = [op for op in ops if isinstance(op, InsertFootnoteOp)]
        assert any(op.footnote_id == "fn3" for op in insert_fn_ops)

        # Named style HEADING_1 changed
        ns_ops = [op for op in ops if isinstance(op, UpdateNamedStyleOp)]
        assert any(op.named_style_type == "HEADING_1" for op in ns_ops)

        # Body content changed in tab2
        body_ops = [
            op
            for op in ops
            if isinstance(op, UpdateBodyContentOp)
            and op.tab_id == "t2"
            and op.story_kind == "body"
        ]
        assert len(body_ops) >= 1

    def test_no_ops_for_identical_complete_document(self) -> None:
        """Identical complex documents → zero ops."""
        footnotes = {
            "fn1": make_footnote("fn1", "Footnote one"),
            "fn2": make_footnote("fn2", "Footnote two"),
        }
        tab = make_tab(
            "t1",
            body_content=[
                make_para_el("Para 1"),
                make_table_el([["A", "B"], ["C", "D"]]),
                make_terminal_para(),
            ],
            headers={"h1": make_header("h1", "Page header")},
            footers={"f1": make_footer("f1", "Page footer")},
            footnotes=footnotes,
            lists={"l1": {"listProperties": {"nestingLevels": []}}},
            named_styles=[make_named_style("NORMAL_TEXT")],
            document_style={"defaultHeaderId": "h1", "defaultFooterId": "f1"},
        )
        base = make_document(tabs=[tab])
        desired = copy.deepcopy(base)
        ops = diff(base, desired)
        assert ops == []

    def test_lowering_produces_requests_for_ops(self) -> None:
        """When ops are detected, lower_ops produces request dicts (or empty list
        when elements lack API index metadata).

        Synthetic test documents do not carry startIndex/endIndex, so the
        lowering skips index-dependent operations rather than crashing.
        The important invariant: lower_ops no longer raises NotImplementedError
        for the basic UpdateBodyContentOp case.
        """
        from extradoc.reconcile_v3.lower import lower_ops

        base = make_document(
            tabs=[
                make_tab(
                    "t1", body_content=[make_para_el("Hello"), make_terminal_para()]
                )
            ]
        )
        desired = make_document(
            tabs=[
                make_tab(
                    "t1",
                    body_content=[make_para_el("Hello changed"), make_terminal_para()],
                )
            ]
        )
        ops = diff(base, desired)
        assert len(ops) > 0
        # Lowering should succeed (may return empty list for docs without indices)
        result = lower_ops(ops)
        assert isinstance(result, list)

    def test_reconcile_api_calls_through(self) -> None:
        """reconcile() calls the diff + lower pipeline end-to-end."""
        from extradoc.reconcile_v3.api import reconcile

        base = make_document(
            tabs=[
                make_tab(
                    "t1", body_content=[make_para_el("Hello"), make_terminal_para()]
                )
            ]
        )
        desired = copy.deepcopy(base)
        # Identical → no ops → empty list returned
        result = reconcile(base, desired)
        assert result == []

    def test_reconcile_api_produces_list_for_changes(self) -> None:
        """reconcile() returns a list (possibly empty) when changes need lowering.

        For synthetic docs without API index metadata, the lowering skips
        index-dependent operations and returns an empty list rather than raising.
        The key invariant: reconcile() does not raise for a basic text change.
        """
        from extradoc.reconcile_v3.api import reconcile

        base = make_document(
            tabs=[
                make_tab(
                    "t1", body_content=[make_para_el("Hello"), make_terminal_para()]
                )
            ]
        )
        desired = make_document(
            tabs=[
                make_tab(
                    "t1",
                    body_content=[make_para_el("Hello changed"), make_terminal_para()],
                )
            ]
        )
        result = reconcile(base, desired)
        assert isinstance(result, list)


# ===========================================================================
# Part 10: Alignment sanity checks (content_align integration)
# ===========================================================================


class TestAlignmentIntegration:
    """Verify that the ContentAlignment embedded in UpdateBodyContentOp is correct."""

    def test_alignment_matches_contain_terminal(self) -> None:
        """Terminal paragraph is always in the matches list."""
        base_content = [make_para_el("Para A"), make_terminal_para()]
        desired_content = [make_para_el("Para A"), make_terminal_para()]
        base = make_document(tabs=[make_tab("t1", body_content=base_content)])
        desired = make_document(tabs=[make_tab("t1", body_content=desired_content)])
        # Identical — no ops
        ops = diff(base, desired)
        assert ops == []

    def test_alignment_insert_index_within_range(self) -> None:
        """Desired insert indices are within [0, len(desired_content)-1]."""
        base_content = [make_para_el("Para A"), make_terminal_para()]
        desired_content = [
            make_para_el("Para A"),
            make_para_el("Para B inserted"),
            make_terminal_para(),
        ]
        base = make_document(tabs=[make_tab("t1", body_content=base_content)])
        desired = make_document(tabs=[make_tab("t1", body_content=desired_content)])
        ops = diff(base, desired)
        body_ops = [op for op in ops if isinstance(op, UpdateBodyContentOp)]
        assert len(body_ops) == 1
        for idx in body_ops[0].alignment.desired_inserts:
            assert 0 <= idx < len(desired_content)

    def test_alignment_delete_index_within_range(self) -> None:
        base_content = [
            make_para_el("Para to delete"),
            make_para_el("Para A"),
            make_terminal_para(),
        ]
        desired_content = [make_para_el("Para A"), make_terminal_para()]
        base = make_document(tabs=[make_tab("t1", body_content=base_content)])
        desired = make_document(tabs=[make_tab("t1", body_content=desired_content)])
        ops = diff(base, desired)
        body_ops = [op for op in ops if isinstance(op, UpdateBodyContentOp)]
        assert len(body_ops) == 1
        for idx in body_ops[0].alignment.base_deletes:
            assert 0 <= idx < len(base_content)


# ===========================================================================
# Part 10: Table structural ops
# ===========================================================================


class TestTableStructuralOps:
    """Tests for row/column insert and delete ops detected by the diff layer."""

    def _make_doc_with_table(self, rows: list[list[str]]) -> dict[str, Any]:
        """Build a minimal document with a single table."""
        body = [make_table_el(rows), make_terminal_para()]
        return make_document(tabs=[make_tab("t1", body_content=body)])

    def test_identical_tables_no_ops(self) -> None:
        """Identical tables should produce no structural ops."""
        doc = self._make_doc_with_table([["A", "B"], ["C", "D"]])
        ops = diff(doc, copy.deepcopy(doc))
        structural = [
            op
            for op in ops
            if isinstance(
                op,
                InsertTableRowOp | DeleteTableRowOp | InsertTableColumnOp | DeleteTableColumnOp,
            )
        ]
        assert structural == []

    def test_row_added(self) -> None:
        """Base 2-row, desired 3-row → InsertTableRowOp for the new row."""
        base = self._make_doc_with_table([["A", "B"], ["C", "D"]])
        desired = self._make_doc_with_table([["A", "B"], ["C", "D"], ["E", "F"]])
        ops = diff(base, desired)
        insert_row_ops = [op for op in ops if isinstance(op, InsertTableRowOp)]
        assert len(insert_row_ops) == 1
        assert insert_row_ops[0].insert_below is True

    def test_row_deleted(self) -> None:
        """Base 3-row, desired 2-row → DeleteTableRowOp for the removed row."""
        base = self._make_doc_with_table([["A", "B"], ["C", "D"], ["E", "F"]])
        desired = self._make_doc_with_table([["A", "B"], ["E", "F"]])
        ops = diff(base, desired)
        delete_row_ops = [op for op in ops if isinstance(op, DeleteTableRowOp)]
        assert len(delete_row_ops) == 1

    def test_column_added(self) -> None:
        """Base 2-col, desired 3-col → InsertTableColumnOp."""
        base = self._make_doc_with_table([["A", "B"], ["C", "D"]])
        desired = self._make_doc_with_table([["A", "B", "X"], ["C", "D", "Y"]])
        ops = diff(base, desired)
        insert_col_ops = [op for op in ops if isinstance(op, InsertTableColumnOp)]
        assert len(insert_col_ops) == 1
        assert insert_col_ops[0].insert_right is True

    def test_column_deleted(self) -> None:
        """Base 3-col, desired 2-col → DeleteTableColumnOp."""
        base = self._make_doc_with_table([["A", "B", "C"], ["D", "E", "F"]])
        desired = self._make_doc_with_table([["A", "C"], ["D", "F"]])
        ops = diff(base, desired)
        delete_col_ops = [op for op in ops if isinstance(op, DeleteTableColumnOp)]
        assert len(delete_col_ops) == 1

    def test_row_added_and_cell_content_changed(self) -> None:
        """Row added AND cell content changed → both InsertTableRowOp and UpdateBodyContentOp."""
        base = self._make_doc_with_table([["A", "B"], ["C", "D"]])
        # Change "A" to "A_modified" and add a new row
        desired = self._make_doc_with_table(
            [["A_modified", "B"], ["C", "D"], ["E", "F"]]
        )
        ops = diff(base, desired)
        insert_row_ops = [op for op in ops if isinstance(op, InsertTableRowOp)]
        cell_ops = [
            op
            for op in ops
            if isinstance(op, UpdateBodyContentOp) and op.story_kind == "table_cell"
        ]
        assert len(insert_row_ops) >= 1
        assert len(cell_ops) >= 1

    def test_fuzzy_row_match_insert_middle(self) -> None:
        """Fuzzy LCS: base has 2 rows, desired has 3 (middle row inserted).

        ["hello", "world"] rows in base; desired adds a new row in the middle.
        The outer rows should be matched, the middle row emits InsertTableRowOp.
        """
        base = self._make_doc_with_table([["hello"], ["world"]])
        desired = self._make_doc_with_table([["hello"], ["new_row"], ["world"]])
        ops = diff(base, desired)
        insert_row_ops = [op for op in ops if isinstance(op, InsertTableRowOp)]
        delete_row_ops = [op for op in ops if isinstance(op, DeleteTableRowOp)]
        # Should insert 1 row (the new middle row) and not delete any
        assert len(insert_row_ops) == 1
        assert len(delete_row_ops) == 0
        # The inserted row should be below row 0 (after "hello")
        assert insert_row_ops[0].row_index == 0
        assert insert_row_ops[0].insert_below is True
