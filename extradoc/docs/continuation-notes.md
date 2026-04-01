# Continuation Notes — extradoc reconcile_v2 + XML/Markdown

**Audience**: Architect familiar with Google Docs API.

---

## The Architecture in One Paragraph

`pull` stores `./raw/document.json` (live API response). From this we construct a **base Document**.
`push` reconstructs a **desired Document** from the edited on-disk files. `reconcile_v2` computes the diff between base and desired, lowers it to `batchUpdate` request batches, and executes them.

The only difference between the XML and markdown paths is how the desired Document is constructed. The entire reconciler pipeline — IR, diff, lower, batch, execute — is shared.

---

## Reconcile_v2 Layer Map

```
serde/{_from_xml,_from_markdown}.py  →  desired Document
raw/document.json                    →  base Document (transport_base)
                                              ↓
reconcile_v2/canonical.py            strip carrier paragraphs, normalize
reconcile_v2/diff.py                 semantic IR diff → list[SemanticEdit]
reconcile_v2/lower.py                SemanticEdit → request dicts (one batch, shadow doc)
reconcile_v2/batches.py              multi-batch planning: tab creation → attachments
                                     → content → footnotes → named ranges
client.py                            live-refresh executor
```

Key invariant: `lower.py` uses the **raw transport base** for index arithmetic, not the canonical IR.

---

## The Mock is Not the Truth

`src/extradoc/mock/` does not replicate real UTF-16 index side effects after structural ops. A fix proven only against the mock is not proven. Live fixtures win.

---

## Current Live State (as of 2026-04-01, checkpoint after table reconciler work)

| Scenario | Status |
|---|---|
| Markdown multi-tab create + edit | **Broken** — separate issue, not addressed here |
| XML minimal (heading + para) | **Proven live** |
| XML heading + list + page break (no table) | **Proven live** |
| XML with simple table (no page break) | **Proven live** — converges in one cycle |
| XML page break + table together | **Failing** — not yet addressed |
| Table: add/delete single row | **Proven live** |
| Table: add 2+ rows at once | **Proven live** |
| Table: cell edits + row insert + column delete in one push | **Proven live** |

---

## Two Experiments Completed — Consequences

### Experiment 1: Revision mismatch on push (commit `4ccdf87`)

**Finding**: `_execute_document_batches_v2_live_refresh` was silently re-fetching the document and re-planning when a `requiredRevisionId` mismatch (HTTP 400) occurred. This is a concurrent-edit scenario — another party modified the document after the base was pulled. Transparent recovery is wrong: the agent's edits may now be based on stale state.

**Change made**: The 400 mismatch now raises `DocumentConflictError` (new exception in `transport.py`, exported from `__init__.py`). The caller must re-pull, merge, and push again. The test `test_execute_v2_live_refresh_recovers_from_revision_mismatch` was renamed and inverted to `test_execute_v2_live_refresh_raises_on_revision_mismatch`.

**Consequence**: There are now two remaining reasons the executor calls `get_document` after `batchUpdate`:
1. **Structural ops** (`insertTable`, `insertPageBreak`) — the code truncates the batch, calls `get_document`, and re-plans. This is Trigger 1 and is the target of Experiment 2.
2. **Delete-then-reinsert** (`delete-only` refresh reason) — `deleteContentRange` followed by insertions whose indices were computed pre-delete. Still requires a re-fetch; not addressed yet.

### Experiment 2: Table index prediction (commit `e5a55cf`)

**Hypothesis**: After `insertTableRow`, `deleteTableRow`, `insertTableColumn`, `deleteTableColumn`, the resulting cell indices are fully deterministic and can be predicted without re-fetching the document.

**Proof**: Added `./extrasuite docs verify-table-indices <url>` (in `client/src/extrasuite/client/cli/doc.py`). The command:
1. Creates a 3×3 table with variable-length cell content in a live Google Doc
2. Applies each structural operation
3. Compares predicted indices against the API response

**Result: 16/16 PASS** across all row/column insert/delete scenarios including 3 chained multi-op cases.

**Index arithmetic formulas** (proven correct, implemented in `doc.py` as `_predict_insert_row`, `_predict_delete_row`, `_predict_insert_column`, `_predict_delete_column`):

