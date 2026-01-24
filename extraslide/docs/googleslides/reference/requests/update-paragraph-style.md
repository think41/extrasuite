# UpdateParagraphStyleRequest

Updates the styling for all of the paragraphs within a Shape or Table that overlap with the given text index range.

## Schema

```json
{
  "updateParagraphStyle": {
    "objectId": string,
    "cellLocation": [TableCellLocation],
    "style": [ParagraphStyle],
    "textRange": [Range],
    "fields": string
  }
}
```

## Properties

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `objectId` | string | No | The object ID of the shape or table with the text to be styled. |
| `cellLocation` | [TableCellLocation] | No | The location of the cell in the table containing the paragraph(s) to style. If `object_id` refers... |
| `style` | [ParagraphStyle] | No | The paragraph's style. |
| `textRange` | [Range] | No | The range of text containing the paragraph(s) to style. |
| `fields` | string | No | The fields that should be updated. At least one field must be specified. The root `style` is impl... |

## Example

```json
{
  "requests": [
    {
      "updateParagraphStyle": {
        // Properties here
      }
    }
  ]
}
```

## Related Objects

- [ParagraphStyle](../objects/paragraph-style.md)
- [Range](../objects/range.md)
- [TableCellLocation](../objects/table-cell-location.md)

