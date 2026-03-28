# Reconciler Semantic IR Implementation Plan

## Scope

This plan implements the new reconciler in-tree under:

`extradoc/src/extradoc/reconcile_v2`

The existing `extradoc.reconcile` package remains untouched until `reconcile_v2`
is production-ready.

## Testing Policy

For `reconcile_v2`, every reconciler test follows the same contract:

1. construct `base: Document`
2. construct `desired: Document`
3. call `reconcile_v2.reconcile(base, desired)`
4. normalize the returned batches into plain request dicts
5. assert exact equality with expected batches

The oracle is the request sequence, not the mock.

The mock may still be used in a small number of transport-level tests, but it is
not the primary correctness oracle for `reconcile_v2`.

There is one additional allowed test class:

1. small lowering legality tests
2. no mock
3. direct assertions on:
   1. legal-point resolution
   2. end-of-segment resolution
   3. explicit unsupported-edit rejection
   4. field-mask and request normalization

These exist to validate lowering invariants that are smaller than a full
`base + desired -> exact plan` contract test.

Canonical helper shape:

```python
assert_reconcile_case(
    base=...,
    desired=...,
    expected_batches=[
        [ ... request dicts for batch 0 ... ],
        [ ... request dicts for batch 1 ... ],
    ],
)
```

Every task below must:

1. do one meaningful thing,
2. add direct contract tests,
3. be cleanly committable.

## Module Layout

Initial module layout:

```text
extradoc/src/extradoc/reconcile_v2/
  __init__.py
  ir.py
  parse.py
  diff.py
  layout.py
  lower.py
  requests.py
  testing.py
  errors.py
  tabs.py
  sections.py
```

Recommended test layout:

```text
extradoc/tests/reconcile_v2/
  __init__.py
  helpers.py
  test_*.py
```

## Task List

### Task 0: Scaffold `reconcile_v2` and the contract test harness

Deliverable:

1. create `extradoc.reconcile_v2` package
2. add stable public entrypoint:
   1. `reconcile(base, desired) -> list[BatchUpdateDocumentRequest]`
3. add `tests/reconcile_v2/helpers.py` with:
   1. request normalization
   2. `assert_reconcile_case`

Tests:

1. trivial empty-plan case:
   1. empty body to same empty body -> `[]`
2. helper normalization test:
   1. request models normalize to plain dicts deterministically

Commit value:

1. creates the isolated rewrite lane
2. establishes the one true test pattern
3. establishes the allowed lowering-legality micro-test shape

### Task 1: Define IR types and capability model

Deliverable:

1. implement immutable IR data structures in `ir.py`
2. encode container kinds and capabilities
3. encode implicit `eop` / `eos` sentinels as structural invariants

Tests:

1. body container advertises page-break capability
2. table-cell container rejects page-break capability
3. paragraph text excludes paragraph terminator by construction

Commit value:

1. makes illegal states explicit
2. freezes the semantic model before algorithms begin

### Task 2: Implement parser for body-only paragraphs

Deliverable:

1. parse Docs `Document` into `DocumentIR`
2. support:
   1. tabs
   2. body
   3. plain paragraphs
3. strip paragraph-final newline into `eop`
4. strip container-final newline into `eos`

Tests:

1. identical one-paragraph docs -> `[]`
2. append paragraph -> exact `insertText`
3. delete paragraph -> exact `deleteContentRange`
4. replace paragraph text -> exact in-paragraph text edit sequence

Commit value:

1. proves that newline sentinels can be removed from semantic content
2. gets the first real end-to-end request generation working

### Task 3: Introduce legal points and layout state for body paragraphs

Deliverable:

1. implement `LegalPoint`
2. implement `LayoutState` for body paragraph interiors and boundaries
3. forbid raw index construction outside `layout.py`

Tests:

1. insertion before first paragraph
2. insertion after last paragraph
3. delete middle paragraph without touching final container newline
4. end-of-segment location resolves immediately before the terminal sentinel

Commit value:

1. isolates index arithmetic
2. removes ad hoc positional math from reconciler logic

### Task 3A: Introduce end-of-segment lowering primitives

Deliverable:

1. implement `EndOfSegmentLocation` lowering for supported segment kinds
2. distinguish carrier-paragraph insertion from direct end-of-segment insertion
3. expose this through `LayoutState`

Tests:

1. body end resolves to legal `endOfSegmentLocation`
2. header end resolves to legal `endOfSegmentLocation`
3. footer end resolves to legal `endOfSegmentLocation`
4. footnote end resolves to legal `endOfSegmentLocation`

Commit value:

1. makes append-at-end a first-class lowering primitive
2. avoids synthetic paragraph tricks when the Docs API exposes a direct form

### Task 4: Implement paragraph semantic diff

Deliverable:

1. align matched paragraphs by structure, not raw text fingerprint only
2. implement inline text edit script
3. keep paragraph match stable across text change

Tests:

1. single-character substitution in one paragraph
2. prefix insertion in one paragraph
3. suffix deletion in one paragraph
4. unicode edit with surrogate pairs

Commit value:

1. eliminates delete/add block replacement for ordinary text edits

### Task 5: Implement paragraph style and text-style lowering

Deliverable:

1. lower paragraph style updates
2. lower text-style span updates
3. reuse current style diff logic only through a new lowering boundary
4. cap style ranges so they remain legal near paragraph/container end

Tests:

1. add bold to one span
2. remove italic from one span
3. paragraph alignment change only
4. paragraph style plus text change in same paragraph
5. style update on final visible span does not target terminal sentinel
6. full-paragraph style update in list context accounts for bullet side effects

Commit value:

1. establishes matched-paragraph editing as the default path

### Task 5A: Implement explicit-style vs effective-style resolution

Deliverable:

1. parse explicit text/paragraph styles into IR
2. implement effective-style resolver
3. diff on effective style while lowering only explicit deltas

Tests:

1. inherited bold vs explicit bold compare correctly
2. clearing a style to inherit from parent emits the correct field mask
3. span formatting next to differently styled text does not bleed

Commit value:

1. closes the main architectural hole around formatting bleed

### Task 6: Lift page break into semantic block and enforce capability checks

Deliverable:

1. parse pure page-break paragraphs as `PageBreakIR`
2. lower page breaks only in `BODY`
3. reject page breaks in `HEADER`, `FOOTER`, `FOOTNOTE`, `TABLE_CELL`

Tests:

1. insert page break between body paragraphs -> exact `insertPageBreak`
2. insert page break at body start -> exact `insertPageBreak`
3. page break inside table cell -> explicit error, no plan emitted

Commit value:

1. closes one known legality hole by construction

### Task 7: Introduce first-class `ListIR` and list canonicalization

Deliverable:

1. parse contiguous compatible bullet paragraphs into `ListIR`
2. derive semantic list spec from list properties, not raw `listId`
3. canonicalize list identity independent of server-generated IDs

Tests:

1. parse two adjacent bullets as one semantic list
2. parse bullet, plain paragraph, bullet as two lists
3. same semantic list despite different transport `listId`

Commit value:

1. removes list identity from transport IDs
2. fixes the root cause of "new list instead of attach to existing list"

### Task 7A: Implement list transport semantics for nesting and releveling

Deliverable:

1. model leading tabs used for list nesting as transport artifacts
2. teach lowering to synthesize/remove leading tabs around bullet creation
3. account for index shifts caused by `createParagraphBullets`

Tests:

1. create nested list from semantic levels -> exact request sequence
2. relevel one existing item -> exact delete-bullets/tab-edit/create-bullets flow
3. adjacent non-list text is index-stable across bullet creation

Commit value:

1. makes list lowering compatible with documented Docs list behavior

### Task 8: Lower list creation and list extension

Deliverable:

1. lower full list creation
2. lower append-to-existing-list
3. lower prepend-to-existing-list where legal

Tests:

1. create three-item list in empty body -> exact `insertText` + one bullet request
2. append one item to existing list -> exact request sequence proving continuation
3. insert paragraph between two list runs -> exact split behavior

Commit value:

1. delivers the first user-visible fix for list continuation

### Task 9: Lower list split, merge, and relevel

Deliverable:

1. split one list into two runs
2. merge adjacent compatible runs
3. relevel items safely

Tests:

1. split list by inserting plain paragraph
2. merge two compatible lists by deleting separator
3. change nesting level of one middle item

Commit value:

1. completes list semantics as a first-class feature

### Task 10: Introduce recursive table IR with cell containers

Deliverable:

1. parse tables as `TableIR`
2. parse each cell as `ContainerIR(kind=TABLE_CELL)`
3. route cell content through the same container parser

Tests:

1. parse 1x1 table with one paragraph cell
2. parse multi-paragraph cell
3. cell container advertises no page-break capability

Commit value:

1. unifies body and cell recursion
2. removes the conceptual split between body and cell content

### Task 11: Lower table insertion for body-only cases

Deliverable:

1. lower `TableIR` insertion in body
2. own pre-table newline as lowering artifact
3. do not model pre/post-table empty paragraphs semantically
4. support both paragraph-carried insertion and `endOfSegmentLocation`

Tests:

1. insert table at body end
2. insert table between paragraphs
3. insert table as first body block after section break

Commit value:

1. establishes the clean abstraction boundary for the table newline artifact

### Task 11A: Lower table insertion at header/footer end

Deliverable:

1. support `InsertTableRequest.endOfSegmentLocation` for header/footer
2. preserve the same semantic treatment of transport-introduced newlines

Tests:

1. insert table at header end
2. insert table at footer end

Commit value:

1. aligns table lowering with the documented end-of-segment request surface

### Task 12: Implement recursive cell content diff and lowering

Deliverable:

1. diff cell containers with the same engine as body containers
2. lower cell text/style edits
3. keep table cell legality checks capability-driven

Tests:

1. replace text in one matched cell
2. add second paragraph inside one cell
3. delete cell paragraph content without touching cell-final newline
4. reject page break in cell

Commit value:

1. validates the central recursive design claim

### Task 13: Implement table structural diff

Deliverable:

1. row alignment
2. column alignment
3. row/column insert/delete lowering
4. cell style lowering
5. deterministic table request ordering

Tests:

1. add row
2. delete row
3. add column
4. delete column
5. change table cell style only

Commit value:

1. completes supported table editing

### Task 13A: Implement full table feature support

Deliverable:

1. parse and diff merge topology
2. lower `MergeTableCellsRequest` and `UnmergeTableCellsRequest`
3. diff and lower pinned header rows
4. diff and lower table row styles
5. diff and lower table column properties
6. preserve merge invariants across row/column edits

Tests:

1. merge rectangular cell region
2. unmerge previously merged region
3. change pinned header row count
4. update row style only
5. update column properties only
6. row/column edit adjacent to merged region remains valid

Commit value:

1. matches and exceeds the current reconciler's effective table support surface

### Task 14: Parse sections and shared header/footer graph

Deliverable:

1. parse body section partition
2. parse section styles
3. represent header/footer attachments explicitly
4. represent shared header/footer segments explicitly
5. parse tab hierarchy (`parentTabId`, child tabs)

Tests:

1. single-section doc with default header
2. multi-section doc with distinct section attachments
3. two sections sharing same header segment
4. nested tab tree parses with stable parent/child relationships

Commit value:

1. replaces top-level header/footer hacks with explicit graph structure
2. prevents accidental flattening of tab topology

### Task 15: Lower header/footer creation, attachment, and content edits

Deliverable:

1. create shared header/footer segments
2. attach them to sections using `CreateHeaderRequest` /
   `CreateFooterRequest.sectionBreakLocation` when creating new scoped segments
3. lower content edits against the shared segment container
4. support multi-batch deferred IDs
5. use `UpdateSectionStyleRequest` only for actual section style updates

Tests:

1. create header in single-section doc
2. modify existing header content
3. attach existing shared header to another section
4. create footer and populate in dependent batch

Commit value:

1. completes shared segment support

### Task 16: Implement tab diff and tab creation

Deliverable:

1. tab property diff
2. tab creation/deletion
3. parent/child tab relationship preservation
4. dependent content population after tab creation

Tests:

1. rename tab only
2. add tab with body content
3. add tab with body plus header
4. add child tab under parent tab

Commit value:

1. completes document-level topology support

### Task 17: Add revision-aware batching and public API

Deliverable:

1. wire `requiredRevisionId`
2. finalize `reconcile_v2.reconcile`
3. expose stable public API without replacing `extradoc.reconcile`

Tests:

1. all prior contract tests run through public entrypoint
2. batch ordering test with deferred IDs

Commit value:

1. makes the module usable by callers

### Task 18: Replace verifier with semantic IR comparator

Deliverable:

1. implement `parse(actual_transport) -> actual_ir`
2. implement semantic equality for IR
3. remove list-identity erasure from `reconcile_v2` tests

Tests:

1. docs differing only by transport `listId` but same semantic list -> equal
2. docs with split vs merged list runs -> not equal
3. docs with different section attachments -> not equal
4. docs with different merge topology -> not equal
5. docs with different effective style but same explicit style source graph ->
   equal or not equal according to effective styling, not transport runs

Commit value:

1. makes test semantics match product semantics

### Task 19: Migration gate and shadow-mode coverage

Deliverable:

1. optional harness that runs both old and new reconciler on selected fixtures
2. record old/new request sequences for review
3. no caller migration yet

Tests:

1. selected regression fixtures produce valid `reconcile_v2` plans
2. known old bugs are covered by exact-plan tests

Commit value:

1. creates a safe adoption path without replacing existing behavior

## What To Reuse From Current Code

### Reuse as-is

1. `extradoc.indexer.utf16_len`
2. generated Docs API request/response models
3. `DeferredID`
4. deferred ID resolution
5. typed request validation

### Reuse behind a new boundary

1. request builder helpers
2. style diff helpers
3. table cell style diff helpers
4. named range request helpers

These must move under lowering, not remain interwoven with diff logic.

### Do not reuse as architecture

1. structural-element LCS as the primary diff model
2. slot/gap edit planning
3. list identity from transport `listId`
4. body detection from `segment_id is None`
5. synthetic newline compensation as a semantic strategy
6. transport comparator that erases semantic list structure

## Recommended Execution Order

Recommended order is exactly the numbered task order above.

The first usable milestone is after Task 8:

1. body paragraphs
2. page breaks
3. lists
4. exact-plan contract tests

That milestone already covers the major newline and list-attachment pain points
without requiring tables or headers to be complete.
