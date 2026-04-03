# Refactor: Unified Content Path and Deferred IDs

## The Vision

### The Reconciler is a Tree Walker

A `Document` is a tree. It has `Tab`s. Tabs have Headers, Footers, and a Body.
There are five things that have **content** — header, footer, body, footnote,
and table cell. Content is a list of `StructuralElement`s, which is one of four
things: `TableOfContents`, `Paragraph`, `Table`, `PageBreak`. So there is
recursion involved.

**The unified-content invariant**: When we have a "content" that is a list of
StructuralElements, then whether it is an insert/delete/update — it must go
through the **exact same code path**. We may not have the ID yet (deferred), or
we may need to start at a different index (table cell), or we may not support
some features (PageBreak inside a header?) — but the approach is exactly the
same and there must be exactly **one implementation**. We are violating this
invariant in several places today.

### The Reconciler is a Planner; the Executor is an Executor

For any object whose ID is not known at planning time (new tabs, new headers,
new footers, new footnotes), the reconciler emits a **deferred placeholder
dict** in place of the real ID:

```python
{"placeholder": True, "batch_index": 0, "request_index": 3,
 "response_path": "createHeader.headerId"}
```

The executor runs batch N, reads real IDs from the response, substitutes all
placeholders in batch N+1 via `resolve_deferred_placeholders`, and continues.
Neither layer knows the other's internals.

This mechanism is already proven for segment IDs (headers, footers, footnotes).
The gap is that the deferred dict is accepted by `_lower_story_content_insert`
but **not** by `_lower_paragraph_insert` or any of its builder helpers. Those
functions take `tab_id: str` and `segment_id: str | None` — hard `str` types
that reject placeholders. Every caller of `_lower_paragraph_insert` must
therefore be in a context where the IDs are already resolved, which is why
`_lower_story_content_insert` was written as a separate, duplicated function
instead of delegating.

**The deferred-ID invariant**: every function that builds a `batchUpdate`
request must accept `str | dict` for `tab_id` and `segment_id`. Deferred
placeholder dicts flow through unchanged; the executor substitutes them at
runtime. There is no need for any special-case logic in the builders
themselves.

### No Newline Awareness, No `endOfSegmentLocation`

Active code must be completely unaware of the trailing newline that the Google
Docs API mandates at the end of every content block, and must never use
`endOfSegmentLocation`.

`endOfSegmentLocation` exists in `_lower_story_content_insert` because the
function was written to avoid computing an absolute index. But the index **is**
computable. A freshly created header, footer, or footnote has exactly one empty
paragraph. Its terminal `\n` occupies index 1 in the segment's coordinate
space. So the first paragraph we insert goes at index 1, the second at
1 + utf16_len(first_text), and so on — the same arithmetic `_lower_paragraph_insert`
already uses.

`endOfSegmentLocation` is therefore a complexity that exists only to paper over
a design gap. Once we unify the content path, it disappears entirely.

---

## What Is Broken Today

### Two (Nearly Three) Implementations of the Same Thing

| Function | Location | Used when |
|----------|----------|-----------|
| `_lower_story_content_update` | `lower.py:698` | Body/header/footer — segment exists, indices known |
| `_lower_story_content_insert` | `lower.py:2187` | New header/footer/footnote — segment ID is deferred |
| *(missing)* | — | New tab body — tab ID is deferred |
| *(missing)* | — | New table cells — indices computable, no deferred IDs |

`_lower_story_content_insert` was written as a separate function to handle the
`endOfSegmentLocation` mechanic. In doing so it duplicated the style-application
logic from `_lower_paragraph_insert` — and in the duplication it lost the
`_PARA_STYLE_READONLY_FIELDS` filter, bullet support, table support, and
page-break support.

### Hard `str` Types Block Deferred IDs from Flowing

`_lower_paragraph_insert`, `_lower_element_insert`, and all builder helpers
(`_make_insert_text`, `_make_update_paragraph_style`, etc.) take `tab_id: str`
and `segment_id: str | None`. A deferred placeholder dict cannot be passed.
This forces the content-insert path to be a separate function with duplicated
logic.

