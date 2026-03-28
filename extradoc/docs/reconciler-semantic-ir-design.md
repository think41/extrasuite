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
6. `CreateHeaderRequest` and `CreateFooterRequest` are typed
   (`DEFAULT`, `FIRST_PAGE`, `EVEN_PAGE`) and may be document-scoped or
   section-scoped via `sectionBreakLocation`.
7. Most write requests default to the first tab when `tabId` is omitted.
   Correct lowering therefore requires explicit tab routing wherever the API
   surface permits it.
8. `batchUpdate` is sequential and revision-sensitive. Exact convergence
   requires `WriteControl.requiredRevisionId`.
9. When `requiredRevisionId` is used across multiple `batchUpdate` calls, each
   later batch must use the revision returned by the previous successful
   response, not the original base revision.
10. A documented request form is not automatically a usable transport capability
    in every context. If the only transport form that can realize a semantic
    edit is rejected by the Docs backend in that target context, lowering must
    reject the edit explicitly.

These constraints are not edge cases. They define the legal edit surface.

## Design Principles

1. Semantic structure must be modeled independently of transport indices.
2. Illegal edits must be unrepresentable or rejected before lowering.
3. Terminal newlines must be modeled as structural sentinels, not user text.
4. Lists must be first-class structure, not paragraph decoration.
5. Table cells must use the same recursive content model as body/header/footer.
6. Shared header/footer semantics must be explicit in the IR.
7. All raw indices must be produced by a dedicated layout/lowering phase.
8. Style environment and anchored annotations must be modeled explicitly.
9. Semantic role, effective style, and explicit style must be modeled
   separately.
10. Lowering must simulate transport side effects in a shadow layout state.
11. Transport canonicalization must be explicit and deterministic.
12. Semantic capability and transport capability must be modeled separately.
13. Request generation must be deterministic.

## Architectural Review

The proposal in this document is directionally correct, but after reviewing it
against the Google Docs transport model and the known historical bug classes,
four conceptual leaks still remain:

1. The body is still too flat. Modeling `SectionBreakIR` as an ordinary body
   block makes sections look like content instead of partitions over content.
   That keeps the mandatory opening section break, section topology, and
   attachment ownership in the same edit space as paragraphs and tables.
2. Shared content still has split identity. Body content, header/footer
   attachments, footnotes, and side catalogs are represented in different
   shapes, so the model still has to translate between "where content lives"
   and "how content is referenced".
3. Annotations and lowering use different coordinate systems. `AnchorPointIR`
   and `LegalPoint` are solving the same logical-position problem at different
   layers, which risks another class of index/anchor drift bugs.
4. Style comparison is still too rendering-centric. Effective style is
   necessary, but it is not sufficient semantic identity by itself. Paragraph
   role and style intent must survive comparison even when two paragraphs happen
   to render the same today.

The revised design below addresses those leaks directly.

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
  style_env: StyleEnvironmentIR
  body: BodyStoryIR
  resource_graph: ResourceGraphIR
  annotations: AnnotationCatalogIR
  child_tabs: list[TabIR]

BodyStoryIR
  id: StoryId
  kind: BODY
  sections: list[SectionIR]

SectionIR
  id: SectionId
  style: SectionStyleIR
  attachments: SectionAttachmentsIR
  blocks: list[BlockIR]
  eos: EndOfStorySentinel

SectionAttachmentsIR
  headers: dict[HeaderFooterSlotIR, StoryRef]
  footers: dict[HeaderFooterSlotIR, StoryRef]

StyleEnvironmentIR
  document_style: DocumentStyleIR
  named_styles: NamedStylesIR
  list_catalog: ListCatalogIR

ResourceGraphIR
  headers: dict[StoryRef, StoryIR(kind=HEADER)]
  footers: dict[StoryRef, StoryIR(kind=FOOTER)]
  footnotes: dict[StoryRef, StoryIR(kind=FOOTNOTE)]
  inline_objects: dict[ObjectRef, OpaqueObjectIR]
  positioned_objects: dict[ObjectRef, OpaqueObjectIR]

StoryIR
  id: StoryId
  kind: HEADER | FOOTER | FOOTNOTE | TABLE_CELL
  capabilities: CapabilitySet
  blocks: list[BlockIR]
  eos: EndOfStorySentinel

AnnotationCatalogIR
  named_ranges: dict[AnnotationName, list[AnchorRangeIR]]

