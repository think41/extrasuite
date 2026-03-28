# Reconciler Semantic IR Design

## Objective

Given `base: Document` and `desired: Document`, compute a sequence of
`BatchUpdateDocumentRequest` values such that, under
`writeControl.requiredRevisionId`, applying the sequence to `base` converges to
`desired` without generating structurally invalid Google Docs requests.

The design optimizes for:

1. Structural correctness.
2. Deterministic convergence.
3. Explicit unsupported-mode rejection instead of heuristic repair.
4. Uniform recursion across body, headers, footers, footnotes, and table cells.

This document is intentionally written from first principles. It does not
preserve current reconciler structure.

## Problem Statement

The input and output contract is:

1. Fetch a Google Doc revision and deserialize it as `base: Document`.
2. Construct `desired: Document`.
3. Compute `plan = reconcile(base, desired)`.
4. Execute `plan` as sequential `batchUpdate` calls.
5. The resulting Google Doc must be semantically equal to `desired`.

The core architectural challenge is that Google Docs does not expose an edit API
over a stable semantic tree. It exposes a request algebra over UTF-16 indices,
segments, tabs, section break locations, and structural side effects.

Therefore the reconciler must not diff transport JSON directly. It must:

1. Parse transport JSON into a canonical semantic intermediate representation.
2. Compute semantic edits over that representation.
3. Lower semantic edits into legality-preserving Docs API requests.

If those three concerns are fused, transport quirks leak upward and appear as
ad hoc special cases:

1. "cannot delete final newline"
2. "cannot insert at table start"
3. "list continuation attaches incorrectly"
4. "headers/footers are shared in some scopes and not in others"

## API Constraints

The design assumes the following Google Docs API facts.

1. Indices are measured in UTF-16 code units.
2. `InsertTextRequest` and `InsertPageBreakRequest` must target positions inside
   an existing paragraph; they cannot target a table start marker.
3. `InsertTableRequest` inserts a newline before the table; the table begins at
   `location.index + 1`.
4. `DeleteContentRangeRequest` must never:
   1. delete the final newline of a `Body`, `Header`, `Footer`, `Footnote`,
      `TableCell`, or `TableOfContents`;
   2. delete only the newline immediately preceding a `Table`,
      `TableOfContents`, or `SectionBreak`;
   3. cut across structural boundary markers.
5. `CreateParagraphBulletsRequest` operates on existing paragraphs. If the
   preceding paragraph is in a compatible list, inserted paragraphs may join
   that list.
6. `CreateHeaderRequest` and `CreateFooterRequest` may be document-scoped or
   section-scoped via `sectionBreakLocation`.
7. `batchUpdate` is sequential and revision-sensitive. Exact convergence
   requires `WriteControl.requiredRevisionId`.

These constraints are not edge cases. They define the legal edit surface.

## Design Principles

1. Semantic structure must be modeled independently of transport indices.
2. Illegal edits must be unrepresentable or rejected before lowering.
3. Terminal newlines must be modeled as structural sentinels, not user text.
4. Lists must be first-class structure, not paragraph decoration.
5. Table cells must use the same recursive content model as body/header/footer.
6. Shared header/footer semantics must be explicit in the IR.
7. All raw indices must be produced by a dedicated layout/lowering phase.
8. Effective style and explicit style must be modeled separately.
9. Request generation must be deterministic.

## Canonical Semantic IR

