## Overview

Python library that converts Google Slides to/from SML (Slide Markup Language), an XML-based format optimized for LLM editing. Implements the pull/diff/push workflow.

## Key Files

| File | Purpose |
|------|---------|
| `src/extraslide/client.py` | `SlidesClient` - main interface for pull/push operations |
| `src/extraslide/parser.py` | Converts Google Slides API response to SML |
| `src/extraslide/generator.py` | Converts SML back to Slides API structures |
| `src/extraslide/diff.py` | Compares original vs modified SML, generates batchUpdate requests |
| `src/extraslide/requests.py` | Builds Google Slides API batchUpdate request objects |
| `src/extraslide/classes.py` | Data classes for slide elements |
| `src/extraslide/credentials.py` | `CredentialsManager` from extrasuite-client |

## Documentation

- `docs/markup-syntax-design.md` - SML format specification
- `docs/sml-reconciliation-spec.md` - How diff/push reconciles changes

## CLI Interface (Desired State)

```bash
# Download a presentation to local folder
python -m extraslide pull <presentation_url_or_id> [output_dir]
# Output: ./<presentation_id>/ or specified output_dir

# Preview changes (dry run)
python -m extraslide diff <folder>
# Output: batchUpdate JSON to stdout

# Apply changes to Google Slides
python -m extraslide push <folder>
# Output: API response
```

Should also work via `uvx extraslide pull/diff/push`.

## Folder Structure (Desired State)

After `pull`, the folder contains:
```
<presentation_id>/
  presentation.sml      # The editable SML file
  .pristine/
    presentation.zip    # Original state for diff comparison
```

The agent edits `presentation.sml` in place. `diff` and `push` compare against `.pristine/` to determine changes.

## Development

```bash
cd extraslide
uv sync
uv run pytest tests/ -v
uv run ruff check . && uv run ruff format .
uv run mypy src/extraslide
```

## Testing

Tests are in `tests/` and focus on:
- Parsing Google Slides API responses to SML
- Generating batchUpdate requests from SML diffs
- Round-trip integrity (parse → modify → generate → verify)

Golden files: Store raw Google Slides API responses in `tests/golden/<presentation_id>/` for offline testing.

## Current Status

Alpha quality. The diff/push workflow exists but expects separate pristine and modified files as arguments. Needs to be updated to use the `.pristine/` folder approach described above.
