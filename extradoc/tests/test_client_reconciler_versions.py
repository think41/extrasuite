from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from extradoc.api_types._generated import BatchUpdateDocumentRequest, Document
from extradoc.client import (
    RECONCILER_ENV_VAR,
    DiffResult,
    DocsClient,
    _execute_document_batches_v2_live_refresh,
    _get_reconciler_version,
    _normalize_raw_base_para_styles,
    _refresh_still_contains_same_structural_shell,
    _refresh_v2_batches_after_live_change,
    _refresh_v2_batches_after_structural_ops,
    _should_refresh_v2_batches,
    _structural_request_signature,
    _tab_ids_subset,
    _truncate_batch_before_delete_sensitive_inserts,
    _truncate_batch_before_post_table_para_ops,
    _truncate_batch_for_live_refresh,
)
from extradoc.comments._types import (
    CommentOperations,
    DocumentWithComments,
    FileComments,
)
from extradoc.reconcile import reindex_document
from extradoc.reconcile_v2.diff import ReplaceParagraphTextEdit
from extradoc.reconcile_v2.errors import UnsupportedReconcileV2Error
from extradoc.reconcile_v2.executor import BatchExecutionResult
from extradoc.reconcile_v2.ir import ParagraphIR, TextSpanIR
from extradoc.reconcile_v2.lower import _content_edit_order_key
from extradoc.serde import serialize
from extradoc.serde._from_markdown import markdown_to_document
from extradoc.transport import APIError


class _FakeTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[dict], dict | None]] = []
        self.get_document_calls: list[str] = []
        self.raw_document: dict | None = None
        self.raw_documents: list[dict] | None = None
        self.batch_update_exceptions: list[Exception] | None = None

    async def batch_update(
        self,
        document_id: str,
        requests: list[dict],
        write_control: dict | None = None,
    ) -> dict:
        if self.batch_update_exceptions:
            exc = self.batch_update_exceptions.pop(0)
            if exc is not None:
                raise exc
        self.calls.append((document_id, requests, write_control))
        return {"replies": []}

    async def get_document(self, document_id: str) -> object:
        self.get_document_calls.append(document_id)
        raw_document = None
        if self.raw_documents:
            raw_document = self.raw_documents.pop(0)
        else:
            raw_document = self.raw_document
        if raw_document is None:
            raise NotImplementedError
        from extradoc.transport import DocumentData

        return DocumentData(document_id=document_id, title="Test", raw=raw_document)

    async def list_comments(self, _file_id: str) -> list[dict]:
        return []

    async def create_reply(
        self,
        file_id: str,
        comment_id: str,
        content: str,
        action: str | None = None,
    ) -> dict:  # pragma: no cover
        raise NotImplementedError

    async def edit_comment(
        self, file_id: str, comment_id: str, content: str
    ) -> dict:  # pragma: no cover
        raise NotImplementedError

    async def delete_comment(self, file_id: str, comment_id: str) -> None:  # pragma: no cover
        raise NotImplementedError

    async def edit_reply(
        self, file_id: str, comment_id: str, reply_id: str, content: str
    ) -> dict:  # pragma: no cover
        raise NotImplementedError

    async def delete_reply(
        self, file_id: str, comment_id: str, reply_id: str
    ) -> None:  # pragma: no cover
        raise NotImplementedError

    async def close(self) -> None:  # pragma: no cover
        return None


def _batch_with_insert(text: str) -> BatchUpdateDocumentRequest:
    return BatchUpdateDocumentRequest.model_validate(
        {
            "requests": [
                {
                    "insertText": {
                        "location": {"index": 1, "tabId": "t.0"},
                        "text": text,
                    }
                }
            ]
        }
    )


def _batch_with_insert_table() -> BatchUpdateDocumentRequest:
    return BatchUpdateDocumentRequest.model_validate(
        {
            "requests": [
                {
                    "insertTable": {
                        "rows": 1,
                        "columns": 1,
                        "location": {"index": 1, "tabId": "t.0"},
                    }
                }
            ]
        }
    )


def _diff_result_v1() -> DiffResult:
    return DiffResult(
        document_id="doc-1",
        batches=[_batch_with_insert("alpha"), _batch_with_insert("beta")],
        comment_ops=CommentOperations(),
        reconciler_version="v1",
    )


def _diff_result_v2() -> DiffResult:
    return DiffResult(
        document_id="doc-2",
        batches=[_batch_with_insert("omega")],
        comment_ops=CommentOperations(),
        reconciler_version="v2",
        base_revision_id="rev-0",
    )


def _diff_result_v2_refresh() -> DiffResult:
    desired = reindex_document(
        markdown_to_document(
            {"Tab_1": "alpha\n"},
            document_id="doc-3",
            title="Test",
            tab_ids={"Tab_1": "t.0"},
        )
    )
    return DiffResult(
        document_id="doc-3",
        batches=[_batch_with_insert_table(), _batch_with_insert("omega")],
        comment_ops=CommentOperations(),
        reconciler_version="v2",
        base_revision_id="rev-0",
        desired_document=desired,
        desired_format="markdown",
        allow_live_refresh=True,
    )


def _diff_result_v2_refresh_with_post_table_style() -> DiffResult:
    desired = reindex_document(
        markdown_to_document(
            {"Tab_1": "alpha\n"},
            document_id="doc-5",
            title="Test",
            tab_ids={"Tab_1": "t.0"},
        )
    )
    batch = BatchUpdateDocumentRequest.model_validate(
        {
            "requests": [
                {
                    "insertText": {
                        "location": {"index": 1, "tabId": "t.0"},
                        "text": "Lists Revised\n",
                    }
                },
                {
                    "insertTable": {
                        "rows": 1,
                        "columns": 1,
                        "location": {"index": 1, "tabId": "t.0"},
                    }
                },
                {
                    "createParagraphBullets": {
                        "range": {"startIndex": 10, "endIndex": 20, "tabId": "t.0"},
                        "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE",
                    }
                },
            ]
        }
    )
    return DiffResult(
        document_id="doc-5",
        batches=[batch],
        comment_ops=CommentOperations(),
        reconciler_version="v2",
        base_revision_id="rev-0",
        desired_document=desired,
        desired_format="markdown",
        allow_live_refresh=True,
    )


def _diff_result_v2_refresh_with_post_page_break_insert() -> DiffResult:
    desired = reindex_document(
        markdown_to_document(
            {"Tab_1": "alpha\n"},
            document_id="doc-6",
            title="Test",
            tab_ids={"Tab_1": "t.0"},
        )
    )
    batch = BatchUpdateDocumentRequest.model_validate(
        {
            "requests": [
                {
                    "insertText": {
                        "location": {"index": 1, "tabId": "t.0"},
                        "text": "After Break\nClosing paragraph.",
                    }
                },
                {
                    "insertPageBreak": {
                        "location": {"index": 1, "tabId": "t.0"},
                    }
                },
                {
                    "insertText": {
                        "location": {"index": 1, "tabId": "t.0"},
                        "text": "Paragraph before the break.\n",
                    }
                },
            ]
        }
    )
    return DiffResult(
        document_id="doc-6",
        batches=[batch],
        comment_ops=CommentOperations(),
        reconciler_version="v2",
        base_revision_id="rev-0",
        desired_document=desired,
        desired_format="xml",
        allow_live_refresh=True,
    )


