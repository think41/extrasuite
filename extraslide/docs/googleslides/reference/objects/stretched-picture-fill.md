# StretchedPictureFill

The stretched picture fill. The page or page element is filled entirely with the specified picture. The picture is stretched to fit its container.

## Schema

```json
{
  "contentUrl": string,
  "size": [Size]
}
```

## Properties

| Property | Type | Description |
|----------|------|-------------|
| `contentUrl` | string | Reading the content_url: An URL to a picture with a default lifetime of 30 minutes. This URL is t... |
| `size` | [Size] | The original size of the picture fill. This field is read-only. |

## Related Objects

- [Size](./size.md)

