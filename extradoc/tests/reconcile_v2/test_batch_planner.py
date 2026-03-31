from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

import extradoc.serde as serde
from extradoc.api_types._generated import BatchUpdateDocumentRequest, Document
from extradoc.client import _normalize_raw_base_para_styles
from extradoc.mock.api import MockGoogleDocsAPI
from extradoc.reconcile import reindex_document
from extradoc.reconcile_v2.api import lower_semantic_diff_batches, reconcile
from extradoc.reconcile_v2.batches import _body_carrier_style_reset_requests
from extradoc.reconcile_v2.errors import UnsupportedSpikeError
from extradoc.reconcile_v2.executor import resolve_deferred_placeholders
from extradoc.serde._from_markdown import markdown_to_document

from .helpers import (
    load_expected_lowered_batches,
    load_fixture_pair,
)


def test_create_tab_table_write_batches_match_fixture() -> None:
    base, desired = load_fixture_pair("create_tab_table_write")

    assert lower_semantic_diff_batches(base, desired) == load_expected_lowered_batches(
        "create_tab_table_write"
    )


def test_create_tab_nested_table_write_batches_match_fixture() -> None:
    base, desired = load_fixture_pair("create_tab_nested_table_write")

    assert lower_semantic_diff_batches(base, desired) == load_expected_lowered_batches(
        "create_tab_nested_table_write"
    )


def test_create_tab_named_range_write_batches_match_fixture() -> None:
    base, desired = load_fixture_pair("create_tab_named_range_write")

    assert lower_semantic_diff_batches(base, desired) == load_expected_lowered_batches(
        "create_tab_named_range_write"
    )


def test_create_parent_child_tab_write_batches_match_fixture() -> None:
    base, desired = load_fixture_pair("create_parent_child_tab_write")

    assert lower_semantic_diff_batches(base, desired) == load_expected_lowered_batches(
        "create_parent_child_tab_write"
    )


def test_create_tab_footnote_write_batches_match_fixture() -> None:
    base, desired = load_fixture_pair("create_tab_footnote_write")

    assert lower_semantic_diff_batches(base, desired) == load_expected_lowered_batches(
        "create_tab_footnote_write"
    )


def test_create_tab_named_range_footnote_write_batches_match_fixture() -> None:
    base, desired = load_fixture_pair("create_tab_named_range_footnote_write")

    assert lower_semantic_diff_batches(base, desired) == load_expected_lowered_batches(
        "create_tab_named_range_footnote_write"
    )


def test_section_create_distinct_header_batches_match_fixture() -> None:
    base, desired = load_fixture_pair("section_create_distinct_header")

    assert lower_semantic_diff_batches(base, desired) == load_expected_lowered_batches(
        "section_create_distinct_header"
    )


def test_section_create_footer_batches_match_fixture() -> None:
    base, desired = load_fixture_pair("section_create_footer")

    assert lower_semantic_diff_batches(base, desired) == load_expected_lowered_batches(
        "section_create_footer"
    )


def test_footnote_create_write_batches_match_fixture() -> None:
    base, desired = load_fixture_pair("footnote_create_write")

    assert lower_semantic_diff_batches(base, desired) == load_expected_lowered_batches(
        "footnote_create_write"
    )


def test_markdown_footnote_insert_from_empty_doc_batches_content_then_footnote() -> None:
    base = reindex_document(
        markdown_to_document(
            {"Tab_1": ""},
            document_id="md-footnote-empty",
            title="Markdown Footnote",
            tab_ids={"Tab_1": "t.0"},
        )
    )
    desired = reindex_document(
        markdown_to_document(
            {
                "Tab_1": (
                    "Paragraph with footnote.[^note]\n\n"
                    "[^note]: Footnote body text.\n"
                )
            },
            document_id="md-footnote-empty",
            title="Markdown Footnote",
            tab_ids={"Tab_1": "t.0"},
        )
    )

    batches = lower_semantic_diff_batches(base, desired)

    assert len(batches) == 3
    assert batches[0] == [
        {
            "insertText": {
                "location": {"index": 1, "tabId": "t.0"},
                "text": "Paragraph with footnote.",
            }
        }
    ]
    assert "createFootnote" in batches[1][0]
    assert batches[2] == [
        {
            "insertText": {
                "location": {
                    "tabId": "t.0",
                    "segmentId": {
                        "placeholder": "footnote-t.0-0-0",
                        "batch_index": 1,
                        "request_index": 0,
                        "response_path": "createFootnote.footnoteId",
                    },
                    "index": 0,
                },
                "text": "Footnote body text.",
            }
        }
    ]


