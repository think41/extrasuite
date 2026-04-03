"""Tests for bullet/list support in reconcile_v3.

Tests verify that:
- Inserting bullet paragraphs emits insertText + createParagraphBullets.
- Nesting levels are handled via leading tabs.
- Matched paragraphs gaining/losing/changing bullets emit the right requests.
- The _diff_lists fix: no UpdateListOp when base and desired list defs differ.
- No-op when bullet paragraph is identical.
"""

from __future__ import annotations

from typing import Any

from extradoc.reconcile_v3.api import diff, reconcile
from extradoc.reconcile_v3.model import UpdateListOp
from tests.reconcile_v3.helpers import (
    make_document,
    make_para_el,
    make_tab,
    make_terminal_para,
)

# ---------------------------------------------------------------------------
# Shared list definition (mimics what createParagraphBullets would produce)
# ---------------------------------------------------------------------------

_BULLET_LIST_DEF: dict[str, Any] = {
    "listProperties": {
        "nestingLevels": [
            {
                "bulletAlignment": "START",
                "glyphSymbol": "●",
                "glyphFormat": "%0",
                "indentFirstLine": {"magnitude": 18, "unit": "PT"},
                "indentStart": {"magnitude": 36, "unit": "PT"},
                "startNumber": 1,
                "textStyle": {"underline": False},
            }
        ]
    }
}

_NUMBERED_LIST_DEF: dict[str, Any] = {
    "listProperties": {
        "nestingLevels": [
            {
                "bulletAlignment": "START",
                "glyphType": "DECIMAL",
                "glyphFormat": "%0.",
                "indentFirstLine": {"magnitude": 18, "unit": "PT"},
                "indentStart": {"magnitude": 36, "unit": "PT"},
                "startNumber": 1,
                "textStyle": {"underline": False},
            }
        ]
    }
}


# ---------------------------------------------------------------------------
# Helper: build docs with bullets
# ---------------------------------------------------------------------------


def make_bullet_para(
    text: str,
    list_id: str = "list1",
    nesting_level: int = 0,
) -> dict[str, Any]:
    """Return a paragraph element dict with a bullet."""
    if not text.endswith("\n"):
        text = text + "\n"
    bullet: dict[str, Any] = {"listId": list_id}
    if nesting_level > 0:
        bullet["nestingLevel"] = nesting_level
    il = 18 + nesting_level * 36
    is_ = 36 + nesting_level * 36
    return {
        "paragraph": {
            "elements": [{"textRun": {"content": text}}],
            "bullet": bullet,
            "paragraphStyle": {
                "namedStyleType": "NORMAL_TEXT",
                "indentFirstLine": {"magnitude": il, "unit": "PT"},
                "indentStart": {"magnitude": is_, "unit": "PT"},
            },
        }
    }


def make_indexed_bullet_para(
    text: str,
    start: int,
    list_id: str = "list1",
    nesting_level: int = 0,
) -> dict[str, Any]:
    """Return an indexed paragraph element dict with a bullet."""
    from extradoc.indexer import utf16_len

    if not text.endswith("\n"):
        text = text + "\n"
    end = start + utf16_len(text)
    bullet: dict[str, Any] = {"listId": list_id}
    if nesting_level > 0:
        bullet["nestingLevel"] = nesting_level
    il = 18 + nesting_level * 36
    is_ = 36 + nesting_level * 36
    return {
        "startIndex": start,
        "endIndex": end,
        "paragraph": {
            "elements": [{"textRun": {"content": text}}],
            "bullet": bullet,
            "paragraphStyle": {
                "namedStyleType": "NORMAL_TEXT",
                "indentFirstLine": {"magnitude": il, "unit": "PT"},
                "indentStart": {"magnitude": is_, "unit": "PT"},
            },
        },
    }


def make_indexed_para(
    text: str, start: int, named_style: str = "NORMAL_TEXT"
) -> dict[str, Any]:
    """Return an indexed paragraph element (no bullet)."""
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
    return make_indexed_para("\n", start)


def make_doc_with_lists(
    tab_id: str,
    body_content: list[dict[str, Any]],
    lists: dict[str, Any],
) -> dict[str, Any]:
    """Build a document dict with explicit body content and lists."""
    return make_document(
        tabs=[
            make_tab(
                tab_id,
                body_content=body_content,
                lists=lists,
            )
        ]
    )


# ---------------------------------------------------------------------------
# Helpers to inspect requests
# ---------------------------------------------------------------------------


