# Performance Optimization

> **Source**: [Google Slides API - Performance](https://developers.google.com/workspace/slides/api/guides/performance)

## Overview

Two primary strategies enhance application performance when working with the Google Slides API: compression and partial resources.

## Compression with gzip

Reduce bandwidth requirements by requesting gzip-encoded responses.

### Implementation

Set these HTTP headers:

```http
Accept-Encoding: gzip
User-Agent: my-app (gzip)
```

### Example Request

```http
GET https://slides.googleapis.com/v1/presentations/{presentationId}
Accept-Encoding: gzip
User-Agent: extraslide/1.0 (gzip)
```

### Trade-offs

| Aspect | Impact |
|--------|--------|
| Bandwidth | Significantly reduced |
| CPU (client) | Slight increase for decompression |
| Network latency | Reduced due to smaller payload |
| Overall | Usually net positive |

## Partial Resources

Request only the fields you need using the `fields` parameter.

### Basic Syntax

```http
GET .../presentations/{id}?fields=field1,field2
```

### Field Selection Patterns

| Pattern | Example |
|---------|---------|
| Single field | `fields=title` |
| Multiple fields | `fields=title,slides` |
| Nested field | `fields=slides/objectId` |
| Multiple nested | `fields=slides(objectId,pageElements)` |
| Sub-selection | `fields=slides/pageElements(objectId,size)` |
| Wildcard | `fields=slides/pageElements/*` |

### Examples

**Get only presentation metadata:**
```http
GET .../presentations/{id}?fields=presentationId,title,locale
```

**Get slide IDs only:**
```http
GET .../presentations/{id}?fields=slides/objectId
```

**Get page elements with transforms:**
```http
GET .../presentations/{id}?fields=slides/pageElements(objectId,transform)
```

### Response Reduction

Full request (no fields):
```json
{
  "presentationId": "...",
  "title": "...",
  "locale": "...",
  "pageSize": {...},
  "slides": [
    {
      "objectId": "...",
      "pageType": "...",
      "pageElements": [...],
      "slideProperties": {...},
      "revisionId": "..."
    }
  ],
  "masters": [...],
  "layouts": [...]
}
```

Partial request (`?fields=presentationId,slides/objectId`):
```json
{
  "presentationId": "abc123",
  "slides": [
    {"objectId": "slide_1"},
    {"objectId": "slide_2"}
  ]
}
```

## Pagination

For large result sets, combine field filtering with pagination:

```http
GET .../presentations/{id}?fields=slides(objectId)&pageSize=10&pageToken=...
```

## Batching

Combine multiple operations into single API calls:

```json
{
  "requests": [
    {"createSlide": {...}},
    {"createShape": {...}},
    {"insertText": {...}}
  ]
}
```

Benefits:
- Single network round-trip
- One authentication
- Atomic execution

See [Batch Updates](./batch.md) for details.

## Caching Strategies

### Revision-Based Caching

Use `revisionId` to detect changes:

```python
# Store the revision ID after reading
cached_revision = presentation.get('revisionId')

# Later, check if presentation changed
current = service.presentations().get(
    presentationId=presentation_id,
    fields='revisionId'
).execute()

if current.get('revisionId') != cached_revision:
    # Presentation changed, fetch full data
    pass
```

### ETag Support

Use ETags for conditional requests:

```http
GET .../presentations/{id}
If-None-Match: "etag_value"
```

Returns `304 Not Modified` if unchanged.

## Error Handling for Performance

### Exponential Backoff

For rate limit errors (429), implement exponential backoff:

```python
import time
import random

def exponential_backoff(attempt):
    wait = min(300, (2 ** attempt) + random.uniform(0, 1))
    time.sleep(wait)
```

### Batch Error Recovery

When a batch fails, identify the failing request and retry:

```python
try:
    response = service.presentations().batchUpdate(...).execute()
except HttpError as e:
    if e.resp.status == 400:
        # Parse error to find failing request
        # Remove or fix it, retry remaining requests
        pass
```

## Performance Checklist

| Optimization | Impact | Effort |
|--------------|--------|--------|
| Use field masks | High | Low |
| Enable gzip | Medium | Low |
| Batch requests | High | Medium |
| Cache with revisionId | Medium | Medium |
| Implement backoff | Medium | Low |

## Quota Considerations

| Operation | Quota Cost |
|-----------|-----------|
| presentations.get | 1 read |
| presentations.batchUpdate | 1 write |
| pages.getThumbnail | 1 expensive read |

Optimize to stay within quota limits:
- Use field masks to reduce read payload
- Batch writes to reduce API calls
- Cache thumbnail URLs (valid for 30 minutes)

## Related Documentation

- [Batch Updates](./batch.md) - Combining requests
- [Field Masks](./field-masks.md) - Efficient data retrieval
- [Overview](./overview.md) - API architecture
