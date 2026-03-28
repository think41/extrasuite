from __future__ import annotations

from pathlib import Path

import pytest

from extradoc.api_types._generated import BatchUpdateDocumentRequest
from extradoc.client import (
    RECONCILER_ENV_VAR,
    DiffResult,
    DocsClient,
    _get_reconciler_version,
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


def test_get_reconciler_version_defaults_to_v1(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(RECONCILER_ENV_VAR, raising=False)
    assert _get_reconciler_version() == "v1"


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


def test_diff_can_use_reconcile_v2_via_env_var(
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

    monkeypatch.setenv(RECONCILER_ENV_VAR, "v2")

    client = DocsClient.__new__(DocsClient)
    result = client.diff(str(folder))

    assert result.reconciler_version == "v2"
    assert result.batches


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
