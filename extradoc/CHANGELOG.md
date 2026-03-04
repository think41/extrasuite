# Changelog

All notable changes to the extradoc library will be documented in this file.

## [0.4.0] - 2026-03-04

### Added

- **Serde module** (`src/extradoc/serde/`) — bidirectional `Document ↔ XML folder` conversion replacing the legacy xml_converter pipeline. Supports text styles, paragraph styles, table cells, lists (bullet/decimal/alpha/roman), inline objects, comments, soft line breaks, and page breaks.
- **Reconcile module** (`src/extradoc/reconcile/`) — diffs two `Document` objects and produces `list[BatchUpdateDocumentRequest]`. Covers text insertion/deletion, paragraph and text style reconciliation, table row/column operations, multi-segment (header/footer) support, multi-tab support, bullet list creation/deletion, and `DeferredID` resolution for multi-batch pushes.
- **`updateTableCellStyle`** support in both reconcile and mock.
- **`insertPageBreak`** — `<pagebreak/>` element in XML round-trips through serde and generates the correct API request.
- **New-tab authoring** — reconcile handles tabs created from scratch (no pull required), with correct handling of the synthetic initial body segment.
- **Named style default suppression** in serde — text/paragraph style attributes implied by the paragraph's named style (e.g. bold on HEADING_1) are omitted from XML output and restored on deserialize.
- **List-level indent suppression** in serde — paragraph indent attributes duplicating the list-level definition are omitted.
- **Multi-batch reconciliation with DeferredID** — when creating new tabs or segments, IDs are unknown until the first batch executes; `DeferredID` placeholders are resolved via `resolve_deferred_ids()` before each subsequent batch.
- **Style provenance tracking** (`__explicit__` key) in the mock — replicates the real API's inherited-vs-explicit style behavior for `updateTextStyle`, heading clearing, link-style stripping, and `createParagraphBullets`.
- Golden file tests for serde round-trips and reconcile scenarios.

### Changed

- Legacy pipeline files (`xml_converter.py`, `engine.py`, `parser.py`, `differ.py`, `walker.py`, `push.py`, `generators/`, `desugar.py`, `block_indexer.py`, `indexer.py`, `style_factorizer.py`) removed — 23 source files and 15 orphaned tests deleted.
- `DocsClient` (`client.py`) migrated to the serde + reconcile pipeline.
- Mock API fidelity: 393 tests passing.

### Fixed

- New-tab heading bug: spurious `updateParagraphStyle` no longer overwrites `HEADING_1` style when creating a new tab.
- List type handling: `bullet`, `decimal`, `alpha`, `roman` list types now correctly round-trip via serde.
- Mixed `<t>` content, `<a>` inside `<t>`, and plain-text `<a href>` parsed correctly (BUG-5/6/10).
- Table diff: content updates emitted before column structural operations.
- Explicit `<p/>` after tables and other slot-ordering bugs in reconcile.
- Default headers/footers handled correctly in multi-tab reconcile.
- `headingId` excluded from `updateParagraphStyle` requests.
- Consecutive added list items batched into a single `createParagraphBullets` call.

## [0.3.0] - 2026-02-18

### Added

- **Paragraph styling reconciliation** in pull/push pipeline — paragraph styles (alignment, spacing, indentation) are now correctly preserved through the pull→edit→push cycle
- **Typed Pydantic models** generated from the Google Docs API discovery document, replacing untyped dicts in the request/response layer
- **Mock API package** (`src/extradoc/mock/`) — a pure-Python mock of the Google Docs `batchUpdate` API for testing, refactored from a monolithic file into 13 focused modules with centralized `reindex_and_normalize_all_tabs()`
- **Style provenance tracking** in the mock via `__explicit__` metadata key, replicating the real API's inherited-vs-explicit style behavior
- `pydantic>=2.0` added as a dependency

### Changed

- Mock API fidelity improved to 61/61 test scenarios passing against the real API

## [0.2.2] - 2026-02-12

### Added

- Inline `<comment-ref>` tags for Google Docs comments
- `comments.xml` added to SKILL.md directory listing

### Fixed

- Comment-ref bugs: mark new comments as unsupported
- Clean up dead code in comment handling

## [0.2.0] - 2026-02-11

### Breaking Changes

- Removed CLI entry point (`python -m extradoc`). Use `extrasuite doc pull/diff/push` instead.
- Removed dependency on `extrasuite` (client) package.

### Added

- `DocsClient` class for programmatic pull/diff/push.
- `LocalFileTransport` in `transport.py`.
- Expanded `__init__.py` exports (`DocsClient`, `PushResult`, all transport types).

## [0.1.0] - 2026-02-11

### Added

- Initial release
- **Pull**: Download Google Docs to a local folder with LLM-friendly XML format
  - `document.xml` - Semantic markup (`<h1>`, `<p>`, `<li>`, `<table>`, etc.)
  - `styles.xml` - Factorized style definitions
  - `.pristine/` snapshot for diff comparison
  - Multi-tab document support
- **Diff**: Compare edited XML against pristine state and generate `batchUpdate` JSON
- **Push**: Apply changes to Google Docs via the API with `--force` and `--verify` options
- **Supported operations**:
  - Text insertion, deletion, and modification
  - Text formatting: bold, italic, underline, strikethrough, superscript, subscript, links
  - Paragraph styles: headings (h1-h6), title, subtitle
  - List types: bullet, decimal, alpha, roman
  - Table operations: insert table with content, insert/delete rows, insert/delete columns
  - Header and footer: create and delete
  - Tab operations: add and delete document tabs
  - Footnote operations: create and delete
  - Person mentions via insertPerson API
  - Date/time field support
- **3-batch push strategy**: Handles header/footer creation, main body changes, and footnote content in separate batches for correct ID resolution
- **Syntactic sugar**: Human-readable elements (`<h1>`, `<li type="bullet">`) automatically desugared for diffing
- **UTF-16 index handling**: Correct index calculation for emoji and multi-byte characters
- Async transport-based architecture with `GoogleDocsTransport` and `LocalFileTransport` for testing
- Golden file testing infrastructure