### `InsertTabOp` Has No Body Content

`lower_batches` emits `addDocumentTab` for `InsertTabOp` and stops. A new tab's
body content is never generated. This is the same pure-insert problem as new
segments — a deferred tab ID and `segment_id=None` (body has no segment ID).

### `_lower_table_insert` Emits No Cell Content

The function notes this explicitly in its docstring: "cell content requires a
separate pass that is not yet implemented." The index arithmetic for cell
positions is proven in `tests/reconcile_v3/test_lower.py`; the only gap is
wiring.

### Legacy String Sentinel `__LAST_ADDED_TAB_ID__`

`resolve_deferred_placeholders` in `reconcile_v2/executor.py` (lines 70–87)
has a special-case check for the string `"__LAST_ADDED_TAB_ID__"`. This is the
old workaround that predates the structured placeholder dict. It must be removed
once `InsertTabOp` emits properly structured placeholders.

---

## The Fix

### Core Insight: Pure-Insert Content is Index Arithmetic

For any content block being inserted into a **new** container (segment or tab
body), we know the starting index without calling the API:

- New header/footer/footnote: terminal `\n` occupies index 1. First paragraph
  inserts at index 1. Each subsequent paragraph inserts at
  `1 + sum(utf16_len(prev_texts))`.
- New tab body: same structure, `segment_id=None`.
- New table cell: opener is 1 char, content starts at `cell_start + 1`.
  The index is computable from `insertTable`'s position and the table structure.

There is nothing special about these cases. They are all just `_lower_element_insert`
called in a loop with a running index — which is exactly what `_lower_story_content_update`
already does for inserts inside existing content.

### Step 1 — Widen Types to Accept Deferred Placeholder Dicts

Change `tab_id` and `segment_id` parameter types throughout `lower.py`:

```python
# Before
tab_id: str
segment_id: str | None

# After
tab_id: str | dict[str, Any]
segment_id: str | dict[str, Any] | None
```

This affects: `_lower_paragraph_insert`, `_lower_element_insert`,
`_lower_element_update`, `_lower_table_insert`, `_lower_section_break_insert`,
`_lower_page_break_insert`, and all `_make_*` builder helpers
(`_make_insert_text`, `_make_update_paragraph_style`, `_make_update_text_style`,
`_make_create_paragraph_bullets`, `_make_delete_paragraph_bullets`,
`_make_delete_content_range`, `_make_update_section_style_deferred`).

The builders construct plain dicts. A deferred placeholder dict passes through
unchanged as a dict value. The executor walks the entire request dict
recursively and substitutes it. No special-case logic needed in any builder.

### Step 2 — Write `_lower_content_insert`

Delete `_lower_story_content_insert`. Replace with a single function that
handles all pure-insert cases:

```python
def _lower_content_insert(
    *,
    content: list[dict[str, Any]],        # StructuralElements to insert
    start_index: int,                      # first position to write into
    tab_id: str | dict[str, Any],
    segment_id: str | dict[str, Any] | None,
    desired_lists: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Insert a list of StructuralElements starting at start_index.

    Skips the terminal paragraph (the trailing \\n of the last element is
    never re-inserted; the container already has one).

    tab_id and segment_id may be deferred placeholder dicts; they are passed
    through to _lower_element_insert and ultimately to the builder helpers,
    where the executor resolves them at runtime.
    """
    requests: list[dict[str, Any]] = []
    running_index = start_index
    content_to_insert = content[:-1]   # skip terminal paragraph

    for el in content_to_insert:
        reqs = _lower_element_insert(
            el=el,
            index=running_index,
            tab_id=tab_id,
            segment_id=segment_id,
            desired_lists=desired_lists,
        )
        requests.extend(reqs)
        running_index += _element_size(el)

    return requests
```

`_element_size(el)` returns the character count of the element — for a
paragraph it is `utf16_len(_para_text(para))`, for a table it is computable
from the table structure. This function may already exist in lower.py or needs
a small helper.

