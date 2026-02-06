# Architectural Direction (Backwards-Walk Diff/Push)

Aligned sources: `docs/refactor-plan.md`, this session's changes, and live testing workflow.

## Core invariants
- Per-segment backwards walk: process changes high→low within each segment (body, each header/footer, each footnote, each table cell). At pristine position P, everything < P is pristine.
- Segment independence: no cross-segment index adjustment; each segment has its own index space.
- Sentinel safety: final newline per segment is never deleted; only `_emit_content_ops` may strip trailing newline on insert at segment end.
- Delete/insert pairs stay together; no global reordering or adjustment pass.

## Indexing rules
- BlockChange carries `pristine_start_index`, `pristine_end_index`, `segment_end_index` (exclusive) from block diff.
- ADD anchoring: `pristine_start_index` is end of preceding pristine sibling (or segment start), never segment end.
- Tables: lengths computed per row/cell; cells carry content start/end for nested content ops. Rows/cells walked bottom→top and right→left.

## Content handling
- Single path `_emit_content_ops` for body/header/footer/footnote/table cell content.
- Deletes clamped to `< segment_end`; inserts clamped to `segment_end-1` only; strip trailing newline when inserting at segment end.
- All content inserts/deletes happen in container order during backwards walk; no scattered clamps elsewhere.

## Table handling
- Row walk high→low; cell walk right→left.
- Deferred inserts: row/col adds applied after deletes/mods to avoid index drift.
- Anchors: row add inserts below `min(row_index-1, last_pristine_row)` (0 if top). Column adds keyed per row to prevent misordering/duplication.
- Column width updates use live table start index from current doc when widths differ.

## Simplifications / removals
- Removed legacy global reorder/adjust code, ad-hoc clamps, merged body insert behavior, `_skipReorder` pattern.
- Only sentinel logic remains in `_emit_content_ops`.

## Validation strategy
- Use the live Google Doc `1VjZV7QjYZ8yTkQ0R-xffxQ5I7mNIPD3eSv327scMACQ` with the scenarios in `docs/live-test-plan.md`.
- Each cycle: pull → edit → diff → push → repull → diff (expect no-op). Capture any duplicate structural ops (e.g., repeated `insertTableRow`).

## Known watch items
- Duplicate `insertTableRow` seen once; scenario #6 in live plan targets this.
- Multi-table sections: table start indexes derived from desugared doc via `calculate_table_indexes`; ensure block_diff carries correct table ids/positions when multiple tables exist.
- Footnote edits: ensure segment keys map correctly so deletes/inserts don't cross-adjust body.
