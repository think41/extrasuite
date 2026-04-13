"""Tests for bullet/list support in reconcile_v3.

Tests verify that:
- Inserting bullet paragraphs emits insertText + createParagraphBullets.
- Nesting levels are handled via leading tabs.
- Matched paragraphs gaining/losing/changing bullets emit the right requests.
- The _diff_lists fix: no UpdateListOp when base and desired list defs differ.
- No-op when bullet paragraph is identical.
"""

from __future__ import annotations

from extradoc.api_types._generated import (
    Bullet,
    Dimension,
    Document,
    ListProperties,
    NestingLevel,
    Paragraph,
    ParagraphElement,
    ParagraphStyle,
    Request,
    StructuralElement,
    TextRun,
    TextStyle,
)
from extradoc.api_types._generated import (
    List as DocList,
)
from extradoc.diffmerge import UpdateListOp, diff
from extradoc.reconcile_v3.api import reconcile
from tests.reconcile_v3.helpers import (
    make_document,
    make_indexed_para,
    make_indexed_terminal,
    make_para_el,
    make_tab,
    make_terminal_para,
)

# ---------------------------------------------------------------------------
# Shared list definition (mimics what createParagraphBullets would produce)
# ---------------------------------------------------------------------------

_BULLET_LIST_DEF = DocList(
    list_properties=ListProperties(
        nesting_levels=[
            NestingLevel(
                bullet_alignment="START",
                glyph_symbol="\u25cf",
                glyph_format="%0",
                indent_first_line=Dimension(magnitude=18, unit="PT"),
                indent_start=Dimension(magnitude=36, unit="PT"),
                start_number=1,
                text_style=TextStyle(underline=False),
            )
        ]
    )
)

_NUMBERED_LIST_DEF = DocList(
    list_properties=ListProperties(
        nesting_levels=[
            NestingLevel(
                bullet_alignment="START",
                glyph_type="DECIMAL",
                glyph_format="%0.",
                indent_first_line=Dimension(magnitude=18, unit="PT"),
                indent_start=Dimension(magnitude=36, unit="PT"),
                start_number=1,
                text_style=TextStyle(underline=False),
            )
        ]
    )
)


# ---------------------------------------------------------------------------
# Helper: build docs with bullets
# ---------------------------------------------------------------------------


def make_bullet_para(
    text: str,
    list_id: str = "list1",
    nesting_level: int = 0,
) -> StructuralElement:
    """Return a paragraph element with a bullet."""
    if not text.endswith("\n"):
        text = text + "\n"
    bullet = Bullet(list_id=list_id)
    if nesting_level > 0:
        bullet = Bullet(list_id=list_id, nesting_level=nesting_level)
    il = 18 + nesting_level * 36
    is_ = 36 + nesting_level * 36
    return StructuralElement(
        paragraph=Paragraph(
            elements=[ParagraphElement(text_run=TextRun(content=text))],
            bullet=bullet,
            paragraph_style=ParagraphStyle(
                named_style_type="NORMAL_TEXT",
                indent_first_line=Dimension(magnitude=il, unit="PT"),
                indent_start=Dimension(magnitude=is_, unit="PT"),
            ),
        )
    )


def make_indexed_bullet_para(
    text: str,
    start: int,
    list_id: str = "list1",
    nesting_level: int = 0,
) -> StructuralElement:
    """Return an indexed paragraph element with a bullet."""
    from extradoc.indexer import utf16_len

    if not text.endswith("\n"):
        text = text + "\n"
    end = start + utf16_len(text)
    bullet = Bullet(list_id=list_id)
    if nesting_level > 0:
        bullet = Bullet(list_id=list_id, nesting_level=nesting_level)
    il = 18 + nesting_level * 36
    is_ = 36 + nesting_level * 36
    return StructuralElement(
        start_index=start,
        end_index=end,
        paragraph=Paragraph(
            elements=[ParagraphElement(text_run=TextRun(content=text))],
            bullet=bullet,
            paragraph_style=ParagraphStyle(
                named_style_type="NORMAL_TEXT",
                indent_first_line=Dimension(magnitude=il, unit="PT"),
                indent_start=Dimension(magnitude=is_, unit="PT"),
            ),
        ),
    )


