# CreateImageRequest

Creates an image.

## Schema

```json
{
  "createImage": {
    "objectId": string,
    "elementProperties": [PageElementProperties],
    "url": string
  }
}
```

## Properties

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `objectId` | string | No | A user-supplied object ID. If you specify an ID, it must be unique among all pages and page eleme... |
| `elementProperties` | [PageElementProperties] | No | The element properties for the image. When the aspect ratio of the provided size does not match t... |
| `url` | string | No | The image URL. The image is fetched once at insertion time and a copy is stored for display insid... |

## Example

```json
{
  "requests": [
    {
      "createImage": {
        // Properties here
      }
    }
  ]
}
```

## Related Objects

- [PageElementProperties](../objects/page-element-properties.md)

