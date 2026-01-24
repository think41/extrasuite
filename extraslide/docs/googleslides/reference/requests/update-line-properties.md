# UpdateLinePropertiesRequest

Updates the properties of a Line.

## Schema

```json
{
  "updateLineProperties": {
    "objectId": string,
    "lineProperties": [LineProperties],
    "fields": string
  }
}
```

## Properties

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `objectId` | string | No | The object ID of the line the update is applied to. |
| `lineProperties` | [LineProperties] | No | The line properties to update. |
| `fields` | string | No | The fields that should be updated. At least one field must be specified. The root `lineProperties... |

## Example

```json
{
  "requests": [
    {
      "updateLineProperties": {
        // Properties here
      }
    }
  ]
}
```

## Related Objects

- [LineProperties](../objects/line-properties.md)

