## Overview

Python library that transforms Google Sheets into a file-based representation optimized for LLM agents. Implements the pull/diff/push workflow.

Instead of working with complex API responses, agents interact with simple files:
- **data.tsv** - Cell values in tab-separated format (formulas show computed values)
- **formula.json** - Sparse dictionary mapping cell coordinates to formulas (with compression)
- **format.json** - Cell formatting definitions (with compression)
- **feature.json** - Advanced features (charts, pivot tables, filters, etc.)

## Key Files

| File | Purpose |
|------|---------|
| `src/extrasheet/transport.py` | `Transport` ABC, `GoogleSheetsTransport`, `LocalFileTransport` |
| `src/extrasheet/client.py` | `SheetsClient` - main interface with single `pull()` method |
| `src/extrasheet/transformer.py` | Transforms API response to on-disk format |
| `src/extrasheet/writer.py` | Writes transformed data to files |
| `src/extrasheet/formula_compression.py` | Compresses formulas with relative references |
| `src/extrasheet/format_compression.py` | Compresses cell formatting |
| `src/extrasheet/credentials.py` | `CredentialsManager` for OAuth token handling |
| `src/extrasheet/api_types.py` | TypedDict definitions for Google Sheets API |
| `src/extrasheet/utils.py` | A1 notation parsing utilities |

## Documentation

- `docs/on-disk-format.md` - Complete specification of the file format
- `docs/llm-agent-guide.md` - How to use extrasheet output for spreadsheet modifications

## CLI Interface

```bash
# Download a spreadsheet to local folder
python -m extrasheet pull <spreadsheet_url_or_id> [output_dir]
# Output: ./<spreadsheet_id>/ or specified output_dir

# Options:
#   --max-rows N   Maximum rows per sheet (default: 100)
#   --no-limit     Fetch all rows (may timeout on large spreadsheets)
#   --no-raw       Don't save raw API responses to .raw/ folder

# Preview changes (dry run) - NOT YET IMPLEMENTED
python -m extrasheet diff <folder>
# Output: batchUpdate JSON to stdout

# Apply changes to Google Sheets - NOT YET IMPLEMENTED
python -m extrasheet push <folder>
# Output: API response
```

Also works via `uvx extrasheet pull/diff/push`.

## Folder Structure

After `pull`, the folder contains:
```
<spreadsheet_id>/
  spreadsheet.json        # Metadata (title, sheets list, etc.)
  <sheet_name>/
    data.tsv              # Cell values
    formula.json          # Formulas (compressed)
    format.json           # Formatting (compressed)
    feature.json          # Charts, pivot tables, etc.
  .raw/
    metadata.json         # Raw metadata API response
    data.json             # Raw data API response (with grid data)
  .pristine/
    spreadsheet.zip       # Original state for diff comparison
```

The agent edits files in place. `diff` and `push` compare against `.pristine/` to determine changes.

## Development

```bash
cd extrasheet
uv sync --all-extras
uv run pytest tests/ -v
uv run ruff check . && uv run ruff format .
uv run mypy src/extrasheet
```

## Testing

Tests are in `tests/` and focus on:
- `test_transformer.py` - API response to on-disk format transformation
- `test_formula_compression.py` - Formula compression/decompression
- `test_utils.py` - A1 notation parsing
- `test_pull_integration.py` - End-to-end pull tests using golden files

### Golden File Testing

Golden files enable testing without mocking or making real API calls:

```
tests/golden/
  <spreadsheet_id>/
    metadata.json    # First API call response (metadata only)
    data.json        # Second API call response (with grid data)
```

Use `LocalFileTransport` in tests:

```python
from extrasheet import SheetsClient, LocalFileTransport

@pytest.fixture
def client():
    transport = LocalFileTransport(Path("tests/golden"))
    return SheetsClient(transport)

@pytest.mark.asyncio
async def test_pull(client, tmp_path):
    files = await client.pull("basic_spreadsheet", tmp_path)
    assert (tmp_path / "basic_spreadsheet" / "Sheet1" / "data.tsv").exists()
```

### Creating New Golden Files

1. Create a Google Sheets file with the features to test
2. Pull it: `python -m extrasheet pull <url>` (raw files saved by default)
3. Copy `.raw/metadata.json` and `.raw/data.json` to `tests/golden/<name>/`
4. Verify the output looks correct
5. Commit the golden files

## Architecture Notes

### Transport-Based Design

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│ SheetsClient    │────▶│ Transport        │────▶│ Google API /    │
│ (orchestration) │     │ (data fetching)  │     │ Local Files     │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

- `Transport` is an abstract base class with `get_metadata()`, `get_data()`, `close()`
- `GoogleSheetsTransport` - Production: makes real API calls via `httpx`
- `LocalFileTransport` - Testing: reads from local golden files
- Access token is a transport concern, not a client concern

### Pull Flow

1. **Metadata fetch** - `transport.get_metadata()` gets sheet names and dimensions
2. **Data fetch** - `transport.get_data()` gets cell contents with row limits
3. **Transform** - `SpreadsheetTransformer` converts API response to file format
4. **Write** - `FileWriter` writes TSV/JSON files to disk
5. **Save raw** - Optionally save `.raw/metadata.json` and `.raw/data.json`
6. **Pristine copy** - Create `.pristine/spreadsheet.zip` for diff/push

### Key Design Decisions

- **Async-first**: All transport and client methods are async
- **Two API calls always**: Metadata first, then data with ranges
- **max_rows=100 default**: Prevents timeout on large spreadsheets
- **save_raw=True default**: Always saves raw responses for debugging/testing
- **No mocking in tests**: Use `LocalFileTransport` with golden files instead

### Dependencies

- `httpx` - Async HTTP client for API calls
- `certifi` - SSL certificates
- `keyring` - OS keyring for token caching (via credentials.py)

## Current Status

`pull` is fully implemented with async support, transport-based architecture, and golden file testing. `diff` and `push` commands do not exist yet - they will compare against `.pristine/` to generate and apply changes.
