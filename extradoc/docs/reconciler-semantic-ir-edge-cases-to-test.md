# Reconciler Semantic IR Edge Cases To Test

This file distills the historical reconciler failures that repeatedly caused
"fix one thing, break another" regressions. These are the scenarios the new
semantic-IR reconciler must pass by construction.

Each entry captures:

1. the scenario to test
2. the historical evidence
3. the design invariant the new reconciler must satisfy

## Structural Boundaries

| Scenario | Historical Evidence | Required Invariant |
|---|---|---|
| Insert first visible content into an otherwise empty tab body | commit `dae13d5`; `extradoc/src/extradoc/reconcile/_generators.py` empty-doc handling | The first body section is structural. Lowering must insert at the first legal position inside that section, never at index `0`. |
| Delete or replace all visible content in a story | `extradoc/docs/googledocs/rules-behavior.md`; `DeleteContentRangeRequest.md` | Final story newline is a sentinel. No delete range may consume it. |
| Delete across text containing emoji / surrogate pairs | `extradoc/tests/test_mock_api.py` UTF-16/surrogate tests; `extradoc/tests/test_reconcile.py` UTF-16 tests | Semantic text diff may operate on graphemes, but lowering must emit UTF-16 ranges that never split a surrogate pair. |
| Insert before a table, TOC, or section break | commits `8daf08e`, `bc50de3`; `rules-behavior.md` | Structural block starts are not text insertion points. Lowering must target a legal carrier paragraph or `endOfSegmentLocation`, never the structural start marker. |
| Delete newline immediately before a table / TOC / section break | `DeleteContentRangeRequest.md`; commit `bc50de3` | Protected separator newlines are structural barriers. Deletes must either remove the full structural element or stop before the barrier. |
| Insert before a TOC without mutating the TOC | commit `bc50de3`; `extradoc/tests/test_reconcile.py` TOC tests | TOC is read-only and boundary-sensitive. Reconciler may insert before it, but never inside it and never normalize its content away. |
| Raw section-break carrier paragraphs appear/disappear around equivalent semantic sections | live confidence-sprint fixtures | Canonicalization must erase transport-only carrier paragraphs before diff so section topology edits stay semantic. |

## Tables And Layout Side Effects

| Scenario | Historical Evidence | Required Invariant |
|---|---|---|
| Insert table between paragraphs | `InsertTableRequest.md`; commits `a426414`, `8daf08e` | `insertTable` transport side effects belong to lowering state, not semantic content. |
| Insert table at the start of a section | commit `8daf08e`; serde `CLAUDE.md` | Lowering must account for the carrier paragraph/newline that the API requires even when semantic section content starts with a table. |
| Consecutive tables in the same gap | commit `8daf08e` | Lowering must simulate post-table separator state so adjacent table inserts stay index-stable. |
| Paragraph immediately after inserted table becomes styled incorrectly | commit `09b684f` | Layout state must include the displaced post-table separator when computing style ranges after table insertion. |
| Edit cell content while deleting columns or rows | commit `40c6741` | Table diff ordering must respect position dependencies: content edits at old coordinates before structural row/column shifts. |
| Multi-paragraph or styled table cell content | commit `c003257`; `extradoc/tests/test_reconcile.py` Issue 15 | Table cells recurse through the same story engine as body/header/footer, not a flattened string path. |
| Table cell style changes | commit `cc61533`; `extradoc/tests/test_reconcile.py` Issue 17 | Cell style is first-class semantic table state, not comparator noise. |
| Distinct tables with similar topology align correctly | commit `39d6768` Issue 16; `extradoc/tests/test_reconcile.py` fingerprint tests | Table matching cannot collapse to a constant fingerprint or plain-text shortcut. |
| Row/column edits adjacent to merged cells | design goal in `reconciler-semantic-ir-design.md` | Merge topology is part of semantic table state and must survive structural edits. |

## Lists And Paragraph Styles

| Scenario | Historical Evidence | Required Invariant |
|---|---|---|
| Append list items at end of segment | `client/EXTRADOC_BUGS.md` BUG-4; commit `4ba973b` | Bullet/style ranges must end strictly before the terminal sentinel. |
| Add multiple consecutive list items as one semantic list | commit `7cbaa9c`; `extradoc/tests/test_reconcile.py` list batching tests | List continuity is a semantic run, not one request per paragraph. |
| Append list items where lowering needs the new item content, not only the count | live confidence-sprint fixtures | Semantic edits must carry appended list fragments so lowering can emit `insertText` and bullet requests deterministically. |
| Insert paragraph between two list runs | `extradoc/tests/test_reconcile.py` list batching tests | Split/merge behavior must be explicit in list space, not inferred from `listId`. |
| Relevel list items | `extradoc/docs/googledocs/lists.md` | Releveling is a transport choreography (`deleteParagraphBullets` + tabs + recreate bullets) planned from semantic list levels. |
| Full-paragraph style update in list context | `rules-behavior.md`; implementation plan Task 5 | Bullet styling side effects are part of planning, not post-hoc verifier suppression. |
| Paragraph style inheritance bleed across inserted blocks | commit `365c44e`; `extradoc/src/extradoc/client.py` raw-base normalization comments | Effective style must be resolved separately from explicit style, and lowering must clear/restore explicit deltas deterministically. |
| Heading-to-normal change with no visible formatting delta | long-running style normalization pain point | Semantic equality must include paragraph role/style intent, not only current effective rendering. |

## Non-Text Inline / Block Elements