```text
DocumentIR
  revision_id: str
  tabs: list[TabIR]

TabIR
  id: TabId
  parent_tab_id: TabId | None
  title: str
  index: int
  icon_emoji: str | None
  body: ContainerIR(kind=BODY)
  sections: list[SectionIR]
  segment_catalog: SegmentCatalogIR
  child_tabs: list[TabIR]

SectionIR
  id: SectionId
  start_break: SectionBreakIR
  style: SectionStyleIR
  header_ref: SegmentRef | None
  footer_ref: SegmentRef | None

SegmentCatalogIR
  headers: dict[SegmentRef, ContainerIR(kind=HEADER)]
  footers: dict[SegmentRef, ContainerIR(kind=FOOTER)]
  footnotes: dict[SegmentRef, ContainerIR(kind=FOOTNOTE)]

ContainerIR
  id: ContainerId
  kind: BODY | HEADER | FOOTER | FOOTNOTE | TABLE_CELL
  capabilities: CapabilitySet
  blocks: list[BlockIR]
  eos: EndOfContainerSentinel

BlockIR =
    ParagraphIR
  | ListIR
  | TableIR
  | PageBreakIR
  | SectionBreakIR
  | TocIR
  | OpaqueBlockIR

ParagraphIR
  explicit_style: ParagraphStyleIR
  inlines: list[InlineIR]
  eop: EndOfParagraphSentinel

ListIR
  spec: ListSpecIR
  items: list[ListItemIR]

ListItemIR
  level: int
  paragraph: ParagraphIR

TableIR
  style: TableStyleIR
  pinned_header_rows: int
  column_properties: list[TableColumnPropertiesIR]
  merge_regions: list[MergeRegionIR]
  rows: list[RowIR]

RowIR
  style: TableRowStyleIR
  cells: list[CellIR]

CellIR
  style: TableCellStyleIR
  row_span: int
  column_span: int
  merge_head: CellCoord | None
  content: ContainerIR(kind=TABLE_CELL)

InlineIR =
    TextSpanIR(text, explicit_text_style)
  | FootnoteRefIR(ref)
  | InlineObjectRefIR(ref)
  | AutoTextIR(kind, payload)
  | OpaqueInlineIR
```

## Critical Modeling Decisions

### 1. End-of-container newline is structural

Every Google Docs container has a terminal newline requirement. That newline is
not modeled as text. It is modeled as `ContainerIR.eos`.

Consequences:

1. Semantic diff can never "delete the last newline".
2. Any attempt to remove all visible content from a container still leaves a
   valid empty container.
3. The lowering phase owns emission of legal delete ranges around `eos`.

This directly eliminates the largest current whack-a-mole class.

### 2. End-of-paragraph newline is structural

Each `ParagraphIR` owns an implicit `eop`. Text spans exclude it.

Consequences:

1. Text diff is independent of paragraph termination mechanics.
2. Paragraph deletion and paragraph merge are structural edits, not string edits.
3. Lowering can protect `eop` when required by Docs request legality.

### 3. List is a first-class block

Lists are represented as `ListIR`, not as `Paragraph.bullet`.

Semantic list identity is:

```text
maximal contiguous run of list items
with identical canonical ListSpecIR
and no intervening non-list block
```

Server `listId` is transport identity, not semantic identity.

Consequences:

1. "attach to existing list" becomes an explicit list edit.
2. Tests can verify list continuity semantically.
3. Reconcile no longer relies on transport `listId` preservation.

### 4. Table cell is a container

`TableCell` content is represented by `ContainerIR(kind=TABLE_CELL)`.

Consequences:

1. Body/header/footer/footnote/table-cell all recurse through the same
   algorithm.
2. Capability checks become uniform.
3. Page-break legality in cells becomes a simple capability failure instead of a
   `segment_id is None` accident.

### 5. Section attachments are explicit edges

Header/footer semantics are represented in `SectionIR.header_ref` and
`SectionIR.footer_ref`.

Consequences:

1. Shared segment semantics are part of the model.
2. Default header/footer reuse is explicit.
3. Section-scoped and document-scoped behavior are represented cleanly.

## Capability Model

```text
BODY
  text: yes
  table: yes
  page_break: yes
  section_break: yes

HEADER
  text: yes
  table: yes
  page_break: no
  section_break: no

FOOTER
  text: yes
  table: yes
  page_break: no
  section_break: no

FOOTNOTE
  text: yes
  table: no
  page_break: no
  section_break: no

TABLE_CELL
  text: yes
  table: no
  page_break: no
  section_break: no
```

