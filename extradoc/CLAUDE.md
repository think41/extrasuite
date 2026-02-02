## Overview

Python library that transforms Google Docs into a file-based representation optimized for LLM agents. Implements the pull/diff/push workflow.

**Status:** Scaffold only - implementation pending.

## Key Files

| File | Purpose |
|------|---------|
| `src/extradoc/transport.py` | `Transport` ABC, `GoogleDocsTransport`, `LocalFileTransport` |
| `src/extradoc/client.py` | `DocsClient` - main interface with `pull()`, `diff()`, `push()` methods |
| `src/extradoc/__main__.py` | CLI entry point for pull/diff/push commands |

## CLI Interface

```bash
# Download a document to local folder
python -m extradoc pull <document_url_or_id> [output_dir]
# Output: ./<document_id>/ or specified output_dir

# Options:
#   --no-raw       Don't save raw API responses to .raw/ folder

# Preview changes (dry run)
python -m extradoc diff <folder>
# Output: batchUpdate JSON to stdout

# Apply changes to Google Docs
python -m extradoc push <folder>
# Output: Success message with number of changes applied

# Options:
#   -f, --force    Push despite warnings (blocks still prevent push)
```

Also works via `uvx extradoc pull/diff/push`.

## Folder Structure

After `pull`, the folder will contain:
```
<document_id>/
  document.json           # Document metadata and content structure
  content/                # Document content in LLM-friendly format (TBD)
  .raw/
    document.json         # Raw API response
  .pristine/
    document.zip          # Original state for diff comparison
```

## Development

```bash
cd extradoc
uv sync --all-extras
uv run pytest tests/ -v
uv run ruff check . && uv run ruff format .
uv run mypy src/extradoc
```

## Testing

Tests are in `tests/` and will include:
- `test_pull_integration.py` - End-to-end pull tests using golden files
- `test_transport.py` - Transport layer unit tests

### Golden File Testing

Golden files enable testing without mocking or making real API calls:

```
tests/golden/
  <document_id>/
    document.json    # Raw API response
```

Use `LocalFileTransport` in tests:

```python
from extradoc import DocsClient, LocalFileTransport

@pytest.fixture
def client():
    transport = LocalFileTransport(Path("tests/golden"))
    return DocsClient(transport)

@pytest.mark.asyncio
async def test_pull(client, tmp_path):
    files = await client.pull("basic_document", tmp_path)
    assert (tmp_path / "basic_document" / "document.json").exists()
```

### Creating New Golden Files

1. Create a Google Docs file with the features to test
2. Pull it: `python -m extradoc pull <url>` (raw files saved by default)
3. Copy `.raw/document.json` to `tests/golden/<name>/document.json`
4. Verify the output looks correct
5. Commit the golden files

## Architecture Notes

### Transport-Based Design

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│ DocsClient      │────▶│ Transport        │────▶│ Google API /    │
│ (orchestration) │     │ (data fetching)  │     │ Local Files     │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

- `Transport` is an abstract base class with `get_document()`, `batch_update()`, `close()`
- `GoogleDocsTransport` - Production: makes real API calls via `httpx`
- `LocalFileTransport` - Testing: reads from local golden files
- Access token is a transport concern, not a client concern

### Pull Flow (To Be Implemented)

1. **Document fetch** - `transport.get_document()` gets full document structure
2. **Transform** - Convert API response to file format
3. **Write** - Write files to disk
4. **Save raw** - Optionally save `.raw/document.json`
5. **Pristine copy** - Create `.pristine/document.zip` for diff/push

### Diff/Push Flow (To Be Implemented)

1. **Extract pristine** - Extract `.pristine/document.zip`
2. **Read current** - Read edited files from disk
3. **Diff** - Compare and generate batchUpdate requests
4. **Validate** - Check for blocking issues
5. **Push** - Send batchUpdate via transport

### Dependencies

- `httpx` - Async HTTP client for API calls
- `certifi` - SSL certificates
- `extrasuite` - Authentication via `extrasuite.client.CredentialsManager`

## Implementation TODO

1. Design on-disk file format for Google Docs content
2. Implement document transformer (API response → file format)
3. Implement file writer
4. Implement diff engine
5. Implement request generator (file changes → batchUpdate requests)
6. Add validation for structural changes
