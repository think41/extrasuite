# Algorithmic Review: extradoc Diff/Reconcile System

**Date**: 2026-04-11  
**Scope**: `diffmerge/`, `reconcile_v3/`, `serde/` — the full pull→edit→diff→push pipeline  
**Lens**: "Lens correctness" — can we edit a view and apply it back without corrupting invisible features?

---

## 1. System Architecture Overview

The pipeline has three conceptually distinct layers:

```
Pull (Google Docs API)
  ↓
Base Document (typed Pydantic models, lossless)
  ├── Serialize → Markdown (lossy projection)
  │
  └─→ User edits Markdown on disk
      ├── Deserialize → Desired Document (Pydantic models)
      │   (3-way merge: ancestor = pristine parse, desired = edited parse, base = live)
      │
      └─→ Reconcile: diff(base, desired) → batchUpdate requests
```

**Key design principles:**
- Element-level granularity: diffs operate on paragraphs/tables/rows, not characters
- Stable-ID anchoring: tabs, headers, footnotes matched by API-assigned IDs
- 3-way merge: the serde round-trip is never applied directly to `base`; instead `apply_ops(base, diff(ancestor, desired))` carries invisible features from `base`
- Index arithmetic: the reconciler works in "base" coordinates and computes shifts for prior deletes/inserts within the same batch

---

## 2. Diff Algorithm Analysis

### 2.1 Content Alignment (`content_align.py`)

**Algorithm**: Minimum-cost edit-distance DP (not Myers diff, not standard LCS)

**Cost model**:
- Delete a paragraph: `len(text) × 2.0 + inline_count × 50.0`
- Insert a paragraph: same
- Match two paragraphs: `(1.0 - similarity) × max_len` where similarity is word-level Jaccard
- Terminal paragraphs: `INFINITE_PENALTY` (pre-matched, never deleted)
- Tables: Fuzzy cell-text Jaccard; `MIN_TABLE_MATCH_SIMILARITY = 0.25`

**Pre-match constraints** (applied before DP):
1. **Terminal pre-match**: Segment-final elements are always matched; prevents deletion of trailing `\n`
2. **Table-flank pinning** (`_pin_table_flanks`): Paragraphs immediately adjacent to tables are forced to match if a 1:1 opportunity exists — prevents structural orphaning
3. **Positional fallback**: In 1:1 gaps (one base element, one desired element, same kind), they are promoted to a match regardless of similarity

### 2.2 Table Diff (`table_diff.py`)

**Row alignment**: Fuzzy LCS using **cell-text recall** (overlap / base_size), threshold = 0.5  
**Column alignment**: LCS on per-column text hashes

**Delete/insert ordering**: Row deletions emitted in **descending index order** to prevent index shifting during the API request sequence.

### 2.3 Where Delete+Insert Pairs Arise

| Trigger | Condition | Result |
|---------|-----------|--------|
| Paragraph similarity below threshold | word-Jaccard < 0.3 AND affix-ratio < 0.4 | Delete+Insert paragraph |
| Table row recall below threshold | recall < 0.5 AND positional similarity < 0.5 | Delete+Insert row |
| Unmatched table (similarity < 0.25) | Table text changes drastically | Delete+Insert whole table |
| Narrowly-failed 1:1 pre-match | Both elements exist but similarity check fails | DP may delete+insert anyway |

The threshold values are heuristics. With word-Jaccard = 0.3, a paragraph that changes 70% of its word tokens will be treated as a deletion, which may corrupt invisible features (comments, formatting on unchanged characters).

---

## 3. Round-Trip Safety Analysis

### 3.1 What Survives Untouched (Transparent Features)

These survive `pull → edit → push` because the 3-way merge carries them from `base`:

| Feature | Mechanism |
|---------|-----------|
| Named paragraph styles | Carried on matched paragraphs via `apply_ops` |
| Text formatting (bold, italic, color) | Carried on matched text runs |
| Comments / suggestions | Not touched; Google API handles separately |
| Custom paragraph properties | Carried via `_carry_through_unmatched_raw` |
| Footnote content (unedited) | Matched by footnoteId; carried through |
| Header/footer structure | Matched by ID; carried through |
| Table cells (unedited) | Unchanged cells carry through in table diff |

### 3.2 What Can Be Corrupted (High-Risk Scenarios)

#### Scenario A: Inline Passthrough Element in Edited Paragraph

