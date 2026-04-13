"""Regression test: nested list items separated by colored empty paragraphs.

Bug discovered in QA of CAPLAW Sample Shared Services Agreement (2026-04-10):

Google Docs often inserts invisible colored empty paragraphs between sibling
list items. On pull, `_to_markdown` emits these as `<!-- -->` HTML-block
placeholders at column 0. On the next parse, mistletoe treats `<!-- -->` as an
HTML block that CLOSES the surrounding list; the following 4-space-indented
sub-item (`    1. Text`) then becomes an *indented code block* (BlockCode),
which `_parse_body` has no handler for — the content is silently dropped.

Symptom: edits made inside nested list sub-items are reflected in the local
`Tab_1.md` file, but `MarkdownSerde.deserialize()` returns the old text (the
edit never reaches the `desired` document), and push produces no batchUpdate
for those ranges. The push reports success but the document is unchanged.

This file tests the bug at the serde layer, end-to-end, using a hand-built
document that models the failing structure (top-level list item containing
nested sub-items separated by colored empty paragraphs).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from extradoc.api_types._generated import Document
from extradoc.comments._types import DocumentWithComments, FileComments
from extradoc.serde.markdown import MarkdownSerde


def _colored_empty_para() -> dict:
    """An invisible colored empty paragraph — the kind Google Docs inserts
    between sibling list items. Has exactly one text run containing '\\n'
    with a foregroundColor override."""
    return {
        "paragraph": {
            "elements": [
                {
                    "textRun": {
                        "content": "\n",
                        "textStyle": {
                            "foregroundColor": {
                                "color": {
                                    "rgbColor": {
                                        "red": 0.2,
                                        "green": 0.2,
                                        "blue": 0.2,
                                    }
                                }
                            }
                        },
                    }
                }
            ],
            "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
        }
    }


def _list_item(text: str, nesting: int) -> dict:
    return {
        "paragraph": {
            "elements": [{"textRun": {"content": text, "textStyle": {}}}],
            "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
            "bullet": {"listId": "L1", "nestingLevel": nesting},
        }
    }


def _build_doc() -> Document:
    """A top-level list item with 3 nested sub-items separated by colored
    empty paragraphs — mirroring the CAPLAW contract structure."""
    content: list[dict] = [
        {"sectionBreak": {"sectionStyle": {}}},
        _list_item("TERMINATION.\n", nesting=0),
        _colored_empty_para(),
        _list_item(
            "Termination for Convenience.  Either Party may terminate this "
            "Agreement by providing ninety (90) days written notice.\n",
            nesting=1,
        ),
        _colored_empty_para(),
        _list_item(
            "Immediate Termination.  Either Party may terminate immediately "
            "upon material breach.\n",
            nesting=1,
        ),
        _colored_empty_para(),
        _list_item(
            "Governing Law.  This Agreement shall be governed by the laws of "
            "the State of X.\n",
            nesting=1,
        ),
    ]
    doc_dict = {
        "documentId": "testdoc",
        "title": "Test",
        "tabs": [
            {
                "tabProperties": {"tabId": "t.0", "title": "Tab 1", "index": 0},
                "documentTab": {
                    "body": {"content": content},
                    "lists": {
                        "L1": {
                            "listProperties": {
                                "nestingLevels": [
                                    {
                                        "glyphType": "DECIMAL",
                                        "indentFirstLine": {
                                            "magnitude": 18,
                                            "unit": "PT",
                                        },
                                        "indentStart": {
                                            "magnitude": 36,
                                            "unit": "PT",
                                        },
                                    },
                                    {
                                        "glyphType": "DECIMAL",
                                        "indentFirstLine": {
                                            "magnitude": 54,
                                            "unit": "PT",
                                        },
                                        "indentStart": {
                                            "magnitude": 72,
                                            "unit": "PT",
                                        },
                                    },
                                ]
                            }
                        }
                    },
                },
            }
        ],
    }
    return Document.model_validate(doc_dict)


def _para_texts(doc: Document) -> list[str]:
    out: list[str] = []
    for tab in doc.tabs or []:
        for se in tab.document_tab.body.content or []:  # type: ignore[union-attr]
            if se.paragraph:
                text = "".join(
                    (pe.text_run.content or "")
                    for pe in (se.paragraph.elements or [])
                    if pe.text_run
                )
                out.append(text)
    return out


def test_edit_inside_nested_list_sub_item_reaches_desired(tmp_path: Path) -> None:
    """Editing a nested list sub-item's text must be reflected in desired.

    Regression guard for the `<!-- -->` list-breaking bug described in the
    module docstring.
    """
    doc = _build_doc()
    bundle = DocumentWithComments(
        document=doc, comments=FileComments(file_id="testdoc")
    )
    serde = MarkdownSerde()

    folder = tmp_path / "doc"
    serde.serialize(bundle, folder)

    tab_path = folder / "tabs" / "Tab_1.md"
    md = tab_path.read_text()

    # Make three realistic edits inside nested sub-items — one in each.
    md = md.replace("ninety (90)", "sixty (60)")
    md = md.replace("Immediate Termination", "Immediate Termination for Cause")
    md = md.replace("State of X", "State of Oregon")
    tab_path.write_text(md)

    result = serde.deserialize(folder)
    texts = " ".join(_para_texts(result.desired.document))

    # Each edit must have made it into the desired document.
    assert "sixty (60)" in texts, (
        "Edit inside first nested sub-item was lost: 'ninety (90)' → 'sixty (60)'"
    )
    assert "Immediate Termination for Cause" in texts, (
        "Edit inside second nested sub-item was lost"
    )
    assert "State of Oregon" in texts, (
        "Edit inside third nested sub-item was lost: 'State of X' → 'State of Oregon'"
    )

    # And the original text must be gone (edits replaced, not appended).
    assert "ninety (90)" not in texts
    assert "State of X" not in texts


# ---------------------------------------------------------------------------
# Known cosmetic bugs (xfail) — adjacent-run consolidation on serialize
# ---------------------------------------------------------------------------
#
# When a paragraph has multiple text runs with IDENTICAL styles, the
# markdown serializer closes and re-opens the formatting delimiters at each
# run boundary, producing visually ugly output that accumulates across
# round-trips:
#
#   ``**AGREEMENT TERM**.**``  →  serialized as  ``**AGREEMENT TERM****.**``
#   ``<u>RFS</u>``             →  serialized as  ``<u>R</u><u>FS</u>``
#
# The fix is to consolidate adjacent same-style runs before serializing (or
# to look across run boundaries when deciding where to place delimiters).
# Not fixed yet — tracked via these xfail tests.
# ---------------------------------------------------------------------------


def _make_para_with_runs(runs: list[tuple[str, dict]]) -> dict:
    """Build a paragraph dict with the given (text, textStyle) runs."""
    elements = [
        {"textRun": {"content": content, "textStyle": style}} for content, style in runs
    ]
    elements.append({"textRun": {"content": "\n", "textStyle": {}}})
    return {
        "paragraph": {
            "elements": elements,
            "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
        }
    }


def _serialize_doc(content: list[dict], tmp_path: Path) -> str:
    doc = Document.model_validate(
        {
            "documentId": "t",
            "title": "t",
            "tabs": [
                {
                    "tabProperties": {
                        "tabId": "t.0",
                        "title": "Tab 1",
                        "index": 0,
                    },
                    "documentTab": {
                        "body": {
                            "content": [
                                {"sectionBreak": {"sectionStyle": {}}},
                                *content,
                            ]
                        }
                    },
                }
            ],
        }
    )
    bundle = DocumentWithComments(document=doc, comments=FileComments(file_id="t"))
    folder = tmp_path / "doc"
    MarkdownSerde().serialize(bundle, folder)
    return (folder / "tabs" / "Tab_1.md").read_text()


def test_edit_nested_list_item_without_l0_parent_reaches_desired(
    tmp_path: Path,
) -> None:
    """Editing a nesting_level=1 list item that has no nesting_level=0 sibling
    directly above it (only another nesting_level=1 sibling separated by a
    colored empty paragraph) must be reflected in desired.

    Concrete structure:
        [colored empty para]        <- serialized as <!-- --> at col 0 (not in list yet)
        (a) Payment Terms           <- nesting_level=1
        [colored empty para]        <- serialized as '        <!-- -->' (8 spaces)
        (b) Taxes; Original Text    <- nesting_level=1 -- EDIT THIS

    The 8-space-indented <!-- --> causes CommonMark to parse the following
    4-space-indented '    2. Taxes' as a BlockCode, dropping the content.
    """
    doc_dict = {
        "documentId": "testdoc",
        "title": "Test",
        "tabs": [
            {
                "tabProperties": {"tabId": "t.0", "title": "Tab 1", "index": 0},
                "documentTab": {
                    "body": {
                        "content": [
                            {"sectionBreak": {"sectionStyle": {}}},
                            # No nesting_level=0 item — jump straight to level 1.
                            _list_item("Payment Terms\n", nesting=1),
                            _colored_empty_para(),
                            _list_item("Taxes; Original Text\n", nesting=1),
                        ]
                    },
                    "lists": {
                        "L1": {
                            "listProperties": {
                                "nestingLevels": [
                                    {
                                        "glyphType": "DECIMAL",
                                        "indentFirstLine": {
                                            "magnitude": 18,
                                            "unit": "PT",
                                        },
                                        "indentStart": {
                                            "magnitude": 36,
                                            "unit": "PT",
                                        },
                                    },
                                    {
                                        "glyphType": "DECIMAL",
                                        "indentFirstLine": {
                                            "magnitude": 54,
                                            "unit": "PT",
                                        },
                                        "indentStart": {
                                            "magnitude": 72,
                                            "unit": "PT",
                                        },
                                    },
                                ]
                            }
                        }
                    },
                },
            }
        ],
    }
    doc = Document.model_validate(doc_dict)
    bundle = DocumentWithComments(
        document=doc, comments=FileComments(file_id="testdoc")
    )
    serde = MarkdownSerde()

    folder = tmp_path / "doc"
    serde.serialize(bundle, folder)

    tab_path = folder / "tabs" / "Tab_1.md"
    md = tab_path.read_text()
    md = md.replace("Taxes; Original Text", "Taxes; Edited Text")
    tab_path.write_text(md)

    result = serde.deserialize(folder)
    texts = " ".join(_para_texts(result.desired.document))

    assert "Taxes; Edited Text" in texts, (
        "Edit inside nesting_level=1 item (no L0 sibling above) was silently "
        "dropped: 'Taxes; Original Text' → 'Taxes; Edited Text' not found in desired"
    )
    assert "Taxes; Original Text" not in texts


def test_adjacent_bold_runs_consolidate(tmp_path: Path) -> None:
    """Two adjacent bold runs should serialize as a single **...** span."""
    bold = {"bold": True}
    # "AGREEMENT TERM" bold + "." bold — both same style, should merge.
    para = _make_para_with_runs([("AGREEMENT TERM", bold), (".", bold)])
    md = _serialize_doc([para], tmp_path)
    assert "****" not in md, f"Got '****' artifact in output:\n{md}"
    assert "**AGREEMENT TERM.**" in md


def test_adjacent_underline_runs_consolidate(tmp_path: Path) -> None:
    """Two adjacent underlined runs should serialize as a single <u>...</u>."""
    underline = {"underline": True}
    para = _make_para_with_runs([("R", underline), ("FS", underline)])
    md = _serialize_doc([para], tmp_path)
    assert "</u><u>" not in md, f"Got '</u><u>' artifact in output:\n{md}"
    assert "<u>RFS</u>" in md
