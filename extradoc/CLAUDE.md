## Overview

Python library that transforms Google Docs into an XML-based format optimized for LLM agents. Implements the pull/diff/push workflow. Agents interact with `document.xml` (semantic markup: `<h1>`, `<p>`, `<li>`, `<table>`) and `styles.xml` (factorized style definitions) instead of the verbose Google Docs API JSON.

Agent-facing skills that explain the XML format and editing workflow are in `server/skills/extradoc/`.

## Two Implementations (Migration In Progress)

There are currently two implementations of the pull/diff/push workflow:

### Legacy (current `client.py` pipeline)

The production code path used by `DocsClient.pull()`, `diff()`, `push()`. Operates on raw JSON dicts and XML strings directly.

### New (serde + reconcile)

A cleaner architecture being developed to replace the legacy pipeline. Uses typed Pydantic models (`Document`) throughout instead of raw dicts, and separates concerns into two packages:

- **`serde`** — Bidirectional `Document ↔ XML folder` conversion via typed intermediate models
- **`reconcile`** — Diffs two `Document` objects to produce `BatchUpdateDocumentRequest` batches

The new pipeline flow:

```
pull:  API → Document → serde.serialize() → folder (XMLs + pristine.zip)
edit:  agent modifies XML files
diff:  pristine XML → serde.deserialize() → base Document
       edited XML   → serde.deserialize() → desired Document
       reconcile(base, desired) → list[BatchUpdateDocumentRequest]
push:  sequentially execute each BatchUpdateDocumentRequest
```

The `client.py` orchestrator has NOT been updated to use serde + reconcile yet. The packages are tested independently and will be integrated once they reach full parity with the legacy pipeline.

## Key Files

### Legacy pipeline

| File | Purpose |
|------|---------|
| `src/extradoc/client.py` | `DocsClient` with `pull()`, `diff()`, `push()` — main orchestrator (uses legacy pipeline) |
| `src/extradoc/transport.py` | `Transport` ABC (`get_document`, `batch_update`, `list_comments`), `GoogleDocsTransport`, `LocalFileTransport` |
| `src/extradoc/xml_converter.py` | `convert_document_to_xml(raw_doc, comments)` → `(document_xml, styles_xml)` |
| `src/extradoc/desugar.py` | Sugar XML (`<h1>`, `<li>`) → internal representation (`<p style="HEADING_1">`, `<p bullet="...">`) |
| `src/extradoc/engine.py` | `DiffEngine.diff(pristine_xml, current_xml)` → `(requests, change_tree)` |
| `src/extradoc/parser.py` | `BlockParser.parse(xml)` → `DocumentBlock` tree (`Tab` → `Segment` → `Paragraph`/`Table`) |
| `src/extradoc/block_indexer.py` | Computes UTF-16 code unit indices on the block tree |
| `src/extradoc/differ.py` | `TreeDiffer.diff(pristine, current)` → `ChangeNode` tree with `ADDED`/`DELETED`/`MODIFIED` ops |
| `src/extradoc/walker.py` | `RequestWalker.walk(change_tree)` → `list[dict]` of `batchUpdate` requests (processes segments backwards by index) |
| `src/extradoc/push.py` | 3-batch push strategy with placeholder→real ID rewriting for headers/footers/footnotes/tabs |
| `src/extradoc/generators/` | Request generators: `ContentGenerator`, `TableGenerator`, `StructuralGenerator` |
| `src/extradoc/indexer.py` | UTF-16 code unit length calculation (emoji = 2 units) |
| `src/extradoc/style_factorizer.py` | Extracts inline styles into shared classes |

### New pipeline (serde + reconcile)

| File | Purpose |
|------|---------|
| `src/extradoc/serde/` | `Document ↔ XML folder` conversion. See `serde/CLAUDE.md` for details |
| `src/extradoc/reconcile/` | Diffs two `Document` objects → `list[BatchUpdateDocumentRequest]` |
| `src/extradoc/reconcile/_core.py` | `reconcile()`, `verify()`, `reindex_document()`, `resolve_deferred_ids()` |
| `src/extradoc/reconcile/_alignment.py` | LCS-based structural element alignment between base and desired |
| `src/extradoc/reconcile/_generators.py` | Generates individual `batchUpdate` requests from aligned diffs |
| `src/extradoc/reconcile/_comparators.py` | `documents_match()` — deep comparison for verification |
| `src/extradoc/reconcile/_extractors.py` | Extracts text, styles, and structure from Document elements |
| `src/extradoc/reconcile/_exceptions.py` | `ReconcileError` for unsupported edit patterns |
| `src/extradoc/api_types/` | Pydantic models generated from Google Docs API schema |

