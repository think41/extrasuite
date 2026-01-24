# REST API Reference

> **Source**: [Google Slides API REST Reference](https://developers.google.com/workspace/slides/api/reference/rest)

## Service Overview

| Property | Value |
|----------|-------|
| Service URL | `https://slides.googleapis.com` |
| API Version | v1 |
| Discovery Document | `https://slides.googleapis.com/$discovery/rest?version=v1` |

## Authentication Scopes

| Scope | Description |
|-------|-------------|
| `https://www.googleapis.com/auth/presentations` | Full access to presentations |
| `https://www.googleapis.com/auth/presentations.readonly` | Read-only access to presentations |
| `https://www.googleapis.com/auth/drive` | Full access to Drive files |
| `https://www.googleapis.com/auth/drive.file` | Access to files created by the app |
| `https://www.googleapis.com/auth/drive.readonly` | Read-only access to Drive |
| `https://www.googleapis.com/auth/spreadsheets.readonly` | Read spreadsheets (for charts) |

## Resources

### presentations

#### get

Retrieves the latest version of a presentation.

```http
GET https://slides.googleapis.com/v1/presentations/{presentationId}
```

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `presentationId` | string | Yes | The ID of the presentation |

**Response:** [Presentation](./objects/presentation.md)

**Example:**
```http
GET https://slides.googleapis.com/v1/presentations/abc123def456
```

#### create

Creates a blank presentation with the specified title.

```http
POST https://slides.googleapis.com/v1/presentations
```

**Request Body:** [Presentation](./objects/presentation.md) (only `title` and optional `presentationId`)

**Response:** [Presentation](./objects/presentation.md)

**Example:**
```json
POST https://slides.googleapis.com/v1/presentations

{
  "title": "My New Presentation"
}
```

#### batchUpdate

Applies one or more updates to a presentation atomically.

```http
POST https://slides.googleapis.com/v1/presentations/{presentationId}:batchUpdate
```

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `presentationId` | string | Yes | The presentation to update |

**Request Body:**
```json
{
  "requests": [Request],
  "writeControl": {
    "requiredRevisionId": "string"
  }
}
```

**Response:**
```json
{
  "presentationId": "string",
  "replies": [Response],
  "writeControl": {
    "requiredRevisionId": "string"
  }
}
```

See [Request Types](./requests/index.md) for all available request types.

### presentations.pages

#### get

Retrieves the latest version of a specific page.

```http
GET https://slides.googleapis.com/v1/presentations/{presentationId}/pages/{pageObjectId}
```

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `presentationId` | string | Yes | The presentation ID |
| `pageObjectId` | string | Yes | The page object ID |

**Response:** [Page](./objects/page.md)

#### getThumbnail

Generates a thumbnail image of a page.

```http
GET https://slides.googleapis.com/v1/presentations/{presentationId}/pages/{pageObjectId}/thumbnail
```

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `presentationId` | string | Yes | The presentation ID |
| `pageObjectId` | string | Yes | The page object ID |
| `thumbnailProperties.mimeType` | string | No | Image format (default: PNG) |
| `thumbnailProperties.thumbnailSize` | string | No | SMALL (200px), MEDIUM (800px), LARGE (1600px) |

**Response:**
```json
{
  "contentUrl": "string",
  "width": integer,
  "height": integer
}
```

**Note**: This counts as an expensive read request for quota purposes.

## Common Patterns

### Reading a Presentation

```python
# Python example
from googleapiclient.discovery import build

service = build('slides', 'v1', credentials=credentials)
presentation = service.presentations().get(
    presentationId='presentation_id'
).execute()
```

### Creating a Presentation

```python
presentation = service.presentations().create(
    body={'title': 'New Presentation'}
).execute()
print(f"Created: {presentation.get('presentationId')}")
```

### Batch Updating

```python
requests = [
    {'createSlide': {'objectId': 'slide_1'}},
    {'createShape': {
        'objectId': 'shape_1',
        'shapeType': 'TEXT_BOX',
        'elementProperties': {
            'pageObjectId': 'slide_1',
            'size': {'width': {'magnitude': 3000000, 'unit': 'EMU'},
                     'height': {'magnitude': 3000000, 'unit': 'EMU'}},
            'transform': {'scaleX': 1, 'scaleY': 1,
                         'translateX': 100000, 'translateY': 100000,
                         'unit': 'EMU'}
        }
    }},
    {'insertText': {'objectId': 'shape_1', 'text': 'Hello!'}}
]

response = service.presentations().batchUpdate(
    presentationId='presentation_id',
    body={'requests': requests}
).execute()
```

## Error Codes

| Code | Status | Description |
|------|--------|-------------|
| 400 | INVALID_ARGUMENT | Invalid request parameters |
| 401 | UNAUTHENTICATED | Authentication required |
| 403 | PERMISSION_DENIED | Insufficient permissions |
| 404 | NOT_FOUND | Presentation or page not found |
| 409 | ABORTED | Concurrent modification conflict |
| 429 | RESOURCE_EXHAUSTED | Rate limit exceeded |
| 500 | INTERNAL | Server error |

## Rate Limits

| Operation Type | Limit |
|----------------|-------|
| Read requests | 300 per minute per user |
| Write requests | 60 per minute per user |
| Expensive reads (thumbnails) | 6 per minute per user |

## Related Documentation

- [Object Types](./objects/index.md) - Data structures
- [Request Types](./requests/index.md) - BatchUpdate requests
- [Batch Updates](../guides/batch.md) - Usage guide
- [Performance](../guides/performance.md) - Optimization tips
