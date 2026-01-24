# Image

A PageElement kind representing an image.

## Schema

```json
{
  "contentUrl": string,
  "imageProperties": [ImageProperties],
  "sourceUrl": string,
  "placeholder": [Placeholder]
}
```

## Properties

| Property | Type | Description |
|----------|------|-------------|
| `contentUrl` | string | An URL to an image with a default lifetime of 30 minutes. This URL is tagged with the account of ... |
| `imageProperties` | [ImageProperties] | The properties of the image. |
| `sourceUrl` | string | The source URL is the URL used to insert the image. The source URL can be empty. |
| `placeholder` | [Placeholder] | Placeholders are page elements that inherit from corresponding placeholders on layouts and master... |

## Related Objects

- [ImageProperties](./image-properties.md)
- [Placeholder](./placeholder.md)