def _setup_markdown_folder(
    tmp_path: Path,
    *,
    doc_id: str,
    md_content: str,
) -> Path:
    import zipfile

    from extradoc.comments._types import DocumentWithComments, FileComments

    folder = tmp_path / doc_id
    folder.mkdir()

    doc = markdown_to_document(
        {"Tab_1": md_content},
        document_id=doc_id,
        title="Test",
        tab_ids={"Tab_1": "t.0"},
    )
    bundle = DocumentWithComments(
        document=doc,
        comments=FileComments(file_id=doc_id),
    )
    serialize(bundle, folder, format="markdown")

    pristine_dir = folder / ".pristine"
    pristine_dir.mkdir()
    zip_path = pristine_dir / "document.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for path in sorted(folder.rglob("*")):
            if path.is_file() and ".pristine" not in str(path) and ".raw" not in str(path):
                zf.write(path, path.relative_to(folder))

    return folder


def _setup_xml_folder(
    tmp_path: Path,
    *,
    doc_id: str,
    base_document: Document,
) -> Path:
    import zipfile

    from extradoc.comments._types import DocumentWithComments, FileComments

    folder = tmp_path / doc_id
    folder.mkdir()

    bundle = DocumentWithComments(
        document=base_document,
        comments=FileComments(file_id=doc_id),
    )
    serialize(bundle, folder, format="xml")

    pristine_dir = folder / ".pristine"
    pristine_dir.mkdir()
    zip_path = pristine_dir / "document.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for path in sorted(folder.rglob("*")):
            if path.is_file() and ".pristine" not in str(path) and ".raw" not in str(path):
                zf.write(path, path.relative_to(folder))

    return folder


