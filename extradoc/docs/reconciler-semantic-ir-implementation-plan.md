# Reconciler Semantic IR Implementation Plan

## Scope

This plan implements the new reconciler in-tree under:

`extradoc/src/extradoc/reconcile_v2`

The existing `extradoc.reconcile` package remains untouched until `reconcile_v2`
is production-ready.

Initial production scope preserves existing section-break topology. Section-break
insertion/deletion remains explicitly unsupported until a dedicated lowering
task exists.

## Testing Policy

For `reconcile_v2`, the primary contract test follows this shape:

1. construct `base: Document`
2. construct `desired: Document`
3. call `reconcile_v2.reconcile(base, desired)`
4. normalize the returned batches into plain request dicts
5. assert exact equality with expected batches

For lowering-focused tasks, the oracle is the request sequence.

But exact-plan assertions are not sufficient by themselves. Historical bugs in
this project frequently produced plausible-looking request sequences that were
still wrong after transport side effects, verifier normalization, or real-API
index differences.

`reconcile_v2` therefore allows two additional test classes:

1. small lowering legality tests
2. no mock
3. direct assertions on:
   1. legal-point resolution
   2. end-of-segment resolution
   3. explicit unsupported-edit rejection
   4. field-mask and request normalization

and:

1. semantic convergence tests
2. execute the emitted batches against the mock or a transport fixture
3. reparse the result into IR
4. assert semantic IR equality with `desired`

These exist to validate:

1. lowering invariants that are smaller than a full contract test
2. transport-side-effect behavior that exact-plan assertions alone do not prove
3. raw-transport fixtures where real API indices differ from mock reindexing

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

## Fixture Capture Standard

Confidence sprints are only valid if they leave behind reusable transport
fixtures and repeatable assertions. Ad hoc live probing without durable capture
does not count as progress.

For every new supported scenario, the default standard is:

1. capture a tiny purpose-built live Docs fixture pair
2. store `base.json` and `desired.json` under
   `tests/reconcile_v2/fixtures/<name>/`
3. store a human-readable `base.summary.txt` and `desired.summary.txt`
4. store any setup choreography needed to recreate the base state, such as
   `base.md`, `base.setup.requests.json`, or `base.header.txt`
5. if recreating the base state requires sequential setup batches or
   response-derived IDs, store `base.setup.batches.json` with explicit
   placeholders that the replay harness resolves from prior batch responses
6. store the transport mutation used to create the desired state as
   `desired.requests.json`
7. store the expected lowered request artifact adjacent to the fixture rather
   than only as an inline test constant:
   `expected.lowered.json` for one batch, or
   `expected.lowered.batches.json` for dependent multi-batch flows
8. when setup or lowering depends on response-derived IDs, store deferred
   placeholders in the fixture artifact rather than captured live IDs
9. add an offline exact-request assertion
10. add an explicit semantic diff assertion
11. add a live replay case through the shared replay harness when the scenario is
   in the supported slice

For every new unsupported scenario, the default standard is:

1. capture the same `base.json` / `desired.json` pair
2. store the transport probe used to demonstrate the target behavior
3. add an explicit rejection assertion with the expected error text
4. document the unsupported boundary in the design and edge-case docs

The reusable harness for this work lives in:

1. `extradoc/scripts/capture_reconcile_v2_fixtures.py`
2. `extradoc/scripts/replay_reconcile_v2_fixtures.py`
3. `extradoc/tests/reconcile_v2/test_diff_spike.py`
4. `extradoc/tests/reconcile_v2/test_canonical_and_lower_spike.py`
5. `extradoc/tests/reconcile_v2/helpers.py`

If a sprint cannot meet this standard, it should first improve the harness
before expanding feature scope.

## Recent Proven Rules

Recent live markdown verification added two concrete rules that now belong to
the implementation contract:

1. Markdown footnote syntax must be parsed into real body `footnoteReference`
   elements plus footnote stories. It is not enough to support only synthetic
   `<x-fn>` passthrough.
2. Footnote creation on an empty body must be planned after any content batch
   that materializes the target paragraph. Desired-side placeholder IDs are not
   required.
3. Editing a paragraph that already contains a trailing footnote reference must
   preserve the existing reference in place. The reconciler must replace only
   the paragraph text range, not the whole paragraph slice, or the reference
   and downstream paragraph boundary can be corrupted.
4. Horizontal rules remain a markdown-serde surface but are a reconciler
   readonly boundary because Google Docs cannot create them through the API.
   Base and desired may contain them unchanged, but `push-md` must reject HR
   create/delete edits explicitly.

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
  styles.py
  annotations.py
  executor.py
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

