## Package Overview

`extrasheet` is a Python library that transforms Google Sheets into a file-based representation optimized for LLM agents. Instead of working with complex API responses, agents interact with simple files:

- **data.tsv** - Cell values in tab-separated format (formulas show computed values)
- **formula.json** - Sparse dictionary mapping cell coordinates to formulas (with compression)
- **format.json** - Cell formatting definitions (with compression)
- **feature.json** - Advanced features (charts, pivot tables, filters, etc.)

This separation allows LLM agents to selectively load only the data they need, reducing token usage.

## Key Files

| File | Purpose |
|------|---------|
| `src/extrasheet/client.py` | `SheetsClient` - main interface for pulling spreadsheets |
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

## Development Commands

```bash
cd extrasheet
uv sync
uv run pytest tests/ -v
uv run ruff check .
uv run ruff format .
uv run mypy src/extrasheet
```

## Testing

Tests are located in `tests/` and focus on:
- `test_transformer.py` - API response to on-disk format transformation
- `test_formula_compression.py` - Formula compression/decompression
- `test_utils.py` - A1 notation parsing

Run tests with coverage:
```bash
uv run pytest tests/ -v --cov=extrasheet --cov-report=term-missing
```

## CLI Usage

```bash
# Download a spreadsheet to local files
python -m extrasheet download <spreadsheet_id_or_url> <output_dir>

# Also save the raw API response for debugging
python -m extrasheet download <spreadsheet_id_or_url> <output_dir> --save-raw
```

## Architecture Notes

1. **Pull flow**: `SheetsClient.pull()` -> Google Sheets API -> `Transformer` -> `Writer` -> files on disk
2. **Formula compression**: Relative cell references are compressed (e.g., `=A1+B1` in C1 becomes `=RC[-2]+RC[-1]`)
3. **Format compression**: Repeated formats are deduplicated and referenced by index
4. **Credentials**: Uses `CredentialsManager` from extrasuite-client for OAuth token handling
