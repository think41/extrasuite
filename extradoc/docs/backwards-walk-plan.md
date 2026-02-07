# Backwards Walk: Diff Engine Rewrite

## 1. The Algorithm

### 1.1 Problem

The diff engine converts block-level changes (added/deleted/modified paragraphs, tables, headers) into Google Docs `batchUpdate` requests. The current implementation generates all requests into a flat list, then globally reorders them into delete/insert/update buckets and applies index adjustments to compensate. This destroys the tree structure that should guarantee correctness. It is the root cause of recurring index drift bugs — cross-segment contamination, structural deletes not accounted for, multi-table failures, and the need for bandaids like `_skipReorder` and "merged body insert."

### 1.2 Core Invariant

**When processing element at pristine position P, everything at positions < P is at pristine state.**

This one rule eliminates the entire class of index drift problems. No delta tracking. No adjustment algorithm. No cross-segment contamination. The index you compute from pristine is the index you use.

### 1.3 How It Works

The diff engine converts block-level changes into Google Docs `batchUpdate` requests using a backwards walk. Each segment (body, each header, each footer, each footnote) has its own index space and is processed independently. Within a segment, the block diff provides an ordered list of changes, each annotated with pristine start/end indexes. The walk reverses this list and emits requests directly: DELETE emits `deleteContentRange` at the pristine range; ADD emits `insertText` + styling at the pristine insertion point; MODIFY emits delete-then-insert as an atomic pair. Because we process highest-index-first, each operation only affects content at or above position P, leaving everything below at pristine state.

Tables are handled by recursive descent into the same pattern. A modified table walks its rows backwards, and within each row walks cells backwards. Each cell's content is a ContentBlock and uses the same delete/insert handler as body content. The cell's content index is calculated from the pristine table XML. Since we walk cells right-to-left and rows bottom-to-top, the invariant holds: operations on later cells do not shift indexes of earlier cells.

The result is a flat list of requests emitted during the walk, already in correct execution order, with no post-processing required. No global reordering. No index adjustment. No `_skipReorder`. No "merged body insert." The algorithm handles content blocks, tables, rows, columns, headers, footers, and footnotes with one uniform principle: walk backwards, use pristine indexes.

---

## 2. Pseudocode

### 2.1 Orchestrator

```
function diff_documents(pristine_xml, current_xml, styles):
    changes = diff_documents_block_level(pristine_xml, current_xml)
    if no changes: return []

    # Same setup as current code
    pristine_doc = desugar(pristine_xml)
    current_doc = desugar(current_xml)
    pristine_table_indexes = calculate_table_indexes(pristine_doc)
    current_table_indexes = calculate_table_indexes(current_doc)
    cell_styles = parse_cell_styles(styles)
    text_styles = parse_text_styles(styles)

    # NEW: group by segment, walk each backwards
    segments = group_changes_by_segment(changes)
    requests = []
    for segment_key, segment_changes in segments:
        requests += walk_segment_backwards(segment_changes, segment_key, ...)
    return requests
```

### 2.2 Segment Grouping

```
function group_changes_by_segment(changes):
    segments = {}  # key → [changes]
    for change in changes:
        key = segment_key_from(change)  # "body", "header:kix.abc", etc.
        segments[key].append(change)
    # Sort each segment ascending by pristine_start_index
    for key in segments:
        sort segments[key] by pristine_start_index ascending
    return segments
```

### 2.3 Backwards Walk

```
function walk_segment_backwards(changes, segment_key, ...):
    requests = []
    segment_id = segment_id_from(segment_key)

    for change in reversed(changes):  # highest pristine index first
        match change.block_type:
            CONTENT_BLOCK → requests += emit_content_block(change, segment_id)
            TABLE         → requests += emit_table(change, segment_id, ...)
            HEADER/FOOTER → requests += handle_header_footer(change)  # existing
            FOOTNOTE      → requests += handle_footnote(change)       # existing
            TAB           → requests += handle_tab(change)            # existing
    return requests
```

### 2.4 Content Block Emitter

```
function emit_content_block(change, segment_id):
    requests = []

    # Handle footnote child changes (same as current)
    for child in change.child_changes:
        if child is FOOTNOTE:
            requests += handle_footnote(child, ...)

    match change.change_type:
        DELETED:
            requests += delete_content(
                change.pristine_start_index,
                change.pristine_end_index,
                segment_id,
                change.segment_end_index
            )

        ADDED:
            insert_idx = change.pristine_start_index
            if insert_idx == 0 and segment is body: insert_idx = 1
            requests += insert_content(change.after_xml, segment_id, insert_idx)

        MODIFIED:
            # Atomic pair: delete then insert at same position
            requests += delete_content(
                change.pristine_start_index,
                change.pristine_end_index,
                segment_id,
                change.segment_end_index
            )
            requests += insert_content(
                change.after_xml, segment_id,
                change.pristine_start_index
            )

    return requests
```