def test_markdown_special_tables_from_empty_doc_split_table_followups() -> None:
    base = reindex_document(
        markdown_to_document(
            {"Tab_1": ""},
            document_id="md-special-table-split",
            title="Markdown Special Table Split",
            tab_ids={"Tab_1": "t.0"},
        )
    )
    desired = reindex_document(
        markdown_to_document(
            {
                "Tab_1": (
                    "> [!INFO]\n"
                    "> Info callout.\n\n"
                    "> Plain blockquote.\n\n"
                    "```json\n"
                    "{\"ok\": true}\n"
                    "```\n"
                )
            },
            document_id="md-special-table-split",
            title="Markdown Special Table Split",
            tab_ids={"Tab_1": "t.0"},
        )
    )

    batches = lower_semantic_diff_batches(base, desired)

    assert len(batches) >= 2
    assert any("insertTable" in request for request in batches[0])
    assert all("insertTable" not in request for request in batches[1][0:1])
    assert not any(
        kind in {"createParagraphBullets", "updateParagraphStyle"}
        for request in batches[0]
        for kind in request
    )
    assert any(
        any(
            kind in {"updateTableCellStyle", "createNamedRange"}
            for request in batch
            for kind in request
        )
        for batch in batches[1:]
    )


def test_create_tab_batches_ignore_desired_future_tab_id() -> None:
    base, desired = load_fixture_pair("create_tab_table_write")
    desired_raw = desired.model_dump(by_alias=True, exclude_none=True)
    desired_raw["tabs"][1]["tabProperties"]["tabId"] = "future.invalid.tab"
    desired_future_id = Document.model_validate(desired_raw)

    assert lower_semantic_diff_batches(base, desired_future_id) == load_expected_lowered_batches(
        "create_tab_table_write"
    )


def test_create_tab_batches_ignore_desired_new_tab_transport_indices() -> None:
    base, desired = load_fixture_pair("create_tab_table_write")
    desired_raw = desired.model_dump(by_alias=True, exclude_none=True)
    _strip_indices(desired_raw["tabs"][1]["documentTab"]["body"]["content"])
    desired_without_indices = Document.model_validate(desired_raw)

    assert lower_semantic_diff_batches(
        base,
        desired_without_indices,
    ) == load_expected_lowered_batches("create_tab_table_write")


def test_create_tab_named_range_batches_ignore_desired_future_tab_id() -> None:
    base, desired = load_fixture_pair("create_tab_named_range_write")
    desired_raw = desired.model_dump(by_alias=True, exclude_none=True)
    desired_raw["tabs"][1]["tabProperties"]["tabId"] = "future.invalid.tab"
    desired_future_id = Document.model_validate(desired_raw)

    assert lower_semantic_diff_batches(base, desired_future_id) == load_expected_lowered_batches(
        "create_tab_named_range_write"
    )


def test_create_parent_child_batches_ignore_desired_future_tab_ids() -> None:
    base, desired = load_fixture_pair("create_parent_child_tab_write")
    desired_raw = desired.model_dump(by_alias=True, exclude_none=True)
    desired_raw["tabs"][1]["tabProperties"]["tabId"] = "future.parent.tab"
    desired_raw["tabs"][1]["childTabs"][0]["tabProperties"]["tabId"] = "future.child.tab"
    desired_future_id = Document.model_validate(desired_raw)

    assert lower_semantic_diff_batches(base, desired_future_id) == load_expected_lowered_batches(
        "create_parent_child_tab_write"
    )


