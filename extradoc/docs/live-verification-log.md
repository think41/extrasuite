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

## Latest Known State

- The most recent live repair check on doc `1prgtIDeKhmIB4B1I8lwr7qbtzUSAZeP-GVBTZ0XGAvk`
  succeeded after the latest list-role and carrier-normalization fixes.
- Final raw verification showed:
  - list items after `## Lists Revised` are `NORMAL_TEXT`
  - callout-gap carrier paragraphs are `NORMAL_TEXT`
  - the blank paragraph before the code-block table is `NORMAL_TEXT`
- Broader local test coverage is not yet aligned with the current reconciler
  behavior. Many failures appear to be stale exact-shape expectations rather
  than newly discovered live regressions.

## Open Questions

1. Does the full maintained live smoke matrix still pass from the current checkpoint?
2. Are there any remaining live XML-specific failures after the recent markdown/body fixes?
3. Do comments need a dedicated live smoke pass before release?
4. Why did `release_smoke_docs.py` exit during `20260331-live-verification-pass1`
   without writing `summary.json`?
