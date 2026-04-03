# Code Review Log — reconcile_v3 & client pipeline

_Reviewed against user's stated concerns: default path, newline hacks, content duplication,
deferred ID consistency, list hacks, dead code._

---

## 1. v3 is NOT the default — v2 still is

**File**: `client.py:374-384`, `reconcile_v3/api.py:6-8`

`_get_reconciler_version()` defaults to `"v2"` via env var `EXTRADOC_RECONCILER`.
The api.py module docstring explicitly says:

> "It does NOT integrate with the production pipeline — use reconcile_v2 for production use."

To use v3 today you must set `EXTRADOC_RECONCILER=v3`. No CLI flag exists — the
env var is the only toggle. The user's intent is to make v3 the **only** path and
eliminate the flag.

**Also**: `client.py:37-43` still imports `reconcile_v1` and `reconcile_v2`, and
`DiffResult` still carries a `reconciler_version: str = "v2"` field.  The live-refresh
path (`_execute_document_batches_v2_live_refresh`) is entirely v2-specific and would
become dead code once v3 is the default.

---

## 2. Three separate content-insertion code paths (massive duplication)

There are **three** distinct functions for inserting paragraph content, all doing
largely the same thing:

### 2a. `_lower_story_content_update()` — lower.py:726
Used for existing body/header/footer/footnote updates (matched + diffed content).

### 2b. `_lower_story_content_insert()` — lower.py:2397
Used for inserting into **newly created** headers/footers/footnotes.
Uses `endOfSegmentLocation` because the segment ID is a deferred placeholder.
Manually strips `\n` from the last paragraph to avoid a duplicate paragraph break.
Has its own inline para-style and text-style application logic (duplication of
`_lower_paragraph_insert`).

### 2c. `_lower_new_tab_body_insert()` — lower.py:2215
Used only for inserting body content into a **newly created tab**.
Has yet another copy of paragraph-insert logic, with a special case for footnote
references inline. Also has a `cumulative = -1` silent-skip after tables.

**Why this is a problem:**
- `_lower_story_content_insert` duplicates paragraph style + text-style application
  that already exists in `_lower_paragraph_insert`.
- `_lower_new_tab_body_insert` duplicates the same logic AGAIN, plus adds a
  special-cased footnote-reference inline path that exists nowhere else.
- Any bug fixed in one is silently not fixed in the others.

The root cause is that newly created segments don't have known absolute indices,
so a different insertion mechanic (endOfSegmentLocation) is used. But the
style-application logic is identical and should be shared.

---

## 3. endOfSegmentLocation hack

**File**: `lower.py:2443-2455`

`_lower_story_content_insert()` uses `endOfSegmentLocation` instead of explicit
`location: {index}` because the header/footer/footnote segment ID is a deferred
placeholder that isn't known at lowering time. This requires:

1. Stripping the trailing `\n` from the last paragraph (lower.py:2442):
   ```python
   insert_text = text.rstrip("\n") if is_last_para else text
   ```
   to avoid creating a duplicate paragraph break (the new segment already has a
   terminal `\n`).
2. Using hardcoded index arithmetic (`para_start = 1 + cumulative_offset`) for
   the style requests while using `endOfSegmentLocation` for the insert — these
   two mechanics are mixed in the same function.
3. Style range indices (lower.py:2468-2471) are absolute numbers while the
   insert location is relative — fragile if the segment's actual initial state
   differs from the assumed `[1, 2)` terminal paragraph.

The `_lower_new_tab_body_insert` avoids `endOfSegmentLocation` entirely and uses
explicit `1 + cumulative` indices — inconsistent with the header/footer path.

---

## 4. "delete first then re-insert" for bullet nesting changes

**File**: `lower.py:1796-1825` (Case C in `_lower_para_style_update`)

When a matched paragraph's nesting level or list type changes, the code:
1. Emits `deleteParagraphBullets`
2. Inserts `\t * nesting_level` tab characters via `insertText`
3. Emits `createParagraphBullets` covering the tabs + paragraph range

