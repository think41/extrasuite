# DeleteTextRequest

Deletes text from a shape or a table cell.

## Schema

```json
{
  "deleteText": {
    "objectId": string,
    "cellLocation": [TableCellLocation],
    "textRange": [Range]
  }
}
```

## Properties

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `objectId` | string | No | The object ID of the shape or table from which the text will be deleted. |
| `cellLocation` | [TableCellLocation] | No | The optional table cell location if the text is to be deleted from a table cell. If present, the ... |
| `textRange` | [Range] | No | The range of text to delete, based on TextElement indexes. There is always an implicit newline ch... |

## Example

```json
{
  "requests": [
    {
      "deleteText": {
        // Properties here
      }
    }
  ]
}
```

## Related Objects

- [Range](../objects/range.md)
- [TableCellLocation](../objects/table-cell-location.md)