def _get_insert_text_requests(reqs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in reqs if "insertText" in r]


def _get_create_bullets_requests(reqs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in reqs if "createParagraphBullets" in r]


def _get_delete_bullets_requests(reqs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in reqs if "deleteParagraphBullets" in r]


def _get_update_para_style_requests(reqs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in reqs if "updateParagraphStyle" in r]


def _get_delete_content_requests(reqs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in reqs if "deleteContentRange" in r]


# ===========================================================================
# Test 1: Insert bullet paragraph into empty doc
# ===========================================================================


class TestInsertBulletParagraph:
    """Inserting bullet paragraphs from scratch."""

    def test_add_bullet_to_empty_doc(self) -> None:
        """Base has one normal terminal, desired has one bullet paragraph.

        Assert: insertText(text, ...) + createParagraphBullets(...).
        """
        base = make_document(
            tabs=[
                make_tab(
                    "t1",
                    body_content=[make_indexed_terminal(1)],
                )
            ]
        )
        desired = make_doc_with_lists(
            "t1",
            body_content=[
                make_bullet_para("Hello\n"),
                make_terminal_para(),
            ],
            lists={"list1": _BULLET_LIST_DEF},
        )

        reqs = reconcile(base, desired)

        insert_reqs = _get_insert_text_requests(reqs)
        bullet_reqs = _get_create_bullets_requests(reqs)

        assert len(insert_reqs) >= 1, "Should have at least one insertText"
        assert len(bullet_reqs) == 1, "Should have exactly one createParagraphBullets"

        # Verify the preset is correct
        preset = bullet_reqs[0]["createParagraphBullets"]["bulletPreset"]
        assert preset == "BULLET_DISC_CIRCLE_SQUARE"

    def test_add_bullet_nested_level_1(self) -> None:
        """Desired has bullet paragraph at nesting_level=1.

        Assert: insertText starts with one tab + createParagraphBullets.
        """
        base = make_document(
            tabs=[
                make_tab(
                    "t1",
                    body_content=[make_indexed_terminal(1)],
                )
            ]
        )
        desired = make_doc_with_lists(
            "t1",
            body_content=[
                make_bullet_para("Hello\n", nesting_level=1),
                make_terminal_para(),
            ],
            lists={"list1": _BULLET_LIST_DEF},
        )

        reqs = reconcile(base, desired)

        insert_reqs = _get_insert_text_requests(reqs)
        bullet_reqs = _get_create_bullets_requests(reqs)

        assert len(bullet_reqs) == 1, "Should have exactly one createParagraphBullets"

        # One of the insertText requests should have a leading tab
        texts_inserted = [r["insertText"]["text"] for r in insert_reqs]
        assert any(
            t.startswith("\t") for t in texts_inserted
        ), f"Expected leading tab in one of: {texts_inserted}"

    def test_add_bullet_nested_level_2(self) -> None:
        """Desired has bullet paragraph at nesting_level=2 → two leading tabs."""
        base = make_document(
            tabs=[
                make_tab(
                    "t1",
                    body_content=[make_indexed_terminal(1)],
                )
            ]
        )
        desired = make_doc_with_lists(
            "t1",
            body_content=[
                make_bullet_para("Hello\n", nesting_level=2),
                make_terminal_para(),
            ],
            lists={"list1": _BULLET_LIST_DEF},
        )

        reqs = reconcile(base, desired)

        insert_reqs = _get_insert_text_requests(reqs)
        bullet_reqs = _get_create_bullets_requests(reqs)

        assert len(bullet_reqs) == 1
        texts_inserted = [r["insertText"]["text"] for r in insert_reqs]
        assert any(
            t.startswith("\t\t") for t in texts_inserted
        ), f"Expected two leading tabs in one of: {texts_inserted}"

    def test_bullet_list_multiple_items(self) -> None:
        """Desired has 3 bullet items. Assert correct number of createParagraphBullets."""
        base = make_document(
            tabs=[
                make_tab(
                    "t1",
                    body_content=[make_indexed_terminal(1)],
                )
            ]
        )
        desired = make_doc_with_lists(
            "t1",
            body_content=[
                make_bullet_para("Item 1\n"),
                make_bullet_para("Item 2\n"),
                make_bullet_para("Item 3\n"),
                make_terminal_para(),
            ],
            lists={"list1": _BULLET_LIST_DEF},
        )

        reqs = reconcile(base, desired)

        insert_reqs = _get_insert_text_requests(reqs)
        bullet_reqs = _get_create_bullets_requests(reqs)

        assert len(insert_reqs) >= 3, "Should have at least 3 insertText requests"
        # Same-position inserts with the same preset are merged into a single
        # createParagraphBullets call covering the full range.
        assert len(bullet_reqs) == 1, "Should have 1 merged createParagraphBullets"

    def test_ordered_list_insert(self) -> None:
        """Desired has decimal/ordered list. Assert NUMBERED_DECIMAL_NESTED preset."""
        base = make_document(
            tabs=[
                make_tab(
                    "t1",
                    body_content=[make_indexed_terminal(1)],
                )
            ]
        )
        desired = make_doc_with_lists(
            "t1",
            body_content=[
                make_bullet_para("Item 1\n", list_id="list1"),
                make_terminal_para(),
            ],
            lists={"list1": _NUMBERED_LIST_DEF},
        )

        reqs = reconcile(base, desired)

        bullet_reqs = _get_create_bullets_requests(reqs)
        assert len(bullet_reqs) == 1
        preset = bullet_reqs[0]["createParagraphBullets"]["bulletPreset"]
        assert preset == "NUMBERED_DECIMAL_NESTED"