| Scenario | Historical Evidence | Required Invariant |
|---|---|---|
| Insert page break in body | `client/EXTRADOC_BUGS.md` BUG-3; commit `eb29b63` | Page break is a semantic block lowered via `insertPageBreak`, not paragraph text. |
| Insert page break in header/footer/footnote/table cell | `client/EXTRADOC_BUGS.md` BUG-3; `CreateFootnoteRequest.md` / `InsertSectionBreakRequest.md` capability rules | Container capabilities must reject unsupported block kinds before lowering. |
| Insert footnote reference plus footnote content | `client/EXTRADOC_BUGS.md` BUG-2; `CreateFootnoteRequest.md` | Footnote refs are ID-producing inline edits: create reference first, then reconcile the footnote story in a dependent batch. |
| Paragraph containing HR / inline object / footnote ref in an add gap | `extradoc/src/extradoc/reconcile/_generators.py` guards; `client/EXTRADOC_BUGS.md` | Non-text inline/block producers need first-class lowering or explicit unsupported rejection. They cannot fall through `insertText`. |

## Sections, Headers, Footers, And Tabs

| Scenario | Historical Evidence | Required Invariant |
|---|---|---|
| Multi-section document with section-specific header/footer attachments | commit `39d6768` Issue 18; `CreateHeaderRequest.md` / `CreateFooterRequest.md` | Section attachment graph is semantic state and must be represented explicitly. |
| Insert a section boundary where lowering needs the exact split anchor | live confidence-sprint fixtures | Section-boundary semantic edits must carry the split location in semantic block space, not only the resulting section count. |
| Shared header/footer reused across sections | current design intent; multi-section tests | Shared story identity must be separate from section attachment edges. |
| Existing header content replayed onto a fresh document with a different `headerId` | live confidence-sprint replay | Shared-story matching must use logical attachment slots, not captured transport IDs. |
| Default vs first-page vs even-page header/footer slots | `DocumentStyle.md` | Header/footer attachments are typed slots, not a single `header_ref` / `footer_ref`. |
| New tab with header/footer in a document that already has tabs | `client/EXTRADOC_BUGS.md` BUG-8 | Lowering must consult a transport capability matrix and explicitly reject semantically-valid but API-broken transforms. |
| Tab hierarchy and child tabs | `tabs.md`; design goal | Reconciler must preserve tree topology, not flatten tabs into a list. |
| Requests without `tabId` silently hit first tab | `tabs.md`; multiple historical tab bugs | Lowering must treat `tabId` as mandatory transport routing except where the API explicitly forbids it. |

## Anchored Extras And Semantic Metadata

| Scenario | Historical Evidence | Required Invariant |
|---|---|---|
| Markdown special tables whose meaning is carried by `extradoc:*` named ranges | `extradoc/tests/test_serde_markdown.py`; `extradoc/src/extradoc/reconcile/_core.py` named-range diff | Named ranges are semantic anchored annotations, not transport debris to ignore. |
| Content unchanged but named-range annotation changed | current named-range diff path | Semantic equality must include annotation anchors; verifier must not collapse these docs as equal. |
| Named-range-only add/delete replay on unchanged body text | live confidence-sprint replay | Annotation lowering must resolve from the same story-local coordinate model as content edits. |
| Annotation anchor survives block split or merge | historical index-drift failures | Anchored annotations must follow logical positions in story space, not stale block IDs or UTF-16 offsets. |
| New tab with named ranges | `_core.py` comment about deferred complexity | Anchored annotations must lower after any ID-producing story/tab creation they depend on. |
| Raw API indices differ from mock-reindexed indices around special tables | commit `365c44e`; `client.py` raw-base comments | Lowering must derive coordinates from real base transport layout or an exact transport shadow, never from approximate reindexing. |

## Batching, Ordering, And Verification

| Scenario | Historical Evidence | Required Invariant |
|---|---|---|
| Body edits combined with header/footer edits in the same batch | `client/EXTRADOC_BUGS.md` BUG-9 | Ordering must be modeled per coordinate partition and per dependency, not as one flat append-only batch. |
| Multiple batches using `requiredRevisionId` | `WriteControl.md`; `extradoc/tests/test_mock_api.py` revision tests | Executor must carry forward the revision returned by each successful batch before sending the next batch. |
| Comparator strips semantic list / attachment / table metadata | `extradoc/src/extradoc/reconcile/_comparators.py`; historical gap docs | `reconcile_v2` verification must compare semantic IR, not transport JSON after aggressive normalization. |
| Request sequence looks plausible but final document is wrong | long history of comparator and mock workarounds | Exact-plan tests are necessary but insufficient; convergence tests against semantic IR remain mandatory. |

## Minimum Regression Fixture Set

The first durable fixture set for `reconcile_v2` should include:

1. Empty body plus first insert into the first section.
2. Emoji edits at document start and end.
3. Insert paragraph before table with concurrent deletes.
4. Insert table between paragraphs, at section start, and adjacent to another table.
5. Paragraph-after-table style application.
6. List creation, continuation, split, merge, and end-of-segment append.
7. Page break add in body and rejection in non-body containers.
8. Footnote creation with content population in a dependent batch.
9. Multi-paragraph styled cell reconciliation plus row/column deletion.
10. Merge/unmerge topology next to row/column edits.
11. TOC read-only plus insert-before-TOC.
12. Multi-section header/footer attachment graph including shared stories and typed slots.
13. Explicit rejection for new-tab header/footer creation on an existing multi-tab doc.
14. Named-range-only diffs and named-range shifts after content edits or block splits.
15. Heading-role-only change with no effective formatting delta.
16. Raw-transport fixture where mock reindexing would have produced different table coordinates.
17. Multi-batch revision handoff using returned `requiredRevisionId`.
18. Live transport fixtures for paragraph-role change, list append, list-kind change, section split, and section delete with replay verification against canonical IR.
19. Live transport fixtures for text replace, paragraph split, table-cell text replace, existing-header text replace, and named-range add with replay verification against semantic diff convergence.
