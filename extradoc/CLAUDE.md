## Overview

Python library that transforms Google Docs into an XML-based format optimized for LLM agents. Implements the pull/diff/push workflow.

Instead of working with complex API responses, agents interact with clean XML files:
- **document.xml** - Document content with semantic markup (`<h1>`, `<p>`, `<li>`, `<table>`)
- **styles.xml** - Factorized style definitions (minimal, referenced by class attribute)

## Key Files

| File | Purpose |
|------|---------|
| `src/extradoc/client.py` | `DocsClient` - main interface with `pull()`, `diff()`, `push()` methods |
| `src/extradoc/transport.py` | `Transport` ABC, `GoogleDocsTransport`, `LocalFileTransport` |
| `src/extradoc/xml_converter.py` | Converts Google Docs JSON to ExtraDoc XML format |
| `src/extradoc/desugar.py` | Transforms sugar XML back to internal representation for diffing |
| `src/extradoc/block_diff.py` | Block-level diff detection |
| `src/extradoc/diff_engine.py` | Generates batchUpdate requests from diffs |
| `src/extradoc/indexer.py` | UTF-16 index calculation and validation |
| `src/extradoc/style_factorizer.py` | Extracts and minimizes styles |
| `src/extradoc/style_hash.py` | Deterministic style ID generation |

## Documentation

- `docs/extradoc-spec.md` - Complete XML format specification
- `docs/diff-implementation-plan.md` - Diff implementation plan and status
- `docs/googledocs/` - Google Docs API reference (120+ pages)

## Key Gotchas

**UTF-16 indexes:** Google Docs uses UTF-16 code unit indexes, not character counts. Emoji and certain Unicode characters count as 2 units. The `indexer.py` module handles this.

**Separate index spaces:** Headers, footers, and footnotes each have their own index space starting at 0. The body is yet another index space.

**Syntactic sugar:** The XML uses sugar elements like `<h1>`, `<li type="bullet">` for readability. These are desugared to internal representation (`<p style="HEADING_1">`, `<p bullet="...">`) before diffing.

**HR is read-only:** Horizontal rules cannot be added or deleted via the API - only their content can be modified.

**Pristine state:** After push, always re-pull before making additional changes.

## CLI Interface

```bash
# Download a document to local folder
python -m extradoc pull <document_url_or_id> [output_dir]
# Output: ./<document_id>/ or specified output_dir

# Options:
#   --no-raw       Don't save raw API response to .raw/ folder

# Preview changes (dry run)
python -m extradoc diff <folder>
# Output: batchUpdate JSON to stdout

# Apply changes to Google Docs
python -m extradoc push <folder> [-f|--force]
# Output: Success message with number of changes applied
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
  <body class="_base">
    <h1>Heading</h1>
    <p>Paragraph text.</p>
    <li type="bullet" level="0">Bullet point</li>
    <table rows="2" cols="2">
      <tr><td><p>Cell</p></td><td><p>Cell</p></td></tr>
    </table>
  </body>
  <header id="kix.abc123" class="_base">...</header>
  <footer id="kix.def456" class="_base">...</footer>
  <footnote id="kix.fn1">...</footnote>
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

Use `LocalFileTransport` in tests:

```python
from extradoc import DocsClient
from extradoc.transport import LocalFileTransport

@pytest.fixture
def client():
    transport = LocalFileTransport(Path("tests/golden"))
    return DocsClient(transport)

@pytest.mark.asyncio
async def test_pull(client, tmp_path):
    await client.pull("document_id", tmp_path)
    assert (tmp_path / "document_id" / "document.xml").exists()
```

### Creating New Golden Files

1. Create a Google Doc with the features to test
2. Pull it: `python -m extradoc pull <url> output/`
3. Copy `.raw/document.json` to `tests/golden/<document_id>.json`
4. Verify the output looks correct
5. Commit the golden file

## Architecture Notes

### Transport-Based Design

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│ DocsClient      │────▶│ Transport        │────▶│ Google API /    │
│ (orchestration) │     │ (data fetching)  │     │ Local Files     │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

- `Transport` is an abstract base class with `get_document()`, `batch_update()`, `close()`
- `GoogleDocsTransport` - Production: makes real API calls via httpx
- `LocalFileTransport` - Testing: reads from local golden files

### Pull Flow

1. **Fetch document** - `transport.get_document()` gets full document JSON
2. **Convert to XML** - `convert_document_to_xml()` transforms to ExtraDoc format
3. **Write files** - Save `document.xml`, `styles.xml` to disk
4. **Save raw** - Optionally save `.raw/document.json`
5. **Pristine copy** - Create `.pristine/document.zip` for diff/push

## Block-Level Diff Architecture

The diff workflow uses a tree-based decomposition to ensure index stability.

### Block Types

The `block_diff.py` module parses XML into a block tree:

| Block Type | Description | Handling |
|------------|-------------|----------|
| `DOCUMENT` | Root container | Contains body, headers, footers, footnotes |
| `BODY` | Document body | Contains structural elements |
| `TAB` | Multi-tab document tab | Contains body content |
| `HEADER` | Page header | Separate index space starting at 0 |
| `FOOTER` | Page footer | Separate index space starting at 0 |
| `FOOTNOTE` | Footnote content | Separate index space starting at 0 |
| `PARAGRAPH` | Individual paragraph | Parsed individually, grouped in changes |
| `CONTENT_BLOCK` | Grouped paragraphs | Change output for consecutive same-status paragraphs |
| `TABLE` | Table element | Has recursive TABLE_CELL children |
| `TABLE_CELL` | Table cell | Contains nested content |
| `TABLE_OF_CONTENTS` | TOC element | Treated as single block |

**Key insight:** Each paragraph is parsed individually, then during diffing, consecutive paragraphs with the same change status are grouped into `CONTENT_BLOCK` changes. This allows surgical updates where only modified paragraphs are included.

### Tree-Based Resolution

```
Document
├── Body
│   ├── Paragraph (title)
│   ├── Paragraph (subtitle) → MODIFIED
│   ├── Paragraph (p1) → unchanged (acts as separator)
│   ├── Paragraph (p2) → MODIFIED
│   ├── Table
│   │   ├── TableCell (0,0)
│   │   └── TableCell (0,1)
│   └── Paragraph (p3)
├── Header (kix.hdr1)
│   └── Paragraph
└── Footer (kix.ftr1)
    └── Paragraph
