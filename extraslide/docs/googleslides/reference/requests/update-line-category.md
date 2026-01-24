# UpdateLineCategoryRequest

Updates the category of a line.

## Schema

```json
{
  "updateLineCategory": {
    "objectId": string,
    "lineCategory": string
  }
}
```

## Properties

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `objectId` | string | No | The object ID of the line the update is applied to. Only a line with a category indicating it is ... |
| `lineCategory` | string | No | The line category to update to. The exact line type is determined based on the category to update... |

### lineCategory Values

| Value | Description |
|-------|-------------|
| `LINE_CATEGORY_UNSPECIFIED` | Unspecified line category. |
| `STRAIGHT` | Straight connectors, including straight connector 1. |
| `BENT` | Bent connectors, including bent connector 2 to 5. |
| `CURVED` | Curved connectors, including curved connector 2 to 5. |

## Example

```json
{
  "requests": [
    {
      "updateLineCategory": {
        // Properties here
      }
    }
  ]
}
```