## Documentation

- `docs/extradoc-spec.md` - XML format specification
- `docs/extradoc-diff-specification.md` - Diff specification
- `docs/gaps.md` - Known bugs and limitations (legacy pipeline)
- `docs/reconciliation-gaps.md` - Known gaps in the reconcile module
- `docs/googledocs/` - Google Docs API reference (120+ pages) — **use this instead of web fetching**
  - `docs/googledocs/api/` - Individual API request/response types
  - `docs/googledocs/rules-behavior.md` - Index behavior rules for batchUpdate

## Legacy Pull Data Flow

`DocsClient.pull()` fetches the document via `Transport.get_document()` → raw JSON dict, then `Transport.list_comments()` → comment list. These feed into `convert_document_to_xml(raw, comments)` which walks the nested Google Docs JSON structure (tabs → body/headers/footers → paragraphs → text runs), converts paragraphs to sugar elements (`<h1>`, `<li type="bullet">`), factorizes inline styles into `styles.xml` classes via `style_factorizer.py`, and positions comment anchors using offset/length or `quotedFileContent` search. The output `document.xml` + `styles.xml` are written to disk alongside `.pristine/document.zip` (the baseline for future diffs) and optionally `.raw/document.json`.

## Legacy Diff + Push Data Flow

`DocsClient.diff()` loads current `document.xml` and pristine XML from `.pristine/document.zip`, then delegates to `DiffEngine.diff()`. The engine pipeline: `BlockParser.parse()` builds typed `DocumentBlock` trees from both XMLs, `BlockIndexer` computes UTF-16 indices on the pristine tree, `TreeDiffer.diff()` aligns blocks via `BlockAligner` and produces a `ChangeNode` tree (each node tagged `ADDED`/`DELETED`/`MODIFIED`/`UNCHANGED`), and `RequestWalker.walk()` traverses the change tree backwards by index (highest first, as required by the Google Docs API) delegating to `ContentGenerator`, `TableGenerator`, and `StructuralGenerator` to emit `batchUpdate` request dicts. `DocsClient.push()` then classifies these requests and executes them in 3 batches: (1) tab/header/footer creation → capture real IDs, (2) main content + footnote creation → capture footnote IDs, (3) footnote content with rewritten segment IDs. Placeholder IDs used in XML are mapped to real API-assigned IDs between batches.

## Debugging

When push produces unexpected results, run `diff` first and save its output for inspection — it shows the exact `batchUpdate` requests that will be sent. Compare the pristine XML (unzip `.pristine/document.zip`) against the current `document.xml` to verify the edit is what you intended. After push, re-pull and diff the before/after XMLs to confirm the API applied changes correctly. For index-related bugs, check UTF-16 code unit calculations in `indexer.py` — emoji and surrogate pairs are the usual culprits. Headers, footers, footnotes, and table cells each have independent index spaces starting at 0.

## Mock API

The `src/extradoc/mock/` package provides a pure-function mock of the Google Docs `batchUpdate` API for testing. Handlers modify document structure only; after each request, `reindex_and_normalize_all_tabs()` recomputes all UTF-16 indices from actual text content. The mock tracks style provenance via an `__explicit__` metadata key to replicate the real API's inherited-vs-explicit style behavior. Currently passes 61/61 test scenarios against the real API.

## Key Gotchas

- **UTF-16 indexes:** Google Docs uses UTF-16 code unit indexes, not character counts. `indexer.py` handles this.
- **Separate index spaces:** Headers, footers, footnotes, and table cells each have their own index space starting at 0.
- **Syntactic sugar:** `<h1>`, `<li>` are desugared to `<p style="HEADING_1">`, `<p bullet="...">` before diffing.
- **Segment-end newline:** The API forbids deleting the final `\n` of any segment. Delete ranges must exclude it; inserts must not include trailing `\n`.
- **Pristine state:** After push, always re-pull before making additional changes.

## Development

```bash
cd extradoc
uv sync --all-extras
uv run pytest tests/ -v
uv run ruff check . && uv run ruff format .
uv run mypy src/extradoc
```

## Testing

Golden files in `tests/golden/<document_id>.json` store raw API responses for reproducible pull testing. End-to-end tests work against real Google Docs — always pull to `extradoc/output/` (gitignored).

Serde and reconcile have their own test suites:
- `tests/test_serde.py` — round-trip tests for Document ↔ XML conversion
- `tests/test_reconcile.py` — reconciliation tests for Document → BatchUpdateDocumentRequest generation
