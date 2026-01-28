## Overview

Python library that converts Google Slides to/from SML (Slide Markup Language), an XML-based format optimized for LLM editing. Implements the pull/diff/push workflow.

## Key Files

| File | Purpose |
|------|---------|
| `src/extraslide/transport.py` | `Transport` ABC, `GoogleSlidesTransport`, `LocalFileTransport` |
| `src/extraslide/client.py` | `SlidesClient` - main interface for pull/diff/push operations |
| `src/extraslide/compression.py` | ID removal with external mapping for cleaner SML |
| `src/extraslide/parser.py` | Parses SML back to internal data structures |
| `src/extraslide/generator.py` | Converts Google Slides API JSON to SML |
| `src/extraslide/diff.py` | Compares original vs modified SML, generates change operations |
| `src/extraslide/requests.py` | Builds Google Slides API batchUpdate request objects |
| `src/extraslide/classes.py` | Data classes for slide elements (Color, Fill, Stroke, etc.) |
| `src/extraslide/credentials.py` | `CredentialsManager` for OAuth token handling |

## Documentation

- `docs/markup-syntax-design.md` - SML format specification
- `docs/sml-reconciliation-spec.md` - How diff/push reconciles changes

## CLI Interface

```bash
# Download a presentation to local folder
python -m extraslide pull <presentation_url_or_id> [output_dir]
# Output: ./<presentation_id>/ or specified output_dir

# Options:
#   --no-raw    Don't save raw API response to .raw/ folder

# Preview changes (dry run)
python -m extraslide diff <folder>
# Output: batchUpdate JSON to stdout

# Apply changes to Google Slides
python -m extraslide push <folder>
# Output: Success message with change count
```

Also works via `uvx extraslide pull/diff/push`.

## Folder Structure

After `pull`, the folder contains:
```
<presentation_id>/
  slides.sml              # Slides content (IDs removed for cleaner editing)
  masters.sml             # Master slide definitions
  layouts.sml             # Layout definitions
  images.sml              # Image URL mappings
  presentation.json       # Metadata (title, presentation ID, slide summaries)
  .meta/
    id_mapping.json       # ID mapping for diff/push restoration
  .raw/
    presentation.json     # Raw API response (for debugging)
  .pristine/
    presentation.zip      # Zip of entire folder for diff comparison
```

The agent edits `slides.sml` in place. `diff` and `push` compare against `.pristine/` to determine changes. IDs are restored from `.meta/id_mapping.json` before generating API requests.

## Development

```bash
cd extraslide
uv sync --all-extras
uv run pytest tests/ -v
uv run ruff check . && uv run ruff format .
uv run mypy src/extraslide
```

## Testing

Tests are in `tests/` and focus on:
- `test_pull_integration.py` - End-to-end pull/diff/push tests using golden files
- `test_client.py` - SlidesClient unit tests
- `test_transport.py` - Transport layer tests
- `test_diff.py` - SML diffing logic
- `test_parser.py` / `test_generator.py` - SML parsing and generation
- `test_requests.py` - batchUpdate request generation

### Golden File Testing

Golden files enable testing without mocking or making real API calls:

```
tests/golden/
  <presentation_id>/
    presentation.json    # Raw API response
```

Use `LocalFileTransport` in tests:

```python
from extraslide import SlidesClient, LocalFileTransport

@pytest.fixture
def client():
    transport = LocalFileTransport(Path("tests/golden"))
    return SlidesClient(transport)

@pytest.mark.asyncio
async def test_pull(client, tmp_path):
    files = await client.pull("simple_presentation", tmp_path)
    assert (tmp_path / "simple_presentation" / "slides.sml").exists()
```

### Creating New Golden Files

1. Create a Google Slides file with the features to test
2. Pull it: `python -m extraslide pull <url>` (raw files saved by default)
3. Copy `.raw/presentation.json` to `tests/golden/<name>/presentation.json`
4. Verify the output looks correct
5. Commit the golden files

## Architecture Notes

### Transport-Based Design

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│ SlidesClient    │────▶│ Transport        │────▶│ Google API /    │
│ (orchestration) │     │ (data fetching)  │     │ Local Files     │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

- `Transport` is an abstract base class with `get_presentation()`, `batch_update()`, `close()`
- `GoogleSlidesTransport` - Production: makes real API calls via `httpx`
- `LocalFileTransport` - Testing: reads from local golden files
- Access token is a transport concern, not a client concern

### Pull Flow

1. **Fetch** - `transport.get_presentation()` gets full presentation JSON
2. **Transform** - `json_to_sml()` converts API response to SML
3. **Split** - Separate SML into slides, masters, layouts, images
4. **Remove IDs** - Strip verbose element IDs from slides, save mapping to `.meta/`
5. **Write** - Save split SML files and `presentation.json` to disk
6. **Save raw** - Optionally save `.raw/presentation.json`
7. **Pristine copy** - Create `.pristine/presentation.zip` (zip of entire folder)

### Diff/Push Flow

1. **Read pristine** - Extract files from `.pristine/presentation.zip`
2. **Read current** - Read split SML files from disk
3. **Reconstruct** - Combine split files and restore IDs from `.meta/id_mapping.json`
4. **Parse both** - Convert SML strings to internal structures
5. **Diff** - Compare and generate change operations
6. **Generate requests** - Convert operations to batchUpdate format
7. **Push** (if not dry-run) - Send to `transport.batch_update()`

### Key Design Decisions

- **Async-first**: All transport and client methods are async
- **Single API call for pull**: Unlike extrasheet, Slides API returns everything in one call
- **save_raw=True default**: Always saves raw responses for debugging/testing
- **No mocking in tests**: Use `LocalFileTransport` with golden files instead

### Dependencies

- `httpx` - Async HTTP client for API calls
- `certifi` - SSL certificates
- `keyring` - OS keyring for token caching (via credentials.py)

## Current Status

The library uses:
- Transport-based architecture with dependency injection
- Split file structure (slides, masters, layouts, images as separate files)
- ID removal with external mapping for cleaner SML editing
- Folder-based workflow (pull creates folder, diff/push use `.pristine/`)
- Async methods throughout
- Golden file testing