### Task 1: Define story/section IR, unified positions, and capability model

Deliverable:

1. implement immutable IR data structures in `ir.py`
2. encode body as ordered sections plus recursive stories for non-body content
3. introduce one logical `PositionIR` model shared by annotations and lowering,
   including nested block-local paths and explicit text offsets
4. encode story/container kinds and capabilities
5. encode implicit `eop` / `eos` sentinels as structural invariants

Tests:

1. body story advertises page-break capability
2. table-cell story rejects page-break capability
3. paragraph text excludes paragraph terminator by construction
4. body starts as a single empty section even before multi-section parsing lands

Commit value:

1. makes illegal states explicit
2. freezes the semantic model before algorithms begin

### Task 1A: Add style environment, typed header/footer slots, and anchored annotation IR

Deliverable:

1. extend `TabIR` with explicit style environment (`documentStyle`,
   `namedStyles`, list catalog)
2. represent section attachment state on `SectionIR` rather than in a duplicate
   side table
3. represent shared headers/footers/footnotes as explicit story resources
4. represent section attachments as typed header/footer slot maps rather than
   singular refs
5. add anchored annotation IR for named ranges using the new logical position
   model
6. parse inline/positioned object catalogs as explicit opaque semantic state

Tests:

1. first section parses as semantic section state rather than as an editable
   body block
2. first-page and even-page header/footer slots parse distinctly
3. named-range anchors survive canonicalization independent of server IDs
4. effective-style resolution has explicit access to tab style environment
5. inline object references resolve against parsed object catalogs

Commit value:

1. closes the main semantic-model gaps before algorithm work begins

### Task 1C: Add explicit canonicalization and lowerable edit payloads

Deliverable:

1. add a canonicalization phase between parse and diff
2. strip transport-only carrier paragraphs and equivalent transport noise there,
   not inside ad hoc diff rules
3. ensure semantic edits carry enough payload to lower deterministically
   (`section split` anchor, appended list fragment, etc.)
4. add canonical signatures/equivalence helpers for replay verification
5. add one story-local layout resolver that can target body, existing
   header/footer stories, table cells, and annotation anchors
6. match shared stories through logical attachment slots rather than transport
   story IDs

Tests:

1. section-split transport fixtures canonicalize to two visible sections with no
   carrier-paragraph noise
2. section-delete desired fixture canonicalizes equal to the pre-split base
3. semantic diff output for append/split edits contains the fragment or anchor
   needed by lowering
4. header-content diff still matches when replaying onto a fresh document whose
   `headerId` differs from the captured fixture

Commit value:

1. separates transport cleanup from semantic algorithms
2. proves the semantic edit layer is rich enough for lowering
3. prevents shared-story replay from collapsing back into transport-ID hacks

### Task 1B: Encode protected versus consumable structural separators

Deliverable:

1. classify story-final sentinels, paragraph separators, and
   structure-protecting separators explicitly in `ir.py`
2. encode which separators are always protected versus consumable by explicit
   paragraph merge/delete edits
3. expose this classification to `layout.py` and `lower.py`

Tests:

1. middle paragraph separator is consumable by structural paragraph delete
2. separator before table is protected
3. separator before TOC is protected
4. separator before section break is protected

Commit value:

1. replaces a major historical off-by-one/delete-range bug class with an
   explicit model boundary

### Task 2: Implement parser for body-only paragraphs

Deliverable:

1. parse Docs `Document` into `DocumentIR`
2. support:
   1. tabs
   2. body as a single-section story
   3. plain paragraphs
3. strip paragraph-final newline into `eop`
4. strip story-final newline into `eos`

Tests:

1. identical one-paragraph docs -> `[]`
2. append paragraph -> exact `insertText`
3. delete paragraph via structural boundary delete -> exact `deleteContentRange`
4. replace paragraph text -> exact in-paragraph text edit sequence

Commit value:

1. proves that newline sentinels can be removed from semantic content
2. gets the first real end-to-end request generation working

### Task 2A: Canonicalize transport variance before diff

Deliverable:

1. normalize equivalent text-run segmentations into one inline representation
2. normalize soft line break encodings used by the raw API
3. normalize missing-versus-synthetic trailing paragraphs into one story-end
   model
4. normalize API-defaulted style fields and numeric precision that should not
   trigger semantic diffs

Tests:

1. embedded-newline run splitting does not produce a diff
2. vertical-tab soft break normalizes to the chosen semantic form
3. missing trailing paragraph in raw transport does not cause a spurious append
4. table-cell color float precision drift does not produce a style update

Commit value:

1. addresses the recurring spurious-diff class at the parser boundary instead
   of in verifier hacks

### Task 3: Introduce legal points and layout state for body paragraphs

Deliverable:

1. implement `LegalPoint`
2. implement `LayoutState` for body paragraph interiors and boundaries
3. forbid raw index construction outside `layout.py`

Tests:

1. insertion before first paragraph
2. insertion after last paragraph
3. delete middle paragraph via boundary delete without touching final container
   newline
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

### Task 3B: Make `LayoutState` a transport shadow state

Deliverable:

1. evolve `LayoutState` from static point resolution into a stateful shadow of
   transport layout
2. teach it to account for request side effects such as:
   1. `insertTable` separator displacement
   2. paragraph merges from deletes
   3. leading-tab removal during bullet creation
3. forbid request emitters from re-deriving positions outside this state

Tests:

1. paragraph after inserted table receives styles at the correct position
2. consecutive tables remain index-stable
3. list creation with leading tabs updates subsequent positions correctly

Commit value:

1. addresses the recurring off-by-one regression class at the architectural
   level rather than per-feature patches

### Task 3C: Enforce protected-boundary delete legality

Deliverable:

1. teach `LayoutState` and lowering to distinguish protected separators from
   consumable paragraph separators
2. lower paragraph deletes/merges only through explicit structural edit paths
3. reject delete plans that would isolate the separator before a table, TOC, or
   section break

Tests:

1. delete middle paragraph merges surrounding paragraphs legally
2. delete paragraph before table preserves the protecting separator
3. edit near TOC does not insert into or delete through the TOC boundary
4. replace paragraphs before a section break preserves section topology

Commit value:

1. turns a long history of delete-range special cases into one legality layer

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

1. parse paragraph semantic role plus explicit text/paragraph styles into IR
2. implement effective-style resolver
3. diff on semantic role plus effective style while lowering only explicit
   deltas

Tests:

1. inherited bold vs explicit bold compare correctly
2. clearing a style to inherit from parent emits the correct field mask
3. span formatting next to differently styled text does not bleed
4. heading-to-normal change still diffs even if effective formatting matches

Commit value:

1. closes the main architectural hole around formatting bleed and false
   equality from role erasure

### Task 5B: Implement anchored annotation diff and lowering

Deliverable:

1. parse named ranges into anchored annotation IR
2. diff annotations independently of block content
3. lower create/delete/update of supported named-range annotations from anchor
   points resolved by `LayoutState`

Tests:

1. annotation-only diff emits named-range requests
2. content edit plus annotation shift lowers against post-edit anchor positions
3. docs differing only by server-generated named-range IDs compare equal

Commit value:

1. preserves semantic metadata currently relied on by markdown special elements

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

### Task 6A: Implement footnote reference diff and dependent footnote creation

Deliverable:

1. treat `FootnoteRefIR` as an id-producing inline edit
2. lower footnote insertion via `CreateFootnoteRequest`
3. reconcile created footnote containers in a dependent batch
4. handle footnote deletion through reference deletion semantics

Tests:

1. insert footnote reference in body -> exact two-layer batch plan
2. populate created footnote content in dependent batch
3. reject footnote insertion in header/footer/footnote

Commit value:

1. closes a long-standing unsupported inline producer path cleanly

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
3. insert table as first body block in the first section

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

1. exact-first row alignment with similarity fallback for mixed structural +
   content cases
2. exact-first column alignment with similarity fallback for mixed structural +
   content cases
3. row/column insert/delete lowering
4. cell style lowering
5. deterministic table request ordering

Tests:

1. add row
2. delete row
3. add column
4. delete column
5. change table cell style only
6. replay end-row/end-column operations from a fresh live 2x2 fixture
7. replay middle-row/middle-column operations from fresh live fixtures
8. replay one mixed "matched cell edit + row insert" fixture and assert content
   edit lowers before the structural request

Commit value:

1. completes supported table editing
2. proves that table structural edits can be lowered from table-relative
   coordinates rather than ad hoc body indices
3. proves the alignment layer can keep matched cell edits alive across a
   structural row/column shift

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
7. merge/unmerge replay ignores covered-cell paragraph-style transport noise
8. row insert directly below a merged region replays without invalidating merge
   topology
9. insert a middle row with inserted cell content and replay live
10. insert a middle column with inserted cell content and replay live
11. replay a simple combined row+column structural edit in one unmerged table
12. explicit unsupported error for column structural edit through an existing
    horizontal merged region

Commit value:

1. matches and exceeds the current reconciler's effective table support surface
2. forces canonicalization to own merge/unmerge transport artifacts explicitly
3. makes the current unsupported table boundary explicit and testable instead of
   leaving it as latent mis-lowering risk

