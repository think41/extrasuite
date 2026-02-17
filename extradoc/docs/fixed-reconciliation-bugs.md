### 1. `request_index` in DeferredID is wrong for multi-batch scenarios

**File:** `_core.py:429`

```python
request_index = len(_requests)   # position in the FLAT global list, not within the batch
_requests.append((current_batch, create_req))
```

When resolving, `prior_responses[batch_index]["replies"][request_index]` is used — but `replies` only contains entries for that batch. The bug triggers when `_requests` has already accumulated entries from *other* batches before a new creation request is appended.

**Concrete scenario:** A new tab is created (added to batch 0), then `_reconcile_new_segment` is called with `current_batch=1` to create a header inside it. At that point `len(_requests) = 1` (the createTab), so the DeferredID records `batch_index=1, request_index=1`. But createHeader will be at index `0` in batch 1's replies — off by one.

**Fix:** Count only entries in the same batch when computing `request_index`, not the flat list length.


---


### 2. Body content of new tabs is never populated

**File:** `_core.py:489-494`

`_reconcile_new_tab` calls `_reconcile_new_segment` for every segment including body, but `_reconcile_new_segment` silently returns for body (`"Body/footnote - can't create, skip"`). A new tab from the API always starts with a body containing a default `\n` — it cannot be created via a separate request, but its content can still be populated. The reconciler should diff desired body content against that initial state, the same way headers/footers are handled.

`test_create_tab` explicitly skips `verify()` and documents this as a known limitation.

---

### 3. Table row/column reordering is silently skipped

**File:** `_generators.py:816-824`

```python
if extract_plain_text_from_table(base_se.table) == extract_plain_text_from_table(desired_se.table):
    return _diff_table_cell_styles_only(...)
return _diff_table_structural(...)
```

If two rows (or columns) are swapped, the plain text of the whole table is identical, so `_diff_table_cell_styles_only` is called and no structural requests are generated. The table stays in the wrong order with no error.

**Fix:** The text-identity shortcut needs to also verify that row and column order matches, or be replaced with a per-cell comparison.

---

### 4. Global mutable state is thread-unsafe

**File:** `_core.py:37-42`

```python
_requests: list[tuple[int, dict[str, Any]]] = []
_id_counter: dict[str, int] = {}
```

These module-level globals are reset at the start of each `reconcile()` call. Concurrent calls will corrupt each other's state. The design note in the plan says "No mutable global state", but that is not what was built. Both should be local to the call and threaded through the DFS, or wrapped in a context object.


### 9. Segment iteration order is non-deterministic

**File:** `_core.py:254`

```python
all_segment_ids = set(base_segments.keys()) | set(desired_segments.keys())
for seg_id in all_segment_ids:
```

Set iteration order is not stable across Python runs. This affects the order in which requests are emitted, which (due to the `request_index` bug above) can flip which reply a DeferredID resolves to. Should use `sorted(...)` for determinism.

---


### 5. `align_structural_elements` duplicates LCS without positional fallback

**File:** `_alignment.py:150-205`

`align_sequences` (used for table rows/columns) has a positional fallback when LCS produces zero matches. `align_structural_elements` (used for document content) is a near-copy of the same LCS backtracking but without the fallback. This means completely-replaced document content follows a different code path than completely-replaced table rows.

The two functions should share the backtracking logic, or `align_structural_elements` should delegate to `align_sequences`.

---

### 6. All tables get the same fingerprint

**File:** `_extractors.py:76`

```python
if se.table:
    return "T:table"
```

Every table in a document has the identical fingerprint. When a document has two tables and their order is swapped, LCS cannot distinguish them and aligns incorrectly. Should use content-based fingerprinting analogous to paragraphs:

```python
if se.table:
    return f"T:{extract_plain_text_from_table(se.table)}"
```

---

### 7. `_diff_single_cell` is dead code

**File:** `_generators.py:1590-1631`

This function is never called. The active variant is `_diff_single_cell_at`, which takes an explicit `cell_start` parameter. `_diff_single_cell` uses `base_cell.content[0].start_index` instead. It should be removed.



### 10. `ReconcileError` is defined in the wrong module

**File:** `_generators.py:41`

`ReconcileError` is the module's public-facing exception but is defined inside the internal generator module. It should live in `__init__.py` or a dedicated `_exceptions.py` so callers can import it without depending on internal structure.

---

### 11. `_filter_section_breaks` is a misleading name

**File:** `_generators.py:404`

The function raises `ReconcileError` immediately when a section break is found. The filtering of `real_deletes`/`real_adds` at the bottom is vestigial — those lists never reach the caller if a section break exists. Should be renamed `_validate_no_section_breaks`, or the raise should be separated from the filtering logic.

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