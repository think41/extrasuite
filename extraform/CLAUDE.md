## Overview

Python library that transforms Google Forms into a file-based representation optimized for LLM agents. Implements the pull/diff/push workflow.

Instead of working with complex API responses, agents interact with a single file:
- **form.json** - Complete form structure (questions, sections, settings)

## Key Files

| File | Purpose |
|------|---------|
| `src/extraform/transport.py` | `FormTransport` ABC, `GoogleFormsTransport`, `LocalFileTransport` |
| `src/extraform/client.py` | `FormsClient` - main interface with `pull()`, `diff()`, `push()` methods |
| `src/extraform/transformer.py` | Transforms API response to on-disk format |
| `src/extraform/diff.py` | Compares pristine vs current form state |
| `src/extraform/request_generator.py` | Generates batchUpdate requests from diff results |
| `src/extraform/pristine.py` | Handles `.pristine/form.zip` creation and extraction |
| `src/extraform/credentials.py` | Token management via extrasuite.client |

## CLI Interface

```bash
# Pull a form
python -m extraform pull <form_url_or_id> [output_dir]

# Preview changes (dry run)
python -m extraform diff <folder>
# Output: batchUpdate JSON to stdout

# Apply changes
python -m extraform push <folder>
```

## Folder Structure

After `pull`, the folder contains:
```
<form_id>/
  form.json       # Edit this file
  .raw/
    form.json     # Raw API response (for debugging)
  .pristine/
    form.zip      # Original state for diff comparison
```

## Key Gotchas

**Item type detection:** Use `"key" in item` instead of `item.get("key")` for detecting item types. Empty dicts like `pageBreakItem: {}` are falsy but indicate the type exists.

**isOther option:** When an option has `isOther: true`, do NOT set the `value` field. The API returns 400 if both are set.

**Move operations:** The Google Forms API processes `moveItem` requests sequentially. Each move changes indices for subsequent moves. The diff engine handles this automatically using simulation.

**Read-only fields:** `itemId` and `questionId` are assigned by the API. Don't include them when creating new items.

**Pristine state:** Not updated after push. Always re-pull before making additional changes.

## Editing form.json

### Change Form Title/Description

```json
{
  "info": {
    "title": "New Title",
    "description": "New description"
  }
}
```

### Add a Question

Add to the `items` array (itemId will be assigned by API):

```json
{
  "title": "What is your email?",
  "questionItem": {
    "question": {
      "required": true,
      "textQuestion": {
        "paragraph": false
      }
    }
  }
}
```

### Question Types

| Type | JSON Key | Example |
|------|----------|---------|
| Short answer | `textQuestion` | `{"paragraph": false}` |
| Long answer | `textQuestion` | `{"paragraph": true}` |
| Multiple choice | `choiceQuestion` | `{"type": "RADIO", "options": [...]}` |
| Checkboxes | `choiceQuestion` | `{"type": "CHECKBOX", "options": [...]}` |
| Dropdown | `choiceQuestion` | `{"type": "DROP_DOWN", "options": [...]}` |
| Linear scale | `scaleQuestion` | `{"low": 1, "high": 5, "lowLabel": "Poor", "highLabel": "Excellent"}` |
| Date | `dateQuestion` | `{"includeYear": true, "includeTime": false}` |
| Time | `timeQuestion` | `{"duration": false}` |
| Rating | `ratingQuestion` | `{"iconType": "STAR", "ratingScaleLevel": 5}` |

### Non-Question Items

```json
// Section divider
{"title": "Section Title", "pageBreakItem": {}}

// Static text
{"title": "Instructions", "description": "Read carefully.", "textItem": {}}
```

### Delete a Question

Remove the item from the `items` array.

### Reorder Questions

Change the order of items in the `items` array. The diff engine handles the move operations automatically.

## What You CAN'T Do

- Create file upload questions (API limitation)
- Modify submitted responses
- Change documentTitle (use Drive API)

## Development

```bash
cd extraform
uv sync --all-extras
uv run pytest tests/ -v
uv run ruff check . && uv run ruff format .
uv run mypy src/extraform
```

## Testing

Tests use golden files in `tests/golden/` with `LocalFileTransport`:

```python
from extraform import FormsClient, LocalFileTransport

transport = LocalFileTransport(Path("tests/golden"))
client = FormsClient(transport)
```

## Supported Operations

- Form title/description changes
- Settings changes (quiz mode, email collection)
- Add/delete/update/reorder questions
- All question types (text, choice, scale, date, time, rating)
- Section dividers (pageBreakItem)
- Static text (textItem)
