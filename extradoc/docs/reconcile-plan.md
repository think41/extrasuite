# Plan: `reconcile` Module for ExtraDoc

## Original Requirements (Verbatim)

> See @extradoc/src/extradoc/api_types/__init__.py - it represents a google doc in the class Document, and Request class which represents all the possible ways to update a Document. This is the API surface of google docs.
>
> Now, in extradoc we pull the Document and convert it to XML, then diff+push - which ultimately results into BatchUpdateDocumentRequest which has a list of Request. In other words, if you squint and disregard the internals of extradoc - the general idea of the entire library can be summarized as :
> - pull a Document d
> - make edits to get another Document d'
> - diff d and d' to generate a BatchUpdateDocumentRequest
> - push to get a d''
> - assert that d' and d'' are semantically equivalent.
>
> What I am getting at - the Document to XML conversion and XML diff to generate the batchUpdate requests is internal. I would first like to focus on a robust Document-Document diff to get to BatchUpdateDocumentRequest.
>
> So here is the ask: Plan a new module that has a single method that takes this signature:
>
> reconcile(base:Document, desired:Document) -> BatchUpdateDocumentRequest
>
> Internally, to verify, it must take a Transport. See @extradoc/src/extradoc/mock/ - we have an entire module that supports the Google Docs API. So you should be able to test this out completely.
>
> Some conventions:
> - We will always request the Document with tabs. So all processing must happen wrt Tabs.
> - If Tabs have been added/removed - add_document_tab or delete_tab. tab properties can also be updated with update_document_tab_properties
> - A Tab has body, headers, footer, footnotes. These have corresponding requests to create or delete. delete footnote doesn't exist, a footnote is deleted by deleting the footnote reference in the paragraph where it is attached.
> - The body, header, footer, footnotes - all have a content field which is a list of StructuralElement. So the processing of these will be identical.
> - A StructuralElement can be 4 things - paragraph, table, section break or table of contents.
> - Table of contents is readonly - there is no way to create one programmatically. So raise a ReadonlyError if you detect changes in table of contents
> - SectionBreak can be deleted with DeleteContentRange, and created with InsertSectionBreakRequest
> - Table has several things going on. There are methods to create insert or delete table, row or column. You can merge/unmerge cells.
> - Within a Cell, again we have a List of StructuralElement. This means we recurse into it and deal it like a Content
> - Paragraphs are complex things, but largely explanatory from an API surface perspective.
>
> Based on all of this, please design this module. Key design questions IMO -
> - How do you detect what has changed? Very few things have ids. Notably, StructuralElement don't have ids, and positions change with every operation.
>
> Success Criteria:
> - reconcile.py with reconcile method with the signature (base:Document, desired:Document) -> BatchUpdateDocumentRequest
> - When BatchUpdateDocumentRequest is provided to mock against base:Document - we will get back a new Document actual.
> - actual and desired should match (not exact match, but intent wise)
> - This should work across all kinds of changes across the spectrum of allowed changes. Use code coverage to guide you in this area. We must have full code coverage across the API surface and across the reconciliation logic.

### Design Decisions (from Q&A)

- **Desired document indices**: Caller must provide a desired Document with correct indices (not stale). A `reindex_document()` helper is provided for convenience.
- **Verification**: Separate `verify()` function (not built into `reconcile()`). `reconcile()` returns requests; `verify(base, requests, desired)` applies via mock and compares.
- **Phasing**: Structure first (tabs, headers, footers, paragraphs, tables), styles later.
- **Test helper**: Tests create Documents without indices, then call `reindex_document()` which auto-computes indices using existing `mock/reindex.py` logic.

---

## Context

ExtraDoc currently diffs XML representations of Google Docs. This new module operates directly on Pydantic `Document` models — given a `base` and `desired` Document, it produces a `BatchUpdateDocumentRequest` that transforms base into desired. This enables a simpler conceptual model: Document → Document diff, without the XML intermediary.

## Public API

```python
# extradoc/src/extradoc/reconcile/__init__.py

def reconcile(base: Document, desired: Document) -> BatchUpdateDocumentRequest
def verify(base: Document, requests: BatchUpdateDocumentRequest, desired: Document) -> tuple[bool, list[str]]
def reindex_document(doc: Document) -> Document  # For test convenience

class ReconcileError(Exception): ...
```

