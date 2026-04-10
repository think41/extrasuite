# Reconcile v3 — Architecture, History, and Status

**Audience**: An engineer picking up where this work left off. Read this before touching any code.

> **See also:** [`coordinate_contract.md`](coordinate_contract.md) — the
> three-state `startIndex`/`endIndex` invariant that `reconcile_v3/lower.py`
> consumes from the desired tree. Required reading before modifying `lower.py`.

---

## The Big Picture

`extradoc` implements a pull → edit → push workflow for Google Docs:

```
pull:   API → raw/document.json → serialize(base) → folder of files
edit:   agent edits files in the folder
push:   deserialize(edited folder) → desired Document
        reconcile(base, desired) → list[BatchUpdateRequest]
        execute requests against live Google Doc
```

The reconciler is the heart of `push`. It takes two `Document` objects — `base` (what the doc looked like at pull time) and `desired` (what the agent wants it to look like) — and produces a list of `BatchUpdateDocumentRequest` batches that transform one into the other.

**Why v3?** `reconcile_v2` worked, but it had a fundamental structural problem: it parsed stable IDs from the document at parse time, then ignored them at diff time, using position-based matching everywhere instead. This caused:
- Tabs matched by position instead of `tabId` → silent failure if tab order changed
- Footnotes matched by paragraph position instead of `footnoteId` → wrong matches on edits
- `DocumentStyle`, `NamedStyles`, `InlineObjects` never diffed → silent data loss
- The SERDE couldn't guarantee "things I don't understand won't be deleted" → headers/footers silently wiped on markdown push

`reconcile_v3` fixes all of this with a deliberate top-down tree traversal, anchoring at stable IDs everywhere the API provides them.

---

## The Document Tree

Google Docs is a tree. v3 traverses it top-down, matching at each level by the stable ID the API provides:

```
Document
  └── Tab  (matched by tabId)
        ├── DocumentStyle       (singular — diff in place)
        ├── NamedStyles         (matched by namedStyleType enum)
        ├── Lists               (matched by listId)
        ├── InlineObjects       (matched by inlineObjectId)
        ├── Headers             (matched by section slot + headerId)
        ├── Footers             (matched by section slot + footerId)
        ├── Footnotes           (matched by footnoteId)
        └── Body content        (ContentAlignment DP — flat sequence)
              └── TableCell     (recurse — same ContentAlignment DP)
```

The `content_align.py` module (proven in 90 tests, copied from v2) handles the flat-sequence matching at body, header, footer, footnote, and table cell levels. It uses an edit-distance DP with a hard terminal constraint (last paragraph never deleted).

---

## The SERDE Interface

The SERDE (serialize/deserialize) was redesigned alongside v3 to use a **3-way merge** on deserialization:

```python
serialize(base: DocumentWithComments, folder: Path) -> None
# Writes files to folder. Also writes .pristine/document.zip as the snapshot.

deserialize(base: DocumentWithComments, folder: Path) -> DocumentWithComments
# 3-way merge:
#   ancestor = parse(.pristine/document.zip)
#   mine     = parse(current folder)
#   ops      = reconcile_v3.diff(ancestor, mine)
#   desired  = apply_ops_in_memory(base, ops)
#   return DocumentWithComments(document=desired, comments=mine.comments)
```

**The guarantee**: If the SERDE doesn't model something (e.g., markdown doesn't model headers/footers), the diff `ancestor → mine` produces zero ops for those fields. Base values flow through unchanged. The SERDE can focus only on what it understands, without fear of destroying what it doesn't.

The shared op applier is `serde/_apply_ops.py`. Both XML and Markdown SERDEs use it.

---

## How We Got Here — Annotated Journey

### Starting point: proven leaf-node algorithms in v2

Before v3 existed, two key algorithms were proven in memory and then live:

**`reconcile_v2/table_diff.py`** (commit `1da82ce`): Fuzzy LCS row matching for tables. Handles add/delete/reorder rows and columns. Proven live — 5 integration bugs fixed in `diff.py` and `lower.py` to make table row/column ops converge in one cycle without re-fetching the document.

**`reconcile_v2/content_align.py`** (commit `b442d20`): Edit-distance DP for matching a flat sequence of structural elements (Paragraph, Table, TOC, SectionBreak). 90 tests. Terminal paragraph always matched (never deleted). Proven in memory only at this stage.

**Index arithmetic** (commit `e5a55cf`): A `verify-table-indices` CLI command proved live that after `insertTableRow`/`deleteTableRow`/`insertTableColumn`/`deleteTableColumn`, resulting cell indices are fully deterministic without re-fetching. 16/16 cases passed.

