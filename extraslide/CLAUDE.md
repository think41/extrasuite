## Overview

Python library that converts Google Slides to/from SML (Slide Markup Language), an XML-based format optimized for LLM editing. Implements the pull/diff/push workflow.

## Key Files

| File | Purpose |
|------|---------|
| `src/extraslide/client.py` | `SlidesClient` - main API with pull/diff/push |
| `src/extraslide/slide_processor.py` | Builds render trees, extracts styles |
| `src/extraslide/content_generator.py` | Generates minimal SML from render trees |
| `src/extraslide/content_parser.py` | Parses SML content files |
| `src/extraslide/content_diff.py` | Detects copies, calculates translations |
| `src/extraslide/content_requests.py` | Generates batchUpdate requests |
| `src/extraslide/style_extractor.py` | Extracts styles to JSON |
| `src/extraslide/render_tree.py` | Visual containment hierarchy |
| `src/extraslide/id_manager.py` | Clean ID assignment and mapping |
| `src/extraslide/transport.py` | `Transport` ABC, `GoogleSlidesTransport`, `LocalFileTransport` |
| `src/extraslide/classes.py` | Data classes for slide elements (Color, Fill, Stroke, etc.) |
| `src/extraslide/credentials.py` | `CredentialsManager` for OAuth token handling |
| `src/extraslide/units.py` | EMU/pt conversion utilities |

## Documentation

- `docs/copy-workflow.md` - Copy-based editing workflow (agent guide)
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

## Folder Structure

After `pull`:
```
<presentation_id>/
  presentation.json       # Metadata (title, presentation ID, dimensions)
  id_mapping.json         # clean_id -> google_object_id
  styles.json             # clean_id -> styles (position, fill, stroke, text)
  slides/
    01/content.sml        # Slide 1 content (minimal XML)
    02/content.sml        # Slide 2 content
    ...
  .raw/
    presentation.json     # Raw API response (for debugging)
  .pristine/
    presentation.zip      # Zip of entire folder for diff comparison
```

Edit `slides/NN/content.sml` files. To copy elements, duplicate XML with same ID but only x,y (omit w,h). See `docs/copy-workflow.md`.

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
- `test_content_diff.py` - Copy detection and diff logic
- `test_slide_processor.py` - Render tree building and SML generation
- `test_transport.py` - Transport layer tests
- `test_classes.py` - Data class conversions
- `test_units.py` - Unit conversions

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
    assert (tmp_path / "simple_presentation" / "slides" / "01" / "content.sml").exists()
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
2. **Process** - `slide_processor.process_presentation()` builds render trees
3. **Extract styles** - Store styles (fill, stroke, text) in `styles.json`
4. **Generate SML** - `content_generator` creates minimal XML per slide
5. **Write** - Save files to `slides/NN/content.sml`
6. **Save raw** - Optionally save `.raw/presentation.json`
7. **Pristine copy** - Create `.pristine/presentation.zip` (zip of entire folder)

### Diff/Push Flow

1. **Read pristine** - Extract files from `.pristine/presentation.zip`
2. **Read current** - Read `slides/NN/content.sml` files
3. **Parse both** - `content_parser` converts SML to internal structures
4. **Diff** - `content_diff.diff_presentation()` detects changes and copies
5. **Generate requests** - `content_requests.generate_batch_requests()` creates API requests
6. **Push** (if not dry-run) - Send to `transport.batch_update()`

### Copy Detection

The copy-based workflow detects copies by:
- Same element ID appearing multiple times
- Copy has x,y but **omits w,h** (signals "copy from original")
- System duplicates the element and moves to new position

### Key Design Decisions

- **Async-first**: All transport and client methods are async
- **Single API call for pull**: Slides API returns everything in one call
- **save_raw=True default**: Always saves raw responses for debugging/testing
- **No mocking in tests**: Use `LocalFileTransport` with golden files instead
- **Per-slide files**: Each slide is a separate content.sml for easier editing
- **Styles in JSON**: Styles stored separately, auto-applied on copy

### Dependencies

- `httpx` - Async HTTP client for API calls
- `certifi` - SSL certificates
- `keyring` - OS keyring for token caching (via credentials.py)