This delete-then-reinsert pattern is a workaround because the Google Docs API
doesn't support changing nesting level directly. The tab-prepending trick is
intentional (the API strips tabs and derives nesting level from them), but it
means the paragraph temporarily has wrong content mid-batch.

The same tab-prepending trick appears in three places:
- `_lower_para_style_update` Case A (gain bullet): lower.py:1743-1763
- `_lower_para_style_update` Case C (change nesting): lower.py:1806-1825
- `_lower_paragraph_insert` (new bullet paragraph): lower.py:1929-1955

Duplicated logic across three spots.

---

## 5. Inconsistent model for "content update" ops

**File**: `model.py:239-325`, `diff.py:473-553`

There are **two** separate patterns for "content of a segment changed":

**Pattern A** — Separate op type per segment kind:
- `UpdateHeaderContentOp` (model.py:239)
- `UpdateFooterContentOp` (model.py:269)
- `UpdateFootnoteContentOp` (model.py:317)

**Pattern B** — Single unified op with `story_kind` field:
- `UpdateBodyContentOp` with `story_kind` ∈ {"body", "table_cell"} (model.py:415)

The table cell case reuses `UpdateBodyContentOp` (diff.py:908-918) but headers,
footers, and footnotes each have their own op type.

**Duplication consequences**:
- `lower.py:411-501`: Three near-identical `case` arms for UpdateHeaderContentOp,
  UpdateFooterContentOp, UpdateFootnoteContentOp — all call `_lower_story_content_update`
  with the same arguments. One unified `UpdateSegmentContentOp` would eliminate this.
- `diff.py:432-565`: `_diff_headers` and `_diff_footers` are near-identical (55 lines
  each). `_header_slots_from_doc_style` and `_footer_slots_from_doc_style` are
  near-identical (8 lines each).

---

## 6. Table cell content — NOT lowered via the unified path

**File**: `lower.py:1219-1225`, `diff.py:908-918`

Table cell content diffs produce `UpdateBodyContentOp(story_kind="table_cell")`.
In `lower_batches()`, only `UpdateBodyContentOp` is handled (lower.py:506-517)
and it calls `_lower_story_content_update()` with `segment_id=None`.

But table cells need `segmentId` set to the cell's own segment (via the row/column
location in the table). Passing `segment_id=None` for a table cell means all
generated requests will have no `segmentId` — which is wrong if the cell is not
the document body.

Wait — actually table cell content in Google Docs IS part of the body segment
coordinate space (cells have their own `startIndex`/`endIndex` within the flat
body). So `segment_id=None` may be correct for same-tab body cells, but the
comment in lower.py:1221-1224 says "cell-level child ops handle the actual
content edits" then returns `[]` for the table case in `_lower_element_update`.
The actual cell content lowering happens via the `UpdateBodyContentOp` child op
from `diff.py`. This is roundabout and hard to follow.

---

## 7. Deferred ID system has hardcoded batch indices

**File**: `lower.py:2347`

In `_lower_new_tab_body_insert`, footnotes inside a new tab reference:
```python
"batch_index": 1,  # hardcoded
"request_index": fn_req_index,
```

This `batch_index: 1` is hardcoded to mean "batch1" (the content batch). But the
actual batch index in `prior_responses` depends on how many prior batches ran.
If batch0 runs first and batch1 second, then `prior_responses[1]` is batch1's
response. This is correct only if batch0 exists. If batch0 is empty (no structural
creates), batches are renumbered. The batch index system assumes a fixed ordering
that may not hold.

For the header/footer deferred IDs (lower.py:187-192, 220-225), `batch_index: 0`
is used correctly. But for footnote-in-new-tab, the `createFootnote` is inside
batch1, and the footnote content is in batch2 — so `batch_index: 1` refers to
batch1's response. This works only if batches are emitted in the specific order
[batch0, batch1, batch2] — which `lower_batches()` does guarantee by construction.
It's fragile but technically correct as long as the construction order never changes.

