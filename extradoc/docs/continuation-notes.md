# Continuation Notes — extradoc reconcile_v2 + XML/Markdown

**Audience**: Architect familiar with Google Docs API. Goal is to pick up from checkpoint `b4aaccf` (2026-03-31).

---

## The Architecture in One Paragraph

`pull` stores `./raw/document.json` (live API response). From this we construct a **base Document**.
`push` reconstructs a **desired Document** from the edited on-disk files. `reconcile_v2` computes the diff between base and desired, lowers it to `batchUpdate` request batches, and executes them.

The critical insight from the last session: **the only difference between the XML and markdown paths is how the desired Document is constructed**. The entire reconciler pipeline — IR, diff, lower, batch, execute — is shared. `client.py` normalises raw-base para styles for markdown before passing to `reconcile_v2` but otherwise the paths are identical.

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
client.py                            live-refresh executor: re-fetch + re-diff after
                                     insertTable / insertPageBreak
```

Key invariant: `lower.py` uses the **raw transport base** for index arithmetic, not the canonical IR.
Key invariant: `batches.py` uses iterative content batching when dense structural edits exist
(`_should_iteratively_batch_content`); re-diffs against `MockGoogleDocsAPI` between rounds.

Reference files:
- `reconciler-semantic-ir-design.md` — full IR spec
- `reconciler-semantic-ir-implementation-plan.md` — task checklist (Tasks 0–21)
- `reconciler-semantic-ir-edge-cases-to-test.md` — edge cases by category

---

## The Mock is Not the Truth

`src/extradoc/mock/` is fast but unreliable as a release signal. It does not replicate:
- real UTF-16 index side effects after structural ops
- actual carrier paragraphs emitted by the API after `insertTable` / `insertPageBreak`
- live revision-ID advancement and write-control semantics

**Rule**: A fix that makes mock tests pass but has no live fixture is not proven. A fix that is proven live and breaks mock tests means the mock is wrong. Fix the mock separately.

The CLAUDE.md in `extradoc/` states this explicitly: "if mock behavior disagrees with live Google Docs, the mock is wrong for that purpose and live fixtures win."

---

## The Iterative Approach: Reduce Risk, Increase Confidence

Each commit should prove one narrow thing live, leave a fixture or log entry, and not break prior proofs.

**Confidence stack** (from lowest to highest):
1. Local unit test against mock — catches obvious regressions, not structural correctness
2. Fixture-backed offline test — `tests/reconcile_v2/fixtures/<name>/{base,desired,expected.*.json}` — proves request shape
3. Live convergence test — pull → edit → push → pull, semantic diff is empty (best signal)
4. Live smoke run — `scripts/release_smoke_docs.py` — multi-scenario matrix

**Never skip steps 3→4 before a release.** The live verification log (`docs/live-verification-log.md`) is the running record of what has been proven.

**Fixture capture**: `scripts/capture_reconcile_v2_fixtures.py` — uses a real Docs backend, captures `base.json`, `desired.json`, and the mutations that produced `desired`. Commit these. Ad hoc live probing without durable fixture capture does not count as progress.

---

## Current Live State (as of 2026-04-01, checkpoint `cad298e`)

| Scenario | Status |
|---|---|
| Markdown multi-tab create + edit (cycle 1 + 2) | **Broken** — see regression note below |
| Markdown callouts / blockquotes / code blocks | **Broken** — same regression |
| Markdown footnotes | Unknown |
| XML minimal (heading + para) | **Proven live** |
| XML heading + list + page break (no table) | **Proven live** — single cycle |
| XML with simple table (no page break) | **Partial** — shell created, cell content empty on first cycle |
| XML page break + heading + list + table (medium) | **Failing** |
| Full structural XML smoke | **Not yet attempted clean** |

### Regression introduced in `3b8a95d`

`./extrasuite doc diff <any-md-doc-with-table-row-change>` fails with:

```
Error: reconcile_v2 iterative content planning could not lower the remaining mixed body rewrite
```

**Root cause** (diagnosed 2026-04-01):

1. `_table_anchor_signature` in `diff.py` includes the row count in the table's identity signature.
2. When any table gains or loses a row (e.g. adding a "Callouts" row to the features table), the signature changes → `_diff_section_blocks` sees base and desired anchor signatures as unequal → falls back to flat `_diff_editable_block_span` for the whole section.
3. Flat mode generates `DeleteTableBlockEdit` (old table) + `InsertTableBlockEdit` (new table) instead of `InsertTableRowEdit`.
4. `_should_iteratively_batch_content` triggers (has_table_delete=True, body_delete_count>1).
5. The iterative planner in `3b8a95d` switched from count-based to score-based iteration. The score-based approach cannot find a valid path for this shape and raises `ReconcileInvariantError`.

At `d95eb28` (one commit before `3b8a95d`), the old count-based planner happened to find a path through, so the bug was hidden.

**Fix**: Option B — remove row count from `_table_anchor_signature`. A table with N rows and a table with N+1 rows should be recognised as the same anchor (matched by column count and spans). Row insertions/deletions are then handled by `_diff_section_tables` via `InsertTableRowEdit` / `DeleteTableRowEdit`, which is the correct path. This eliminates the spurious `DeleteTableBlockEdit` and prevents the iterative planner from triggering for routine table edits.

This is the **next task** before any other work.

---

## How to Work on the Next Fix

**The active problem**: `_table_anchor_signature` uses row count as part of identity. Any row addition/removal causes flat-mode fallback → spurious delete/reinsert → iterative planner → failure.

**Fix location**: `diff.py:_table_anchor_signature` (~line 1081).

Change: drop `len(table.rows)` from the signature. Keep column count (derived from first row) and span structure, which actually identifies the table's structural shape. Row count is not an identity property — it changes on insert/delete and that is expected.

```python
# BEFORE
def _table_anchor_signature(table: TableIR) -> tuple[object, ...]:
    return (
        "table",
        len(table.rows),           # ← remove this
        tuple(len(row.cells) for row in table.rows),  # ← changes with row count too
        ...
    )

