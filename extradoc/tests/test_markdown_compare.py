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
