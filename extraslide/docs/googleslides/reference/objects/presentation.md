# Presentation

The root object representing a Google Slides presentation.

## Schema

```json
{
  "presentationId": "string",
  "title": "string",
  "locale": "string",
  "pageSize": Size,
  "slides": [Page],
  "masters": [Page],
  "layouts": [Page],
  "notesMaster": Page,
  "revisionId": "string"
}
```

## Properties

| Property | Type | Description |
|----------|------|-------------|
| `presentationId` | string | Unique identifier for the presentation |
| `title` | string | The title of the presentation |
| `locale` | string | IETF BCP 47 language tag (e.g., "en-US") |
| `pageSize` | [Size](./size.md) | Default page dimensions |
| `slides` | [Page](./page.md)[] | Array of slide pages |
| `masters` | [Page](./page.md)[] | Array of master pages |
| `layouts` | [Page](./page.md)[] | Array of layout pages |
| `notesMaster` | [Page](./page.md) | Notes master page (read-only) |
| `revisionId` | string | Revision ID for optimistic locking (output only) |

## Page Size

Standard presentation sizes:

| Type | Width (EMU) | Height (EMU) | Aspect Ratio |
|------|-------------|--------------|--------------|
| Standard (4:3) | 9144000 | 6858000 | 4:3 |
| Widescreen (16:9) | 9144000 | 5143500 | 16:9 |
| Widescreen (16:10) | 9144000 | 5715000 | 16:10 |

## Example

```json
{
  "presentationId": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
  "title": "My Presentation",
  "locale": "en",
  "pageSize": {
    "width": {"magnitude": 9144000, "unit": "EMU"},
    "height": {"magnitude": 5143500, "unit": "EMU"}
  },
  "slides": [
    {
      "objectId": "p",
      "pageType": "SLIDE",
      "pageElements": [...],
      "slideProperties": {
        "layoutObjectId": "p1_l1",
        "masterObjectId": "p1_m"
      }
    }
  ],
  "masters": [
    {
      "objectId": "p1_m",
      "pageType": "MASTER",
      "pageElements": [...]
    }
  ],
  "layouts": [
    {
      "objectId": "p1_l1",
      "pageType": "LAYOUT",
      "layoutProperties": {
        "masterObjectId": "p1_m",
        "name": "Title Slide",
        "displayName": "Title Slide"
      }
    }
  ],
  "revisionId": "ALm37BWx..."
}
```

## Reading a Presentation

```python
from googleapiclient.discovery import build

service = build('slides', 'v1', credentials=credentials)

# Get full presentation
presentation = service.presentations().get(
    presentationId='presentation_id'
).execute()

# Access properties
print(f"Title: {presentation.get('title')}")
print(f"Slides: {len(presentation.get('slides', []))}")

# With field mask (more efficient)
presentation = service.presentations().get(
    presentationId='presentation_id',
    fields='presentationId,title,slides(objectId,pageElements)'
).execute()
```

## Creating a Presentation

```python
presentation = service.presentations().create(
    body={
        'title': 'New Presentation'
    }
).execute()

print(f"Created: {presentation.get('presentationId')}")
```

## Revision ID Usage

The `revisionId` enables optimistic locking:

```python
# Read presentation
presentation = service.presentations().get(
    presentationId='presentation_id',
    fields='revisionId'
).execute()

# Update with revision check
response = service.presentations().batchUpdate(
    presentationId='presentation_id',
    body={
        'requests': [...],
        'writeControl': {
            'requiredRevisionId': presentation.get('revisionId')
        }
    }
).execute()
```

If the presentation was modified since reading, the update fails with a 409 conflict.

## Related Objects

- [Page](./page.md) - Slide, master, layout pages
- [Size](./size.md) - Page dimensions
- [PageElement](./page-element.md) - Elements on pages

## Related Documentation

- [REST API Reference](../rest-api.md) - API endpoints
- [Presentations Guide](../../guides/presentations.md) - Working with presentations