AnchorRangeIR
  start: PositionIR
  end: PositionIR

PositionIR
  story_id: StoryId
  path: FlowPathIR

FlowPathIR
  section_index: int | None
  block_index: int
  node_path: tuple[int, ...]
  inline_path: InlinePath | None
  text_offset_utf16: int | None
  edge: BEFORE | AFTER | INTERIOR

BlockIR =
    ParagraphIR
  | ListIR
  | TableIR
  | PageBreakIR
  | TocIR
  | OpaqueBlockIR

ParagraphIR
  role: ParagraphRoleIR
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
  content: StoryIR(kind=TABLE_CELL)

InlineIR =
    TextSpanIR(text, explicit_text_style)
  | FootnoteRefIR(ref)
  | InlineObjectRefIR(ref)
  | AutoTextIR(kind, payload)
  | OpaqueInlineIR
```

## Critical Modeling Decisions

### 1. Body is a sectioned story, not a flat block list

Google Docs represents section breaks as structural elements, but semantically a
section is not "a block among other blocks". It is a partition of the body with
its own style and attachment state.

Consequences:

1. The mandatory opening section break is no longer modeled as an editable body
   block.
2. Body diff first aligns `SectionIR` partitions, then diffs blocks within each
   matched section.
3. Section topology and section-local attachment ownership stop competing with
   paragraph/table diff logic.

### 2. Shared and ID-bearing content lives in a story graph

Headers, footers, footnotes, and table-cell content are all stories. Some are
shared and externally referenced, some are owned by a parent node, but they all
have the same recursive content shape.

Consequences:

1. Header/footer attachment edges point to stories; they do not duplicate
   content.
2. Footnote references and header/footer attachments use the same identity model
   for dependent content.
3. The design stops translating between "segment semantics" and "container
   semantics" as separate worlds.
4. Shared stories must be matched through logical attachment edges or owned
   container position, not by transport `headerId` / `footerId` / `footnoteId`.
   Live replay against fresh Docs files proved that transport IDs are not
   stable semantic matching keys.

### 3. Logical positions are first-class and shared by annotations and lowering

`PositionIR` is the one semantic coordinate system. Anchored annotations, diff
edits, and lowering all start from the same story-local logical position model.

Consequences:

1. Annotation diff does not depend on a second anchor model.
2. Lowering derives `LegalPoint` from `PositionIR` rather than inventing a
   parallel coordinate scheme.
3. The position model can represent anchors inside nested block-local
   structures such as list items, not only top-level paragraphs.
4. Block splits, merges, and table insertions no longer require separate
   "annotation remap" logic.
5. One story-local layout resolver can serve body paragraphs, shared
   header/footer stories, table-cell stories, and anchored annotations.

### 3A. Story-local paragraph slice replacement is the right text primitive

The confidence sprint now has live fixture replays for:

1. plain paragraph text replacement
2. paragraph split via inserted paragraph boundary
3. table-cell text replacement
4. existing-header text replacement

The first four reduce cleanly to the same semantic operation:

```text
replace paragraph slice in story S
  at block range [i, j)
  with paragraph fragments P*
