# Live Verification Log

## Purpose

Track end-user-facing live verification for the current `pull` / `push` and
`pull-md` / `push-md` workflows. This log is intentionally live-first: Google
Docs behavior is the authority, and mock-only checks do not count as release
verification.

## Current Goal

Decide whether the remaining work should focus on:

1. more live workflow verification and code fixes, or
2. broader cleanup of stale local tests and exact-shape expectations.

## Verification Checklist

### Markdown workflow

- [ ] Empty doc -> `pull-md` -> author initial content -> `push-md` -> `pull-md`
- [ ] Existing markdown doc -> edit headings/prose/lists -> `push-md` -> `pull-md`
- [ ] Multi-tab markdown doc -> edit existing tabs + new tab -> `push-md` -> `pull-md`
- [ ] Markdown doc with callouts / blockquotes / code blocks -> second-pass edits converge
- [ ] Markdown doc with tables / rich cell text -> second-pass edits converge
- [ ] Markdown doc with footnotes -> second-pass edits converge
- [ ] Markdown doc with named ranges in supported paths -> second-pass edits converge
- [ ] Repair an already-broken markdown doc in place

### XML workflow

- [ ] Empty doc -> `pull` -> author initial XML -> `push` -> `pull`
- [ ] Existing XML doc -> edit headings/prose/lists -> `push` -> `pull`
- [ ] XML doc with sections / header / footer -> second-pass edits converge
- [ ] XML doc with tables / nested tables / rich cell text -> second-pass edits converge
- [ ] XML doc with page break -> second-pass edits converge
- [ ] XML doc with footnotes -> second-pass edits converge

### Read-only / unsupported boundaries

- [ ] TOC / opaque block remains stable when unchanged
- [ ] Horizontal rule create/delete is rejected explicitly
- [ ] Unsupported header/footer-on-new-tab path fails explicitly
- [ ] Unsupported advanced merged-table path fails explicitly

### Comments workflow

- [ ] Reply flow remains functional
- [ ] Resolve flow remains functional
- [ ] Comment edits remain functional while document edits also occur

## Log

### 2026-03-31

- Started this log after checkpoint `3b8a95d`.
- Immediate focus:
  - rerun the maintained live release smoke workflows from the current code
  - record fresh markdown/XML confidence from live Docs
  - use those results to decide whether more live verification or test-suite cleanup is higher value
- Started live smoke run `20260331-live-verification-pass1`.
- Current status of that run:
  - artifact root created
  - `markdown_multitab/cycle1-authored` created
  - `xml_structural/cycle1-authored` created
  - no `summary.json` was written
  - the runner process exited before producing a final result
- This means the current live verification pass is incomplete and needs direct
  inspection of the harness / partial artifacts before it can count toward
  release confidence.
- Reproduced the same harness issue with retry run
  `20260331-live-verification-pass1-retry`.
- Live docs created by the harness before it stalled:
  - markdown smoke doc `1khFDxcCfEC1UoWRbWJp1NFqmtqYn9Sq_Ej2Z3PAXD-c`
  - XML smoke doc `17hbfDZT2S4VgYktuJscLHmf_UICHiFr_XAkHM68x0kM`
- Next action:
  - use the authored artifacts from the stalled harness as manual live
    verification inputs
  - continue verification directly with CLI push/pull rather than depending on
    the smoke wrapper
- Manual XML verification attempt on doc `17hbfDZT2S4VgYktuJscLHmf_UICHiFr_XAkHM68x0kM`:
  - fresh pull completed
  - authored XML payload copied onto the fresh base
  - `extrasuite docs push` did not return a terminal result and left a live
    `extrasuite docs push ... manual-xml-cycle1 ...` subprocess running
  - stale subprocesses were terminated explicitly
- Current interpretation:
  - XML verification is still the lower-confidence area
  - there may be a real hang or transport-level stall in the XML push workflow
    for the complex structural document, distinct from normal markdown repair flows
- Manual minimal XML verification on doc `1vDGwo3KGlw9_d3jxBSaKA2_yQp8acXHYFzQMzADIhvY`:
  - fresh pull completed
  - authored XML added one `<h1>` and one `<p>` after the required `<sectionbreak/>`
  - `extrasuite docs push` returned successfully: `Applied 3 document changes`
  - re-pull completed successfully
  - semantic comparison between authored XML and re-pulled XML was empty