### Task 14: Parse sections, style environment, and the shared header/footer story graph

Deliverable:

1. parse body section partition
2. parse section styles
3. parse tab style environment (`documentStyle`, `namedStyles`, lists)
4. represent typed header/footer slot attachments explicitly
5. represent shared header/footer stories explicitly
6. parse tab hierarchy (`parentTabId`, child tabs)

Tests:

1. single-section doc with default header
2. multi-section doc with distinct typed slot attachments
3. two sections sharing same header story
4. first-page/even-page slot parsing is preserved
5. nested tab tree parses with stable parent/child relationships

Commit value:

1. replaces top-level header/footer hacks with explicit graph structure
2. prevents accidental flattening of tab topology

### Task 15: Lower header/footer creation, attachment, and story content edits

Deliverable:

1. create shared header/footer stories
2. attach them to sections using `CreateHeaderRequest` /
   `CreateFooterRequest.sectionBreakLocation` when creating new scoped stories
3. lower content edits against the shared story
4. support multi-batch deferred IDs
5. support typed slots (`DEFAULT`, `FIRST_PAGE`, `EVEN_PAGE`)
6. enforce an explicit transport capability matrix for attachment operations
7. use `UpdateSectionStyleRequest` only for actual section style updates, not
   header/footer retargeting; live replay showed `defaultHeaderId` /
   `defaultFooterId` updates are rejected by Docs

Tests:

1. create header in single-section doc
2. modify existing header content
3. split a shared/default header into a new section-scoped header
4. create footer and populate in dependent batch
5. first-page or even-page attachment lowers distinctly from default
6. new tab with a new header/footer in an existing multi-tab document yields an
   explicit unsupported error, not a best-effort request
7. transport-broken create path yields explicit unsupported error, not a
   best-effort request

Commit value:

1. completes shared-story support

### Task 16: Implement tab diff and tab creation

Deliverable:

1. tab property diff
2. tab creation/deletion
3. parent/child tab relationship preservation
4. dependent content population after tab creation

Tests:

1. rename tab only
2. add tab with body content
3. add tab with body plus unsupported header/footer create path -> explicit
   error
4. add tab with body content plus deferred response placeholder resolution
5. add tab with body content plus anchored annotations
6. add child tab under parent tab
7. create tab + create table + populate cells in one logical cycle
8. create tab + nested table creation inside a table cell with one more nested
   level
9. create tab + create footnote + populate footnote + create named range over
   post-footnote body text in one logical cycle

Commit value:

1. completes document-level topology support

### Task 17: Add revision-aware batching and public API

Deliverable:

1. wire `requiredRevisionId`
2. advance revision IDs between executed dependency layers using the previous
   response's `writeControl.requiredRevisionId`
3. finalize `reconcile_v2.reconcile`
4. expose stable public API without replacing `extradoc.reconcile`

Tests:

1. all prior contract tests run through public entrypoint
2. batch ordering test with deferred IDs
3. multi-batch execution uses returned revision IDs rather than reusing the
   base revision

Commit value:

1. makes the module usable by callers

### Task 18: Replace verifier with semantic IR comparator

Deliverable:

1. implement `parse(actual_transport) -> actual_ir`
2. implement semantic equality for IR
3. remove list-identity erasure from `reconcile_v2` tests
4. compare supported sidecar resource catalogs explicitly

Tests:

1. docs differing only by transport `listId` but same semantic list -> equal
2. docs with split vs merged list runs -> not equal
3. docs with different section attachments -> not equal
4. docs with different typed header/footer slot attachments -> not equal
5. docs with different named-range anchors -> not equal
6. docs with different merge topology -> not equal
7. docs with different semantic role but same current effective formatting ->
   not equal
8. docs with different supported object catalogs -> not equal

Commit value:

1. makes test semantics match product semantics

### Task 19: Migration gate and shadow-mode coverage

Deliverable:

1. optional harness that runs both old and new reconciler on selected fixtures
2. record old/new request sequences for review
3. include raw-transport fixtures captured from real pulls where mock reindexing
   historically diverged
4. no caller migration yet

Tests:

1. selected regression fixtures produce valid `reconcile_v2` plans
2. known old bugs are covered by exact-plan tests
3. known transport-layout bugs are covered by semantic convergence tests

Commit value:

1. creates a safe adoption path without replacing existing behavior

### Task 20: Caller Cutover And Legacy Retirement

Deliverable:

1. route `DocsClient.diff()` / `push()` through a reconciler adapter that can
   execute either legacy reconcile or `reconcile_v2`
