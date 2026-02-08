# extradoc

Declarative Google Docs editing for AI agents. Pull, edit, push.

Part of the [ExtraSuite](https://github.com/think41/extrasuite) project - declarative Google Workspace editing for AI agents.

## Overview

extradoc converts Google Docs into compact, token-efficient local files that agents can edit declaratively. The library computes the minimal `batchUpdate` API calls to sync changes back - like Terraform for documents. Agents edit local file representations through the pull/diff/push workflow.

## Installation

```bash
pip install extradoc
# or
uvx extradoc
```

## Quick Start

```bash
# Authenticate (one-time)
python -m extrasuite.client login

# Pull a document
python -m extradoc pull https://docs.google.com/document/d/DOCUMENT_ID/edit

# Edit files locally...

# Preview changes (dry run)
python -m extradoc diff ./DOCUMENT_ID/

# Push changes
python -m extradoc push ./DOCUMENT_ID/
```

## CLI Commands

### pull

Download a Google Doc to local files:

```bash
python -m extradoc pull <document_url_or_id> [output_dir]

# Options:
#   --no-raw    Don't save raw API responses to .raw/ folder
```

### diff

Preview changes (dry run, no API calls):

```bash
python -m extradoc diff <folder>
# Output: batchUpdate JSON to stdout
```

### push

Apply changes to Google Docs:

```bash
python -m extradoc push <folder>

# Options:
#   -f, --force    Push despite warnings (blocks still prevent push)
```

## Folder Structure

After `pull`, the folder contains:

```
<document_id>/
  document.json           # Document metadata and structure
  content/                # Document content in LLM-friendly format
    ...
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

## Part of ExtraSuite

This package is part of the [ExtraSuite](https://github.com/think41/extrasuite) project - a platform for declarative Google Workspace editing by AI agents. ExtraSuite supports Sheets, Docs, Slides, and Forms with a consistent pull-edit-diff-push workflow, with Apps Script support upcoming.

## License

MIT License - see LICENSE file for details.