- Table opener: 1 char. Table closer: 1 char. `table.endIndex = last_row.endIndex + 1`.
- Row opener: 1 char. `row[n+1].startIndex = row[n].endIndex`. No row closer.
- Cell opener: 1 char. `cell[n+1].startIndex = cell[n].endIndex`. Content starts at `cell.startIndex + 1`.
- Blank cell span: 2 (1 opener + 1 `\n`).
- `insertTableRow(rowIndex=R, insertBelow=False)`: new blank row at R, span = `1 + ncols*2`. All rows ≥ R shift by that span.
- `insertTableRow(rowIndex=R, insertBelow=True)`: new row after R. All rows > R shift.
- `deleteTableRow(rowIndex=R)`: remove row, shift all rows > R by `-deleted_row_span`.
- `insertTableColumn(columnIndex=C, insertRight=False)`: new blank cell at col C in every row. Since rows are sequential, row r accumulates `r*2` shift from insertions in rows 0..r-1.
- `deleteTableColumn(columnIndex=C)`: each row r has cell[C] removed; subsequent rows accumulate negative shift.

**Consequence**: The structural re-fetch after `insertTable`/`insertPageBreak` in `client.py` can be eliminated. Instead of re-fetching and re-planning, the reconciler should emit all operations (structural + cell content) in one or two deterministic batches, using these formulas to predict cell indices before any API call is made.

---

## Path Forward

### Step 1: DONE — Table reconciler fixes

Five bugs fixed in `diff.py` and `lower.py`:

1. **`_table_anchor_signature`** — removed `len(table.rows)` so tables with row count changes are still recognised as the same body-level anchor (no flat delete+reinsert fallback).
2. **`_diff_section_tables`** — when `_plan_table_comparison` raises `UnsupportedReconcileV2Error` (>±1 change), now calls `diff_tables()` from `table_diff.py` instead of falling back to delete+reinsert.
3. **`InsertTableRowEdit` iteration order** — reversed `inserted_cells` loop (last column first) so earlier insertions don't corrupt later cell indices in the same batch.
4. **Terminal row insert anchor** — new last-row inserts now use `table.end_index + 1` as the cell-0 anchor instead of raising `UnsupportedReconcileV2Error`.
5. **Shadow layout for anchor lookup** — switched non-terminal row/column insert anchor lookups from `story_layouts` (base) to `current_story_layouts` (shadow) so consecutive inserts in one batch correctly anchor to previously-inserted rows.

Proven live in one push cycle:
- Add/delete single row
- Add 2+ rows at once
- Cell edits + row insert + column delete together

### Step 2: Eliminate the structural re-fetch in `client.py`

`insertTableRow` / `deleteTableRow` / `insertTableColumn` / `deleteTableColumn` do **not** trigger the structural re-fetch (that is only `insertTable` and `insertPageBreak`). The row/column ops already converge in one cycle without any re-fetch.

The remaining re-fetch cases are:
1. **`insertTable` / `insertPageBreak`** — still triggers `_refresh_v2_batches_after_structural_ops`. Now that tables converge via row/column ops instead of delete+reinsert, this path fires less often but is not yet eliminated.
2. **`delete-only` refresh** — `deleteContentRange` followed by inserts whose indices were computed pre-delete. Not yet addressed.

### Step 3: Prove broader convergence

- XML page break + table together — still failing
- Full structural XML smoke (`scripts/release_smoke_docs.py`)
- Markdown table row insert/delete

---

## Key Code Locations

| Purpose | File |
|---|---|
| Client orchestration + live-refresh executor | `src/extradoc/client.py` |
| Public reconcile_v2 entry point | `src/extradoc/reconcile_v2/api.py` |
| Semantic diff (table anchor signature bug here) | `src/extradoc/reconcile_v2/diff.py` |
| Table diff algorithm (new, not yet integrated) | `src/extradoc/reconcile_v2/table_diff.py` |
| Lowering (single batch + shadow doc) | `src/extradoc/reconcile_v2/lower.py` |
| Multi-batch planning | `src/extradoc/reconcile_v2/batches.py` |
| Table index prediction formulas (proven live) | `client/src/extrasuite/client/cli/doc.py` (`_predict_*` functions) |
| Live fixture capture script | `scripts/capture_reconcile_v2_fixtures.py` |
| Live smoke runner | `scripts/release_smoke_docs.py` |
| Fixture pairs | `tests/reconcile_v2/fixtures/` |

---

## How to Run Tests

```bash
cd extradoc
uv run pytest tests/ -x -q          # fast suite (use --no-verify for commits, mypy has 757 pre-existing errors)
uv run pytest tests/reconcile_v2/ -v  # higher-signal fixture-backed tests
uv run python scripts/release_smoke_docs.py  # live smoke (needs auth)
```

**Warning**: Tests outside `tests/reconcile_v2/` have stale exact-shape expectations. Failures there may not be live regressions. Verify against a live doc before treating as a bug.
