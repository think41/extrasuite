from __future__ import annotations

from pathlib import Path

import pytest

from extradoc.api_types._generated import BatchUpdateDocumentRequest, Document
from extradoc.client import (
    RECONCILER_ENV_VAR,
    DiffResult,
    DocsClient,
    _get_reconciler_version,
    _normalize_raw_base_para_styles,
)
from extradoc.comments._types import CommentOperations
from extradoc.reconcile import reindex_document
from extradoc.reconcile_v2.executor import BatchExecutionResult
from extradoc.serde import serialize
from extradoc.serde._from_markdown import markdown_to_document


class _FakeTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[dict], dict | None]] = []

    async def batch_update(
        self,
        document_id: str,
        requests: list[dict],
        write_control: dict | None = None,
    ) -> dict:
        self.calls.append((document_id, requests, write_control))
        return {"replies": []}

    async def get_document(self, document_id: str) -> object:  # pragma: no cover
        raise NotImplementedError

    async def list_comments(self, file_id: str) -> list[dict]:  # pragma: no cover
        raise NotImplementedError

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
    assert any(request.create_paragraph_bullets for request in requests)
    assert any(request.update_paragraph_style for request in requests)
    assert any(
        request.create_named_range
        and request.create_named_range.range.start_index
        < request.create_named_range.range.end_index
        for request in requests
    )


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