**Callers** in `lower_batches`:
- `CreateHeaderOp` / `CreateFooterOp` / `InsertFootnoteOp`: replace the call to
  `_lower_story_content_insert(...)` with
  `_lower_content_insert(content=op.desired_content, start_index=1, tab_id=..., segment_id=deferred_id)`.
- `InsertTabOp`: see Step 3.

### Step 3 — Wire `InsertTabOp` to Generate Body Content

```python
case InsertTabOp():
    req_index = len(batch0)
    batch0.append(_make_add_document_tab(...))

    deferred_tab_id: dict[str, Any] = {
        "placeholder": True,
        "batch_index": 0,
        "request_index": req_index,
        "response_path": "addDocumentTab.tabProperties.tabId",
    }

    desired_body = _extract_tab_body_content(op.desired_tab)
    batch1.extend(
        _lower_content_insert(
            content=desired_body,
            start_index=1,
            tab_id=deferred_tab_id,
            segment_id=None,              # body has no segmentId
        )
    )
```

`_extract_tab_body_content(tab_dict)` extracts `tab["documentTab"]["body"]["content"]`,
skipping any leading `sectionBreak` element (which `addDocumentTab` creates
automatically).

### Step 4 — Wire Cell Content in `_lower_table_insert`

After emitting `insertTable`, walk the desired table's rows and cells. For each
cell, call `_lower_content_insert` at the computed absolute index:

```python
# After the insertTable request:
cell_start = index + 1     # skip table opener (1 char)
for row in table.get("tableRows", []):
    cell_start += 1        # skip row opener (1 char)
    for cell in row.get("tableCells", []):
        cell_content = cell.get("content", [])
        requests.extend(
            _lower_content_insert(
                content=cell_content,
                start_index=cell_start + 1,    # skip cell opener
                tab_id=tab_id,
                segment_id=segment_id,
            )
        )
        cell_start += _cell_size(cell)
```

`_cell_size(cell)` = `sum(_element_size(el) for el in cell["content"])` + 1
(for the cell opener character).

### Step 5 — Remove `endOfSegmentLocation`

After Step 2 is complete, `_lower_story_content_insert` is gone and
`endOfSegmentLocation` no longer appears anywhere in `lower.py`. Grep the
entire codebase to confirm there are no other occurrences in active code paths.

### Step 6 — Retire `__LAST_ADDED_TAB_ID__`

After Step 3 is complete:

1. Remove lines 70–87 of `reconcile_v2/executor.py` that handle the
   `"__LAST_ADDED_TAB_ID__"` string sentinel.
2. Grep for `__LAST_ADDED_TAB_ID__` across the entire repo to confirm no other
   emitter remains.

---

## Concrete Code Changes

| File | Change |
|------|--------|
| `reconcile_v3/lower.py` | Widen `tab_id`/`segment_id` in `_lower_paragraph_insert`, `_lower_element_insert`, `_lower_element_update`, all `_make_*` builders |
| `reconcile_v3/lower.py` | Delete `_lower_story_content_insert` |
| `reconcile_v3/lower.py` | Add `_lower_content_insert` (single pure-insert entry point) |
| `reconcile_v3/lower.py` | Add `_element_size` helper |
| `reconcile_v3/lower.py` | Update `CreateHeaderOp` / `CreateFooterOp` / `InsertFootnoteOp` handlers to call `_lower_content_insert` |
| `reconcile_v3/lower.py` | Extend `InsertTabOp` handler to emit body content via `_lower_content_insert` with deferred tab ID |
| `reconcile_v3/lower.py` | Extend `_lower_table_insert` to emit cell content via `_lower_content_insert` |
| `reconcile_v3/lower.py` | Add `_extract_tab_body_content` helper |
| `reconcile_v3/lower.py` | Add `_cell_size` helper |
| `reconcile_v2/executor.py` | Remove `__LAST_ADDED_TAB_ID__` string sentinel handling (lines 70–87) |

### Dead Code to Delete

- `_lower_story_content_insert` in full (replaced by `_lower_content_insert`).
- `__LAST_ADDED_TAB_ID__` handling in `executor.py`.
- Any remaining `endOfSegmentLocation` usage in active code paths.