# ===========================================================================
# Test 2: Matched paragraph bullet changes
# ===========================================================================


class TestMatchedParagraphBulletChanges:
    """Matched paragraphs whose bullet status changes."""

    def test_normal_paragraph_gains_bullet(self) -> None:
        """Matched paragraph, base has no bullet, desired has bullet.

        Assert: createParagraphBullets emitted.
        """
        base = make_document(
            tabs=[
                make_tab(
                    "t1",
                    body_content=[
                        make_indexed_para("Hello\n", 1),
                        make_indexed_terminal(7),
                    ],
                )
            ]
        )
        desired = make_doc_with_lists(
            "t1",
            body_content=[
                make_bullet_para("Hello\n"),
                make_terminal_para(),
            ],
            lists={"list1": _BULLET_LIST_DEF},
        )

        reqs = reconcile(base, desired)

        bullet_reqs = _get_create_bullets_requests(reqs)
        assert len(bullet_reqs) == 1, f"Expected createParagraphBullets, got: {reqs}"

    def test_bullet_paragraph_loses_bullet(self) -> None:
        """Matched paragraph, base has bullet, desired has no bullet.

        Assert: deleteParagraphBullets + updateParagraphStyle to clear indent.
        """
        base = make_doc_with_lists(
            "t1",
            body_content=[
                make_indexed_bullet_para("Hello\n", 1),
                make_indexed_terminal(7),
            ],
            lists={"list1": _BULLET_LIST_DEF},
        )
        desired = make_document(
            tabs=[
                make_tab(
                    "t1",
                    body_content=[
                        make_para_el("Hello\n"),
                        make_terminal_para(),
                    ],
                )
            ]
        )

        reqs = reconcile(base, desired)

        delete_bullet_reqs = _get_delete_bullets_requests(reqs)
        assert (
            len(delete_bullet_reqs) == 1
        ), f"Expected deleteParagraphBullets, got: {reqs}"

        # Should also clear indentation
        para_style_reqs = _get_update_para_style_requests(reqs)
        assert any(
            "indentStart" in r["updateParagraphStyle"]["fields"]
            or "indentFirstLine" in r["updateParagraphStyle"]["fields"]
            for r in para_style_reqs
        ), f"Expected indent clear in updateParagraphStyle, got: {para_style_reqs}"

    def test_bullet_nesting_level_change(self) -> None:
        """Matched bullet paragraph, nesting_level changes from 0 to 1.

        Assert: deleteParagraphBullets + insertText (tabs) + createParagraphBullets.
        """
        base = make_doc_with_lists(
            "t1",
            body_content=[
                make_indexed_bullet_para("Hello\n", 1, nesting_level=0),
                make_indexed_terminal(7),
            ],
            lists={"list1": _BULLET_LIST_DEF},
        )
        desired = make_doc_with_lists(
            "t1",
            body_content=[
                make_bullet_para("Hello\n", nesting_level=1),
                make_terminal_para(),
            ],
            lists={"list1": _BULLET_LIST_DEF},
        )

        reqs = reconcile(base, desired)

        delete_bullet_reqs = _get_delete_bullets_requests(reqs)
        create_bullet_reqs = _get_create_bullets_requests(reqs)

        assert (
            len(delete_bullet_reqs) == 1
        ), f"Expected deleteParagraphBullets, got: {reqs}"
        assert (
            len(create_bullet_reqs) == 1
        ), f"Expected createParagraphBullets, got: {reqs}"


