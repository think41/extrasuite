## Overview

Python library that transforms Google Docs into an XML-based format optimized for LLM agents. Implements the pull/diff/push workflow.

Instead of working with complex API responses, agents interact with clean XML files:
- **document.xml** - Document content with semantic markup (`<h1>`, `<p>`, `<li>`, `<table>`)
- **styles.xml** - Factorized style definitions (minimal, referenced by class attribute)

## Key Files

| File | Purpose |
|------|---------|
| `src/extradoc/__main__.py` | CLI entry point with `pull`, `diff`, `push` commands |
| `src/extradoc/transport.py` | `Transport` ABC, `GoogleDocsTransport`, `LocalFileTransport` |
| `src/extradoc/xml_converter.py` | Converts Google Docs JSON to ExtraDoc XML format |
| `src/extradoc/desugar.py` | Transforms sugar XML back to internal representation for diffing |
| `src/extradoc/indexer.py` | UTF-16 code unit length calculation |
| `src/extradoc/style_factorizer.py` | Extracts and minimizes styles |
| `src/extradoc/style_hash.py` | Deterministic style ID generation |
| `src/extradoc/style_converter.py` | Declarative style property mappings |
| `src/extradoc/engine.py` | Top-level diff pipeline orchestrator |
| `src/extradoc/parser.py` | Parses XML into typed `DocumentBlock` tree |
| `src/extradoc/block_indexer.py` | UTF-16 index calculator for block trees |
| `src/extradoc/aligner.py` | Block alignment for tree diffing |
| `src/extradoc/differ.py` | Tree differ producing `ChangeNode` tree |
| `src/extradoc/walker.py` | Walks change tree to emit `batchUpdate` requests |
| `src/extradoc/push.py` | Push orchestration (3-batch strategy) |
| `src/extradoc/generators/` | Request generators (content, structural, table) |
| `src/extradoc/request_generators/structural.py` | Structural request utilities (footnote/header/footer ID handling) |
| `src/extradoc/request_generators/table.py` | Table row/column insert/delete request generation |

## Documentation

- `docs/extradoc-spec.md` - Complete XML format specification
- `docs/extradoc-diff-specification.md` - Diff specification
- `docs/gaps.md` - Known bugs and limitations
- `docs/googledocs/` - Google Docs API reference (120+ pages) - **use this instead of web fetching**
  - `docs/googledocs/api/` - Individual API request/response types (CreateParagraphBulletsRequest, etc.)
  - `docs/googledocs/lists.md` - Working with bullet/numbered lists
  - `docs/googledocs/rules-behavior.md` - Index behavior rules for batchUpdate

## Key Gotchas

**UTF-16 indexes:** Google Docs uses UTF-16 code unit indexes, not character counts. Emoji and certain Unicode characters count as 2 units. The `indexer.py` module handles this.

**Separate index spaces:** Headers, footers, and footnotes each have their own index space starting at 0. The body is yet another index space.

**Syntactic sugar:** The XML uses sugar elements like `<h1>`, `<li type="bullet">` for readability. These are desugared to internal representation (`<p style="HEADING_1">`, `<p bullet="...">`) before diffing.

**HR is read-only:** Horizontal rules cannot be added or deleted via the API - only their content can be modified.

**Segment-end newline:** Google Docs API forbids deleting the final newline of a segment (body, header, footer, footnote, table cell). When deleting content at segment end, the delete range must exclude the final newline, and insert operations should not include a trailing newline.

**Pristine state:** After push, always re-pull before making additional changes.

## CLI Interface

```bash
# Download a document to local folder
uv run python -m extradoc pull <document_url_or_id> [output_dir]
# Output: ./<document_id>/ or specified output_dir

# Options:
#   --no-raw       Don't save raw API response to .raw/ folder

# Preview changes (dry run)
uv run python -m extradoc diff <folder>

# Apply changes to Google Docs
uv run python -m extradoc push <folder> [-f|--force] [--verify]
```

Also works via `uvx extradoc pull/diff/push`.

## Folder Structure

After `pull`, the folder contains:
```
<document_id>/
  document.xml          # ExtraDoc XML (main content)
  styles.xml            # Factorized style definitions
  .raw/
    document.json       # Raw Google Docs API response
  .pristine/
    document.zip        # Original state for diff comparison
```