---

## What `_lower_story_content_update` Is and Why It Stays

`_lower_story_content_update` handles the **update case** — diffing base and
desired content that both already exist. It is passed an `alignment` from
`align_content()` and must deal with deletions, in-place updates, and
insertions into existing content (where indices come from the base document's
actual `startIndex`/`endIndex` values, not from pure arithmetic).

This is genuinely different from pure-insert: in the update case we delete
ranges at known base indices, then insert at positions derived from surviving
base elements. `_lower_content_insert` cannot handle this because it has no
base document to reference.

`_lower_story_content_update` should **call `_lower_element_insert` and
`_lower_element_update`** (which it already does) so that the per-element logic
remains in one place. With the type widening from Step 1, `segment_id` and
`tab_id` can also be deferred dicts here if ever needed — but in practice the
update path always has known IDs (you can't diff against a segment that doesn't
exist yet).

The two functions are therefore complementary:

| Function | Input | When used |
|----------|-------|-----------|
| `_lower_content_insert` | desired content + start_index | New container (new tab, header, footer, footnote, table cell) |
| `_lower_story_content_update` | alignment + base + desired | Existing container being modified |

---

## Test Strategy

### Unit Tests (`tests/reconcile_v3/test_lower.py`)

1. **Deferred segment ID passes through builders** — call `_lower_paragraph_insert`
   with a deferred placeholder dict for `segment_id`; verify the placeholder
   dict appears verbatim in the emitted `insertText`, `updateParagraphStyle`,
   and `updateTextStyle` requests.

2. **`_lower_content_insert` produces the same output as the old
   `_lower_story_content_insert`** — for a simple paragraph with text and
   paragraph style, verify the new function with `start_index=1` emits
   byte-identical requests to the old implementation. This is the regression
   gate for the refactor.

3. **`_lower_content_insert` supports bullets** — insert a bullet paragraph
   into a new header (pass deferred `segment_id`); verify `createParagraphBullets`
   is emitted. The old `_lower_story_content_insert` silently dropped bullets.

4. **`_lower_content_insert` filters readonly fields** — use a paragraph whose
   `paragraphStyle` contains `headingId`; verify it is absent from the
   `updateParagraphStyle` fields mask. The old function did not filter these.

5. **`InsertTabOp` emits body content with deferred tab ID** — build an
   `InsertTabOp` with one body paragraph; call `lower_batches`; verify batch 0
   has `addDocumentTab`, batch 1 has `insertText` + `updateParagraphStyle` where
   `tabId` is the deferred placeholder dict.

6. **Deferred tab ID resolves correctly** — pass the batch 0 response through
   `resolve_deferred_placeholders`; verify the deferred tab ID is replaced with
   the real tab ID string from the response.

7. **`_lower_table_insert` emits cell content at correct indices** — build a
   desired 2×2 table with known text per cell; call `_lower_table_insert`; verify
   `insertTable` is followed by `insertText` at the correct absolute indices for
   each cell. Confirm with `make_indexed_table` / `make_indexed_cell` helpers.

8. **`__LAST_ADDED_TAB_ID__` is gone** — verify that `resolve_deferred_placeholders`
   does not handle the legacy sentinel, and that no emitter in `lower_batches`
   produces it.

9. **`endOfSegmentLocation` is absent** — grep `lower.py` for
   `endOfSegmentLocation` and assert the result is empty. This can be a simple
   string-search test or a CI lint rule.

### Live Tests (against real Google Doc)

Use `./extrasuite doc pull/push` and verify one full pull → edit → push →
re-pull cycle per scenario. These are the release-confidence gate.

Priority order:

1. **New header with paragraph + bullet** — push a desired state that adds a
   header containing a heading and a bullet list to a doc with no existing
   header. Re-pull and verify header content round-trips. This exercises the
   renamed `_lower_content_insert` call in the `CreateHeaderOp` path and
   confirms bullet support.