Legality is always checked against `ContainerIR.capabilities`, never inferred
from transport fields.

## Canonicalization

The parser converts `Document` transport JSON into canonical `DocumentIR`.

### Canonicalization rules

1. Remove paragraph-final newline from text runs and store it as `eop`.
2. Remove container-final newline from visible content and store it as `eos`.
3. Lift pure page-break paragraphs into `PageBreakIR`.
4. Lift contiguous bullet paragraphs into `ListIR`.
5. Derive `ListSpecIR` from effective list properties, not raw `listId`.
6. Represent tab hierarchy explicitly rather than flattening tabs.
7. Represent sections explicitly and attach header/footer references to them.
8. Preserve shared segment references if multiple sections resolve to the same
   header/footer object.
9. Represent TOC and other read-only structures as `read_only` blocks.

### Canonical list spec

`ListSpecIR` contains only semantic properties:

```text
ListSpecIR
  kind: BULLETED | NUMBERED | CHECKBOX
  levels: list[ListLevelSpecIR]

ListLevelSpecIR
  glyph_kind
  glyph_symbol
  start_number
  indent_start
  indent_first_line
  text_style
```

Transport `listId` is excluded.

## Style Semantics

Google Docs style behavior is inheritance-based and range-based, not purely
run-local.

The IR therefore distinguishes:

1. `explicit_style`: properties materially stored on the node/span
2. `effective_style`: properties observed after inheritance from enclosing
   paragraph, named style, list context, and editor defaults

Rules:

1. parse transport into explicit styles only
2. compute effective styles through a style resolver
3. perform semantic comparison on effective style
4. emit only explicit deltas during lowering

Consequences:

1. removing bold from a span that inherits bold from a paragraph is modeled
   correctly
2. span-level formatting near paragraph boundaries does not accidentally bleed
   through inherited defaults
3. list bullets affected by full-paragraph text-style updates are handled
   intentionally rather than as an API surprise

## List Transport Semantics

Google Docs list transport semantics are not the same as list semantics.

Transport facts:

1. `CreateParagraphBulletsRequest` determines nesting from leading tabs
2. the request removes those leading tabs
3. `DeleteParagraphBulletsRequest` preserves visual indentation by adding
   indentation back
4. index positions may shift as part of bullet creation

Semantic rule:

1. leading tabs used solely for list nesting are transport artifacts, not user
   text, once parsed into `ListIR`

Lowering rule:

1. when creating or releveling list items, lowering may need to synthesize
   leading tabs as a temporary transport encoding
2. those tab insertions/removals must be accounted for in `LayoutState`
3. list continuation and releveling are planned in semantic list space, not in
   paragraph text space

Consequences:

1. list identity is not coupled to transport text prefixes
2. index shifts caused by bullet creation are planned, not incidental
3. releveling can be implemented without corrupting surrounding text ranges

## Diff Phase

The diff phase computes semantic edits over the IR. It does not emit requests or
indices.

### Edit program

```text
Edit =
    UpdateTabProperties
  | EditContainer(container_id, ContainerEditProgram)
  | UpdateSectionAttachment(section_id, header_ref/footer_ref changes)
  | CreateSharedSegment
  | DeleteSharedSegment
  | UnsupportedEdit(reason)
```

### Container diff

`diff_container(base, desired)` uses typed weighted sequence alignment over
`blocks`.

Two blocks may match only if they have compatible types:

1. paragraph <-> paragraph
2. list <-> list
3. table <-> table
4. pagebreak <-> pagebreak
5. sectionbreak <-> sectionbreak
6. toc <-> toc
7. opaque <-> exact-same opaque payload

This replaces transport-text LCS and avoids destructive block replacement for
small text edits.

### Paragraph diff