```

This is the elegant design direction. Body text, header text, and table-cell
text are not separate feature families. They are story-local text edits over
the same recursive model.

### 4. End-of-story and end-of-paragraph newlines are structural

Every story has a terminal newline requirement. That newline is not modeled as
text. It is modeled as `StoryIR.eos` or `SectionIR.eos`. Each paragraph owns an
implicit `eop`.

Consequences:

1. Semantic diff can never "delete the last newline".
2. Text diff is independent of paragraph termination mechanics.
3. Paragraph deletion and paragraph merge are structural edits, not string
   edits.

This directly eliminates the largest current whack-a-mole class.

### 5. List is a first-class block

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

### 6. Table cell is a story

`TableCell` content is represented by `StoryIR(kind=TABLE_CELL)`.

Consequences:

1. Body/header/footer/footnote/table-cell all recurse through the same
   algorithm.
2. Capability checks become uniform.
3. Page-break legality in cells becomes a simple capability failure instead of a
   `segment_id is None` accident.

### 7. Header/footer slots are typed attachment edges

Headers and footers are not singular edges. Google Docs distinguishes
`DEFAULT`, `FIRST_PAGE`, and `EVEN_PAGE` slots, with document-style flags that
activate them.

Consequences:

1. The IR can represent the real attachment graph instead of collapsing it.
2. First-page and even-page behavior is not lost during semantic comparison.
3. Lowering can reject only the transport paths that are unsupported, rather
   than rejecting all non-default header/footer edits.

### 8. Style semantics have three layers

Effective style depends on more than the paragraph or text run itself. It
depends on paragraph role, the tab's named styles, document style, and
list-level properties.

Consequences:

1. The IR can preserve paragraph role or semantic style intent even when two
   nodes happen to render identically.
2. Effective-style comparison has an explicit source of truth.
3. Raw-vs-derived style differences can be normalized semantically instead of
   with verifier hacks.

### 9. Anchored annotations are first-class semantic state

Per-tab named ranges are not incidental transport metadata in this project.
They carry semantics for markdown special elements and other higher-level
features.

Consequences:

1. Semantic equality can detect annotation-only changes.
2. Named ranges can be diffed using anchor points in semantic space instead of
   stale UTF-16 offsets.
3. Annotation lowering can be ordered after the content mutations it depends on.
4. The currently proven slice includes stable-content add/delete and
   story-local anchor moves coupled with paragraph-text edits, provided lowering
   stages content mutations first and recreates named ranges against the
   post-edit story layout.
5. Semantic annotation comparison cannot key on transport tab IDs. For matched
   body and table-cell stories, anchor identity must be relative to the logical
   story route, so replay on a fresh document with different generated tab IDs
   still converges.

### 10. Lowering uses a transport shadow state

Lowering does not merely resolve static coordinates. It simulates the transport
side effects of the requests it emits.

Consequences:

1. `insertTable`-introduced separators are accounted for deterministically.
2. bullet creation tab removal and paragraph merges are modeled in one place.
3. later requests in the same batch are resolved against the post-effect
   transport state, not against guessed arithmetic.
4. multi-batch execution is part of the design, not an outer-shell concern:
   `requiredRevisionId` handoff and response-derived setup IDs belong to the
   executor/harness layer.

### 11. Structural separators are typed, not uniformly protected

`eos` is always protected. `eop` is structural, but some paragraph separators
are consumable during an explicit paragraph merge/delete, while others are
protected because they guard a `Table`, `TableOfContents`, or `SectionBreak`.

Consequences:

1. paragraph deletion is modeled as structure, not as forbidden string surgery
2. "newline before table/TOC/section break" becomes a first-class boundary rule
3. legal paragraph merges can be expressed without reintroducing newline hacks

### 12. Transport canonicalization is a phase, not an accident

The parser must normalize transport representations that are semantically
equivalent but structurally different in raw JSON.

Consequences:

1. run-splitting differences do not force positional fallbacks
2. missing synthetic trailing paragraphs do not cause spurious adds
3. numeric/style default drift is normalized before diff
4. section-break carrier paragraphs are erased in canonical IR rather than
   leaking into semantic edits
5. a story that semantically starts with a table canonicalizes away the leading
   pre-table carrier paragraph that `insertTable` introduces
6. table-cell canonicalization is recursive: nested tables inherit the same
   carrier-paragraph cleanup rules as top-level tables
7. newly created footnote segments canonicalize away the transport-owned
   carrier space before the final newline, so footnote text diff does not treat
   that bootstrap artifact as semantic content

Canonicalization is therefore a dedicated pre-diff phase:

1. parse transport JSON into semantic IR
2. canonicalize transport-only carrier structure
3. diff canonical semantic IR

## Capability Model

```text
BODY
  text: yes
  table: yes
  page_break: yes
  section_break: topology-aware

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

Legality is always checked against story/container capabilities, never inferred
from transport fields.

Story/container capabilities describe semantic locality. They are not
an unconditional promise that every transport request shape is currently usable.

## Transport Capability Matrix

The reconciler distinguishes:

1. semantic capability: the edit is meaningful in the IR
2. transport capability: the Docs API can realize it in this target context

Rules:

1. section topology is parsed and preserved explicitly, but section-break
   insertion/deletion is unsupported until a dedicated legality-preserving
   lowering path exists
2. header/footer attachment edits are supported only where the transport layer
   exposes a working targetable request form for the relevant tab/section
3. if the only documented request shape is rejected by the backend in the
   target context, lowering returns `UnsupportedEdit` rather than guessing

## Canonicalization

