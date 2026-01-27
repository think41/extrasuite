# extrasheet

File-based Google Sheets representation library for LLM agents.

## Overview

`extrasheet` transforms Google Sheets into a file-based representation optimized for LLM agents. Instead of working with complex API responses, agents interact with simple files:

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
from extrasheet import SheetsClient

# Initialize client with access token
client = SheetsClient(access_token="your_token")

# Pull spreadsheet to local files
client.pull("1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms", "./output")

# Files created:
# ./output/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/
#   ├── spreadsheet.json     # Spreadsheet metadata
#   └── Sheet1/
#       ├── data.tsv         # Cell values
#       ├── formula.json     # Cell formulas
#       ├── format.json      # Cell formatting
#       └── feature.json     # Charts, pivot tables, etc.
```

## CLI Usage

```bash
# Download a spreadsheet to local files
python -m extrasheet download <spreadsheet_id_or_url> <output_dir>

# Also save the raw API response
python -m extrasheet download <spreadsheet_id_or_url> <output_dir> --save-raw
```

## Documentation

- **[On-Disk Format](docs/on-disk-format.md)** - Complete specification of the file format
- **[LLM Agent Guide](docs/llm-agent-guide.md)** - How to use extrasheet output for spreadsheet modifications
- **[API Types](src/extrasheet/api_types.py)** - TypedDict definitions generated from Google Sheets API

## Development

```bash
cd extrasheet
uv sync
uv run pytest tests/ -v
uv run ruff check .
uv run ruff format .
uv run mypy src/extrasheet
```

## License

MIT License - see [LICENSE](LICENSE) for details.

## Part of ExtraSuite

This package is part of the [ExtraSuite](https://github.com/think41/extrasuite) project, which provides AI agents with secure access to Google Workspace files.
