# UpdateSlidesPositionRequest

Updates the position of slides in the presentation.

## Schema

```json
{
  "updateSlidesPosition": {
    "slideObjectIds": array of string,
    "insertionIndex": integer
  }
}
```

## Properties

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `slideObjectIds` | array of string | No | The IDs of the slides in the presentation that should be moved. The slides in this list must be i... |
| `insertionIndex` | integer | No | The index where the slides should be inserted, based on the slide arrangement before the move tak... |

## Example

```json
{
  "requests": [
    {
      "updateSlidesPosition": {
        // Properties here
      }
    }
  ]
}
```

