# extrasheet

File-based Google Sheets representation library for LLM agents.

## Overview

`extrasheet` pulls a spreadsheet into a small set of TSV and JSON files that are
easier for humans and agents to inspect than raw Google Sheets API responses.
The current on-disk format uses:

- `spreadsheet.json` for spreadsheet metadata, sheet list, previews, and
  truncation hints
- `data.tsv` for cell values
- `formula.json` for formulas
- `format.json` for cell formatting, merges, notes, and rich text runs
- Separate feature files such as `charts.json`, `filters.json`,
  `pivot-tables.json`, and `data-validation.json`
- Optional per-sheet `comments.json` files for Google Drive comments

Some pulled files are informational only today and are not diffed or pushed
back. See [docs/gaps.md](docs/gaps.md).

## Python Usage

```python
import asyncio
from extrasheet import GoogleSheetsTransport, SheetsClient


async def main() -> None:
    transport = GoogleSheetsTransport(access_token="your_token")
    client = SheetsClient(transport)

    try:
        await client.pull(
            "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
            "./output",
            max_rows=100,
            save_raw=True,
        )
    finally:
        await transport.close()


asyncio.run(main())
```

Typical output:

```text
./output/<spreadsheet_id>/
  spreadsheet.json
  theme.json                     # optional, informational
  named_ranges.json              # optional, editable
  developer_metadata.json        # optional, informational
  data_sources.json              # optional, informational
  <sheet_folder>/
    data.tsv
    formula.json
    format.json                  # optional
    dimension.json               # optional
    charts.json                  # optional
    pivot-tables.json            # optional
    tables.json                  # optional
    filters.json                 # optional
    banded-ranges.json           # optional
    data-validation.json         # optional
    slicers.json                 # optional
    data-source-tables.json      # optional
    protection.json              # optional, informational
    comments.json                # optional, replies/resolve only
  .raw/
    metadata.json                # optional, saved unless save_raw=False
    data.json
  .pristine/
    spreadsheet.zip
```

## CLI Usage

`extrasheet` is the library package. The CLI lives in `extrasuite`:

```bash
extrasuite sheet pull <url> [output_dir]
extrasuite sheet diff <folder>
extrasuite sheet push <folder>
extrasuite sheet batchUpdate <url> <requests.json>
```

Inside this repo you can run the local CLI with:

```bash
uv run --project client extrasuite sheet pull <url>
```

## Notes

- `pull` always fetches metadata first, then grid data with the requested row
  limit.
- `comments.json` is fetched separately through the Drive API and written per
  sheet when comments exist.
- `.pristine/spreadsheet.zip` is the baseline used by `diff` and `push`.
- After any successful `push`, re-pull before editing again. `.pristine` is not
  updated in place.

## Documentation

- [docs/on-disk-format.md](docs/on-disk-format.md) - Current file layout and
  field reference
- [docs/architecture.md](docs/architecture.md) - Implementation overview
- [docs/diff-push-spec.md](docs/diff-push-spec.md) - What diff/push actually
  honors
- [docs/gaps.md](docs/gaps.md) - Current pull-only and partially supported
  areas

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

MIT License - see [LICENSE](LICENSE).
