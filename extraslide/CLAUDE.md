## Overview

Python library that converts Google Slides to/from SML (Slide Markup Language), an XML-based format optimized for LLM editing. Implements the pull/diff/push workflow.

## Key Files

### Core (both clients)
| File | Purpose |
|------|---------|
| `src/extraslide/transport.py` | `Transport` ABC, `GoogleSlidesTransport`, `LocalFileTransport` |
| `src/extraslide/classes.py` | Data classes for slide elements (Color, Fill, Stroke, etc.) |
| `src/extraslide/credentials.py` | `CredentialsManager` for OAuth token handling |
| `src/extraslide/units.py` | EMU/pt conversion utilities |

### V2 Client (Copy-Based Workflow) - Recommended
| File | Purpose |
|------|---------|
| `src/extraslide/client_v2.py` | `SlidesClientV2` - new client with copy support |
| `src/extraslide/slide_processor.py` | Builds render trees, extracts styles |
| `src/extraslide/content_generator.py` | Generates minimal SML from render trees |
| `src/extraslide/content_parser.py` | Parses SML content files |
| `src/extraslide/content_diff.py` | Detects copies, calculates translations |
| `src/extraslide/content_requests.py` | Generates batchUpdate requests for copies |
| `src/extraslide/style_extractor.py` | Extracts styles to JSON |
| `src/extraslide/render_tree.py` | Visual containment hierarchy |

### V1 Client (Legacy)
| File | Purpose |
|------|---------|
| `src/extraslide/client.py` | `SlidesClient` - original client |
| `src/extraslide/compression.py` | ID removal with external mapping |
| `src/extraslide/parser.py` | Parses SML back to internal structures |
| `src/extraslide/generator.py` | Converts API JSON to SML |
| `src/extraslide/diff.py` | Compares SML, generates change operations |
| `src/extraslide/requests.py` | Builds batchUpdate request objects |

## Documentation

- `docs/copy-workflow.md` - Copy-based workflow for V2 client (recommended)
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

### V2 Format (Copy-Based Workflow)

After `pull` with V2 client:
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

### V1 Format (Legacy)

After `pull` with V1 client:
```
<presentation_id>/
  slides.sml              # Slides content (IDs removed)
  masters.sml             # Master slide definitions
  layouts.sml             # Layout definitions
  images.sml              # Image URL mappings
  presentation.json       # Metadata
  .meta/
    id_mapping.json       # ID mapping for restoration
  .raw/
    presentation.json     # Raw API response
  .pristine/
    presentation.zip      # Zip for diff comparison
```

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

The library has two clients:

### V2 Client (Recommended for new work)
- Per-slide content files (`slides/01/content.sml`, etc.)
- Copy-based workflow: duplicate element XML with same ID, omit w/h
- Translation-based child positioning for copies
- Styles extracted to `styles.json`
- Supports 100+ Google Slides shape types

### V1 Client (Legacy)
- Split SML files (slides.sml, masters.sml, etc.)
- ID removal with external mapping
- Folder-based workflow (pull creates folder, diff/push use `.pristine/`)

Both clients use:
- Transport-based architecture with dependency injection
- Async methods throughout
- Golden file testing
