# ExtraForm

Declarative Google Forms editing for AI agents. Pull, edit, push.

Part of the [ExtraSuite](https://github.com/think41/extrasuite) project - declarative Google Workspace editing for AI agents.

ExtraForm converts Google Forms into compact, token-efficient local JSON files that agents can edit declaratively. The library computes the minimal `batchUpdate` API calls to sync changes back. It follows the same pull/diff/push workflow as all ExtraSuite packages.

## Installation

```bash
pip install extraform
```

Or with `uvx`:

```bash
uvx extraform pull <form_url>
```

## Quick Start

```bash
# 1. Login (one-time)
extraform login

# 2. Pull a form
extraform pull https://docs.google.com/forms/d/1FAIpQLSd.../edit

# 3. Edit form.json in your editor or with an AI agent

# 4. Preview changes
extraform diff 1FAIpQLSd...

# 5. Apply changes
extraform push 1FAIpQLSd...
```

## Commands

### pull

Download a Google Form to a local folder:

```bash
extraform pull <form_url_or_id> [output_dir]
```

Options:
- `--responses` - Include form responses (read-only)
- `--max-responses N` - Maximum responses to fetch (default: 100)
- `--no-raw` - Don't save raw API responses

### diff

Preview changes without applying them:

```bash
extraform diff <folder>
```

Outputs the batchUpdate JSON to stdout.

### push

Apply changes to the Google Form:

```bash
extraform push <folder>
```

## On-Disk Format

After pulling a form, you'll have:

```
<form_id>/
  form.json                 # Form structure - edit this!
  responses.tsv             # Read-only snapshot of responses
  .raw/
    form.json               # Raw API response
    responses.json          # Raw responses (if fetched)
  .pristine/
    form.zip                # Original state for diff
```

### form.json

The form structure mirrors the Google Forms API but is cleaned up for readability:

```json
{
  "formId": "1FAIpQLSd...",
  "info": {
    "title": "My Survey",
    "description": "Please fill out this survey"
  },
  "items": [
    {
      "itemId": "abc123",
      "title": "What is your name?",
      "questionItem": {
        "question": {
          "required": true,
          "textQuestion": {
            "paragraph": false
          }
        }
      }
    }
  ]
}
```

## Question Types

| Type | JSON Key | Example |
|------|----------|---------|
| Short answer | `textQuestion` | `{"paragraph": false}` |
| Long answer | `textQuestion` | `{"paragraph": true}` |
| Multiple choice | `choiceQuestion` | `{"type": "RADIO", "options": [...]}` |
| Checkboxes | `choiceQuestion` | `{"type": "CHECKBOX", "options": [...]}` |
| Dropdown | `choiceQuestion` | `{"type": "DROP_DOWN", "options": [...]}` |
| Linear scale | `scaleQuestion` | `{"low": 1, "high": 5}` |
| Date | `dateQuestion` | `{"includeYear": true}` |
| Time | `timeQuestion` | `{"duration": false}` |
| Rating | `ratingQuestion` | `{"iconType": "STAR", "ratingScaleLevel": 5}` |

## Non-Question Items

| Type | Purpose |
|------|---------|
| `pageBreakItem` | Section divider |
| `textItem` | Static text/instructions |
| `imageItem` | Embedded image |
| `videoItem` | Embedded YouTube video |

## Limitations

- **File upload questions**: Cannot be created via API (read-only)
- **Responses**: Read-only, cannot modify submitted responses
- **documentTitle**: Read-only, update via Google Drive

## Development

```bash
cd extraform
uv sync
uv run pytest tests/ -v
uv run ruff check . && uv run ruff format .
uv run mypy src/extraform
```

## Part of ExtraSuite

This package is part of the [ExtraSuite](https://github.com/think41/extrasuite) project - a platform for declarative Google Workspace editing by AI agents. ExtraSuite supports Sheets, Docs, Slides, and Forms with a consistent pull-edit-diff-push workflow, with Apps Script support upcoming.

## License

MIT