2. **New tab with body content** — push a desired state that adds a tab with
   several paragraphs. Re-pull and verify tab body round-trips. This exercises
   the new `InsertTabOp` body-content path and deferred tab ID resolution.

3. **Newly inserted table with cell content** — push a new table into the body.
   Re-pull and verify all cells contain the correct text. This exercises the
   new cell-content path in `_lower_table_insert` and confirms the cell index
   arithmetic.

4. **Existing scenarios still pass** — run the full existing test suite
   (`uv run pytest tests/ -v`) to confirm no regressions.

---

## Out of Scope

- Table cell bullets in newly inserted tables (can be added after single-paragraph
  cells are confirmed live).
- Multi-paragraph cells in newly inserted tables (same path; add after
  single-paragraph cells work).
- Named ranges in new tabs (separate concern).
- Updating `_lower_story_content_update` to call a shared per-element function
  for the update case — it already delegates to `_lower_element_update` and
  `_lower_element_insert`; no structural change needed there.

---

## Changelog

### Implemented (commit `0e637a7`)

All six steps from the plan were implemented:

**Step 1 — Type widening**: Added `_StrOrDeferred = str | dict[str, Any]` type alias. Widened `tab_id` and `segment_id` in all `_make_*` builders (`_make_insert_text`, `_make_update_paragraph_style`, `_make_update_text_style`, `_make_create_paragraph_bullets`, `_make_delete_paragraph_bullets`, `_make_delete_content_range`) and in `_lower_element_insert`, `_lower_paragraph_insert`, `_lower_table_insert`, `_lower_section_break_insert`, `_lower_page_break_insert`.

**Step 2 — `_lower_content_insert`**: Deleted `_lower_story_content_insert` (with its `endOfSegmentLocation` hack). Added `_element_size` helper (paragraph size from text, section break = 1, others from startIndex/endIndex). Added `_lower_content_insert` as the single unified pure-insert entry point. Updated `CreateHeaderOp`, `CreateFooterOp`, `InsertFootnoteOp` handlers to call `_lower_content_insert(start_index=1)`.

**Step 3 — `InsertTabOp` body content**: Added `_extract_tab_body_content` (extracts body elements, skips leading sectionBreak). Extended `InsertTabOp` handler to emit body content via `_lower_content_insert` with a properly structured deferred tab ID placeholder (`response_path = "addDocumentTab.tabProperties.tabId"`).

**Step 4 — `_lower_table_insert` cell content**: Rewrote `_lower_table_insert` to iterate rows and cells after `insertTable`, computing absolute content positions via running `table_pos` arithmetic. Each cell's content is inserted via `_lower_element_insert`.

**Step 5 — Remove `endOfSegmentLocation`**: Gone from `lower.py` as a result of Step 2. Confirmed by grep.

**Step 6 — Retire `__LAST_ADDED_TAB_ID__`**: Removed 18 lines from `reconcile_v2/executor.py`. No emitters remain.

### Bug fixed during live testing (commit `TBD`)

**Discovered**: Cell content from the markdown serde is `[para("Feature\n")]` — one paragraph, no separate terminal. `_lower_table_insert` used `content[:-1]` (via `_lower_content_insert`) which skipped the only element, producing zero `insertText` requests for cell content.

**Root cause**: `content[:-1]` assumes a terminal paragraph is always present as the last element (which is true for body/header/footer content and for real API-pulled table cells). The markdown deserialiser produces single-paragraph cells without a terminal.

**Fix**: Added `_is_cell_terminal(el)` helper that returns True if an element is a bare `\n` paragraph. In `_lower_table_insert`, replaced `_lower_content_insert(content=cell_content)` with a direct loop that filters terminal paragraphs and calls `_lower_element_insert` for each remaining element. Both cell formats now work:
- Real API pull: `[para("Feature\n"), para("\n")]` → terminal filtered, inserts "Feature\n"
- Markdown serde: `[para("Feature\n")]` → nothing filtered, inserts "Feature\n"

**Tests added**: `test_cell_with_no_terminal_paragraph_still_inserts_content` and `test_cell_with_explicit_terminal_paragraph_is_not_double_inserted`.
