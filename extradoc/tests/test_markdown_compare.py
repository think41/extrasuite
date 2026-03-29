from __future__ import annotations

from extradoc.markdown_compare import compare_markdown_tabs


def test_compare_markdown_tabs_reports_identical_docs_as_matching() -> None:
    tabs = {
        "Tab_1": "# Title\n\nAlpha paragraph.\n",
        "Second_Tab": "- one\n- two\n",
    }

    result = compare_markdown_tabs(tabs, tabs)

    assert result.matching is True
    assert result.missing_tabs == ()
    assert result.extra_tabs == ()
    assert result.semantic_edits == ()
    assert result.tab_diffs == {}


def test_compare_markdown_tabs_reports_semantic_heading_change() -> None:
    desired = {"Tab_1": "# Title\n\nAlpha paragraph.\n"}
    actual = {"Tab_1": "Title\n\nAlpha paragraph.\n"}

    result = compare_markdown_tabs(desired, actual)

    assert result.matching is False
    assert result.semantic_edits == (
        "tab t.0: section 0 block 0 role NORMAL_TEXT -> HEADING_1",
    )
    assert "Tab_1" in result.tab_diffs


def test_compare_markdown_tabs_reports_missing_and_extra_tabs() -> None:
    desired = {
        "Tab_1": "Alpha\n",
        "Second_Tab": "Bravo\n",
    }
    actual = {
        "Tab_1": "Alpha\n",
        "Third_Tab": "Charlie\n",
    }

    result = compare_markdown_tabs(desired, actual)

    assert result.matching is False
    assert result.missing_tabs == ("Second_Tab",)
    assert result.extra_tabs == ("Third_Tab",)
    assert result.semantic_edits == ()


def test_compare_markdown_tabs_is_independent_of_tab_dict_order() -> None:
    desired = {
        "Tab_1": "# Title\n\nAlpha paragraph.\n",
        "Second_Tab": "Bravo\n",
    }
    actual = {
        "Second_Tab": "Bravo\n",
        "Tab_1": "# Title\n\nAlpha paragraph.\n",
    }

    result = compare_markdown_tabs(desired, actual)

    assert result.matching is True
    assert result.semantic_edits == ()


def test_compare_markdown_tabs_normalizes_footnote_labels_semantically() -> None:
    desired = {
        "Tab_1": "Alpha with note.[^overview-note]\n\n[^overview-note]: Footnote text.\n",
    }
    actual = {
        "Tab_1": "Alpha with note.[^kix.123]\n\n[^kix.123]: Footnote text.\n",
    }

    result = compare_markdown_tabs(desired, actual)

    assert result.matching is True
    assert result.semantic_edits == ()
    assert "Tab_1" in result.tab_diffs
