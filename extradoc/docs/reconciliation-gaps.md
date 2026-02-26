# Reconciliation Module — Known Gaps and Issues

Code review findings for `extradoc/src/extradoc/reconcile/`. Issues are grouped by severity.

---

## Architectural Issues

---

## Design Issues

*(None open.)*

---

## Fixed Issues

### 8. Bullet preset was hardcoded — FIXED (Phase 6)

The reconciler now calls `_infer_bullet_preset(desired_se, desired_lists)` which reads the desired document's `lists` dict to determine the correct `bulletPreset`. `type="bullet"` maps to `BULLET_DISC_CIRCLE_SQUARE`, `type="decimal"` to `NUMBERED_DECIMAL_NESTED`, etc.

### ADDED paragraphs were missing style requests — FIXED

Style requests (`updateParagraphStyle`, `updateTextStyle`, `createParagraphBullets`) were only generated for MATCHED paragraphs. Paragraphs in the ADDED group (trailing gap or inner gap) received `insertText` only with no styles applied. Fixed by adding `_generate_style_for_added_paragraph()` and `_style_reqs_for_added_paras()` in `_generators.py`.

---

## Code Quality Issues

### 12. Silent `return []` on text mismatch should be an assertion

**File:** `_generators.py:1853-1854`

```python
if base_run.content != desired_run.content:
    return []  # silently drops all style updates
```

Style diff is only called for MATCHED paragraphs whose text content must match. If this guard triggers, it indicates a correctness bug upstream. A silent `return []` causes style updates to be silently dropped rather than surfacing the problem. Should be an `assert` or `ReconcileError`.

---

### 13. `_strip_cell_para_styles` is too aggressive

**File:** `_comparators.py:137-168`

`_strip_cell_para_styles` removes `paragraphStyle` from every paragraph inside table cells. This means `verify()` reports success even when table cell paragraph styles differ between actual and desired. The stripping was introduced to paper over mock-vs-test-builder discrepancies in default styles, but it masks real failures such as headings or alignment changes inside table cells.

---

### 14. `documents_match` is exposed as a public API

**File:** `__init__.py:26`

`documents_match` is an internal comparison utility used by `verify()`. Exporting it creates an implied stability contract. If the normalization strategy changes, external callers break. It should be unexported or explicitly marked as unstable.

---

## Unhandled Cases (Silent Failures)

The following scenarios produce no error but incorrect or incomplete results:

### 15. Multi-paragraph cells lose structure

`_diff_single_cell_at` and `_populate_cell_at` use `_cell_text`, which concatenates all paragraphs in a cell into a single string. If a cell has two paragraphs ("Line 1\nLine 2\n"), the paragraph boundaries are lost — the new cell gets the combined text but as a single paragraph. No error is raised.

### 16. Nested tables are invisible

`content_fingerprint` returns `"T:table"` and `_cell_text` only handles paragraphs. Tables nested inside table cells are silently ignored during both fingerprinting and text extraction. Their content will not be reconciled.

### 17. `tableCellStyle` changes are not reconciled

`_diff_table_cell_styles_only` handles paragraph and text styles within cells but not cell-level styles (borders, background color, padding). Changes to `tableCellStyle`, `tableRowStyle`, or the overall `tableStyle` are silently ignored.

### 18. Section-specific headers and footers

`_make_create_header` and `_make_create_footer` always omit `sectionBreakLocation`, meaning they apply to the document style (first section only). Documents with multiple sections that have per-section headers/footers cannot be reconciled.