def test_get_reconciler_version_defaults_to_v2(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(RECONCILER_ENV_VAR, raising=False)
    assert _get_reconciler_version() == "v2"


def test_get_reconciler_version_accepts_v2_aliases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(RECONCILER_ENV_VAR, "semantic-ir")
    assert _get_reconciler_version() == "v2"


def test_get_reconciler_version_rejects_invalid_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(RECONCILER_ENV_VAR, "broken")
    with pytest.raises(ValueError, match=RECONCILER_ENV_VAR):
        _get_reconciler_version()


def test_should_refresh_v2_batches_for_insert_table_or_page_break() -> None:
    assert _should_refresh_v2_batches(
        [{"insertTable": {"rows": 1, "columns": 1, "location": {"index": 1, "tabId": "t.0"}}}]
    )
    assert _should_refresh_v2_batches(
        [{"insertPageBreak": {"location": {"index": 1, "tabId": "t.0"}}}]
    )
    assert not _should_refresh_v2_batches(
        [{"insertText": {"location": {"index": 1, "tabId": "t.0"}, "text": "x"}}]
    )


def test_structural_request_signature_extracts_insert_locations() -> None:
    assert _structural_request_signature(
        {"insertTable": {"rows": 1, "columns": 1, "location": {"index": 7, "tabId": "t.0"}}}
    ) == ("insertTable", "t.0", 7)
    assert _structural_request_signature(
        {"insertPageBreak": {"location": {"index": 11, "tabId": "t.0"}}}
    ) == ("insertPageBreak", "t.0", 11)
    assert _structural_request_signature(
        {"insertText": {"location": {"index": 1, "tabId": "t.0"}, "text": "x"}}
    ) is None


def test_refresh_detects_stale_same_structural_shell() -> None:
    resolved_batch = [
        {"insertPageBreak": {"location": {"index": 1, "tabId": "t.0"}}}
    ]
    stale_batches = [
        BatchUpdateDocumentRequest.model_validate(
            {"requests": resolved_batch}
        )
    ]
    fresh_batches = [
        BatchUpdateDocumentRequest.model_validate(
            {
                "requests": [
                    {
                        "insertText": {
                            "location": {"index": 1, "tabId": "t.0"},
                            "text": "After Break",
                        }
                    }
                ]
            }
        )
    ]
    progressed_same_shell_batches = [
        BatchUpdateDocumentRequest.model_validate(
            {
                "requests": [
                    {
                        "deleteContentRange": {
                            "range": {
                                "startIndex": 72,
                                "endIndex": 74,
                                "tabId": "t.0",
                            }
                        }
                    },
                    {
                        "insertPageBreak": {
                            "location": {"index": 72, "tabId": "t.0"}
                        }
                    },
                    {
                        "insertText": {
                            "location": {"index": 71, "tabId": "t.0"},
                            "text": "\nParagraph before the break.\n",
                        }
                    },
                ]
            }
        )
    ]

    assert _refresh_still_contains_same_structural_shell(
        resolved_batch=resolved_batch,
        refreshed_batches=stale_batches,
    )
    assert not _refresh_still_contains_same_structural_shell(
        resolved_batch=resolved_batch,
        refreshed_batches=progressed_same_shell_batches,
    )
    assert not _refresh_still_contains_same_structural_shell(
        resolved_batch=resolved_batch,
        refreshed_batches=fresh_batches,
    )


@pytest.mark.asyncio
async def test_refresh_retries_until_structural_shell_disappears(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base_doc = reindex_document(
        markdown_to_document(
            {"Tab_1": "alpha\n"},
            document_id="retry-doc",
            title="Retry",
            tab_ids={"Tab_1": "t.0"},
        )
    )
    base_raw = base_doc.model_dump(by_alias=True, exclude_none=True)
    transport = _FakeTransport()
    transport.raw_documents = [base_raw, base_raw]
    desired = base_doc
    stale_batch = [
        BatchUpdateDocumentRequest.model_validate(
            {"requests": [{"insertPageBreak": {"location": {"index": 1, "tabId": "t.0"}}}]}
        )
    ]
    fresh_batch = [
        BatchUpdateDocumentRequest.model_validate(
            {"requests": [{"insertText": {"location": {"index": 1, "tabId": "t.0"}, "text": "After Break"}}]}
        )
    ]
    planned = iter([stale_batch, fresh_batch])

    def _fake_reconcile(
        _base: Document,
        _desired_document: Document,
        *,
        transport_base: Document | None = None,
    ) -> list[BatchUpdateDocumentRequest]:
        _ = transport_base
        return next(planned)

    monkeypatch.setattr("extradoc.client.reconcile_v2", _fake_reconcile)

    refreshed_batches, revision_id = await _refresh_v2_batches_after_structural_ops(
        transport=transport,
        document_id="retry-doc",
        _resolved_batch=[{"insertPageBreak": {"location": {"index": 1, "tabId": "t.0"}}}],
        desired_document=desired,
        desired_format="xml",
        current_revision_id=None,
    )

    assert revision_id is None
    assert len(transport.get_document_calls) == 2
    assert refreshed_batches == fresh_batch


@pytest.mark.asyncio
async def test_refresh_raises_if_structural_shell_never_materializes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base_doc = reindex_document(
        markdown_to_document(
            {"Tab_1": "alpha\n"},
            document_id="retry-doc-fail",
            title="Retry",
            tab_ids={"Tab_1": "t.0"},
        )
    )
    base_raw = base_doc.model_dump(by_alias=True, exclude_none=True)
    transport = _FakeTransport()
    transport.raw_documents = [base_raw] * 20
    desired = base_doc
    stale_batch = [
        BatchUpdateDocumentRequest.model_validate(
            {"requests": [{"insertPageBreak": {"location": {"index": 1, "tabId": "t.0"}}}]}
        )
    ]

    def _always_stale(
        _base: Document,
        _desired_document: Document,
        *,
        transport_base: Document | None = None,
    ) -> list[BatchUpdateDocumentRequest]:
        _ = transport_base
        return stale_batch

    monkeypatch.setattr("extradoc.client.reconcile_v2", _always_stale)

    with pytest.raises(RuntimeError, match="structural change"):
        await _refresh_v2_batches_after_structural_ops(
            transport=transport,
            document_id="retry-doc-fail",
            _resolved_batch=[{"insertPageBreak": {"location": {"index": 1, "tabId": "t.0"}}}],
            desired_document=desired,
            desired_format="xml",
            current_revision_id=None,
        )


def test_truncate_batch_before_post_structural_para_ops() -> None:
    batch = [
        {
            "insertText": {
                "location": {"index": 1, "tabId": "t.0"},
                "text": "Lists Revised\n",
            }
        },
        {
            "insertTable": {
                "rows": 1,
                "columns": 1,
                "location": {"index": 1, "tabId": "t.0"},
            }
        },
        {
            "insertText": {
                "location": {"index": 5, "tabId": "t.0"},
                "text": "Tip callout replacement text.",
            }
        },
        {
            "createParagraphBullets": {
                "range": {"startIndex": 422, "endIndex": 484, "tabId": "t.0"},
                "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE",
            }
        },
    ]

    # insertText before the table (batch[0]) is kept; non-text followups dropped.
    assert _truncate_batch_before_post_table_para_ops(batch) == [batch[0], batch[1]]


def test_truncate_batch_before_post_page_break_ops() -> None:
    # For insertPageBreak: keep everything up to and including the break.
    # Content that appears AFTER the break in the request list (which inserts
    # BEFORE the break in the final document) is deferred to the refresh cycle.
    batch = [
        {
            "insertText": {
                "location": {"index": 1, "tabId": "t.0"},
                "text": "After Break\nClosing paragraph.",
            }
        },
        {
            "insertPageBreak": {
                "location": {"index": 1, "tabId": "t.0"},
            }
        },
        {
            "insertText": {
                "location": {"index": 1, "tabId": "t.0"},
                "text": "Paragraph before the break.\n",
            }
        },
    ]

    assert _truncate_batch_before_post_table_para_ops(batch) == [batch[0], batch[1]]


def test_truncate_batch_before_post_page_break_ops_drops_lower_anchor_suffix() -> None:
    # Lower-anchor inserts that follow the insertPageBreak in the request list
    # insert BEFORE the break in the final document.  They are deferred so the
    # refreshed plan can anchor them correctly relative to the live break.
    batch = [
        {
            "insertText": {
                "location": {"index": 73, "tabId": "t.0"},
                "text": "\nAfter Break\nClosing paragraph.",
            }
        },
        {
            "insertPageBreak": {
                "location": {"index": 72, "tabId": "t.0"},
            }
        },
        {
            "insertText": {
                "location": {"index": 71, "tabId": "t.0"},
                "text": "\nParagraph before the break.\n",
            }
        },
        {
            "insertText": {
                "location": {"index": 71, "tabId": "t.0"},
                "text": "First bullet\nSecond bullet",
            }
        },
    ]

    assert _truncate_batch_before_post_table_para_ops(batch) == [batch[0], batch[1]]


def test_truncate_batch_preserves_same_anchor_prefix_text_after_insert_table() -> None:
    batch = [
        {
            "insertText": {
                "location": {"index": 1, "tabId": "t.0"},
                "text": "Closing paragraph.\n",
            }
        },
        {
            "insertTable": {
                "rows": 2,
                "columns": 2,
                "location": {"index": 1, "tabId": "t.0"},
            }
        },
        {
            "insertText": {
                "location": {"index": 12, "tabId": "t.0"},
                "text": "Delta",
            }
        },
        {
            "insertText": {
                "location": {"index": 1, "tabId": "t.0"},
                "text": "First bullet\nSecond bullet\n",
            }
        },
        {
            "insertText": {
                "location": {"index": 1, "tabId": "t.0"},
                "text": "Simple Table Verification\nXML body with a list and table, but no page break.\n",
            }
        },
        {
            "createParagraphBullets": {
                "range": {"startIndex": 78, "endIndex": 105, "tabId": "t.0"},
                "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE",
            }
        },
    ]

    # batch[0]: insertText("Closing paragraph.\n", index=1) — before table, kept
    # batch[1]: insertTable(index=1) — kept
    # batch[2]: insertText("Delta", index=12) — high-index cell write, deferred
    # batch[3]: insertText("First bullet..", index=1) — same-anchor after table, kept
    # batch[4]: insertText("Simple Table..", index=1) — same-anchor after table, kept
    # batch[5]: createParagraphBullets — deferred
    assert _truncate_batch_before_post_table_para_ops(batch) == [
        batch[0],
        batch[1],
        batch[3],
        batch[4],
    ]


def test_truncate_batch_before_delete_sensitive_inserts_keeps_delete_only_round() -> None:
    batch = [
        {
            "deleteContentRange": {
                "range": {"startIndex": 50, "endIndex": 80, "tabId": "t.0"}
            }
        },
        {
            "insertText": {
                "location": {"index": 34, "tabId": "t.0"},
                "text": "After Break\nClosing paragraph.\n",
            }
        },
        {
            "updateParagraphStyle": {
                "range": {"startIndex": 34, "endIndex": 46, "tabId": "t.0"},
                "paragraphStyle": {"namedStyleType": "HEADING_2"},
                "fields": "namedStyleType",
            }
        },
    ]

    assert _truncate_batch_before_delete_sensitive_inserts(batch) == [batch[0]]
    assert _truncate_batch_for_live_refresh(batch) == ([batch[0]], "delete-only")


@pytest.mark.asyncio
async def test_refresh_after_live_change_replans_from_latest_raw_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base_doc = reindex_document(
        markdown_to_document(
            {"Tab_1": "alpha\n"},
            document_id="refresh-live-change",
            title="Refresh",
            tab_ids={"Tab_1": "t.0"},
        )
    )
    base_raw = base_doc.model_dump(by_alias=True, exclude_none=True)
    transport = _FakeTransport()
    transport.raw_document = base_raw
    desired = base_doc
    replanned = [
        BatchUpdateDocumentRequest.model_validate(
            {"requests": [{"insertText": {"location": {"index": 1, "tabId": "t.0"}, "text": "beta"}}]}
        )
    ]

    def _fake_reconcile(
        _base: Document,
        _desired_document: Document,
        *,
        transport_base: Document | None = None,
    ) -> list[BatchUpdateDocumentRequest]:
        assert transport_base is not None
        return replanned

    monkeypatch.setattr("extradoc.client.reconcile_v2", _fake_reconcile)

    refreshed_batches, revision_id = await _refresh_v2_batches_after_live_change(
        transport=transport,
        document_id="refresh-live-change",
        desired_document=desired,
        desired_format="xml",
        current_revision_id=None,
    )

    assert revision_id is None
    assert transport.get_document_calls == ["refresh-live-change"]
    assert refreshed_batches == replanned


@pytest.mark.asyncio
async def test_execute_v2_live_refresh_recovers_from_revision_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base_doc = reindex_document(
        markdown_to_document(
            {"Tab_1": "alpha\n"},
            document_id="retry-revision-doc",
            title="Retry",
            tab_ids={"Tab_1": "t.0"},
        )
    )
    base_raw = base_doc.model_dump(by_alias=True, exclude_none=True)
    desired = base_doc
    initial_batch = BatchUpdateDocumentRequest.model_validate(
        {
            "requests": [
                {
                    "insertText": {
                        "location": {"index": 1, "tabId": "t.0"},
                        "text": "omega",
                    }
                }
            ]
        }
    )
    refreshed_batch = BatchUpdateDocumentRequest.model_validate(
        {
            "requests": [
                {
                    "insertText": {
                        "location": {"index": 1, "tabId": "t.0"},
                        "text": "beta",
                    }
                }
            ]
        }
    )
    transport = _FakeTransport()
    transport.raw_document = base_raw
    transport.batch_update_exceptions = [
        APIError("The required revision ID 'rev-old' does not match the latest revision.", 400)
    ]

    def _fake_reconcile(
        _base: Document,
        _desired_document: Document,
        *,
        transport_base: Document | None = None,
    ) -> list[BatchUpdateDocumentRequest]:
        assert transport_base is not None
        return [refreshed_batch]

    monkeypatch.setattr("extradoc.client.reconcile_v2", _fake_reconcile)

    result = DiffResult(
        document_id="retry-revision-doc",
        batches=[initial_batch],
        comment_ops=CommentOperations(),
        reconciler_version="v2",
        base_revision_id="rev-old",
        desired_document=desired,
        desired_format="xml",
        allow_live_refresh=True,
    )

    changes = await _execute_document_batches_v2_live_refresh(transport, result)

    assert changes == 1
    assert transport.get_document_calls == ["retry-revision-doc"]
    assert transport.calls == [
        (
            "retry-revision-doc",
            refreshed_batch.model_dump(by_alias=True, exclude_none=True, mode="json")["requests"],
            {"requiredRevisionId": "rev-old"},
        )
    ]


def test_table_cell_story_edits_sort_descending_by_cell_anchor() -> None:
    paragraph = ParagraphIR(
        role="NORMAL_TEXT",
        explicit_style={},
        inlines=[TextSpanIR(text="x", explicit_text_style={})],
    )
    edits = [
        ReplaceParagraphTextEdit(
            tab_id="t.0",
            story_id="t.0:body:table:2:r0:c0",
            section_index=0,
            block_index=0,
            desired_paragraph=paragraph,
        ),
        ReplaceParagraphTextEdit(
            tab_id="t.0",
            story_id="t.0:body:table:2:r0:c1",
            section_index=0,
            block_index=0,
            desired_paragraph=paragraph,
        ),
        ReplaceParagraphTextEdit(
            tab_id="t.0",
            story_id="t.0:body:table:2:r1:c0",
            section_index=0,
            block_index=0,
            desired_paragraph=paragraph,
        ),
        ReplaceParagraphTextEdit(
            tab_id="t.0",
            story_id="t.0:body:table:2:r1:c1",
            section_index=0,
            block_index=0,
            desired_paragraph=paragraph,
        ),
    ]

    ordered_story_ids = [
        edit.story_id
        for _, edit in sorted(
            enumerate(edits),
            key=lambda item: _content_edit_order_key(item[0], item[1]),
        )
    ]

    assert ordered_story_ids == [
        "t.0:body:table:2:r1:c1",
        "t.0:body:table:2:r1:c0",
        "t.0:body:table:2:r0:c1",
        "t.0:body:table:2:r0:c0",
    ]


def test_tab_ids_subset_rejects_future_tabs() -> None:
    base = reindex_document(
        markdown_to_document(
            {"Tab_1": "alpha\n"},
            document_id="subset-base",
            title="Test",
            tab_ids={"Tab_1": "t.0"},
        )
    )
    desired = reindex_document(
        markdown_to_document(
            {"Tab_1": "alpha\n", "Second_Tab": "beta\n"},
            document_id="subset-base",
            title="Test",
            tab_ids={"Tab_1": "t.0", "Second_Tab": "t.future"},
        )
    )

    assert not _tab_ids_subset(base, desired)


def test_diff_uses_reconcile_v2_by_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base_md = "alpha paragraph\n"
    edited_md = "# alpha paragraph\n"

    folder = _setup_markdown_folder(
        tmp_path,
        doc_id="test-v2-diff",
        md_content=base_md,
    )
    (folder / "Tab_1.md").write_text(edited_md, encoding="utf-8")

    raw_doc = markdown_to_document(
        {"Tab_1": base_md},
        document_id="test-v2-diff",
        title="Test",
        tab_ids={"Tab_1": "t.0"},
    )
    raw_dir = folder / ".raw"
    raw_dir.mkdir()
    (raw_dir / "document.json").write_text(
        reindex_document(raw_doc).model_dump_json(by_alias=True, exclude_none=True),
        encoding="utf-8",
    )

    monkeypatch.delenv(RECONCILER_ENV_VAR, raising=False)

    client = DocsClient.__new__(DocsClient)
    result = client.diff(str(folder))

    assert result.reconciler_version == "v2"
    assert result.batches


def test_diff_can_use_reconcile_v1_via_env_var(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base_md = "alpha paragraph\n"
    edited_md = "# alpha paragraph\n"

    folder = _setup_markdown_folder(
        tmp_path,
        doc_id="test-v1-diff",
        md_content=base_md,
    )
    (folder / "Tab_1.md").write_text(edited_md, encoding="utf-8")

    raw_doc = markdown_to_document(
        {"Tab_1": base_md},
        document_id="test-v1-diff",
        title="Test",
        tab_ids={"Tab_1": "t.0"},
    )
    raw_dir = folder / ".raw"
    raw_dir.mkdir()
    (raw_dir / "document.json").write_text(
        reindex_document(raw_doc).model_dump_json(by_alias=True, exclude_none=True),
        encoding="utf-8",
    )

    monkeypatch.setenv(RECONCILER_ENV_VAR, "v1")

    client = DocsClient.__new__(DocsClient)
    result = client.diff(str(folder))

    assert result.reconciler_version == "v1"
    assert result.batches


def test_diff_v2_detects_first_markdown_content_in_empty_doc(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    folder = _setup_markdown_folder(
        tmp_path,
        doc_id="test-v2-empty-first-push",
        md_content="",
    )
    (folder / "Tab_1.md").write_text("alpha paragraph\n\nbeta paragraph\n", encoding="utf-8")

    raw_doc = markdown_to_document(
        {"Tab_1": ""},
        document_id="test-v2-empty-first-push",
        title="Test",
        tab_ids={"Tab_1": "t.0"},
    )
    raw_dir = folder / ".raw"
    raw_dir.mkdir()
    (raw_dir / "document.json").write_text(
        reindex_document(raw_doc).model_dump_json(by_alias=True, exclude_none=True),
        encoding="utf-8",
    )

    monkeypatch.delenv(RECONCILER_ENV_VAR, raising=False)

    client = DocsClient.__new__(DocsClient)
    result = client.diff(str(folder))

    assert result.reconciler_version == "v2"
    assert result.batches


def test_diff_v2_preserves_inserted_markdown_heading_and_link_styles(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    folder = _setup_markdown_folder(
        tmp_path,
        doc_id="test-v2-rich-first-push",
        md_content="",
    )
    (folder / "Tab_1.md").write_text(
        "# Delivery Plan\n\nSee [spec](https://example.com).\n",
        encoding="utf-8",
    )

    raw_doc = markdown_to_document(
        {"Tab_1": ""},
        document_id="test-v2-rich-first-push",
        title="Test",
        tab_ids={"Tab_1": "t.0"},
    )
    raw_dir = folder / ".raw"
    raw_dir.mkdir()
    (raw_dir / "document.json").write_text(
        reindex_document(raw_doc).model_dump_json(by_alias=True, exclude_none=True),
        encoding="utf-8",
    )

    monkeypatch.delenv(RECONCILER_ENV_VAR, raising=False)

    client = DocsClient.__new__(DocsClient)
    result = client.diff(str(folder))

    requests = [request for batch in result.batches for request in batch.requests]
    assert result.reconciler_version == "v2"
    assert any(request.update_paragraph_style for request in requests)
    assert any(request.update_text_style for request in requests)


def test_diff_v2_detects_list_insert_beside_existing_paragraph(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    folder = _setup_markdown_folder(
        tmp_path,
        doc_id="test-v2-list-insert",
        md_content="Intro\n",
    )
    (folder / "Tab_1.md").write_text("Intro\n\n- one\n- two\n", encoding="utf-8")

    raw_doc = markdown_to_document(
        {"Tab_1": "Intro\n"},
        document_id="test-v2-list-insert",
        title="Test",
        tab_ids={"Tab_1": "t.0"},
    )
    raw_dir = folder / ".raw"
    raw_dir.mkdir()
    (raw_dir / "document.json").write_text(
        reindex_document(raw_doc).model_dump_json(by_alias=True, exclude_none=True),
        encoding="utf-8",
    )

    monkeypatch.delenv(RECONCILER_ENV_VAR, raising=False)

    client = DocsClient.__new__(DocsClient)
    result = client.diff(str(folder))

    requests = [request for batch in result.batches for request in batch.requests]
    assert result.reconciler_version == "v2"
    assert any(request.create_paragraph_bullets for request in requests)


def test_diff_v2_detects_table_insert_beside_existing_paragraphs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    folder = _setup_markdown_folder(
        tmp_path,
        doc_id="test-v2-table-insert",
        md_content="Alpha\n\nOmega\n",
    )
    (folder / "Tab_1.md").write_text(
        "Alpha\n\n```\ncode\n```\n\nOmega\n",
        encoding="utf-8",
    )

    raw_doc = markdown_to_document(
        {"Tab_1": "Alpha\n\nOmega\n"},
        document_id="test-v2-table-insert",
        title="Test",
        tab_ids={"Tab_1": "t.0"},
    )
    raw_dir = folder / ".raw"
    raw_dir.mkdir()
    (raw_dir / "document.json").write_text(
        reindex_document(raw_doc).model_dump_json(by_alias=True, exclude_none=True),
        encoding="utf-8",
    )

    monkeypatch.delenv(RECONCILER_ENV_VAR, raising=False)

    client = DocsClient.__new__(DocsClient)
    result = client.diff(str(folder))

    requests = [request for batch in result.batches for request in batch.requests]
    assert result.reconciler_version == "v2"
    assert any(request.insert_table for request in requests)
    assert any(request.create_named_range for request in requests)


def test_diff_v2_uses_raw_transport_base_for_iterative_markdown_batches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import zipfile

    fixture_root = (
        Path(__file__).resolve().parent
        / "reconcile_v2"
        / "fixtures"
        / "live_multitab_cycle2_probe"
    )
    base = Document.model_validate(
        json.loads((fixture_root / "base.json").read_text(encoding="utf-8"))
    )
    desired_folder = fixture_root / "desired"

    folder = tmp_path / "live-multitab-cycle2"
    folder.mkdir()
    bundle = DocumentWithComments(
        document=base,
        comments=FileComments(file_id="live-multitab-cycle2"),
    )
    serialize(bundle, folder, format="markdown")

    pristine_dir = folder / ".pristine"
    pristine_dir.mkdir()
    with zipfile.ZipFile(pristine_dir / "document.zip", "w") as zf:
        for path in sorted(folder.rglob("*")):
            if path.is_file() and ".pristine" not in str(path) and ".raw" not in str(path):
                zf.write(path, path.relative_to(folder))

    for path in desired_folder.iterdir():
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            if path.name == "Tab_1.md":
                text = text.replace("\n---\n\n", "\n")
            (folder / path.name).write_text(text, encoding="utf-8")

    raw_dir = folder / ".raw"
    raw_dir.mkdir()
    (raw_dir / "document.json").write_text(
        (fixture_root / "base.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    monkeypatch.delenv(RECONCILER_ENV_VAR, raising=False)

    client = DocsClient.__new__(DocsClient)
    result = client.diff(str(folder))

    assert result.reconciler_version == "v2"
    requests = [
        request.model_dump(by_alias=True, exclude_none=True, mode="json")
        for batch in result.batches
        for request in (batch.requests or [])
    ]
    assert {
        "deleteContentRange": {
            "range": {"startIndex": 497, "endIndex": 515, "tabId": "t.0"}
        }
    } in requests
    assert {
        "insertText": {
            "location": {"index": 497, "tabId": "t.0"},
            "text": '    return "blue"',
        }
    } in requests
    assert {
        "deleteContentRange": {
            "range": {"startIndex": 520, "endIndex": 558, "tabId": "t.0"}
        }
    } in requests
    assert {
        "insertText": {
            "location": {"index": 520, "tabId": "t.0"},
            "text": '{"stage": "edited", "verified": false}',
        }
    } in requests


def test_pull_always_writes_raw_document_json_even_when_save_raw_is_false(
    tmp_path: Path,
) -> None:
    raw_document = reindex_document(
        markdown_to_document(
            {"Tab_1": "alpha\n"},
            document_id="pull-raw-doc",
            title="Test",
            tab_ids={"Tab_1": "t.0"},
        )
    ).model_dump(by_alias=True, exclude_none=True)

    transport = _FakeTransport()
    transport.raw_document = raw_document
    client = DocsClient(transport)

    written = asyncio.run(
        client.pull(
            "pull-raw-doc",
            tmp_path,
            save_raw=False,
            format="xml",
        )
    )

    raw_doc_path = tmp_path / "pull-raw-doc" / ".raw" / "document.json"
    raw_comments_path = tmp_path / "pull-raw-doc" / ".raw" / "comments.json"

    assert raw_doc_path in written
    assert raw_doc_path.exists()
    assert not raw_comments_path.exists()


def test_diff_xml_uses_raw_transport_base_when_present(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base_document = markdown_to_document(
        {"Tab_1": "alpha paragraph\n"},
        document_id="xml-raw-base",
        title="Test",
        tab_ids={"Tab_1": "t.0"},
    )
    desired_document = markdown_to_document(
        {"Tab_1": "beta paragraph\n"},
        document_id="xml-raw-base",
        title="Test",
        tab_ids={"Tab_1": "t.0"},
    )

    folder = _setup_xml_folder(
        tmp_path,
        doc_id="xml-raw-base",
        base_document=base_document,
    )

    desired_dir = tmp_path / "xml-desired"
    serialize(
        DocumentWithComments(
            document=desired_document,
            comments=FileComments(file_id="xml-raw-base"),
        ),
        desired_dir,
        format="xml",
    )
    (folder / "Tab_1" / "document.xml").write_text(
        (desired_dir / "Tab_1" / "document.xml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (folder / "Tab_1" / "styles.xml").write_text(
        (desired_dir / "Tab_1" / "styles.xml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    raw_doc = reindex_document(base_document)
    raw_doc.revision_id = "rev-xml-raw"
    raw_dir = folder / ".raw"
    raw_dir.mkdir()
    (raw_dir / "document.json").write_text(
        raw_doc.model_dump_json(by_alias=True, exclude_none=True),
        encoding="utf-8",
    )

    monkeypatch.delenv(RECONCILER_ENV_VAR, raising=False)
    captured: dict[str, object] = {}

    def _fake_reconcile_documents(
        base: Document,
        desired: Document,
        *,
        reconciler_version: str,
        transport_base: Document | None = None,
    ) -> list[BatchUpdateDocumentRequest]:
        captured["reconciler_version"] = reconciler_version
        captured["base"] = base
        captured["desired"] = desired
        captured["transport_base"] = transport_base
        return []

    client = DocsClient.__new__(DocsClient)
    monkeypatch.setattr("extradoc.client._reconcile_documents", _fake_reconcile_documents)
    result = client.diff(str(folder))

    assert result.reconciler_version == "v2"
    assert result.base_revision_id == "rev-xml-raw"
    assert result.desired_format == "xml"
    assert captured["reconciler_version"] == "v2"
    assert isinstance(captured["transport_base"], Document)
    assert captured["transport_base"].revision_id == "rev-xml-raw"
    assert isinstance(captured["base"], Document)
    assert isinstance(captured["desired"], Document)
    assert any(
        element.start_index is not None
        for element in captured["base"].tabs[0].document_tab.body.content
    )
    assert (
        any(
            element.start_index is not None
            for element in captured["transport_base"].tabs[0].document_tab.body.content
        )
    )


def test_diff_v2_detects_empty_doc_mixed_body_insert(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    folder = _setup_markdown_folder(
        tmp_path,
        doc_id="test-v2-mixed-empty-insert",
        md_content="",
    )
    (folder / "Tab_1.md").write_text(
        (
            "# Mixed Body QA\n\n"
            "Lead paragraph.\n\n"
            "- first bullet\n"
            "- second bullet\n\n"
            "```python\n"
            "print('hi')\n"
            "```\n\n"
            "Closing paragraph.\n"
        ),
        encoding="utf-8",
    )

    raw_doc = markdown_to_document(
        {"Tab_1": ""},
        document_id="test-v2-mixed-empty-insert",
        title="Test",
        tab_ids={"Tab_1": "t.0"},
    )
    raw_dir = folder / ".raw"
    raw_dir.mkdir()
    (raw_dir / "document.json").write_text(
        reindex_document(raw_doc).model_dump_json(by_alias=True, exclude_none=True),
        encoding="utf-8",
    )

    monkeypatch.delenv(RECONCILER_ENV_VAR, raising=False)

    client = DocsClient.__new__(DocsClient)
    result = client.diff(str(folder))

    requests = [request for batch in result.batches for request in batch.requests]
    assert result.reconciler_version == "v2"
    assert any(request.insert_table for request in requests)


def test_diff_v2_detects_markdown_footnote_create_from_empty_doc(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    folder = _setup_markdown_folder(
        tmp_path,
        doc_id="test-v2-footnote-insert",
        md_content="",
    )
    (folder / "Tab_1.md").write_text(
        "Paragraph with footnote.[^note]\n\n[^note]: Footnote body text.\n",
        encoding="utf-8",
    )

    raw_doc = markdown_to_document(
        {"Tab_1": ""},
        document_id="test-v2-footnote-insert",
        title="Test",
        tab_ids={"Tab_1": "t.0"},
    )
    raw_dir = folder / ".raw"
    raw_dir.mkdir()
    (raw_dir / "document.json").write_text(
        reindex_document(raw_doc).model_dump_json(by_alias=True, exclude_none=True),
        encoding="utf-8",
    )

    monkeypatch.delenv(RECONCILER_ENV_VAR, raising=False)

    client = DocsClient.__new__(DocsClient)
    result = client.diff(str(folder))

    raw_batches = [
        batch.model_dump(by_alias=True, exclude_none=True, mode="json")
        for batch in result.batches
    ]
    assert result.reconciler_version == "v2"
    assert any(
        any("createFootnote" in request for request in batch["requests"])
        for batch in raw_batches
    )


def test_diff_v2_preserves_existing_footnote_ref_when_body_text_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    footnote_id = "kix.fn123"
    base_md = (
        "# Footnote Verification\n\n"
        f"Base paragraph with footnote.[^{footnote_id}]\n\n"
        f"[^{footnote_id}]: First footnote text.\n"
    )
    desired_md = (
        "# Footnote Verification\n\n"
        f"Edited paragraph with footnote preserved.[^{footnote_id}]\n\n"
        f"[^{footnote_id}]: Second footnote text.\n"
    )

    folder = _setup_markdown_folder(
        tmp_path,
        doc_id="test-v2-footnote-edit",
        md_content=base_md,
    )
    (folder / "Tab_1.md").write_text(desired_md, encoding="utf-8")

    raw_doc = markdown_to_document(
        {"Tab_1": base_md},
        document_id="test-v2-footnote-edit",
        title="Test",
        tab_ids={"Tab_1": "t.0"},
    )
    raw_dir = folder / ".raw"
    raw_dir.mkdir()
    (raw_dir / "document.json").write_text(
        reindex_document(raw_doc).model_dump_json(by_alias=True, exclude_none=True),
        encoding="utf-8",
    )

    monkeypatch.delenv(RECONCILER_ENV_VAR, raising=False)

    client = DocsClient.__new__(DocsClient)
    result = client.diff(str(folder))
    raw_batches = [
        batch.model_dump(by_alias=True, exclude_none=True, mode="json")
        for batch in result.batches
    ]
    requests = [request for batch in raw_batches for request in batch["requests"]]

    assert not any("createFootnote" in request for request in requests)
    assert any(
        request.get("deleteContentRange", {}).get("range", {}).get("segmentId") == footnote_id
        for request in requests
    )
    assert any(
        request.get("deleteContentRange", {}).get("range", {}).get("tabId") == "t.0"
        and "segmentId" not in request.get("deleteContentRange", {}).get("range", {})
        for request in requests
    )


def test_diff_v2_rejects_markdown_horizontal_rule_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    folder = _setup_markdown_folder(
        tmp_path,
        doc_id="test-v2-hr-readonly",
        md_content="",
    )
    (folder / "Tab_1.md").write_text(
        "Paragraph before\n\n---\n\nParagraph after\n",
        encoding="utf-8",
    )

    raw_doc = markdown_to_document(
        {"Tab_1": ""},
        document_id="test-v2-hr-readonly",
        title="Test",
        tab_ids={"Tab_1": "t.0"},
    )
    raw_dir = folder / ".raw"
    raw_dir.mkdir()
    (raw_dir / "document.json").write_text(
        reindex_document(raw_doc).model_dump_json(by_alias=True, exclude_none=True),
        encoding="utf-8",
    )

    monkeypatch.delenv(RECONCILER_ENV_VAR, raising=False)

    client = DocsClient.__new__(DocsClient)
    with pytest.raises(
        UnsupportedReconcileV2Error,
        match="read-only or opaque body blocks",
    ):
        client.diff(str(folder))


def test_normalize_raw_base_preserves_empty_paragraphs_used_by_named_ranges() -> None:
    raw = Document.model_validate(
        {
            "documentId": "doc-nr",
            "revisionId": "rev-nr",
            "tabs": [
                {
                    "tabProperties": {"tabId": "t.0", "title": "Tab 1", "index": 0},
                    "documentTab": {
                        "namedRanges": {
                            "extradoc:blockquote": {
                                "name": "extradoc:blockquote",
                                "namedRanges": [
                                    {
                                        "name": "extradoc:blockquote",
                                        "namedRangeId": "nr-1",
                                        "ranges": [
                                            {
                                                "startIndex": 7,
                                                "endIndex": 13,
                                                "tabId": "t.0",
                                            }
                                        ],
                                    }
                                ],
                            }
                        },
                        "body": {
                            "content": [
                                {"endIndex": 1, "sectionBreak": {}},
                                {
                                    "startIndex": 1,
                                    "endIndex": 7,
                                    "paragraph": {
                                        "elements": [
                                            {
                                                "startIndex": 1,
                                                "endIndex": 7,
                                                "textRun": {"content": "Lead\n"},
                                            }
                                        ]
                                    },
                                },
                                {
                                    "startIndex": 7,
                                    "endIndex": 8,
                                    "paragraph": {
                                        "elements": [
                                            {
                                                "startIndex": 7,
                                                "endIndex": 8,
                                                "textRun": {"content": "\n"},
                                            }
                                        ]
                                    },
                                },
                                {
                                    "startIndex": 8,
                                    "endIndex": 12,
                                    "table": {"rows": 1, "columns": 1, "tableRows": []},
                                },
                                {
                                    "startIndex": 12,
                                    "endIndex": 13,
                                    "paragraph": {
                                        "elements": [
                                            {
                                                "startIndex": 12,
                                                "endIndex": 13,
                                                "textRun": {"content": "\n"},
                                            }
                                        ]
                                    },
                                },
                            ]
                        },
                    },
                }
            ],
        }
    )
    markdown_reference = reindex_document(
        markdown_to_document(
            {"Tab_1": "> quoted\n"},
            document_id="doc-nr",
            title="Named Range Preserve",
            tab_ids={"Tab_1": "t.0"},
        )
    )

    _normalize_raw_base_para_styles(raw, markdown_reference)

    content = raw.tabs[0].document_tab.body.content
    assert [element.start_index for element in content if element.paragraph] == [1, 7, 12]


@pytest.mark.asyncio
async def test_push_uses_v1_batch_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = _FakeTransport()
    client = DocsClient(transport)
    monkeypatch.setattr(
        DocsClient,
        "diff",
        lambda _self, _folder: _diff_result_v1(),
    )

    result = await client.push(Path("/tmp/folder"))

    assert result.success is True
    assert result.changes_applied == 2
    assert len(transport.calls) == 2
    assert [call[1][0]["insertText"]["text"] for call in transport.calls] == [
        "alpha",
        "beta",
    ]


@pytest.mark.asyncio
async def test_push_uses_v2_executor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = _FakeTransport()
    client = DocsClient(transport)
    monkeypatch.setattr(
        DocsClient,
        "diff",
        lambda _self, _folder: _diff_result_v2(),
    )
    seen: dict[str, object] = {}

    async def _fake_execute(
        transport_arg: object,
        *,
        document_id: str,
        request_batches: list[list[dict]],
        initial_revision_id: str | None,
    ) -> BatchExecutionResult:
        seen["transport"] = transport_arg
        seen["document_id"] = document_id
        seen["request_batches"] = request_batches
        seen["initial_revision_id"] = initial_revision_id
        return BatchExecutionResult(responses=(), final_revision_id="rev-1")

    monkeypatch.setattr("extradoc.client.execute_request_batches", _fake_execute)

    result = await client.push(Path("/tmp/folder"))

    assert result.success is True
    assert result.changes_applied == 1
    assert not transport.calls
    assert seen == {
        "transport": transport,
        "document_id": "doc-2",
        "request_batches": [
            [
                {
                    "insertText": {
                        "location": {"index": 1, "tabId": "t.0"},
                        "text": "omega",
                    }
                }
            ]
        ],
        "initial_revision_id": "rev-0",
    }


@pytest.mark.asyncio
async def test_push_refreshes_v2_batches_after_insert_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = _FakeTransport()
    transport.raw_document = reindex_document(
        markdown_to_document(
            {"Tab_1": "alpha\n"},
            document_id="doc-3",
            title="Test",
            tab_ids={"Tab_1": "t.0"},
        )
    ).model_dump(by_alias=True, exclude_none=True)
    client = DocsClient(transport)
    monkeypatch.setattr(
        DocsClient,
        "diff",
        lambda _self, _folder: _diff_result_v2_refresh(),
    )

    refreshed = BatchUpdateDocumentRequest.model_validate(
        {
            "requests": [
                {
                    "insertText": {
                        "location": {"index": 1, "tabId": "t.0"},
                        "text": "refreshed",
                    }
                }
            ]
        }
    )
    def _fake_reconcile_v2(
        _base: Document,
        _desired: Document,
        transport_base: Document | None = None,
    ) -> list[BatchUpdateDocumentRequest]:
        _ = transport_base
        return [refreshed]

    monkeypatch.setattr("extradoc.client.reconcile_v2", _fake_reconcile_v2)

    result = await client.push(Path("/tmp/folder"))

    assert result.success is True
    assert transport.get_document_calls == ["doc-3"]
    assert [call[1][0] for call in transport.calls] == [
        {
            "insertTable": {
                "rows": 1,
                "columns": 1,
                "location": {"index": 1, "tabId": "t.0"},
            }
        },
        {
            "insertText": {
                "location": {"index": 1, "tabId": "t.0"},
                "text": "refreshed",
            }
        },
    ]


@pytest.mark.asyncio
async def test_push_truncates_post_table_paragraph_ops_before_refresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = _FakeTransport()
    transport.raw_document = reindex_document(
        markdown_to_document(
            {"Tab_1": "alpha\n"},
            document_id="doc-5",
            title="Test",
            tab_ids={"Tab_1": "t.0"},
        )
    ).model_dump(by_alias=True, exclude_none=True)
    client = DocsClient(transport)
    monkeypatch.setattr(
        DocsClient,
        "diff",
        lambda _self, _folder: _diff_result_v2_refresh_with_post_table_style(),
    )

    refreshed = BatchUpdateDocumentRequest.model_validate(
        {
            "requests": [
                {
                    "insertText": {
                        "location": {"index": 1, "tabId": "t.0"},
                        "text": "refreshed",
                    }
                }
            ]
        }
    )

    def _fake_reconcile_v2(
        _base: Document,
        _desired: Document,
        transport_base: Document | None = None,
    ) -> list[BatchUpdateDocumentRequest]:
        _ = transport_base
        return [refreshed]

    monkeypatch.setattr("extradoc.client.reconcile_v2", _fake_reconcile_v2)

    result = await client.push(Path("/tmp/folder"))

    assert result.success is True
    assert transport.calls[0][1] == [
        {
            "insertText": {
                "location": {"index": 1, "tabId": "t.0"},
                "text": "Lists Revised\n",
            }
        },
        {
            "insertTable": {
                "rows": 1,
                "columns": 1,
                "location": {"index": 1, "tabId": "t.0"},
            }
        },
    ]


@pytest.mark.asyncio
async def test_push_truncates_post_page_break_ops_before_refresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = _FakeTransport()
    transport.raw_document = reindex_document(
        markdown_to_document(
            {"Tab_1": "alpha\n"},
            document_id="doc-6",
            title="Test",
            tab_ids={"Tab_1": "t.0"},
        )
    ).model_dump(by_alias=True, exclude_none=True)
    client = DocsClient(transport)
    monkeypatch.setattr(
        DocsClient,
        "diff",
        lambda _self, _folder: _diff_result_v2_refresh_with_post_page_break_insert(),
    )

    refreshed = BatchUpdateDocumentRequest.model_validate(
        {
            "requests": [
                {
                    "insertText": {
                        "location": {"index": 1, "tabId": "t.0"},
                        "text": "refreshed",
                    }
                }
            ]
        }
    )

    def _fake_reconcile_v2(
        _base: Document,
        _desired: Document,
        transport_base: Document | None = None,
    ) -> list[BatchUpdateDocumentRequest]:
        _ = transport_base
        return [refreshed]

    monkeypatch.setattr("extradoc.client.reconcile_v2", _fake_reconcile_v2)

    result = await client.push(Path("/tmp/folder"))

    assert result.success is True
    assert transport.calls[0][1] == [
        {
            "insertText": {
                "location": {"index": 1, "tabId": "t.0"},
                "text": "After Break\nClosing paragraph.",
            }
        },
        {
            "insertPageBreak": {
                "location": {"index": 1, "tabId": "t.0"},
            }
        },
    ]


@pytest.mark.asyncio
async def test_push_refreshes_v2_batches_after_insert_page_break(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = _FakeTransport()
    transport.raw_document = reindex_document(
        markdown_to_document(
            {"Tab_1": "alpha\n"},
            document_id="doc-7",
            title="Test",
            tab_ids={"Tab_1": "t.0"},
        )
    ).model_dump(by_alias=True, exclude_none=True)
    client = DocsClient(transport)
    monkeypatch.setattr(
        DocsClient,
        "diff",
        lambda _self, _folder: _diff_result_v2_refresh_with_post_page_break_insert(),
    )

    refreshed = BatchUpdateDocumentRequest.model_validate(
        {
            "requests": [
                {
                    "insertText": {
                        "location": {"index": 1, "tabId": "t.0"},
                        "text": "refreshed",
                    }
                }
            ]
        }
    )

    def _fake_reconcile_v2(
        _base: Document,
        _desired: Document,
        transport_base: Document | None = None,
    ) -> list[BatchUpdateDocumentRequest]:
        _ = transport_base
        return [refreshed]

    monkeypatch.setattr("extradoc.client.reconcile_v2", _fake_reconcile_v2)

    result = await client.push(Path("/tmp/folder"))

    assert result.success is True
    assert transport.get_document_calls == ["doc-6"]
    assert [call[1][0] for call in transport.calls] == [
        {
            "insertText": {
                "location": {"index": 1, "tabId": "t.0"},
                "text": "After Break\nClosing paragraph.",
            }
        },
        {
            "insertText": {
                "location": {"index": 1, "tabId": "t.0"},
                "text": "refreshed",
            }
        },
    ]


@pytest.mark.asyncio
async def test_push_refresh_uses_fetched_revision_id_for_followup_batches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = _FakeTransport()
    refreshed_doc = reindex_document(
        markdown_to_document(
            {"Tab_1": "alpha\n"},
            document_id="doc-4",
            title="Test",
            tab_ids={"Tab_1": "t.0"},
        )
    ).model_dump(by_alias=True, exclude_none=True)
    refreshed_doc["revisionId"] = "rev-1"
    transport.raw_document = refreshed_doc
    client = DocsClient(transport)
    monkeypatch.setattr(
        DocsClient,
        "diff",
        lambda _self, _folder: _diff_result_v2_refresh(),
    )

    refreshed = BatchUpdateDocumentRequest.model_validate(
        {
            "requests": [
                {
                    "insertText": {
                        "location": {"index": 1, "tabId": "t.0"},
                        "text": "refreshed",
                    }
                }
            ]
        }
    )

    def _fake_reconcile_v2(
        _base: Document,
        _desired: Document,
        transport_base: Document | None = None,
    ) -> list[BatchUpdateDocumentRequest]:
        _ = transport_base
        return [refreshed]

    monkeypatch.setattr("extradoc.client.reconcile_v2", _fake_reconcile_v2)

    result = await client.push(Path("/tmp/folder"))

    assert result.success is True
    assert transport.get_document_calls == ["doc-3"]
    assert transport.calls[0][2] == {"requiredRevisionId": "rev-0"}
    assert transport.calls[1][2] == {"requiredRevisionId": "rev-1"}
