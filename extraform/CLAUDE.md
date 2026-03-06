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

## CLI Interface

```bash
# Pull a form
./extrasuite form pull <form_url_or_id> [output_dir]

# Preview changes (dry run)
./extrasuite form diff <folder>
# Output: batchUpdate JSON to stdout

# Apply changes
./extrasuite form push <folder>
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

**Post-push sync:** After a successful push, `client.py` rewrites `form.json` from the API response (`include_form_in_response=True`) via `FormTransformer` and updates `.pristine/`. This ensures API-assigned IDs are reflected immediately — no re-pull needed.

**updateItem index:** When an item has both a content change and a position change in the same push, `updateItem` must reference the item's position *after deletes and creates but before moves*. Use `_update_item_index()` in `request_generator.py` to compute this. Using `new_index` (final desired position) would target the wrong item.

## Multi-Phase Push (Conditional Branching)

When a push includes new sections (`pageBreakItem`) referenced by `goToSectionId` in the same push, the API cannot resolve those IDs in a single call. `generate_batched_requests()` in `request_generator.py` splits the work into ordered batches:

**Batch 0** (sent first):
- Form info / settings updates
- `deleteItem` requests
- `createItem` for new sections (pageBreakItems) and other items with no cross-dependencies
- Indices in batch-0 creates are adjusted: `adj_idx = new_idx - count(batch-1 creates at positions ≤ new_idx)`

**Batch 1** (sent after batch 0 replies arrive):
- `createItem` for items whose `goToSectionId` references a new section from batch 0
- `updateItem` requests (using `_update_item_index()` for correct pre-move positions)
- `moveItem` requests

**DeferredItemID** — when a batch-1 create has a `goToSectionId` pointing to a new section, the value is set to a `DeferredItemID(placeholder, batch_index=0, request_index=N)` object rather than a real ID. After batch 0 completes, `resolve_deferred_ids()` walks the batch-1 requests and replaces each `DeferredItemID` with the actual itemId from `prior_responses[0]["replies"][N]["createItem"]["itemId"]`.

If there are no cross-dependencies, `generate_batched_requests()` returns a single batch and push makes one API call.

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