- Current interpretation after the minimal XML pass:
  - basic XML `pull -> edit -> push -> pull` works
  - the remaining XML risk is narrower and appears tied to more complex
    structural documents rather than the XML path in general
- Manual medium XML verification on doc `1whB5_JpoqZ3EGSvOVJYXl_EG4ZTDwhZXjGhm62_enYs`:
  - fresh pull completed
  - authored XML added:
    - heading
    - prose paragraph
    - bulleted list
    - table
    - paragraph before page break
    - page break
    - heading after break
    - closing paragraph
  - `extrasuite docs push` did not return a terminal result
  - stale live `extrasuite docs push ... medium-xml-verification ...` subprocesses were terminated explicitly
- Current interpretation after the medium XML pass:
  - XML push does not only fail on the full structural smoke doc
  - the remaining XML risk now appears to include at least body documents with
    table-backed structure
  - next useful isolation step would be:
    1. XML with list + page break but no table
    2. XML with simple table but no page break
- Manual XML verification on page break without table, doc
  `1qeufmU6pLMSaSA8fX7QSOKWiapWDLZqTdh5312QZSB0`:
  - fresh pull completed
  - authored XML added:
    - heading
    - prose paragraph
    - bulleted list
    - paragraph before page break
    - page break
    - heading after break
    - closing paragraph
  - `extrasuite docs push` returned successfully: `Applied 15 document changes`
  - re-pull completed successfully
  - semantic comparison was **not** empty
  - visible corruption in re-pulled XML:
    - heading text came back as `PXML Page Break Verification`
    - paragraph text came back as `aragraph before the break.`
- Current interpretation after the page-break-without-table pass:
  - page breaks without tables do not hang, but they do not yet converge
  - there is still a real XML body rewrite bug affecting content around
    heading/list/page-break structure
  - the XML path still needs more live debugging before release confidence is justified
- Page-break XML path follow-up:
  - root cause 1: grouped pre-pagebreak inserts were re-resolving their anchor
    after each fragment and drifting from index `1` to `2`
  - root cause 2: the live-refresh executor only refreshed after a structural
    batch if there was already another preplanned batch queued; one-batch XML
    page-break pushes skipped refresh entirely
- Live verification after those fixes:
  - doc `1_2rTgW_C39BGHyXtahGmfdDn-xNH4zGxx_MH4f5V0KY` proved that a second-cycle
    fresh-base push now converges after the stable-anchor fix
  - doc `1y-8SrWvjhn_icBuo2T-4_gdLpnUbkeOD5SA6aHCCieQ` proved that the same XML
    page-break case now converges in a single push
  - re-pulled semantic diff for `1y-8SrWvjhn_icBuo2T-4_gdLpnUbkeOD5SA6aHCCieQ`
    was empty
- Current interpretation after the one-cycle page-break fix:
  - minimal XML path: proven live
  - XML heading/list/page-break body rewrite: proven live
  - the next XML blocker to verify is the medium body case that adds a real
    table before the page break
- XML table follow-up after the page-break fix:
  - simple table without page break no longer hangs
  - live doc `1z3iykofRa1w219W3_yfhhyW_sRCspSvzJCP8wV-jmTQ` showed that one-cycle
    XML table creation still does **not** populate cell content; the table
    structure is created, but the cells come back empty on re-pull
  - a second-cycle diff from that re-pull back to the authored XML is exactly
    the missing cell-content work (`Alpha`, `Beta`, `Gamma`, `Delta`)
  - medium table + page-break doc `1grWEhVXOt6JW1yOGv_dxBwbHXqL6qqvQhQHGGe3_Yxk`
    still entered a bad live partial state with repeated empty headings and an
    empty table before the push was terminated
- Current interpretation after the XML table split:
  - the remaining XML issue is no longer “page breaks” in general
  - it is specifically fresh table population / same-cycle table cell writes
    after the structural table insert on the XML path