# ===========================================================================
# Test 3: Delete bullet paragraph
# ===========================================================================


class TestDeleteBulletParagraph:
    """Deleting bullet paragraphs."""

    def test_delete_bullet_paragraph(self) -> None:
        """Base has bullet paragraph, desired doesn't.

        Assert: deleteContentRange (no bullet-specific requests needed).
        """
        base = make_doc_with_lists(
            "t1",
            body_content=[
                make_indexed_bullet_para("Hello\n", 1),
                make_indexed_terminal(7),
            ],
            lists={"list1": _BULLET_LIST_DEF},
        )
        desired = make_document(
            tabs=[
                make_tab(
                    "t1",
                    body_content=[
                        make_terminal_para(),
                    ],
                )
            ]
        )

        reqs = reconcile(base, desired)

        delete_reqs = _get_delete_content_requests(reqs)
        assert len(delete_reqs) >= 1, "Should have at least one deleteContentRange"
        # Should NOT have createParagraphBullets or deleteParagraphBullets
        assert _get_create_bullets_requests(reqs) == []
        assert _get_delete_bullets_requests(reqs) == []


# ===========================================================================
# Test 4: No-op bullet
# ===========================================================================


class TestNoOpBullet:
    """Identical bullet paragraphs produce no requests."""

    def test_no_op_bullet(self) -> None:
        """Identical bullet paragraph in base and desired → no requests."""
        base = make_doc_with_lists(
            "t1",
            body_content=[
                make_indexed_bullet_para("Hello\n", 1),
                make_indexed_terminal(7),
            ],
            lists={"list1": _BULLET_LIST_DEF},
        )
        # Desired matches base exactly (no index fields, but same content)
        desired = make_doc_with_lists(
            "t1",
            body_content=[
                make_indexed_bullet_para("Hello\n", 1),
                make_indexed_terminal(7),
            ],
            lists={"list1": _BULLET_LIST_DEF},
        )

        reqs = reconcile(base, desired)

        assert (
            reqs == []
        ), f"Expected no requests for identical bullet docs, got: {reqs}"


# ===========================================================================
# Test 5: Text edit in bullet paragraph
# ===========================================================================


class TestBulletTextEdit:
    """Text changes within bullet paragraphs."""

    def test_bullet_text_edit(self) -> None:
        """Matched bullet paragraph, same bullet, different text.

        Assert: text diff requests only (no bullet requests — bullet unchanged).
        """
        base = make_doc_with_lists(
            "t1",
            body_content=[
                make_indexed_bullet_para("Old text\n", 1),
                make_indexed_terminal(10),
            ],
            lists={"list1": _BULLET_LIST_DEF},
        )
        desired = make_doc_with_lists(
            "t1",
            body_content=[
                make_bullet_para("New text\n"),
                make_terminal_para(),
            ],
            lists={"list1": _BULLET_LIST_DEF},
        )

        reqs = reconcile(base, desired)

        # Should NOT have createParagraphBullets — bullet is unchanged
        assert (
            _get_create_bullets_requests(reqs) == []
        ), f"Expected no createParagraphBullets for same-bullet text edit, got: {reqs}"
        # Should NOT have deleteParagraphBullets
        assert (
            _get_delete_bullets_requests(reqs) == []
        ), f"Expected no deleteParagraphBullets, got: {reqs}"
        # Should have some text modification request
        assert len(reqs) > 0, "Should have at least one request for text change"


# ===========================================================================
# Test 6: _diff_lists fix — no UpdateListOp
# ===========================================================================


