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

## Phased Implementation (Structure First, Styles Later)

### Phase 1: Scaffolding + paragraph text (body only) — DONE

All 5 files created, 23 tests passing, lint/mypy/format clean. See `tests/test_reconcile.py`.

### Phase 2: Tables (body only)
- `_alignment.py`: `align_table_rows()` for row matching
- `_generators.py`: `insertTable`, `deleteContentRange` (whole table), row/column add/delete
- Recursive cell content diffing (cells contain `list[StructuralElement]`)
- **Tests**: add/delete tables, add/delete rows/columns, modify cell text

### Phase 3: Multi-segment (headers, footers, footnotes)
- Segment creation/deletion: `createHeader`/`deleteHeader`, `createFooter`/`deleteFooter`
- Footnote handling: detect added/removed `footnoteReference` in paragraphs; `createFootnote` for new
- Content diffing within headers/footers/footnotes (reuse segment diff logic)
- **Tests**: add/remove header, modify footer content, add/remove footnotes

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

### `_core.py` — `_reconcile_segment` input handling

Segment content from `extract_segments()` returns `list[StructuralElement]` (Pydantic models), but `_reconcile_segment` defensively handles both Pydantic objects and raw dicts via `isinstance` checks + `model_validate()`. This guards against future changes where content might arrive as dicts.

### Pydantic model construction

`BatchUpdateDocumentRequest` requires all fields including `writeControl=None` (alias form). Using `populate_by_name=True` means both `write_control` and `writeControl` work, but mypy only accepts the alias form.

### Test helper `_make_doc()`

The `_make_doc(*paragraphs)` helper creates a Document with a section break + N paragraphs, auto-appends `\n`, and calls `reindex_document()`. This makes tests extremely concise — a single line per document.
