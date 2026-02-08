# extradoc

File-based Google Docs representation library for LLM agents.

Part of the [ExtraSuite](https://github.com/think41/extrasuite) project.

## Overview

extradoc transforms Google Docs into a file-based representation optimized for LLM agents, enabling efficient "fly-blind" editing through the pull/diff/push workflow.

## Installation

```bash
pip install extradoc
# or
uvx extradoc
```

## Quick Start

```bash
# Authenticate (one-time)
uv run python -m extrasuite.client login

# Pull a document
uv run python -m extradoc pull https://docs.google.com/document/d/DOCUMENT_ID/edit

# Edit files locally...

# Preview changes (dry run)
uv run python -m extradoc diff ./DOCUMENT_ID/

# Push changes
uv run python -m extradoc push ./DOCUMENT_ID/
```

## CLI Commands

### pull

Download a Google Doc to local files:

```bash
uv run python -m extradoc pull <document_url_or_id> [output_dir]

# Options:
#   --no-raw    Don't save raw API responses to .raw/ folder
```

### diff

Preview changes (dry run, no API calls):

```bash
uv run python -m extradoc diff <folder>
# Output: batchUpdate JSON to stdout
```

### push

Apply changes to Google Docs:

```bash
uv run python -m extradoc push <folder>

# Options:
#   -f, --force    Push despite warnings (blocks still prevent push)
#   --verify       Re-pull after push and compare to verify correctness
```

## Folder Structure

After `pull`, the folder contains:

```
<document_id>/
  document.xml            # ExtraDoc XML (main content)
  styles.xml              # Factorized style definitions
  .raw/
    document.json         # Raw API response
  .pristine/
    document.zip          # Original state for diff comparison
```

## Development

```bash
cd extradoc
uv sync --all-extras
uv run pytest tests/ -v
uv run ruff check . && uv run ruff format .
uv run mypy src/extradoc
```

## License

MIT License - see LICENSE file for details.
