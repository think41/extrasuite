"""Regression test capturing index-drift bug when multiple insertTable ops
are followed by insertText ops that target the newly created table cells.

BUG REPORT
==========
When pushing large edits to a Google Doc that involved adding multiple cost
tables in a document (a shared services contract), the reconciler emitted
835 operations in a single batch. The push failed with:

    Error: API error (400): {
      "error": {
        "code": 400,
        "message": "Invalid requests[200].insertText: The insertion index
                    must be inside the bounds of an existing paragraph.",
        "status": "INVALID_ARGUMENT"
      }
    }

ROOT CAUSE
==========
The reconciler emits multiple ``insertTable`` requests followed immediately by
``insertText`` requests to fill in the cell content of those tables. However,
``insertTable`` creates substantial structural overhead beyond the text content
— each cell boundary, row delimiter, and table-start/end marker consumes
additional index space in the live document.

In this scenario, three consecutive tables were inserted at positions near
index 11902 (ops 147, 169, 188 in the batch). Each ``insertTable`` call adds
structural bytes that shift all subsequent positions. The ``insertText`` ops
computed their target indices against the BASE document coordinates, not
accounting for the structural bytes introduced by the preceding
``insertTable`` ops.

By the time the API processes request[200] (``insertText`` at raw index
12198), the doc had shifted by more than the reconciler expected — the index
12198 no longer pointed inside an existing paragraph.

The ``simulate_ops_against_base`` oracle confirms: after un-shifting by the
cumulative plain-text delta, the index appears valid against the base segment
map. But the oracle only tracks text bytes, not structural table overhead.
This means the violation ONLY manifests as a live API 400, not in our
in-process validator.

WHAT THIS TEST CAPTURES
=======================
This test loads the real contract document (golden file
``18WZe578kHC0DP4Q1c-hhs15VWUJlFYNMvSwtzk-Wgbo.json``) and applies the same
edits that triggered the production failure: replacing placeholder org names
with real Bangalore-based organizations (BCDF and SBEET) and adding multiple
cost tables with INR amounts.

The test asserts that ``reconcile_batches`` produces a batch where the
flat request list contains MORE THAN 700 operations. This is the
symptom of the underlying issue: the reconciler generated a massive
single batch (835 ops) instead of splitting structural ops (``insertTable``)
into separate batches from the cell-fill ``insertText`` ops that follow.

The test is marked ``xfail(strict=True)`` to document the known failure.
When fixed, remove the xfail marker and convert this into a passing
regression guard.

SUGGESTED FIX
=============
The reconciler should either:

1. Emit each ``insertTable`` in its own batch, followed in the next batch by
   the ``insertText`` ops that fill its cells. The executor resolves deferred
   placeholders between batches, so structural shifts are absorbed before the
   cell-fill ops run.

2. Track the structural byte overhead of each ``insertTable`` op (which the
   Google Docs API documents as: rows x columns x 3 bytes per cell + 1 byte
   per table + 1 byte per row) and apply that offset when computing
   subsequent ``insertText`` locations within cells of those tables.

Option 1 is safer and aligns with the existing multi-batch design.

See: https://github.com/think41/extrasuite/issues (index-drift on multi-table push)
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from extradoc.api_types._generated import Document
from extradoc.comments._types import DocumentWithComments, FileComments
from extradoc.reconcile_v3.api import reconcile_batches
from extradoc.serde.markdown import MarkdownSerde

GOLDEN_DIR = Path(__file__).parent.parent / "golden"
CONTRACT_BASE_ID = "18WZe578kHC0DP4Q1c-hhs15VWUJlFYNMvSwtzk-Wgbo"
EDITED_TAB_MD = Path(__file__).parent / "contract_edited_tab.md"

_serde = MarkdownSerde()


def _load_base() -> Document:
    path = GOLDEN_DIR / f"{CONTRACT_BASE_ID}.json"
    return Document.model_validate(json.loads(path.read_text()))


def _bundle(doc: Document) -> DocumentWithComments:
    return DocumentWithComments(
        document=doc,
        comments=FileComments(file_id=doc.document_id or ""),
    )


def _flatten_requests(batches: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for batch in batches:
        for req in batch.requests or []:
            out.append(req.model_dump(by_alias=True, exclude_none=True))
    return out


def _count_insert_tables(reqs: list[dict[str, Any]]) -> int:
    return sum(1 for r in reqs if "insertTable" in r)


def _batches_with_multiple_insert_tables(
    batches: list[Any],
) -> list[int]:
    """Return indices (into batches) of any batch that contains MORE THAN ONE
    ``insertTable`` op in the same request list.

    The root cause of index drift: when N > 1 ``insertTable`` ops appear in
    the same batch, each table's structural overhead (cell/row/table boundary
    bytes) shifts all subsequent indices.  The cell-fill ``insertText`` ops for
    tables 2..N were computed against base-doc coordinates that do not include
    this overhead, so their indices become stale.

    A batch with exactly ONE ``insertTable`` followed by its own cell-fill
    ``insertText`` ops is safe: within that batch the ``insertTable`` runs
    first and all subsequent ops address positions that are well-defined
    relative to the freshly created table skeleton.

    A batch with MULTIPLE ``insertTable`` ops is unsafe: each table adds
    structural overhead that shifts every later index in the batch, including
    the cell-fill ops for subsequent tables.
    """
    bad: list[int] = []
    for bi, batch in enumerate(batches):
        reqs = [
            r.model_dump(by_alias=True, exclude_none=True)
            for r in (batch.requests or [])
        ]
        n_insert_tables = sum(1 for r in reqs if "insertTable" in r)
        if n_insert_tables > 1:
            bad.append(bi)
    return bad


def test_multi_table_insert_does_not_produce_oversized_single_batch(
    tmp_path: Path,
) -> None:
    """Regression test: contract with multiple added cost tables must isolate
    each ``insertTable`` op in its own batch.

    The production failure was:

        Error: API error (400): Invalid requests[200].insertText:
        The insertion index must be inside the bounds of an existing paragraph.

    in a batch of 835 ops. The root cause: three ``insertTable`` ops (at
    positions 147, 169, 188 in the batch) were followed by ``insertText``
    cell-fill ops — including request[200] — in the SAME batch. Each
    ``insertTable`` call adds structural overhead bytes (cell boundary markers,
    row delimiters, table-start/end markers) that shift all subsequent indices
    in the batch. The cell-fill ``insertText`` ops for tables 2 and 3 were
    computed against base-doc coordinates that did not include this overhead,
    so by request[200] the cumulative structural shift had moved the target
    paragraph out of range.

    The fix: ``lower_batches`` splits batch1 at every ``insertTable`` boundary.
    Each ``insertTable`` and its immediately following cell-fill ops form a
    separate batch.  A batch with exactly one ``insertTable`` is self-consistent:
    the table skeleton is created first, and all cell-fill ``insertText`` ops
    address positions relative to that fresh skeleton.

    This test verifies that:
    1. The scenario produces >= 3 ``insertTable`` ops (precondition).
    2. No batch contains more than one ``insertTable`` op (the invariant).
    """
    folder = tmp_path / "contract"

    # Serialize the base document to a markdown folder.
    base_doc = _load_base()
    _serde.serialize(_bundle(base_doc), folder)

    # Identify the tab markdown file (should be a single tab document).
    tab_files = list((folder / "tabs").glob("*.md"))
    assert len(tab_files) >= 1, f"expected at least one tab file, got: {tab_files}"
    tab_md = tab_files[0]

    # Replace the pristine tab content with the edited version (the contract
    # edits that triggered the production 400: new org names + cost tables).
    shutil.copy(EDITED_TAB_MD, tab_md)

    # Deserialize (3-way merge) to produce base + desired documents.
    result = _serde.deserialize(folder)
    batches = reconcile_batches(result.base.document, result.desired.document)
    flat_reqs = _flatten_requests(batches)

    # ------------------------------------------------------------------
    # Precondition: >= 3 insertTable ops must be present.
    # ------------------------------------------------------------------
    n_insert_tables = _count_insert_tables(flat_reqs)
    assert n_insert_tables >= 3, (
        f"precondition: expected >= 3 insertTable ops in the scenario; got {n_insert_tables}. "
        "The edited markdown may not have been applied correctly."
    )

    # ------------------------------------------------------------------
    # Invariant: no batch may contain more than one insertTable op.
    #
    # Each insertTable adds structural overhead bytes that shift all
    # subsequent indices in the same batch.  Cell-fill insertText ops for
    # table N+1 were computed without accounting for table N's overhead.
    # Isolating each insertTable in its own batch makes each batch
    # self-consistent: the single insertTable runs first, then its own
    # cell-fill ops address positions relative to the freshly created
    # skeleton — no stale-index hazard.
    # ------------------------------------------------------------------
    bad_batches = _batches_with_multiple_insert_tables(batches)
    assert bad_batches == [], (
        f"reconciler emitted {len(bad_batches)} batch(es) with multiple insertTable ops "
        f"(batch indices: {bad_batches}). "
        f"Total ops across all batches: {len(flat_reqs)} "
        f"({n_insert_tables} insertTable ops). "
        "Each insertTable must be in its own batch to prevent index drift."
    )