The parser converts `Document` transport JSON into canonical `DocumentIR`.

### Canonicalization rules

1. Remove paragraph-final newline from text runs and store it as `eop`.
2. Remove story-final newline from visible content and store it as `eos`.
3. Lift pure page-break paragraphs into `PageBreakIR`.
4. Lift contiguous bullet paragraphs into `ListIR`.
5. Derive `ListSpecIR` from effective list properties, not raw `listId`.
6. Represent tab hierarchy explicitly rather than flattening tabs.
7. Represent the body as ordered `SectionIR` partitions rather than a flat block
   list containing section-break nodes.
8. Preserve typed header/footer slot attachments (`DEFAULT`, `FIRST_PAGE`,
   `EVEN_PAGE`) rather than collapsing them to a single ref.
9. Preserve shared story references if multiple sections resolve to the same
   header/footer object.
10. Parse per-tab style environment explicitly (`documentStyle`, `namedStyles`,
    lists).
11. Parse named ranges as anchored semantic annotations.
12. Represent TOC and other read-only structures as `read_only` blocks.
13. Canonicalize equivalent text-run segmentations into the same inline stream.
14. Normalize soft line break encodings and other transport-only text variants.
15. Normalize absent-versus-synthetic trailing paragraphs into the same
    story-end representation.
16. Normalize API-defaulted style fields and numeric precision before diff.

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

### Transport normalization rules

Canonicalization must also erase non-semantic transport variance:

1. embedded newline run splitting versus single-run storage
2. vertical-tab or equivalent in-paragraph soft-break encodings
3. missing but implied trailing empty paragraph representations
4. API-defaulted paragraph/table-cell style fields
5. float precision drift in color/style payloads

If base and desired are semantically equal after these normalizations,
`reconcile(base, desired)` must be `[]`.

## Style Semantics

Google Docs style behavior is inheritance-based and range-based, not purely
run-local.

The IR therefore distinguishes:

1. `semantic_role`: paragraph/list role that remains meaningful even if the
   current effective formatting matches something else
2. `explicit_style`: properties materially stored on the node/span
3. `effective_style`: properties observed after inheritance from paragraph
   role, named style, list context, and editor defaults

Rules:

1. parse transport into semantic role plus explicit styles
2. compute effective styles through a style resolver
3. resolve effective style against `TabIR.style_env`
4. perform semantic comparison on semantic role plus effective style
5. emit only explicit deltas during lowering

Consequences:

1. changing a heading to normal text still produces a semantic diff even if the
   rendered style currently matches
2. removing bold from a span that inherits bold from a paragraph is modeled
   correctly
3. span-level formatting near paragraph boundaries does not accidentally bleed
   through inherited defaults
4. list bullets affected by full-paragraph text-style updates are handled
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

## Anchored Annotation Semantics

Google Docs named ranges and similar anchored extras are semantic metadata over
document content, not part of the block tree itself.

Rules:

1. annotations are anchored to semantic positions, not stored as raw UTF-16
   offsets in the canonical IR
2. annotation diff happens after block/inline alignment, over anchor points in
   semantic space
3. lowering resolves annotation anchors only after content/layout state for the
   target batch is known

Consequences:

1. named-range-only edits are visible to semantic diff
2. markdown special-element annotations survive content edits without stale
   index arithmetic
3. annotation comparison no longer depends on server-generated IDs

## Diff Phase

The diff phase computes semantic edits over the IR. It does not emit requests or
indices.

### Edit program

```text
Edit =
    UpdateTabProperties
  | EditBody(tab_id, BodyEditProgram)
  | EditStory(story_id, StoryEditProgram)
  | EditSection(section_id, SectionEditProgram)
  | EditAnchoredAnnotations(tab_id, AnnotationEditProgram)
  | CreateResource(resource_kind, resource_ref)
  | DeleteResource(resource_kind, resource_ref)
  | UnsupportedEdit(reason)
```

### Story and section diff

`diff_body(base, desired)` first aligns `SectionIR` partitions. For matched
sections it then calls `diff_story_blocks(base_section.blocks, desired_section.blocks)`.
Non-body stories (`HEADER`, `FOOTER`, `FOOTNOTE`, `TABLE_CELL`) skip the
section layer and diff their block lists directly.

Two blocks may match only if they have compatible types:

1. paragraph <-> paragraph
2. list <-> list
3. table <-> table
4. pagebreak <-> pagebreak
5. toc <-> toc
6. opaque <-> exact-same opaque payload

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