Paragraphs remain matched even when text changes.

Algorithm:

1. Normalize inline stream into grapheme-cluster segments.
2. Diff text by grapheme clusters.
3. Diff paragraph style independently.
4. Diff inline styles independently.
5. Treat footnote references and inline object refs as atomic inline nodes.

UTF-16 conversion happens only during lowering.

### List diff

`diff_list(base, desired)`:

1. Diff `ListSpecIR`.
2. Align items by weighted similarity on paragraph content and style.
3. Recurse into item paragraphs.
4. Support insert/delete/relevel/move-within-list.

List continuity is now explicit. Appending a single list item to an existing
list is a list-item insertion, not a paragraph insertion plus a hopeful bullet
request.

### Table diff

`diff_table(base, desired)`:

1. Diff table style.
2. Diff pinned header row count.
3. Diff column properties.
4. Diff merge topology.
5. Align rows by weighted row similarity.
6. Align columns by weighted column similarity.
7. Emit structural row/column edits semantically.
8. Recurse into each cell container.
9. Diff cell style independently.

Tables are recursive structural containers, not string fingerprints.

### Full table support

The reconciler must support the current exposed table feature surface rather than
leaving advanced features unsupported.

Supported semantic table features:

1. table insertion and deletion
2. row insertion and deletion
3. column insertion and deletion
4. cell content diff
5. table cell style diff
6. table row style diff
7. table column property diff
8. pinned header row diff
9. merge and unmerge of rectangular cell regions

Design rule:

1. table topology is part of semantic table state, not a transport-side
   incidental detail

Lowering rule:

1. merge topology changes are lowered using explicit merge/unmerge requests
2. structural row/column edits must preserve merge invariants
3. property updates must be emitted with deterministic field masks and stable
   request ordering

### Section and shared segment diff

Body content diff and section attachment diff are separate.

1. Diff body blocks including `SectionBreakIR`.
2. Diff section styles.
3. Diff header/footer attachment graph.
4. Diff referenced header/footer contents exactly once per shared segment.

This eliminates the need for document-wide "find first default header/footer"
stateful hacks.

## Lowering Phase

Lowering converts semantic edits into legal Docs API requests.

Lowering is the only phase allowed to know:

1. UTF-16 request coordinates
2. paragraph carrier positions
3. table start locations
4. section break locations
5. request batching and deferred ID dependencies
6. revision control

### Layout state

`LayoutState` is maintained per `(tab_id, segment_id or container_ref)` and
tracks legal insertion/deletion coordinates.

It resolves:

1. paragraph interior positions
2. paragraph end positions
3. container end positions
4. table start positions
5. section break attachment locations

No code outside the lowering layer may construct raw Docs indices.

### Legal point system

```text
LegalPoint =
    ParagraphInterior(paragraph_id, utf16_offset)
  | ParagraphBoundaryBefore(block_id)
  | ParagraphBoundaryAfter(block_id)
  | EndOfContainer(container_id)
  | TableStart(table_id)
  | SectionBreakLocation(section_id)
```

`LegalPoint` resolves to Docs coordinates only through `LayoutState`.

### Lowering invariants

1. No delete range may include `eop` or `eos`.
2. No text insertion may target a table start.
3. No page break may be lowered outside `BODY`.
4. No table may be lowered into `FOOTNOTE` or `TABLE_CELL`.
5. Every request using IDs created earlier is topologically ordered after the
   producer request.
6. Within a coordinate partition, mutations are emitted in descending resolved
   position order unless a request dependency requires otherwise.

## Range legality

Delete legality is not sufficient. Formatting and bullet ranges must also obey
Docs boundary rules.

Rules:

1. delete ranges must exclude `eop` / `eos`
2. text-style and paragraph-style ranges must never extend past the final legal
   content position of the target container
3. bullet ranges must never terminate at or beyond the terminal container
   sentinel