class TestDiffListsNoUpdateListOp:
    """_diff_lists should not emit UpdateListOp when base and desired list defs differ."""

    def test_no_update_list_op_when_list_defs_differ(self) -> None:
        """Base and desired have same list ID but different list defs.

        The old code emitted UpdateListOp (which raises NotImplementedError in lower).
        The fix: emit nothing when the list exists in both.
        """
        base = make_doc_with_lists(
            "t1",
            body_content=[make_indexed_terminal(1)],
            lists={
                "list1": {"listProperties": {"nestingLevels": [{"glyphSymbol": "●"}]}}
            },
        )
        desired = make_doc_with_lists(
            "t1",
            body_content=[make_terminal_para()],
            lists={
                "list1": {
                    "listProperties": {
                        "nestingLevels": [
                            {
                                "glyphSymbol": "●",
                                "bulletAlignment": "START",
                                "indentFirstLine": {"magnitude": 18, "unit": "PT"},
                                "indentStart": {"magnitude": 36, "unit": "PT"},
                            }
                        ]
                    }
                }
            },
        )

        # With the old code, this would raise NotImplementedError via UpdateListOp.
        # With the fix, it should return empty ops (no list change to lower).
        ops = diff(base, desired)
        update_list_ops = [op for op in ops if isinstance(op, UpdateListOp)]
        assert (
            update_list_ops == []
        ), f"Expected no UpdateListOp, got: {update_list_ops}"

        # Should not raise
        reqs = reconcile(base, desired)
        assert isinstance(reqs, list)

    def test_insert_new_list_emits_insert_list_op(self) -> None:
        """A new list in desired (not in base) emits InsertListOp (no-op in lower)."""
        base = make_doc_with_lists(
            "t1",
            body_content=[make_indexed_terminal(1)],
            lists={},
        )
        desired = make_doc_with_lists(
            "t1",
            body_content=[
                make_bullet_para("Hello\n"),
                make_terminal_para(),
            ],
            lists={"list1": _BULLET_LIST_DEF},
        )

        # Should not raise and should produce bullet requests
        reqs = reconcile(base, desired)
        assert _get_create_bullets_requests(reqs), "Expected createParagraphBullets"

    def test_delete_list_is_no_op(self) -> None:
        """A list in base but not in desired emits DeleteListOp (no-op in lower)."""
        base = make_doc_with_lists(
            "t1",
            body_content=[make_indexed_terminal(1)],
            lists={"list1": _BULLET_LIST_DEF},
        )
        desired = make_doc_with_lists(
            "t1",
            body_content=[make_terminal_para()],
            lists={},
        )

        # Should not raise
        reqs = reconcile(base, desired)
        assert isinstance(reqs, list)


# ===========================================================================
# Test 7: Bullet preset inference
# ===========================================================================


class TestBulletPresetInference:
    """_infer_bullet_preset correctly maps list defs to preset strings."""

    def test_disc_bullet_preset(self) -> None:
        """glyphSymbol '●' → BULLET_DISC_CIRCLE_SQUARE."""
        from extradoc.reconcile_v3.lower import _infer_bullet_preset

        bullet = {"listId": "list1"}
        lists = {"list1": {"listProperties": {"nestingLevels": [{"glyphSymbol": "●"}]}}}
        assert _infer_bullet_preset(bullet, lists) == "BULLET_DISC_CIRCLE_SQUARE"

    def test_decimal_numbered_preset(self) -> None:
        """glyphType 'DECIMAL' → NUMBERED_DECIMAL_NESTED."""
        from extradoc.reconcile_v3.lower import _infer_bullet_preset

        bullet = {"listId": "list1"}
        lists = {
            "list1": {"listProperties": {"nestingLevels": [{"glyphType": "DECIMAL"}]}}
        }
        assert _infer_bullet_preset(bullet, lists) == "NUMBERED_DECIMAL_NESTED"

    def test_checkbox_preset(self) -> None:
        """glyphType 'GLYPH_TYPE_UNSPECIFIED' → BULLET_CHECKBOX."""
        from extradoc.reconcile_v3.lower import _infer_bullet_preset

        bullet = {"listId": "list1"}
        lists = {
            "list1": {
                "listProperties": {
                    "nestingLevels": [{"glyphType": "GLYPH_TYPE_UNSPECIFIED"}]
                }
            }
        }
        assert _infer_bullet_preset(bullet, lists) == "BULLET_CHECKBOX"

    def test_missing_list_falls_back_to_disc(self) -> None:
        """Missing list_id → BULLET_DISC_CIRCLE_SQUARE fallback."""
        from extradoc.reconcile_v3.lower import _infer_bullet_preset

        bullet = {"listId": "missing_list"}
        assert _infer_bullet_preset(bullet, {}) == "BULLET_DISC_CIRCLE_SQUARE"

    def test_empty_lists_falls_back_to_disc(self) -> None:
        """No lists dict → BULLET_DISC_CIRCLE_SQUARE fallback."""
        from extradoc.reconcile_v3.lower import _infer_bullet_preset

        bullet = {"listId": "list1"}
        assert _infer_bullet_preset(bullet, {}) == "BULLET_DISC_CIRCLE_SQUARE"