### 2.5 Table Emitter

```
function emit_table(change, segment_id, ...):
    match change.change_type:
        ADDED:
            return generate_table_add(change.after_xml, segment_id,
                                      change.pristine_start_index)

        DELETED:
            return generate_table_delete(change.before_xml, segment_id,
                                         change.pristine_start_index)

        MODIFIED:
            return emit_table_modify(change, segment_id, ...)
```

### 2.6 Table Modify — Backwards Cell Walk

```
function emit_table_modify(change, segment_id, ...):
    requests = []
    table_start = change.pristine_start_index

    # Column width changes (uses current table index)
    if column_widths_changed:
        requests += generate_column_width_requests(...)

    # Walk rows backwards
    row_changes = change.child_changes where type == TABLE_ROW
    sort row_changes descending by row_index
    columns_added = {}
    columns_deleted = {}

    for row_change in row_changes:
        row_idx = row_index_from(row_change)

        match row_change.change_type:
            ADDED:
                requests += insert_table_row(table_start, row_idx, segment_id)

            DELETED:
                requests += delete_table_row(table_start, row_idx, segment_id)

            MODIFIED:
                # Walk cells backwards within this row
                cell_changes = row_change.child_changes where type == TABLE_CELL
                sort cell_changes descending by col_index

                for cell_change in cell_changes:
                    col_idx = col_index_from(cell_change)

                    match cell_change.change_type:
                        ADDED (column):
                            if col_idx not in columns_added:
                                columns_added.add(col_idx)
                                requests += insert_table_column(...)

                        DELETED (column):
                            if col_idx not in columns_deleted:
                                columns_deleted.add(col_idx)
                                requests += delete_table_column(...)

                        MODIFIED:
                            cell_idx = calculate_cell_content_index(
                                table_start, row_idx, col_idx,
                                change.before_xml  # pristine table XML
                            )
                            cell_len = get_pristine_cell_length(
                                change.before_xml, row_idx, col_idx
                            )
                            # Delete old cell content
                            if cell_len > 1:
                                requests += delete_content(
                                    cell_idx, cell_idx + cell_len - 1,
                                    segment_id, cell_idx + cell_len
                                )
                            # Insert new cell content
                            inner = extract_cell_inner_content(cell_change.after_xml)
                            requests += insert_content(
                                inner, segment_id, cell_idx,
                                strip_trailing_newline=true
                            )
                            # Cell styling
                            if cell_style:
                                requests += cell_style_request(...)

    return requests
```

---

## 3. Implementation Changes

### 3.1 Update CLAUDE.md

**File:** `extradoc/CLAUDE.md`

Replace the "Two-Phase Diff Algorithm" section and all its subsections (through the "Block vs ContentBlock Changes" table, approximately lines 268-338) with a concise 3-paragraph description of the backwards walk algorithm, written as the current algorithm (not a future proposal).

### 3.2 Propagate pristine indexes for TABLE changes

**File:** `extradoc/src/extradoc/block_diff.py`

Two small edits:

**3.2a** `_diff_single_block()` (line 900-908): The TABLE MODIFIED `BlockChange` is created without `pristine_start_index` or `pristine_end_index`. The `pristine` Block parameter has `start_index` and `end_index` available. Propagate them:

```python
# In _diff_single_block, the TABLE MODIFIED BlockChange (line 900):
changes.append(
    BlockChange(
        change_type=ChangeType.MODIFIED,
        block_type=BlockType.TABLE,
        before_xml=pristine.xml_content,
        after_xml=current.xml_content,
        container_path=path,
        child_changes=table_changes,
        pristine_start_index=pristine.start_index,   # ADD
        pristine_end_index=pristine.end_index,         # ADD
    )
)
```

**3.2b** `_group_paragraph_changes()` (line 860-862): After processing a TABLE MODIFIED, `last_pristine_end_index` is never updated. This causes subsequent ADDED blocks to get wrong insertion positions. Fix:

```python
# After line 862: grouped_changes.extend(table_changes)
last_pristine_end_index = p_block.end_index  # ADD
```

### 3.3 Rewrite `diff_documents()` orchestrator

**File:** `extradoc/src/extradoc/diff_engine.py`

Replace the current `diff_documents()` function (lines 275-668, ~394 lines). The new function keeps the same signature and return type.

