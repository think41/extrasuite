# DeleteObjectRequest

Deletes a page or page element from the presentation.

## Schema

```json
{
  "deleteObject": {
    "objectId": "string"
  }
}
```

## Properties

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `objectId` | string | Yes | ID of the object to delete |

## What Can Be Deleted

| Object Type | Can Delete | Notes |
|-------------|------------|-------|
| Slide | Yes | Cannot delete last slide |
| Shape | Yes | |
| Image | Yes | |
| Table | Yes | |
| Line | Yes | |
| Video | Yes | |
| SheetsChart | Yes | |
| Group | Yes | Also deletes children |
| Master | No | Read-only |
| Layout | No | Read-only |
| Notes Master | No | Read-only |

## Examples

### Delete a Shape

```json
{
  "deleteObject": {
    "objectId": "shape_123"
  }
}
```

### Delete a Slide

```json
{
  "deleteObject": {
    "objectId": "slide_456"
  }
}
```

### Delete Multiple Objects

```json
{
  "requests": [
    {"deleteObject": {"objectId": "shape_1"}},
    {"deleteObject": {"objectId": "shape_2"}},
    {"deleteObject": {"objectId": "shape_3"}}
  ]
}
```

### Delete and Replace

```json
{
  "requests": [
    {
      "deleteObject": {
        "objectId": "old_shape"
      }
    },
    {
      "createShape": {
        "objectId": "new_shape",
        "shapeType": "TEXT_BOX",
        "elementProperties": {
          "pageObjectId": "slide_1",
          "size": {
            "width": {"magnitude": 3000000, "unit": "EMU"},
            "height": {"magnitude": 1000000, "unit": "EMU"}
          },
          "transform": {
            "scaleX": 1,
            "scaleY": 1,
            "translateX": 100000,
            "translateY": 100000,
            "unit": "EMU"
          }
        }
      }
    }
  ]
}
```

## Response

Empty response: `{}`

## Behavior

### Groups
- Deleting a group also deletes all elements within it
- To keep children, ungroup first with `UngroupObjectsRequest`

### Slides
- Cannot delete the last slide in a presentation
- Attempting to delete the last slide returns an error

### Placeholders
- Placeholders can be deleted
- New content won't appear in that placeholder position

### Notes Pages
- Cannot delete notes pages directly
- They are tied to their parent slide

## Error Cases

| Error | Cause |
|-------|-------|
| NOT_FOUND | Object ID doesn't exist |
| INVALID_ARGUMENT | Trying to delete protected object (master, layout) |
| FAILED_PRECONDITION | Trying to delete last slide |

## Common Patterns

### Clear Slide Content

Delete all page elements on a slide:

```python
slide = get_slide(presentation_id, slide_id)
requests = [
    {'deleteObject': {'objectId': elem['objectId']}}
    for elem in slide.get('pageElements', [])
]
service.presentations().batchUpdate(
    presentationId=presentation_id,
    body={'requests': requests}
).execute()
```

### Replace Element

```json
{
  "requests": [
    {"deleteObject": {"objectId": "old_element"}},
    {"createShape": {"objectId": "new_element", ...}}
  ]
}
```

## Notes

- Deletion is permanent within the batch
- If batch fails, no deletions occur (atomic)
- Object IDs can be reused after deletion (in subsequent batches)

## Related Requests

- [CreateShapeRequest](./create-shape.md) - Create new elements
- [DuplicateObjectRequest](./duplicate-object.md) - Copy before delete
- [UngroupObjectsRequest](./ungroup-objects.md) - Ungroup before delete

## Related Documentation

- [Page Elements](../objects/page-element.md) - Element types
- [Batch Updates Guide](../../guides/batch.md) - Request ordering