```
Base:    "Hello <x-colbreak/> world"
Edited:  "Hi there <x-colbreak/> world"

Diff matches the paragraphs (similarity ≈ 0.6 → in-place update).
The reconciler emits deleteContentRange + insertText for the text portion.
But <x-colbreak/> is a named-range annotation with a base-coordinate index.
After the text edit, the colbreak's base index is stale.
```

**Status**: Bug #65, currently `xfail(strict=True)`. Confirmed broken.

**Affects**: Column breaks, page breaks, equations, rich links — anything represented as a named-range marker in markdown, embedded in an edited paragraph.

**Root cause**: The reconciler treats named-range markers as opaque passthrough with fixed base indices. It has no mechanism to adjust those indices when the surrounding paragraph is edited in-place.

#### Scenario B: Delete+Insert Destroys Invisible Formatting

```
Base:    "The quick brown fox" (entire paragraph is italic via API-only style)
Edited:  "A slow red fox"  (word-Jaccard ≈ 0.14 → Delete+Insert)

Result:  New paragraph inserted, base paragraph deleted.
         Italic style from base is GONE.
```

This is expected (by the system's design) but the threshold is a binary cliff: at 0.3 Jaccard similarity, a paragraph suddenly flips from "in-place update that preserves invisible styles" to "delete+insert that destroys them."

**Affects**: Any document with invisible paragraph-level styles (background shading, border, custom spacing) on paragraphs that are substantially rewritten.

#### Scenario C: Table Row Below Match Threshold

```
Base table row: ["Product ID", "Description (en)", "Price USD"]
Edited:         ["Product ID", "Beschreibung",     "Price USD"]

Recall = ({"Product ID", "Price USD"} ∩ {"Product ID", "Beschreibung", "Price USD"}) / 3 = 2/3 ≈ 0.67 → MATCH ✓

But if a 4th cell with completely different text is added and the algorithm uses 
positional similarity:
  pos_sim = (1.0 + 0.0 + 1.0 + 0.0) / 4 = 0.5 → borderline
```

Row deletions destroy any Google Docs formatting on the deleted row (merged cells, background color, custom borders).

---

## 4. Core Algorithmic Gaps

### Gap 1: Sub-Paragraph Diff — IMPLEMENTED

~~When two paragraphs are matched, the reconciler emits a "replace entire paragraph text" operation.~~

`_diff_paragraph_runs` in `reconcile_v3/lower.py` already performs character-level diffing via `difflib.SequenceMatcher`. For matched paragraphs it emits fine-grained `deleteContentRange` + `insertText` pairs covering only changed runs, and emits `updateTextStyle` only for equal spans where the style changed. This gap is closed.

### Gap 2: Hard Similarity Thresholds

The match/no-match decision at Jaccard = 0.3 (paragraph) and recall = 0.5 (table row) is a cliff. A small change in text content can flip the outcome from an in-place update to a delete+insert — destroying invisible features.

**Proposal A**: Increase the similarity threshold for paragraphs that contain inline passthrough elements (colbreak, equation markers). These paragraphs are "higher value" and should be matched even at lower similarity.

**Proposal B**: Introduce a "forced match" mode: if the paragraph at the same structural position (same list nesting, same flanking table) has similarity > 0.1, always match it and emit a coarser in-place update rather than delete+insert.

### Gap 3: Named-Range Index Tracking

Named ranges (colbreaks, equations, codeblocks, callouts) have API-assigned `startIndex` / `endIndex` values from the base document. When a paragraph is edited in-place, these indices become stale.

The reconciler must:
1. Detect which named ranges overlap with paragraphs being updated in-place
2. Compute the text delta for those paragraphs
3. Adjust named-range indices by the delta, or re-create the named ranges at the correct position

This is a significant architectural gap; it explains Bug #65.

### Gap 4: Three-State Index Invariant Enforcement

The desired document produced by `apply_ops` has three states for index fields:
- **Concrete**: carried from base (safe to lower)
- **None**: synthesized/mutated (must NOT be lowered as a raw index)
- **Mixed**: propagates as None (invalid edit plan)

There is no automated enforcement that all paths in `apply_ops` that emit new content set indices to `None`. A missed assignment here produces a silent corruption: the reconciler uses a stale base index as if it were valid.

**Proposal**: Add an `__debug__`-guarded assertion in `lower.py` that all concrete indices consumed by the reconciler correspond to elements that are either (a) unchanged from base, or (b) have been adjusted by a verified shift computation.

---

## 5. Recommendations

### Immediate (Bug Fixes)

1. **Bug #65 (colbreak/passthrough element index)**: In `reconcile_v3/lower.py`, when emitting in-place paragraph updates, scan the desired document's named ranges that overlap the paragraph range. For each named range with a base-coordinate index, compute the text delta and emit a `updateNamedRange` or recreate it at the adjusted position.

2. **Bug #64 (table row match threshold)**: In `table_diff.py::_fuzzy_lcs_indices`, make `match_threshold` adaptive: `max(0.3, 0.5 - 0.03 * num_cells)`. For wide tables, lower the threshold slightly so that rows with many stable cells aren't split on account of one or two changed cells.

### Short-term (Robustness)

3. ~~**Sub-paragraph diff for matched paragraphs**~~: Already implemented via `_diff_paragraph_runs` in `reconcile_v3/lower.py`.

4. **Inline passthrough boost**: Before the DP in `content_align.py`, detect paragraphs with inline passthrough elements (`_has_passthrough_inline(para)`). Boost their match score by multiplying the edit cost by 2.0 — this makes the DP prefer matching these paragraphs even at lower similarity.

5. **Monotonicity assertion**: Add a post-`apply_ops` invariant check that base-coordinate indices in the desired document are monotonically increasing within each segment. This catches bugs in the 3-way merge before they reach the reconciler.

### Medium-term (Architecture)

6. **Named-range-aware reconciliation**: Redesign the named-range handling in `lower.py` to track all named ranges that are "anchored" to paragraph content. When emitting paragraph edits, compute the resulting index shifts and schedule named-range updates accordingly.

7. **Parameterized similarity thresholds**: Expose `MIN_PARA_MATCH_SIMILARITY` and `MIN_TABLE_ROW_MATCH_SIMILARITY` as configuration options so that callers (e.g., the CLI) can tune them based on the document type (text-heavy vs. data-heavy).

---

## 6. Specific Code Locations

| File | Location | Issue |
|------|----------|-------|
| `table_diff.py` | `_fuzzy_lcs_indices` L193: `match_threshold = 0.5` | Hard-coded; bug #64 |
| `content_align.py` | `MIN_PARA_MATCH_SIMILARITY = 0.3` | Binary cliff; should be boosted for passthrough-containing paragraphs |
| `reconcile_v3/lower.py` | `_lower_story_content_update` | Does not adjust named-range indices on in-place paragraph edits (bug #65) |
| `diffmerge/apply_ops.py` | `_carry_through_unmatched_raw` | Verify that None-index invariant is maintained on all synthetic elements |
| `content_align.py` | `_pin_table_flanks` conflict resolution loop | No convergence bound; pathological graphs could loop |

---

## 7. Testing Coverage Gaps

| Area | Status | Notes |
|------|--------|-------|
| Delete+insert prevention | Partial | Bugs #64/#65 in xfail; no fuzzing |
| Passthrough element round-trips | Poor | No tests for colbreak+paragraph edit, equation+text change |
| Sub-paragraph formatting preservation | Absent | No test that italic on unchanged chars is preserved after edit |
| Named-style propagation | Weak | Tests update but not preservation on matched edits |
| Index monotonicity post-apply_ops | Absent | No explicit checker |
| Wide table row matching | Absent | No test for tables with 6+ columns and mixed edits |

---

## 8. Conclusion

The architecture is sound: the 3-way merge is the right mechanism for preserving invisible features. The main correctness risks are:

1. **Named-range index staleness** (Bug #65): A design gap, not a coding error. Requires architectural work in `lower.py`.
2. **Hard similarity thresholds**: Produce unexpected delete+insert on moderate rewrites, silently destroying invisible formatting. Adaptive thresholds and passthrough-element boosts are the pragmatic fix.
3. **No sub-paragraph diff**: Coarse in-place updates are safe but less accurate than character-level diffs; comments and per-character styles are at higher risk.

The "lens guarantee" — edit the markdown representation, push back, unrepresented features survive — holds **only for paragraphs that are matched by the DP**. For paragraphs below the similarity threshold, the guarantee breaks unconditionally. For paragraphs above the threshold but containing inline passthrough elements, the guarantee breaks due to Bug #65.