2. select reconciler version via `EXTRADOC_RECONCILER`
3. keep `pull` / `pull-md` unchanged, because the cutover is push-side only
4. ensure `diff`, `push`, and `push-md` work with either reconciler version
5. add shadow-mode tooling or operational guidance to compare legacy and v2
   plans on the same pulled folder during the fallback period
6. make `v2` the default active reconciler once markdown/XML workflow parity is
   established and the remaining unsupported boundaries are either implemented
   or documented as true transport limits
7. preserve markdown-authored structure on inserted paragraph slices by carrying
   paragraph role plus inline span styles through semantic edits and lowering
8. support mixed-section slice edits where a list block is inserted or deleted
   beside existing paragraph content, instead of silently dropping the change
9. lower same-anchor mixed body inserts as one grouped block-sequence operation
   so bullet/style ranges are computed against final coordinates rather than an
   intermediate shifted state
   Rule:
   compute those bullet/style ranges from the actual inserted positions while
   walking backward, following the `v1` reconciler discipline, rather than from
   the desired document's forward idealized indices
   For table-backed mixed inserts, derive those final coordinates from a
   shadow-applied structural document, not from heuristic table-size math.
10. treat unchanged read-only body blocks as immutable anchors and diff the
    editable spans around them independently; insertion edits near those anchors
    must preserve the raw body anchor needed for lowering
11. remove the legacy reconciler path only after:
   1. markdown workflow parity is established
   2. XML workflow parity is established
   3. the feature matrix is explicit for any residual transport-broken cases

Tests:

1. `DocsClient.diff()` returns legacy plans when `EXTRADOC_RECONCILER=v1`
2. `DocsClient.diff()` returns `reconcile_v2` plans by default
3. `DocsClient.diff()` returns legacy plans when `EXTRADOC_RECONCILER=v1`
4. `DocsClient.push()` executes legacy batches through legacy deferred-ID
   resolution
5. `DocsClient.push()` executes v2 batches through the v2 revision-aware
   executor
6. pulled markdown folder edits can be diffed under both versions
7. CLI help/docs mention that `v2` is default and `v1` remains available as a
   fallback during the migration period
8. `pull-md` -> edit inserted heading/link markdown -> `push-md` -> `pull-md`
   preserves heading markers and inline links
9. `pull-md` -> insert list beside existing paragraph content -> `push-md`
   produces deterministic list creation requests under `v2`
10. `pull-md` on an empty doc -> insert heading + paragraph + list + code block
    -> `push-md` -> `pull-md` round-trips without style or bullet drift
11. unchanged TOC/read-only body blocks can shift as anchors while nearby table
    delete/paragraph insert edits still lower against the correct raw body
    boundary

Commit value:

1. turns `reconcile_v2` from an isolated engine into the real production
   migration target

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
2. transport canonicalization
3. protected-boundary legality
4. page breaks
5. lists
6. exact-plan contract tests

That milestone already covers the major newline and list-attachment pain points
without requiring tables or headers to be complete.

Repair-path rule learned from broken live docs:

1. capture a durable `(base.json, desired.json, expected.lowered.json)` fixture
   whenever a malformed live doc exposes a new reconciler failure
2. grouped same-anchor body inserts must be lowered in reverse execution order
   against a shadow document
3. those grouped inserts must resolve their anchor from the canonical body
   layout by default, and only use the raw body anchor when the target is a
   read-only transport block such as TOC/opaque content
4. reverse ordering alone is not enough for table-backed body content; once any
   prior request has been emitted, later body deletes/inserts must resolve
   their transport indices from the evolving shadow document, not from a frozen
   base layout
5. `extradoc:*` named ranges attached to special markdown tables are semantic
   metadata, not transport cleanup work; when the owning content is deleted,
   lowering should not emit a separate `deleteNamedRange` request unless the
   semantic annotation itself is being changed independently
6. dense special-table rewrites may require iterative content batching even
   when the semantic diff is a single unmatched body slice; plan batches
   against an evolving shadow document and apply annotation edits only after
   the content batches converge
7. every live repair or convergence probe must begin from a fresh `pull-md`
   of the target doc. Reusing a previously pulled folder after any successful
   probe push can create false failures that are really stale-base mismatches,
   not reconciler bugs
8. markdown workflow uses two distinct base documents:
   a. a semantic base derived from the raw doc after markdown-only
      normalization for diffing
   b. the untouched raw transport base for iterative batch planning and shadow
      execution
   Reusing the normalized semantic base as the transport shadow can produce
   impossible post-batch indices around special tables and invalid delete
   ranges, even when the semantic edit plan is correct
