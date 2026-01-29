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
| `src/extrasheet/client.py` | `SheetsClient` - main interface with `pull()`, `diff()`, `push()` methods |
| `src/extrasheet/transformer.py` | Transforms API response to on-disk format |
| `src/extrasheet/writer.py` | Writes transformed data to files |
| `src/extrasheet/formula_compression.py` | Compresses formulas with relative references |
| `src/extrasheet/format_compression.py` | Compresses cell formatting |
| `src/extrasheet/credentials.py` | `CredentialsManager` for OAuth token handling |
| `src/extrasheet/api_types.py` | TypedDict definitions for Google Sheets API |
| `src/extrasheet/utils.py` | A1 notation parsing utilities |
| `src/extrasheet/diff.py` | Core diff engine - compares pristine vs current |
| `src/extrasheet/request_generator.py` | Generates batchUpdate requests from diff results |
| `src/extrasheet/pristine.py` | Extracts .pristine/spreadsheet.zip |
| `src/extrasheet/file_reader.py` | Reads current files from disk |
| `src/extrasheet/exceptions.py` | Custom exceptions for diff/push |
| `src/extrasheet/formula_refs.py` | Parses formula references for validation |
| `src/extrasheet/structural_validation.py` | Validates structural changes (insert/delete rows/cols) |

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

# Preview changes (dry run)
python -m extrasheet diff <folder>
# Output: batchUpdate JSON to stdout

# Apply changes to Google Sheets
python -m extrasheet push <folder>
# Output: Success message with number of changes applied

# Execute batchUpdate requests directly (for structural changes)
python -m extrasheet batchUpdate <spreadsheet_url_or_id> <requests.json>
# Options:
#   -v, --verbose  Print API response
```

Also works via `uvx extrasheet pull/diff/push/batchUpdate`.

## Folder Structure

After `pull`, the folder contains:
```
<spreadsheet_id>/
  spreadsheet.json        # Metadata + sheet index + data previews (first 5 / last 3 rows)
  theme.json              # Default formatting and theme colors (optional)
  named_ranges.json       # Named ranges (optional)
  <sheet_name>/
    data.tsv              # Cell values
    formula.json          # Formulas (compressed)
    format.json           # Formatting (compressed)
    feature.json          # Charts, pivot tables, etc.
    dimension.json        # Row/column sizes (optional)
  .raw/
    metadata.json         # Raw metadata API response
    data.json             # Raw data API response (with grid data)
  .pristine/
    spreadsheet.zip       # Original state for diff comparison
```

**Progressive disclosure:** LLM agents should start by reading `spreadsheet.json` to understand the structure. The `preview` field in each sheet shows first 5 and last 3 rows, giving agents enough context to decide which sheets need detailed examination.

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
- `test_diff.py` - Diff engine unit tests
- `test_request_generator.py` - Request generation tests
- `test_formula_refs.py` - Formula reference parsing for validation
- `test_structural_validation.py` - Structural change validation tests

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

- `Transport` is an abstract base class with `get_metadata()`, `get_data()`, `batch_update()`, `close()`
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

### Diff/Push Flow

1. **Extract pristine** - `pristine.extract_pristine()` extracts `.pristine/spreadsheet.zip`
2. **Read current** - `file_reader.read_current_files()` reads edited files
3. **Diff** - `diff.diff()` compares and returns `DiffResult`
4. **Generate requests** - `request_generator.generate_requests()` converts to batchUpdate JSON
5. **Push** - `transport.batch_update()` sends to Google Sheets API

### Declarative vs Imperative Workflow

**Declarative (diff/push):** Edit files locally, then push. Works for almost everything:
- Cell value changes
- Formula changes (single cells and ranges with autoFill)
- Sheet/spreadsheet property changes
- Insert/delete rows/columns (with validation - see below)
- Delete sheets (with validation)
- All formatting and feature changes

**Structural Change Validation:**
When structural changes (insert/delete rows/columns, delete sheets) are detected, the diff engine validates them:
- **BLOCK:** Formula edits + structural changes that conflict = silent bug prevention. Push fails.
- **WARN:** Structural changes that break existing formulas (will show #REF! in cells). Use `--force` to proceed.
- **SILENT:** Ambiguous but valid cases (e.g., appending rows beyond a formula's range). Proceeds without comment.

**Imperative (batchUpdate):** Use direct batchUpdate for complex operations that require precise control:
- Complex multi-step structural changes
- Sorting data
- Moving rows/columns

## Current Status

All core functionality is implemented:
- `pull` - Downloads spreadsheet to local files
- `diff` - Compares current vs pristine, outputs batchUpdate JSON
- `push` - Applies changes to Google Sheets
- `batchUpdate` - Executes raw batchUpdate requests

**Supported change types:**
- New sheet creation (add folder + entry in spreadsheet.json, diff/push will create it)
- Delete sheets (remove folder from disk, validated for cross-sheet references)
- Insert/delete rows (edit data.tsv, validated for formula conflicts)
- Insert/delete columns (edit data.tsv, validated for formula conflicts)
- Cell value changes (add, modify, delete)
- Formula changes (single cells and ranges with autoFill)
- Format rules (backgroundColor, numberFormat, textFormat, alignment)
- Column/row dimensions (width/height changes)
- Sheet/spreadsheet properties (title, frozen rows/columns, hidden)
- Data validation (dropdowns, checkboxes, etc.)
- textFormatRuns (rich text formatting within cells)
- Cell notes
- Cell merges
- Conditional formatting (add, update, delete rules)
- Basic filters (set, clear)
- Banded ranges (alternating row/column colors)
- Filter views (add, update, delete)
- Charts (add, update spec, update position, delete)