def make_doc_with_lists(
    tab_id: str,
    body_content: list[StructuralElement],
    lists: dict[str, DocList],
) -> Document:
    """Build a document with explicit body content and lists."""
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


def _get_insert_text_requests(reqs: list[Request]) -> list[Request]:
    return [r for r in reqs if r.insert_text is not None]


def _get_create_bullets_requests(reqs: list[Request]) -> list[Request]:
    return [r for r in reqs if r.create_paragraph_bullets is not None]


def _get_delete_bullets_requests(reqs: list[Request]) -> list[Request]:
    return [r for r in reqs if r.delete_paragraph_bullets is not None]


def _get_update_para_style_requests(reqs: list[Request]) -> list[Request]:
    return [r for r in reqs if r.update_paragraph_style is not None]


def _get_delete_content_requests(reqs: list[Request]) -> list[Request]:
    return [r for r in reqs if r.delete_content_range is not None]


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
        preset = bullet_reqs[0].create_paragraph_bullets.bullet_preset
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
        texts_inserted = [r.insert_text.text for r in insert_reqs]
        assert any(t.startswith("\t") for t in texts_inserted), (
            f"Expected leading tab in one of: {texts_inserted}"
        )

    def test_add_bullet_nested_level_2(self) -> None:
        """Desired has bullet paragraph at nesting_level=2 -> two leading tabs."""
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
        texts_inserted = [r.insert_text.text for r in insert_reqs]
        assert any(t.startswith("\t\t") for t in texts_inserted), (
            f"Expected two leading tabs in one of: {texts_inserted}"
        )

    def test_mixed_nested_ordered_then_bullet(self) -> None:
        """Insert an ordered nested list followed by a bullet nested list.

        Regression: _emit_same_position_group must account for tabs stripped
        by an earlier createParagraphBullets when computing the start index
        of the next createParagraphBullets and when shifting style-request
        ranges.  Before the fix, the second createParagraphBullets ran off
        the end of the segment because its range still counted bytes the
        first call had already stripped.
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
                # Ordered list with a nested item
                make_bullet_para("Apple\n", list_id="ord", nesting_level=0),
                make_bullet_para("Fuji\n", list_id="ord", nesting_level=1),
                make_bullet_para("Gala\n", list_id="ord", nesting_level=1),
                make_bullet_para("Cherry\n", list_id="ord", nesting_level=0),
                # Bullet list with a nested item
                make_bullet_para("Red\n", list_id="blt", nesting_level=0),
                make_bullet_para("Crimson\n", list_id="blt", nesting_level=1),
                make_bullet_para("Blue\n", list_id="blt", nesting_level=0),
                make_terminal_para(),
            ],
            lists={"ord": _NUMBERED_LIST_DEF, "blt": _BULLET_LIST_DEF},
        )

        reqs = reconcile(base, desired)

        bullet_reqs = _get_create_bullets_requests(reqs)
        # One merged call per distinct preset
        assert len(bullet_reqs) == 2
        presets = [r.create_paragraph_bullets.bullet_preset for r in bullet_reqs]
        assert presets == ["NUMBERED_DECIMAL_NESTED", "BULLET_DISC_CIRCLE_SQUARE"]

        # The two ranges must be contiguous in POST-STRIP coordinates: the
        # second run's start_index equals the first run's end_index minus the
        # number of tabs the first run strips.
        ord_range = bullet_reqs[0].create_paragraph_bullets.range
        blt_range = bullet_reqs[1].create_paragraph_bullets.range
        # Ordered run: "Apple\n" (6) + "\tFuji\n" (6) + "\tGala\n" (6) +
        # "Cherry\n" (7) = 25 chars, 2 leading tabs to strip.
        assert ord_range.start_index == 1
        assert ord_range.end_index == 26
        # Bullet run post-strip start = 26 - 2 = 24.
        # Pre-strip-of-own-run length: "Red\n" (4) + "\tCrimson\n" (9) +
        # "Blue\n" (5) = 18.
        assert blt_range.start_index == 24
        assert blt_range.end_index == 24 + 18

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
        preset = bullet_reqs[0].create_paragraph_bullets.bullet_preset
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
        assert len(delete_bullet_reqs) == 1, (
            f"Expected deleteParagraphBullets, got: {reqs}"
        )

        # Should also clear indentation
        para_style_reqs = _get_update_para_style_requests(reqs)
        assert any(
            r.update_paragraph_style.fields is not None
            and (
                "indentStart" in r.update_paragraph_style.fields
                or "indentFirstLine" in r.update_paragraph_style.fields
            )
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

        assert len(delete_bullet_reqs) == 1, (
            f"Expected deleteParagraphBullets, got: {reqs}"
        )
        assert len(create_bullet_reqs) == 1, (
            f"Expected createParagraphBullets, got: {reqs}"
        )


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
        """Identical bullet paragraph in base and desired -> no requests."""
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

        assert reqs == [], (
            f"Expected no requests for identical bullet docs, got: {reqs}"
        )


# ===========================================================================
# Test 5: Text edit in bullet paragraph
# ===========================================================================


class TestBulletTextEdit:
    """Text changes within bullet paragraphs."""

    def test_bullet_text_edit(self) -> None:
        """Matched bullet paragraph, same bullet, different text.

        Assert: text diff requests only (no bullet requests -- bullet unchanged).
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

        # Should NOT have createParagraphBullets -- bullet is unchanged
        assert _get_create_bullets_requests(reqs) == [], (
            f"Expected no createParagraphBullets for same-bullet text edit, got: {reqs}"
        )
        # Should NOT have deleteParagraphBullets
        assert _get_delete_bullets_requests(reqs) == [], (
            f"Expected no deleteParagraphBullets, got: {reqs}"
        )
        # Should have some text modification request
        assert len(reqs) > 0, "Should have at least one request for text change"


