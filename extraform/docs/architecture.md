# Architecture

This document provides a technical overview of the ExtraForm package.

## Module Structure

```
extraform/
  src/extraform/
    __init__.py             # Public exports
    __main__.py             # CLI entry point
    client.py               # FormsClient with pull/diff/push
    transport.py            # FormTransport ABC + implementations
    transformer.py          # API JSON → file format conversion
    diff.py                 # Compare pristine vs current
    request_generator.py    # Generate batchUpdate requests
    writer.py               # Write files to disk
    file_reader.py          # Read files from disk
    pristine.py             # Handle .pristine/form.zip
    exceptions.py           # Custom exceptions
    schema/
      form.schema.json      # JSON Schema for validation
```

## Core Components

### Transport Layer

The transport layer abstracts API communication.

```
FormTransport (ABC)
├── GoogleFormsTransport  # Production: Google Forms API
└── LocalFileTransport    # Testing: local golden files
```

**FormTransport** defines three operations:
- `get_form(form_id)` - Fetch form structure
- `get_responses(form_id, page_size, page_token)` - Fetch responses
- `batch_update(form_id, requests)` - Apply changes

### Client Layer

**FormsClient** orchestrates the pull/diff/push workflow:

```
FormsClient
├── pull()   # Download form → transform → write → create pristine
├── diff()   # Compare pristine vs current → generate requests
└── push()   # diff → batch_update → update pristine
```

### Diff Engine

The diff engine compares two form states and produces a `DiffResult`:

```
DiffResult
├── info_changes      # Title/description changes
├── settings_changes  # Quiz/email settings changes
└── item_changes      # List of ItemChange objects
```

**ItemChange** types:
- `add` - New item in current, not in pristine
- `delete` - Item in pristine, not in current
- `update` - Same itemId, different content
- `move` - Same itemId, different position

### Request Generator

Converts `DiffResult` to Google Forms API batchUpdate requests.

Request order is important:
1. `updateFormInfo` - Form title/description
2. `updateSettings` - Quiz/email settings
3. `deleteItem` - Remove items (end to start)
4. `createItem` - Add new items (in order)
5. `updateItem` - Modify existing items
6. `moveItem` - Reorder items

## Data Flow

### Pull

```
Google Forms API
      │
      ▼
  get_form()
      │
      ▼
FormTransformer
      │
      ▼
  FileWriter
      │
      ▼
 Local files + .pristine/form.zip
```

### Diff

```
.pristine/form.zip     form.json (current)
        │                    │
        ▼                    ▼
  get_pristine_form()   read_form_json()
        │                    │
        └────────┬───────────┘
                 │
                 ▼
            diff_forms()
                 │
                 ▼
           DiffResult
                 │
                 ▼
        generate_requests()
                 │
                 ▼
        batchUpdate JSON
```

### Push

```
     diff()
       │
       ▼
 batchUpdate JSON
       │
       ▼
 batch_update() ──────► Google Forms API
       │
       ▼
 update_pristine()
```

## Error Handling

Exception hierarchy:

```
ExtraFormError (base)
├── TransportError
│   ├── AuthenticationError (401/403)
│   ├── NotFoundError (404)
│   └── APIError (other HTTP errors)
├── DiffError
│   ├── MissingPristineError
│   └── InvalidFileError
└── ValidationError
```

## Testing Strategy

### Golden File Testing

1. Create test forms covering all question types
2. Pull with raw responses saved
3. Store in `tests/golden/<form_id>/form.json`
4. Tests use `LocalFileTransport` to read golden files

### Test Coverage

| Module | Tests |
|--------|-------|
| transformer.py | API JSON → file format conversion |
| diff.py | Diff algorithm correctness |
| request_generator.py | batchUpdate request generation |
| client.py | End-to-end pull/diff/push workflow |

## Concurrency Control

The Forms API supports optional concurrency control via `writeControl`:

```json
{
  "requests": [...],
  "writeControl": {
    "requiredRevisionId": "00000042"
  }
}
```

- `requiredRevisionId` - Fail if form was modified since this revision
- Revision IDs are valid for 24 hours only

Currently not implemented in ExtraForm but could be added for conflict detection.

## Shared Credentials

ExtraForm reuses the `extrasuite.client` package for authentication:

```python
from extrasuite.client import authenticate
token = authenticate()
```

This provides:
- OAuth flow with browser authentication
- Service account support
- Token caching via OS keyring