A cleaner approach: use symbolic batch names ("structural", "content", "footnotes")
and resolve them by name at execution time.

---

## 8. `reconcile()` in api.py is effectively dead code

**File**: `reconcile_v3/api.py:54-96`

The `reconcile()` function (non-batched) is never called from `client.py`, which
uses `reconcile_batches` exclusively. The function's own docstring warns:

> "If the diff requires multiple batches ... this function returns only the first
> batch and will miss deferred-ID resolution. Use `reconcile_batches` for production use."

It is only useful in narrow test scenarios where no structural ops (new headers/tabs)
are needed. It can be removed or kept only as an internal test helper.

---

## 9. `_lower_one()` duplicates `lower_batches()` call

**File**: `lower.py:611-618`

```python
def _lower_one(op: ReconcileOp) -> list[dict[str, Any]]:
    batches = lower_batches([op])
    return [req for batch in batches for req in batch]
```

This function is never called outside of `lower_ops()` (lower.py:119-128), which
itself is only used in tests. If `lower_ops` and `_lower_one` are only for tests,
they should be in the test file.

---

## 10. Silent skipping of content after table in new-tab insert

**File**: `lower.py:2270-2272, 2377-2392`

In `_lower_new_tab_body_insert`, after inserting a table:
```python
cumulative = -1  # unknown after table insertion
```
All subsequent paragraph elements are silently skipped (`continue`). There is no
error, no warning, no indication to the caller that content was dropped. A document
with content after a table in a new tab will have that content silently omitted.

---

## 11. `_CELL_STYLE_FIELDS` defined inside a loop

**File**: `diff.py:923-934`

```python
_CELL_STYLE_FIELDS = [
    "backgroundColor",
    ...
]
result = _styles_changed(b_cell_style, d_cell_style, _CELL_STYLE_FIELDS)
```

This list is recreated on every loop iteration. It should be a module-level
constant (like `_PARA_STYLE_READONLY_FIELDS` or `_WRITABLE_DOC_STYLE_FIELDS`).

---

## 12. v1 reconciler still imported and callable

**File**: `client.py:37-43, 406`

```python
from extradoc.reconcile import reconcile as reconcile_v1, ...
...
return reconcile_v1(base, desired), None
```

v1 is still a live code path reachable via `EXTRADOC_RECONCILER=v1` or `legacy`.
If v3 becomes the default, v1 and v2 imports + code paths in `client.py` become
dead code (3 imports, the entire `_execute_document_batches_v2_live_refresh` function,
`_refresh_v2_batches_after_structural_ops`, `_refresh_v2_batches_after_live_change`,
`_should_refresh_v2_batches`, `_truncate_batch_for_live_refresh`).

---

## 13. `lower_ops()` is dead code in production

**File**: `lower.py:119-128`

`lower_ops()` is a single-batch flattening wrapper used only by tests. Production
always calls `lower_batches()`. If this is only for tests, move to test helpers.

---

## Summary by concern area

| Concern | Severity | Key Files |
|---------|----------|-----------|
| v3 not default (env var toggle) | High | client.py:374 |
| 3 separate content-insert paths | High | lower.py:726, 2215, 2397 |
| endOfSegmentLocation hack | Medium | lower.py:2443 |
| Delete-then-reinsert for bullet nesting | Medium | lower.py:1796 |
| Header/footer op types not unified | Medium | model.py:239-325, diff.py:432-565 |
| Table cell content path unclear | Medium | lower.py:1219, diff.py:908 |
| Deferred IDs with hardcoded batch_index | Medium | lower.py:2347 |
| `reconcile()` dead code | Low | api.py:54 |
| `lower_ops`/`_lower_one` dead code | Low | lower.py:119, 611 |
| Silent content drop after table in new tab | Low | lower.py:2270 |
| `_CELL_STYLE_FIELDS` in loop | Low | diff.py:923 |
| v1/v2 code paths dead if v3 default | Low | client.py:37-530 |
