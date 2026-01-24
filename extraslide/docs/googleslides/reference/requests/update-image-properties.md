# UpdateImagePropertiesRequest

Update the properties of an Image.

## Schema

```json
{
  "updateImageProperties": {
    "objectId": string,
    "imageProperties": [ImageProperties],
    "fields": string
  }
}
```

## Properties

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `objectId` | string | No | The object ID of the image the updates are applied to. |
| `imageProperties` | [ImageProperties] | No | The image properties to update. |
| `fields` | string | No | The fields that should be updated. At least one field must be specified. The root `imagePropertie... |

## Example

```json
{
  "requests": [
    {
      "updateImageProperties": {
        // Properties here
      }
    }
  ]
}
```

## Related Objects

- [ImageProperties](../objects/image-properties.md)

