# Batch Updates

> **Source**: [Google Slides API - Batch](https://developers.google.com/workspace/slides/api/guides/batch)

## Overview

The Google Slides API enables developers to combine multiple requests into a single batch operation, reducing network overhead and improving application efficiency.

## Benefits

- **Performance**: Single network round-trip for multiple operations
- **Atomicity**: All requests succeed or all fail together
- **Efficiency**: One authentication for the entire batch
- **Quota**: Each batch counts as one API call

## When to Use Batching

- Initial data uploads with large datasets
- Applying formatting updates across multiple objects
- Bulk deletion operations
- Creating multiple elements in sequence

## Request Structure

```json
POST https://slides.googleapis.com/v1/presentations/{presentationId}:batchUpdate

{
  "requests": [
    { /* request 1 */ },
    { /* request 2 */ },
    { /* request 3 */ }
  ],
  "writeControl": {
    "requiredRevisionId": "revision_id"
  }
}
```

### WriteControl (Optional)

Provides optimistic locking:

```json
{
  "writeControl": {
    "requiredRevisionId": "abc123"
  }
}
```

The update fails if the presentation has been modified since the specified revision.

## Response Structure

```json
{
  "presentationId": "presentation_id",
  "replies": [
    { /* reply 1 */ },
    { /* reply 2 */ },
    { /* reply 3 */ }
  ],
  "writeControl": {
    "requiredRevisionId": "new_revision_id"
  }
}
```

Responses are returned in the same order as requests. Some requests return empty replies.

## Processing Order

**Important**: Requests are processed in order. Later requests can depend on actions taken during earlier requests.

```json
{
  "requests": [
    {
      "createSlide": {
        "objectId": "new_slide"
      }
    },
    {
      "createShape": {
        "objectId": "new_shape",
        "elementProperties": {
          "pageObjectId": "new_slide"  // References the slide created above
        },
        "shapeType": "TEXT_BOX"
      }
    },
    {
      "insertText": {
        "objectId": "new_shape",  // References the shape created above
        "text": "Hello World"
      }
    }
  ]
}
```

## Atomicity

All requests in a batch are applied atomically:
- If **any** request fails, **no** changes are written
- The entire batch is validated before execution
- Partial updates never occur

## Complete Example

### Request

```json
{
  "requests": [
    {
      "createSlide": {
        "objectId": "slide_001",
        "insertionIndex": 1,
        "slideLayoutReference": {
          "predefinedLayout": "BLANK"
        }
      }
    },
    {
      "createShape": {
        "objectId": "textbox_001",
        "shapeType": "TEXT_BOX",
        "elementProperties": {
          "pageObjectId": "slide_001",
          "size": {
            "width": {"magnitude": 6000000, "unit": "EMU"},
            "height": {"magnitude": 2000000, "unit": "EMU"}
          },
          "transform": {
            "scaleX": 1,
            "scaleY": 1,
            "translateX": 1500000,
            "translateY": 1500000,
            "unit": "EMU"
          }
        }
      }
    },
    {
      "insertText": {
        "objectId": "textbox_001",
        "text": "Hello World"
      }
    },
    {
      "updateTextStyle": {
        "objectId": "textbox_001",
        "textRange": {"type": "ALL"},
        "style": {
          "bold": true,
          "fontSize": {"magnitude": 24, "unit": "PT"}
        },
        "fields": "bold,fontSize"
      }
    }
  ]
}
```

### Response

```json
{
  "presentationId": "abc123",
  "replies": [
    {
      "createSlide": {
        "objectId": "slide_001"
      }
    },
    {
      "createShape": {
        "objectId": "textbox_001"
      }
    },
    {},
    {}
  ],
  "writeControl": {
    "requiredRevisionId": "xyz789"
  }
}
```

## Available Request Types

### Creation Requests

| Request | Creates |
|---------|---------|
| `createSlide` | New slide |
| `createShape` | Shape element |
| `createImage` | Image element |
| `createVideo` | Video element |
| `createLine` | Line element |
| `createTable` | Table element |
| `createSheetsChart` | Embedded chart |
| `createParagraphBullets` | Bulleted list |

### Modification Requests

| Request | Modifies |
|---------|----------|
| `updateShapeProperties` | Shape appearance |
| `updateImageProperties` | Image appearance |
| `updateVideoProperties` | Video appearance |
| `updateLineProperties` | Line appearance |
| `updatePageProperties` | Page settings |
| `updateSlideProperties` | Slide settings |
| `updatePageElementTransform` | Position/size |
| `updateTextStyle` | Character formatting |
| `updateParagraphStyle` | Paragraph formatting |
| `updateTableCellProperties` | Table cell appearance |
| `updateTableBorderProperties` | Table borders |
| `updateTableRowProperties` | Row height |
| `updateTableColumnProperties` | Column width |
| `updatePageElementAltText` | Accessibility |
| `updatePageElementsZOrder` | Layer order |
| `updateLineCategoryRequest` | Line category |

### Text Requests

| Request | Operation |
|---------|-----------|
| `insertText` | Add text |
| `deleteText` | Remove text |
| `replaceAllText` | Global find/replace |

### Deletion Requests

| Request | Deletes |
|---------|---------|
| `deleteObject` | Any object |
| `deleteParagraphBullets` | Bullets |
| `deleteTableRow` | Table row |
| `deleteTableColumn` | Table column |

### Other Requests

| Request | Operation |
|---------|-----------|
| `duplicateObject` | Copy object |
| `updateSlidesPosition` | Reorder slides |
| `groupObjects` | Create group |
| `ungroupObjects` | Dissolve group |
| `mergeTableCells` | Merge cells |
| `unmergeTableCells` | Split cells |
| `insertTableRows` | Add rows |
| `insertTableColumns` | Add columns |
| `refreshSheetsChart` | Update chart |
| `replaceAllShapesWithImage` | Template merge |
| `replaceAllShapesWithSheetsChart` | Template merge |
| `replaceImage` | Replace image |
| `rerouteLine` | Reroute connector |

## Error Handling

If any request fails:
1. The entire batch is rejected
2. No changes are applied
3. An error response is returned with details

```json
{
  "error": {
    "code": 400,
    "message": "Invalid objectId",
    "status": "INVALID_ARGUMENT"
  }
}
```

## Best Practices

1. **Combine related operations** into single batches
2. **Order requests correctly** when dependencies exist
3. **Use optimistic locking** for concurrent editing scenarios
4. **Keep batches reasonable** in size (hundreds, not thousands)
5. **Handle failures gracefully** with retry logic

## Related Documentation

- [Overview](./overview.md) - API architecture
- [Performance](./performance.md) - Optimization tips
- [Field Masks](./field-masks.md) - Efficient updates