### The v3 design decision

A gap analysis of `reconcile_v2` found:
- Tabs matched by hierarchy **position** (not `tabId`)
- Footnotes matched by **paragraph position** (not `footnoteId`)
- Lists matched **positionally** (not by `listId`)
- `DocumentStyle`, `NamedStyles`, `InlineObjects` have **zero handling** — changes silently dropped

> *"Think of the Document as a tree. We first have tabs. Each tab has a stable id. So matching tabs is easy. Then within a Tab, we have various things. Most of them have ids that can be matched."*

This led to the decision to build `reconcile_v3` as a top-down tree traversal. The interface is identical to v2:

```python
reconcile(base: Document, desired: Document) -> list[BatchUpdateDocumentRequest]
```

No `transport_base` parameter — v3 doesn't need structural re-fetches.

### Building v3 — the sequential subagent pattern

Each component was built in an isolated worktree by a subagent, with tests, then committed to `main`. The rule: **prove in memory first, then live**.

| Commit | What | Tests added |
|--------|------|-------------|
| `7862345` | Top-down diff experiment — 21 ReconcileOp types, all tree levels | 51 |
| `cf9b121` | Basic lowering + multi-batch deferred ID resolution | +28 |
| `0e3233c` | Table cell content lowering (recursive story content) | +8 |
| `a1d883e` | Multi-run paragraph style edits (`_diff_paragraph_runs` using `difflib`) | +12 |
| `4a76bf9` | Footnote lowering (3-batch: create → anchor → content) | +10 |
| `abe4d33` | Wired into `client.py` via `EXTRADOC_RECONCILER=v3` | — |
| `8420331` | Table row/column insert/delete (ported `table_diff.py` to v3) | +13 |
| `641f0f3` | Table cell/row/column style diffing | +11 |
| `7b7024f` | DocumentStyle diffing and lowering | +9 |
| `282df2e` | Inline image insert/delete | +10 |
| `9d49fac` | Page break and section break insertion | +10 |

Then the SERDE redesign:

| Commit | What | Tests added |
|--------|------|-------------|
| `0000206` | Markdown SERDE 3-way merge + `_apply_ops.py` | +24 |
| `2f41405` | XML SERDE 3-way merge | +34 |
| `354926a` | Fix: reverse same-position insertions for correct order | — |
| `9e03fcf` | Fix: skip namedStyles/documentStyle diffs for formats that don't model them | — |
| `a9b6cbc` | Fix: thread `pre_delete_shift` into `_lower_paragraph_update` — broken by SERDE integration commits | — |

Then the newline compensation cleanup:

| Commit | What |
|--------|------|
| `044062c` | Remove all newline/trailing-paragraph compensation from lower.py and client.py |

Then list support and live testing:

| Commit | What | Tests added |
|--------|------|-------------|
| (list work) | List support: `createParagraphBullets`/`deleteParagraphBullets`, tabs for nesting, `_diff_lists` fix, `base_lists_by_tab` threading | +19 |
| (list bugs) | Fix `headingId` in fields mask; fix list-type change detection on matched paragraphs; fix same-position insertion style index drift; fix descending insertion order for different-position inserts | — |

### Key design decisions made along the way

**On the content alignment DP**: "Identical elements are always matched" is NOT a valid global DP invariant. A short identical paragraph adjacent to a large expensive element can be rationally delete+reinserted if it saves cost on a better global alignment. This is mathematically correct. In practice, agents don't reorder content blocks so this doesn't arise.

**On table row/column ops**: The `table_diff.py` algorithm was already proven in v2. For v3, it was copied and adapted to work on raw API dicts instead of IR objects, returning `ReconcileOp` types instead of `SemanticEdit` types. The core fuzzy LCS logic was not changed.

**On multi-run paragraph diffs**: Uses `difflib.SequenceMatcher` for character-level diffing. For equal spans with style changes: `updateTextStyle`. For deletions: `deleteContentRange`. For insertions: `insertText` + `updateTextStyle`. All ops emitted in descending index order to avoid corruption.

**On the SERDE 3-way merge**: The key insight is that `deserialize` is a 3-way merge, not a straightforward parse:
> *"Think of deserialize as a 3-way merge. The deserialization does a diff internally — markdown in .pristine and markdown that was edited. It finds out what changed. But then it superimposes the changes to the DocumentWithComments corresponding to base to get the desired DocumentWithComments. Each SERDE can then focus only on the subset of information it can truly model, but without fear of deleting things it doesn't understand."*