**Keep (lines 301-329):** The block diff call, desugaring, table index calculation, and style parsing. These are correct and unchanged.

**Replace (lines 331-668):** The entire body — change separation, merged body insert check, structural change iteration, body content iteration, the fallback catch-all, and the global reordering + index adjustment block. Replace with:

1. `_group_changes_by_segment(block_changes)` — new function
2. Loop over segments, call `_walk_segment_backwards()` for each — new function
3. Return the accumulated requests

**New function: `_group_changes_by_segment(changes)`**

Groups `list[BlockChange]` into `dict[str, list[BlockChange]]` keyed by segment. The segment key is derived from `container_path[0]` (e.g., `"body:body"` → `"body"`, `"header:kix.abc"` → `"header:kix.abc"`). For top-level changes where `container_path` is empty (HEADER/FOOTER/TAB/FOOTNOTE block types), derive the key from `block_type` and `block_id`.

Each segment's changes are sorted ascending by `pristine_start_index` (the walk will reverse them).

**New function: `_walk_segment_backwards(changes, segment_key, ...)`**

Iterates `reversed(changes)` and dispatches based on `block_type`:

- `CONTENT_BLOCK` → `_emit_content_block()`
- `TABLE` → `_emit_table()`
- `HEADER` / `FOOTER` → `_handle_header_footer_change()` (existing, no changes)
- `FOOTNOTE` → `_handle_footnote_change()` (existing, no changes)
- `TAB` → `_handle_tab_change()` (existing, no changes)

### 3.4 New `_emit_content_block()` function

**File:** `extradoc/src/extradoc/diff_engine.py`

Replaces `_handle_content_block_change()` (lines 889-991). The logic is simpler because no index adjustment is needed — the backwards walk guarantees pristine indexes are correct.

**Reuses these existing functions (unchanged):**
- `_generate_content_delete_requests_by_index()` (line 1811) — handles segment-end newline rule
- `_generate_content_insert_requests()` (line 1571) — the universal content inserter

**Handles footnote `child_changes`** the same way as current code (lines 912-922).

### 3.5 New `_emit_table()` and `_emit_table_modify()` functions

**File:** `extradoc/src/extradoc/diff_engine.py`

**`_emit_table()`** replaces `_handle_table_change()` (lines 994-1061). Dispatches:

- ADDED → `_generate_table_add_requests()` (line 2211, existing, unchanged)
- DELETED → `_generate_table_delete_requests()` (line 2356, existing, unchanged). Uses `change.pristine_start_index` directly instead of `_get_table_start_index()` lookup.
- MODIFIED → `_emit_table_modify()`

**`_emit_table_modify()`** replaces `_generate_table_modify_requests()` (lines 2402-2585). The key structural change is the backwards walk over rows and cells, as described in the pseudocode (Section 2.6).

**Reuses these existing functions (unchanged):**
- `_generate_column_width_requests()` (line 146) — column width updates
- `generate_insert_table_row_request()` — from `request_generators/`
- `generate_delete_table_row_request()` — from `request_generators/`
- `generate_insert_table_column_request()` — from `request_generators/`
- `generate_delete_table_column_request()` — from `request_generators/`
- `_calculate_cell_content_index()` (line 1976) — cell index from pristine table XML
- `_get_pristine_cell_length()` (line 2098) — cell content length
- `_extract_cell_inner_content()` (line 2125) — inner XML extraction
- `_generate_cell_style_request()` (line 2150) — cell styling
- `_generate_content_insert_requests()` (line 1571) — universal content inserter
- `_generate_content_delete_requests_by_index()` (line 1811) — content deletion

### 3.6 Remove dead code

**File:** `extradoc/src/extradoc/diff_engine.py`

Delete entirely:

| Function/Block | Approx Lines | Reason |
|---------------|-------------|--------|
| Global reordering + index adjustment | 454-668 | Replaced by backwards walk |
| `_generate_merged_body_insert()` | 793-886 | Bandaid for flat approach |
| `_generate_requests_for_change()` | 671-754 | Dispatcher replaced by walk |
| `_handle_content_block_change()` | 889-991 | Replaced by `_emit_content_block()` |
| `_handle_table_change()` | 994-1061 | Replaced by `_emit_table()` |
| `_generate_table_modify_requests()` | 2402-2585 | Replaced by `_emit_table_modify()` |

Also remove all `"_skipReorder": True` markers from `_generate_content_insert_requests()` and `_generate_table_add_requests()`. These markers existed to prevent the global reorder from splitting paired requests. There is no reorder step anymore, so they are dead code.

