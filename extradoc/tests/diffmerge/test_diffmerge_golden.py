"""Golden-file round-trip tests for the diffmerge package.

Load a real Google Docs Document, make targeted edits to create a 'desired'
version, then verify:
  1. diff(base, desired) produces the expected ops
  2. apply(base_dict, ops) produces a document matching desired
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

from extradoc.api_types._generated import Document
from extradoc.diffmerge import (
    DeleteTableRowOp,
    DiffOp,
    InsertTableRowOp,
    UpdateBodyContentOp,
    UpdateNamedStyleOp,
    apply,
    diff,
)

GOLDEN_DIR = Path(__file__).parent.parent / "golden"
MD_GOLDEN_ID = "1vL8dY0Ok__9VaUIqhBCMeElS5QdaKZfbgr_YCja5kx0"
MULTITAB_GOLDEN_ID = "14nMj7vggV3XR3WQtYcgrABRABjKk-fqw0UQUCP25rhQ"
LISTS_GOLDEN_ID = "1YicNYwId9u4okuK4uNfWdTEuKyS1QWb1RcnZl9eVyTc"


def _load_golden(doc_id: str) -> Document:
    path = GOLDEN_DIR / f"{doc_id}.json"
    return Document.model_validate(json.loads(path.read_text()))


def _to_dict(doc: Document) -> dict[str, Any]:
    return doc.model_dump(by_alias=True, exclude_none=True)


def _edit(doc: Document, mutator: Callable[[dict[str, Any]], None]) -> Document:
    """Deep copy doc as dict, apply mutation, return new Document."""
    d = _to_dict(doc)
    mutator(d)
    return Document.model_validate(d)


def _strip_indices(d: Any) -> Any:
    """Recursively remove startIndex/endIndex for comparison."""
    if isinstance(d, dict):
        return {
            k: _strip_indices(v)
            for k, v in d.items()
            if k not in ("startIndex", "endIndex")
        }
    if isinstance(d, list):
        return [_strip_indices(item) for item in d]
    return d


def _body_content(d: dict[str, Any], tab_idx: int = 0) -> list[dict[str, Any]]:
    """Get body content elements from a document dict."""
    return d["tabs"][tab_idx]["documentTab"]["body"]["content"]


def _para_text(element: dict[str, Any]) -> str:
    """Extract plain text from a paragraph element."""
    para = element.get("paragraph", {})
    parts = []
    for el in para.get("elements", []):
        tr = el.get("textRun", {})
        parts.append(tr.get("content", ""))
    return "".join(parts)


def _assert_roundtrip(base: Document, desired: Document) -> None:
    """Verify that diff->apply reproduces desired from base."""
    ops = diff(base, desired)
    base_dict = _to_dict(base)
    merged_dict = apply(base_dict, ops)
    desired_dict = _to_dict(desired)
    assert _strip_indices(merged_dict) == _strip_indices(desired_dict)


def _flatten_ops(ops: list[DiffOp]) -> list[DiffOp]:
    """Flatten ops including child_ops from UpdateBodyContentOp."""
    result: list[DiffOp] = []
    for op in ops:
        result.append(op)
        if isinstance(op, UpdateBodyContentOp) and op.child_ops:
            result.extend(_flatten_ops(op.child_ops))
    return result


class TestDiffMergeGolden:
    """Golden-file round-trip tests for diff and apply."""

    # ------------------------------------------------------------------ #
    # 1. No-op: identical documents produce zero ops
    # ------------------------------------------------------------------ #
    def test_noop(self) -> None:
        base = _load_golden(MD_GOLDEN_ID)
        desired = _load_golden(MD_GOLDEN_ID)  # fresh identical copy
        ops = diff(base, desired)
        assert ops == [], f"Expected zero ops for identical docs, got {len(ops)}"
        _assert_roundtrip(base, desired)

    # ------------------------------------------------------------------ #
    # 2. Edit paragraph text
    # ------------------------------------------------------------------ #
    def test_edit_paragraph_text(self) -> None:
        """Change 'Second plain paragraph.' to 'Edited paragraph text.'"""
        base = _load_golden(MD_GOLDEN_ID)

        def mutator(d: dict[str, Any]) -> None:
            # Element at index 3 (0=sectionBreak, 1=H1 "Introduction",
            # 2="This is a plain paragraph...", 3="Second plain paragraph.")
            content = _body_content(d)
            para = content[3]["paragraph"]
            para["elements"] = [
                {
                    "textRun": {
                        "content": "Edited paragraph text.\n",
                        "textStyle": {},
                    }
                }
            ]

        desired = _edit(base, mutator)
        ops = diff(base, desired)
        assert len(ops) > 0, "Expected at least one op"

        # Should contain an UpdateBodyContentOp targeting the body
        body_ops = [op for op in ops if isinstance(op, UpdateBodyContentOp)]
        assert len(body_ops) > 0, "Expected UpdateBodyContentOp"

        _assert_roundtrip(base, desired)

    # ------------------------------------------------------------------ #
    # 3. Add a paragraph
    # ------------------------------------------------------------------ #
    def test_add_paragraph(self) -> None:
        """Insert a new paragraph after 'Second plain paragraph.'"""
        base = _load_golden(MD_GOLDEN_ID)

        def mutator(d: dict[str, Any]) -> None:
            content = _body_content(d)
            new_para = {
                "paragraph": {
                    "elements": [
                        {
                            "textRun": {
                                "content": "A brand new paragraph.\n",
                                "textStyle": {},
                            }
                        }
                    ],
                    "paragraphStyle": {
                        "namedStyleType": "NORMAL_TEXT",
                        "direction": "LEFT_TO_RIGHT",
                    },
                }
            }
            # Insert after index 3 ("Second plain paragraph.")
            content.insert(4, new_para)

        desired = _edit(base, mutator)
        ops = diff(base, desired)
        assert len(ops) > 0, "Expected at least one op for added paragraph"

        body_ops = [op for op in ops if isinstance(op, UpdateBodyContentOp)]
        assert len(body_ops) > 0, "Expected UpdateBodyContentOp"

        _assert_roundtrip(base, desired)

    # ------------------------------------------------------------------ #
    # 4. Delete a paragraph
    # ------------------------------------------------------------------ #
    def test_delete_paragraph(self) -> None:
        """Remove 'Second plain paragraph.' from the document."""
        base = _load_golden(MD_GOLDEN_ID)

        def mutator(d: dict[str, Any]) -> None:
            content = _body_content(d)
            # Remove element at index 3 ("Second plain paragraph.\n")
            del content[3]

        desired = _edit(base, mutator)
        ops = diff(base, desired)
        assert len(ops) > 0, "Expected at least one op for deleted paragraph"

        body_ops = [op for op in ops if isinstance(op, UpdateBodyContentOp)]
        assert len(body_ops) > 0, "Expected UpdateBodyContentOp"

        _assert_roundtrip(base, desired)

    # ------------------------------------------------------------------ #
    # 5. Change heading level
    # ------------------------------------------------------------------ #
    def test_change_heading_level(self) -> None:
        """Change 'Formatting Section' from HEADING_2 to HEADING_3."""
        base = _load_golden(MD_GOLDEN_ID)

        def mutator(d: dict[str, Any]) -> None:
            content = _body_content(d)
            # Element at index 4: "Formatting Section\n" with HEADING_2
            para_style = content[4]["paragraph"]["paragraphStyle"]
            assert para_style["namedStyleType"] == "HEADING_2", (
                f"Expected HEADING_2 at index 4, got {para_style['namedStyleType']}"
            )
            para_style["namedStyleType"] = "HEADING_3"

        desired = _edit(base, mutator)
        ops = diff(base, desired)
        assert len(ops) > 0, "Expected at least one op for heading change"

        _assert_roundtrip(base, desired)

    # ------------------------------------------------------------------ #
    # 6. Edit table cell text
    # ------------------------------------------------------------------ #
    def test_edit_table_cell(self) -> None:
        """Change cell text 'Alpha' to 'Omega' in the table.

        The table is at body content index (searching for element with 'table' key).
        Row 1 (data row), cell 0 contains 'Alpha\\n'.
        """
        base = _load_golden(MD_GOLDEN_ID)

        def mutator(d: dict[str, Any]) -> None:
            content = _body_content(d)
            # Find the table element
            table_el = None
            for el in content:
                if "table" in el:
                    table_el = el
                    break
            assert table_el is not None, "No table found in golden file"

            # Row 1 (second row, first data row), cell 0: "Alpha\n"
            cell = table_el["table"]["tableRows"][1]["tableCells"][0]
            cell_para = cell["content"][0]["paragraph"]
            cell_para["elements"] = [
                {
                    "textRun": {
                        "content": "Omega\n",
                        "textStyle": {},
                    }
                }
            ]

        desired = _edit(base, mutator)
        ops = diff(base, desired)
        assert len(ops) > 0, "Expected at least one op for table cell edit"

        # The table cell edit should appear as an UpdateBodyContentOp with
        # child_ops or a nested body content op
        all_ops = _flatten_ops(ops)
        body_ops = [op for op in all_ops if isinstance(op, UpdateBodyContentOp)]
        assert len(body_ops) > 0, "Expected UpdateBodyContentOp for table cell"

        _assert_roundtrip(base, desired)

    # ------------------------------------------------------------------ #
    # 7. Add a table row
    # ------------------------------------------------------------------ #
    def test_add_table_row(self) -> None:
        """Add a new row to the table with cells [Gamma, 300, Third item]."""
        base = _load_golden(MD_GOLDEN_ID)

        def mutator(d: dict[str, Any]) -> None:
            content = _body_content(d)
            table_el = None
            for el in content:
                if "table" in el:
                    table_el = el
                    break
            assert table_el is not None

            table = table_el["table"]
            # Copy the structure of an existing data row (row 1)
            existing_row = copy.deepcopy(table["tableRows"][1])

            # Update cell contents: Gamma, 300, Third item
            cells = existing_row["tableCells"]
            cells[0]["content"][0]["paragraph"]["elements"] = [
                {"textRun": {"content": "Gamma\n", "textStyle": {}}}
            ]
            cells[1]["content"][0]["paragraph"]["elements"] = [
                {"textRun": {"content": "300\n", "textStyle": {}}}
            ]
            cells[2]["content"][0]["paragraph"]["elements"] = [
                {"textRun": {"content": "Third item\n", "textStyle": {}}}
            ]

            # Strip indices from the new row (apply will recompute)
            def _strip(obj: Any) -> Any:
                if isinstance(obj, dict):
                    return {
                        k: _strip(v)
                        for k, v in obj.items()
                        if k not in ("startIndex", "endIndex")
                    }
                if isinstance(obj, list):
                    return [_strip(i) for i in obj]
                return obj

            new_row = _strip(existing_row)
            table["tableRows"].append(new_row)
            table["rows"] = len(table["tableRows"])

        desired = _edit(base, mutator)
        ops = diff(base, desired)
        assert len(ops) > 0, "Expected ops for added table row"

        all_ops = _flatten_ops(ops)
        row_insert_ops = [op for op in all_ops if isinstance(op, InsertTableRowOp)]
        assert len(row_insert_ops) > 0, "Expected InsertTableRowOp"

        _assert_roundtrip(base, desired)

    # ------------------------------------------------------------------ #
    # 8. Delete a table row
    # ------------------------------------------------------------------ #
    def test_delete_table_row(self) -> None:
        """Delete the last data row (row 2: Beta, 200, The second item)."""
        base = _load_golden(MD_GOLDEN_ID)

        def mutator(d: dict[str, Any]) -> None:
            content = _body_content(d)
            table_el = None
            for el in content:
                if "table" in el:
                    table_el = el
                    break
            assert table_el is not None

            table = table_el["table"]
            # Remove last row (index 2: Beta / 200 / The second item)
            del table["tableRows"][2]
            table["rows"] = len(table["tableRows"])

        desired = _edit(base, mutator)
        ops = diff(base, desired)
        assert len(ops) > 0, "Expected ops for deleted table row"

        all_ops = _flatten_ops(ops)
        row_delete_ops = [op for op in all_ops if isinstance(op, DeleteTableRowOp)]
        assert len(row_delete_ops) > 0, "Expected DeleteTableRowOp"

        _assert_roundtrip(base, desired)

    # ------------------------------------------------------------------ #
    # 9. Edit only one tab of a multitab document
    # ------------------------------------------------------------------ #
    def test_edit_multitab_one_tab_only(self) -> None:
        """Edit tab 1 ('Version 2') of the multitab doc; other tabs unchanged."""
        base = _load_golden(MULTITAB_GOLDEN_ID)

        # The multitab doc has 3 tabs with tabIds: t.0, t.onxbcvnykaov, t.q5ol1vnmynzo
        target_tab_id = "t.onxbcvnykaov"

        def mutator(d: dict[str, Any]) -> None:
            # Tab index 1 = "Version 2" (tabId: t.onxbcvnykaov)
            content = _body_content(d, tab_idx=1)
            # Content[1] is the first paragraph after sectionBreak
            para = content[1]["paragraph"]
            para["elements"] = [
                {
                    "textRun": {
                        "content": "Modified text in Version 2 tab.\n",
                        "textStyle": {},
                    }
                }
            ]

        desired = _edit(base, mutator)
        ops = diff(base, desired)
        assert len(ops) > 0, "Expected ops for single-tab edit"

        # All ops should reference only the edited tab
        for op in ops:
            if hasattr(op, "tab_id"):
                assert op.tab_id == target_tab_id, (
                    f"Op targets tab {op.tab_id}, expected {target_tab_id}"
                )

        _assert_roundtrip(base, desired)

    # ------------------------------------------------------------------ #
    # 10. Update a named style definition
    # ------------------------------------------------------------------ #
    def test_named_style_update(self) -> None:
        """Change HEADING_1 fontSize from 20pt to 24pt."""
        base = _load_golden(MD_GOLDEN_ID)

        def mutator(d: dict[str, Any]) -> None:
            tab = d["tabs"][0]["documentTab"]
            styles = tab["namedStyles"]["styles"]
            for style in styles:
                if style["namedStyleType"] == "HEADING_1":
                    style["textStyle"]["fontSize"] = {
                        "magnitude": 24,
                        "unit": "PT",
                    }
                    break

        desired = _edit(base, mutator)
        ops = diff(base, desired)
        assert len(ops) > 0, "Expected ops for named style update"

        style_ops = [op for op in ops if isinstance(op, UpdateNamedStyleOp)]
        assert len(style_ops) > 0, "Expected UpdateNamedStyleOp"
        assert style_ops[0].named_style_type == "HEADING_1"

        _assert_roundtrip(base, desired)
