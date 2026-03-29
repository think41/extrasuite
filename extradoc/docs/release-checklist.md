# ExtraDoc Release Checklist

Release is blocked until the items in **Release Gate** are complete and the
remaining unsupported boundaries are documented in user-facing help.

## Release Gate

1. Public help and docs match the actual `pull` / `push` / `pull-md` /
   `push-md` behavior.
2. `reconcile_v2` is the default reconciler in the client.
3. The legacy reconciler remains in the codebase only as an internal rollback
   path. It is not part of the public CLI contract.
4. Live smoke verification passes for both XML and markdown workflows.
5. The supported / unsupported feature matrix is documented in one place.
6. Release-facing errors use stable product language, not sprint / spike
   terminology.

## Live Smoke Matrix

Run these on a fresh document and re-pull after every push:

1. XML cycle: `pull -> edit existing content -> push -> pull`
2. Markdown cycle: `pull-md -> create from empty -> push-md -> pull-md`
3. Markdown second cycle:
   `pull-md -> complex edits to existing content -> push-md -> pull-md`
4. Multi-tab cycle: create a new tab, edit existing tabs, then re-pull
5. Table cycle:
   edit cell text, insert/delete rows and columns, merge/unmerge supported
   regions, then re-pull
6. Footnote cycle:
   create a new footnote, edit surrounding prose, edit the footnote
   definition, then re-pull
7. Named-range cycle:
   add/delete named ranges and verify semantic convergence after re-pull
8. Header/footer cycle:
   edit supported existing header/footer stories and re-pull

## Current Status

1. `markdown_multitab` live smoke is semantically converging on both cycles.
   Remaining diffs are serializer normalization only:
   footnote IDs, ordered-list numbering normalization, HTML-table -> pipe-table,
   and bold header-cell markdown formatting.
2. `xml_structural` live smoke is still a release blocker.
   Current live evidence shows:
   `push` succeeds, but re-pulled XML still drops authored page breaks,
   first-section header/footer content, and cycle-2 footnote persistence.
3. The maintained smoke runner is
   `extradoc/scripts/release_smoke_docs.py`.

## Accepted Unsupported Boundaries

These are acceptable for release only if they are documented clearly in
user-facing help and the errors are explicit:

1. Creating or deleting horizontal rules through `push` / `push-md`
2. Editing TOC or other opaque read-only blocks
3. Creating a header/footer on a newly added tab in an existing multi-tab doc
4. First-section attachment reassignment through unsupported Docs transport
5. Advanced merged-table structural edits that the planner rejects explicitly

## User-Facing Support Matrix

The release help/docs must state these points explicitly:

1. Footnote creation and editing are supported in body content.
2. Page breaks are supported only where the Docs API supports them.
3. Horizontal rules are read-only.
4. Section breaks are required structural elements and are read-only.
5. New tabs are supported, but some header/footer creation paths are not.
6. Tables are supported broadly, with explicit errors for unsupported merged
   structural cases.

## CI / Verification Expectations

1. `ruff`, `mypy`, and `pytest` pass in CI.
2. At least one maintained live verification script exists for markdown
   convergence.
3. At least one maintained live verification script exists for raw replay
   fixtures.
4. Release notes summarize supported features and explicit limits.