### Inline producer edits

Some inline nodes introduce new server-assigned IDs and dependent containers.
`FootnoteRefIR` insertion is the key case.

Rule:

1. inserting a `FootnoteRefIR` is lowered as:
   1. create the inline producer at a legal body insertion point
   2. bind the returned ID to the referenced footnote container
   3. reconcile the footnote container in a dependent batch

Consequence:

1. footnote support fits the same semantic/lowering split as new tabs and new
   shared stories.

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
5. Align rows by exact match first, then weighted row similarity as a fallback
   when a structural row edit coexists with matched-row content edits.
6. Align columns by exact match first, then weighted column similarity under the
   same rule.
7. Emit structural row/column edits semantically.
8. Recurse into each matched cell story using the structural alignment map.
9. Diff cell style independently.

Tables are recursive structural containers, not string fingerprints.

Observed transport fact from live replay:

1. row/column structural edits lower cleanly from `tableStartLocation +
   (rowIndex, columnIndex)` and do not require document-global raw indices
2. merge/unmerge changes can leave transport-visible covered cells and
   paragraph-style noise behind; semantic diff must key on canonical merge
   topology and cell stories, not incidental covered-cell paragraph styles
3. when a matched cell edit shares a batch with a row/column insert or delete,
   the matched-cell edit must lower before the structural shift so base-story
   coordinates stay valid
4. fixture design matters: table fixtures must avoid semantically ambiguous
   duplicate empty columns or rows when the goal is to prove a specific
   structural coordinate choice
5. pinned header rows may surface semantically through leading
   `tableRowStyle.tableHeader = true` rows rather than an obvious table-level
   `pinnedHeaderRowsCount` field, so parse/canonicalization must derive the
   semantic count from row state
6. inserted-row and inserted-column content can be lowered without body-index
   arithmetic, but only if the semantic edit carries the inserted cell payload
   explicitly
7. some table transport shapes are still intentionally rejected in the spike:
   multiple row/column structural edits in one diff, and column structural
   edits through horizontally merged regions

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
4. covered cells produced by transport merge/unmerge are canonicalization
   artifacts, not semantic sibling cells
5. matched-cell content edits in rows/columns that will shift must be emitted
   before the row/column structural request
6. inserted-row/column text must lower from table-local anchors computed after
   the structural request, not from guessed document-global offsets
7. when the semantic model cannot distinguish a safe unique lowering plan,
   lowering must reject explicitly rather than synthesizing a best-effort table
   patch

### Section and shared story diff

Sections are first-class body partitions. Their boundaries are structural, but
their styles and attachment state are part of the semantic document model.

1. Diff body sections before diffing body blocks.
2. Diff section style and attachment fields on matched `SectionIR` nodes.
3. Diff referenced header/footer contents exactly once per shared story.
4. Reject attachment creates whose target topology is not transport-verified.
5. Do not treat header/footer attachment retargeting as a generic section-style
   field update. Live Docs replay showed `updateSectionStyle` rejects
   `defaultHeaderId` / `defaultFooterId`, so supported attachment transforms are
   create, continue, content-update-in-place, and delete.

This eliminates the need for document-wide "find first default header/footer"
stateful hacks.

If the target context requires a transport form that the Docs backend does not
honor or rejects, lowering must reject the edit explicitly. That is a transport
capability failure, not a reason to fall back to document-global heuristics.

Tabs need the same identity split as shared headers. Live replay of a second-tab
fixture showed that transport `tabId` is not a stable semantic matching key
across fresh documents. Diff must therefore match tabs by structural path in the
tab tree, while lowering still emits requests against the live base tab ID.

The proven tab slice now includes:

1. top-level tab creation with immediate body population
2. child-tab creation using deferred parent tab IDs
3. named-range creation inside a newly created tab without any valid desired-side
   transport `tabId`

The remaining explicit tab boundary is header/footer creation on a newly added
tab in a document that already has tabs. The live Docs transport still
mis-targets that path to the first tab, so the reconciler must reject it
explicitly.

## Lowering Phase

Lowering converts semantic edits into legal Docs API requests.

Semantic edits must carry enough information to lower deterministically.
Lowering should not rediscover intent by reparsing arbitrary desired-state
subtrees.

Lowering is the only phase allowed to know:

1. UTF-16 request coordinates
2. paragraph carrier positions
3. table start locations
4. section break locations
5. request batching and deferred ID dependencies
6. revision control

### Layout state

`LayoutState` is maintained per `(tab_id, story_id)` and
tracks legal insertion/deletion coordinates plus the transport side effects of
already-planned requests.

It resolves:

1. paragraph interior positions
2. paragraph end positions
3. story end positions
4. table start positions
5. section attachment locations
6. annotation anchor positions in the current shadow transport state

No code outside the lowering layer may construct raw Docs indices.

### Legal point system

```text
LegalPoint =
    InteriorText(position, utf16_offset)
  | BlockBoundary(position)
  | EndOfStory(story_id)
  | TableStart(table_id)
  | SectionStart(section_id)
```

`LegalPoint` is a lowering refinement of `PositionIR`, not a second semantic
coordinate system. It resolves to Docs coordinates only through `LayoutState`.

### Lowering invariants

1. No delete range may include `eos`.
2. A protected structural separator may never be deleted in isolation.
3. An interior paragraph separator may be consumed only by an explicit
   paragraph-merge or block-delete lowering rule.
4. No text insertion may target a table start.
5. No page break may be lowered outside `BODY`.
6. No table may be lowered into `FOOTNOTE` or `TABLE_CELL`.
7. Every request using IDs created earlier is topologically ordered after the
   producer request.
8. Within a coordinate partition, mutations are emitted in descending resolved
   position order unless a request dependency requires otherwise.
9. `LayoutState` is updated after every emitted request side effect that changes
   legal positions inside the current batch.
10. Section-boundary edits carry an explicit split/delete anchor, not only a
    target section ordinal.
11. Content-producing edits carry the semantic fragment they introduce or
    transform, not only counts or transport hints.
12. Shared-story edits are matched by logical attachment edges, not transport
    story IDs.

## Range legality

Delete legality is not sufficient. Formatting and bullet ranges must also obey
Docs boundary rules.

Rules:

1. text-style, paragraph-style, and bullet ranges must exclude `eop` / `eos`
2. delete ranges may cross paragraph boundaries only when planned as structural
   boundary deletes that preserve story/container legality
3. delete ranges must exclude `eos` and any protected structural separator
4. text-style and paragraph-style ranges must never extend past the final legal
   content position of the target story
5. bullet ranges must never terminate at or beyond the terminal story
   sentinel
6. when the Docs API extends a style range to include adjacent newlines, the
   planner must cap the requested range so that the effective applied range
   remains legal
7. if a full-paragraph text-style update would also style a list bullet, that
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

Interior paragraph separators are consumed only by structural paragraph edits,
never by paragraph-local text diff.

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
   terminal story sentinel.
2. It is valid for body, header, footer, and footnote operations whose Docs
   request form supports end-of-segment insertion.
3. Lowering should prefer `endOfSegmentLocation` over synthetic carrier
   insertion when the API exposes both forms.

Consequences:

1. append-at-end is a first-class lowering operation
2. segment-end insertion is independent of paragraph-carrier heuristics
3. terminal newline preservation remains explicit

### Deletion

All deletes are lowered from semantic spans that exclude `eos`.

Plain text diff never consumes `eop`. An interior paragraph separator may be
consumed only by an explicit structural paragraph/list delete or merge.

The planner computes the maximal legal delete range under Docs constraints:

1. never delete final story sentinel
2. never delete only the separator protecting a table, TOC, or section break
3. consume interior paragraph separators only when the semantic edit is an
   explicit paragraph merge/delete
4. if a semantic delete would violate these rules, rewrite as a legal
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
   typed slots and `sectionBreakLocation` when a new section-scoped story must
   be created
2. content edits against the referenced story
3. `UpdateSectionStyleRequest` only when actual section style fields must be
   updated, not to retarget header/footer IDs

Shared stories are created once and referenced by the section graph in the
semantic model.

Lowering must also consult a transport capability matrix. If the live Docs API
cannot reliably realize a semantically-valid attachment transform for the target
tab/section/slot combination, the reconciler must reject that transform
explicitly instead of misrouting it to another tab or section.

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

Use sequential batches only for producer-consumer dependencies.

The dependency graph is batch-relative, never global.

Batch layer 0:

1. `AddDocumentTabRequest`
2. `CreateHeaderRequest`
3. `CreateFooterRequest`
4. `CreateFootnoteRequest`