- **`reconcile`**: Diffs two Documents with valid indices, returns batch update requests
- **`verify`**: Applies requests to base via `MockGoogleDocsAPI`, compares result with desired, returns `(match, diff_descriptions)`
- **`reindex_document`**: Converts Document to dict, runs `reindex_and_normalize_all_tabs()` from `mock/reindex.py`, converts back. Tests create Documents without worrying about indices, then call this.

## File Structure

```
extradoc/src/extradoc/reconcile/
    __init__.py          # Public API: reconcile(), verify(), reindex_document(), ReconcileError
    _alignment.py        # LCS-based alignment of StructuralElements between base/desired
    _extractors.py       # Extract text, fingerprints, segments from Pydantic models
    _generators.py       # Generate request dicts from aligned element pairs
    _comparators.py      # Normalize + compare Document dicts for verify()
```

## Algorithm Overview

### Step 1: Tab alignment
Match tabs by `tab_properties.tab_id`. Detect added/deleted/modified tabs.

### Step 2: Segment alignment (per tab)
For each matched tab, extract segments: body, headers (by header_id), footers (by footer_id), footnotes (by footnote_id). Match by ID.

### Step 3: StructuralElement alignment (LCS)
For matched segments, align the two `content: list[StructuralElement]` lists using LCS on content fingerprints:
1. **Fingerprint each element**: type + text content (concatenated text from all runs; recursive for tables)
2. **LCS**: Find longest common subsequence of fingerprints
3. **Result**: Each element → MATCHED, DELETED, or ADDED

### Step 4: Request generation (reverse index order)
Process from highest base index to lowest:
- **DELETED**: `deleteContentRange` covering the element's range (protect segment-final `\n`)
- **ADDED**: `insertText` at position + `insertTable` for tables + content population
- **MODIFIED paragraph**: Delete old content (preserve `\n`), insert new text, apply styles
- **MODIFIED table**: Row/column add/delete, recursive cell content diff

## `reindex_document` — Test Helper

Tests create Documents without indices, then call `reindex_document()`:

```python
def reindex_document(doc: Document) -> Document:
    """Reindex a Document using mock/reindex.py logic.

    Converts to dict, runs reindex_and_normalize_all_tabs(), converts back.
    Allows tests to create Documents without worrying about indices.
    """
    doc_dict = doc.model_dump(by_alias=True, exclude_none=True)
    reindex_and_normalize_all_tabs(doc_dict)
    return Document.model_validate(doc_dict)
```

This reuses `mock/reindex.py:reindex_and_normalize_all_tabs()` which walks all content and assigns correct UTF-16 indices. Tests look like:

```python
def test_add_paragraph():
    base = reindex_document(Document.model_validate({
        "documentId": "test",
        "tabs": [{"tabProperties": {"tabId": "t.0"}, "documentTab": {"body": {"content": [
            {"sectionBreak": {}},
            {"paragraph": {"elements": [{"textRun": {"content": "Hello\n"}}]}}
        ]}}}]
    }))

    desired = reindex_document(Document.model_validate({
        "documentId": "test",
        "tabs": [{"tabProperties": {"tabId": "t.0"}, "documentTab": {"body": {"content": [
            {"sectionBreak": {}},
            {"paragraph": {"elements": [{"textRun": {"content": "Hello\n"}}]}},
            {"paragraph": {"elements": [{"textRun": {"content": "World\n"}}]}}
        ]}}}]
    }))

    result = reconcile(base, desired)
    ok, diffs = verify(base, result, desired)
    assert ok, diffs
```

## Key Files to Reference

| File | Why |
|------|-----|
| `api_types/_generated.py` | All Pydantic models (Document, Request, StructuralElement, etc.) |
| `mock/api.py` | MockGoogleDocsAPI interface for verify() |
| `mock/reindex.py` | `reindex_and_normalize_all_tabs()` — reused by `reindex_document()` |
| `indexer.py` | `utf16_len()` — UTF-16 code unit calculation |

## Design Decisions

### Testing philosophy
Only test via public interface (`reconcile`/`verify`). No unit tests for internal modules (`_extractors`, `_generators`, `_alignment`, `_comparators`) — internal abstractions will evolve as phases are added, but the public API is stable. Every test calls `reconcile()` then `verify()` to ensure end-to-end correctness.

### Performance
LCS alignment is O(n*m) where n and m are the number of StructuralElements. The comparator does 3 passes (normalize, compare, diff). This is not optimized but correctness comes first. For typical documents (<1000 elements), performance is not a concern.

## Phased Implementation (Structure First, Styles Later)

### Phase 1: Scaffolding + paragraph text (body only) — DONE

