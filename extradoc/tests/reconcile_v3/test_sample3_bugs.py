"""Regression tests for bugs #64 and #65 on the sample3 golden document.

Both tests use the ``1YKyqqH8wZa3kSnoBEdlwAumI94gRivSsZB1qvc9y4CA`` golden
(docs title "sample3"). They follow the same pattern used by peer golden-based
tests in ``extradoc/tests/``:

1. Load the golden JSON into a typed ``Document``.
2. Serialize to a markdown folder via ``MarkdownSerde``.
3. Apply a targeted edit to ``tabs/Tab_1.md``.
4. Deserialize (3-way merge) to get ``base`` and ``desired`` documents.
5. Run ``reconcile_batches`` to get the live API ``batchUpdate`` requests.
6. Assert on the generated requests (bug #64) or apply them via
   ``MockGoogleDocsAPI`` + re-serialize and assert on the resulting markdown
   (bug #65).

These tests are marked ``xfail(strict=True)`` — they must fail today and will
be un-xfailed after the fixes land.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from extradoc.api_types._generated import Document
from extradoc.comments._types import DocumentWithComments, FileComments
from extradoc.mock.api import MockGoogleDocsAPI
from extradoc.reconcile_v3.api import reconcile_batches
from extradoc.reconcile_v3.executor import resolve_deferred_placeholders
from extradoc.serde.markdown import MarkdownSerde

from .helpers import assert_batches_within_base

GOLDEN_DIR = Path(__file__).parent.parent / "golden"
SAMPLE3_ID = "1YKyqqH8wZa3kSnoBEdlwAumI94gRivSsZB1qvc9y4CA"

_serde = MarkdownSerde()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_golden() -> Document:
    path = GOLDEN_DIR / f"{SAMPLE3_ID}.json"
    return Document.model_validate(json.loads(path.read_text()))


def _bundle(doc: Document) -> DocumentWithComments:
    return DocumentWithComments(
        document=doc,
        comments=FileComments(file_id=doc.document_id or ""),
    )


def _pull_to_markdown(folder: Path) -> Document:
    doc = _load_golden()
    _serde.serialize(_bundle(doc), folder)
    return doc


def _edit_tab1(folder: Path, *, find: str, replace: str) -> None:
    tab_md = folder / "tabs" / "Tab_1.md"
    content = tab_md.read_text(encoding="utf-8")
    assert find in content, f"precondition: {find!r} not found in Tab_1.md"
    tab_md.write_text(content.replace(find, replace), encoding="utf-8")


def _request_types(batches: list[Any]) -> list[str]:
    types: list[str] = []
    for batch in batches:
        for req in batch.requests or []:
            d = req.model_dump(by_alias=True, exclude_none=True)
            types.extend(d.keys())
    return types


def _apply_batches_via_mock(base: Document, batches: list[Any]) -> Document:
    """Apply reconcile batches to ``base`` using the mock API and return the result."""
    mock = MockGoogleDocsAPI(base)
    responses: list[dict[str, Any]] = []
    for batch in batches:
        resolved = resolve_deferred_placeholders(responses, batch)
        resp = mock.batch_update(resolved)
        responses.append(resp.model_dump(by_alias=True, exclude_none=True))
    return mock.get()


# ---------------------------------------------------------------------------
# Bug #64: simple-table cell edit must not delete+recreate a row
# ---------------------------------------------------------------------------


def test_bug64_simple_table_cell_edit_no_row_ops(tmp_path: Path) -> None:
    """Editing a single JAWS row cell in the simple table must not emit any
    insertTableRow / deleteTableRow requests.

    The simple table in the sample3 golden has a JAWS row rendered as:
        | **JAWS** | **900** | **52%**  |

    Changing just the two numeric cells should be expressible as targeted
    text replacements inside existing cells; the reconciler currently falls
    back to delete-row + insert-row because the fuzzy-LCS similarity for the
    edited row drops below threshold.
    """
    folder = tmp_path / "doc"
    _pull_to_markdown(folder)

    _edit_tab1(
        folder,
        find="| **JAWS** | **900** | **52%**  |",
        replace="| **JAWS** | **950** | **55%**  |",
    )

    result = _serde.deserialize(folder)
    batches = reconcile_batches(result.base.document, result.desired.document)
    assert_batches_within_base(result.base.document, batches)
    types = _request_types(batches)

    assert "insertTableRow" not in types, (
        f"unexpected insertTableRow for a pure cell-text edit; request types: {types}"
    )
    assert "deleteTableRow" not in types, (
        f"unexpected deleteTableRow for a pure cell-text edit; request types: {types}"
    )


# ---------------------------------------------------------------------------
# Bug #65: inline x-colbreak must not relocate on surrounding-paragraph edit
# ---------------------------------------------------------------------------


def test_bug65_colbreak_preserved_on_columns_text_edit(tmp_path: Path) -> None:
    """Editing the Columns paragraph text must not relocate the x-colbreak.

    In the sample3 golden, the Columns section ends with an x-colbreak
    paragraph directly after the "This is an example of columns..." paragraph.
    Editing an unrelated word in that paragraph must not move the
    ``<x-colbreak/>`` marker away from its original position (directly after
    the Columns paragraph) — it must not end up floating at the end of the
    tab or be dropped entirely.
    """
    folder = tmp_path / "doc"
    _pull_to_markdown(folder)

    # Capture the original colbreak position (line index relative to the
    # trailing content) before the edit.
    original_md = (folder / "tabs" / "Tab_1.md").read_text(encoding="utf-8")
    original_lines = original_md.splitlines()
    original_colbreak_lines = [
        i for i, line in enumerate(original_lines) if "<x-colbreak/>" in line
    ]
    assert original_colbreak_lines, "precondition: golden must contain <x-colbreak/>"
    # The colbreak is mid-tab: must have non-empty content AFTER it in the original.
    # (It lives right after the Columns paragraph, not as the final line.)
    first_colbreak_line = original_colbreak_lines[0]
    trailing_original = "\n".join(original_lines[first_colbreak_line + 1 :]).strip()

    _edit_tab1(
        folder,
        find="Clearly, that is not accessible.",
        replace="Obviously, that is not accessible.",
    )

    result = _serde.deserialize(folder)
    batches = reconcile_batches(result.base.document, result.desired.document)
    assert_batches_within_base(result.base.document, batches)

    # Apply via mock API and re-serialize to markdown.
    try:
        after_doc = _apply_batches_via_mock(result.base.document, batches)
    except Exception as exc:
        pytest.fail(
            f"mock API rejected reconcile output for a simple paragraph edit: {exc!r}"
        )

    out_folder = tmp_path / "doc_after"
    _serde.serialize(_bundle(after_doc), out_folder)
    after_md = (out_folder / "tabs" / "Tab_1.md").read_text(encoding="utf-8")
    after_lines = after_md.splitlines()

    after_colbreak_lines = [
        i for i, line in enumerate(after_lines) if "<x-colbreak/>" in line
    ]
    assert after_colbreak_lines, "x-colbreak disappeared entirely after reconcile+apply"
    first_after = after_colbreak_lines[0]
    trailing_after = "\n".join(after_lines[first_after + 1 :]).strip()

    # The colbreak must remain mid-tab (same non-empty trailing content after
    # it as the original), not be relocated to the very end of the tab.
    assert trailing_after == trailing_original, (
        "x-colbreak relocated after a paragraph text edit.\n"
        f"original trailing after colbreak: {trailing_original!r}\n"
        f"after reconcile trailing: {trailing_after!r}"
    )