4. when the Docs API extends a style range to include adjacent newlines, the
   planner must cap the requested range so that the effective applied range
   remains legal
5. if a full-paragraph text-style update would also style a list bullet, that
   side effect must be treated as part of planning rather than as verification
   noise

Consequences:

1. end-of-segment formatting requests remain valid
2. bullet creation at segment end cannot regress into the historical
   `endIndex == segment_end` bug
3. style bleed across spans and paragraph boundaries is constrained by design

## Transport-Lowering Rules

### Paragraph/text updates

For matched paragraphs:

1. lower text edit script to `InsertText` + `DeleteContentRange` inside the
   paragraph interior
2. lower paragraph style updates via `UpdateParagraphStyle`
3. lower inline style updates via `UpdateTextStyle`

Because `eop` is structural, the planner never deletes the last paragraph
newline.

### Block insertion

Some Docs requests require insertion inside an existing paragraph even when the
semantic edit is "insert block between blocks". Lowering therefore uses a
carrier paragraph rule.

Carrier rule:

1. find a legal paragraph carrier adjacent to the insertion boundary
2. insert text/list/table/pagebreak relative to that carrier
3. absorb transport artifacts into lowering bookkeeping, not into semantic IR

### Table insertion

`InsertTableRequest` always introduces a pre-table newline. This is treated as a
transport artifact owned by lowering.

The semantic IR never models:

1. "empty paragraph before first table"
2. "empty paragraph displaced after inserted table"

Those are not semantic content. They are implementation details of
`InsertTableRequest`.

### End-of-segment insertion

Lowering must model `EndOfSegmentLocation` as a first-class target.

Rules:

1. `EndOfSegmentLocation` resolves to the position immediately before the
   terminal container sentinel.
2. It is valid for body, header, footer, and footnote operations whose Docs
   request form supports end-of-segment insertion.
3. Lowering should prefer `endOfSegmentLocation` over synthetic carrier
   insertion when the API exposes both forms.

Consequences:

1. append-at-end is a first-class lowering operation
2. segment-end insertion is independent of paragraph-carrier heuristics
3. terminal newline preservation remains explicit

### Deletion

All deletes are lowered from semantic spans that exclude `eop` and `eos`.

The planner computes the maximal legal delete range under Docs constraints:

1. never delete final container sentinel
2. never delete only the newline protecting a table or section break
3. if a semantic delete would violate these rules, rewrite as a legal
   combination of:
   1. structural delete
   2. sibling merge
   3. block replacement

### Lists

Because `ListIR` is first-class, lowering has explicit choices:

1. extend an adjacent compatible list
2. create a new list run
3. split a list
4. merge two list runs

Lowering no longer guesses based on paragraph-local bullet fields alone.

### Headers and footers

Section attachment edits are lowered using:

1. `CreateHeaderRequest` / `CreateFooterRequest` with
   `sectionBreakLocation` when a new section-scoped segment must be created
2. content edits against the referenced segment
3. `UpdateSectionStyleRequest` only when actual section style fields must be
   updated

Shared segments are created once and referenced by the section graph in the
semantic model.

## Determinism

Exact-plan testing requires deterministic request generation.

The reconciler therefore must define:

1. stable tie-breaking for sequence alignment
2. stable ordering of matched/inserted/deleted nodes
3. stable request ordering within a batch
4. stable dependency batching
5. stable field-mask ordering
6. stable normalization of semantically-equivalent style deltas

Determinism is a correctness requirement for `reconcile_v2`, not merely a test
convenience.

## Batching and ID Dependencies

Use sequential batches only for ID-producing operations.

Batch layer 0:

1. `AddDocumentTabRequest`
2. `CreateHeaderRequest`
3. `CreateFooterRequest`
4. `CreateFootnoteRequest`

Batch layer N+1:

1. requests that reference IDs created in batch N

All other operations stay in the earliest dependency-valid batch.

Every batch uses `WriteControl.requiredRevisionId`.

