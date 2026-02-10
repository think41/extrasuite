# extrasheet

Declarative Google Sheets editing for AI agents. Pull, edit, push.

Part of the [ExtraSuite](https://github.com/think41/extrasuite) project - declarative Google Workspace editing for AI agents.

## Overview

`extrasheet` converts Google Sheets into compact, token-efficient local files that agents can edit declaratively. The library then computes the minimal `batchUpdate` API calls to sync changes back - like Terraform for spreadsheets. Instead of working with complex API responses, agents interact with simple files:

- **data.tsv** - Cell values in tab-separated format (formulas show computed values)
- **formula.json** - Sparse dictionary mapping cell coordinates to formulas
- **format.json** - Cell formatting definitions
- **feature.json** - Advanced features (charts, pivot tables, filters, etc.)

This separation allows LLM agents to selectively load only the data they need, reducing token usage and enabling efficient "fly-blind" editing.

## Installation

```bash
pip install extrasheet
```

Or with uv:

```bash
uv add extrasheet
```

## Quick Start

```python
import asyncio
from extrasheet import SheetsClient, GoogleSheetsTransport

async def main():
    # Create transport with access token
    transport = GoogleSheetsTransport(access_token="your_token")

    # Initialize client with transport
    client = SheetsClient(transport)

    # Pull spreadsheet to local files
    files = await client.pull(
        "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
        "./output",
        max_rows=100,      # Default: 100 rows per sheet
        save_raw=True,     # Default: saves raw API responses
    )

    # Clean up
    await transport.close()

asyncio.run(main())

# Files created:
# ./output/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/
#   ├── spreadsheet.json     # Spreadsheet metadata
#   ├── Sheet1/
#   │   ├── data.tsv         # Cell values
#   │   ├── formula.json     # Cell formulas
#   │   ├── format.json      # Cell formatting
#   │   └── feature.json     # Charts, pivot tables, etc.
#   ├── .raw/
#   │   ├── metadata.json    # Raw metadata API response
#   │   └── data.json        # Raw data API response
#   └── .pristine/
#       └── spreadsheet.zip  # Pristine copy for diff/push
```

## CLI Usage

```bash
# Pull a spreadsheet to local files (defaults to ./<spreadsheet_id>/)
python -m extrasheet pull <spreadsheet_url_or_id> [output_dir]

# Limit rows fetched per sheet (default: 100)
python -m extrasheet pull <url> --max-rows 500

# Fetch all rows (may timeout on large spreadsheets)
python -m extrasheet pull <url> --no-limit

# Don't save raw API responses
python -m extrasheet pull <url> --no-raw
```

## Architecture

The library uses a transport-based architecture for clean separation of concerns:

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│ SheetsClient    │────▶│ Transport        │────▶│ Google API /    │
│ (orchestration) │     │ (data fetching)  │     │ Local Files     │
└─────────────────┘     └──────────────────┘     └─────────────────┘
        │
        ▼
┌─────────────────┐     ┌──────────────────┐
│ Transformer     │────▶│ FileWriter       │
│ (API → files)   │     │ (disk I/O)       │
└─────────────────┘     └──────────────────┘
```

**Transport implementations:**
- `GoogleSheetsTransport` - Production transport using Google Sheets API
- `LocalFileTransport` - Test transport reading from local golden files

## Testing with Golden Files

The library supports golden file testing without mocking:

```python
import pytest
from pathlib import Path
from extrasheet import SheetsClient, LocalFileTransport

@pytest.fixture
def client():
    transport = LocalFileTransport(Path("tests/golden"))
    return SheetsClient(transport)

@pytest.mark.asyncio
async def test_pull(client, tmp_path):
    files = await client.pull("my_spreadsheet", tmp_path)
    assert (tmp_path / "my_spreadsheet" / "Sheet1" / "data.tsv").exists()
```

Golden files are stored as:
```
tests/golden/
  my_spreadsheet/
    metadata.json    # First API call response
    data.json        # Second API call response
```

## Documentation

- **[On-Disk Format](docs/on-disk-format.md)** - Complete specification of the file format
- **[LLM Agent Guide](docs/llm-agent-guide.md)** - How to use extrasheet output for spreadsheet modifications
- **[API Types](src/extrasheet/api_types.py)** - TypedDict definitions generated from Google Sheets API

## Development

```bash
cd extrasheet
uv sync --all-extras
uv run pytest tests/ -v
uv run ruff check .
uv run ruff format .
uv run mypy src/extrasheet
```

## License

MIT License - see [LICENSE](LICENSE) for details.

## Part of ExtraSuite

This package is part of the [ExtraSuite](https://github.com/think41/extrasuite) project - a platform for declarative Google Workspace editing by AI agents. ExtraSuite supports Sheets, Docs, Slides, and Forms with a consistent pull-edit-diff-push workflow, with Apps Script support upcoming.
