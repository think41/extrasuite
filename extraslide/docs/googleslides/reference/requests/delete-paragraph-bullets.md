# DeleteParagraphBulletsRequest

Deletes bullets from all of the paragraphs that overlap with the given text index range. The nesting level of each paragraph will be visually preserved by adding indent to the start of the corresponding paragraph.

## Schema

```json
{
  "deleteParagraphBullets": {
    "objectId": string,
    "cellLocation": [TableCellLocation],
    "textRange": [Range]
  }
}
```

## Properties

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `objectId` | string | No | The object ID of the shape or table containing the text to delete bullets from. |
| `cellLocation` | [TableCellLocation] | No | The optional table cell location if the text to be modified is in a table cell. If present, the o... |
| `textRange` | [Range] | No | The range of text to delete bullets from, based on TextElement indexes. |

## Example

```json
{
  "requests": [
    {
      "deleteParagraphBullets": {
        // Properties here
      }
    }
  ]
}
```

## Related Objects

- [Range](../objects/range.md)
- [TableCellLocation](../objects/table-cell-location.md)

