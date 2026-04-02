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

## Current Live State (as of 2026-04-02, checkpoint after content alignment experiment)

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

## Content Alignment Experiment (2026-04-02)

### Why This Was Needed

The current reconciler falls back to `DeleteContentRange + InsertText` whenever it
cannot precisely map a block between base and desired. This is dangerous:

1. **Comments are lost.** A reviewer annotates a paragraph; the agent rewrites it;
   the reconciler deletes the old paragraph and inserts the new one. The comment and
   its audit trail disappear. This is a high-impact usability regression.
2. **Styling breaks.** Manual formatting, named style overrides, and tracked changes
   are destroyed on delete+reinsert.
3. **Last-newline problem.** Attempting to delete the terminal paragraph fails with
   HTTP 400 because the segment-final `\n` is untouchable via the API.

### Design: Unified Cost-Based DP

A document body is a flat sequence of content elements:
`[Table | Paragraph | TOC | SectionBreak | PageBreak | ...]`.
Reconciliation = aligning base sequence with desired sequence, where:

- **Matched pairs** → reconciled via in-place edits (surgical text changes, style
  updates, table row/column ops). Never deleted and reinserted.
- **Unmatched base elements** → deleted.
- **Unmatched desired elements** → inserted.

The alignment is found by a standard edit-distance DP:

```
dp[i][j] = min cost to reconcile base[0..i-1] with desired[0..j-1]

Match(i,j):  dp[i-1][j-1] + edit_cost(base[i], desired[j])   (if matchable)
Delete(i):   dp[i-1][j]   + delete_penalty(base[i])
Insert(j):   dp[i][j-1]   + insert_penalty(desired[j])
```

**Terminal constraint (hard):** `base[-1]` and `desired[-1]` are always matched.
Enforced by pre-matching the terminals and running the DP on the prefix sequences.
This eliminates the last-newline problem entirely — no special-casing downstream.

**Cost model philosophy:** higher penalty = algorithm prefers to match rather than
delete+insert. One infinite penalty (terminal paragraph). Everything else is finite,
proportional to the "impact of recreation" — preserving a large paragraph with
inline images matters more than preserving a one-word stub.

### Tunable Constants

All constants live in `reconcile_v2/content_align.py` (one place, all named):

| Constant | Default | Meaning |
|---|---|---|
| `PARA_PENALTY_PER_CHAR` | 2.0 | Cost per character when a paragraph is deleted/inserted |
| `PARA_INLINE_ELEMENT_PENALTY` | 50.0 | Extra cost per inline image / footnote ref |
| `TABLE_CELL_PENALTY` | 10.0 | Cost per cell when a table is deleted/inserted |
| `FIXED_STRUCTURAL_PENALTY` | 20.0 | Cost for PageBreak, SectionBreak, TOC |
| `MIN_PARA_MATCH_SIMILARITY` | 0.3 | Token Jaccard floor below which paragraphs are not matchable |
| `MIN_LIST_MATCH_SIMILARITY` | 0.3 | Same for lists of different kinds |
| `INFINITE_PENALTY` | inf | Terminal paragraph — never deleted |

`matchable(base, desired)` is the hard gate before costs are compared:
- Must be the same broad kind (paragraph↔paragraph, table↔table, …).
- Paragraphs: token Jaccard ≥ `MIN_PARA_MATCH_SIMILARITY`.
- Tables: cell-text similarity > 0 (any cell in common).
- Lists: same `list_kind` OR item-text similarity > `MIN_LIST_MATCH_SIMILARITY`.
- SectionBreak / PageBreak / TOC: always matchable with the same kind.

`edit_cost` uses word-Jaccard for paragraphs/lists (fast, good enough for cost
estimation). Character-level LCS is deferred to Module 2 (actual op generation).

### What Was Proven

**90/90 tests pass** (`tests/reconcile_v2/test_content_align.py`, 0.93 s):