- Fresh re-verification after the XML semantic-boundary work:
  - minimal XML doc `1xkQ_h6xuKVjWhAg1c-757XrzBNRANce1EYCi2ccTyCM` still converged
    semantically after `pull -> edit -> push -> pull`
  - page-break XML doc `1mE_g4n8uEf25CDCbghX_wXF3Tigsyuexy6XJQwXmNrE` still did not
    converge; re-pull showed `Second bullet` promoted to `HEADING_2`
  - fresh-table XML doc `1M9QS6jEMN2QdJsiduD4WacUDBIbAs2kNXESHcfMmO7U` still created
    only the table shell; re-pull showed all four `<td>` contents empty
- Current interpretation after the fresh re-verification:
  - desired XML parsing is no longer the main suspect
  - the remaining XML failures are in the structural refresh / staged execution
    path after shell inserts
- Structural refresh follow-up:
  - current code now truncates same-tab structural batches to the shell request
    only and retries live refresh when the refreshed plan still asks for the
    same shell insert
  - fresh page-break rerun `1ffZjm0TKoJ1Q5LZG228RTaCzyEI0w0wMJxiFnJIbC5k` no longer
    hangs silently; `push` now fails explicitly with:
    `Live Docs did not expose the applied structural change after refresh retries`
  - re-pulling the partial doc showed exactly the structural shell state:
    `<pagebreak/>` plus an empty trailing paragraph, with none of the intended
    surrounding heading/list/prose content
- Current interpretation after the explicit refresh failure:
  - the XML structural path is still blocked, but the failure mode is now much
    cleaner: the executor can detect that live Docs has not exposed enough
    structural state to continue safely
  - the next fix should target the structural refresh strategy itself rather
    than XML parsing or semantic diffing
- XML structural execution follow-up after the semantic-boundary work:
  - using shell-only truncation was too aggressive; it left the live base too
    empty, so refresh kept replanning the same shell inserts
  - preserving safe same-anchor prefix text after the structural shell moved
    the page-break path forward, but exposed that the stale-shell detector was
    too strict; a refreshed plan can still contain the same shell request and
    still represent real semantic progress
  - the stale-shell detector now only blocks when the first refreshed batch
    truncates back to the exact same shell batch we already executed
  - after that change, the page-break path advanced to the next real failure:
    stale post-delete indices in live refreshed batches
  - delete-sensitive live batches now split into a delete-only round, then
    re-fetch and replan from the actual post-delete document state
  - revision-mismatch responses after live refresh are now treated as a signal
    to re-fetch and replan rather than a terminal failure
  - stale raw insertion anchors are now clamped to the current raw section end
    instead of crashing during XML replan
- Fresh live XML page-break retest on doc `1rXUhe2T2f0iNuS-wUvcKgexV1QpRYXfh8SskmxvADqw`:
  - one-cycle `push` completed successfully: `Applied 38 document changes`
  - re-pull no longer shows total corruption or structural failure
  - semantic diff after re-pull is down to 2 localized paragraph-slice repairs
  - remaining issue:
    - the `<pagebreak />` ends up after the `After Break` heading and closing
      paragraph instead of before them
    - re-pulled XML also has one leading empty paragraph and one trailing empty
      paragraph around the page-break region
- Current interpretation after the latest page-break retest:
  - the XML page-break path is no longer blocked on refresh timing or stale
    revision handling
  - the remaining gap is now a narrower reconciler/lowering issue:
    content intended for the suffix span after an existing page break is still
    being reinserted on the wrong side of that page break during repair/replan

### 2026-04-10 — coordinate contract (Direction A) final verification

Branch `coordinate-contract-direction-a`. Validating the apply_ops/lower
coordinate contract refactor (Tasks 1–9) against the live API. Previous
attempts on FORM-15G were failing with invalid `deleteContentRange[496..497)`
targeting a table cell boundary.

Doc: `1FkRTeU852Mxg0OJh684MXutDxW7ubTkiA6_EXyRce54` (FORM-15G).

**Run 1 — no-op round trip**
- `pull → push (no edit) → verify`
- Result: **0 requests emitted**, push succeeded, verify passed.

**Run 2 — 3 targeted edits in the previously-drifting region**
1. Text edit inside the "Previous year" table cell (`2020-21` → `2025-26`) —
   this is the N-to-1 paragraph-collapse case that previously triggered the
   `[496..497)` bug.
2. New italic paragraph inserted before the `**PARTI**` heading.
3. Bold markers added around `DIVIDEND` inside an HTML `<td>` cell.

Total ops emitted: **16** (previous attempts on similar edits were producing
50+ ops with invalid ranges). Breakdown:

- Edit 1 (insert paragraph): 3 ops (insertText + updateParagraphStyle +
  updateTextStyle). Surgical.
- Edit 2 (text edit in cell): 8 ops — two deletes `[519..557)` and
  `[477..519)`, then insertText @477 plus four updateTextStyle run-style
  replays.
- Edit 3 (bold markers): 5 ops — two `**` insertText plus three
  updateTextStyle.

**Critical assertion**: no op touches indices `{496, 497}`. The cell
boundary that was the prior bug is untouched by the emitted batch.

Push succeeded with 0 API errors; `--verify` passed; re-pull after push is
byte-identical to the edited file (`diff` → empty).

**Non-contract quirks observed** (both pre-existing, unrelated to this work):

- Edit 3 (`**DIVIDEND**`) was pushed as literal `**` character insertion
  rather than a bold style toggle. HTML-in-markdown parser does not
  recognize markdown bold inside an HTML `<td>` cell.
- Edit 2 used delete+insert for the in-cell text change rather than a
  narrower string diff. Both ranges are clean cell-interior ranges; the
  pattern is expected when run styles need to be replayed inside the cell.

**Conclusion**: the coordinate contract refactor holds end-to-end against
the real API. The previously-drifted `[414..496)` cell region now generates
legal, surgical ops, and the full pull → edit → push → pull cycle is
byte-stable.

### 2026-04-01

- Applied diff.py anchor changes (PageBreakIR + TableIR treated as section anchors)
  and lower.py fixes (table cell sort order, raw_block_index clamping).
- XML page-break test on doc `1ffZjm0TKoJ1Q5LZG228RTaCzyEI0w0wMJxiFnJIbC5k`:
  - Starting state: nearly empty doc (just a shell pagebreak + empty para)
  - Authored XML: h1 + para + 2 bullets + pagebreak + h2 + para
  - Cycle 1: Applied 11 changes. Page break landed on CORRECT side. Second list item
    came back as `<p>` instead of `<li>` (list continuation lost across refresh boundary).
  - Cycle 2: Applied 10 changes. Both list items now correct `<li>`.
    Extra carrier `<p/>` before and after pagebreak (API-emitted, not user content).
  - Cycle 3: **No changes to apply** — fully converged.
- XML table-repair test on doc `1M9QS6jEMN2QdJsiduD4WacUDBIbAs2kNXESHcfMmO7U`:
  - Starting state: table shell with empty cells (from prior session)
  - Authored XML: h1 + para + 2x2 table with Alpha/Beta/Gamma/Delta + para
  - Cycle 1: Applied 8 changes. All cells correctly populated.
  - Cycle 2: **No changes to apply** — fully converged.
- Test suite cleanup: deleted 7 internal-implementation test files (~10.8K LOC),
  added `test_serde_xml_semantic.py` (public interface: XML folder → Document).

## Latest Known State

- XML page-break push: converges in 2 cycles. The page break now lands on the correct
  side in cycle 1. The second list item before the break loses its bullet and becomes
  a `<p>` in cycle 1 (list continuation across the structural refresh boundary), then
  recovers in cycle 2. Carrier `<p/>` elements around the break are API-emitted and
  are correctly ignored by the reconciler diff.
- XML table repair (existing shell → fill cells): converges in 1 cycle.
- XML minimal (heading + para): proven live, unchanged.
- Fresh table creation from empty doc (table insert + cell fill in one shot): NOT YET
  VERIFIED with current changes. Prior behavior was 2 cycles (shell in cycle 1, cells
  in cycle 2). The lower.py table-cell sort order fix may improve this.
- Test suite: internal spike tests deleted. Remaining failures are 9 pre-existing
  off-by-1 index errors in the old v1 reconciler table tests (unrelated to v2 path)
  and 1 pre-existing `UnsupportedSpikeError` in iterative markdown batching.

## Open Questions

1. Does fresh XML table creation (empty doc → table with cell content) now converge
   in 1 cycle with the lower.py table-cell sort fix?
2. Does the full maintained live smoke matrix still pass from the current checkpoint?
3. Do comments need a dedicated live smoke pass before release?
4. Why did `release_smoke_docs.py` exit during `20260331-live-verification-pass1`
   without writing `summary.json`?