# ===========================================================================
# Test 6: _diff_lists fix -- no UpdateListOp
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
                "list1": DocList(
                    list_properties=ListProperties(
                        nesting_levels=[NestingLevel(glyph_symbol="\u25cf")]
                    )
                )
            },
        )
        desired = make_doc_with_lists(
            "t1",
            body_content=[make_terminal_para()],
            lists={
                "list1": DocList(
                    list_properties=ListProperties(
                        nesting_levels=[
                            NestingLevel(
                                glyph_symbol="\u25cf",
                                bullet_alignment="START",
                                indent_first_line=Dimension(magnitude=18, unit="PT"),
                                indent_start=Dimension(magnitude=36, unit="PT"),
                            )
                        ]
                    )
                )
            },
        )

        # With the old code, this would raise NotImplementedError via UpdateListOp.
        # With the fix, it should return empty ops (no list change to lower).
        ops = diff(base, desired)
        update_list_ops = [op for op in ops if isinstance(op, UpdateListOp)]
        assert update_list_ops == [], (
            f"Expected no UpdateListOp, got: {update_list_ops}"
        )

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
    """_infer_bullet_preset_from_model correctly maps list defs to preset strings."""

    def test_disc_bullet_preset(self) -> None:
        """glyphSymbol '\u25cf' -> BULLET_DISC_CIRCLE_SQUARE."""
        from extradoc.reconcile_v3.lower import _infer_bullet_preset_from_model

        bullet = Bullet(list_id="list1")
        lists = {
            "list1": DocList(
                list_properties=ListProperties(
                    nesting_levels=[NestingLevel(glyph_symbol="\u25cf")]
                )
            )
        }
        assert (
            _infer_bullet_preset_from_model(bullet, lists)
            == "BULLET_DISC_CIRCLE_SQUARE"
        )

    def test_decimal_numbered_preset(self) -> None:
        """glyphType 'DECIMAL' -> NUMBERED_DECIMAL_NESTED."""
        from extradoc.reconcile_v3.lower import _infer_bullet_preset_from_model

        bullet = Bullet(list_id="list1")
        lists = {
            "list1": DocList(
                list_properties=ListProperties(
                    nesting_levels=[NestingLevel(glyph_type="DECIMAL")]
                )
            )
        }
        assert (
            _infer_bullet_preset_from_model(bullet, lists) == "NUMBERED_DECIMAL_NESTED"
        )

    def test_checkbox_preset(self) -> None:
        """glyphType 'GLYPH_TYPE_UNSPECIFIED' -> BULLET_CHECKBOX."""
        from extradoc.reconcile_v3.lower import _infer_bullet_preset_from_model

        bullet = Bullet(list_id="list1")
        lists = {
            "list1": DocList(
                list_properties=ListProperties(
                    nesting_levels=[NestingLevel(glyph_type="GLYPH_TYPE_UNSPECIFIED")]
                )
            )
        }
        assert _infer_bullet_preset_from_model(bullet, lists) == "BULLET_CHECKBOX"

    def test_missing_list_falls_back_to_disc(self) -> None:
        """Missing list_id -> BULLET_DISC_CIRCLE_SQUARE fallback."""
        from extradoc.reconcile_v3.lower import _infer_bullet_preset_from_model

        bullet = Bullet(list_id="missing_list")
        assert (
            _infer_bullet_preset_from_model(bullet, {}) == "BULLET_DISC_CIRCLE_SQUARE"
        )

    def test_empty_lists_falls_back_to_disc(self) -> None:
        """No lists dict -> BULLET_DISC_CIRCLE_SQUARE fallback."""
        from extradoc.reconcile_v3.lower import _infer_bullet_preset_from_model

        bullet = Bullet(list_id="list1")
        assert (
            _infer_bullet_preset_from_model(bullet, {}) == "BULLET_DISC_CIRCLE_SQUARE"
        )