def test_create_tab_footnote_batches_ignore_desired_future_tab_and_footnote_ids() -> None:
    base, desired = load_fixture_pair("create_tab_footnote_write")
    desired_raw = desired.model_dump(by_alias=True, exclude_none=True)
    desired_raw["tabs"][1]["tabProperties"]["tabId"] = "future.footnote.tab"
    footnotes = desired_raw["tabs"][1]["documentTab"]["footnotes"]
    footnote_id = next(iter(footnotes))
    footnote = footnotes.pop(footnote_id)
    footnote["footnoteId"] = "future.footnote.segment"
    footnotes["future.footnote.segment"] = footnote
    for element in desired_raw["tabs"][1]["documentTab"]["body"]["content"]:
        paragraph = element.get("paragraph")
        if not paragraph:
            continue
        for child in paragraph.get("elements", []):
            footnote_ref = child.get("footnoteReference")
            if footnote_ref:
                footnote_ref["footnoteId"] = "future.footnote.segment"
    desired_future_id = Document.model_validate(desired_raw)

    assert lower_semantic_diff_batches(base, desired_future_id) == load_expected_lowered_batches(
        "create_tab_footnote_write"
    )


def test_create_new_tab_with_mixed_markdown_body_is_supported() -> None:
    base = reindex_document(
        markdown_to_document(
            {"Tab_1": "alpha\n"},
            document_id="new-tab-mixed-body",
            title="New Tab Mixed Body",
            tab_ids={"Tab_1": "t.0"},
        )
    )
    desired = reindex_document(
        markdown_to_document(
            {
                "Tab_1": "alpha\n",
                "Second_Tab": (
                    "# Heading\n\n"
                    "Lead paragraph.\n\n"
                    "- bullet one\n"
                    "- bullet two\n\n"
                    "```python\n"
                    "print('ok')\n"
                    "```\n"
                ),
            },
            document_id="new-tab-mixed-body",
            title="New Tab Mixed Body",
            tab_ids={"Tab_1": "t.0", "Second_Tab": "t.future"},
        )
    )

    batches = lower_semantic_diff_batches(base, desired)

    assert len(batches) >= 2
    assert "addDocumentTab" in batches[0][0]
    flattened = [request for batch in batches[1:] for request in batch]
    assert any("insertText" in request for request in flattened)
    assert any("insertTable" in request for request in flattened)
    assert any("createParagraphBullets" in request for request in flattened)
    assert any("updateParagraphStyle" in request for request in flattened)
    assert any("createNamedRange" in request for request in flattened)
    assert not any(
        "insertText" in request
        and request["insertText"]["location"].get("index") == 1
        and isinstance(request["insertText"]["text"], str)
        and request["insertText"]["text"].startswith("\n")
        for request in flattened
    )


def test_create_new_tab_with_note_callout_emits_special_named_range() -> None:
    base = reindex_document(
        markdown_to_document(
            {"Tab_1": "alpha\n"},
            document_id="new-tab-note-callout",
            title="New Tab Note Callout",
            tab_ids={"Tab_1": "t.0"},
        )
    )
    desired = reindex_document(
        markdown_to_document(
            {
                "Tab_1": "alpha\n",
                "Second_Tab": (
                    "# Workbench\n\n"
                    "## Quotes\n\n"
                    "> [!NOTE]\n"
                    "> Keep the note callout metadata on creation.\n"
                ),
            },
            document_id="new-tab-note-callout",
            title="New Tab Note Callout",
            tab_ids={"Tab_1": "t.0", "Second_Tab": "t.future"},
        )
    )

    flattened = [
        request
        for batch in lower_semantic_diff_batches(base, desired)
        for request in batch
    ]

    assert any(
        request.get("createNamedRange", {}).get("name") == "extradoc:callout:note"
        for request in flattened
    )