```

### Block Change Detection

The `BlockDiffDetector` uses LCS-based alignment with paragraph-level granularity:

```python
from extradoc import diff_documents_block_level, format_changes

changes = diff_documents_block_level(pristine_xml, current_xml)
print(format_changes(changes))
```

Each `BlockChange` contains:
- `change_type`: ADDED, DELETED, or MODIFIED
- `block_type`: The type of block affected
- `before_xml`: Original XML (for DELETE/MODIFY)
- `after_xml`: New XML (for ADD/MODIFY)
- `container_path`: Path to container (e.g., `["body:body"]`, `["header:kix.hdr1"]`)
- `child_changes`: Nested changes (for tables)

### Paragraph-Level Granularity

Only modified paragraphs are included in changes:

```
pristine: [title, subtitle, p1, p2]
current:  [title, subtitle', p1, p2']

Result:
- ContentBlock([subtitle]) → MODIFIED (title unchanged, not included)
- ContentBlock([p2]) → MODIFIED (p1 unchanged, acts as separator)
```

### Bottom-Up Processing

**Critical:** Process changes from the END of the document toward the BEGINNING.

**Why this works:**
- Changes at higher indexes don't affect lower indexes
- If we insert 10 characters at index 50, indexes 1-49 stay the same
- If individual ContentBlock diffs are correct, overall diff is guaranteed correct

### Block vs ContentBlock Changes

| Change Type | What Changed | Generated Requests |
|-------------|--------------|-------------------|
| Table ADD | New table | `insertTable` |
| Table DELETE | Remove table | `deleteContentRange` covering entire block |
| Table Row ADD | New row | `insertTableRow` |
| Table Row DELETE | Remove row | `deleteTableRow` |
| Table Column ADD | New column | `insertTableColumn` (deduplicated) |
| Table Column DELETE | Remove column | `deleteTableColumn` (deduplicated) |
| Header ADD | New header | `createHeader` |
| Header DELETE | Remove header | `deleteHeader` |
| Footer ADD | New footer | `createFooter` |
| Footer DELETE | Remove footer | `deleteFooter` |
| Tab ADD | New tab | `addDocumentTab` |
| Tab DELETE | Remove tab | `deleteTab` |
| Footnote ADD | New footnote | `createFootnote` (at end of body) |
| Footnote DELETE | Remove footnote | `deleteContentRange` (1 char at ref position) |
| ContentBlock ADD | New paragraph sequence | `insertText` + styling (Phase 3) |
| ContentBlock DELETE | Remove paragraphs | `deleteContentRange` (Phase 3) |
| ContentBlock MODIFY | Text or formatting changed | Delete + Insert (Phase 3) |

## Current Status

**Working (Pull):**
- `pull` - Downloads document to local XML files
- Transport layer (GoogleDocsTransport + LocalFileTransport)
- XML conversion with semantic markup
- Style factorization
- Multi-tab document support
- Header/footer/footnote support (inline footnote model)
- Block-level diff detection with paragraph-level granularity (`block_diff.py`)

**Working (Structural Operations - Phase 2):**
- Table operations: `insertTable`, `insertTableRow`, `deleteTableRow`, `insertTableColumn`, `deleteTableColumn`
- Header/footer operations: `createHeader`, `deleteHeader`, `createFooter`, `deleteFooter`
- Tab operations: `addDocumentTab`, `deleteTab`
- Footnote operations: `createFootnote` (at end), `deleteContentRange` (for deletion)

**In Progress (Phase 3):**
- ContentBlock request generation for text content changes
- Precise footnote positioning (requires text content to exist first)

**Next Steps:**
1. Implement `ParsedContentBlock` extraction from XML
2. Implement `_generate_content_insert_requests()` for text/styling
3. Implement `_generate_content_delete_requests()` for deletions
4. Handle MODIFIED ContentBlocks with delete + insert strategy
5. End-to-end test with real documents

See `docs/diff-implementation-plan.md` for detailed implementation plan.
