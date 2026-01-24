# Create and Manage Presentations

> **Source**: [Google Slides API - Presentations](https://developers.google.com/workspace/slides/api/guides/presentations)

## Overview

The Google Slides API enables developers to programmatically create, copy, and manage presentations.

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/v1/presentations/{presentationId}` | Retrieve a presentation |
| `POST` | `/v1/presentations` | Create a new presentation |
| `POST` | `/v1/presentations/{presentationId}:batchUpdate` | Modify a presentation |

## Reading a Presentation

Use the `presentations.get` method to retrieve the full JSON representation:

```http
GET https://slides.googleapis.com/v1/presentations/{presentationId}
```

### Response Structure

```json
{
  "presentationId": "abc123",
  "title": "My Presentation",
  "pageSize": {
    "width": {"magnitude": 9144000, "unit": "EMU"},
    "height": {"magnitude": 5143500, "unit": "EMU"}
  },
  "slides": [...],
  "masters": [...],
  "layouts": [...],
  "notesMaster": {...}
}
```

## Creating a Blank Presentation

Use the `presentations.create` method:

```http
POST https://slides.googleapis.com/v1/presentations
Content-Type: application/json

{
  "title": "New Presentation"
}
```

### Response

```json
{
  "presentationId": "new_presentation_id",
  "title": "New Presentation",
  "slides": [
    {
      "objectId": "default_slide_id",
      "pageElements": [...]
    }
  ]
}
```

### Required Scopes

- `https://www.googleapis.com/auth/presentations`
- `https://www.googleapis.com/auth/drive.file`

## Working with Drive Folders

**Important limitation**: There's no option to create a presentation directly within a specified Drive folder using the Google Slides API.

### Workarounds

1. **Move after creation**: Create the presentation, then move it using the Drive API's `files.update()` method

2. **Create via Drive API**: Use Drive API's `files.create()` method with MIME type:
   ```
   application/vnd.google-apps.presentation
   ```
   This allows specifying a parent folder.

Both approaches require appropriate Drive API scopes.

## Copying Presentations

Use the Drive API's `files.copy()` method:

```http
POST https://www.googleapis.com/drive/v3/files/{fileId}/copy
Content-Type: application/json

{
  "name": "Copy of My Presentation"
}
```

### Required Scopes

- `https://www.googleapis.com/auth/drive`
- `https://www.googleapis.com/auth/drive.file`

## Modifying Presentations

Use the `batchUpdate` method for all modifications:

```http
POST https://slides.googleapis.com/v1/presentations/{presentationId}:batchUpdate
Content-Type: application/json

{
  "requests": [
    { /* request 1 */ },
    { /* request 2 */ }
  ]
}
```

### Atomicity

All requests in a batch are applied atomically:
- If any request fails, no changes are written
- Responses are returned in the same order as requests

## Presentation Object Structure

```json
{
  "presentationId": "string",
  "title": "string",
  "locale": "string",
  "pageSize": {
    "width": {"magnitude": number, "unit": "EMU"},
    "height": {"magnitude": number, "unit": "EMU"}
  },
  "slides": [Page],
  "masters": [Page],
  "layouts": [Page],
  "notesMaster": Page,
  "revisionId": "string"
}
```

## Related Documentation

- [Overview](./overview.md) - API architecture
- [Create Slide](./create-slide.md) - Adding slides
- [Batch Updates](./batch.md) - Efficient modifications
- [REST API Reference](../reference/rest-api.md) - Complete endpoints
