# UpdateShapePropertiesRequest

Update the properties of a Shape.

## Schema

```json
{
  "updateShapeProperties": {
    "objectId": string,
    "shapeProperties": [ShapeProperties],
    "fields": string
  }
}
```

## Properties

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `objectId` | string | No | The object ID of the shape the updates are applied to. |
| `shapeProperties` | [ShapeProperties] | No | The shape properties to update. |
| `fields` | string | No | The fields that should be updated. At least one field must be specified. The root `shapePropertie... |

## Example

```json
{
  "requests": [
    {
      "updateShapeProperties": {
        // Properties here
      }
    }
  ]
}
```

## Related Objects

- [ShapeProperties](../objects/shape-properties.md)