def test_iterative_batches_split_complex_live_table_backed_body_rewrite() -> None:
    fixture_root = (
        Path(__file__).resolve().parent / "fixtures" / "live_multitab_cycle2_probe"
    )
    transport_base = Document.model_validate(
        json.loads((fixture_root / "base.json").read_text(encoding="utf-8"))
    )
    base = Document.model_validate(
        json.loads((fixture_root / "base.json").read_text(encoding="utf-8"))
    )
    with tempfile.TemporaryDirectory() as tmp:
        desired_dir = Path(tmp)
        for path in (fixture_root / "desired").iterdir():
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")
            if path.name == "Tab_1.md":
                text = text.replace("\n---\n\n", "\n")
            (desired_dir / path.name).write_text(text, encoding="utf-8")
        desired_bundle = serde.deserialize(desired_dir)
    _normalize_raw_base_para_styles(base, desired_bundle.document)

    batches = lower_semantic_diff_batches(
        base,
        reindex_document(desired_bundle.document),
        transport_base=transport_base,
    )

    assert len(batches) > 1
    flattened = [request for batch in batches for request in batch]
    assert any(
        request.get("insertText", {}).get("text") == '    return "blue"'
        and request["insertText"]["location"].get("tabId") == "t.0"
        for request in flattened
    )
    assert any(
        request.get("insertText", {}).get("text") == '{"stage": "edited", "verified": false}'
        and request["insertText"]["location"].get("tabId") == "t.0"
        for request in flattened
    )
    assert sum(
        1
        for request in flattened
        if request.get("updateTextStyle", {}).get("textStyle", {}).get(
            "weightedFontFamily", {}
        ).get("fontFamily")
        == "Courier New"
        and request["updateTextStyle"]["range"].get("tabId") == "t.0"
    ) >= 2
    named_range_names = [
        request["createNamedRange"]["name"]
        for batch in batches
        for request in batch
        if "createNamedRange" in request
    ]
    assert {
        "extradoc:blockquote",
        "extradoc:callout:tip",
        "extradoc:callout:warning",
    }.issubset(named_range_names)
    assert batches[-2] == [
        {"createFootnote": {"location": {"index": 220, "tabId": "t.0"}}}
    ]

    current = transport_base
    prior_responses: list[dict[str, object]] = []
    for batch in batches:
        mock = MockGoogleDocsAPI(current)
        resolved_batch = resolve_deferred_placeholders(prior_responses, list(batch))
        response = mock._batch_update_raw(resolved_batch)
        prior_responses.append(response)
        current = mock.get()


def test_iterative_batches_accept_small_xml_live_residual_fallback() -> None:
    fixture_root = Path(__file__).resolve().parent / "fixtures" / "xml_live_cycle1_after_failure"
    base = Document.model_validate(
        json.loads((fixture_root / "base.json").read_text(encoding="utf-8"))
    )
    desired_bundle = serde.deserialize(fixture_root / "desired")
    desired = reindex_document(desired_bundle.document)

    batches = lower_semantic_diff_batches(base, desired, transport_base=base)

    assert batches
    assert any(
        any("insertTable" in request for request in batch)
        for batch in batches
    )
    assert any(
        any("createFootnote" in request for request in batch)
        for batch in batches
    )


def test_iterative_batches_support_xml_cycle2_live_probe() -> None:
    fixture_root = Path(__file__).resolve().parent / "fixtures" / "xml_cycle2_live_probe"
    base = Document.model_validate(
        json.loads((fixture_root / "base.json").read_text(encoding="utf-8"))
    )
    desired_bundle = serde.deserialize(fixture_root / "desired")
    desired = reindex_document(desired_bundle.document)

    batches = lower_semantic_diff_batches(base, desired, transport_base=base)

    assert batches
    flattened = [request for batch in batches for request in batch]
    assert any("deleteTableRow" in request or "deleteContentRange" in request for request in flattened)
    assert any("insertTable" in request for request in flattened)
    assert any(
        request.get("insertText", {}).get("location", {}).get("segmentId")
        or request.get("deleteContentRange", {}).get("range", {}).get("segmentId")
        for request in flattened
    )


def test_body_carrier_style_reset_requests_normalize_table_adjacent_blank_paragraphs() -> None:
    document = reindex_document(
        markdown_to_document(
            {
                "Tab_1": (
                    "## Alerts Revised\n\n"
                    "> [!TIP]\n"
                    "> Tip callout replacement text.\n\n"
                    "> [!WARNING]\n"
                    "> Warning callout edited text.\n"
                )
            },
            document_id="carrier-style-reset",
            title="Carrier Style Reset",
            tab_ids={"Tab_1": "t.0"},
        )
    )
    raw = document.model_dump(by_alias=True, exclude_none=True)
    body = raw["tabs"][0]["documentTab"]["body"]["content"]
    body.insert(
        5,
        {
            "startIndex": 271,
            "endIndex": 272,
            "paragraph": {
                "elements": [
                    {
                        "startIndex": 271,
                        "endIndex": 272,
                        "textRun": {"content": "\n", "textStyle": {}},
                    }
                ],
                "paragraphStyle": {"namedStyleType": "HEADING_2"},
            },
        },
    )
    broken = Document.model_validate(raw)

    requests = _body_carrier_style_reset_requests(broken)

    assert requests == [
        {
            "updateParagraphStyle": {
                "range": {"startIndex": 271, "endIndex": 272, "tabId": "t.0"},
                "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                "fields": "namedStyleType",
            }
        }
    ]