All 5 files created, 23 tests passing, lint/mypy/format clean. See `tests/test_reconcile.py`.

### Phase 2: Tables (body only) — DONE

52 table tests passing (23 Phase 1 + 21 Phase 2 base + 8 new structural tests). Full structural row/column operations with proper `insertTableRow`, `deleteTableRow`, `insertTableColumn`, `deleteTableColumn` requests.

**Implementation:** Replaced the dimension-based dispatch (`_diff_table_replace` for different dimensions, `_diff_table_cells` for same dimensions) with a unified `_diff_table_structural()` that always uses proper row/column operations. All table diffs now go through structural diff regardless of dimension changes.

**Key components:**
- `align_sequences()` in `_alignment.py`: Generic LCS alignment with positional fallback (guarantees ≥1 MATCHED entry when both sequences non-empty)
- `row_fingerprint()`, `column_fingerprint()` in `_extractors.py`: Text-based fingerprints for alignment
- `_RowTable` tracker: Maintains current table state for UTF-16 index computation during bottom-to-top processing
- Request generation order: (1) column deletes (right-to-left), (2) column inserts (right-to-left), (3) row ops + cell content (bottom-to-top, interleaved)

**Learnings for Phase 3:**
1. **Bottom-to-top ordering works**: Processing highest index first keeps all lower indices valid for both structural ops (row/column indices) and content ops (character indices)
2. **Positional fallback is essential**: When table content is completely different (no LCS matches), positional alignment pairs rows/columns by index, providing stable anchors for structural diff
3. **State tracking is simpler than index prediction**: The `_RowTable` tracker maintains actual row lengths and computes indices on-demand, eliminating error-prone manual index arithmetic
4. **Alignment can be reused**: `align_sequences()` is generic and will work for any fingerprint-based alignment (tabs, segments, inline elements in future phases)

### Phase 3: Multi-segment (headers, footers, footnotes) — DONE

58 tests passing (52 Phase 1+2 + 6 new Phase 3). Deletion and content modification work fully. Creation is partial (segment created but not populated).

**Implementation:** Added segment creation/deletion logic to `_core.py:_reconcile_tab()`. When segments don't match by ID:
- **Added segment**: generate `createHeader`/`createFooter` request, then call `_reconcile_new_segment()` (currently stubbed)
- **Deleted segment**: generate `deleteHeader`/`deleteFooter` request
- **Matched segment**: existing `_reconcile_segment()` handles content diff (works for all segment types)

**Request generators** in `_generators.py`:
- `_make_create_header(header_type, tab_id)` → `createHeader` with `type="DEFAULT"`, no `sectionBreakLocation` (applies to DocumentStyle)
- `_make_delete_header(header_id, tab_id)` → `deleteHeader`
- `_make_create_footer(footer_type, tab_id)` → `createFooter` with `type="DEFAULT"`
- `_make_delete_footer(footer_id, tab_id)` → `deleteFooter`

**Mock API bug fixes** in `segment_ops.py`:
- `handle_delete_header` was validating but not deleting → added `del headers[header_id]`
- `handle_delete_footer` was validating but not deleting → added `del footers[footer_id]`
- When deleting the last header/footer, remove empty `headers`/`footers` dict from `documentTab` to match expected document structure

**Tests** in `test_reconcile.py`:
- `test_delete_header` — delete header, verify with full reconcile+verify cycle
- `test_delete_footer` — delete footer
- `test_modify_header_content` — change header text (tests matched segment diff)
- `test_modify_footer_content` — change footer text
- `test_create_header` — partial: creates empty header (content population deferred to Phase 4+)
- `test_create_footer` — partial: creates empty footer

