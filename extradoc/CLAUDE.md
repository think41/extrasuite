## Overview

Python library that transforms Google Docs into an XML folder structure for
LLM-assisted editing. The active implementation is the `serde` +
`reconcile` pipeline used by `DocsClient`.

**Canonical on-disk format:** `docs/on-disk-format.md`

## Active Pipeline

```text
pull:  API -> DocumentWithComments -> serde.serialize() -> folder
edit:  agent edits document.xml / styles.xml / comments.xml
diff:  pristine.zip -> serde.deserialize() -> base bundle
       edited folder -> serde.deserialize() -> desired bundle
       reconcile(base.document, desired.document) -> document batches
       diff_comments(base.comments, desired.comments) -> comment ops
push:  apply comment ops first
       then batch_update() document batches with resolve_deferred_ids()
```

`DocsClient` in `src/extradoc/client.py` already uses this pipeline.

## Key Packages

| Package | Purpose |
|---------|---------|
| `src/extradoc/serde/` | `DocumentWithComments ↔ XML folder` |
| `src/extradoc/reconcile/` | `Document` diff -> `BatchUpdateDocumentRequest` batches |
| `src/extradoc/comments/` | `comments.xml`, inline `comment-ref`, and comment diffs |
| `src/extradoc/mock/` | In-process mock of the Docs `batchUpdate` API |
| `src/extradoc/api_types/` | Generated typed models from the Docs API schema |
| `src/extradoc/transport.py` | Transport interfaces and implementations |
| `src/extradoc/client.py` | `DocsClient` pull/diff/push orchestration |

## Documentation

- `docs/on-disk-format.md` — authoritative file/folder/XML format
- `docs/comment-anchoring-limitation.md` — Drive API limitation for anchored comments
- `docs/googledocs/` — local reference material for Google Docs API behavior

## Key Gotchas

- Google Docs indices are UTF-16 code units, not Python character offsets.
- Headers, footers, footnotes, and table cells each have their own index rules.
- New tabs require an `index.xml` entry and a `<sectionbreak>` as the first
  element of `<body>`.
- `styles.xml` is written on serialize, but deserialize also tolerates a
  missing `styles.xml` and treats it as empty `<styles />`.
- After `push`, always re-pull before making further edits.
- `comment-ref` elements in `document.xml` are display metadata derived from
  `comments.xml`, not primary editable content.
- `src/extradoc/mock/` is useful for fast local regressions, but it is not a
  release-confidence source and must not be treated as the transport truth.
  For reconciler changes, prefer fixture-backed live Google Docs replay before
  trusting the result.
- Do not add compensating reconciler logic just to satisfy the mock. If mock
  behavior disagrees with live Google Docs, the mock is wrong for that purpose
  and live fixtures win.

## Development

```bash
cd extradoc
uv sync --all-extras
uv run pytest tests/ -v
uv run ruff check . && uv run ruff format .
uv run mypy src/extradoc
```