Batch layer N+1:

1. requests that reference IDs created in batch N
2. dependent story edits that populate newly created resources
3. dependent batches may carry deferred response placeholders rather than
   captured transport IDs; executor resolution is part of the batch model

All other operations stay in the earliest dependency-valid batch.

Execution rule:

1. batch 0 uses `base.revision_id`
2. batch `N+1` uses the `requiredRevisionId` returned by the response to batch
   `N`

The planner computes dependency layers. The executor advances revision control
between layers.

## Unsupported Operations

Reject, do not guess, when the desired semantic transform cannot be lowered
safely.

Examples:

1. mutation of read-only TOC contents
2. page breaks inside non-body containers
3. nested table transforms outside the proven empty-cell creation slice
4. unsupported opaque block mutation
5. section attachment transforms lacking a legal section break target
6. header/footer creation paths that require a Docs API transport route known to
   mis-target or fail for the target tab/section/slot
7. section-break topology edits without dedicated lowering support
8. sidecar resource mutations outside the supported surface

Live confidence-sprint result:

1. creating a nested table inside a newly inserted empty table cell is viable in
   Google Docs transport and can be modeled recursively without special-case
   request hacks
2. recursive support does not remove the need to reject harder nested-table
   transforms until they are replay-proven

Failure mode must be `UnsupportedEdit(reason)` at semantic phase or
`LoweringError(reason)` at lowering phase, never a best-effort invalid request.

## Correctness Guarantees

For all supported edits, under execution that starts from
`requiredRevisionId == base.revisionId` and advances the required revision after
each successful batch, the system guarantees:

1. every emitted request is structurally legal by construction
2. no request deletes a final newline sentinel
3. no page break is emitted in header/footer/footnote/table cell
4. no text insertion targets a table start
5. list continuity is explicit and testable
6. body/header/footer/footnote/table-cell recursion uses one algorithm with
   different capability sets
7. shared header/footer semantics are preserved through explicit section
   attachments for supported attachment transforms
8. tab hierarchy is preserved rather than flattened away
9. semantic annotations such as named ranges are preserved through anchored
   comparison and lowering

## Test Contract

All reconciler tests belong to one of two allowed classes:

1. exact-plan contract tests:
   1. `base Document`
   2. `desired Document`
   3. parse -> diff -> lower
   4. normalize requests
   5. assert exact batch equality
2. convergence tests:
   1. `base Document`
   2. `desired Document`
   3. parse -> diff -> lower
   4. execute requests
   5. parse actual result back into `DocumentIR`
   6. compare semantic IR equality

Raw transport JSON equality is never the oracle.

### Mandatory test classes

1. story-end edits in body/header/footer/footnote/table-cell
2. append/prepend/split/merge of list runs
3. paragraph text mutation without block replacement
4. mixed paragraph/table/pagebreak insertion around structural boundaries
5. safe header/footer creation, shared-story reuse, and explicit rejection of
   unsupported attachment routes
6. recursive cell content edits
7. footnote reference creation plus dependent footnote content population
8. annotation-only diffs and annotation shifts after content edits
9. raw-transport fixtures whose real API indices differ from mock reindexing
10. typed header/footer slot behavior (`DEFAULT`, `FIRST_PAGE`, `EVEN_PAGE`)
11. idempotence: `reconcile(x, x) == []`
12. convergence: after apply, reparsed actual IR equals desired IR
13. multi-batch revision handoff using returned `requiredRevisionId`
14. transport normalization fixtures: run splitting, soft line breaks, missing
    trailing paragraph, numeric style normalization
15. explicit unsupported transport-capability failures

### Comparator rule

The verifier must compare semantic list runs and section attachments.

It must not ignore:

1. `lists`
2. list continuity
3. shared story attachment graph
4. typed header/footer slot attachments
5. anchored annotations such as named ranges
6. supported sidecar resource catalogs

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
5. explicit unsupported rejection for ambiguous table transport shapes

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
2. typed structural separators with explicit protected-versus-consumable roles
3. first-class lists plus explicit section and resource graphs
4. typed semantic diff independent of Docs transport coordinates
5. a deterministic canonicalization pass for transport variance
6. legality-preserving lowering phase that alone understands Docs request rules

This is the architecture that makes newline compensation unnecessary and turns
today's structural bugs into invalid states that the system cannot express.