## Unsupported Operations

Reject, do not guess, when the desired semantic transform cannot be lowered
safely.

Examples:

1. mutation of read-only TOC contents
2. page breaks inside non-body containers
3. nested tables if Docs API does not represent them safely in target context
4. unsupported opaque block mutation
5. section attachment transforms lacking a legal section break target

Failure mode must be `UnsupportedEdit(reason)` at semantic phase or
`LoweringError(reason)` at lowering phase, never a best-effort invalid request.

## Correctness Guarantees

For all supported edits, under `requiredRevisionId == base.revisionId`, the
system guarantees:

1. every emitted request is structurally legal by construction
2. no request deletes a final newline sentinel
3. no page break is emitted in header/footer/footnote/table cell
4. no text insertion targets a table start
5. list continuity is explicit and testable
6. body/header/footer/footnote/table-cell recursion uses one algorithm with
   different capability sets
7. shared header/footer semantics are preserved through explicit section
   attachments
8. tab hierarchy is preserved rather than flattened away

## Test Contract

All reconciler tests should follow one contract:

1. `base Document`
2. `desired Document`
3. parse -> diff -> lower
4. execute requests
5. parse actual result back into `DocumentIR`
6. compare semantic IR equality

Raw transport JSON equality is not the oracle.

### Mandatory test classes

1. container-end edits in body/header/footer/footnote/table-cell
2. append/prepend/split/merge of list runs
3. paragraph text mutation without block replacement
4. mixed paragraph/table/pagebreak insertion around structural boundaries
5. section-scoped header/footer creation and reuse
6. recursive cell content edits
7. idempotence: `reconcile(x, x) == []`
8. convergence: after apply, reparsed actual IR equals desired IR

### Comparator rule

The verifier must compare semantic list runs and section attachments.

It must not ignore:

1. `lists`
2. list continuity
3. shared segment attachment graph

Transport-generated IDs may be canonicalized, but semantic identity must be
preserved.

## Migration: What To Reuse

The current code base contains useful transport utilities, but the current
reconciler architecture should not be preserved wholesale.

### Reuse as-is

1. `indexer.utf16_len`
2. Pydantic Docs API types in `api_types._generated`
3. `DeferredID` / deferred response resolution mechanics
4. request model validation via `Request` and `BatchUpdateDocumentRequest`
5. mock transport execution and reindexing infrastructure as a test harness

### Reuse after refactor

1. request builder helpers for:
   1. `insertText`
   2. `deleteContentRange`
   3. `updateTextStyle`
   4. `updateParagraphStyle`
   5. `insertTable`
   6. row/column operations
   7. header/footer create/delete
   8. tab create/delete/update
2. style diff machinery
3. UTF-16-aware text style range generation
4. table cell style diff machinery
5. named range request generation

These should move into a pure lowering library. They should not remain coupled
to structural alignment logic.

### Reuse conceptually, but reimplement

1. segment extraction
2. table row/column alignment ideas
3. request batching by dependency layer
4. verify-via-mock pattern

The ideas are sound. The current shape is too transport-coupled.

### Do not reuse architecturally

1. element-level LCS over raw transport fingerprints as the primary diff model
2. gap-slot processing as the main edit abstraction
3. treating bullet/list semantics as paragraph-local decoration
4. `segment_id is None` as a proxy for body semantics
5. newline-only synthetic paragraph compensation as a core strategy
6. hard-coded special cases for table insertion topology
7. document-global default header/footer scanning hacks
8. verifier normalization that erases semantic list structure

## Summary

The correct architecture is:

1. canonical recursive semantic IR with implicit structural sentinels
2. first-class lists and explicit section attachment graph
3. typed semantic diff independent of Docs transport coordinates
4. legality-preserving lowering phase that alone understands Docs request rules

This is the architecture that makes newline compensation unnecessary and turns
today's structural bugs into invalid states that the system cannot express.
