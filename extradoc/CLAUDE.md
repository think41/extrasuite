## Overview

Python library that transforms Google Docs into an XML folder structure optimized for LLM agents. Implements the pull/diff/push workflow via typed Pydantic models throughout.

Agent-facing skills that explain the XML format and editing workflow are in `server/skills/extradoc/`.

## Pipeline

```
pull:  API → Document → serde.serialize() → folder (XMLs + pristine.zip)
edit:  agent modifies XML files in the folder
diff:  pristine.zip → serde.deserialize() → base Document
       edited XML   → serde.deserialize() → desired Document
       reconcile(base, desired) → list[BatchUpdateDocumentRequest]
push:  for each batch: resolve_deferred_ids() → transport.batch_update()
```

**On-disk format spec:** `docs/on-disk-format.md` — what files are written, which are editable, which are read-only.

## Key Packages

| Package | Purpose |
|---------|---------|
| `src/extradoc/serde/` | `Document ↔ XML folder`. See `serde/CLAUDE.md` |
| `src/extradoc/reconcile/` | Diffs two `Document` objects → `list[BatchUpdateDocumentRequest]`. Public API: `reconcile()`, `verify()`, `reindex_document()`, `resolve_deferred_ids()` |
| `src/extradoc/mock/` | Pure-function mock of `batchUpdate` API for testing. See `mock/CLAUDE.md` |
| `src/extradoc/api_types/` | Pydantic models generated from Google Docs API schema. Key types: `Document`, `BatchUpdateDocumentRequest`, `Request`, `DeferredID` |
| `src/extradoc/transport.py` | `Transport` ABC + `GoogleDocsTransport` (production) + `LocalFileTransport` (golden files) |
| `src/extradoc/client.py` | `DocsClient` orchestrator: `pull()`, `diff()`, `push()` |

## Testing Pattern

Tests are end-to-end: start from a golden document, convert to XML, modify, diff, push to mock, verify the result.

```python
# 1. Load golden → Document → XML on disk
raw = json.loads(Path("tests/golden/<id>.json").read_text())
doc = Document.model_validate(raw)
serde.serialize(doc, output_dir)

# 2. Agent edits XML files in output_dir

# 3. Diff: deserialize pristine and edited
base = serde.deserialize(pristine_dir)    # from pristine.zip
desired = serde.deserialize(output_dir)   # after edits
batches = reconcile(base, desired)

# 4. Push to mock, verify result matches desired
base_dict = base.model_dump(by_alias=True, exclude_none=True)
mock = MockGoogleDocsAPI(base_dict)
responses = []
for i, batch in enumerate(batches):
    if i > 0:
        batch = resolve_deferred_ids(responses, batch)
    responses.append(mock.batch_update([r.model_dump(...) for r in batch.requests]))

actual = Document.model_validate(mock.get())
assert documents_match(actual, desired)
```

For convenience, `reconcile._core.verify(base, batches, desired)` wraps steps 4–5.

Golden files: `tests/golden/<document_id>.json` — raw API responses for reproducible testing.

## Documentation

- `docs/on-disk-format.md` — **On-disk format spec (canonical reference)**
- `docs/reconciliation-gaps.md` — Known gaps in the reconcile module
- `docs/googledocs/` — Google Docs API reference — **use this instead of web fetching**
  - `docs/googledocs/api/` — Individual request/response types
  - `docs/googledocs/rules-behavior.md` — Index behavior rules for batchUpdate

## Deprecated / Stale

The following files belong to the **legacy pipeline** (pre-serde/reconcile). They are kept for reference but are no longer the active code path. `client.py` will be updated to use the new pipeline; until then, `DocsClient` still calls these.

| File | Status |
|------|--------|
| `src/extradoc/xml_converter.py` | **Deprecated** — replaced by `serde` |
| `src/extradoc/engine.py`, `parser.py`, `differ.py`, `walker.py` | **Deprecated** — replaced by `reconcile` |
| `src/extradoc/push.py` | **Deprecated** — replaced by `resolve_deferred_ids` + `transport.batch_update` |
| `src/extradoc/desugar.py`, `block_indexer.py`, `indexer.py`, `style_factorizer.py` | **Deprecated** — internal to legacy pipeline |
| `src/extradoc/generators/` | **Deprecated** — replaced by `reconcile/_generators.py` |
| `docs/extradoc-spec.md` | **Stale** — superseded by `docs/on-disk-format.md` |
| `docs/extradoc-diff-specification.md` | **Stale** — describes legacy diff engine |
| `docs/gaps.md` | **Stale** — describes legacy pipeline bugs |

## Key Gotchas

- **UTF-16 indexes:** Google Docs uses UTF-16 code unit indexes, not character counts. The mock's `reindex_and_normalize_all_tabs()` handles this.
- **Separate index spaces:** Headers, footers, footnotes, and table cells each have their own index space starting at 0.
- **Deferred IDs:** When reconcile creates new segments (headers, footers) or tabs, the IDs assigned by the API aren't known until the first batch executes. `DeferredID` objects are placeholders resolved via `resolve_deferred_ids()` before each subsequent batch.
- **Pristine state:** After push, always re-pull before making additional changes.
- **Consistency not accuracy:** The `XML → Document` path doesn't need to perfectly reproduce the API's Document — both base and desired go through the same path, so any systematic bias cancels out in the diff.

## Authoring New Tabs

When creating a new tab folder from scratch (not pulled from the API), three things are required:

**`styles.xml` is mandatory.** The deserializer unconditionally reads it — no existence check. A minimal valid file:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<styles>
  <para class="_default" direction="LEFT_TO_RIGHT" />
  <listlevel class="_default" indentFirst="18.0pt" indentLeft="36.0pt" />
</styles>
```

**`<sectionbreak>` must be the first element of `<body>`.** The reconciler's `_create_initial_body_segment()` models a freshly-created tab as already containing a section break. If your desired XML omits it, the reconciler sees a deletion and raises `ReconcileError: Section break deletion is not supported`. Use:
```xml
<sectionbreak sectionType="CONTINUOUS" contentDirection="LEFT_TO_RIGHT" columnSeparatorStyle="NONE" />
```

**Use `type=` syntax for list items in new tabs.** Pulled documents use `parent="kix..."` referencing a `<lists>` section, but new tabs have no existing list IDs. Use `type="bullet"` or `type="decimal"` with `level="0"` — the serde deserializer accepts both forms.

## Development

```bash
cd extradoc
uv sync --all-extras
uv run pytest tests/ -v
uv run ruff check . && uv run ruff format .
uv run mypy src/extradoc
```
