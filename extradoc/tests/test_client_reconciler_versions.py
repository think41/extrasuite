from __future__ import annotations

import json
from pathlib import Path

import pytest

from extradoc.api_types._generated import BatchUpdateDocumentRequest, Document
from extradoc.client import (
    RECONCILER_ENV_VAR,
    DiffResult,
    DocsClient,
    _get_reconciler_version,
    _normalize_raw_base_para_styles,
    _should_refresh_v2_batches,
    _tab_ids_subset,
    _truncate_batch_before_post_table_para_ops,
)
from extradoc.comments._types import (
    CommentOperations,
    DocumentWithComments,
    FileComments,
)
from extradoc.reconcile import reindex_document
from extradoc.reconcile_v2.errors import UnsupportedSpikeError
from extradoc.reconcile_v2.executor import BatchExecutionResult
from extradoc.serde import serialize
from extradoc.serde._from_markdown import markdown_to_document


class _FakeTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[dict], dict | None]] = []
        self.get_document_calls: list[str] = []
        self.raw_document: dict | None = None

    async def batch_update(
        self,
        document_id: str,
        requests: list[dict],
        write_control: dict | None = None,
    ) -> dict:
        self.calls.append((document_id, requests, write_control))
        return {"replies": []}

    async def get_document(self, document_id: str) -> object:
        self.get_document_calls.append(document_id)
        if self.raw_document is None:
            raise NotImplementedError
        from extradoc.transport import DocumentData

        return DocumentData(document_id=document_id, title="Test", raw=self.raw_document)

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


def test_should_refresh_v2_batches_only_for_insert_table() -> None:
    assert _should_refresh_v2_batches(
        [{"insertTable": {"rows": 1, "columns": 1, "location": {"index": 1, "tabId": "t.0"}}}]
    )
    assert not _should_refresh_v2_batches(
        [{"insertText": {"location": {"index": 1, "tabId": "t.0"}, "text": "x"}}]
    )


def test_truncate_batch_before_post_table_para_ops() -> None:
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

    assert _truncate_batch_before_post_table_para_ops(batch) == batch[:3]


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
    first_batch = result.batches[0].model_dump(by_alias=True, exclude_none=True, mode="json")
    second_batch = result.batches[1].model_dump(by_alias=True, exclude_none=True, mode="json")
    assert first_batch == {
        "requests": [
            {
                "deleteContentRange": {
                    "range": {"startIndex": 497, "endIndex": 515, "tabId": "t.0"}
                }
            },
            {
                "insertText": {
                    "location": {"index": 497, "tabId": "t.0"},
                    "text": '    return "blue"',
                }
            },
            {
                "updateTextStyle": {
                    "range": {"startIndex": 497, "endIndex": 514, "tabId": "t.0"},
                    "textStyle": {
                        "fontSize": {"magnitude": 10.0, "unit": "PT"},
                        "weightedFontFamily": {"fontFamily": "Courier New"},
                    },
                    "fields": "fontSize,weightedFontFamily",
                }
            },
        ]
    }
    assert second_batch == {
        "requests": [
            {
                "deleteContentRange": {
                    "range": {"startIndex": 520, "endIndex": 558, "tabId": "t.0"}
                }
            },
            {
                "insertText": {
                    "location": {"index": 520, "tabId": "t.0"},
                    "text": '{"stage": "edited", "verified": false}',
                }
            },
            {
                "updateTextStyle": {
                    "range": {"startIndex": 520, "endIndex": 558, "tabId": "t.0"},
                    "textStyle": {
                        "fontSize": {"magnitude": 10.0, "unit": "PT"},
                        "weightedFontFamily": {"fontFamily": "Courier New"},
                    },
                    "fields": "fontSize,weightedFontFamily",
                }
            },
        ]
    }


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
        UnsupportedSpikeError,
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