**On `_apply_ops.py`**: Works entirely on raw dicts (not Pydantic models). For content ops (`UpdateBodyContentOp`), applies `desired_content` wholesale from the alignment — both matched and inserted elements come from `desired_content`; deleted elements are simply absent. This is correct because the 3-way merge `desired_content` represents the complete target state.

**On newlines and terminal paragraphs** (commit `044062c`): The reconciler must be a faithful translator — it takes `desired` from the SERDE and emits API requests, nothing else. It must not add, remove, or adjust content the SERDE didn't produce.

Early in development, the SERDE always appended an explicit trailing empty paragraph (via `_ensure_trailing_paragraph`), but the live Google Docs API sometimes didn't return one as a separate element. Someone added `_ensure_base_trailing_paragraph` in `client.py` to paper over this — it injected a synthetic paragraph with `startIndex == endIndex` (no real range). That zero-width fake element then forced a cascade of compensating logic in `lower.py`:

- `_is_terminal_paragraph(el)` — checked paragraph *content* to detect the synthetic terminal. Wrong: terminal = last element by *position*, not by content. Any paragraph (including a heading with real text) can be the last paragraph.
- `_lower_element_insert_end_of_segment()` — a separate insert path that used `endOfSegmentLocation` because the synthetic terminal's `startIndex == endIndex == segment_end`, making explicit `insertText(index)` invalid.
- `"\n" + text` prepending — needed because `endOfSegmentLocation` inserts *into* the current last paragraph rather than *before* it; prepending `\n` created a paragraph break.
- `if not text.endswith("\n")` guards — patching paragraphs that "didn't have a trailing newline".
- `if text.strip()` guard — skipping "empty" paragraphs the reconciler had no business skipping.

All of this was removed in `044062c`. The correct model:

1. The SERDE produces `desired`. The reconciler trusts it completely.
2. Every real paragraph from the Google Docs API has a real `startIndex`. The terminal paragraph's `startIndex` is a valid insertion point — only `terminal.endIndex` (the exclusive segment end) is off-limits.
3. All body inserts use explicit indices. No `endOfSegmentLocation` for body content.
4. `endOfSegmentLocation` is retained *only* in `_lower_story_content_insert` for freshly-created headers/footers, where the segment ID is genuinely deferred (the header/footer was just created in batch 0 and its ID isn't resolved yet). That is a real constraint, not compensation.
5. The terminal is identified by position (`content[:-1]` to skip it), never by inspecting content.
6. `_diff_paragraph_runs` still strips the trailing `\n` before character-level diffing. This is *correct*, not compensation: when updating a matched paragraph in place, you never want to delete/insert its paragraph-terminating `\n` (that would merge it with the adjacent paragraph). It is not about "ensuring" a newline — it is about scoping the diff to paragraph content only.

---

## Current Status

### Test suite (as of last check)

```bash
cd extradoc && uv run pytest tests/ -q
# 10 failed, 705 passed
```

**0 failures in `tests/reconcile_v3/`** — 180 tests, all passing.

**10 failures in `tests/test_reconcile.py` / `test_client_reconciler_versions.py`** — pre-existing failures in edge cases around table insertion, unrelated to v3 work. These predate all reconcile_v3 development.

### Regressions that were caught and fixed

**`pre_delete_shift` not threaded through** (`a9b6cbc`): The SERDE integration commits added a `pre_delete_shift` parameter to `_lower_element_update()` but forgot to thread it into `_lower_paragraph_update()`. Caused `TypeError` across 46 tests. Fixed by adding the parameter and applying it as `adjusted_start = start - pre_delete_shift`.

**Lesson**: When a subagent modifies existing code to fix an issue found during SERDE integration, always run `uv run pytest tests/reconcile_v3/ -q` before committing to catch regressions in the lowering layer.

**List bugs found during live testing**:

- **`headingId` in `updateParagraphStyle` fields** — `lower.py` built the fields mask directly from the desired paragraph style dict, which includes `headingId` (assigned server-side). The API rejects `headingId` in the fields list. Fix: added `_PARA_STYLE_READONLY_FIELDS` constant (`headingId`, `indentStart`, `indentFirstLine` for bullet paragraphs) and filtered it out in all three `updateParagraphStyle` emit sites.
- **List-type change not detected on matched paragraphs** — When a matched paragraph changed from unordered to ordered (or vice versa), Case C in `_lower_para_style_update` only checked nesting level, not the bullet preset. Since both base and desired use the same synthetic list ID (`kix.md_list_1`), the list-ID comparison didn't help. Fix: thread `base_lists_by_tab` (alongside the existing `desired_lists_by_tab`) through the full call stack; Case C now computes `_infer_bullet_preset` for both base and desired and re-issues `deleteParagraphBullets` + `createParagraphBullets` when presets differ.
- **Same-position insertion style index drift** — When multiple paragraphs were inserted at the same position (emitted in reverse for correct ordering), the style requests (`updateParagraphStyle`, `updateTextStyle`) for each item used the base insertion index. After the first item's `insertText`, subsequent items' actual document positions shifted by the cumulative byte length of earlier items. Fix: added `_shift_request_indices()` and applied cumulative offsets to each item's style requests.
- **Wrong insertion order for different-position inserts** — Insertions at different positions were sorted in ascending order; inserting at a lower index first would shift everything above it, corrupting indices for the next insertion. Fix: sort in descending position order so higher-position inserts run first and don't affect lower-position inserts.

**Newline compensation cascade** (`044062c`): First live test against a real Google Doc revealed that heading styles were silently dropped on new paragraph inserts. Root cause traced back to `_ensure_base_trailing_paragraph` in `client.py`, which injected a synthetic paragraph that cascaded into `endOfSegmentLocation` usage, `\n` prepending, and a content-based `_is_terminal_paragraph` check — all of which conspired to skip `updateParagraphStyle` for paragraphs inserted at body end. Removed all compensation; all inserts now use explicit indices and emit full style requests. See "On newlines and terminal paragraphs" in Key Design Decisions above.

### What is and isn't implemented in lowering

**Fully implemented** (emits correct API requests):
- All tab ops (add, delete)
- DocumentStyle (margins, page size, background, orientation)
- NamedStyles (update, insert)
- Headers and footers (create, delete, update content)
- Footnotes (insert, delete, update content)
- Body content (insert/delete/update paragraphs with multi-run style diffs)
- Lists (bullet/ordered/checkbox: insert via `createParagraphBullets` with tab-based nesting, delete via `deleteParagraphBullets`, list-type change on matched paragraphs)
- Table structural ops (insert/delete row, insert/delete column)
- Table cell/row/column styling
- Inline image insert/delete
- Page break and section break insertion

**Intentional no-ops** (API limitations):
- `DeleteNamedStyleOp` — Google Docs API cannot remove named styles
- `UpdateListOp` — List definitions not editable via batchUpdate
- `UpdateInlineObjectOp` — Image properties not editable via batchUpdate
- `InsertInlineObjectOp` / `DeleteInlineObjectOp` in `_apply_ops.py` — deferred (index-arithmetic heavy)

**Known gaps** (acceptable for now):
- Tab reordering (`updateDocumentTabProperties`)
- `replaceAllText` (different workflow)
- Named ranges (rarely edited)
- Positioned objects (rare, complex)
- New-tab content in a single push: `InsertTabOp` goes into batch 0; body content for the new tab goes into batch 1 which is built against the pre-push base (tab not yet known). Result: first push creates the empty tab; a second push fills the content. Fix requires deferred tab-ID handling for body content, similar to the header/footer deferred-ID pattern.

### File map

```
src/extradoc/reconcile_v3/
  api.py           # Public interface: reconcile(base, desired) -> list[BatchUpdateRequest]
  diff.py          # Top-down tree diff -> list[ReconcileOp]
  lower.py         # ReconcileOp -> list[dict] (API request dicts)
  model.py         # 21 ReconcileOp dataclass types
  content_align.py # DP alignment (copied from v2, proven in 90 tests)
  table_diff.py    # Table row/col diff (adapted from v2, proven live)
  errors.py        # UnsupportedReconcileV3Error, ReconcileV3InvariantError

src/extradoc/serde/
  _apply_ops.py    # In-memory op applier for 3-way merge deserialize
  __init__.py      # serialize/deserialize dispatch; 3-way merge logic
  _to_xml.py       # XML serializer
  _from_xml.py     # XML deserializer
  _to_markdown.py  # Markdown serializer
  _from_markdown.py # Markdown deserializer

tests/reconcile_v3/
  test_diff.py     # 72 tests for the diff layer
  test_lower.py    # 89 tests for the lowering layer
  test_bullets.py  # 19 tests for list/bullet support
  helpers.py       # Synthetic document factory functions

tests/
  test_serde_markdown_roundtrip.py  # 24 tests: serialize → edit → deserialize
  test_serde_xml_roundtrip.py       # 34 tests: serialize → edit → deserialize
```

---

## The Testing Method

We follow a strict **in-memory first, then live** discipline:

### In-memory testing (unit/integration)

Every new component gets a full test suite using synthetic `dict`-based documents before any live API calls. The pattern:

1. Build a minimal synthetic Document dict that exercises the scenario
2. Call the function under test
3. Assert the output (ops list, request shapes, field values)

For SERDE testing, the pattern is:
1. Build a `DocumentWithComments` dict
2. `serialize(base, folder)` → writes files to a temp dir
3. Make **deterministic edits** to the files (string replace, ElementTree xpath, direct writes — you know exactly what you changed)
4. `deserialize(base, folder)` → returns `desired: DocumentWithComments`
5. Assert: edited things changed; unmodeled things preserved from base

This is the approach in `test_serde_markdown_roundtrip.py` and `test_serde_xml_roundtrip.py`.

### Live testing (end-to-end)

After in-memory tests pass, live testing uses real Google Docs:

```bash
# Create a test document
./extrasuite docs create "Title"

# Pull as markdown
EXTRADOC_RECONCILER=v3 ./extrasuite docs pull-md <url> <folder>

# Edit files in <folder>

# Push changes
EXTRADOC_RECONCILER=v3 ./extrasuite docs push-md <folder>

# Re-pull to verify
EXTRADOC_RECONCILER=v3 ./extrasuite docs pull-md <url> <folder>
```

The live test sequence (to be executed once in-memory tests pass):

**Phase 1 (markdown):**
1. ✅ No-op push (serialize → push without edits → verify zero changes)
2. ✅ Text edits (paragraph change, add, delete)
3. ✅ Formatting (bold, italic, links)
4. ✅ Lists (create, edit add/remove item, bullet↔ordered conversion, nesting)
5. Tables (create, edit cell, add row)
6. Multi-tab (add tab, edit one tab only) — tab creation works; known gap: content requires second push
7. Footnotes (add, edit)
8. Preservation test: add header via XML push → pull-md → edit body → push-md → verify header survived
9. Multi-change stress test

**Phase 2 (XML, after markdown passes):**
Focus on things markdown doesn't model:
1. Named style edits via `styles.xml` or `namedstyles.xml`
2. Paragraph style edits (alignment, spacing, indentation)
3. Header and footer content editing
4. Document style (page margins, background)
5. All scenarios from markdown, now via XML path

**The invariant for any live test**: After push, re-pull the document and assert the expected state. Never accept "no error" as success — verify the actual Google Doc content changed correctly.

### Bug discipline

If a live test fails:
1. Diagnose root cause (read the error, check request shapes, compare with API docs)
2. Write a failing in-memory test that reproduces the bug
3. Fix the code
4. Verify the in-memory test passes
5. Commit: `"Fix: <clear description>"`
6. Re-run the live test to confirm fix

**Warning from prior work**: The mock in `src/extradoc/mock/` does NOT replicate real UTF-16 index side effects. A fix proven against the mock is not proven. Live fixtures win.

---

## How to Activate v3

```bash
# Use reconcile_v3 for push
EXTRADOC_RECONCILER=v3 ./extrasuite docs push-md <folder>
EXTRADOC_RECONCILER=v3 ./extrasuite docs push <folder>

# Use reconcile_v3 for pull (pulls always use the SERDE; v3 is used on push)
EXTRADOC_RECONCILER=v3 ./extrasuite docs pull-md <url> <folder>
```

Without the env var, `reconcile_v2` is used (the default).

---

## Immediate Next Steps

1. **Fix new-tab content in single push** — `InsertTabOp` lands in batch 0; body content for the new tab should follow in the same push. Requires deferred tab-ID handling for the new tab's body content (analogous to the header/footer deferred-ID pattern).

2. **Markdown live test — remaining Phase 1 items** — Tables, footnotes, preservation test, multi-change stress test.

3. **XML live test** — same pattern, Phase 2 scenarios.

4. **Graduate v3 to default** — once live tests pass, remove the `EXTRADOC_RECONCILER` env var requirement; make v3 the default and deprecate v2.

---

## The Warning to Carry Forward

From the original continuation notes:

> **The Mock is Not the Truth.** `src/extradoc/mock/` does not replicate real UTF-16 index side effects after structural ops. A fix proven only against the mock is not proven. Live fixtures win.

And the corollary for the SERDE:

> **The Pristine is the Anchor.** The `.pristine/document.zip` written by `serialize()` is what makes the 3-way merge work. If it's missing (legacy folders), the fallback is direct parse — which is the old behavior, not wrong, just without the preservation guarantee. New pulls always have the pristine.
