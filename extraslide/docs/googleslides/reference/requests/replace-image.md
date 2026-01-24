# ReplaceImageRequest

Replaces an existing image with a new image. Replacing an image removes some image effects from the existing image.

## Schema

```json
{
  "replaceImage": {
    "imageObjectId": string,
    "url": string,
    "imageReplaceMethod": string
  }
}
```

## Properties

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `imageObjectId` | string | No | The ID of the existing image that will be replaced. The ID can be retrieved from the response of ... |
| `url` | string | No | The image URL. The image is fetched once at insertion time and a copy is stored for display insid... |
| `imageReplaceMethod` | string | No | The replacement method. |

### imageReplaceMethod Values

| Value | Description |
|-------|-------------|
| `IMAGE_REPLACE_METHOD_UNSPECIFIED` | Unspecified image replace method. This value must not be used. |
| `CENTER_INSIDE` | Scales and centers the image to fit within the bounds of the original shape and maintains the ima... |
| `CENTER_CROP` | Scales and centers the image to fill the bounds of the original shape. The image may be cropped i... |

## Example

```json
{
  "requests": [
    {
      "replaceImage": {
        // Properties here
      }
    }
  ]
}
```