**Partial implementation note**: `_reconcile_new_segment()` currently returns empty list. Full content population requires solving the ID assignment problem:
- User's desired document has segment with ID "hdr_xyz"
- `createHeader` returns new ID "hdr_abc" from API
- Content requests must reference "hdr_abc", not "hdr_xyz"
- This requires multi-pass execution or placeholder ID rewriting (like push.py's 3-batch approach)
- Deferred to Phase 4+

**Footnotes**: Deferred to Phase 4+. Footnotes are created via `createFootnote` which inserts a `footnoteReference` element in a paragraph. This requires element-level diffing (detecting added `footnoteReference` in paragraph elements), which is beyond current paragraph text diffing.

**Learnings for Phase 4:**
1. **Segment deletion works cleanly**: Just remove from dict, cleanup empty dict
2. **Segment creation needs multi-pass**: Can't generate content requests without knowing the new segment ID
3. **Content diff is segment-agnostic**: `_reconcile_segment()` works for body/headers/footers/footnotes without modification
4. **Mock API completeness**: Found and fixed bugs in mock's delete handlers — shows value of comprehensive testing

### Phase 4: Multi-tab
- `addDocumentTab`, `deleteTab`, `updateDocumentTabProperties`
- Content requests scoped to tab via `tab_id` in Location/Range
- **Tests**: add tab with content, delete tab, rename tab, modify content across tabs

### Phase 5: Paragraph styles + text styles
- `updateParagraphStyle` generation (namedStyleType, alignment, spacing, etc.) with field masks
- `updateTextStyle` generation (bold, italic, links, fonts, colors) with field masks
- Bullet handling: `createParagraphBullets`, `deleteParagraphBullets`
- **Tests**: heading changes, bold/italic, bullet lists, mixed style changes

### Phase 6: Edge cases + coverage
- tableOfContents validation (raise `ReconcileError` if changed)
- Section breaks (`insertSectionBreak`, `deleteContentRange`)
- Special paragraph elements: inline objects, page breaks, footnote references, horizontal rules
- UTF-16 correctness (emoji)
- Named ranges
- Full code coverage audit

## Verification: `verify()` Implementation

1. `base.model_dump(by_alias=True, exclude_none=True)` → dict
2. Create `MockGoogleDocsAPI(base_dict)`
3. Convert `BatchUpdateDocumentRequest.requests` to list of request dicts
4. `mock.batch_update(request_dicts)`
5. `actual = mock.get()`
6. `desired_dict = desired.model_dump(by_alias=True, exclude_none=True)`
7. Normalize both dicts (strip server-generated IDs like `headingId`/`listId`, ignore `revisionId`, etc.)
8. Deep-compare, return `(match, list_of_differences)`

---

## Implementation Learnings (Phase 1)

### Gap-based request generation

The original plan described a simple "reverse index order" approach. In practice, the request generation needed a **gap-based approach** to handle edge cases correctly:

1. LCS alignment produces MATCHED anchors with DELETED/ADDED elements between them
2. Consecutive non-MATCHED elements are grouped into "gaps" between anchors
3. Each gap is processed as a unit: delete the contiguous base range, then insert desired text
4. Gaps are processed right-to-left so indices remain valid

This was necessary because naive element-by-element processing (insert-then-delete or delete-then-insert) fails for the **full replacement case** — when all content is replaced (no LCS matches), interleaving inserts and deletes produces extra empty paragraphs.

### Segment-final `\n` protection

The Google Docs API forbids deleting the final `\n` of any segment. Three cases:

| Case | Delete range | Insert approach |
|------|-------------|-----------------|
| **Non-last element** | `[start, end)` — full range | Insert full text at gap start |
| **Last element, has predecessor** | `[pred.end-1, end-1)` — eats preceding `\n`, protects final | Insert `"\n" + text_stripped` at `pred.end-1` |
| **Only element (besides SB)** | `[start, end-1)` — clear content, keep final `\n` | Insert `text_stripped` at `start` (after SB) |

### Section break `startIndex`

Per the mock's `reindex.py`, the first element in body content has `startIndex = None` (not 0), but does have `endIndex = 1`. The `_el_start()` helper defaults `None` to `0`.

### `_comparators.py` normalization

The comparator strips many server-generated keys (`revisionId`, `documentId`, `headingId`, `lists`, `namedStyles`, `documentStyle`, etc.) and removes empty `textStyle`/`paragraphStyle` dicts. This is essential because the mock produces slightly different metadata than a freshly-constructed desired Document.

### `Segment` dataclass

`extract_segments()` returns `dict[str, Segment]` where `Segment` is a frozen dataclass wrapping the source model (`Body`/`Header`/`Footer`/`Footnote`). Properties `segment_id` and `content` derive from the source, eliminating untyped dicts and defensive dict-to-model conversion.

### Pydantic model construction

`BatchUpdateDocumentRequest` requires all fields including `writeControl=None` (alias form). Using `populate_by_name=True` means both `write_control` and `writeControl` work, but mypy only accepts the alias form.

### Test helper `_make_doc()`

The `_make_doc(*paragraphs)` helper creates a Document with a section break + N paragraphs, auto-appends `\n`, and calls `reindex_document()`. This makes tests extremely concise — a single line per document.