**document.xml structure:**
```xml
<?xml version="1.0" encoding="UTF-8"?>
<doc id="DOCUMENT_ID" revision="REVISION_ID">
  <meta>
    <title>Document Title</title>
  </meta>
  <tab id="t.0" title="Tab 1" class="_base">
    <body>
      <h1>Heading</h1>
      <p>Paragraph text.</p>
      <li type="bullet" level="0">Bullet point</li>
      <table rows="2" cols="2">
        <tr><td><p>Cell</p></td><td><p>Cell</p></td></tr>
      </table>
    </body>
    <header id="kix.abc123" class="_base">...</header>
    <footer id="kix.def456" class="_base">...</footer>
  </tab>
</doc>
```

The agent edits files in place. `diff` and `push` compare against `.pristine/` to determine changes.

## Development

```bash
cd extradoc
uv sync --all-extras
uv run pytest tests/ -v
uv run ruff check . && uv run ruff format .
uv run mypy src/extradoc
```

## Testing

Tests are end-to-end and work against real Google Docs. Always pull to the `extradoc/output/` directory (gitignored).

**Test workflow:**
1. **Pull** the document to `output/`
2. **Edit** the XML files
3. **Diff** to preview changes - save diff output in same folder for debugging
4. **Push** to apply changes
5. **Pull again** to confirm changes were applied correctly

If push fails or subsequent pull doesn't match expectations, the saved diff helps debug.

### Golden File Testing

Golden files store raw API responses for reproducible testing:

```
tests/golden/
  <document_id>.json    # Raw Google Docs API response
```

### Creating New Golden Files

1. Create a Google Doc with the features to test
2. Pull it: `uv run python -m extradoc pull <url> output/`
3. Copy `.raw/document.json` to `tests/golden/<document_id>.json`
4. Verify the output looks correct
5. Commit the golden file

## Architecture Notes

### Transport-Based Design

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│ __main__.py     │────▶│ Transport        │────▶│ Google API /    │
│ (CLI + pull)    │     │ (data fetching)  │     │ Local Files     │
├─────────────────┤     └──────────────────┘     └─────────────────┘
│ PushClient      │
│ (diff + push)   │
└─────────────────┘
```

- `Transport` is an abstract base class with `get_document()`, `batch_update()`, `close()`
- `GoogleDocsTransport` - Production: makes real API calls via httpx

### Pull Flow

1. **Fetch document** - `transport.get_document()` gets full document JSON
2. **Convert to XML** - `convert_document_to_xml()` transforms to ExtraDoc format
3. **Write files** - Save `document.xml`, `styles.xml` to disk
4. **Save raw** - Optionally save `.raw/document.json`
5. **Pristine copy** - Create `.pristine/document.zip` for diff/push

### Diff/Push Flow

1. **Parse** - `parser.py` builds `DocumentBlock` trees from pristine and current XML
2. **Diff** - `differ.py` `TreeDiffer` compares trees, producing a `ChangeNode` tree
3. **Generate** - `walker.py` walks the change tree to emit `batchUpdate` requests
4. **Push** - `push.py` `PushClient` orchestrates the 3-batch strategy:
   - Batch 1: createHeader/createFooter → capture real IDs
   - Batch 2: Main body + createFootnote → capture real footnote IDs
   - Batch 3: Footnote content requests (with rewritten segment IDs)

## Current Status

**Working (Pull):**
- `pull` - Downloads document to local XML files
- Transport layer (GoogleDocsTransport + LocalFileTransport)
- XML conversion with semantic markup
- Style factorization
- Multi-tab document support
- Header/footer/footnote support (inline footnote model)

**Working (Push):**
- Table operations: `insertTable` with cell content, `insertTableRow`, `deleteTableRow`, `insertTableColumn`, `deleteTableColumn`
- Header/footer operations: `createHeader`, `deleteHeader`, `createFooter`, `deleteFooter`
- Tab operations: `addDocumentTab`, `deleteTab`
- Footnote operations: `createFootnote` (at end), `deleteContentRange` (for deletion)
- ContentBlock operations: `insertText`, `updateTextStyle`, `updateParagraphStyle`, `createParagraphBullets`
- Text formatting: bold, italic, underline, strikethrough, superscript, subscript, links
- Paragraph styles: headings (h1-h6), title, subtitle
- List types: bullet, decimal, alpha, roman

**Known Issues:** See `docs/gaps.md` for current bugs and limitations.