**Net change:** ~800 lines removed, ~200 lines added → ~600 lines smaller.

### 3.7 Fix `_get_table_start_index()` for multi-table sections

**File:** `extradoc/src/extradoc/diff_engine.py`, line 2588

The current function hardcodes `f"{section_type}:0"`, which breaks for documents with 2+ tables. For TABLE MODIFIED, we now use `change.pristine_start_index` directly (from Step 3.2), so this function is only needed for column width changes (which use `current_table_indexes`).

Fix: accept a `table_position` parameter defaulting to 0. Callers that know the table's ordinal position can provide it. This is sufficient for current usage while unblocking multi-table support.

---

## 4. Testing

### 4.1 Test Protocol

All testing against the live Google Doc:
`https://docs.google.com/document/d/1VjZV7QjYZ8yTkQ0R-xffxQ5I7mNIPD3eSv327scMACQ/edit`

Each test case follows this flow:

1. **Pull** → `extradoc/output/`
2. **Edit** `document.xml`
3. **Save expected** → `cp document.xml expected.xml`
4. **Diff** → `python -m extradoc diff <folder> > diff.json`
5. **Push** → `python -m extradoc push <folder>`
6. **Repull** → `python -m extradoc pull <url> extradoc/output-after/`
7. **Assert** → compare `expected.xml` vs repulled `document.xml`

### 4.2 Scripted Assertion

The ExtraDoc XML output is almost entirely deterministic across pulls:

- **Table/row/cell IDs**: Content-hashed via SHA256 (`content_hash_id()` in `xml_converter.py`). Same content → same ID.
- **Style class names**: Deterministic hash via MD5 of sorted properties (`style_id()` in `style_hash.py`).
- **Header/footer/footnote IDs**: Copied verbatim from Google Docs API.
- **All content markup**: Deterministic conversion from API response.

**Only unstable field: `<doc revision="...">`** — increments on every push.

This means a simple comparison after stripping `revision` gives a reliable assertion:

```bash
sed 's/ revision="[^"]*"//' expected.xml > /tmp/expected_stripped.xml
sed 's/ revision="[^"]*"//' output-after/<doc_id>/document.xml > /tmp/actual_stripped.xml
diff /tmp/expected_stripped.xml /tmp/actual_stripped.xml
```

- **Empty diff** = push was perfect.
- **Non-empty diff** = something went wrong. The diff + saved `diff.json` are the debugging artifacts.

For cases where new elements are created (new tables, new headers), the content-hashed IDs in the repulled version won't match the expected file (since the expected file has the pre-push IDs). These ID differences are expected and benign. An LLM reviewing the diff can distinguish "ID changed because content was created" from "content is wrong."

### 4.3 Test Cases

Run incrementally — each on its own pull-push cycle.

| # | Test Case | Edit Description |
|---|-----------|-----------------|
| 1 | Modify a paragraph | Change text in an existing `<p>` |
| 2 | Add paragraphs | Add new `<p>` elements between existing ones |
| 3 | Delete paragraphs | Remove `<p>` elements |
| 4 | Mixed body changes | Modify one paragraph, add another, delete a third |
| 5 | Modify table cell | Change text inside a `<td>` |
| 6 | Add + modify around table | Add paragraphs before/after an existing table |
| 7 | Header + body changes | Modify both a header and body content simultaneously |
| 8 | Formatting changes | Add `<b>`, `<i>`, `<a>` tags to existing text |

### 4.4 Existing Tests

```bash
cd extradoc && uv run pytest tests/ -v
```

The existing golden-file tests (46 tests across `test_block_diff.py`, `test_indexer.py`, `test_pull_integration.py`, `test_transport.py`) must pass. These validate that `pull` and `block_diff` still work correctly after the `block_diff.py` changes.

### 4.5 Lint and Type Check

```bash
cd extradoc && uv run ruff check . && uv run ruff format . && uv run mypy src/extradoc
```

---

## 5. Files Modified

| File | Change |
|------|--------|
| `extradoc/CLAUDE.md` | Replace diff algorithm section with 3-paragraph backwards walk description |
| `extradoc/src/extradoc/block_diff.py` | Propagate `pristine_start_index`/`pristine_end_index` for TABLE changes; update `last_pristine_end_index` tracking (2 small edits) |
| `extradoc/src/extradoc/diff_engine.py` | Rewrite `diff_documents()` orchestrator; add `_group_changes_by_segment()`, `_walk_segment_backwards()`, `_emit_content_block()`, `_emit_table()`, `_emit_table_modify()`; remove global reordering, merged body insert, `_skipReorder`, old handlers |
