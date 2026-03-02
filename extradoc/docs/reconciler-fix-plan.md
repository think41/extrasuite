# Reconciler Fix Plan

Analysis performed 2026-02-27. Covers `extradoc/src/extradoc/reconcile/`.

---

## Confirmed Bugs

### B1 — insertText at index 0 (empty document)
**Status:** TODO
**File:** `_generators.py`, `_process_inner_gap` ~line 731
**Root cause:** When the only body element is the opening sectionbreak
(`startIndex` absent → `_el_start = 0`), an inner gap with
`right_anchor = sectionbreak` computes `insert_idx = _el_start(right_anchor) = 0`.
The API rejects insertText at index 0 ("must be inside bounds of an existing paragraph").
**Fix:** When `right_anchor` is a sectionbreak, use `_el_end(right_anchor)` (= 1)
instead of `_el_start(right_anchor)`.

```python
elif gap.right_anchor:
    if _is_section_break(gap.right_anchor):
        insert_idx = _el_end(gap.right_anchor)   # 1, not 0
    else:
        insert_idx = _el_start(gap.right_anchor)
```

---

### B2 — `_generate_text_style_updates_positional` misses interior style changes
**Status:** TODO
**File:** `_generators.py`, `_generate_text_style_updates_positional` ~line 2313
**Root cause:** For each desired run `[run_start, run_end)`, the function calls
`_get_base_style_at(run_start)` — only the style at the START of the run.
When a desired run spans multiple base intervals (different styles in middle),
the interior styles are never compared. Specifically: removing bold/italic
collapses N base runs into 1 plain desired run; the bold/italic in the interior
base intervals is never cleared.
**Fix:** For each desired run, walk all base intervals that overlap
`[run_start, run_end)` and compare each sub-range independently against the
desired style. Emit one `updateTextStyle` per sub-range where they differ.
Merge contiguous sub-ranges with identical diffs as before.

---

### B3 — Table cell edits silently lose formatting
**Status:** DONE (subsumed by B3a below)
**Root cause:** `_diff_single_cell_at`, `_populate_cell_at`, and
`_generate_insert_table_with_content` only emit `insertText`/
`deleteContentRange`. They never emit `updateTextStyle` or
`updateParagraphStyle`. Any bold/italic/heading in table cells is silently
dropped when text changes or a new table is inserted.

---

### B3a — Architectural fix: recursive cell reconciliation
**Status:** DONE
**Root cause (design):** Table cell content is a list of `StructuralElement` —
identical in type to a body/header/footer segment. The current code treats cells
as flat plain-text strings. This discards all paragraph and text style
information.
**Key insight:** `generate_requests(alignment, segment_id, tab_id)` already
works on any aligned `StructuralElement` list. Cell content uses the **same
absolute body index space** (cell paragraphs have real `startIndex`/`endIndex`
from the API). Cells can be reconciled by calling `generate_requests` on aligned
cell content — full recursion, zero special-casing.
**Fix:** Extract `_reconcile_cell_content(base_elements, desired_elements,
segment_id, tab_id, desired_lists)` that aligns and calls `generate_requests`.
Replace:
- `_diff_single_cell_at` → `_reconcile_cell_content(base_cell.content,
  desired_cell.content, ...)` — base_cell.content has real API indices
- `_populate_cell_at` → `_reconcile_cell_content([fake_empty_para_at(cell_start)],
  desired_cell.content, ...)`
- `_generate_insert_table_with_content` cell population → same pattern

The trailing-gap logic in `generate_requests` already protects the cell-ending
`\n` (same as for body segments). No special-casing needed.

---

### B4 — Spurious empty paragraph after inserted table (inner gap)
**Status:** TODO
**Root cause:** `insertTable` at index I **always**:
  1. Inserts `\n` at I (splitting the paragraph)
  2. Places the table after the split point

With current strategy `insert_idx = _el_end(left_anchor) - 1` (h1's `\n`):
```
Before: [h1: "My Title\n"] [p: "Content\n"]
After:  [h1: "My Title\n"] [table] ["\n" ← spurious] [p: "Content\n"]
```
The split-off `\n` of h1 becomes its own empty paragraph after the table.
The comment in the code claiming this "avoids" the extra paragraph is wrong.

This is confirmed by `table_ops.py` (`handle_insert_table`):
```python
_insert_text_impl(document, "\n", index, tab_id, segment_id)  # always
```

**Fix:** After `insertTable` at `insert_idx`, add a `deleteContentRange` for
the extra paragraph at `[table_end, table_end+1)` where
`table_end = insert_idx + 1 + _table_structural_size(desired_table)`.
Then emit an `updateParagraphStyle` to restore the right anchor's paragraph
style on the now-merged range (since merging inherits the empty para's style,
which came from the left anchor).

**Constraint:** This only applies to inner gaps (right anchor exists). Trailing
gaps naturally need the extra `\n` as the segment-final paragraph.

**Note:** The API forbids deleting the `\n` immediately BEFORE a table
(rules-behavior.md), but this delete targets the `\n` AFTER the table (before
the right anchor paragraph), which IS allowed.

---

## Implementation Order

| # | Bug | Effort | Status |
|---|-----|--------|--------|
| B1 | Index-0 sectionbreak insertion | 2 lines | DONE |
| B3a | Recursive cell reconciliation | Medium | DONE |
| B4 | Spurious `\n` after insertTable | Medium | TODO |
| B2 | Positional style alignment interior | Medium | TODO |

---

## Key File Map

| File | Role |
|------|------|
| `reconcile/_generators.py` | All request generation; gap processing; style diffs |
| `reconcile/_core.py` | Orchestration: tab/segment/header/footer reconciliation |
| `reconcile/_alignment.py` | LCS-based element alignment |
| `reconcile/_extractors.py` | Fingerprints, plain-text extraction |
| `mock/table_ops.py` | `insertTable` mock — confirms B4 root cause |
| `mock/api.py` | Full batchUpdate mock; used by `verify()` in tests |

---

## Key API Facts (from `docs/googledocs/`)

- **`insertTable` always inserts `\n` first** (`table_ops.py` line 70), creating
  an auto-split paragraph. This is the B4 root cause.
- **Cannot delete `\n` before a structural element** (table, sectionbreak)
  (`rules-behavior.md`). Deleting after the table IS allowed.
- **Table cells share the body index space** — no separate segment ID needed.
- **UTF-16 indices** throughout; use `utf16_len()` for all length calculations.
- **Segment-final `\n` cannot be deleted** — `_process_trailing_gap` already
  protects it; same protection applies to cell-final `\n` via recursion.