def test_body_carrier_style_reset_requests_normalize_blank_paragraph_runs_before_tables() -> None:
    raw = {
        "documentId": "carrier-run",
        "tabs": [
            {
                "tabProperties": {"tabId": "t.0", "title": "Tab 1", "index": 0},
                "documentTab": {
                    "body": {
                        "content": [
                            {
                                "endIndex": 1,
                                "sectionBreak": {
                                    "sectionStyle": {"columnSeparatorStyle": "NONE"}
                                },
                            },
                            {
                                "startIndex": 1,
                                "endIndex": 17,
                                "paragraph": {
                                    "elements": [
                                        {
                                            "startIndex": 1,
                                            "endIndex": 17,
                                            "textRun": {"content": "Code Samples\n"},
                                        }
                                    ],
                                    "paragraphStyle": {"namedStyleType": "HEADING_2"},
                                },
                            },
                            {
                                "startIndex": 17,
                                "endIndex": 18,
                                "paragraph": {
                                    "elements": [
                                        {
                                            "startIndex": 17,
                                            "endIndex": 18,
                                            "textRun": {"content": "\n", "textStyle": {}},
                                        }
                                    ],
                                    "paragraphStyle": {"namedStyleType": "HEADING_2"},
                                },
                            },
                            {
                                "startIndex": 18,
                                "endIndex": 19,
                                "paragraph": {
                                    "elements": [
                                        {
                                            "startIndex": 18,
                                            "endIndex": 19,
                                            "textRun": {"content": "\n", "textStyle": {}},
                                        }
                                    ],
                                    "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                                },
                            },
                            {
                                "startIndex": 19,
                                "endIndex": 29,
                                "table": {
                                    "rows": 1,
                                    "columns": 1,
                                    "tableRows": [
                                        {
                                            "startIndex": 20,
                                            "endIndex": 28,
                                            "tableCells": [
                                                {
                                                    "startIndex": 21,
                                                    "endIndex": 28,
                                                    "content": [
                                                        {
                                                            "startIndex": 22,
                                                            "endIndex": 27,
                                                            "paragraph": {
                                                                "elements": [
                                                                    {
                                                                        "startIndex": 22,
                                                                        "endIndex": 26,
                                                                        "textRun": {"content": "code"},
                                                                    },
                                                                    {
                                                                        "startIndex": 26,
                                                                        "endIndex": 27,
                                                                        "textRun": {"content": "\n"},
                                                                    },
                                                                ]
                                                            },
                                                        },
                                                        {
                                                            "startIndex": 27,
                                                            "endIndex": 28,
                                                            "paragraph": {
                                                                "elements": [
                                                                    {
                                                                        "startIndex": 27,
                                                                        "endIndex": 28,
                                                                        "textRun": {"content": "\n"},
                                                                    }
                                                                ]
                                                            },
                                                        },
                                                    ],
                                                    "tableCellStyle": {},
                                                }
                                            ],
                                        }
                                    ],
                                },
                            },
                        ]
                    }
                },
            }
        ],
    }
    broken = Document.model_validate(raw)

    requests = _body_carrier_style_reset_requests(broken)

    assert requests == [
        {
            "updateParagraphStyle": {
                "range": {"startIndex": 17, "endIndex": 18, "tabId": "t.0"},
                "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                "fields": "namedStyleType",
            }
        }
    ]


def test_create_tab_named_range_footnote_batches_ignore_desired_future_tab_and_footnote_ids() -> None:
    base, desired = load_fixture_pair("create_tab_named_range_footnote_write")
    desired_raw = desired.model_dump(by_alias=True, exclude_none=True)
    desired_raw["tabs"][1]["tabProperties"]["tabId"] = "future.range.footnote.tab"
    footnotes = desired_raw["tabs"][1]["documentTab"]["footnotes"]
    footnote_id = next(iter(footnotes))
    footnote = footnotes.pop(footnote_id)
    footnote["footnoteId"] = "future.range.footnote.segment"
    footnotes["future.range.footnote.segment"] = footnote
    for element in desired_raw["tabs"][1]["documentTab"]["body"]["content"]:
        paragraph = element.get("paragraph")
        if not paragraph:
            continue
        for child in paragraph.get("elements", []):
            footnote_ref = child.get("footnoteReference")
            if footnote_ref:
                footnote_ref["footnoteId"] = "future.range.footnote.segment"
    desired_future_id = Document.model_validate(desired_raw)

    assert lower_semantic_diff_batches(base, desired_future_id) == load_expected_lowered_batches(
        "create_tab_named_range_footnote_write"
    )


def test_reconcile_returns_batch_update_models() -> None:
    base, desired = load_fixture_pair("create_tab_table_write")

    batches = reconcile(base, desired)

    assert all(isinstance(batch, BatchUpdateDocumentRequest) for batch in batches)
    assert [batch.model_dump(by_alias=True, exclude_none=True)["requests"] for batch in batches] == (
        load_expected_lowered_batches("create_tab_table_write")
    )


def test_create_tab_with_footer_is_explicitly_unsupported() -> None:
    base, desired = load_fixture_pair("create_tab_table_write")
    _, footer_desired = load_fixture_pair("section_create_footer")
    desired_raw = desired.model_dump(by_alias=True, exclude_none=True)
    footer_raw = footer_desired.model_dump(by_alias=True, exclude_none=True)
    desired_raw["tabs"][1]["documentTab"]["footers"] = footer_raw["tabs"][0]["documentTab"][
        "footers"
    ]
    desired_with_footer = Document.model_validate(desired_raw)

    with pytest.raises(UnsupportedSpikeError, match="cannot safely create headers/footers"):
        lower_semantic_diff_batches(base, desired_with_footer)


def test_page_break_batches_insert_and_replay_semantically() -> None:
    base = reindex_document(
        markdown_to_document(
            {"Tab_1": ""},
            document_id="pagebreak-batches",
            title="Pagebreak Batches",
            tab_ids={"Tab_1": "t.0"},
        )
    )
    desired = reindex_document(
        markdown_to_document(
            {
                "Tab_1": (
                    "Leading paragraph.\n\n"
                    "<x-pagebreak/>\n\n"
                    "Trailing paragraph.\n"
                )
            },
            document_id="pagebreak-batches",
            title="Pagebreak Batches",
            tab_ids={"Tab_1": "t.0"},
        )
    )

    batches = lower_semantic_diff_batches(base, desired)

    flattened = [request for batch in batches for request in batch]
    assert any("insertPageBreak" in request for request in flattened)
    assert any(
        request.get("insertText", {}).get("text") == "Trailing paragraph."
        for request in flattened
    )
    assert any(
        request.get("insertText", {}).get("text") == "Leading paragraph.\n"
        for request in flattened
    )


def test_page_break_splits_empty_body_grouped_insert_with_other_blocks() -> None:
    base = reindex_document(
        markdown_to_document(
            {"Tab_1": ""},
            document_id="pagebreak-mixed-group",
            title="Pagebreak Mixed Group",
            tab_ids={"Tab_1": "t.0"},
        )
    )
    desired = reindex_document(
        markdown_to_document(
            {
                "Tab_1": (
                    "# Heading\n\n"
                    "- first bullet\n"
                    "- second bullet\n\n"
                    "| A | B |\n"
                    "| --- | --- |\n"
                    "| 1 | 2 |\n\n"
                    "<x-pagebreak/>\n\n"
                    "After break.\n"
                )
            },
            document_id="pagebreak-mixed-group",
            title="Pagebreak Mixed Group",
            tab_ids={"Tab_1": "t.0"},
        )
    )

    batches = lower_semantic_diff_batches(base, desired)

    flattened = [request for batch in batches for request in batch]
    assert any("insertPageBreak" in request for request in flattened)
    assert any("insertTable" in request for request in flattened)
    assert any("createParagraphBullets" in request for request in flattened)
    assert any(
        request.get("insertText", {}).get("text") == "After break."
        for request in flattened
    )


def _strip_indices(elements: list[dict]) -> None:
    for element in elements:
        element.pop("startIndex", None)
        element.pop("endIndex", None)
        paragraph = element.get("paragraph")
        if isinstance(paragraph, dict):
            for child in paragraph.get("elements", []):
                child.pop("startIndex", None)
                child.pop("endIndex", None)
        table = element.get("table")
        if isinstance(table, dict):
            for row in table.get("tableRows", []):
                for cell in row.get("tableCells", []):
                    _strip_indices(cell.get("content", []))
