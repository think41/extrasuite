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

## Current Live State (as of 2026-04-01, checkpoint `e5a55cf`)

| Scenario | Status |
|---|---|
| Markdown multi-tab create + edit | **Broken** — see regression below |
| XML minimal (heading + para) | **Proven live** |
| XML heading + list + page break (no table) | **Proven live** |
| XML with simple table (no page break) | **Partial** — shell created, cells empty first cycle |
| XML page break + table together | **Failing** |

### Open regression: `_table_anchor_signature` includes row count

`./extrasuite doc diff <any-md-doc-with-table-row-change>` fails:

```
Error: reconcile_v2 iterative content planning could not lower the remaining mixed body rewrite
```

Root cause: `_table_anchor_signature` in `diff.py` (~line 1081) includes `len(table.rows)`. When a table gains or loses a row, the signature changes → flat fallback → `DeleteTableBlockEdit` + `InsertTableBlockEdit` → iterative planner triggers → fails.

**Fix**: Drop `len(table.rows)` from the signature. Keep column count from the first row and `pinned_header_rows`. Row count is not an identity property.

```python
# AFTER
def _table_anchor_signature(table: TableIR) -> tuple[object, ...]:
    first_row = table.rows[0] if table.rows else None
    return (
        "table",
        len(first_row.cells) if first_row else 0,
        tuple((cell.row_span, cell.column_span) for cell in (first_row.cells if first_row else [])),
        table.pinned_header_rows,
    )
```

This must be fixed before the bigger table integration work below.

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

### Step 1: Fix the open regression (prerequisite)

Fix `_table_anchor_signature` as described above. Without this, markdown docs with any table row change are broken. Validate:
```bash
cd extradoc
uv run pytest tests/ -x -q
./extrasuite docs diff md-test   # should produce InsertTableRowEdit, not error
```

### Step 2: Integrate `table_diff.py` into the reconciler

`reconcile_v2/table_diff.py` (commit `1da82ce`) has `match_tables()` and `diff_tables()` that produce `InsertTableRowEdit` / `DeleteTableRowEdit` / `InsertTableColumnEdit` / `DeleteTableColumnEdit`. This needs to replace `_table_anchor_signature` + `_diff_section_tables` in `diff.py`.

The integration must handle the identity-matching improvement: use cell-hash similarity (`table_similarity()`) instead of the current signature-based approach so tables with row/column changes are matched correctly rather than treated as delete+reinsert.

### Step 3: Eliminate the structural re-fetch in `client.py`

Once the reconciler emits correct row/column edits (Step 2), the cell content edits that follow can be expressed using the deterministic index formulas above. The goal is:

1. `diff.py` / `lower.py` emit structural ops (insertTableRow etc.) AND subsequent cell content ops (insertText into new cells) in the same lowered batch.
2. The cell content indices are computed using the prediction formulas — **no `get_document` call needed**.
3. Remove `_truncate_batch_for_live_refresh` logic for the `structural` case in `client.py`.

The delete-then-reinsert re-fetch (`delete-only` reason) is a separate concern and should not be conflated with this work.

### Step 4: Prove live convergence

After Steps 2–3:
- XML simple table (no page break) must converge in one cycle
- XML table + page break must converge
- Full structural XML smoke (`scripts/release_smoke_docs.py`)
- Markdown table row insert/delete must converge

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