# AFTER — identity based on column structure, not row count
def _table_anchor_signature(table: TableIR) -> tuple[object, ...]:
    first_row = table.rows[0] if table.rows else None
    return (
        "table",
        len(first_row.cells) if first_row else 0,   # column count
        tuple((cell.row_span, cell.column_span) for cell in (first_row.cells if first_row else [])),
        table.pinned_header_rows,
    )
```

**Validation steps** (in order):
1. `uv run pytest tests/ -x -q` — all 142 should still pass
2. `./extrasuite doc diff md-test` — should produce valid batches (no error)
3. Inspect the diff output: should see `InsertTableRowEdit` not `DeleteTableBlockEdit`
4. Live push of md-test, re-pull, semantic diff empty
5. Then continue XML isolation steps:
   - XML with simple table (no page break) — should converge in one cycle
   - XML with table + page break together
   - Full structural XML smoke

**Debugging workflow**:
```bash
# Pull a fresh empty doc
./extrasuite docs pull <doc_id> <folder>

# Copy authored XML fixture on top
cp tests/reconcile_v2/fixtures/<name>/authored/* <folder>/

# Dry-run to inspect requests
./extrasuite docs diff <folder>

# Live push
./extrasuite docs push <folder>

# Re-pull and compare
./extrasuite docs pull <doc_id> <folder2>
# compare <folder> vs <folder2> semantically — empty diff = converged
```

**Log every live verification attempt** in `docs/live-verification-log.md` with doc ID, what was authored, what happened, and the interpretation. This is the primary continuity artifact.

**Key docs** in `docs/googledocs/` to consult when debugging:
- `structural-elements.md` — body vs. story vs. segment-level API semantics
- `tables.md` — `insertTable` + cell population rules; table carrier paragraphs
- `page-breaks.md` — how carrier paras around page breaks behave post-insert

---

## How to Run Tests

```bash
cd extradoc

# Fast local suite (mock-backed, stale expectations exist — failures may not be regressions)
uv run pytest tests/ -v

# Reconcile_v2 specific (higher-signal)
uv run pytest tests/reconcile_v2/ -v

# Client integration
uv run pytest tests/test_client_reconciler_versions.py -v

# Live smoke (needs auth, creates real Docs)
uv run python scripts/release_smoke_docs.py
```

**Warning**: Many tests in `tests/` outside `tests/reconcile_v2/` have stale exact-shape expectations. Failures there are not necessarily live regressions. Before declaring a test failure a bug, verify against a live doc.

**Fixture-backed tests are the trusted suite.** If a live proof contradicts a fixture, update the fixture and commit a note to the live verification log.

---

## Key Code Locations

| Purpose | File |
|---|---|
| Client orchestration + live-refresh executor | `src/extradoc/client.py` |
| Public reconcile_v2 entry point | `src/extradoc/reconcile_v2/api.py` |
| Semantic IR data model | `src/extradoc/reconcile_v2/ir.py` |
| Semantic diff | `src/extradoc/reconcile_v2/diff.py` |
| Lowering (single batch + shadow doc) | `src/extradoc/reconcile_v2/lower.py` |
| Multi-batch planning | `src/extradoc/reconcile_v2/batches.py` |
| Batch executor + deferred ID resolution | `src/extradoc/reconcile_v2/executor.py` |
| XML desired-Document construction | `src/extradoc/serde/_from_xml.py` |
| Markdown desired-Document construction | `src/extradoc/serde/_from_markdown.py` |
| Live fixture capture script | `scripts/capture_reconcile_v2_fixtures.py` |
| Live smoke runner | `scripts/release_smoke_docs.py` |
| Fixture pairs | `tests/reconcile_v2/fixtures/` |

---

## What's Next

**Immediate** (fix the regression first):
1. Fix `_table_anchor_signature` to not include row count (see How to Work on the Next Fix above)
2. Verify markdown diff/push works again for docs with table row changes
3. Verify XML simple table path converges (cell content filled in first cycle)
4. Prove: XML table + page break converges in one or two cycles live
5. Prove: the full structural XML smoke scenario (heading + list + table + page break)

**After XML stabilises**:
6. Align `tests/` with current reconciler behavior — delete stale exact-shape expectations
7. Verify the full live smoke matrix passes clean from `release_smoke_docs.py`
8. Release `extradoc` with v2 as the locked default

**Key decision made 2026-04-01**: The iterative planner should be a last resort. The correct fix for row insert/delete is to improve `_diff_section_blocks` to produce the right edit type in the first place, not to make the iterative planner more capable. Improving the planner is whack-a-mole.

**Known unsupported boundaries** (do not attempt to fix without a dedicated design task):
- Section-break insertion/deletion
- Horizontal rule create/delete
- Page breaks inside table cells / headers / footnotes
- New tabs with pre-existing custom header/footer templates
