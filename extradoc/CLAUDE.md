## Overview

Python library that transforms Google Docs into a file-based representation optimized for LLM agents. Implements the pull/diff/push workflow using clean HTML format with custom elements for Google Docs concepts.

**Status:** Core pull/diff/push workflow implemented. Diff algorithm is placeholder (returns empty requests).

## Key Files

| File | Purpose |
|------|---------|
| `src/extradoc/transport.py` | `Transport` ABC, `GoogleDocsTransport`, `LocalFileTransport` |
| `src/extradoc/client.py` | `DocsClient` - main interface with `pull()`, `diff()`, `push()` methods |
| `src/extradoc/indexer.py` | UTF-16 index calculation and validation |
| `src/extradoc/html_converter.py` | Convert Google Docs JSON → HTML |
| `src/extradoc/html_parser.py` | Parse HTML → structured form, generate batchUpdate requests |
| `src/extradoc/__main__.py` | CLI entry point for pull/diff/push commands |

## Documentation

- `docs/html-format-design.md` - Complete HTML format specification, including custom elements, multi-tab support, headers/footers, and diff algorithm

## CLI Interface

```bash
# Download a document to local folder
python -m extradoc pull <document_url_or_id> [output_dir]
# Output: ./<document_id>/ or specified output_dir

# Preview changes (dry run)
python -m extradoc diff <folder>
# Output: batchUpdate JSON to stdout

# Apply changes to Google Docs
python -m extradoc push <folder>
# Output: Success message with number of changes applied
```

Also works via `uvx extradoc pull/diff/push`.

## Folder Structure

After `pull`, the folder will contain:
```
<document_id>/
  document.html           # Main document content (all tabs, with embedded metadata)
  styles.json             # Extracted styles (fonts, colors, spacing)
  .raw/
    document.json         # Raw API response
  .pristine/
    document.zip          # Original state for diff comparison
```

Note: No separate `metadata.json` - document metadata is embedded in the HTML `<head>` as JSON.

## HTML Format

### Custom Elements (Atomic)

Google Docs-specific concepts use custom self-closing elements to keep them atomic:

| Google Docs | Custom Element | Index Cost |
|-------------|----------------|------------|
| HorizontalRule | `<hr/>` | 1 |
| PageBreak | `<PageBreak/>` | 1 |
| FootnoteReference | `<FootnoteRef id="..." num="..."/>` | 1 |
| Person | `<Person email="..." name="..."/>` | 1 |
| Image | `<Image src="..." width="..." height="..."/>` | 1 |
| RichLink | `<RichLink url="..." title="..."/>` | 1 |
| Date | `<Date/>` | 1 |
| AutoText | `<AutoText type="..."/>` | variable |

### Structural Elements

| Google Docs | HTML |
|-------------|------|
| Tab | `<article id="..." data-title="...">` |
| Header | `<Header id="...">` |
| Footer | `<Footer id="...">` |
| Footnote | `<Footnote id="...">` |
| Body | `<main>` |
| TOC | `<nav>` |

### Standard HTML Elements

| Google Docs | HTML |
|-------------|------|
| TITLE | `<h1 class="title">` |
| SUBTITLE | `<p class="subtitle">` |
| HEADING_1 | `<h1 id="...">` |
| HEADING_2-6 | `<h2 id="...">`-`<h6 id="...">` |
| NORMAL_TEXT | `<p>` |
| Bulleted list | `<ul class="bullet"><li>` |
| Numbered list | `<ol class="decimal|alpha|roman"><li>` |
| Checkbox list | `<ul class="checkbox"><li>` |
| Table | `<table>` |
| Bold | `<strong>` |
| Italic | `<em>` |
| Link | `<a>` |

See `docs/html-format-design.md` for complete specification.

## Key Design Decisions

1. **Custom elements for atomic items**: `<PageBreak/>`, `<Person/>` etc. are self-closing to prevent LLMs from breaking them
2. **Standard HTML where possible**: `<hr/>` instead of custom element, `<article>` instead of `<Tab>`
3. **Embedded metadata**: Document metadata in `<script type="application/json">` in `<head>`
4. **Heading IDs preserved**: For internal links to work correctly
5. **Multi-tab support**: Use `<article id="..." data-title="...">` for each tab
6. **List types via class**: `<ul class="bullet">`, `<ol class="decimal">`, etc. for round-trip parity
7. **Separate index spaces**: Headers, footers, and footnotes each have their own index space starting at 0

## Index Calculation

Google Docs uses UTF-16 code units for indexing. Key functions:

```python
from extradoc import utf16_len, validate_document

# Calculate UTF-16 length
length = utf16_len("Hello 😀")  # Returns 8 (6 + 2 for emoji)

# Validate document indexes
result = validate_document(document_json)
assert result.is_valid
```

The core insight: **indexes can be derived from document structure without explicit tracking**.

## Development

```bash
cd extradoc
uv sync --all-extras
uv run pytest tests/ -v
uv run ruff check . && uv run ruff format .
uv run mypy src/extradoc
```

## Testing

Tests are in `tests/`:
- `test_indexer.py` - Index calculation (14 tests passing)
- `test_transport.py` - Transport layer (3 tests passing)
- `test_pull_integration.py` - Pull/diff/push integration tests (5 tests passing)

### Golden File Testing

Golden files enable testing without API calls:

```
tests/golden/
  1tlHGpgjoibP0eVXRvCGSmkqrLATrXYTo7dUnmV7x01o.json  # R41 AI Support Agent
  1arcBS-A_LqbvrstLAADAjCZj4kvTlqmQ0ztFNfyAEyc.json  # Sri-Document-Edit-Testing
```

Use `LocalFileTransport` in tests:

```python
from extradoc import DocsClient, LocalFileTransport

@pytest.fixture
def client():
    transport = LocalFileTransport(Path("tests/golden"))
    return DocsClient(transport)
```

## Implementation Status

### Completed
- [x] Project structure and configuration
- [x] Transport layer (GoogleDocsTransport + LocalFileTransport)
- [x] Index validation engine (indexer.py)
- [x] HTML conversion with custom elements
- [x] Multi-tab support
- [x] Header/footer/footnote support
- [x] Table support with colspan/rowspan
- [x] Format design document
- [x] Golden file testing infrastructure
- [x] DocsClient.pull() implementation
- [x] DocsClient.diff() implementation (framework in place)
- [x] DocsClient.push() implementation
- [x] CLI entry point (pull/diff/push commands)

### Pending
- [ ] Diff algorithm (diff_documents returns empty requests currently)
- [ ] Style extraction to styles.json
- [ ] Table merge/unmerge operations
- [ ] Image insertion support
