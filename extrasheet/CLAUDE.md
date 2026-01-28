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
| `src/extrasheet/client.py` | `SheetsClient` - main interface for pull operations |
| `src/extrasheet/transformer.py` | Transforms API response to on-disk format |
| `src/extrasheet/writer.py` | Writes transformed data to files |
| `src/extrasheet/formula_compression.py` | Compresses formulas with relative references |
| `src/extrasheet/format_compression.py` | Compresses cell formatting |
| `src/extrasheet/credentials.py` | `CredentialsManager` from extrasuite-client |
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

# Preview changes (dry run)
python -m extrasheet diff <folder>
# Output: batchUpdate JSON to stdout

# Apply changes to Google Sheets
python -m extrasheet push <folder>
# Output: API response
```

Also works via `uvx extrasheet pull/diff/push`.

## Folder Structure (Desired State)

After `pull`, the folder contains:
```
<spreadsheet_id>/
  spreadsheet.json        # Metadata (title, sheets list, etc.)
  <sheet_name>/
    data.tsv              # Cell values
    formula.json          # Formulas (compressed)
    format.json           # Formatting (compressed)
    feature.json          # Charts, pivot tables, etc.
  .pristine/
    spreadsheet.zip       # Original state for diff comparison
```

The agent edits files in place. `diff` and `push` compare against `.pristine/` to determine changes.

## Development

```bash
cd extrasheet
uv sync
uv run pytest tests/ -v
uv run ruff check . && uv run ruff format .
uv run mypy src/extrasheet
```

## Testing

Tests are in `tests/` and focus on:
- `test_transformer.py` - API response to on-disk format transformation
- `test_formula_compression.py` - Formula compression/decompression
- `test_utils.py` - A1 notation parsing

Golden files: Store raw Google Sheets API responses in `tests/golden/<spreadsheet_id>/` for offline testing.

## Architecture Notes

1. **Pull flow**: `SheetsClient.pull()` → Google Sheets API → `Transformer` → `Writer` → files on disk
2. **Formula compression**: Relative cell references are compressed (e.g., `=A1+B1` in C1 becomes `=RC[-2]+RC[-1]`)
3. **Format compression**: Repeated formats are deduplicated and referenced by index
4. **Credentials**: Uses `CredentialsManager` from extrasuite-client for OAuth token handling

## Current Status

`pull` is fully implemented with `.pristine/` support. After pulling, a `.pristine/spreadsheet.zip` is created containing the original state. `diff` and `push` commands do not exist yet - they will compare against `.pristine/` to generate and apply changes.
