# Live Validation Plan (Google Doc 1VjZV7QjYZ8yTkQ0R-xffxQ5I7mNIPD3eSv327scMACQ)

Use full pull → edit → diff → push → repull cycles. Prefer editing the live doc directly in Google Docs UI between cycles, then sync with `python -m extradoc pull` before each diff/push. Aim to run all scenarios at least once per refactor iteration.

## Scenarios (8+)
1) **Body mid-block modify**: edit text in the middle of a paragraph (no tables nearby). Expect a single CONTENT_BLOCK MOD with pristine_start anchored to preceding paragraph end.
2) **Body end-of-segment insert**: append a line at the very end of the body. Ensure `_emit_content_ops` strips trailing newline instead of deleting sentinel.
3) **Header end edit**: add text at end of default header. Confirms segment_start=0 handling and no cross-segment index bleed.
4) **Footnote content change**: edit an existing footnote paragraph. Verify segment grouping keeps body/footnote indexes separate.
5) **Table cell modify**: change text in a middle cell (no structure changes). Confirm cell content start/end from block_diff are used, no clamps elsewhere.
6) **Table row add + cell edits**: insert a row between existing rows, then edit one of its cells. Expect a single `insertTableRow` and cell content ops; this guards against the duplicated `insertTableRow` we observed.
7) **Table column add + right-to-left cell edits**: add a column to the rightmost side and edit cells in the new column. Validate deferred column inserts and reverse cell walk.
8) **Table bottom/right delete**: delete last row and last column in a table, plus edit a remaining cell. Ensures deletes run before content ops without index drift.
9) **Nested table cell edit**: edit text inside a nested table cell (table inside a cell). Confirms segment_end propagation and recursive content handler use.

## Execution notes
- Use `PYTHONPATH=src python3 -m extradoc pull ...` and `diff/push` for each scenario. Capture request JSON for spot-checks.
- After push, always `pull` into a fresh folder (e.g., `output-after/`) and re-run `diff` to confirm clean state (no-op).
- Log any duplicate structural ops (e.g., repeated `insertTableRow`) and capture the exact doc edits that triggered them.
- Keep output folders per scenario or timestamped to avoid mixing results.

## Execution tracker
| Scenario | Status | Notes |
| --- | --- | --- |
| 1 Body mid-block modify | PASS | Clean diff/push/repull; mid-paragraph edit produced expected 4 ops |
| 2 Body end-of-segment insert | PASS | Inserted final paragraph; ops clamped before sentinel; clean repull |
| 3 Header end edit | PASS | Header tail edit stayed within header segment; clean repull |
| 4 Footnote content change | FAIL | Inline footnote was dropped; requests issued createFootnote(endOfSegment) without content |
| 5 Table cell modify | PASS | Single cell edit in row 1 col 1; clean repull |
| 6 Table row add + cell edits (dup row guard) | PASS | ID-based row alignment; combined row add + cell edit verified; 9 requests |
| 7 Table column add + R→L cell edits | PASS | ID-based column alignment; 14 requests (1 insertTableColumn + cell content + bold style); content in correct cells |
| 8 Table bottom/right delete + cell edit | Not run | TODO |
| 9 Nested table cell edit | Not run | TODO |
