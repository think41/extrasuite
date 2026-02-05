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
| `src/extradoc/diff_engine.py` | Generates batchUpdate requests from XML differences |
| `src/extradoc/indexer.py` | UTF-16 index calculation and validation |
| `src/extradoc/style_factorizer.py` | Extracts and minimizes styles |
| `src/extradoc/style_hash.py` | Deterministic style ID generation |

## Documentation

- `docs/extradoc-spec.md` - Complete XML format specification
- `docs/implementation-gap.md` - Gap analysis and implementation roadmap
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

## Diff/Push Workflow

The diff workflow operates as a tree, processing from bottom to top to preserve indexes.

### Tree-Based Resolution

1. **Resolve top-level components** - Identify changes at body/header/footer/footnote level
2. **Localize changes** - Within each component, identify changed ContentBlocks
3. **Resolve ContentBlocks** - For each block:
   - First use InsertText/DeleteText/ReplaceText to match text content
   - Then update formatting (styles, lists, textruns) on specific ranges within that block

### Bottom-Up Processing

Process changes from the end of the document toward the beginning. This ensures:
- Earlier indexes remain stable as we make changes
- If individual ContentBlock diffs are correct, the overall diff is guaranteed correct

### Block vs ContentBlock Changes

| Change Type | Operation |
|-------------|-----------|
| Block changes (table, row, cell, tab, header, footer, footnote) | Insert or delete entire block |
| ContentBlock edits | Complete insert, complete delete, or incremental edits |
| Incremental edits | Text operations first, then style/formatting updates |

### Request Generation

For each ContentBlock edit:
1. Calculate text diff → InsertTextRequest / DeleteContentRangeRequest
2. Calculate style diff → UpdateTextStyleRequest / UpdateParagraphStyleRequest
3. Calculate list diff → CreateParagraphBulletsRequest / DeleteParagraphBulletsRequest
4. Order requests: deletions before insertions, bottom-up by index

## Current Status

**Working:**
- `pull` - Downloads document to local XML files
- Transport layer (GoogleDocsTransport + LocalFileTransport)
- XML conversion with semantic markup
- Style factorization
- Multi-tab document support
- Header/footer/footnote support

**In Progress:**
- `diff` - Framework exists, tree-based algorithm being implemented
- `push` - Framework exists, depends on diff completion

See branch `claude/refactor-diff-detection-Rh2ku` for current diff implementation work.
