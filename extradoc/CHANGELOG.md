# Changelog

All notable changes to the extradoc library will be documented in this file.

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