# ===========================================================================
# Regression: text edit inside one item of a multi-item numbered list
# should NOT fragment the list (no delete/createParagraphBullets emitted).
# ===========================================================================


class TestNumberedListTextEditNoFragmentation:
    """Editing only the text of one item in a numbered list must not touch bullets."""

    def test_edit_item4_text_only_emits_no_bullet_requests(self, tmp_path) -> None:
        """Simulates the real pull->edit->push pipeline via MarkdownSerde.

        Build a document with a numbered list, serialize to markdown, edit a
        single list item's text in the markdown file, deserialize, then run
        reconcile. The generated requests should contain only text edits --
        no bullet add/remove requests.
        """
        from extradoc.comments._types import DocumentWithComments, FileComments
        from extradoc.indexer import utf16_len
        from extradoc.serde.markdown import MarkdownSerde

        items = ["Headings", "Lists", "Links", "Images", "Tables"]

        # Build base with indexed numbered-list paragraphs starting at 1.
        base_body: list[StructuralElement] = []
        idx = 1
        for text in items:
            base_body.append(
                make_indexed_bullet_para(
                    text + "\n", idx, list_id="list1", nesting_level=0
                )
            )
            idx += utf16_len(text + "\n")
        base_body.append(make_indexed_terminal(idx))
        base_doc = make_doc_with_lists(
            "t1",
            body_content=base_body,
            lists={"list1": _NUMBERED_LIST_DEF},
        )
        base_doc.document_id = "testdoc"

        serde = MarkdownSerde()
        bundle = DocumentWithComments(
            document=base_doc,
            comments=FileComments(file_id="testdoc"),
        )
        serde.serialize(bundle, tmp_path)

        # Edit only item 4's text in the tab markdown file.
        edited = False
        for md_path in tmp_path.rglob("*.md"):
            if "tabs" not in str(md_path):
                continue
            content = md_path.read_text()
            if "4. Images" in content:
                md_path.write_text(
                    content.replace("4. Images", "4. Images and Figures")
                )
                edited = True
        assert edited, "Expected to find '4. Images' in the serialized markdown"

        result = serde.deserialize(tmp_path)
        reqs = reconcile(result.base.document, result.desired.document)

        # Core bug assertion: no bullet add/remove requests should be emitted
        # for a pure text edit inside a matched bullet paragraph.
        assert _get_create_bullets_requests(reqs) == [], (
            f"Expected no createParagraphBullets for pure text edit, got: {reqs}"
        )
        assert _get_delete_bullets_requests(reqs) == [], (
            f"Expected no deleteParagraphBullets for pure text edit, got: {reqs}"
        )

        # Strengthening: the only non-trivial requests should be text edits.
        non_text_reqs = [
            r for r in reqs if r.insert_text is None and r.delete_content_range is None
        ]
        assert non_text_reqs == [], (
            f"Expected only insertText/deleteContentRange requests, got extras: "
            f"{non_text_reqs}"
        )
