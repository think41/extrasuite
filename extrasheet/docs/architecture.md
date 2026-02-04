# ExtraSheet Architecture

Technical overview for engineers working on or integrating with ExtraSheet.

## Overview

ExtraSheet transforms Google Sheets into a file-based representation optimized for LLM agents. Instead of working with the verbose Google Sheets API, agents interact with simple local files (TSV, JSON) that can be diffed and pushed back.

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│ SheetsClient    │────▶│ Transport        │────▶│ Google Sheets   │
│ (orchestration) │     │ (data fetching)  │     │ API             │
└─────────────────┘     └──────────────────┘     └─────────────────┘
        │
        ▼
┌─────────────────┐     ┌──────────────────┐
│ Transformer     │────▶│ Local Files      │
│ (API → Files)   │     │ (TSV, JSON)      │
└─────────────────┘     └──────────────────┘
```

## Core Workflow

```bash
extrasheet pull <url>      # API → Local files
# ... agent edits files ...
extrasheet diff <folder>   # Compare against .pristine, output batchUpdate JSON
extrasheet push <folder>   # Apply changes via batchUpdate API
```

## Key Components

| Component | File | Purpose |
|-----------|------|---------|
| SheetsClient | `client.py` | Main interface: `pull()`, `diff()`, `push()` |
| Transport | `transport.py` | Abstract data fetching (Google API or local files) |
| Transformer | `transformer.py` | Converts API response to on-disk format |
| FileWriter | `writer.py` | Writes transformed data to disk |
| Diff Engine | `diff.py` | Compares pristine vs current state |
| RequestGenerator | `request_generator.py` | Generates batchUpdate requests from diff |

## Pull Flow

1. **Metadata fetch** — `transport.get_metadata()` gets sheet names and dimensions
2. **Data fetch** — `transport.get_data()` gets cell contents (with configurable row limits)
3. **Transform** — `SpreadsheetTransformer` converts API response to file format
4. **Write** — `FileWriter` writes TSV/JSON files to disk
5. **Pristine copy** — Creates `.pristine/spreadsheet.zip` for diff comparison

## Diff/Push Flow

1. **Extract pristine** — `pristine.extract_pristine()` extracts `.pristine/spreadsheet.zip`
2. **Read current** — `file_reader.read_current_files()` reads edited files
3. **Diff** — `diff.diff()` compares and returns `DiffResult`
4. **Validate** — Structural changes are validated for formula conflicts
5. **Generate requests** — `request_generator.generate_requests()` converts to batchUpdate JSON
6. **Push** — `transport.batch_update()` sends to Google Sheets API

## Design Decisions

**Async-first:** All transport and client methods are async for efficient I/O.

**Two API calls always:** Metadata first (to get sheet dimensions), then data with specific ranges. This allows row limiting without fetching everything.

**Transport abstraction:** `GoogleSheetsTransport` for production, `LocalFileTransport` for testing with golden files. No mocking needed.

**Declarative over imperative:** Most operations work by editing local files and pushing. Only complex operations (sort, move) require direct batchUpdate calls.

**Formula compression:** Contiguous cells with the same formula pattern are stored as ranges (e.g., `"C2:C100": "=A2+B2"`). Relative references auto-increment on push.

**Format compression:** Cell formats are stored as range-based rules, not per-cell. Reduces file size and makes bulk formatting changes easier.

## File Format

The on-disk format is designed for:
- Human readability (TSV for data, JSON for structure)
- LLM comprehension (progressive disclosure via `spreadsheet.json` previews)
- Efficient diffing (range-based compression, stable ordering)

See **[on-disk-format.md](on-disk-format.md)** for the complete specification.

## Diff/Push Implementation

The diff engine handles:
- Cell value changes (add, modify, delete)
- Formula changes (single cells and ranges with autoFill)
- Format rule changes
- Structural changes (insert/delete rows/columns, create/delete sheets)
- Feature changes (charts, pivot tables, filters, etc.)

Structural change validation prevents silent bugs:
- **BLOCK:** Formula edits + conflicting structural changes
- **WARN:** Structural changes that break existing formulas (use `--force`)

See **[diff-push-spec.md](diff-push-spec.md)** for implementation details.

## Known Issues

**Color formats:** `formatRules` uses hex strings, but `conditionalFormats` and other sections use RGB dicts. Mixing them causes `'dict' object has no attribute 'lstrip'`.

**Pristine state:** Not auto-updated after push. Always re-pull before making additional changes.

**Sheet IDs:** Google may reassign IDs when creating sheets. Re-pull to get server-assigned IDs.

**Error messages:** The error `'dict' object has no attribute 'lstrip'` can mean several different things (wrong color format, wrong JSON structure, etc.).

## Testing

Tests use golden files instead of mocks:

```
tests/golden/
  <spreadsheet_id>/
    metadata.json    # First API call response
    data.json        # Second API call response
```

`LocalFileTransport` reads from these files, enabling deterministic testing without API calls.

## Related Documentation

- **[on-disk-format.md](on-disk-format.md)** — Complete file format specification
- **[diff-push-spec.md](diff-push-spec.md)** — Diff/push implementation details
- **[agent-guide/](agent-guide/)** — LLM-focused usage guides