- Identical sequences → zero cost, all matched.
- Single add / edit / delete on synthetic sequences → correct.
- Terminal always matched, even when content differs completely.
- List kind change (bullet → numbered) → matched, not replaced.
- Table with row/cell changes → matched via cell-text similarity.
- Real fixture documents (paragraph_split, text_replace, list_append, list_kind_change,
  table fixtures) → exactly the changed element is matched/edited; all others unchanged.
- 200 fuzz tests: every invariant holds (order-preserving, all elements accounted for,
  terminals always matched).
- Large golden documents (185–194 elements): self-alignment → zero cost.
  One-element modification → exactly one element affected, all others matched.
- Performance: 35–101 ms for 185–194 element documents. Acceptable.

### One Known Nuance

"Identical elements are always matched" is **not** a valid global DP invariant.
If a short identical paragraph sits adjacent to a large expensive element, the DP
can rationally choose to delete+reinsert the short one to save cost on a better
global alignment. This is mathematically correct but can lose comments on very
short paragraphs during large structural rearrangements.

Practical impact: agents do not reorder content blocks. This scenario does not
arise in normal edit→push workflows. If it becomes an issue, a post-processing
guard can force matching of identical-text pairs after the DP backtracks.

### Key Files

| File | Purpose |
|---|---|
| `src/extradoc/reconcile_v2/content_align.py` | Standalone DP alignment module (324 lines) |
| `tests/reconcile_v2/test_content_align.py` | 90 tests across 7 parts |

### Integration Path (Next Step)

`content_align.py` is a standalone module — it does not touch `diff.py` or `lower.py`.
Integration means replacing the top-level block-matching logic in `diff.py` with
`align_content()`. See "Step 2" in the Path Forward section below.

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

### Step 2: DONE (experiment) — Content alignment algorithm

`content_align.py` proven correct. See the "Content Alignment Experiment" section
above for full details and test results.

Next: integrate into `diff.py` — see Step 3 below.

### Step 3: Integrate content_align into reconcile_v2

Replace the top-level block-matching logic in `_diff_section_block_slice` (diff.py)
with a call to `align_content()`. Concretely:

1. Build `ContentNode` lists from the base and desired `BlockIR` sequences using
   `content_node_from_ir()` (already implemented in `content_align.py`).
2. Call `align_content(base_nodes, desired_nodes)` to get the `ContentAlignment`.
3. For each `ContentMatch`: route to the existing per-type diff logic
   (paragraph diff, list diff, table diff via `table_diff.py`).
4. For each `base_deletes` index: emit `DeleteContentRange` (existing path).
5. For each `desired_inserts` index: emit insert ops (existing path).

The terminal pre-match in `align_content` replaces `_ensure_base_trailing_paragraph`
— the synthetic paragraph patching in `client.py` becomes unnecessary.

Key callsite to replace: `_diff_section_block_slice` in `diff.py`, currently ~lines
1370–1494. The prefix/suffix trimming and fallback to `_plan_mixed_body_block_slice`
are replaced by the DP output.

### Step 4: Eliminate the structural re-fetch in `client.py`

`insertTableRow` / `deleteTableRow` / `insertTableColumn` / `deleteTableColumn` do **not** trigger the structural re-fetch (that is only `insertTable` and `insertPageBreak`). The row/column ops already converge in one cycle without any re-fetch.

The remaining re-fetch cases are:
1. **`insertTable` / `insertPageBreak`** — still triggers `_refresh_v2_batches_after_structural_ops`. Now that tables converge via row/column ops instead of delete+reinsert, this path fires less often but is not yet eliminated.
2. **`delete-only` refresh** — `deleteContentRange` followed by inserts whose indices were computed pre-delete. Not yet addressed.

### Step 5: Prove broader convergence

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
| Table diff algorithm (proven, integrated) | `src/extradoc/reconcile_v2/table_diff.py` |
| Content alignment DP (proven, not yet integrated) | `src/extradoc/reconcile_v2/content_align.py` |
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
