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

## Current Live State (as of 2026-03-31, checkpoint `b4aaccf`)

| Scenario | Status |
|---|---|
| Markdown multi-tab create + edit (cycle 1 + 2) | **Proven live** |
| Markdown callouts / blockquotes / code blocks | **Proven live** |
| Markdown footnotes | **Proven live** |
| XML minimal (heading + para) | **Proven live** |
| XML heading + list + page break (no table) | **Proven live** — single cycle |
| XML with simple table (no page break) | **Partial** — shell created, cell content empty on first cycle; second-cycle diff fills cells |
| XML page break + heading + list + table (medium) | **Failing** — page break ends up on wrong side of suffix content |
| Full structural XML smoke | **Not yet attempted clean** |

**Active uncommitted changes** (`git diff HEAD`):
- `batches.py`: adds `_rebatch_same_tab_structural_requests()` — splits multiple `insertTable` / `insertPageBreak` in same tab into separate batches. Fixes medium-XML regression where page-break and table shell were being batched together.
- `batches.py`: adds `_request_tab_id()` helper used by the above.
- `client.py`: `DiffResult` now carries `desired_document`, `desired_format`, `allow_live_refresh`; the live-refresh executor `_execute_document_batches_v2_live_refresh` uses these.

These uncommitted changes should be committed once the medium-XML page-break + table scenario is proven.

---

## How to Work on XML Correctness

**The active problem**: after a structural live-refresh cycle, content intended for the *suffix* of a page break is still being reinserted on the *wrong side* of the break. Root cause is in how the refreshed plan resolves indices after the partial structural state.

**Isolation steps** (least to most complex, build confidence at each step):
1. XML with list + page break (no table) — already proven ✓
2. XML with simple table (no page break) — shell proves, cell fill needs second cycle
3. XML with table + page break together — current blocker
4. XML with multiple tables, footnotes, sections

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

**Immediate** (before calling XML "done"):
1. Commit the current uncommitted changes once medium-XML page-break + table converges
2. Identify why suffix content goes to the wrong side of the page break during replan — instrument `lower.py` anchor resolution in the refresh path
3. Prove: XML table + page break converges in one or two cycles live
4. Prove: the full structural XML smoke scenario (heading + list + table + page break + footnote)

**After XML stabilises**:
5. Align `tests/` with current reconciler behavior — delete stale exact-shape expectations, replace with fixture-backed or semantic-convergence tests
6. Verify the full live smoke matrix passes clean from `release_smoke_docs.py`
7. Release `extradoc` with v2 as the locked default (remove v1 fallback env var)

**Known unsupported boundaries** (do not attempt to fix without a dedicated design task):
- Section-break insertion/deletion
- Horizontal rule create/delete
- Page breaks inside table cells / headers / footnotes
- New tabs with pre-existing custom header/footer templates
